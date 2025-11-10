# -*- coding: utf-8 -*-
"""
Type stubs for backend.core.base module
"""

from typing import Any, Dict, List, Optional, Union, TYPE_CHECKING
from enum import Enum

if TYPE_CHECKING:
    import datetime
    import json
    import threading
    import time
    import traceback
    import logging
    from pathlib import Path

# Lazy loaded modules and availability flags
PANDAS_AVAILABLE: bool
NUMPY_AVAILABLE: bool
PSUTIL_AVAILABLE: bool
VNPY_AVAILABLE: bool
CTA_ENGINE_AVAILABLE: bool
ALGO_ENGINE_AVAILABLE: bool
PORTFOLIO_ENGINE_AVAILABLE: bool
CTP_GATEWAY_AVAILABLE: bool
IB_GATEWAY_AVAILABLE: bool
PAPERACCOUNT_GATEWAY_AVAILABLE: bool
TUSHARE_DATAFEED_AVAILABLE: bool
RQDATA_DATAFEED_AVAILABLE: bool
SYSTEM_MODULE_AVAILABLE: bool

# Lazy loaded module placeholders
if TYPE_CHECKING:
    pd: Any
    np: Any
    psutil: Any
    MainEngine: Any
    EventEngine: Any
    Event: Any
    TickData: Any
    BarData: Any
    OrderData: Any
    TradeData: Any
    PositionData: Any
    AccountData: Any
    EVENT_TICK: Any
    EVENT_ORDER: Any
    EVENT_TRADE: Any
    EVENT_POSITION: Any
    EVENT_ACCOUNT: Any
    EVENT_LOG: Any
    CTA_ENGINE: Any
    ALGO_ENGINE: Any
    PORTFOLIO_ENGINE: Any
    CTP_GATEWAY: Any
    IB_GATEWAY: Any
    PAPER_ACCOUNT_GATEWAY: Any
    TUSHARE_DATAFEED: Any
    RQDATA_DATAFEED: Any
    SystemMonitor: Any
    ProcessManager: Any
    setup_logging: Any
    vnpy_to_pandas: Any
    CtpGateway: Any
    IbGateway: Any
    PaperAccountGateway: Any
    PortfolioEngine: Any
    RqdataDatafeed: Any
    TushareDatafeed: Any

# Service management types
class ErrorSeverity(Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

class ServiceError:
    def __init__(
        self,
        service_name: str,
        error_type: str,
        message: str,
        exception: Optional[Exception] = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
    ) -> None: ...
    service_name: str
    error_type: str
    message: str
    exception: Optional[Exception]
    severity: ErrorSeverity
    timestamp: str
    traceback: Optional[str]

    def to_dict(self) -> Dict[str, Any]: ...
    def get_user_friendly_message(self) -> str: ...

class ServiceManager:
    def __init__(self) -> None: ...
    services: Dict[str, Any]
    errors: List[ServiceError]
    initialization_attempted: bool
    initialization_completed: bool

    def register_service(self, name: str, service: Any) -> bool: ...
    def get_service(self, name: str, silent: bool = False) -> Any: ...
    def has_service(self, name: str) -> bool: ...
    def list_services(self) -> List[str]: ...
    def record_error(
        self,
        service_name: str,
        error_type: str,
        message: str,
        exception: Optional[Exception] = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
    ) -> None: ...
    def get_error_summary(self) -> Dict[str, Any]: ...
    def get_user_friendly_error_report(self) -> str: ...
    def clear_errors(self) -> None: ...
    def get_service_status(self) -> Dict[str, str]: ...
    def get_detailed_error_log(self) -> List[Dict[str, Any]]: ...
    def export_error_report(self, file_path: str) -> bool: ...

# Service management functions
def get_service_manager() -> ServiceManager: ...
def get_main_engine() -> Optional[Any]: ...
def get_event_engine() -> Optional[Any]: ...
def get_china_stock_engine() -> Optional[Any]: ...
def set_main_engine(engine: Any) -> None: ...
def set_event_engine(engine: Any) -> None: ...
def set_china_stock_engine(engine: Any) -> None: ...
def get_error_report() -> str: ...
def clear_error_log() -> None: ...

# Service initializer types (lazy loaded)
class InitializationPhase(Enum):
    STARTUP = "startup"
    SERVICES = "services"
    ENGINES = "engines"
    COMPLETE = "complete"

class ServiceInitializer:
    pass

def initialize_services() -> None: ...
def initialize_real_services() -> None: ...
def shutdown_services() -> None: ...
def shutdown_real_services() -> None: ...
