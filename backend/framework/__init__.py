"""
Terminal Framework - 统一框架层API
提供VnPy集成、数据模型、配置、服务、生命周期管理等功能

此模块整合了 foundation、runtime、lifecycle、integration 四个子模块，
提供统一的导入接口。
"""

# ============================================================================
# Foundation 层 - 基础抽象
# ============================================================================

# VnPy集成
from .foundation import (
    ensure_vnpy_imported,
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
    PANDAS_AVAILABLE,
    NUMPY_AVAILABLE,
    pd,
    np,
)

# 数据模型
from .foundation import (
    UnifiedMarketData,
    UnifiedOrder,
    UnifiedTrade,
    UnifiedPosition,
    UnifiedAccount,
    ContractInfo,
    Exchange,
    DataSource,
    DataConverter,
)

# 扩展数据模型
from .foundation import (
    SymbolInfo,
    DownloadTask,
    DataSourceConfig,
    BacktestConfig,
    BacktestResult,
    OptimizationConfig,
    GatewayConfig,
    StrategyInstance,
    SystemStatus,
    ProcessInfo,
    AlertConfig,
)

# 配置系统
from .foundation import (
    get_settings,
    TerminalSettings,
    DatabaseConfig,
    LoggingConfig,
    TradingConfig,
    ConfigManager,
)

# 服务系统
from .foundation import (
    ServiceBase,
    ServiceStatus,
    ServiceError,
    ServiceRegistry,
    get_service_registry,
    register_service,
    get_service,
)

# 引擎管理
from .foundation import (
    get_main_engine,
    get_event_engine,
    EngineManager,
)

# 模块生命周期
from .foundation import (
    ModuleLifecycle,
    ModuleState,
    ModuleEventBus,
)

# 依赖管理
from .foundation import (
    DependencyResolver,
    DependencyGraph,
)

# 调度系统
from .foundation import (
    CronScheduler,
)

# ============================================================================
# Lifecycle 层 - 生命周期管理
# ============================================================================

# 启动编排
from .lifecycle import (
    StartupOrchestrator,
    StartupContext,
    StartupResult,
    StartupStage,
    StartupPhase,
    UIActivationStage,  # 添加UI激活阶段
)

# 进程管理
from .lifecycle import (
    ProcessManager,
    ProcessStatus,
    ProcessSpec,
)

# 健康检查
from .lifecycle import (
    HealthCheckManager,
    HealthStatus,
)

# 生命周期管理
from .lifecycle import (
    LifecycleManager,
    get_lifecycle_manager,
)

# ============================================================================
# Runtime 层 - 运行时固件
# ============================================================================

# 日志系统
from .runtime import (
    LoggingSystemManager,
    get_logging_manager,
    get_logger,
    LazyLogger,
    LogType,
)

# 监控系统
from .runtime import (
    SystemMonitor,
    HealthMonitor,
    MetricsCollector,
    AlertManager,
)

# ============================================================================
# Integration 层 - 框架集成
# ============================================================================

# 框架主类
from .integration import (
    Framework,
    FrameworkStatus,
    get_framework,
    init_framework,
    shutdown_framework,
)

# Native集成
from .integration import (
    NativeIntegrationError,
    NativePerformanceMonitor,
    NativeFunctionWrapper,
    NativeMemoryManager,
    NativeModuleLoader,
    NativeHotReloader,
    NativeCompatibilityChecker,
    NativeIntegrationManager,
)

# 服务注册扩展
from .integration import (
    ServiceRegistryExtensions,
    extend_service_registry,
)

# 工具函数
from .integration import (
    cleanup_temp_files,
    cleanup_old_logs,
    cleanup_cache,
    ensure_directory_structure,
    backup_configuration,
    restore_configuration,
)

# ============================================================================
# 导出清单
# ============================================================================

__all__ = [
    # VnPy集成
    "ensure_vnpy_imported",
    "VNPY_AVAILABLE",
    "PANDAS_AVAILABLE",
    "NUMPY_AVAILABLE",
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
    "pd",
    "np",

    # 数据模型
    "UnifiedMarketData",
    "UnifiedOrder",
    "UnifiedTrade",
    "UnifiedPosition",
    "UnifiedAccount",
    "ContractInfo",
    "Exchange",
    "DataSource",
    "DataConverter",

    # 扩展数据模型
    "SymbolInfo",
    "DownloadTask",
    "DataSourceConfig",
    "BacktestConfig",
    "BacktestResult",
    "OptimizationConfig",
    "GatewayConfig",
    "StrategyInstance",
    "SystemStatus",
    "ProcessInfo",
    "AlertConfig",

    # 配置系统
    "get_settings",
    "TerminalSettings",
    "DatabaseConfig",
    "LoggingConfig",
    "TradingConfig",
    "ConfigManager",

    # 服务系统
    "ServiceBase",
    "ServiceStatus",
    "ServiceError",
    "ServiceRegistry",
    "get_service_registry",
    "register_service",
    "get_service",

    # 引擎管理
    "get_main_engine",
    "get_event_engine",
    "EngineManager",

    # 模块生命周期
    "ModuleLifecycle",
    "ModuleState",
    "ModuleEventBus",

    # 依赖管理
    "DependencyResolver",
    "DependencyGraph",

    # 调度系统
    "CronScheduler",

    # 启动编排
    "StartupOrchestrator",
    "StartupContext",
    "StartupResult",
    "StartupStage",
    "StartupPhase",
    "UIActivationStage",

    # 进程管理
    "ProcessManager",
    "ProcessStatus",
    "ProcessSpec",

    # 健康检查
    "HealthCheckManager",
    "HealthStatus",

    # 生命周期管理
    "LifecycleManager",
    "get_lifecycle_manager",

    # 日志系统
    "LoggingSystemManager",
    "get_logging_manager",
    "get_logger",
    "LazyLogger",
    "LogType",

    # 监控系统
    "SystemMonitor",
    "HealthMonitor",
    "MetricsCollector",
    "AlertManager",

    # 框架主类
    "Framework",
    "FrameworkStatus",
    "get_framework",
    "init_framework",
    "shutdown_framework",

    # Native集成
    "NativeIntegrationError",
    "NativePerformanceMonitor",
    "NativeFunctionWrapper",
    "NativeMemoryManager",
    "NativeModuleLoader",
    "NativeHotReloader",
    "NativeCompatibilityChecker",
    "NativeIntegrationManager",

    # 服务注册扩展
    "ServiceRegistryExtensions",
    "extend_service_registry",

    # 工具函数
    "cleanup_temp_files",
    "cleanup_old_logs",
    "cleanup_cache",
    "ensure_directory_structure",
    "backup_configuration",
    "restore_configuration",
]
