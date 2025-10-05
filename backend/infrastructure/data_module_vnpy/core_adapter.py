# -*- coding: utf-8 -*-
"""
VnPy核心适配器.

通过vnpy主包统一接入所有VnPy功能
"""

import logging
from typing import Any, Dict, Optional, TYPE_CHECKING, Type

# VnPy core imports
from vnpy.event import Event
from vnpy.trader.app import BaseApp
from vnpy.trader.constant import Direction, Exchange, Interval, OrderType, Status
from vnpy.trader.datafeed import BaseDatafeed
from vnpy.trader.gateway import BaseGateway
from vnpy.trader.object import (
    AccountData,
    BarData,
    CancelRequest,
    HistoryRequest,
    OrderData,
    OrderRequest,
    PositionData,
    SubscribeRequest,
    TickData,
    TradeData,
)

# Type-only imports for type checking
if TYPE_CHECKING:
    from vnpy.trader.engine import MainEngine
    from vnpy.event import EventEngine
else:
    # Runtime imports with fallbacks
    try:
        from vnpy import MainEngine, EventEngine
    except ImportError:
        # Fallback imports if not available in vnpy root
        try:
            from vnpy.trader.engine import MainEngine
            from vnpy.event import EventEngine
        except ImportError:
            MainEngine = None
            EventEngine = None

# Optional gateway imports
try:
    from vnpy_ctp import CtpGateway  # type: ignore
except ImportError:
    CtpGateway = None

try:
    from vnpy_xtp import XtpGateway  # type: ignore
except ImportError:
    XtpGateway = None

try:
    from vnpy_ib import IbGateway  # type: ignore
except ImportError:
    IbGateway = None

try:
    from vnpy_paperaccount import PaperAccountGateway  # type: ignore
except ImportError:
    PaperAccountGateway = None

# Optional app imports
try:
    from vnpy_ctastrategy import CtaStrategyApp  # type: ignore
except ImportError:
    CtaStrategyApp = None

try:
    from vnpy_portfoliostrategy import PortfolioStrategyApp  # type: ignore
except ImportError:
    PortfolioStrategyApp = None

try:
    from vnpy_algotrading import AlgoTradingApp  # type: ignore
except ImportError:
    AlgoTradingApp = None

try:
    from vnpy_datarecorder import DataRecorderApp  # type: ignore
except ImportError:
    DataRecorderApp = None

try:
    from vnpy_riskmanager import RiskManagerApp  # type: ignore
except ImportError:
    RiskManagerApp = None

try:
    from vnpy_chartwizard import ChartWizardApp  # type: ignore
except ImportError:
    ChartWizardApp = None

# Optional datafeed imports
try:
    from vnpy_tushare import TushareDatafeed  # type: ignore
except ImportError:
    TushareDatafeed = None

try:
    from vnpy_rqdata import RqdataDatafeed  # type: ignore
except ImportError:
    RqdataDatafeed = None

try:
    from vnpy_ifind import IfindDatafeed  # type: ignore
except ImportError:
    IfindDatafeed = None

logger = logging.getLogger(__name__)


class VnPyCoreAdapter:
    """VnPy核心适配器 - 通过vnpy主包统一接入."""

    def __init__(self):
        """初始化VnPy核心适配器."""
        self.event_engine: Optional["EventEngine"] = None
        self.main_engine: Optional["MainEngine"] = None
        self.gateways: Dict[str, Type[BaseGateway]] = {}
        self.apps: Dict[str, Type[BaseApp]] = {}
        self.datafeeds: Dict[str, Type[BaseDatafeed]] = {}
        self._initialized = False

    def initialize(self) -> bool:
        """初始化VnPy核心引擎."""
        try:
            # 检查是否可用
            if EventEngine is None or MainEngine is None:
                logger.error("VnPy核心组件不可用，请检查vnpy安装")
                return False

            # 创建事件引擎
            self.event_engine = EventEngine()

            # 创建主引擎
            self.main_engine = MainEngine(self.event_engine)

            # 启动事件引擎
            if self.event_engine:
                self.event_engine.start()

            # 注册核心组件
            self._register_core_components()

            self._initialized = True
            logger.info("VnPy核心适配器初始化成功")
            return True

        except (ImportError, AttributeError, RuntimeError) as e:
            logger.error("VnPy核心适配器初始化失败: %s", e)
            return False

    def _register_core_components(self):
        """注册核心组件."""
        try:
            # 注册交易网关
            self._register_gateways()

            # 注册应用模块
            self._register_apps()

            # 注册数据源
            self._register_datafeeds()

        except (ImportError, AttributeError, RuntimeError) as e:
            logger.error("注册核心组件失败: %s", e)

    def _register_gateways(self):
        """注册交易网关."""
        try:
            if self.main_engine is None:
                logger.warning("主引擎未初始化，跳过网关注册")
                return

            # 注册可用的网关到主引擎
            gateways_to_register = []

            if CtpGateway is not None:
                self.main_engine.add_gateway(CtpGateway)
                gateways_to_register.append(("CTP", CtpGateway))

            if XtpGateway is not None:
                self.main_engine.add_gateway(XtpGateway)
                gateways_to_register.append(("XTP", XtpGateway))

            if IbGateway is not None:
                self.main_engine.add_gateway(IbGateway)
                gateways_to_register.append(("IB", IbGateway))

            if PaperAccountGateway is not None:
                self.main_engine.add_gateway(PaperAccountGateway)
                gateways_to_register.append(("PAPER", PaperAccountGateway))

            # 保存引用
            self.gateways.update(dict(gateways_to_register))

            logger.info(
                "交易网关注册完成,已注册: %s",
                [name for name, _ in gateways_to_register],
            )

        except (AttributeError, RuntimeError) as e:
            logger.error("注册交易网关失败: %s", e)

    def _register_apps(self):
        """注册应用模块."""
        try:
            if self.main_engine is None:
                logger.warning("主引擎未初始化，跳过应用注册")
                return

            # 注册可用的应用到主引擎
            apps_to_register = []

            if CtaStrategyApp is not None:
                self.main_engine.add_app(CtaStrategyApp)
                apps_to_register.append(("CTA_STRATEGY", CtaStrategyApp))

            if PortfolioStrategyApp is not None:
                self.main_engine.add_app(PortfolioStrategyApp)
                apps_to_register.append(("PORTFOLIO_STRATEGY", PortfolioStrategyApp))

            if AlgoTradingApp is not None:
                self.main_engine.add_app(AlgoTradingApp)
                apps_to_register.append(("ALGO_TRADING", AlgoTradingApp))

            if DataRecorderApp is not None:
                self.main_engine.add_app(DataRecorderApp)
                apps_to_register.append(("DATA_RECORDER", DataRecorderApp))

            if RiskManagerApp is not None:
                self.main_engine.add_app(RiskManagerApp)
                apps_to_register.append(("RISK_MANAGER", RiskManagerApp))

            if ChartWizardApp is not None:
                self.main_engine.add_app(ChartWizardApp)
                apps_to_register.append(("CHART_WIZARD", ChartWizardApp))

            # 保存引用
            self.apps.update(dict(apps_to_register))

            logger.info(
                "应用模块注册完成,已注册: %s", [name for name, _ in apps_to_register]
            )

        except (AttributeError, RuntimeError) as e:
            logger.error("注册应用模块失败: %s", e)

    def _register_datafeeds(self):
        """注册数据源."""
        try:
            # 保存可用的数据源引用
            datafeeds_to_register = []

            if TushareDatafeed is not None:
                datafeeds_to_register.append(("TUSHARE", TushareDatafeed))

            if RqdataDatafeed is not None:
                datafeeds_to_register.append(("RQDATA", RqdataDatafeed))

            if IfindDatafeed is not None:
                datafeeds_to_register.append(("IFIND", IfindDatafeed))

            # 保存引用
            self.datafeeds.update(dict(datafeeds_to_register))

            logger.info(
                "数据源注册完成,已注册: %s", [name for name, _ in datafeeds_to_register]
            )

        except (AttributeError, RuntimeError) as e:
            logger.error("注册数据源失败: %s", e)

    def get_main_engine(self) -> Optional["MainEngine"]:
        """获取主引擎."""
        return self.main_engine

    def get_event_engine(self) -> Optional["EventEngine"]:
        """获取事件引擎."""
        return self.event_engine

    def create_tick_data(self, **kwargs) -> TickData:
        """创建Tick数据对象."""
        return TickData(**kwargs)

    def create_bar_data(self, **kwargs) -> BarData:
        """创建Bar数据对象."""
        return BarData(**kwargs)

    def create_event(self, event_type: str, data: Any) -> Event:
        """创建事件对象."""
        return Event(event_type, data)

    def put_event(self, event: Event):
        """推送事件."""
        if self.event_engine:
            self.event_engine.put(event)

    def is_initialized(self) -> bool:
        """检查是否已初始化."""
        return self._initialized

    def shutdown(self):
        """关闭适配器."""
        try:
            if self.event_engine:
                self.event_engine.stop()

            if self.main_engine:
                self.main_engine.close()

            self._initialized = False
            logger.info("VnPy核心适配器已关闭")

        except (AttributeError, RuntimeError) as e:
            logger.error("关闭VnPy核心适配器失败: %s", e)


# 全局适配器实例
vnpy_adapter = VnPyCoreAdapter()


# 导出常用类和常量
__all__ = [
    "VnPyCoreAdapter",
    "vnpy_adapter",
    "AccountData",
    "BarData",
    "CancelRequest",
    "Direction",
    "Event",
    "Exchange",
    "HistoryRequest",
    "Interval",
    "OrderData",
    "OrderRequest",
    "OrderType",
    "PositionData",
    "Status",
    "SubscribeRequest",
    "TickData",
    "TradeData",
    "SubscribeRequest",
    "OrderRequest",
    "CancelRequest",
    "HistoryRequest",
    "Exchange",
    "Interval",
    "Direction",
    "OrderType",
    "Status",
    "Event",
]
