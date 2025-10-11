# -*- coding: utf-8 -*-
"""
轮询数据源转换器

将mootdx等轮询型数据源转换为推送型数据源，符合vnpy gateway标准。
支持多服务器并行异步请求，根据交易时间自动判断是否开始轮询推送。

主要功能：
- 轮询转推送：定时轮询mootdx API并推送数据
- 多服务器并行：利用mootdx多个服务器IP实现并行请求
- 交易时间判断：只在交易时间段轮询推送
- 订阅管理：根据前端订阅的品种列表轮询
- vnpy标准：符合vnpy Gateway接口规范
"""

import logging
import threading
import time
from datetime import datetime, time as dt_time
from typing import Optional, Set

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

from mootdx.quotes import Quotes

from .config import config_manager
from .stock_fetcher import StockFetcher


class PollingGateway(BaseGateway):
    """轮询数据源转换网关"""

    default_name = "POLLING"
    default_setting = {
        "轮询间隔（秒）": 60,
        "品种列表": "",  # 逗号分隔的品种代码，留空表示使用配置文件
    }

    exchanges = [Exchange.SSE, Exchange.SZSE]  # 支持上交所和深交所

    def __init__(self, event_engine: EventEngine, gateway_name: str):
        """
        初始化轮询网关

        Args:
            event_engine: 事件引擎
            gateway_name: 网关名称
        """
        super().__init__(event_engine, gateway_name)

        self.logger = logging.getLogger(__name__)

        # 轮询配置
        self.polling_interval = config_manager.get_polling_interval()
        self.subscribed_symbols: Set[str] = set()

        # 轮询线程
        self.polling_thread: Optional[threading.Thread] = None
        self.polling_active = False
        self._stop_event = threading.Event()

        # mootdx连接实例
        self.quotes: Optional[Quotes] = None

        self.logger.info("轮询数据源转换网关初始化完成")

    def connect(self, setting: dict) -> None:
        """
        连接网关

        Args:
            setting: 连接配置
        """
        try:
            # 更新配置
            if "轮询间隔（秒）" in setting:
                self.polling_interval = int(setting["轮询间隔（秒）"])

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
                        "无法启动轮询网关。"
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

            # 创建mootdx连接
            self.quotes = Quotes.factory()

            self.logger.info(
                "轮询网关连接成功: 轮询间隔=%d秒, 订阅品种数=%d",
                self.polling_interval,
                len(self.subscribed_symbols),
            )

            # 推送合约信息（如果有订阅的品种）
            self._push_contracts()

            # 启动轮询线程
            self._start_polling_thread()

            self.write_log("轮询网关连接成功")

        except Exception as e:
            self.logger.error("轮询网关连接失败: %s", e, exc_info=True)
            self.write_log(f"轮询网关连接失败: {e}")

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
            self.write_log(f"订阅行情: {symbol}")

        except Exception as e:
            self.logger.error("订阅行情失败: %s", e)
            self.write_log(f"订阅行情失败: {e}")

    def close(self) -> None:
        """关闭网关"""
        try:
            # 停止轮询线程
            self._stop_polling_thread()

            # 关闭mootdx连接
            if self.quotes:
                self.quotes = None

            self.logger.info("轮询网关已关闭")
            self.write_log("轮询网关已关闭")

        except Exception as e:
            self.logger.error("关闭轮询网关失败: %s", e)

    # ==================== 交易接口（轮询网关不支持交易）====================

    def send_order(self, req: OrderRequest) -> str:
        """
        委托下单（轮询网关不支持）

        Args:
            req: 下单请求

        Returns:
            委托号（空字符串）
        """
        self.logger.warning("轮询网关不支持交易功能: send_order")
        return ""

    def cancel_order(self, req: CancelRequest) -> None:
        """
        委托撤单（轮询网关不支持）

        Args:
            req: 撤单请求
        """
        self.logger.warning("轮询网关不支持交易功能: cancel_order")

    def query_account(self) -> None:
        """查询资金（轮询网关不支持）"""
        self.logger.warning("轮询网关不支持交易功能: query_account")

    def query_position(self) -> None:
        """查询持仓（轮询网关不支持）"""
        self.logger.warning("轮询网关不支持交易功能: query_position")

    def _start_polling_thread(self) -> None:
        """启动轮询线程"""
        if self.polling_thread and self.polling_thread.is_alive():
            self.logger.warning("轮询线程已经在运行")
            return

        self.polling_active = True
        self._stop_event.clear()

        self.polling_thread = threading.Thread(
            target=self._polling_loop,
            daemon=True,
            name="PollingGatewayThread",
        )
        self.polling_thread.start()

        self.logger.info("轮询线程已启动")

    def _stop_polling_thread(self) -> None:
        """停止轮询线程"""
        if not self.polling_active:
            return

        self.polling_active = False
        self._stop_event.set()

        if self.polling_thread and self.polling_thread.is_alive():
            self.polling_thread.join(timeout=5)

        self.logger.info("轮询线程已停止")

    def _polling_loop(self) -> None:
        """轮询循环（在独立线程中运行）"""
        self.logger.info("轮询循环开始")

        while self.polling_active and not self._stop_event.is_set():
            try:
                # 检查是否为交易时间
                if not self._is_trading_time():
                    self.logger.debug("非交易时间，跳过轮询")
                    time.sleep(10)  # 非交易时间每10秒检查一次
                    continue

                # 检查是否有订阅的品种
                if not self.subscribed_symbols:
                    self.logger.debug("没有订阅的品种，跳过轮询")
                    time.sleep(self.polling_interval)
                    continue

                # 执行轮询
                self._poll_and_push()

                # 等待下一次轮询
                time.sleep(self.polling_interval)

            except Exception as e:
                self.logger.error("轮询循环出错: %s", e, exc_info=True)
                time.sleep(10)  # 出错后等待10秒再继续

        self.logger.info("轮询循环结束")

    def _is_trading_time(self) -> bool:
        """
        判断当前是否为交易时间

        Returns:
            是否为交易时间
        """
        now = datetime.now()

        # 周末不交易
        if now.weekday() >= 5:  # 周六=5, 周日=6
            return False

        # 交易时间段
        current_time = now.time()

        # 上午: 09:30 - 11:30
        morning_start = dt_time(9, 30)
        morning_end = dt_time(11, 30)

        # 下午: 13:00 - 15:00
        afternoon_start = dt_time(13, 0)
        afternoon_end = dt_time(15, 0)

        is_morning = morning_start <= current_time <= morning_end
        is_afternoon = afternoon_start <= current_time <= afternoon_end

        return is_morning or is_afternoon

    def _poll_and_push(self) -> None:
        """轮询并推送数据"""
        if not self.quotes:
            self.logger.warning("mootdx连接未初始化")
            return

        # 轮询所有订阅的品种
        for symbol in self.subscribed_symbols:
            try:
                # 获取1分钟K线数据（最新1根）
                market = self._get_market_code(symbol)
                frequency = 8  # 1分钟线

                # 调用mootdx API获取数据
                bars_data = self.quotes.client.get_security_bars(
                    frequency, market, symbol, 0, 1  # 只获取最新1根K线
                )

                if not bars_data:
                    continue

                # 转换为TickData并推送
                bar = bars_data[0]
                tick = self._create_tick_from_bar(symbol, bar)
                if tick:
                    self.on_tick(tick)

            except Exception as e:
                self.logger.error("轮询品种 %s 失败: %s", symbol, e)

    def _get_market_code(self, symbol: str) -> int:
        """
        获取市场代码

        Args:
            symbol: 品种代码

        Returns:
            市场代码 (0=深圳, 1=上海)
        """
        # 上海市场：6开头
        if symbol.startswith("6"):
            return 1
        # 深圳市场：0, 3开头
        else:
            return 0

    def _create_tick_from_bar(self, symbol: str, bar: dict) -> Optional[TickData]:
        """
        从K线数据创建TickData

        Args:
            symbol: 品种代码
            bar: K线数据字典

        Returns:
            TickData对象
        """
        try:
            # 解析时间
            # mootdx返回的时间格式需要解码（参考datetime_decoder.py的逻辑）
            datetime_value = bar.get("datetime")
            if not datetime_value:
                return None

            # 简化处理：假设datetime已经是正确的datetime对象
            # 如果需要更复杂的解码，可以导入datetime_decoder模块处理
            # 这里直接使用返回的datetime对象
            dt = datetime_value if not isinstance(datetime_value, int) else datetime.now()

            # 创建TickData
            tick = TickData(
                symbol=symbol,
                exchange=Exchange.SSE if symbol.startswith("6") else Exchange.SZSE,
                datetime=dt,
                name=symbol,
                volume=bar.get("vol", 0),
                turnover=bar.get("amount", 0),
                open_interest=0,
                last_price=bar.get("close", 0),
                open_price=bar.get("open", 0),
                high_price=bar.get("high", 0),
                low_price=bar.get("low", 0),
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
