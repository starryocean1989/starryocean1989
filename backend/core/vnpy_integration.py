# -*- coding: utf-8 -*-
"""
VNPY架构深度集成模块
提供统一的VNPY事件引擎、主引擎和核心组件集成
"""

import logging
from typing import Dict, Any

# VNPY核心导入
try:
    from vnpy.trader.engine import MainEngine, BaseEngine
    from vnpy.event import EventEngine, Event
    from vnpy.trader.object import (
        BaseData, TickData, BarData, OrderData,
        TradeData, PositionData, AccountData
    )
    from vnpy.trader.event import (
        EVENT_TICK, EVENT_ORDER, EVENT_TRADE,
        EVENT_POSITION, EVENT_ACCOUNT, EVENT_LOG
    )
    VNPY_AVAILABLE = True
except ImportError as e:
    logging.warning(f"VNPY核心模块导入失败: {e}")
    VNPY_AVAILABLE = False

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
    from vnpy_portfoliostrategy import PortfolioEngine
    VNPY_PORTFOLIO_AVAILABLE = True
except ImportError:
    VNPY_PORTFOLIO_AVAILABLE = False
    PortfolioEngine = None

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

    # 创建兼容性存根类
    class EventEngineCompat:
        def __init__(self):
            self._handlers = {}

        def register(self, event_type, handler):
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)

        def unregister(self, event_type, handler):
            if event_type in self._handlers:
                try:
                    self._handlers[event_type].remove(handler)
                except ValueError:
                    pass

        def put(self, event):
            if event.type in self._handlers:
                for handler in self._handlers[event.type]:
                    try:
                        handler(event)
                    except (TypeError, AttributeError, RuntimeError) as e:
                        logging.error(f"事件处理失败 {event.type}: {e}")

    class MainEngineStub:
        def __init__(self, event_engine):
            self.event_engine = event_engine
            self.engines = {}

        def add_engine(self, engine):
            self.engines[engine.engine_name] = engine

        def get_engine(self, engine_name):
            return self.engines.get(engine_name)

    class BaseDataStub:
        def __init__(self):
            self.datetime = None
            self.gateway_name = ""

    class TickData(BaseDataStub):
        def __init__(self):
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

    class BarData(BaseData):
        def __init__(self):
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

    class OrderData(BaseData):
        def __init__(self):
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

    class TradeData(BaseData):
        def __init__(self):
            super().__init__()
            self.symbol = ""
            self.exchange = ""
            self.direction = ""
            self.offset = ""
            self.price = 0
            self.volume = 0
            self.time = ""

    class PositionData(BaseData):
        def __init__(self):
            super().__init__()
            self.symbol = ""
            self.exchange = ""
            self.direction = ""
            self.volume = 0
            self.frozen = 0
            self.price = 0
            self.pnl = 0
            self.yd_volume = 0

    class AccountData(BaseData):
        def __init__(self):
            super().__init__()
            self.accountid = ""
            self.balance = 0
            self.available = 0
            self.commission = 0
            self.margin = 0
            self.close_profit = 0
            self.position_profit = 0

    # 事件类型常量
    EVENT_TICK = "eTick"
    EVENT_ORDER = "eOrder"
    EVENT_TRADE = "eTrade"
    EVENT_POSITION = "ePosition"
    EVENT_ACCOUNT = "eAccount"
    EVENT_LOG = "eLog"


class TerminalEngine:
    """终端主引擎，继承VNPY架构"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # 初始化事件引擎
        self.event_engine = EventEngine()
        self.logger.info("事件引擎初始化完成")

        # 初始化主引擎
        self.main_engine = MainEngine(self.event_engine)
        self.logger.info("主引擎初始化完成")

        # 引擎注册表
        self.engines: Dict[str, BaseEngine] = {}

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
        """注册自定义事件类型"""
        # 系统状态事件
        self.event_engine.register("eSystemStatus", self._on_system_status)
        self.event_engine.register("eDataQuality", self._on_data_quality)
        self.event_engine.register("eStrategyLog", self._on_strategy_log)
        self.event_engine.register("eGatewayStatus", self._on_gateway_status)

    def _register_all_packages(self):
        """注册所有VNPY包"""
        if not VNPY_AVAILABLE:
            self.logger.warning("VNPY不可用，跳过包注册")
            return

        try:
            # 注册CTA策略引擎
            if VNPY_CTA_AVAILABLE and CtaEngine:
                cta_engine = CtaEngine(self.main_engine, self.event_engine)
                self.main_engine.add_engine(cta_engine)
                self.strategy_engines["cta"] = cta_engine
                self.logger.info("CTA策略引擎注册完成")
            else:
                self.logger.warning("CTA策略引擎不可用")

            # 注册算法交易引擎
            if VNPY_ALGO_AVAILABLE and AlgoEngine:
                algo_engine = AlgoEngine(self.main_engine, self.event_engine)
                self.main_engine.add_engine(algo_engine)
                self.strategy_engines["algo"] = algo_engine
                self.logger.info("算法交易引擎注册完成")
            else:
                self.logger.warning("算法交易引擎不可用")

            # 注册组合策略引擎
            try:
                from vnpy_portfoliostrategy import PortfolioEngine
                if PortfolioEngine:
                    portfolio_engine = PortfolioEngine(
                        self.main_engine, self.event_engine
                    )
                    self.main_engine.add_engine(portfolio_engine)
                    self.strategy_engines["portfolio"] = portfolio_engine
                    self.logger.info("组合策略引擎注册完成")
            except ImportError:
                self.logger.warning("组合策略引擎不可用")

            # 注册价差交易引擎
            if VNPY_SPREAD_AVAILABLE and SpreadEngine:
                spread_engine = SpreadEngine(
                    self.main_engine, self.event_engine
                )
                self.main_engine.add_engine(spread_engine)
                self.strategy_engines["spread"] = spread_engine
                self.logger.info("价差交易引擎注册完成")
            else:
                self.logger.warning("价差交易引擎不可用")

            # 注册脚本交易引擎
            if VNPY_SCRIPT_AVAILABLE and ScriptEngine:
                script_engine = ScriptEngine(
                    self.main_engine, self.event_engine
                )
                self.main_engine.add_engine(script_engine)
                self.strategy_engines["script"] = script_engine
                self.logger.info("脚本交易引擎注册完成")
            else:
                self.logger.warning("脚本交易引擎不可用")

            # 注册期权策略引擎
            if VNPY_OPTION_AVAILABLE and OptionEngine:
                option_engine = OptionEngine(
                    self.main_engine, self.event_engine
                )
                self.main_engine.add_engine(option_engine)
                self.strategy_engines["option"] = option_engine
                self.logger.info("期权策略引擎注册完成")
            else:
                self.logger.warning("期权策略引擎不可用")

        except (RuntimeError, AttributeError, ImportError) as e:
            self.logger.error(f"注册VNPY包失败: {e}")

    def add_gateway(self, gateway_name: str, gateway_class: Any, **kwargs):
        """添加交易网关"""
        try:
            gateway = gateway_class(
                self.main_engine, self.event_engine, **kwargs
            )
            self.main_engine.add_gateway(gateway)
            self.gateways[gateway_name] = gateway
            self.logger.info(f"网关 {gateway_name} 添加完成")
            return gateway
        except (TypeError, AttributeError, RuntimeError) as e:
            self.logger.error(f"添加网关 {gateway_name} 失败: {e}")
            return None

    def add_datafeed(self, datafeed_name: str, datafeed_class: Any, **kwargs):
        """添加数据源"""
        try:
            datafeed = datafeed_class(
                self.main_engine, self.event_engine, **kwargs
            )
            # VNPY可能没有add_datafeed方法，直接使用数据源对象
            # self.main_engine.add_datafeed(datafeed)
            self.datafeeds[datafeed_name] = datafeed
            self.logger.info("数据源 %s 添加完成", datafeed_name)
            return datafeed
        except (TypeError, AttributeError, RuntimeError) as e:
            self.logger.error("添加数据源 %s 失败: %s", datafeed_name, e)
            return None

    def connect_gateway(self, gateway_name: str, **settings):
        """连接交易网关"""
        if gateway_name in self.gateways:
            try:
                gateway = self.gateways[gateway_name]
                gateway.connect(settings)
                self.logger.info(f"网关 {gateway_name} 连接成功")
                return True
            except (ConnectionError, TimeoutError, RuntimeError) as e:
                self.logger.error(f"连接网关 {gateway_name} 失败: {e}")
                return False
        else:
            self.logger.error(f"网关 {gateway_name} 未找到")
            return False

    def subscribe_symbol(self, symbol: str, exchange: str = ""):
        """订阅行情数据"""
        try:
            for gateway in self.gateways.values():
                if hasattr(gateway, 'subscribe'):
                    gateway.subscribe(symbol, exchange)
            self.logger.info(f"订阅 {symbol} 行情数据成功")
            return True
        except (AttributeError, RuntimeError, TypeError) as e:
            self.logger.error(f"订阅行情数据失败: {e}")
            return False

    def get_status(self) -> Dict[str, Any]:
        """获取系统状态"""
        status = {
            "vnpy_available": VNPY_AVAILABLE,
            "event_engine_running": True,
            "main_engine_running": True,
            "gateways": {},
            "datafeeds": {},
            "strategy_engines": {},
            "connected_gateways": 0,
            "subscribed_symbols": 0,
            "real_time_worker_running": False
        }

        # 网关状态
        for name, gateway in self.gateways.items():
            status["gateways"][name] = {
                "connected": getattr(gateway, 'connected', False),
                "trading": getattr(gateway, 'trading', False)
            }
            if getattr(gateway, 'connected', False):
                status["connected_gateways"] += 1

        # 数据源状态
        for name, datafeed in self.datafeeds.items():
            status["datafeeds"][name] = {
                "connected": getattr(datafeed, 'connected', False),
                "symbols": getattr(datafeed, 'subscribed_symbols', [])
            }

        # 策略引擎状态
        for name, engine in self.strategy_engines.items():
            status["strategy_engines"][name] = {
                "running": getattr(engine, 'running', False),
                "strategies": len(getattr(engine, 'strategies', {}))
            }

        return status

    def start_strategy(
        self, strategy_name: str, strategy_class: Any, **kwargs
    ):
        """启动策略"""
        try:
            if "cta" in self.strategy_engines:
                cta_engine = self.strategy_engines["cta"]
                strategy = strategy_class(cta_engine, **kwargs)
                cta_engine.add_strategy(strategy, strategy_name)
                self.logger.info(f"策略 {strategy_name} 启动成功")
                return strategy
        except (TypeError, AttributeError, RuntimeError) as e:
            self.logger.error(f"启动策略失败: {e}")
        return None

    def stop_strategy(self, strategy_name: str):
        """停止策略"""
        try:
            if "cta" in self.strategy_engines:
                cta_engine = self.strategy_engines["cta"]
                cta_engine.remove_strategy(strategy_name)
                self.logger.info(f"策略 {strategy_name} 停止成功")
                return True
        except (AttributeError, RuntimeError, KeyError) as e:
            self.logger.error(f"停止策略失败: {e}")
        return False

    def _on_system_status(self, event: Event):
        """系统状态事件处理"""
        self.logger.info(f"系统状态更新: {event.data}")

    def _on_data_quality(self, event: Event):
        """数据质量事件处理"""
        self.logger.info(f"数据质量更新: {event.data}")

    def _on_strategy_log(self, event: Event):
        """策略日志事件处理"""
        self.logger.info(f"策略日志: {event.data}")

    def _on_gateway_status(self, event: Event):
        """网关状态事件处理"""
        self.logger.info(f"网关状态更新: {event.data}")

    def emit_event(self, event_type: str, data: Any = None):
        """发送事件"""
        event = Event(event_type, data)
        self.event_engine.put(event)

    def register_event_handler(self, event_type: str, handler):
        """注册事件处理器"""
        self.event_engine.register(event_type, handler)

    def unregister_event_handler(self, event_type: str, handler):
        """注销事件处理器"""
        self.event_engine.unregister(event_type, handler)

    def shutdown(self):
        """关闭终端引擎"""
        try:
            # 停止所有策略
            if "cta" in self.strategy_engines:
                cta_engine = self.strategy_engines["cta"]
                for strategy_name in list(cta_engine.strategies.keys()):
                    cta_engine.remove_strategy(strategy_name)

            # 断开所有网关
            for gateway in self.gateways.values():
                if hasattr(gateway, 'close'):
                    gateway.close()

            self.logger.info("终端引擎已关闭")
        except (AttributeError, RuntimeError, IOError) as e:
            self.logger.error(f"关闭终端引擎失败: {e}")


# 全局终端引擎实例
_terminal_engine = None


def get_terminal_engine() -> TerminalEngine:
    """获取全局终端引擎实例"""
    global _terminal_engine
    if _terminal_engine is None:
        _terminal_engine = TerminalEngine()
    return _terminal_engine


def reset_terminal_engine():
    """重置终端引擎（用于测试）"""
    global _terminal_engine
    if _terminal_engine:
        _terminal_engine.shutdown()
        _terminal_engine = None


# 兼容性导出
if VNPY_AVAILABLE:
    __all__ = [
        # VNPY核心类
        "MainEngine", "EventEngine", "Event", "BaseData",
        "TickData", "BarData", "OrderData", "TradeData",
        "PositionData", "AccountData",

        # 事件常量
        "EVENT_TICK", "EVENT_ORDER", "EVENT_TRADE",
        "EVENT_POSITION", "EVENT_ACCOUNT", "EVENT_LOG",

        # 终端引擎
        "TerminalEngine", "get_terminal_engine", "reset_terminal_engine"
    ]
else:
    __all__ = [
        # 存根类
        "EventEngine", "MainEngine", "BaseData",
        "TickData", "BarData", "OrderData", "TradeData",
        "PositionData", "AccountData",

        # 事件常量
        "EVENT_TICK", "EVENT_ORDER", "EVENT_TRADE",
        "EVENT_POSITION", "EVENT_ACCOUNT", "EVENT_LOG",

        # 终端引擎
        "TerminalEngine", "get_terminal_engine", "reset_terminal_engine"
    ]
