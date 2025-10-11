# -*- coding: utf-8 -*-
"""
虚拟推送数据网关

在非交易时段模拟交易时段状态，使用本地历史1分钟线数据作为虚拟推送源。
符合vnpy gateway架构，可配置起始时间点，从该时点开始模拟推送历史行情。

主要功能：
- 历史数据回放：从StorageManager读取历史1分钟K线数据
- 时间模拟：从配置的起始时间开始，按时间顺序推送
- 速度控制：支持配置推送速度倍数（1.0=实时，2.0=2倍速）
- 订阅管理：只推送订阅的品种
- vnpy标准：符合vnpy Gateway接口规范
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, Optional, Set

from vnpy.event import EventEngine
from vnpy.trader.constant import Exchange
from vnpy.trader.gateway import BaseGateway
from vnpy.trader.object import (
    CancelRequest,
    ContractData,
    OrderRequest,
    SubscribeRequest,
    TickData,
)

import pandas as pd

from .config import config_manager
from .storage import StorageManager
from .stock_fetcher import StockFetcher


class VirtualGateway(BaseGateway):
    """虚拟推送数据网关"""

    default_name = "VIRTUAL"
    default_setting = {
        "起始时间": "",  # 格式：YYYY-MM-DD HH:MM:SS
        "推送速度": 1.0,  # 1.0=实时，2.0=2倍速
        "品种列表": "",  # 逗号分隔的品种代码，留空表示使用配置文件
    }

    exchanges = [Exchange.SSE, Exchange.SZSE]  # 支持上交所和深交所

    def __init__(self, event_engine: EventEngine, gateway_name: str):
        """
        初始化虚拟网关

        Args:
            event_engine: 事件引擎
            gateway_name: 网关名称
        """
        super().__init__(event_engine, gateway_name)

        self.logger = logging.getLogger(__name__)

        # 推送配置
        self.start_datetime: Optional[datetime] = None
        self.push_speed = 1.0  # 推送速度倍数
        self.subscribed_symbols: Set[str] = set()

        # 历史数据缓存
        self.historical_data: Dict[str, pd.DataFrame] = {}

        # 推送线程
        self.push_thread: Optional[threading.Thread] = None
        self.push_active = False
        self._stop_event = threading.Event()

        # 当前推送位置（每个品种的索引）
        self.push_positions: Dict[str, int] = {}

        # 存储管理器
        self.storage_manager = StorageManager()

        self.logger.info("虚拟推送数据网关初始化完成")

    def connect(self, setting: dict) -> None:
        """
        连接网关

        Args:
            setting: 连接配置
        """
        try:
            # 解析起始时间
            start_time_str = setting.get("起始时间", "")
            if not start_time_str:
                start_time_str = config_manager.get_virtual_gateway_start_datetime()

            if not start_time_str:
                raise ValueError("必须配置虚拟推送起始时间")

            self.start_datetime = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")

            # 解析推送速度
            if "推送速度" in setting:
                self.push_speed = float(setting["推送速度"])
            else:
                self.push_speed = config_manager.get_virtual_gateway_speed()

            # 解析品种列表
            symbols_str = setting.get("品种列表", "")
            if symbols_str:
                # 从设置中获取品种列表（用户手动指定）
                self.subscribed_symbols = set(
                    s.strip() for s in symbols_str.split(",") if s.strip()
                )
                self.logger.info("使用用户指定的品种列表: %d个品种", len(self.subscribed_symbols))
            else:
                # 从本地品种缓存加载所有品种
                self.logger.info("从本地品种缓存加载品种列表...")
                stock_fetcher = StockFetcher()
                cached_stocks = stock_fetcher.load_cached_stock_list()

                if cached_stocks is None or not cached_stocks:
                    error_msg = (
                        "本地品种缓存不存在或为空！\n"
                        "请先在数据中心模块执行【重新加载品种】操作，"
                        "以获取并缓存品种列表。\n"
                        "无法启动虚拟推送网关。"
                    )
                    self.logger.error(error_msg)
                    self.write_log(error_msg)
                    raise ValueError(error_msg)

                # 合并所有市场的品种
                all_symbols = []
                for market_type, symbols in cached_stocks.items():
                    all_symbols.extend(symbols)
                    self.logger.info("  加载 %s: %d个品种", market_type, len(symbols))

                self.subscribed_symbols = set(all_symbols)
                self.logger.info("从缓存加载完成: 共%d个品种", len(self.subscribed_symbols))

            self.logger.info(
                "虚拟网关连接成功: 起始时间=%s, 推送速度=%.1fx, 订阅品种数=%d",
                self.start_datetime,
                self.push_speed,
                len(self.subscribed_symbols),
            )

            # 推送合约信息（如果有订阅的品种）
            self._push_contracts()

            # 加载历史数据
            if self.subscribed_symbols:
                self._load_historical_data()

            # 启动推送线程
            self._start_push_thread()

            self.write_log("虚拟网关连接成功")

        except Exception as e:
            self.logger.error("虚拟网关连接失败: %s", e, exc_info=True)
            self.write_log(f"虚拟网关连接失败: {e}")

    def subscribe(self, req: SubscribeRequest) -> None:
        """
        订阅行情

        Args:
            req: 订阅请求
        """
        try:
            symbol = req.symbol
            self.subscribed_symbols.add(symbol)
            self.logger.info("订阅行情: %s", symbol)

            # 加载该品种的历史数据
            self._load_symbol_data(symbol)

            self.write_log(f"订阅行情: {symbol}")

        except Exception as e:
            self.logger.error("订阅行情失败: %s", e)
            self.write_log(f"订阅行情失败: {e}")

    def close(self) -> None:
        """关闭网关"""
        try:
            # 停止推送线程
            self._stop_push_thread()

            # 清理数据
            self.historical_data.clear()
            self.push_positions.clear()

            self.logger.info("虚拟网关已关闭")
            self.write_log("虚拟网关已关闭")

        except Exception as e:
            self.logger.error("关闭虚拟网关失败: %s", e)

    # ==================== 交易接口（虚拟网关不支持交易）====================

    def send_order(self, req: OrderRequest) -> str:
        """
        委托下单（虚拟网关不支持）

        Args:
            req: 下单请求

        Returns:
            委托号（空字符串）
        """
        self.logger.warning("虚拟网关不支持交易功能: send_order")
        return ""

    def cancel_order(self, req: CancelRequest) -> None:
        """
        委托撤单（虚拟网关不支持）

        Args:
            req: 撤单请求
        """
        self.logger.warning("虚拟网关不支持交易功能: cancel_order")

    def query_account(self) -> None:
        """查询资金（虚拟网关不支持）"""
        self.logger.warning("虚拟网关不支持交易功能: query_account")

    def query_position(self) -> None:
        """查询持仓（虚拟网关不支持）"""
        self.logger.warning("虚拟网关不支持交易功能: query_position")

    def _start_push_thread(self) -> None:
        """启动推送线程"""
        if self.push_thread and self.push_thread.is_alive():
            self.logger.warning("推送线程已经在运行")
            return

        self.push_active = True
        self._stop_event.clear()

        self.push_thread = threading.Thread(
            target=self._push_loop,
            daemon=True,
            name="VirtualGatewayThread",
        )
        self.push_thread.start()

        self.logger.info("推送线程已启动")

    def _stop_push_thread(self) -> None:
        """停止推送线程"""
        if not self.push_active:
            return

        self.push_active = False
        self._stop_event.set()

        if self.push_thread and self.push_thread.is_alive():
            self.push_thread.join(timeout=5)

        self.logger.info("推送线程已停止")

    def _load_historical_data(self) -> None:
        """加载所有订阅品种的历史数据"""
        for symbol in self.subscribed_symbols:
            self._load_symbol_data(symbol)

    def _load_symbol_data(self, symbol: str) -> None:
        """
        加载单个品种的历史数据

        Args:
            symbol: 品种代码
        """
        try:
            # 从StorageManager读取1分钟线数据
            df = self.storage_manager.query_kline(
                symbol=symbol,
                interval="1m",
                start_date=self.start_datetime.date() if self.start_datetime else None,
            )

            if df is None or df.empty:
                self.logger.warning("品种 %s 没有历史数据", symbol)
                return

            # 过滤起始时间之后的数据
            if self.start_datetime and "datetime" in df.columns:
                df = df[df["datetime"] >= self.start_datetime].copy()

            if df.empty:
                self.logger.warning("品种 %s 在起始时间之后没有数据", symbol)
                return

            # 按时间排序
            df = df.sort_values("datetime")

            # 缓存数据
            self.historical_data[symbol] = df
            self.push_positions[symbol] = 0

            self.logger.info(
                "加载品种 %s 历史数据: %d 条，时间范围 %s ~ %s",
                symbol,
                len(df),
                df["datetime"].min(),
                df["datetime"].max(),
            )

        except Exception as e:
            self.logger.error("加载品种 %s 历史数据失败: %s", symbol, e)

    def _push_loop(self) -> None:
        """推送循环（在独立线程中运行）"""
        self.logger.info("推送循环开始")

        # 记录虚拟时间（模拟的当前时间）
        virtual_now = self.start_datetime

        while self.push_active and not self._stop_event.is_set():
            try:
                # 检查是否还有数据需要推送
                if not self._has_more_data():
                    self.logger.info("所有历史数据已推送完毕")
                    break

                # 推送当前时间点的所有品种数据
                pushed = self._push_current_minute(virtual_now)

                if pushed:
                    # 推进虚拟时间（1分钟）
                    virtual_now += timedelta(minutes=1)

                    # 根据推送速度计算等待时间
                    # 实时速度：等待60秒
                    # 2倍速：等待30秒
                    wait_time = 60.0 / self.push_speed
                    time.sleep(wait_time)
                else:
                    # 没有数据推送，快速前进
                    virtual_now += timedelta(minutes=1)
                    time.sleep(0.1)  # 短暂等待

            except Exception as e:
                self.logger.error("推送循环出错: %s", e, exc_info=True)
                time.sleep(1)  # 出错后等待1秒再继续

        self.logger.info("推送循环结束")

    def _has_more_data(self) -> bool:
        """
        检查是否还有数据需要推送

        Returns:
            是否还有数据
        """
        for symbol, position in self.push_positions.items():
            if symbol in self.historical_data:
                df = self.historical_data[symbol]
                if position < len(df):
                    return True
        return False

    def _push_current_minute(self, virtual_time: datetime) -> bool:
        """
        推送当前分钟的所有品种数据

        Args:
            virtual_time: 虚拟时间

        Returns:
            是否有数据被推送
        """
        pushed = False

        for symbol in self.subscribed_symbols:
            if symbol not in self.historical_data:
                continue

            df = self.historical_data[symbol]
            position = self.push_positions.get(symbol, 0)

            # 检查是否还有数据
            if position >= len(df):
                continue

            # 获取当前位置的数据
            row = df.iloc[position]
            row_time = row["datetime"]

            # 检查时间是否匹配（允许1分钟误差）
            time_diff = abs((row_time - virtual_time).total_seconds())
            if time_diff <= 60:
                # 推送该数据
                tick = self._create_tick_from_row(symbol, row)
                if tick:
                    self.on_tick(tick)
                    pushed = True

                # 更新位置
                self.push_positions[symbol] = position + 1

        return pushed

    def _create_tick_from_row(self, symbol: str, row: pd.Series) -> Optional[TickData]:
        """
        从DataFrame行创建TickData

        Args:
            symbol: 品种代码
            row: DataFrame行

        Returns:
            TickData对象
        """
        try:
            tick = TickData(
                symbol=symbol,
                exchange=Exchange.SSE if symbol.startswith("6") else Exchange.SZSE,
                datetime=row["datetime"],
                name=symbol,
                volume=float(row.get("volume", 0)),
                turnover=float(row.get("turnover", 0)),
                open_interest=0,
                last_price=float(row.get("close", 0)),
                open_price=float(row.get("open", 0)),
                high_price=float(row.get("high", 0)),
                low_price=float(row.get("low", 0)),
                pre_close=0,
                gateway_name=self.gateway_name,
            )

            return tick

        except Exception as e:
            self.logger.error("创建TickData失败: %s", e)
            return None

    def _push_contracts(self) -> None:
        """推送合约信息"""
        if not self.subscribed_symbols:
            return

        for symbol in self.subscribed_symbols:
            try:
                contract = ContractData(
                    symbol=symbol,
                    exchange=Exchange.SSE if symbol.startswith("6") else Exchange.SZSE,
                    name=symbol,
                    product=None,
                    size=1,
                    pricetick=0.01,
                    min_volume=100,
                    gateway_name=self.gateway_name,
                )

                self.on_contract(contract)

            except Exception as e:
                self.logger.error("推送合约 %s 失败: %s", symbol, e)
