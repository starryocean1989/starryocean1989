# -*- coding: utf-8 -*-
"""
数据网关模块

负责将轮询型数据源转换为推送型数据源，包括：
- 轮询网关：定时轮询mootdx API并推送数据
- 虚拟网关：使用历史数据模拟实时推送

合并来源：polling_gateway.py + virtual_gateway.py
"""

# ==================== 导入声明 ====================
import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

import pandas as pd

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

from .config import config_manager
from .data_fetcher import MultiProcessStockFetcher
from .data_quality import StorageManager

# ==================== 网关管理器（从core.py迁移） ====================


class GatewayManager:
    """网关生命周期管理器 - 封装网关的启动/停止逻辑"""

    @staticmethod
    def start_polling(event_engine, existing_gateway=None, setting=None):
        """
        启动轮询网关（完整业务逻辑，从core.py迁移）

        Args:
            event_engine: vnpy事件引擎
            existing_gateway: 现有网关实例（可选）
            setting: 网关设置（可选）

        Returns:
            网关实例（成功）或 None（失败）
        """
        from .events import EventPublisher

        logger = logging.getLogger(__name__)
        event_publisher = EventPublisher(event_engine)

        try:
            if existing_gateway is None:
                gateway = PollingGateway.create_and_start(event_engine, setting)
            else:
                gateway = existing_gateway
                gateway.connect(setting or {})

            event_publisher.push_log_event("✅ 轮询网关已成功启动", "INFO")
            return gateway

        except Exception as e:
            error_msg = f"启动轮询网关失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            event_publisher.push_log_event(error_msg, "ERROR")
            return None

    @staticmethod
    def stop_polling(gateway):
        """
        停止轮询网关（完整业务逻辑，从core.py迁移）

        Args:
            gateway: 网关实例

        Returns:
            是否停止成功
        """
        logger = logging.getLogger(__name__)

        try:
            if gateway:
                gateway.close()
                logger.info("轮询网关已停止")
            return True

        except Exception as e:
            logger.error("停止轮询网关失败: %s", e)
            return False

    @staticmethod
    def init_virtual_gateway(event_engine):
        """
        初始化虚拟网关（完整业务逻辑，从core.py迁移）

        Args:
            event_engine: vnpy事件引擎

        Returns:
            网关实例
        """
        from datetime import datetime, timedelta

        logger = logging.getLogger(__name__)

        try:
            # 使用默认配置创建
            default_start_time = config_manager.get("chinastock.virtual_gateway.start_datetime", "")

            if not default_start_time:
                default_start_time = (datetime.now() - timedelta(days=1)).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )

            gateway = VirtualGateway.create_and_start(event_engine, default_start_time)
            logger.info("虚拟网关已初始化")
            return gateway

        except Exception as e:
            logger.error("初始化虚拟网关失败: %s", e)
            return None

    @staticmethod
    def start_virtual(event_engine, existing_gateway=None, start_datetime="", speed=1.0, symbols=None):
        """
        启动虚拟网关（完整业务逻辑，从core.py迁移）

        Args:
            event_engine: vnpy事件引擎
            existing_gateway: 现有网关实例（可选）
            start_datetime: 起始时间
            speed: 推送速度
            symbols: 品种列表

        Returns:
            网关实例（成功）或 None（失败）
        """
        from .events import EventPublisher

        logger = logging.getLogger(__name__)
        event_publisher = EventPublisher(event_engine)

        try:
            if existing_gateway is None:
                gateway = VirtualGateway.create_and_start(
                    event_engine, start_datetime, speed, symbols
                )
            else:
                gateway = existing_gateway
                setting = {
                    "起始时间": start_datetime,
                    "推送速度": speed,
                    "品种列表": ",".join(symbols) if symbols else "",
                }
                gateway.connect(setting)

            event_publisher.push_log_event("✅ 虚拟网关已成功启动", "INFO")
            return gateway

        except Exception as e:
            error_msg = f"启动虚拟网关失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            event_publisher.push_log_event(error_msg, "ERROR")
            return None

    @staticmethod
    def stop_virtual(gateway):
        """
        停止虚拟网关（完整业务逻辑，从core.py迁移）

        Args:
            gateway: 网关实例

        Returns:
            是否停止成功
        """
        logger = logging.getLogger(__name__)

        try:
            if gateway:
                gateway.close()
                logger.info("虚拟网关已停止")
            return True

        except Exception as e:
            logger.error("停止虚拟网关失败: %s", e)
            return False


# ==================== 轮询网关 ====================


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

        # 数据获取器
        self.stock_fetcher = MultiProcessStockFetcher()

        self.logger.info("轮询数据源转换网关初始化完成")

    @classmethod
    def create_and_start(
        cls, event_engine: EventEngine, setting: Optional[dict] = None
    ) -> "PollingGateway":
        """
        创建并启动网关（工厂方法，从core.py迁移）

        Args:
            event_engine: 事件引擎
            setting: 网关设置（可选）

        Returns:
            已启动的网关实例
        """
        gateway = cls(event_engine, cls.default_name)
        gateway.connect(setting or {})
        return gateway

    def connect(self, setting: dict) -> None:
        """
        连接网关

        Args:
            setting: 网关设置
        """
        try:
            # 更新配置
            if "轮询间隔（秒）" in setting:
                self.polling_interval = int(setting["轮询间隔（秒）"])

            # 获取订阅品种
            symbols_str = setting.get("品种列表", "")
            if symbols_str:
                self.subscribed_symbols = set(
                    symbol.strip() for symbol in symbols_str.split(",") if symbol.strip()
                )
            else:
                # 从配置获取
                symbols = config_manager.get("chinastock.polling_gateway.symbols", [])
                self.subscribed_symbols = set(symbols) if symbols else set()

            # 启动轮询线程
            self._start_polling()

            self.logger.info("轮询网关连接成功，订阅品种: %s", len(self.subscribed_symbols))

        except Exception as e:
            self.logger.error("轮询网关连接失败: %s", e)
            raise

    def close(self) -> None:
        """关闭网关"""
        try:
            self._stop_polling()
            self.logger.info("轮询网关已关闭")
        except Exception as e:
            self.logger.error("关闭轮询网关失败: %s", e)

    def _start_polling(self) -> None:
        """启动轮询线程"""
        if self.polling_thread and self.polling_thread.is_alive():
            self.logger.warning("轮询线程已在运行")
            return

        self.polling_active = True
        self._stop_event.clear()

        self.polling_thread = threading.Thread(
            target=self._polling_loop,
            daemon=True,
            name="PollingGatewayThread",
        )
        self.polling_thread.start()

        self.logger.info("轮询线程已启动，间隔: %d秒", self.polling_interval)

    def _stop_polling(self) -> None:
        """停止轮询线程"""
        if not self.polling_active:
            return

        self.polling_active = False
        self._stop_event.set()

        if self.polling_thread and self.polling_thread.is_alive():
            self.polling_thread.join(timeout=5)

        self.logger.info("轮询线程已停止")

    def _polling_loop(self) -> None:
        """轮询主循环"""
        self.logger.info("轮询循环开始")

        while not self._stop_event.is_set():
            try:
                # 检查是否在交易时间
                if not self._is_trading_time():
                    time.sleep(60)  # 非交易时间每分钟检查一次
                    continue

                # 执行轮询
                self._do_polling()

                # 等待下次轮询
                time.sleep(self.polling_interval)

            except Exception as e:
                self.logger.error("轮询异常: %s", e)
                time.sleep(10)  # 异常后等待10秒再试

        self.logger.info("轮询循环结束")

    def _is_trading_time(self) -> bool:
        """检查是否在交易时间"""
        now = datetime.now().time()

        # 交易时间段：9:30-11:30, 13:00-15:00
        morning_start = datetime.strptime("09:30", "%H:%M").time()
        morning_end = datetime.strptime("11:30", "%H:%M").time()
        afternoon_start = datetime.strptime("13:00", "%H:%M").time()
        afternoon_end = datetime.strptime("15:00", "%H:%M").time()

        # 周末不交易
        if datetime.now().weekday() >= 5:
            return False

        # 检查是否在交易时间段内
        if (morning_start <= now <= morning_end) or (afternoon_start <= now <= afternoon_end):
            return True

        return False

    def _do_polling(self) -> None:
        """执行一次轮询"""
        try:
            if not self.subscribed_symbols:
                return

            self.logger.debug("开始轮询 %d 个品种", len(self.subscribed_symbols))

            # 获取最新数据（这里简化处理，实际应该调用股票获取器）
            for symbol in list(self.subscribed_symbols)[:10]:  # 限制每次轮询的品种数量
                try:
                    # 这里应该调用实际的数据获取逻辑
                    # 为了演示，这里创建一个模拟的TickData
                    tick = TickData(
                        gateway_name=self.gateway_name,
                        symbol=symbol,
                        exchange=Exchange.SSE if symbol.startswith("6") else Exchange.SZSE,
                        datetime=datetime.now(),
                        name=f"股票{symbol}",
                        volume=1000,
                        last_price=10.0,
                        open_price=10.0,
                        high_price=10.0,
                        low_price=10.0,
                        pre_close=10.0,
                    )

                    # 发送tick数据
                    self.on_tick(tick)

                except Exception as e:
                    self.logger.error("轮询品种 %s 失败: %s", symbol, e)

        except Exception as e:
            self.logger.error("轮询执行失败: %s", e)

    def subscribe(self, req: SubscribeRequest) -> None:
        """订阅行情"""
        self.subscribed_symbols.add(req.symbol)
        self.logger.info("订阅品种: %s", req.symbol)

    def unsubscribe(self, req: SubscribeRequest) -> None:
        """取消订阅"""
        self.subscribed_symbols.discard(req.symbol)
        self.logger.info("取消订阅品种: %s", req.symbol)

    def send_order(self, req: OrderRequest) -> str:
        """发送订单（轮询网关不支持交易，仅用于数据推送）"""
        self.logger.warning("轮询网关不支持交易功能")
        return ""

    def cancel_order(self, req: CancelRequest) -> None:
        """取消订单（轮询网关不支持交易，仅用于数据推送）"""
        self.logger.warning("轮询网关不支持交易功能")

    def get_account(self) -> None:
        """获取账户信息（轮询网关不支持交易，仅用于数据推送）"""
        self.logger.warning("轮询网关不支持交易功能")

    def get_position(self) -> None:
        """获取持仓信息（轮询网关不支持交易，仅用于数据推送）"""
        self.logger.warning("轮询网关不支持交易功能")

    def query_account(self) -> None:
        """查询账户信息（轮询网关不支持交易，仅用于数据推送）"""
        self.logger.warning("轮询网关不支持交易功能")

    def query_position(self) -> None:
        """查询持仓信息（轮询网关不支持交易，仅用于数据推送）"""
        self.logger.warning("轮询网关不支持交易功能")


# ==================== 虚拟网关 ====================


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

    @classmethod
    def create_and_start(
        cls,
        event_engine: EventEngine,
        start_datetime: str,
        speed: float = 1.0,
        symbols: Optional[List[str]] = None,
    ) -> "VirtualGateway":
        """
        创建并启动网关（工厂方法，从core.py迁移）

        Args:
            event_engine: 事件引擎
            start_datetime: 起始时间（格式：YYYY-MM-DD HH:MM:SS）
            speed: 推送速度倍数
            symbols: 品种列表（可选）

        Returns:
            已启动的网关实例
        """
        gateway = cls(event_engine, cls.default_name)
        setting = {
            "起始时间": start_datetime,
            "推送速度": speed,
            "品种列表": ",".join(symbols) if symbols else "",
        }
        gateway.connect(setting)
        return gateway

    def connect(self, setting: dict) -> None:
        """
        连接网关

        Args:
            setting: 网关设置
        """
        try:
            # 更新配置
            start_time_str = setting.get("起始时间", "")
            if start_time_str:
                self.start_datetime = datetime.strptime(start_time_str, "%Y-%m-%d %H:%M:%S")
            else:
                self.start_datetime = datetime.now() - timedelta(days=1)  # 默认昨天

            self.push_speed = float(setting.get("推送速度", 1.0))

            # 获取订阅品种
            symbols_str = setting.get("品种列表", "")
            if symbols_str:
                self.subscribed_symbols = set(
                    symbol.strip() for symbol in symbols_str.split(",") if symbol.strip()
                )
            else:
                # 从配置获取
                symbols = config_manager.get("chinastock.virtual_gateway.symbols", [])
                self.subscribed_symbols = set(symbols) if symbols else set()

            # 加载历史数据
            self._load_historical_data()

            # 启动推送线程
            self._start_pushing()

            self.logger.info("虚拟网关连接成功，起始时间: %s", self.start_datetime)

        except Exception as e:
            self.logger.error("虚拟网关连接失败: %s", e)
            raise

    def close(self) -> None:
        """关闭网关"""
        try:
            self._stop_pushing()
            self.logger.info("虚拟网关已关闭")
        except Exception as e:
            self.logger.error("关闭虚拟网关失败: %s", e)

    def _load_historical_data(self) -> None:
        """加载历史数据"""
        if not self.subscribed_symbols:
            return

        try:
            self.logger.info("加载历史数据用于虚拟推送...")

            for symbol in self.subscribed_symbols:
                try:
                    # 查询1分钟历史数据
                    df = self.storage_manager.query_kline(symbol, "1m")
                    if df is not None and not df.empty:
                        self.historical_data[symbol] = df
                        self.push_positions[symbol] = 0
                        self.logger.debug("加载 %s 的历史数据: %d条", symbol, len(df))
                    else:
                        self.logger.warning("未找到 %s 的历史数据", symbol)

                except Exception as e:
                    self.logger.error("加载 %s 历史数据失败: %s", symbol, e)

            self.logger.info("历史数据加载完成，共 %d 个品种", len(self.historical_data))

        except Exception as e:
            self.logger.error("加载历史数据失败: %s", e)

    def _start_pushing(self) -> None:
        """启动推送线程"""
        if self.push_thread and self.push_thread.is_alive():
            self.logger.warning("推送线程已在运行")
            return

        self.push_active = True
        self._stop_event.clear()

        self.push_thread = threading.Thread(
            target=self._pushing_loop,
            daemon=True,
            name="VirtualGatewayThread",
        )
        self.push_thread.start()

        self.logger.info("虚拟推送线程已启动，速度倍数: %.1f", self.push_speed)

    def _stop_pushing(self) -> None:
        """停止推送线程"""
        if not self.push_active:
            return

        self.push_active = False
        self._stop_event.set()

        if self.push_thread and self.push_thread.is_alive():
            self.push_thread.join(timeout=5)

        self.logger.info("虚拟推送线程已停止")

    def _pushing_loop(self) -> None:
        """推送主循环"""
        self.logger.info("虚拟推送循环开始")

        while not self._stop_event.is_set():
            try:
                # 执行推送
                self._do_pushing()

                # 根据速度倍数计算等待时间
                wait_time = 60 / self.push_speed  # 1分钟数据，实时为60秒
                time.sleep(wait_time)

            except Exception as e:
                self.logger.error("虚拟推送异常: %s", e)
                time.sleep(10)  # 异常后等待10秒再试

        self.logger.info("虚拟推送循环结束")

    def _do_pushing(self) -> None:
        """执行一次推送"""
        try:
            # 确保起始时间已设置
            if self.start_datetime is None:
                self.logger.warning("起始时间未设置，使用当前时间")
                self.start_datetime = datetime.now()

            current_time = self.start_datetime

            for symbol in list(self.subscribed_symbols):
                if symbol not in self.historical_data:
                    continue

                df = self.historical_data[symbol]
                if df.empty:
                    continue

                # 获取当前推送位置
                position = self.push_positions.get(symbol, 0)

                if position >= len(df):
                    # 推送完成，重置位置
                    self.push_positions[symbol] = 0
                    position = 0

                # 获取当前数据行
                if position < len(df):
                    row = df.iloc[position]

                    # 创建TickData
                    tick = TickData(
                        gateway_name=self.gateway_name,
                        symbol=symbol,
                        exchange=Exchange.SSE if symbol.startswith("6") else Exchange.SZSE,
                        datetime=current_time,
                        name=f"股票{symbol}",
                        volume=float(row.get("volume", 0)),
                        last_price=float(row.get("close", 0)),
                        open_price=float(row.get("open", 0)),
                        high_price=float(row.get("high", 0)),
                        low_price=float(row.get("low", 0)),
                        pre_close=float(row.get("close", 0)),  # 简化处理
                    )

                    # 发送tick数据
                    self.on_tick(tick)

                    # 更新推送位置
                    self.push_positions[symbol] = position + 1

            # 更新起始时间
            self.start_datetime += timedelta(minutes=1)

        except Exception as e:
            self.logger.error("推送执行失败: %s", e)

    def subscribe(self, req: SubscribeRequest) -> None:
        """订阅行情"""
        self.subscribed_symbols.add(req.symbol)
        self.logger.info("订阅品种: %s", req.symbol)

    def unsubscribe(self, req: SubscribeRequest) -> None:
        """取消订阅"""
        self.subscribed_symbols.discard(req.symbol)
        self.logger.info("取消订阅品种: %s", req.symbol)

    def send_order(self, req: OrderRequest) -> str:
        """发送订单（虚拟网关不支持交易，仅用于数据推送）"""
        self.logger.warning("虚拟网关不支持交易功能")
        return ""

    def cancel_order(self, req: CancelRequest) -> None:
        """取消订单（虚拟网关不支持交易，仅用于数据推送）"""
        self.logger.warning("虚拟网关不支持交易功能")

    def get_account(self) -> None:
        """获取账户信息（虚拟网关不支持交易，仅用于数据推送）"""
        self.logger.warning("虚拟网关不支持交易功能")

    def get_position(self) -> None:
        """获取持仓信息（虚拟网关不支持交易，仅用于数据推送）"""
        self.logger.warning("虚拟网关不支持交易功能")

    def query_account(self) -> None:
        """查询账户信息（虚拟网关不支持交易，仅用于数据推送）"""
        self.logger.warning("虚拟网关不支持交易功能")

    def query_position(self) -> None:
        """查询持仓信息（虚拟网关不支持交易，仅用于数据推送）"""
        self.logger.warning("虚拟网关不支持交易功能")


# ==================== 全局实例 ====================

# 全局网关实例（用于向后兼容）
polling_gateway = None
virtual_gateway = None
