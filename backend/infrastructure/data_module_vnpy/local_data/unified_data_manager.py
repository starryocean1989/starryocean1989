# -*- coding: utf-8 -*-
"""
统一数据管理器 - 数据管理中枢

提供完整的数据管理服务，包括：
1. TDX数据源（请求/推送双模式）- 连接通达信API
2. 虚拟数据源（回测模拟）- 历史数据模拟推送
3. 外部网关适配（CTP、IB等真实交易网关）
4. 数据融合（本地存储 + 录制 + 实时）
5. 查询式服务（给行情看板、策略中心）
6. 订阅式服务（给交易策略）
7. 预加载优化

合并来源：
- unified_data_manager.py（原统一数据管理器）
- gateways.py（轮询网关、虚拟网关）
"""

from __future__ import annotations

import asyncio
import logging
import random
import threading
import time
from collections import deque
from datetime import date, datetime, timedelta
from threading import Lock, Thread
from typing import (
    Any,
    Deque,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    TYPE_CHECKING,
    Union,
    cast,
)

import pandas as pd
from pandas import Timestamp

from vnpy.event import EventEngine
from vnpy.trader.constant import Exchange
from vnpy.trader.gateway import BaseGateway
from vnpy.trader.object import (
    BarData,
    CancelRequest,
    ContractData,
    OrderRequest,
    SubscribeRequest,
    TickData,
)
from vnpy.trader.constant import Interval, Product

from backend.infrastructure.tdx_asyncio.async_hq import AsyncTdxHq_API
from backend.infrastructure.data_module_vnpy.load_balancer import ServerPoolManager

from ..config import config_manager
from ..load_balancer import (
    NetworkTask,
    LocalProcessingTask,
    TaskMetrics,
    TaskType,
    ResourceProfile,
)

if TYPE_CHECKING:  # pragma: no cover
    from ..core import ChinaStockEngine


# ==================== LoadBalancer任务类定义 ====================


class RealtimePollingTask(NetworkTask):
    """实时行情轮询任务"""

    def __init__(self, name: str, subscribed_count: int = 0):
        """初始化实时行情轮询任务

        Args:
            name: 任务名称
            subscribed_count: 订阅的品种数量
        """
        super().__init__(name)
        self.subscribed_count = subscribed_count
        # 更新预估连接数：通常1个连接可以查询多个品种
        self.metrics.estimated_connections = max(1, subscribed_count // 100)

    def _define_metrics(self) -> TaskMetrics:
        return TaskMetrics(
            task_name="realtime_polling",
            task_type=TaskType.NETWORK,
            resource_profile=ResourceProfile.NETWORK_IO_INTENSIVE,
            critical_metrics=[
                "network_speed",
                "packet_loss_rate",
                "event_queue_depth",
                "websocket_message_backlog",
            ],
            estimated_duration=0,  # 持续运行
            estimated_memory_mb=50,  # 约50MB
            estimated_connections=1,  # 默认值，会在__init__中更新
        )

    def execute(self, config: Dict[str, Any]) -> Any:
        """执行实时轮询（占位方法）

        实际轮询由TdxDataSource._polling_loop执行。
        """
        return None


class VirtualReplayTask(LocalProcessingTask):
    """虚拟推送回放任务"""

    def __init__(self, name: str, replay_speed: float = 1.0):
        """初始化虚拟推送回放任务

        Args:
            name: 任务名称
            replay_speed: 回放速度倍数
        """
        super().__init__(name)
        self.replay_speed = replay_speed
        # 更新预估工作数：根据回放速度
        self.metrics.estimated_workers = min(4, max(1, int(replay_speed)))

    def _define_metrics(self) -> TaskMetrics:
        return TaskMetrics(
            task_name="virtual_replay",
            task_type=TaskType.LOCAL_PROCESSING,
            resource_profile=ResourceProfile.MIXED,  # 内存+CPU
            critical_metrics=[
                "memory_percent",
                "event_queue_depth",
                "cpu_percent",
            ],
            estimated_duration=0,  # 持续运行
            estimated_memory_mb=200,  # 约200MB（历史数据缓存）
            estimated_workers=1,  # 默认值，会在__init__中更新
        )

    def execute(self, config: Dict[str, Any]) -> Any:
        """执行虚拟回放（占位方法）

        实际回放由VirtualDataSource的推送线程执行。
        """
        return None


class PreloadTask(LocalProcessingTask):
    """数据预加载任务"""

    def __init__(self, name: str, symbols_count: int = 0):
        """初始化数据预加载任务

        Args:
            name: 任务名称
            symbols_count: 待预加载的品种数量
        """
        super().__init__(name)
        self.symbols_count = symbols_count
        # 更新预估工作数：根据品种数量
        if symbols_count < 10:
            self.metrics.estimated_workers = 1
        elif symbols_count < 50:
            self.metrics.estimated_workers = 2
        else:
            self.metrics.estimated_workers = 4

    def _define_metrics(self) -> TaskMetrics:
        return TaskMetrics(
            task_name="data_preload",
            task_type=TaskType.LOCAL_PROCESSING,
            resource_profile=ResourceProfile.MIXED,  # 磁盘I/O + 内存
            critical_metrics=[
                "disk_io_speed",
                "memory_percent",
                "average_io_latency_ms",
            ],
            estimated_duration=30,  # 预计30秒
            estimated_memory_mb=100,  # 约100MB
            estimated_workers=1,  # 默认值，会在__init__中更新
        )

    def execute(self, config: Dict[str, Any]) -> Any:
        """执行数据预加载（占位方法）

        实际预加载由PreloadService._run执行。
        """
        return None


# ==================== 数据源适配器（TDX数据源） ====================


class TdxDataSource(BaseGateway):
    """TDX数据源 - 请求/推送双模式（集成ServerPoolManager和真实tdx_asyncio API）

    职责：
    - 集成ServerPoolManager获取最优服务器
    - 使用AsyncTdxHq_API获取真实行情数据
    - 权重轮询负载均衡
    - tick数据推送

    特点：
    - 智能服务器选择（权重轮询）
    - 交易时间自动轮询
    - 真实API调用（get_security_quotes）
    - 支持推送和请求双模式
    """

    default_name = "TDX"
    default_setting = {
        "轮询间隔（秒）": 3,
        "品种列表": "",  # 逗号分隔的品种代码，留空表示使用配置文件
        "最大服务器数": 5,  # 使用的最优服务器数量
    }

    exchanges = [Exchange.SSE, Exchange.SZSE]  # 支持上交所和深交所

    def __init__(self, event_engine: EventEngine, gateway_name: str):
        """
        初始化TDX数据源

        Args:
            event_engine: 事件引擎
            gateway_name: 网关名称
        """
        super().__init__(event_engine, gateway_name)

        self.logger = logging.getLogger(__name__)

        # 服务器池管理器（单例）
        self.server_pool_manager = ServerPoolManager()

        # AsyncTdxHq_API连接池（对应多个服务器）
        self._api_connections: Dict[str, AsyncTdxHq_API] = {}  # {server_key: api}
        self._server_weights: List[float] = []  # 服务器权重（基于响应时间）

        # 订阅管理
        self._subscribed_symbols: Set[str] = set()
        self._polling_interval = 3.0  # 轮询间隔（秒）
        self._polling_thread: Optional[Thread] = None
        self._polling_stop = False

        # 事件循环（用于异步调用）
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread: Optional[Thread] = None

        self.logger.info("TDX数据源初始化完成")

    @classmethod
    def create_and_start(
        cls, event_engine: EventEngine, setting: Optional[dict] = None
    ) -> "TdxDataSource":
        """
        创建并启动TDX数据源（工厂方法）

        Args:
            event_engine: 事件引擎
            setting: 网关设置（可选）

        Returns:
            已启动的TDX数据源实例
        """
        gateway = cls(event_engine, cls.default_name)
        gateway.connect(setting or {})
        return gateway

    def connect(self, setting: Optional[dict] = None) -> None:
        """
        连接TDX数据源

        Args:
            setting: 网关设置
                - polling_interval: 轮询间隔（秒）
                - symbols: 预订阅品种列表
                - max_servers: 最大使用服务器数量
        """
        if setting is None:
            setting = {}

        if self.server_pool_manager._running and self._api_connections:
            self.logger.info("TDX数据源已连接")
            return

        # 启动服务器池管理器
        if not self.server_pool_manager.start():
            self.logger.error("服务器池启动失败")
            return

        # 获取最优服务器列表（已排序）
        try:
            max_servers = setting.get("max_servers", 5)
            if "最大服务器数" in setting:
                max_servers = int(setting["最大服务器数"])

            sorted_servers = self.server_pool_manager.get_servers(count=max_servers)
            if not sorted_servers:
                self.logger.error("无可用服务器")
                return

            # 转换为包含响应时间的格式（假设响应时间为索引的倍数）
            top_servers = [
                (host, port, 0.05 + idx * 0.01)  # 假设响应时间从0.05秒递增
                for idx, (host, port) in enumerate(sorted_servers)
            ]
        except Exception as e:
            self.logger.error("获取服务器列表失败: %s", e)
            return

        # 计算服务器权重（基于响应时间的倒数）
        self._calculate_server_weights(top_servers)

        # 启动异步事件循环线程
        self._start_event_loop()

        # 创建API连接（每个服务器一个）
        if self._loop is not None:
            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._create_api_connections(top_servers), self._loop
                )
                future.result(timeout=10)
            except Exception as e:
                self.logger.error("创建API连接失败: %s", e)
                return
        else:
            self.logger.error("事件循环未启动")
            return

        # 更新配置
        if "轮询间隔（秒）" in setting:
            self._polling_interval = float(setting["轮询间隔（秒）"])
        elif "polling_interval" in setting:
            self._polling_interval = float(setting["polling_interval"])

        # 获取订阅品种
        symbols_str = setting.get("品种列表", "")
        if symbols_str:
            self._subscribed_symbols = set(
                symbol.strip() for symbol in symbols_str.split(",") if symbol.strip()
            )
        elif "symbols" in setting and setting["symbols"]:
            self._subscribed_symbols = set(setting["symbols"])
        else:
            # 从配置获取
            symbols = config_manager.get("chinastock.tdx_source.symbols", [])
            if not symbols:
                # 兼容旧配置
                symbols = config_manager.get("chinastock.polling_gateway.symbols", [])
            self._subscribed_symbols = set(symbols) if symbols else set()

        # 启动轮询线程（如果有订阅品种）
        if self._subscribed_symbols:
            self._start_polling()

        self.logger.info(
            "TDX数据源已连接，使用%d个服务器，订阅%d个品种",
            len(top_servers),
            len(self._subscribed_symbols),
        )

    def close(self) -> None:
        """关闭TDX数据源"""
        try:
            self._stop_polling()

            # 关闭所有API连接
            if self._loop:
                future = asyncio.run_coroutine_threadsafe(self._close_api_connections(), self._loop)
                future.result(timeout=5)

            # 停止事件循环
            self._stop_event_loop()

            self.logger.info("TDX数据源已关闭")
        except Exception as e:
            self.logger.error("关闭TDX数据源失败: %s", e)

    def _start_event_loop(self) -> None:
        """启动异步事件循环线程"""
        if self._loop_thread and self._loop_thread.is_alive():
            return

        def run_event_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._loop_thread = Thread(target=run_event_loop, daemon=True, name="TdxEventLoop")
        self._loop_thread.start()

        # 等待事件循环启动
        while self._loop is None:
            time.sleep(0.01)

        self.logger.info("异步事件循环线程已启动")

    def _stop_event_loop(self) -> None:
        """停止异步事件循环线程"""
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._loop_thread:
                self._loop_thread.join(timeout=3)
            self.logger.info("异步事件循环线程已停止")

    def _calculate_server_weights(self, servers: List[Tuple[str, int, float]]) -> None:
        """
        计算服务器权重（基于响应时间）

        权重计算公式：weight = 1 / response_time
        最快服务器权重最高，被选中概率最大
        """
        if not servers:
            return

        # 提取响应时间
        response_times = [s[2] for s in servers]

        # 计算权重（响应时间的倒数）
        raw_weights = [1.0 / (rt + 0.001) for rt in response_times]  # +0.001防止除零

        # 归一化权重（和为1）
        total = sum(raw_weights)
        self._server_weights = [w / total for w in raw_weights]

        self.logger.info("服务器权重: %s", [f"{w:.3f}" for w in self._server_weights])

    def _weighted_round_robin_select(self) -> Optional[str]:
        """
        权重轮询选择服务器

        采用加权轮询算法：
        - 最快服务器有更高概率被选中
        - 保证所有服务器都能被使用（负载均衡）
        """
        if not self._api_connections or not self._server_weights:
            return None

        # 使用累积权重选择
        rand = random.random()
        cumulative = 0.0

        server_keys = list(self._api_connections.keys())
        for i, weight in enumerate(self._server_weights):
            cumulative += weight
            if rand <= cumulative:
                return server_keys[i]

        # 兜底返回最后一个
        return server_keys[-1]

    async def _create_api_connections(self, servers: List[Tuple[str, int, float]]) -> None:
        """创建多个AsyncTdxHq_API连接"""
        for server in servers:
            host, port, response_time = server
            server_key = f"{host}:{port}"

            try:
                api = AsyncTdxHq_API()
                await api.connect(host, port, time_out=5.0)
                await api.setup()

                self._api_connections[server_key] = api
                self.logger.info("已连接服务器: %s (响应时间: %.3fs)", server_key, response_time)
            except Exception as e:
                self.logger.warning("连接服务器失败: %s, %s", server_key, e)

    async def _close_api_connections(self) -> None:
        """关闭所有API连接"""
        for server_key, api in self._api_connections.items():
            try:
                await api.close()
                self.logger.debug("已关闭服务器连接: %s", server_key)
            except Exception as e:
                self.logger.warning("关闭服务器连接失败: %s, %s", server_key, e)
        self._api_connections.clear()

    def _start_polling(self) -> None:
        """启动轮询线程"""
        if self._polling_thread and self._polling_thread.is_alive():
            return

        self._polling_stop = False
        self._polling_thread = Thread(target=self._polling_loop, daemon=True, name="TdxPolling")
        self._polling_thread.start()

        self.logger.info("TDX轮询线程已启动，间隔: %s秒", self._polling_interval)

    def _stop_polling(self) -> None:
        """停止轮询线程"""
        if not self._polling_thread:
            return

        self._polling_stop = True
        if self._polling_thread.is_alive():
            self._polling_thread.join(timeout=5)

        self.logger.info("TDX轮询线程已停止")

    def _polling_loop(self) -> None:
        """轮询循环（在独立线程中运行）"""
        self.logger.info("TDX轮询循环开始")

        while not self._polling_stop:
            try:
                # 检查是否在交易时间
                if not self._is_trading_time():
                    time.sleep(60)  # 非交易时间每分钟检查一次
                    continue

                # 权重轮询选择服务器
                server_key = self._weighted_round_robin_select()
                if not server_key:
                    self.logger.warning("无可用服务器")
                    time.sleep(self._polling_interval)
                    continue

                api = self._api_connections.get(server_key)
                if not api:
                    time.sleep(self._polling_interval)
                    continue

                # 异步调用 get_security_quotes
                if self._loop is not None:
                    future = asyncio.run_coroutine_threadsafe(
                        self._fetch_realtime_data(api, server_key), self._loop
                    )
                    future.result(timeout=5.0)
                else:
                    self.logger.error("事件循环未启动")

            except Exception as e:
                self.logger.error("轮询失败: %s", e)

            # 等待下一次轮询
            time.sleep(self._polling_interval)

        self.logger.info("TDX轮询循环结束")

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

    async def _fetch_realtime_data(self, api: AsyncTdxHq_API, server_key: str) -> None:
        """
        从tdx获取实时行情数据

        使用 get_security_quotes() 批量获取（最多80只）
        """
        if not self._subscribed_symbols:
            return

        # 转换品种格式：000001.SZ → (0, "000001")
        stocks = []
        for symbol in self._subscribed_symbols:
            try:
                if "." in symbol:
                    code, exchange_str = symbol.split(".")
                    market = 0 if exchange_str.upper() in ("SZ", "SZSE") else 1  # 0=深圳, 1=上海
                else:
                    # 如果没有交易所后缀，根据代码推断
                    code = symbol
                    if code.startswith("6"):
                        market = 1  # 上海
                    else:
                        market = 0  # 深圳
                stocks.append((market, code))
            except Exception as e:
                self.logger.error("解析品种格式失败: %s, %s", symbol, e)

        if not stocks:
            return

        try:
            # 调用真实API（最多80只）
            quotes = await api.get_security_quotes(stocks[:80])

            # 检查返回值
            if quotes is None:
                self.logger.warning("从 %s 获取行情返回 None", server_key)
                return

            # 转换为TickData并推送
            for quote in quotes:
                tick = self._convert_to_tick(quote)
                if tick:
                    self.on_tick(tick)

            self.logger.debug("从 %s 获取 %d 个行情", server_key, len(quotes))

        except Exception as e:
            self.logger.error("获取实时数据失败 (%s): %s", server_key, e)
            # 自动切换到下一个服务器（轮询会自动处理）

    def _convert_to_tick(self, quote: dict) -> Optional[TickData]:
        """
        将tdx行情数据转换为vnpy TickData

        tdx字段：code, price, open, high, low, last_close, vol, amount,
                bid1-bid5, ask1-ask5, bid_vol1-bid_vol5, ask_vol1-ask_vol5
        """
        try:
            code = quote["code"]
            # 推断交易所
            if code.startswith(("0", "3")):
                exchange = Exchange.SZSE
            elif code.startswith("6"):
                exchange = Exchange.SSE
            else:
                exchange = Exchange.SZSE  # 默认深圳

            symbol = code

            tick = TickData(
                gateway_name=self.gateway_name,
                symbol=symbol,
                exchange=exchange,
                datetime=datetime.now(),
                # 价格字段
                last_price=quote.get("price", 0),
                open_price=quote.get("open", 0),
                high_price=quote.get("high", 0),
                low_price=quote.get("low", 0),
                pre_close=quote.get("last_close", 0),
                # 成交量字段
                volume=quote.get("vol", 0),
                turnover=quote.get("amount", 0),
                # 盘口字段
                bid_price_1=quote.get("bid1", 0),
                bid_price_2=quote.get("bid2", 0),
                bid_price_3=quote.get("bid3", 0),
                bid_price_4=quote.get("bid4", 0),
                bid_price_5=quote.get("bid5", 0),
                ask_price_1=quote.get("ask1", 0),
                ask_price_2=quote.get("ask2", 0),
                ask_price_3=quote.get("ask3", 0),
                ask_price_4=quote.get("ask4", 0),
                ask_price_5=quote.get("ask5", 0),
                bid_volume_1=quote.get("bid_vol1", 0),
                bid_volume_2=quote.get("bid_vol2", 0),
                bid_volume_3=quote.get("bid_vol3", 0),
                bid_volume_4=quote.get("bid_vol4", 0),
                bid_volume_5=quote.get("bid_vol5", 0),
                ask_volume_1=quote.get("ask_vol1", 0),
                ask_volume_2=quote.get("ask_vol2", 0),
                ask_volume_3=quote.get("ask_vol3", 0),
                ask_volume_4=quote.get("ask_vol4", 0),
                ask_volume_5=quote.get("ask_vol5", 0),
            )

            return tick

        except Exception as e:
            self.logger.error("转换TickData失败: %s, quote=%s", e, quote)
            return None

    def subscribe(self, req: SubscribeRequest) -> None:
        """订阅实时数据"""
        symbol = req.symbol

        if symbol in self._subscribed_symbols:
            return

        self._subscribed_symbols.add(symbol)
        self.logger.info("订阅: %s", symbol)

        # 启动轮询（如果未启动）
        if not self._polling_thread or not self._polling_thread.is_alive():
            self._start_polling()

    def unsubscribe(self, req: SubscribeRequest) -> None:
        """取消订阅"""
        symbol = req.symbol
        self._subscribed_symbols.discard(symbol)
        self.logger.info("取消订阅: %s", symbol)

    def send_order(self, req: OrderRequest) -> str:
        """发送订单（TDX数据源不支持交易，仅用于数据推送）"""
        self.logger.warning("TDX数据源不支持交易功能")
        return ""

    def cancel_order(self, req: CancelRequest) -> None:
        """取消订单（TDX数据源不支持交易，仅用于数据推送）"""
        self.logger.warning("TDX数据源不支持交易功能")

    def query_account(self) -> None:
        """查询账户信息（TDX数据源不支持交易，仅用于数据推送）"""
        self.logger.warning("TDX数据源不支持交易功能")

    def query_position(self) -> None:
        """查询持仓信息（TDX数据源不支持交易，仅用于数据推送）"""
        self.logger.warning("TDX数据源不支持交易功能")


# ==================== 数据源适配器（虚拟数据源） ====================


class VirtualDataSource(BaseGateway):
    """虚拟数据源（原VirtualGateway）- 回测模拟

    职责：
    - 加载历史数据
    - 模拟实时推送
    - 回测数据提供

    特点：
    - 可配置起始时间
    - 可调节推送速度
    - 支持历史回放
    """

    default_name = "VIRTUAL"
    default_setting = {
        "起始时间": "",  # 格式：YYYY-MM-DD HH:MM:SS
        "推送速度": 1.0,  # 1.0=实时，2.0=2倍速
        "品种列表": "",  # 逗号分隔的品种代码，留空表示使用配置文件
    }

    exchanges = [Exchange.SSE, Exchange.SZSE]  # 支持上交所和深交所

    def __init__(self, event_engine: EventEngine, gateway_name: str):
        """
        初始化虚拟数据源

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
        self._pause_event = threading.Event()  # 暂停事件

        # 当前推送位置（每个品种的索引）
        self.push_positions: Dict[str, int] = {}

        # 当前时间（用于回放控制）
        self._current_datetime: Optional[datetime] = None

        # 存储管理器（延迟导入）
        self.storage_manager = None

        # 暂停状态
        self._is_paused = False

        self.logger.info("虚拟数据源初始化完成")

    @classmethod
    def create_and_start(
        cls,
        event_engine: EventEngine,
        start_datetime: str,
        speed: float = 1.0,
        symbols: Optional[List[str]] = None,
    ) -> "VirtualDataSource":
        """
        创建并启动虚拟数据源（工厂方法）

        Args:
            event_engine: 事件引擎
            start_datetime: 起始时间（格式：YYYY-MM-DD HH:MM:SS）
            speed: 推送速度倍数
            symbols: 品种列表（可选）

        Returns:
            已启动的虚拟数据源实例
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
        连接虚拟数据源

        Args:
            setting: 网关设置
        """
        try:
            # 延迟导入StorageManager
            if self.storage_manager is None:
                from ..local_data.data_quality import StorageManager

                self.storage_manager = StorageManager()

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
                symbols = config_manager.get("chinastock.virtual_source.symbols", [])
                if not symbols:
                    # 兼容旧配置
                    symbols = config_manager.get("chinastock.virtual_gateway.symbols", [])
                self.subscribed_symbols = set(symbols) if symbols else set()

            # 加载历史数据
            self._load_historical_data()

            # 启动推送线程
            self._start_pushing()

            self.logger.info("虚拟数据源连接成功，起始时间: %s", self.start_datetime)

        except Exception as e:
            self.logger.error("虚拟数据源连接失败: %s", e)
            raise

    def close(self) -> None:
        """关闭虚拟数据源"""
        try:
            self._stop_pushing()
            self.logger.info("虚拟数据源已关闭")
        except Exception as e:
            self.logger.error("关闭虚拟数据源失败: %s", e)

    def _load_historical_data(self) -> None:
        """加载历史数据"""
        if not self.subscribed_symbols:
            return

        try:
            self.logger.info("加载历史数据用于虚拟推送...")

            for symbol in self.subscribed_symbols:
                try:
                    # 查询1分钟历史数据
                    if self.storage_manager is not None:
                        df = self.storage_manager.query_kline(symbol, "1m")
                        if df is not None and not df.empty:
                            self.historical_data[symbol] = df
                            self.push_positions[symbol] = 0
                            self.logger.debug("加载 %s 的历史数据: %d条", symbol, len(df))
                        else:
                            self.logger.warning("未找到 %s 的历史数据", symbol)
                    else:
                        self.logger.warning("StorageManager未初始化")

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
            name="VirtualDataSourceThread",
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
                # 检查暂停状态
                if self._is_paused:
                    self._pause_event.wait(timeout=0.1)
                    continue

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
            self.logger.error("虚拟推送执行失败: %s", e)

    def subscribe(self, req: SubscribeRequest) -> None:
        """订阅行情"""
        self.subscribed_symbols.add(req.symbol)
        self.logger.info("订阅品种: %s", req.symbol)

    def unsubscribe(self, req: SubscribeRequest) -> None:
        """取消订阅"""
        self.subscribed_symbols.discard(req.symbol)
        self.logger.info("取消订阅品种: %s", req.symbol)

    def send_order(self, req: OrderRequest) -> str:
        """发送订单（虚拟数据源不支持交易，仅用于数据推送）"""
        self.logger.warning("虚拟数据源不支持交易功能")
        return ""

    def cancel_order(self, req: CancelRequest) -> None:
        """取消订单（虚拟数据源不支持交易，仅用于数据推送）"""
        self.logger.warning("虚拟数据源不支持交易功能")

    def query_account(self) -> None:
        """查询账户信息（虚拟数据源不支持交易，仅用于数据推送）"""
        self.logger.warning("虚拟数据源不支持交易功能")

    def query_position(self) -> None:
        """查询持仓信息（虚拟数据源不支持交易，仅用于数据推送）"""
        self.logger.warning("虚拟数据源不支持交易功能")

    # ===== 回放控制功能 =====

    def pause(self) -> None:
        """暂停推送"""
        if not self._is_paused:
            self._is_paused = True
            self._pause_event.clear()
            self.logger.info("虚拟数据源已暂停")

    def resume(self) -> None:
        """恢复推送"""
        if self._is_paused:
            self._is_paused = False
            self._pause_event.set()
            self.logger.info("虚拟数据源已恢复")

    def set_speed(self, speed: float) -> None:
        """
        设置推送速度

        Args:
            speed: 速度倍率（1.0=实时，10.0=10倍速，100.0=100倍速）
        """
        self.push_speed = max(0.1, min(1000.0, speed))  # 限制在0.1x到1000x之间
        self.logger.info("虚拟数据源速度已设置为: %sx", self.push_speed)

    def jump_to_datetime(self, target_datetime: datetime) -> None:
        """
        跳转到指定时间

        Args:
            target_datetime: 目标时间
        """
        if target_datetime:
            self.start_datetime = target_datetime
            self._current_datetime = target_datetime

            # 重置推送位置
            for symbol in self.push_positions:
                self.push_positions[symbol] = 0

            self.logger.info("虚拟数据源已跳转到: %s", target_datetime)

    def get_current_datetime(self) -> Optional[datetime]:
        """获取当前回放时间"""
        return self._current_datetime or self.start_datetime


# ==================== 统一数据管理器（核心类） ====================


class UnifiedDataManager:
    """统一数据管理中枢

    核心职责：
    1. 数据源管理（TDX、虚拟、外部网关）
    2. 数据融合（本地存储 + 录制 + 实时）
    3. 查询式服务（给行情看板、策略中心）
    4. 订阅式服务（给交易策略）
    5. 预加载优化

    数据流向：
    - 外部实时数据网关（TDX数据源、虚拟数据源、CTP/IB等）
    - 内部本地数据（StorageManager）
    - Recording录制数据
    - 对外提供统一接口（查询式、订阅式）
    """

    _VIRTUAL_MODULES = {"backtest", "replay", "virtual_gateway", "virtual"}

    def __init__(
        self,
        engine: "ChinaStockEngine",
        *,
        preload_service: Optional["PreloadService"] = None,
    ) -> None:
        """初始化统一数据管理器

        Args:
            engine: ChinaStockEngine引擎实例
            preload_service: 预加载服务实例（可选）
        """
        self.engine = engine
        self.logger = logging.getLogger(__name__)

        # === 数据源管理 ===
        self.tdx_source: Optional[TdxDataSource] = None  # TDX数据源
        self.virtual_source: Optional[VirtualDataSource] = None  # 虚拟数据源
        self.external_gateways: Dict[str, BaseGateway] = {}  # 外部交易网关

        # === 本地数据管理 ===
        self.storage_manager = engine.storage_manager  # 本地存储管理器
        self.recording_manager = None  # 录制数据管理器（预留）

        # === 预加载服务 ===
        self.preload_service = preload_service

        # === 订阅管理（vnpy事件驱动） ===
        self.event_engine = engine.event_engine
        self._module_subscriptions: Dict[str, Set[str]] = {}  # 模块订阅映射
        self._module_gateways: Dict[str, str] = {}  # 模块使用的网关
        self._gateway_symbols: Dict[str, Set[str]] = {
            "tdx": set(),
            "virtual": set(),
            "polling": set(),  # 兼容旧代码
        }
        self._lock = Lock()

    # ==================== 对外接口：查询式 ====================

    def get_kline_data(
        self,
        symbol: str,
        *,
        interval: str = "1d",
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        check_gaps: bool = True,
        use_preload: bool = True,
    ) -> Optional[pd.DataFrame]:
        """查询K线数据（自动融合多数据源）

        数据融合顺序：
        1. 预加载缓存（如果use_preload=True）
        2. 本地存储（StorageManager）
        3. 录制数据（RecordingManager）
        4. 实时数据（当前活跃的数据源）

        Args:
            symbol: 品种代码
            interval: 周期（默认"1d"）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            check_gaps: 是否检查缺口并触发自动下载
            use_preload: 是否使用预加载缓存

        Returns:
            DataFrame: K线数据，None表示无数据
        """
        frames = []

        # 1. 预加载缓存
        if use_preload and self.preload_service:
            cached = self.preload_service.get_cached_dataframe(symbol, interval)
            if cached is not None and not cached.empty:
                frames.append(cached)

        # 2. 本地存储
        storage_frame = self.engine.storage_manager.query_kline(
            symbol, interval, start_date, end_date
        )
        if storage_frame is not None and not storage_frame.empty:
            frames.append(storage_frame)

        # 3. 录制数据
        recording_frame = self._query_recording_layer(symbol, interval)
        if recording_frame is not None and not recording_frame.empty:
            frames.append(recording_frame)

        # 4. 实时数据
        realtime_frame = self._query_realtime_layer(symbol, interval)
        if realtime_frame is not None and not realtime_frame.empty:
            frames.append(realtime_frame)

        # 5. 融合去重
        merged = self._merge_frames(frames, interval)

        # 6. 缺口检查和自动下载
        if check_gaps and (merged is None or merged.empty):
            if config_manager.is_unified_manager_auto_download_enabled():
                self._trigger_backfill(symbol, start_date)
                storage_frame = self.engine.storage_manager.query_kline(
                    symbol, interval, start_date, end_date
                )
                merged = self._merge_frames(
                    [storage_frame] if storage_frame is not None else [], interval
                )

        if merged is None or merged.empty:
            return None

        # 7. 裁剪到指定范围
        trimmed = self._trim_range(merged, start_date, end_date)

        # 8. 触发预加载
        if check_gaps and config_manager.is_unified_manager_auto_download_enabled():
            self._enqueue_preload_if_needed(symbol, interval, trimmed)

        return trimmed

    def get_multi_kline_data(
        self,
        symbols: Sequence[str],
        *,
        interval: str = "1d",
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        check_gaps: bool = True,
    ) -> Dict[str, Optional[pd.DataFrame]]:
        """批量查询K线数据

        Args:
            symbols: 品种代码列表
            interval: 周期（默认"1d"）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            check_gaps: 是否检查缺口

        Returns:
            Dict: {品种代码: DataFrame}
        """
        result: Dict[str, Optional[pd.DataFrame]] = {}
        for symbol in symbols:
            result[symbol] = self.get_kline_data(
                symbol,
                interval=interval,
                start_date=start_date,
                end_date=end_date,
                check_gaps=check_gaps,
            )
        return result

    def query_unified(
        self,
        symbol: Optional[str] = None,
        interval: str = "1d",
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
        **kwargs,
    ) -> Optional[Union[pd.DataFrame, Dict]]:
        """
        统一查询接口（兼容旧代码）

        自动判断单品种还是多品种查询，返回适当的格式。

        Args:
            symbol: 单品种代码（可选）
            interval: 周期（默认"1d"）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            **kwargs: 其他参数
                - symbols: 多品种列表（与symbol互斥）
                - frequency: 周期别名（优先级低于interval）
                - check_gaps: 是否检查缺口（默认True）

        Returns:
            单品种：DataFrame 或 None
            多品种：Dict {"success": bool, "data": {symbol: []}, "interval": str, "message": str}
        """
        symbols_param = kwargs.get("symbols")
        frequency = kwargs.get("frequency") or interval
        check_gaps = kwargs.get("check_gaps", True)

        # 多品种查询路径
        if symbols_param is not None:
            symbols_list = (
                [symbols_param] if isinstance(symbols_param, str) else list(symbols_param)
            )
            if not symbols_list:
                return {"success": True, "data": {}, "interval": frequency, "message": None}

            # 调用多品种查询
            datasets = self.get_multi_kline_data(
                symbols_list,
                interval=frequency,
                start_date=start_date,
                end_date=end_date,
                check_gaps=check_gaps,
            )

            # 转换为字典格式
            payload = {
                sym: (df.to_dict("records") if df is not None else [])
                for sym, df in datasets.items()
            }

            success = any(payload.values())
            return {
                "success": success,
                "data": payload,
                "interval": frequency,
                "message": None if success else "未查询到数据",
            }

        # 单品种查询路径
        target_symbol = symbol or kwargs.get("symbols")

        # 类型缩窄：处理 list/tuple 情况
        if isinstance(target_symbol, (list, tuple)):
            if len(target_symbol) > 0:
                target_symbol = target_symbol[0]
            else:
                target_symbol = None

        # 类型检查：确保是字符串类型
        if target_symbol is None or not isinstance(target_symbol, str):
            return None

        try:
            data = self.get_kline_data(
                target_symbol,
                interval=interval,
                start_date=start_date,
                end_date=end_date,
                check_gaps=check_gaps,
            )

            if data is not None and hasattr(data, "__len__"):
                self.logger.info(
                    "查询数据成功: %s %s, %d 条记录", target_symbol, interval, len(data)
                )
            else:
                self.logger.warning("未找到数据: %s %s", target_symbol, interval)

            return data

        except Exception as e:
            self.logger.error("查询数据失败: %s %s, %s", target_symbol, interval, e)
            return None

    # ==================== 对外接口：订阅式 ====================

    def subscribe(self, module: str, symbols: Iterable[str]) -> bool:
        """订阅实时数据（推送模式）

        根据模块类型自动路由到合适的数据源：
        - backtest/replay/virtual → 虚拟数据源
        - trading/strategy → TDX数据源或外部网关
        - 其他 → TDX数据源

        Args:
            module: 调用模块标识（用于路由）
            symbols: 品种列表

        Returns:
            bool: 是否订阅成功
        """
        gateway_name = self._resolve_gateway(module)
        gateway = self._get_gateway(gateway_name)
        if gateway is None:
            self.logger.warning("网关未初始化: %s", gateway_name)
            return False

        normalized = {s.strip() for s in symbols if s.strip()}
        if not normalized:
            return True

        with self._lock:
            module_symbols = self._module_subscriptions.get(module, set())
            new_symbols = normalized - module_symbols
            if not new_symbols:
                return True

            module_symbols.update(new_symbols)
            self._module_subscriptions[module] = module_symbols
            self._module_gateways[module] = gateway_name

            attach_set = self._gateway_symbols.setdefault(gateway_name, set())
            for symbol in sorted(new_symbols):
                if symbol in attach_set:
                    continue
                req = self._build_subscribe_request(symbol)
                if req is None:
                    continue
                try:
                    gateway.subscribe(req)
                    attach_set.add(symbol)
                    self.logger.info("订阅成功: %s → %s", symbol, gateway_name)
                except Exception as exc:  # pragma: no cover
                    self.logger.error("订阅 %s 失败: %s", symbol, exc, exc_info=True)
            return True

    def unsubscribe(self, module: str, symbols: Optional[Iterable[str]] = None) -> None:
        """取消订阅

        Args:
            module: 调用模块标识
            symbols: 品种列表（None表示取消该模块的所有订阅）
        """
        with self._lock:
            if module not in self._module_subscriptions:
                return

            gateway_name = self._module_gateways.get(module, "tdx")
            module_symbols = self._module_subscriptions[module]

            if symbols is None:
                removed = set(module_symbols)
                module_symbols.clear()
            else:
                targets = {s.strip() for s in symbols if s.strip()}
                removed = module_symbols & targets
                module_symbols.difference_update(targets)

            if not module_symbols:
                self._module_subscriptions.pop(module, None)
                self._module_gateways.pop(module, None)

            self._reconcile_gateway(gateway_name, removed)

    # ==================== 数据源管理接口 ====================

    def start_tdx_source(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """启动TDX数据源

        Args:
            config: 配置字典，包含：
                - interval/polling_interval: 轮询间隔（秒）
                - symbols: 订阅品种列表
                - max_servers: 最大使用服务器数量

        Returns:
            bool: 是否启动成功
        """
        try:
            if self.tdx_source is not None:
                self.logger.warning("TDX数据源已启动")
                return True

            setting = {}
            if config:
                if "interval" in config:
                    setting["轮询间隔（秒）"] = config["interval"]
                elif "polling_interval" in config:
                    setting["轮询间隔（秒）"] = config["polling_interval"]
                if "symbols" in config:
                    symbols_list = config["symbols"]
                    setting["品种列表"] = (
                        ",".join(symbols_list) if isinstance(symbols_list, list) else symbols_list
                    )
                if "max_servers" in config:
                    setting["最大服务器数"] = config["max_servers"]

            self.tdx_source = TdxDataSource.create_and_start(self.event_engine, setting)
            self.logger.info("✅ TDX数据源已启动")
            return True

        except Exception as e:
            self.logger.error("启动TDX数据源失败: %s", e, exc_info=True)
            self.tdx_source = None
            return False

    def stop_tdx_source(self) -> bool:
        """停止TDX数据源

        Returns:
            bool: 是否停止成功
        """
        try:
            if self.tdx_source is None:
                self.logger.warning("TDX数据源未运行")
                return True

            self.tdx_source.close()
            self.tdx_source = None
            self.logger.info("✅ TDX数据源已停止")
            return True

        except Exception as e:
            self.logger.error("停止TDX数据源失败: %s", e)
            return False

    def start_virtual_source(self, config: Optional[Dict[str, Any]] = None) -> bool:
        """启动虚拟数据源

        Args:
            config: 配置字典，包含：
                - start_datetime: 起始时间（字符串格式：YYYY-MM-DD HH:MM:SS）
                - speed: 推送速度倍数
                - symbols: 订阅品种列表

        Returns:
            bool: 是否启动成功
        """
        try:
            if self.virtual_source is not None:
                self.logger.warning("虚拟数据源已启动")
                return True

            # 准备配置
            start_datetime = ""
            speed = 1.0
            symbols = None

            if config:
                start_datetime = config.get("start_datetime", "")
                speed = config.get("speed", 1.0)
                symbols = config.get("symbols")

            # 默认起始时间为昨天
            if not start_datetime:
                start_datetime = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")

            self.virtual_source = VirtualDataSource.create_and_start(
                self.event_engine, start_datetime, speed, symbols
            )
            self.logger.info("✅ 虚拟数据源已启动")
            return True

        except Exception as e:
            self.logger.error("启动虚拟数据源失败: %s", e, exc_info=True)
            self.virtual_source = None
            return False

    def stop_virtual_source(self) -> bool:
        """停止虚拟数据源

        Returns:
            bool: 是否停止成功
        """
        try:
            if self.virtual_source is None:
                self.logger.warning("虚拟数据源未运行")
                return True

            self.virtual_source.close()
            self.virtual_source = None
            self.logger.info("✅ 虚拟数据源已停止")
            return True

        except Exception as e:
            self.logger.error("停止虚拟数据源失败: %s", e)
            return False

    def connect_external_gateway(self, gateway_name: str, gateway_instance: BaseGateway) -> bool:
        """连接外部交易网关（CTP、IB等）

        Args:
            gateway_name: 网关名称标识
            gateway_instance: vnpy网关实例

        Returns:
            bool: 是否连接成功
        """
        try:
            if gateway_name in self.external_gateways:
                self.logger.warning("外部网关 %s 已连接", gateway_name)
                return True

            self.external_gateways[gateway_name] = gateway_instance
            self.logger.info("✅ 外部网关 %s 已连接", gateway_name)
            return True

        except Exception as e:
            self.logger.error("连接外部网关 %s 失败: %s", gateway_name, e)
            return False

    def disconnect_external_gateway(self, gateway_name: str) -> bool:
        """断开外部交易网关

        Args:
            gateway_name: 网关名称标识

        Returns:
            bool: 是否断开成功
        """
        try:
            if gateway_name not in self.external_gateways:
                self.logger.warning("外部网关 %s 未连接", gateway_name)
                return True

            self.external_gateways.pop(gateway_name)
            # vnpy网关的关闭由外部管理
            self.logger.info("✅ 外部网关 %s 已断开", gateway_name)
            return True

        except Exception as e:
            self.logger.error("断开外部网关 %s 失败: %s", gateway_name, e)
            return False

    # ==================== 辅助方法（兼容旧代码） ====================

    def refresh_preload(self, symbols: Iterable[str], priority: bool = False) -> None:
        """刷新预加载缓存

        Args:
            symbols: 品种列表
            priority: 是否优先处理
        """
        if not self.preload_service:
            return
        for symbol in symbols:
            self.preload_service.enqueue(symbol, priority=priority)

    # ==================== 内部实现方法 ====================

    def _resolve_gateway(self, module: str) -> str:
        """根据模块确定数据源

        路由规则：
        - backtest/replay/virtual → virtual（虚拟数据源）
        - 其他 → tdx（TDX数据源）
        """
        return "virtual" if module.lower() in self._VIRTUAL_MODULES else "tdx"

    def _get_gateway(self, gateway_name: str) -> Optional[BaseGateway]:
        """获取网关实例（按需启动）

        Args:
            gateway_name: 网关名称（"tdx", "virtual", 或外部网关名称）

        Returns:
            BaseGateway实例或None
        """
        # 虚拟数据源
        if gateway_name == "virtual":
            if self.virtual_source is None:
                if not self.start_virtual_source():
                    return None
            return self.virtual_source

        # TDX数据源
        if gateway_name == "tdx" or gateway_name == "polling":  # polling为兼容旧代码
            if self.tdx_source is None:
                if not self.start_tdx_source():
                    return None
            return self.tdx_source

        # 外部网关
        return self.external_gateways.get(gateway_name)

    def _reconcile_gateway(self, gateway_name: str, removed: Set[str]) -> None:
        """协调网关订阅（取消不再需要的订阅）

        Args:
            gateway_name: 网关名称
            removed: 已移除的品种集合
        """
        gateway = self._get_gateway(gateway_name)
        if gateway is None:
            return

        # 计算仍需要的品种
        required: Set[str] = set()
        for module, module_symbols in self._module_subscriptions.items():
            if self._module_gateways.get(module, "tdx") == gateway_name:
                required.update(module_symbols)

        attach_set = self._gateway_symbols.setdefault(gateway_name, set())
        obsolete = (attach_set - required) & removed if removed else attach_set - required
        for symbol in sorted(obsolete):
            req = self._build_subscribe_request(symbol)
            if req is None:
                continue
            try:
                if hasattr(gateway, "unsubscribe"):
                    gateway.unsubscribe(req)  # type: ignore[attr-defined]
                    self.logger.info("取消订阅: %s ← %s", symbol, gateway_name)
            except Exception as exc:  # pragma: no cover
                self.logger.error("取消订阅 %s 失败: %s", symbol, exc, exc_info=True)
            attach_set.discard(symbol)

    def _build_subscribe_request(self, symbol: str) -> Optional[SubscribeRequest]:
        """构建订阅请求

        Args:
            symbol: 品种代码

        Returns:
            SubscribeRequest或None
        """
        exchange = self._infer_exchange(symbol)
        if exchange is None:
            self.logger.debug("无法识别交易所: %s", symbol)
            return None
        return SubscribeRequest(symbol=symbol, exchange=exchange)

    def _infer_exchange(self, symbol: str) -> Optional[Exchange]:
        """推断交易所

        Args:
            symbol: 品种代码

        Returns:
            Exchange或None
        """
        if not symbol:
            return None
        code = symbol.strip()
        if code.startswith("6") or code.startswith("9"):
            return Exchange.SSE
        if code.startswith("0") or code.startswith("3"):
            return Exchange.SZSE
        if code.startswith("8"):
            # 北交所暂映射为深交所对象，后续可扩展
            return Exchange.SZSE
        return None

    def _merge_frames(
        self, frames: Iterable[Optional[pd.DataFrame]], interval: str  # noqa: ARG002
    ) -> Optional[pd.DataFrame]:
        """融合多个数据帧（保持现有实现）

        Args:
            frames: 数据帧列表
            interval: 周期（预留参数，用于未来扩展）

        Returns:
            融合后的DataFrame或None
        """
        _ = interval  # 预留参数
        normalized = []
        for frame in frames:
            prepared = self._normalize_frame(frame)
            if prepared is not None and not prepared.empty:
                normalized.append(prepared)

        if not normalized:
            return None

        merged = pd.concat(normalized, ignore_index=True)  # type: ignore[arg-type]
        if "datetime" in merged.columns:
            merged["datetime"] = pd.to_datetime(merged["datetime"])
            merged = merged.drop_duplicates(subset="datetime", keep="last")
            merged = merged.sort_values("datetime")
        return merged.reset_index(drop=True)

    def _normalize_frame(self, frame: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        """规范化数据帧格式

        Args:
            frame: 原始数据帧

        Returns:
            规范化后的DataFrame或None
        """
        if frame is None or frame.empty:
            return None
        df = frame.copy()
        if "datetime" not in df.columns:
            if isinstance(df.index, pd.DatetimeIndex):
                index_name = df.index.name or "index"
                df = df.reset_index().rename(columns={index_name: "datetime"})
            else:
                df = df.reset_index(drop=False)
                if "datetime" not in df.columns and df.columns.size > 0:
                    candidate = str(df.columns[0])
                    if candidate != "datetime":
                        df = df.rename(columns={candidate: "datetime"})
        if "datetime" not in df.columns:
            return df
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
        df = df.dropna(subset=["datetime"])
        return df

    def _trim_range(
        self,
        frame: pd.DataFrame,
        start_date: Optional[Union[str, date]],
        end_date: Optional[Union[str, date]],
    ) -> pd.DataFrame:
        """裁剪数据到指定日期范围

        Args:
            frame: 数据帧
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            裁剪后的DataFrame
        """
        if "datetime" not in frame.columns:
            return frame

        series = frame["datetime"]
        start = self._to_timestamp(start_date) if start_date else None
        end = self._to_timestamp(end_date) if end_date else None

        mask = pd.Series([True] * len(frame))
        if start is not None:
            mask &= series >= start
        if end is not None:
            mask &= series <= end
        return frame.loc[mask].reset_index(drop=True)

    def _to_timestamp(self, value: Union[str, date, datetime]) -> Timestamp:
        """转换为Timestamp

        Args:
            value: 日期值

        Returns:
            Timestamp
        """
        if isinstance(value, datetime):
            return cast(Timestamp, pd.Timestamp(value))
        if isinstance(value, date):
            return cast(Timestamp, pd.Timestamp(datetime.combine(value, datetime.min.time())))
        return cast(Timestamp, pd.to_datetime(value))

    def _trigger_backfill(self, symbol: str, start_date: Optional[Union[str, date]]) -> None:
        """触发数据回填（自动下载）

        Args:
            symbol: 品种代码
            start_date: 开始日期
        """
        if start_date is None:
            return
        if isinstance(start_date, str):
            start = start_date
        elif isinstance(start_date, datetime):
            start = start_date.strftime("%Y-%m-%d")
        else:
            start = start_date.strftime("%Y-%m-%d")
        self.logger.info("触发自动增量下载: %s 从 %s", symbol, start)
        try:
            self.engine.download_incremental(start)
        except Exception as exc:  # pragma: no cover
            self.logger.error("自动下载失败: %s", exc, exc_info=True)

    def _enqueue_preload_if_needed(
        self,
        symbol: str,
        interval: str,
        frame: Optional[pd.DataFrame],
    ) -> None:
        """如果需要，触发预加载

        Args:
            symbol: 品种代码
            interval: 周期
            frame: 数据帧
        """
        if not self.preload_service:
            return
        if frame is None or frame.empty:
            self.preload_service.enqueue(symbol, intervals=[interval], priority=True)

    def _query_recording_layer(self, symbol: str, interval: str) -> Optional[pd.DataFrame]:
        """查询录制数据层（vnpy_datarecorder）

        Args:
            symbol: 品种代码
            interval: 周期

        Returns:
            DataFrame或None
        """
        try:
            # 检查是否有可用的引擎
            if not hasattr(self, "engine") or not self.engine:
                return None

            # 尝试获取DataRecorder引擎
            try:
                from vnpy_datarecorder import DataRecorderEngine  # noqa: F401
            except ImportError:
                self.logger.debug("vnpy_datarecorder未安装，跳过录制数据查询")
                return None

            # 从engine获取main_engine（ChinaStockEngine继承自BaseEngine）
            main_engine = getattr(self.engine, "main_engine", None)
            if not main_engine:
                return None

            recorder = main_engine.get_engine("DataRecorder")
            if not recorder:
                return None

            # 转换周期格式
            interval_map = {
                "1d": "1d",
                "1h": "1h",
                "30m": "30m",
                "15m": "15m",
                "5m": "5m",
                "1m": "1m",
            }

            vnpy_interval = interval_map.get(interval)
            if not vnpy_interval:
                return None

            # 查询录制的K线数据
            from vnpy.trader.object import Exchange
            from datetime import datetime, timedelta

            # 查询最近一年的数据
            end = datetime.now()
            start = end - timedelta(days=365)

            # 构造vt_symbol（需要交易所后缀）
            # 根据代码判断交易所
            if symbol.startswith("6"):
                exchange = Exchange.SSE
            elif symbol.startswith(("0", "3")):
                exchange = Exchange.SZSE
            elif symbol.startswith(("8", "4")):
                exchange = Exchange.BSE
            else:
                exchange = Exchange.SSE

            vt_symbol = f"{symbol}.{exchange.value}"

            # 查询K线数据
            bars = recorder.query_bar_data(
                vt_symbol=vt_symbol, interval=vnpy_interval, start=start, end=end
            )

            if not bars:
                return None

            # 转换为DataFrame
            data = pd.DataFrame(
                [
                    {
                        "datetime": bar.datetime,
                        "open": bar.open_price,
                        "high": bar.high_price,
                        "low": bar.low_price,
                        "close": bar.close_price,
                        "volume": bar.volume,
                        "turnover": getattr(bar, "turnover", 0),
                    }
                    for bar in bars
                ]
            )

            self.logger.debug(f"从录制数据查询到 {len(data)} 条K线: {symbol} {interval}")
            return data

        except Exception as e:
            self.logger.warning(f"查询录制数据失败: {symbol} {interval} - {e}")
            return None

    def _query_realtime_layer(self, symbol: str, interval: str) -> Optional[pd.DataFrame]:
        """查询实时推送缓存数据

        Args:
            symbol: 品种代码
            interval: 周期

        Returns:
            DataFrame或None
        """
        try:
            import time

            # 检查是否有实时数据缓存
            if not hasattr(self, "_realtime_cache"):
                self._realtime_cache = {}

            # 构造缓存键
            cache_key = f"{symbol}_{interval}"

            # 从内存缓存中获取
            if cache_key in self._realtime_cache:
                cached_data = self._realtime_cache[cache_key]

                # 检查缓存是否过期（5分钟）
                cache_time = cached_data.get("timestamp", 0)
                if time.time() - cache_time < 300:  # 5分钟内有效
                    data = cached_data.get("data")
                    if data is not None and not data.empty:
                        self.logger.debug(
                            f"从实时缓存获取到 {len(data)} 条K线: {symbol} {interval}"
                        )
                        return data.copy()

            # 缓存未命中或过期
            return None

        except Exception as e:
            self.logger.warning(f"查询实时推送数据失败: {symbol} {interval} - {e}")
            return None

    def _update_realtime_cache(self, symbol: str, interval: str, data: pd.DataFrame):
        """更新实时数据缓存（由数据推送回调调用）

        Args:
            symbol: 品种代码
            interval: 周期
            data: K线数据
        """
        import time

        if not hasattr(self, "_realtime_cache"):
            self._realtime_cache = {}

        cache_key = f"{symbol}_{interval}"
        self._realtime_cache[cache_key] = {"data": data.copy(), "timestamp": time.time()}

        # 限制缓存大小（最多保留100个品种×周期）
        if len(self._realtime_cache) > 100:
            # 删除最旧的缓存
            oldest_key = min(
                self._realtime_cache.keys(), key=lambda k: self._realtime_cache[k]["timestamp"]
            )
            del self._realtime_cache[oldest_key]

    # ==================== vnpy 标准接口（供 vnpy_chartwizard 使用）====================

    def get_all_contracts(self) -> List[ContractData]:
        """获取所有合约信息（vnpy标准接口）

        从缓存的股票列表转换为 vnpy ContractData 格式
        供 vnpy_chartwizard 显示代码联想

        Returns:
            List[ContractData]: 合约信息列表
        """
        try:
            # 读取股票列表缓存
            cache_file = config_manager.get_cache_dir() / "stock_list_classified.json"

            if not cache_file.exists():
                self.logger.warning("股票列表缓存文件不存在: %s", cache_file)
                return []

            import json

            with open(cache_file, "r", encoding="utf-8") as f:
                cache_data = json.load(f)

            contracts = []
            classified_data = cache_data.get("data", {}).get("classified", {})

            # 遍历所有分类
            for _category, stocks in classified_data.items():
                for stock in stocks:
                    code = stock.get("code", "")
                    name = stock.get("name", "")
                    market = stock.get("market", 0)

                    # 判断交易所
                    if market == 1:  # 上交所
                        exchange = Exchange.SSE
                    elif market == 0:  # 深交所
                        exchange = Exchange.SZSE
                    elif market == 2:  # 北交所
                        exchange = Exchange.BSE
                    else:
                        exchange = Exchange.SSE  # 默认

                    # 创建 ContractData 对象
                    contract = ContractData(
                        symbol=code,
                        exchange=exchange,
                        name=name,
                        product=Product.EQUITY,
                        size=100,  # A股标准手数
                        pricetick=0.01,  # A股最小变动价位
                        gateway_name="UnifiedDataManager",
                    )
                    contracts.append(contract)

            self.logger.info("已加载 %d 个合约信息", len(contracts))
            return contracts

        except Exception as e:
            self.logger.error("获取合约信息失败: %s", e, exc_info=True)
            return []

    def load_bar_data(
        self, symbol: str, exchange: Exchange, interval: Interval, start: datetime, end: datetime
    ) -> List[BarData]:
        """加载历史K线数据（vnpy标准接口）

        调用现有的 get_kline_data() 方法，转换为 vnpy BarData 格式
        供 vnpy_chartwizard 绘制K线图

        Args:
            symbol: 品种代码（如 "000001"）
            exchange: 交易所
            interval: 周期
            start: 开始时间
            end: 结束时间

        Returns:
            List[BarData]: K线数据列表
        """
        try:
            # 转换周期格式
            interval_str = self._convert_interval_to_string(interval)

            # 转换日期格式
            start_date = start.strftime("%Y-%m-%d")
            end_date = end.strftime("%Y-%m-%d")

            # 调用现有方法获取数据
            df = self.get_kline_data(
                symbol=symbol,
                interval=interval_str,
                start_date=start_date,
                end_date=end_date,
                check_gaps=False,
                use_preload=True,
            )

            if df is None or df.empty:
                self.logger.warning("未找到品种 %s 的K线数据", symbol)
                return []

            # 转换为 BarData 列表
            bars = []
            for idx, row in df.iterrows():
                # 确保 datetime 是 datetime 对象
                if isinstance(idx, Timestamp):
                    dt = idx.to_pydatetime()
                elif isinstance(idx, datetime):
                    dt = idx
                else:
                    try:
                        dt = pd.to_datetime(str(idx)).to_pydatetime()
                    except Exception:
                        continue

                bar = BarData(
                    symbol=symbol,
                    exchange=exchange,
                    datetime=dt,
                    interval=interval,
                    volume=float(row.get("volume") or 0),
                    turnover=float(row.get("amount") or 0),
                    open_interest=0,
                    open_price=float(row.get("open") or 0),
                    high_price=float(row.get("high") or 0),
                    low_price=float(row.get("low") or 0),
                    close_price=float(row.get("close") or 0),
                    gateway_name="UnifiedDataManager",
                )
                bars.append(bar)

            self.logger.info("加载了 %d 根K线数据：%s %s", len(bars), symbol, interval_str)
            return bars

        except Exception as e:
            self.logger.error("加载K线数据失败: %s", e, exc_info=True)
            return []

    def _convert_interval_to_string(self, interval: Interval) -> str:
        """将 vnpy Interval 枚举转换为项目使用的周期字符串

        Args:
            interval: vnpy Interval 枚举

        Returns:
            str: 周期字符串（如 "1d", "1m", "5m"）
        """
        mapping = {
            Interval.MINUTE: "1m",
            Interval.HOUR: "60m",
            Interval.DAILY: "1d",
            Interval.WEEKLY: "1w",
            Interval.TICK: "tick",
        }
        return mapping.get(interval, "1d")


# ==================== 预加载服务 ====================


class PreloadService:
    """数据预加载服务（整合优化版）

    增强功能：
    - 智能预加载策略
    - 多级缓存管理
    - 异步加载优化
    - 与数据源联动
    """

    QUEUE_WAIT_SECONDS = 1.0

    def __init__(self, engine: "ChinaStockEngine") -> None:
        """初始化预加载服务

        Args:
            engine: ChinaStockEngine引擎实例
        """
        self.engine = engine
        self.logger = logging.getLogger(__name__)
        self._queue: Deque[Tuple[str, Optional[Tuple[str, ...]]]] = deque()
        self._queue_lock = threading.Lock()
        self._pending: Set[str] = set()
        self._running = False
        self._worker: Optional[threading.Thread] = None
        self._cache_lock = threading.Lock()
        self._cache: Dict[str, Dict[str, pd.DataFrame]] = {}
        self._cache_meta: Dict[str, Dict[str, datetime]] = {}
        self._cache_order: Deque[str] = deque()
        self._max_cache_symbols = config_manager.get_preload_max_cache_symbols()
        self._default_intervals = tuple(config_manager.get_preload_intervals())
        self._stats = {
            "total_preloaded": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "last_preload": None,
        }

    def start(self, prime: bool = True) -> None:
        """启动预加载服务

        Args:
            prime: 是否预加载常用品种
        """
        if self._running:
            return
        self._running = True
        self._worker = threading.Thread(target=self._run, name="DataPreloadWorker", daemon=True)
        self._worker.start()
        self.logger.info("预加载服务已启动")
        if prime:
            self.prime_with_frequently_used()

    def stop(self) -> None:
        """停止预加载服务"""
        if not self._running:
            return
        self._running = False
        if self._worker and self._worker.is_alive():
            self._worker.join(timeout=5)
        self.logger.info("预加载服务已停止")

    def enqueue(
        self, symbol: str, *, intervals: Optional[Iterable[str]] = None, priority: bool = False
    ) -> None:
        """将品种加入预加载队列

        Args:
            symbol: 品种代码
            intervals: 周期列表（可选）
            priority: 是否优先处理
        """
        if not symbol:
            return
        canonical = symbol.strip()
        if not canonical:
            return
        req_intervals = tuple(str(it).strip() for it in intervals) if intervals else None
        with self._queue_lock:
            if canonical in self._pending:
                return
            if priority:
                self._queue.appendleft((canonical, req_intervals))
            else:
                self._queue.append((canonical, req_intervals))
            self._pending.add(canonical)

    def preload_now(self, symbol: str, *, intervals: Optional[Iterable[str]] = None) -> None:
        """立即预加载（高优先级）

        Args:
            symbol: 品种代码
            intervals: 周期列表（可选）
        """
        self.enqueue(symbol, intervals=intervals, priority=True)

    def prime_with_frequently_used(self) -> None:
        """预加载常用品种"""
        symbols = config_manager.get_preload_frequently_used_symbols()
        for symbol in symbols:
            self.enqueue(symbol, priority=False)

    def get_cached_dataframe(self, symbol: str, interval: str) -> Optional[pd.DataFrame]:
        """获取缓存的数据帧

        Args:
            symbol: 品种代码
            interval: 周期

        Returns:
            DataFrame或None
        """
        key = symbol.strip()
        if not key:
            return None
        interval_key = interval.strip()
        with self._cache_lock:
            interval_map = self._cache.get(key)
            if not interval_map:
                self._stats["cache_misses"] += 1
                return None
            frame = interval_map.get(interval_key)
            if frame is None or frame.empty:
                self._stats["cache_misses"] += 1
                return None
            self._stats["cache_hits"] += 1
            return frame.copy(deep=False)

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息

        Returns:
            统计字典
        """
        with self._cache_lock, self._queue_lock:
            return {
                **self._stats,
                "cached_symbols": len(self._cache),
                "queue_size": len(self._queue),
                "max_cache_symbols": self._max_cache_symbols,
            }

    def clear_cache(self) -> None:
        """清空缓存"""
        with self._cache_lock:
            self._cache.clear()
            self._cache_meta.clear()
            self._cache_order.clear()

    def _run(self) -> None:
        """预加载工作线程主循环"""
        while self._running:
            task = self._next_task()
            if not task:
                time.sleep(self.QUEUE_WAIT_SECONDS)
                continue
            symbol, intervals = task
            try:
                self._execute(symbol, intervals or self._default_intervals)
            except Exception as exc:  # pragma: no cover
                self.logger.error("预加载 %s 失败: %s", symbol, exc, exc_info=True)

    def _next_task(self) -> Optional[Tuple[str, Optional[Tuple[str, ...]]]]:
        """获取下一个任务

        Returns:
            (品种代码, 周期元组)或None
        """
        with self._queue_lock:
            if not self._queue:
                return None
            symbol, intervals = self._queue.popleft()
            self._pending.discard(symbol)
            return symbol, intervals

    def _execute(self, symbol: str, intervals: Tuple[str, ...]) -> None:
        """执行预加载任务

        Args:
            symbol: 品种代码
            intervals: 周期元组
        """
        loaded_any = False
        for interval in intervals:
            interval_key = interval.strip()
            if not interval_key:
                continue
            frame = self.engine.storage_manager.query_kline(symbol, interval_key)
            if frame is None or frame.empty:
                continue
            loaded_any = True
            self._store(symbol, interval_key, frame)

        if loaded_any:
            self._stats["total_preloaded"] += 1
            self._stats["last_preload"] = datetime.now().isoformat()

    def _store(self, symbol: str, interval: str, frame: pd.DataFrame) -> None:
        """存储到缓存

        Args:
            symbol: 品种代码
            interval: 周期
            frame: 数据帧
        """
        with self._cache_lock:
            if symbol not in self._cache:
                if len(self._cache) >= self._max_cache_symbols:
                    self._evict_oldest()
                self._cache[symbol] = {}
                self._cache_meta[symbol] = {}
                self._cache_order.append(symbol)
            self._cache[symbol][interval] = frame.copy(deep=False)
            self._cache_meta[symbol][interval] = datetime.now()

    def _evict_oldest(self) -> None:
        """驱逐最旧的缓存项"""
        while self._cache_order:
            candidate = self._cache_order.popleft()
            if candidate in self._cache:
                del self._cache[candidate]
                del self._cache_meta[candidate]
                break


# ==================== 向后兼容导出 ====================

# 为了兼容旧代码，提供别名
PollingGateway = TdxDataSource
VirtualGateway = VirtualDataSource
