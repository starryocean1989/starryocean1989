# -*- coding: utf-8 -*-
"""
VNPY架构深度集成模块.

提供统一的VNPY事件引擎、主引擎和核心组件集成.
"""

import contextlib
import logging
from typing import Any, Dict, List, Optional

# VNPY核心导入
# 首先定义存根类


class EventEngineCompat:
    """VNPY事件引擎兼容性存根类."""

    def __init__(self):
        """初始化事件引擎存根."""
        self._handlers = {}

    def register(self, event_type, handler):
        """注册事件处理器."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)

    def unregister(self, event_type, handler):
        """注销事件处理器."""
        if event_type in self._handlers:
            with contextlib.suppress(ValueError):
                self._handlers[event_type].remove(handler)

    def put(self, event):
        """发送事件."""
        if event.type in self._handlers:
            for handler in self._handlers[event.type]:
                try:
                    handler(event)
                except (TypeError, AttributeError, RuntimeError) as e:
                    logging.error("事件处理失败 %s: %s", event.type, e)


class MainEngineStub:
    """VNPY主引擎兼容性存根类."""

    def __init__(self, event_engine):
        """初始化主引擎存根."""
        self.event_engine = event_engine
        self.engines = {}
        self.gateways = {}

    def add_engine(self, engine):
        """添加引擎."""
        self.engines[engine.engine_name] = engine

    def get_engine(self, engine_name):
        """获取引擎."""
        return self.engines.get(engine_name)

    def add_gateway(self, gateway):
        """添加网关."""
        self.gateways[gateway.gateway_name] = gateway


class BaseDataStub:
    """VNPY基础数据类兼容性存根."""

    def __init__(self):
        """初始化基础数据存根."""
        self.datetime = None
        self.gateway_name = ""


class TickDataStub(BaseDataStub):
    """VNPY TickData兼容性存根类."""

    def __init__(self):
        """初始化TickData存根."""
        super().__init__()
        self.symbol = ""
        self.name = ""
        self.volume = 0
        self.turnover = 0
        self.open_interest = 0
        self.last_price = 0
        self.last_volume = 0
        self.limit_up = 0
        self.limit_down = 0
        self.open_price = 0
        self.high_price = 0
        self.low_price = 0
        self.pre_close = 0
        self.bid_price_1 = 0
        self.bid_volume_1 = 0
        self.ask_price_1 = 0
        self.ask_volume_1 = 0


class BarDataStub(BaseDataStub):
    """VNPY BarData兼容性存根类."""

    def __init__(self):
        """初始化BarData存根."""
        super().__init__()
        self.symbol = ""
        self.exchange = ""
        self.interval = 1
        self.volume = 0
        self.turnover = 0
        self.open_interest = 0
        self.open_price = 0
        self.high_price = 0
        self.low_price = 0
        self.close_price = 0


class OrderDataStub(BaseDataStub):
    """VNPY OrderData兼容性存根类."""

    def __init__(self):
        """初始化OrderData存根."""
        super().__init__()
        self.symbol = ""
        self.exchange = ""
        self.type = ""
        self.direction = ""
        self.offset = ""
        self.price = 0
        self.volume = 0
        self.traded = 0
        self.status = ""
        self.time = ""


class TradeDataStub(BaseDataStub):
    """VNPY TradeData兼容性存根类."""

    def __init__(self):
        """初始化TradeData存根."""
        super().__init__()
        self.symbol = ""
        self.exchange = ""
        self.direction = ""
        self.offset = ""
        self.price = 0
        self.volume = 0
        self.time = ""


class PositionDataStub(BaseDataStub):
    """VNPY PositionData兼容性存根类."""

    def __init__(self):
        """初始化PositionData存根."""
        super().__init__()
        self.symbol = ""
        self.exchange = ""
        self.direction = ""
        self.volume = 0
        self.frozen = 0
        self.price = 0
        self.pnl = 0
        self.yd_volume = 0


class AccountDataStub(BaseDataStub):
    """VNPY AccountData兼容性存根类."""

    def __init__(self):
        """初始化AccountData存根."""
        super().__init__()
        self.accountid = ""
        self.balance = 0
        self.available = 0
        self.commission = 0
        self.margin = 0
        self.close_profit = 0
        self.position_profit = 0


# 事件类型常量
EVENT_TICK_STUB = "eTick"
EVENT_ORDER_STUB = "eOrder"
EVENT_TRADE_STUB = "eTrade"
EVENT_POSITION_STUB = "ePosition"
EVENT_ACCOUNT_STUB = "eAccount"
EVENT_LOG_STUB = "eLog"


try:
    from vnpy.trader.engine import MainEngine
    from vnpy.event import EventEngine, Event
    from vnpy.trader.object import (
        BaseData,
        TickData,
        BarData,
        OrderData,
        TradeData,
        PositionData,
        AccountData,
    )
    from vnpy.trader.event import (
        EVENT_TICK,
        EVENT_ORDER,
        EVENT_TRADE,
        EVENT_POSITION,
        EVENT_ACCOUNT,
        EVENT_LOG,
    )

    VNPY_AVAILABLE = True
except ImportError as e:
    logging.warning("VNPY核心模块导入失败: %s", e)
    VNPY_AVAILABLE = False
    # 设置存根类作为fallback
    MainEngine = MainEngineStub
    BASE_ENGINE = None
    EventEngine = EventEngineCompat
    Event = None
    BaseData = BaseDataStub
    TickData = TickDataStub
    BarData = BarDataStub
    OrderData = OrderDataStub
    TradeData = TradeDataStub
    PositionData = PositionDataStub
    AccountData = AccountDataStub
    EVENT_TICK = EVENT_TICK_STUB
    EVENT_ORDER = EVENT_ORDER_STUB
    EVENT_TRADE = EVENT_TRADE_STUB
    EVENT_POSITION = EVENT_POSITION_STUB
    EVENT_ACCOUNT = EVENT_ACCOUNT_STUB
    EVENT_LOG = EVENT_LOG_STUB

# 类型别名，用于处理兼容性
MainEngineType = MainEngine
EventEngineType = EventEngine

# VNPY扩展引擎导入（条件性导入）
try:
    from vnpy_ctastrategy import CtaEngine

    VNPY_CTA_AVAILABLE = True
except ImportError:
    VNPY_CTA_AVAILABLE = False
    CtaEngine = None

try:
    from vnpy_algotrading import AlgoEngine

    VNPY_ALGO_AVAILABLE = True
except ImportError:
    VNPY_ALGO_AVAILABLE = False
    AlgoEngine = None

try:
    from vnpy_portfoliostrategy import PortfolioEngine  # type: ignore

    VNPY_PORTFOLIO_AVAILABLE = True
except ImportError:
    VNPY_PORTFOLIO_AVAILABLE = False
    PortfolioEngine = None


class PortfolioEngineStub:
    """VNPY组合策略引擎兼容性存根类."""

    def __init__(self, main_engine, event_engine):
        """初始化组合策略引擎存根."""
        self.main_engine = main_engine
        self.event_engine = event_engine
        self.engine_name = "portfolio"
        self.strategies = {}

    def add_strategy(self, strategy, strategy_name):
        """添加策略."""
        self.strategies[strategy_name] = strategy

    def remove_strategy(self, strategy_name):
        """移除策略."""
        if strategy_name in self.strategies:
            del self.strategies[strategy_name]


# 如果PortfolioEngine不可用，使用存根类
if PortfolioEngine is None:
    PortfolioEngine = PortfolioEngineStub

try:
    from vnpy_spreadtrading import SpreadEngine

    VNPY_SPREAD_AVAILABLE = True
except ImportError:
    VNPY_SPREAD_AVAILABLE = False
    SpreadEngine = None

try:
    from vnpy_scripttrader import ScriptEngine

    VNPY_SCRIPT_AVAILABLE = True
except ImportError:
    VNPY_SCRIPT_AVAILABLE = False
    ScriptEngine = None

try:
    from vnpy_optionmaster import OptionEngine

    VNPY_OPTION_AVAILABLE = True
except ImportError:
    VNPY_OPTION_AVAILABLE = False
    OptionEngine = None


class TerminalEngine:
    """终端主引擎，继承VNPY架构."""

    def __init__(self):
        """初始化终端引擎."""
        self.logger = logging.getLogger(__name__)

        # 初始化事件引擎
        self.event_engine = EventEngine()  # type: ignore
        self.logger.info("事件引擎初始化完成")

        # 初始化主引擎
        self.main_engine = MainEngine(self.event_engine)  # type: ignore
        self.logger.info("主引擎初始化完成")

        # 引擎注册表
        self.engines: Dict[str, Any] = {}

        # 网关注册表
        self.gateways: Dict[str, Any] = {}

        # 策略引擎状态
        self.strategy_engines: Dict[str, Any] = {}

        # 数据源状态
        self.datafeeds: Dict[str, Any] = {}

        # 扩展事件类型
        self._register_custom_events()

        # 注册所有引擎
        self._register_all_packages()

        self.logger.info("终端引擎初始化完成")

    def _register_custom_events(self):
        """注册自定义事件类型."""
        # 系统状态事件
        self.event_engine.register("eSystemStatus", self._on_system_status)
        self.event_engine.register("eDataQuality", self._on_data_quality)
        self.event_engine.register("eStrategyLog", self._on_strategy_log)
        self.event_engine.register("eGatewayStatus", self._on_gateway_status)

    def _register_all_packages(self):
        """注册所有VNPY包."""
        if not VNPY_AVAILABLE:
            self.logger.warning("VNPY不可用，跳过包注册")
            return

        try:
            # 注册CTA策略引擎
            if VNPY_CTA_AVAILABLE and CtaEngine:
                cta_engine = CtaEngine(self.main_engine, self.event_engine)  # type: ignore
                # 直接添加到策略引擎字典，不通过main_engine.add_engine
                self.strategy_engines["cta"] = cta_engine
                self.logger.info("CTA策略引擎注册完成")
            else:
                self.logger.warning("CTA策略引擎不可用")

            # 注册算法交易引擎
            if VNPY_ALGO_AVAILABLE and AlgoEngine:
                algo_engine = AlgoEngine(self.main_engine, self.event_engine)  # type: ignore
                # 直接添加到策略引擎字典，不通过main_engine.add_engine
                self.strategy_engines["algo"] = algo_engine
                self.logger.info("算法交易引擎注册完成")
            else:
                self.logger.warning("算法交易引擎不可用")

            # 注册组合策略引擎
            try:
                if PortfolioEngine:
                    portfolio_engine = PortfolioEngine(
                        self.main_engine, self.event_engine  # type: ignore
                    )
                    # 直接添加到策略引擎字典，不通过main_engine.add_engine
                    self.strategy_engines["portfolio"] = portfolio_engine
                    self.logger.info("组合策略引擎注册完成")
            except ImportError:
                self.logger.warning("组合策略引擎不可用")

            # 注册价差交易引擎
            if VNPY_SPREAD_AVAILABLE and SpreadEngine:
                spread_engine = SpreadEngine(self.main_engine, self.event_engine)  # type: ignore
                # 直接添加到策略引擎字典，不通过main_engine.add_engine
                self.strategy_engines["spread"] = spread_engine
                self.logger.info("价差交易引擎注册完成")
            else:
                self.logger.warning("价差交易引擎不可用")

            # 注册脚本交易引擎
            if VNPY_SCRIPT_AVAILABLE and ScriptEngine:
                script_engine = ScriptEngine(self.main_engine, self.event_engine)  # type: ignore
                # 直接添加到策略引擎字典，不通过main_engine.add_engine
                self.strategy_engines["script"] = script_engine
                self.logger.info("脚本交易引擎注册完成")
            else:
                self.logger.warning("脚本交易引擎不可用")

            # 注册期权策略引擎
            if VNPY_OPTION_AVAILABLE and OptionEngine:
                option_engine = OptionEngine(self.main_engine, self.event_engine)  # type: ignore
                # 直接添加到策略引擎字典，不通过main_engine.add_engine
                self.strategy_engines["option"] = option_engine
                self.logger.info("期权策略引擎注册完成")
            else:
                self.logger.warning("期权策略引擎不可用")

        except (RuntimeError, AttributeError, ImportError) as e:
            self.logger.error("注册VNPY包失败: %s", e)

    def add_gateway(self, gateway_name: str, gateway_class: Any, **kwargs):
        """添加交易网关."""
        try:
            gateway = gateway_class(self.main_engine, self.event_engine, **kwargs)
            self.main_engine.add_gateway(gateway)  # type: ignore
            self.gateways[gateway_name] = gateway
            self.logger.info("网关 %s 添加完成", gateway_name)
            return gateway
        except (TypeError, AttributeError, RuntimeError) as e:
            self.logger.error("添加网关 %s 失败: %s", gateway_name, e)
            return None

    def add_datafeed(self, datafeed_name: str, datafeed_class: Any, **kwargs):
        """添加数据源."""
        try:
            datafeed = datafeed_class(self.main_engine, self.event_engine, **kwargs)
            # VNPY可能没有add_datafeed方法，直接使用数据源对象
            # self.main_engine.add_datafeed(datafeed)
            self.datafeeds[datafeed_name] = datafeed
            self.logger.info("数据源 %s 添加完成", datafeed_name)
            return datafeed
        except (TypeError, AttributeError, RuntimeError) as e:
            self.logger.error("添加数据源 %s 失败: %s", datafeed_name, e)
            return None

    def connect_gateway(self, gateway_name: str, **settings):
        """连接交易网关."""
        if gateway_name in self.gateways:
            try:
                gateway = self.gateways[gateway_name]
                gateway.connect(settings)
                self.logger.info("网关 %s 连接成功", gateway_name)
                return True
            except (ConnectionError, TimeoutError, RuntimeError) as e:
                self.logger.error("连接网关 %s 失败: %s", gateway_name, e)
                return False
        else:
            self.logger.error("网关 %s 未找到", gateway_name)
            return False

    def subscribe_symbol(self, symbol: str, exchange: str = ""):
        """订阅行情数据."""
        try:
            for gateway in self.gateways.values():
                if hasattr(gateway, "subscribe"):
                    gateway.subscribe(symbol, exchange)
            self.logger.info("订阅 %s 行情数据成功", symbol)
            return True
        except (AttributeError, RuntimeError, TypeError) as e:
            self.logger.error("订阅行情数据失败: %s", e)
            return False

    def get_status(self) -> Dict[str, Any]:
        """获取系统状态."""
        status = {
            "vnpy_available": VNPY_AVAILABLE,
            "event_engine_running": True,
            "main_engine_running": True,
            "gateways": {},
            "datafeeds": {},
            "strategy_engines": {},
            "connected_gateways": 0,
            "subscribed_symbols": 0,
            "real_time_worker_running": False,
        }

        # 网关状态
        for name, gateway in self.gateways.items():
            status["gateways"][name] = {
                "connected": getattr(gateway, "connected", False),
                "trading": getattr(gateway, "trading", False),
            }
            if getattr(gateway, "connected", False):
                status["connected_gateways"] += 1

        # 数据源状态
        for name, datafeed in self.datafeeds.items():
            status["datafeeds"][name] = {
                "connected": getattr(datafeed, "connected", False),
                "symbols": getattr(datafeed, "subscribed_symbols", []),
            }

        # 策略引擎状态
        for name, engine in self.strategy_engines.items():
            status["strategy_engines"][name] = {
                "running": getattr(engine, "running", False),
                "strategies": len(getattr(engine, "strategies", {})),
            }

        return status

    def get_positions(self, gateway_name: Optional[str] = None) -> Dict[str, Any]:
        """获取持仓信息."""
        try:
            positions = {}

            # 如果指定了网关名称，只获取该网关的持仓
            if gateway_name:
                if gateway_name not in self.gateways:
                    raise ValueError(f"网关不存在: {gateway_name}")

                gateway = self.gateways[gateway_name]
                if not hasattr(gateway, "get_positions"):
                    raise NotImplementedError(f"网关 {gateway_name} 未实现get_positions方法")

                positions = gateway.get_positions()
            else:
                # 获取所有网关的持仓
                for name, gateway in self.gateways.items():
                    if not hasattr(gateway, "get_positions"):
                        raise NotImplementedError(f"网关 {name} 未实现get_positions方法")

                    gateway_positions = gateway.get_positions()
                    positions.update(gateway_positions)

            self.logger.info("获取持仓信息成功: %s", len(positions))
            return positions
        except (AttributeError, TypeError, RuntimeError, ValueError) as e:
            self.logger.error("获取持仓信息失败: %s", e)
            raise

    def get_account_info(self, gateway_name: Optional[str] = None) -> Dict[str, Any]:
        """获取账户信息."""
        try:
            account_info = {}

            # 如果指定了网关名称，只获取该网关的账户信息
            if gateway_name:
                if gateway_name not in self.gateways:
                    raise ValueError(f"网关不存在: {gateway_name}")

                gateway = self.gateways[gateway_name]
                if not hasattr(gateway, "get_account_info"):
                    raise NotImplementedError(f"网关 {gateway_name} 未实现get_account_info方法")

                account_info = gateway.get_account_info()
            else:
                # 获取所有网关的账户信息
                for name, gateway in self.gateways.items():
                    if not hasattr(gateway, "get_account_info"):
                        raise NotImplementedError(f"网关 {name} 未实现get_account_info方法")

                    gateway_account = gateway.get_account_info()
                    account_info[name] = gateway_account

            self.logger.info("获取账户信息成功: %s", len(account_info))
            return account_info
        except (AttributeError, TypeError, RuntimeError, ValueError) as e:
            self.logger.error("获取账户信息失败: %s", e)
            raise

    def start_strategy(self, strategy_name: str, strategy_class: Any, **kwargs):
        """启动策略."""
        try:
            if "cta" in self.strategy_engines:
                cta_engine = self.strategy_engines["cta"]
                strategy = strategy_class(cta_engine, **kwargs)
                cta_engine.add_strategy(strategy, strategy_name)
                self.logger.info("策略 %s 启动成功", strategy_name)
                return strategy
        except (TypeError, AttributeError, RuntimeError) as e:
            self.logger.error("启动策略失败: %s", e)
        return None

    def stop_strategy(self, strategy_name: str):
        """停止策略."""
        try:
            if "cta" in self.strategy_engines:
                cta_engine = self.strategy_engines["cta"]
                cta_engine.remove_strategy(strategy_name)
                self.logger.info("策略 %s 停止成功", strategy_name)
                return True
        except (AttributeError, RuntimeError, KeyError) as e:
            self.logger.error("停止策略失败: %s", e)
        return False

    def get_strategies(self) -> List[Dict[str, Any]]:
        """获取所有策略列表."""
        strategies: List[Dict[str, Any]] = []
        try:
            # 从所有策略引擎中获取策略信息
            for engine_name, engine in self.strategy_engines.items():
                if hasattr(engine, "strategies"):
                    engine_strategies = getattr(engine, "strategies", {})
                    for strategy_name, strategy in engine_strategies.items():
                        strategy_info = {
                            "name": strategy_name,
                            "engine": engine_name,
                            "gateway": getattr(strategy, "gateway_name", "未知"),
                            "status": "运行中" if getattr(strategy, "trading", False) else "已停止",
                            "start_time": getattr(strategy, "start_time", ""),
                        }
                        strategies.append(strategy_info)

            self.logger.info("获取策略列表成功，共 %d 个策略", len(strategies))
        except (AttributeError, RuntimeError, TypeError) as e:
            self.logger.error("获取策略列表失败: %s", e)

        return strategies

    def _on_system_status(self, event):
        """系统状态事件处理."""
        self.logger.info("系统状态更新: %s", getattr(event, "data", event))

    def _on_data_quality(self, event):
        """数据质量事件处理."""
        self.logger.info("数据质量更新: %s", getattr(event, "data", event))

    def _on_strategy_log(self, event):
        """策略日志事件处理."""
        self.logger.info("策略日志: %s", getattr(event, "data", event))

    def _on_gateway_status(self, event):
        """网关状态事件处理."""
        self.logger.info("网关状态更新: %s", getattr(event, "data", event))

    def emit_event(self, event_type: str, data: Any = None):
        """发送事件."""
        if Event is not None:
            event = Event(event_type, data)  # type: ignore
            self.event_engine.put(event)  # type: ignore
        else:
            # 使用存根事件处理
            self.event_engine.put(
                type("Event", (), {"type": event_type, "data": data})()  # type: ignore
            )

    def register_event_handler(self, event_type: str, handler):
        """注册事件处理器."""
        self.event_engine.register(event_type, handler)

    def unregister_event_handler(self, event_type: str, handler):
        """注销事件处理器."""
        self.event_engine.unregister(event_type, handler)

    def shutdown(self):
        """关闭终端引擎."""
        try:
            # 停止所有策略
            if "cta" in self.strategy_engines:
                cta_engine = self.strategy_engines["cta"]
                for strategy_name in list(cta_engine.strategies.keys()):
                    cta_engine.remove_strategy(strategy_name)

            # 断开所有网关
            for gateway in self.gateways.values():
                if hasattr(gateway, "close"):
                    gateway.close()

            self.logger.info("终端引擎已关闭")
        except (AttributeError, RuntimeError, IOError) as e:
            self.logger.error("关闭终端引擎失败: %s", e)


# 全局终端引擎实例
_TERMINAL_ENGINE = None


def get_terminal_engine() -> TerminalEngine:
    """获取全局终端引擎实例."""
    global _TERMINAL_ENGINE
    if _TERMINAL_ENGINE is None:
        _TERMINAL_ENGINE = TerminalEngine()
    return _TERMINAL_ENGINE


def reset_terminal_engine():
    """重置终端引擎（用于测试）."""
    global _TERMINAL_ENGINE
    if _TERMINAL_ENGINE:
        _TERMINAL_ENGINE.shutdown()
        _TERMINAL_ENGINE = None


# 兼容性导出
if VNPY_AVAILABLE:
    __all__ = [
        # VNPY核心类
        "MainEngine",
        "EventEngine",
        "Event",
        "BaseData",
        "TickData",
        "BarData",
        "OrderData",
        "TradeData",
        "PositionData",
        "AccountData",
        # 事件常量
        "EVENT_TICK",
        "EVENT_ORDER",
        "EVENT_TRADE",
        "EVENT_POSITION",
        "EVENT_ACCOUNT",
        "EVENT_LOG",
        # 终端引擎
        "TerminalEngine",
        "get_terminal_engine",
        "reset_terminal_engine",
    ]
else:
    __all__ = [
        # 存根类
        "EventEngine",
        "MainEngine",
        "BaseData",
        "TickData",
        "BarData",
        "OrderData",
        "TradeData",
        "PositionData",
        "AccountData",
        # 事件常量
        "EVENT_TICK",
        "EVENT_ORDER",
        "EVENT_TRADE",
        "EVENT_POSITION",
        "EVENT_ACCOUNT",
        "EVENT_LOG",
        # 终端引擎
        "TerminalEngine",
        "get_terminal_engine",
        "reset_terminal_engine",
    ]
