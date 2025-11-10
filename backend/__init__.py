# -*- coding: utf-8 -*-
"""
Backend主模块.

提供统一的后端服务入口。
"""

__version__ = "1.0.0"
__author__ = "星辰科技"

# 导入启动模块
from . import startup

# 延迟导出核心模块，避免模块级初始化问题
def _lazy_import_core():
    """延迟导入核心模块"""
    from .core.vnpy_imports import (
        # VnPy集成
        VNPY_AVAILABLE,
        MainEngine,
        EventEngine,
        Event,
        TickData,
        BarData,
        OrderData,
        TradeData,
        PositionData,
        AccountData,
        EVENT_TICK,
        EVENT_ORDER,
        EVENT_TRADE,
        EVENT_POSITION,
        EVENT_ACCOUNT,
        EVENT_LOG,
        # 工具
        setup_logging,
    )
    from .core.base import (
        # 共享服务
        ServiceManager,
        ErrorSeverity,
        get_service_manager,
        get_main_engine,
        get_event_engine,
        get_china_stock_engine,
    )
    from .core.models import (
        # 数据模型
        DataModelManager,
        get_data_model_manager,
    )

    # 将导入的变量添加到当前模块的全局命名空间
    import sys
    current_module = sys.modules[__name__]

    # VnPy集成
    current_module.VNPY_AVAILABLE = VNPY_AVAILABLE  # type: ignore[reportAttributeAccessIssue]
    current_module.MainEngine = MainEngine  # type: ignore[reportAttributeAccessIssue]
    current_module.EventEngine = EventEngine  # type: ignore[reportAttributeAccessIssue]
    current_module.Event = Event  # type: ignore[reportAttributeAccessIssue]
    current_module.TickData = TickData  # type: ignore[reportAttributeAccessIssue]
    current_module.BarData = BarData  # type: ignore[reportAttributeAccessIssue]
    current_module.OrderData = OrderData  # type: ignore[reportAttributeAccessIssue]
    current_module.TradeData = TradeData  # type: ignore[reportAttributeAccessIssue]
    current_module.PositionData = PositionData  # type: ignore[reportAttributeAccessIssue]
    current_module.AccountData = AccountData  # type: ignore[reportAttributeAccessIssue]
    current_module.EVENT_TICK = EVENT_TICK  # type: ignore[reportAttributeAccessIssue]
    current_module.EVENT_ORDER = EVENT_ORDER  # type: ignore[reportAttributeAccessIssue]
    current_module.EVENT_TRADE = EVENT_TRADE  # type: ignore[reportAttributeAccessIssue]
    current_module.EVENT_POSITION = EVENT_POSITION  # type: ignore[reportAttributeAccessIssue]
    current_module.EVENT_ACCOUNT = EVENT_ACCOUNT  # type: ignore[reportAttributeAccessIssue]
    current_module.EVENT_LOG = EVENT_LOG  # type: ignore[reportAttributeAccessIssue]

    # 共享服务
    current_module.ServiceManager = ServiceManager  # type: ignore[reportAttributeAccessIssue]
    current_module.ErrorSeverity = ErrorSeverity  # type: ignore[reportAttributeAccessIssue]
    current_module.get_service_manager = get_service_manager  # type: ignore[reportAttributeAccessIssue]
    current_module.get_main_engine = get_main_engine  # type: ignore[reportAttributeAccessIssue]
    current_module.get_event_engine = get_event_engine  # type: ignore[reportAttributeAccessIssue]
    current_module.get_china_stock_engine = get_china_stock_engine  # type: ignore[reportAttributeAccessIssue]

    # 数据模型
    current_module.DataModelManager = DataModelManager  # type: ignore[reportAttributeAccessIssue]
    current_module.get_data_model_manager = get_data_model_manager  # type: ignore[reportAttributeAccessIssue]

    # 工具
    current_module.setup_logging = setup_logging  # type: ignore[reportAttributeAccessIssue]

# 延迟初始化标志
_core_imported = False

def _ensure_core_imported():
    """确保核心模块导入已完成"""
    global _core_imported
    if not _core_imported:
        _lazy_import_core()
        _core_imported = True

# 创建延迟代理
class _LazyCoreProxy:
    """延迟访问代理"""
    def __init__(self, name):
        self._name = name
        self._value = None
        self._initialized = False

    def _get_value(self):
        if not self._initialized:
            _ensure_core_imported()
            _ensure_services_imported()
            import sys
            current_module = sys.modules[__name__]
            self._value = getattr(current_module, self._name)
            self._initialized = True
        return self._value

    def __getattr__(self, name):
        return getattr(self._get_value(), name)

    def __call__(self, *args, **kwargs):
        return self._get_value()(*args, **kwargs)  # type: ignore[reportOptionalCall]

    def __repr__(self):
        return repr(self._get_value())

# VnPy集成
VNPY_AVAILABLE = _LazyCoreProxy('VNPY_AVAILABLE')
MainEngine = _LazyCoreProxy('MainEngine')
EventEngine = _LazyCoreProxy('EventEngine')
Event = _LazyCoreProxy('Event')
TickData = _LazyCoreProxy('TickData')
BarData = _LazyCoreProxy('BarData')
OrderData = _LazyCoreProxy('OrderData')
TradeData = _LazyCoreProxy('TradeData')
PositionData = _LazyCoreProxy('PositionData')
AccountData = _LazyCoreProxy('AccountData')
EVENT_TICK = _LazyCoreProxy('EVENT_TICK')
EVENT_ORDER = _LazyCoreProxy('EVENT_ORDER')
EVENT_TRADE = _LazyCoreProxy('EVENT_TRADE')
EVENT_POSITION = _LazyCoreProxy('EVENT_POSITION')
EVENT_ACCOUNT = _LazyCoreProxy('EVENT_ACCOUNT')
EVENT_LOG = _LazyCoreProxy('EVENT_LOG')

# 共享服务
ServiceManager = _LazyCoreProxy('ServiceManager')
ErrorSeverity = _LazyCoreProxy('ErrorSeverity')
get_service_manager = _LazyCoreProxy('get_service_manager')
get_main_engine = _LazyCoreProxy('get_main_engine')
get_event_engine = _LazyCoreProxy('get_event_engine')
get_china_stock_engine = _LazyCoreProxy('get_china_stock_engine')

# 数据模型
DataModelManager = _LazyCoreProxy('DataModelManager')
get_data_model_manager = _LazyCoreProxy('get_data_model_manager')

# 工具
setup_logging = _LazyCoreProxy('setup_logging')

# 延迟导出其他模块，避免模块级初始化问题
def _lazy_import_services():
    """延迟导入服务模块"""
    from .services.database_adapter import DatabaseManager
    from .services.data_center_service import DataCenterService
    from .services.market_board_service import MarketBoardService
    from .services.portfolio_service import PortfolioService
    from .services.strategy_center_service import StrategyCenterService
    from .services.ai_assistant_service import AIAssistantService
    from .services.system_manager_service import SystemManagerService
    from .services.trading_gateway_service import TradingGatewayService
    from .core.config import get_settings

    # 将导入的变量添加到当前模块的全局命名空间
    import sys
    current_module = sys.modules[__name__]

    current_module.DatabaseManager = DatabaseManager  # type: ignore[reportAttributeAccessIssue]
    current_module.DataCenterService = DataCenterService  # type: ignore[reportAttributeAccessIssue]
    current_module.MarketBoardService = MarketBoardService  # type: ignore[reportAttributeAccessIssue]
    current_module.PortfolioService = PortfolioService  # type: ignore[reportAttributeAccessIssue]
    current_module.StrategyCenterService = StrategyCenterService  # type: ignore[reportAttributeAccessIssue]
    current_module.AIAssistantService = AIAssistantService  # type: ignore[reportAttributeAccessIssue]
    current_module.SystemManagerService = SystemManagerService  # type: ignore[reportAttributeAccessIssue]
    current_module.TradingGatewayService = TradingGatewayService  # type: ignore[reportAttributeAccessIssue]
    current_module.get_settings = get_settings  # type: ignore[reportAttributeAccessIssue]

# 延迟初始化标志
_services_imported = False

def _ensure_services_imported():
    """确保服务模块导入已完成"""
    global _services_imported
    if not _services_imported:
        _lazy_import_services()
        _services_imported = True

# 创建延迟代理
DatabaseManager = _LazyCoreProxy('DatabaseManager')
DataCenterService = _LazyCoreProxy('DataCenterService')
MarketBoardService = _LazyCoreProxy('MarketBoardService')
PortfolioService = _LazyCoreProxy('PortfolioService')
StrategyCenterService = _LazyCoreProxy('StrategyCenterService')
AIAssistantService = _LazyCoreProxy('AIAssistantService')
SystemManagerService = _LazyCoreProxy('SystemManagerService')
TradingGatewayService = _LazyCoreProxy('TradingGatewayService')
get_settings = _LazyCoreProxy('get_settings')

__all__ = [
    # 版本信息
    "__version__",
    "__author__",
    # VnPy核心
    "VNPY_AVAILABLE",
    "MainEngine",
    "EventEngine",
    "Event",
    "TickData",
    "BarData",
    "OrderData",
    "TradeData",
    "PositionData",
    "AccountData",
    "EVENT_TICK",
    "EVENT_ORDER",
    "EVENT_TRADE",
    "EVENT_POSITION",
    "EVENT_ACCOUNT",
    "EVENT_LOG",
    # 服务管理
    "ServiceManager",
    "ErrorSeverity",
    "get_service_manager",
    "get_main_engine",
    "get_event_engine",
    "get_china_stock_engine",
    # 数据库
    "DatabaseManager",
    "DataModelManager",
    "get_data_model_manager",
    # 业务服务
    "DataCenterService",
    "MarketBoardService",
    "PortfolioService",
    "StrategyCenterService",
    "AIAssistantService",
    "SystemManagerService",
    "TradingGatewayService",
    # 工具函数
    "setup_logging",
    # 配置管理
    "get_settings",
]
