# -*- coding: utf-8 -*-
# Backend 后端服务架构文档

## 📋 目录结构

```
backend/
├── core/           # 核心基础模块
├── services/       # 业务服务模块
└── infrastructure/ # 底层基础设施
    ├── data_module_vnpy/  # VnPy数据模块
    ├── native/           # Native性能扩展
    ├── system_vnpy/      # 系统基础设施模块
    └── [其他基础设施模块...]
```

---

## 🏗️ Core 核心模块

核心模块提供后端服务的基础架构，包括服务管理、配置管理、数据模型和基础服务类。

### 1. `base.py` - 核心基础模块

**功能定位：**
- 提供全局服务管理器（`ServiceManager`）
- 管理 VnPy 核心引擎（`MainEngine`、`EventEngine`、`ChinaStockEngine`）的全局访问
- 提供全局引擎访问器（`get_main_engine`、`get_event_engine` 等）
- 向后兼容导入桥接（服务初始化器已迁移至 `backend.startup.initializers`）

**核心接口：**
```python
# 服务管理
get_service_manager() -> ServiceManager

# 服务初始化（已迁移到 backend.startup.initializers）
from backend.startup.initializers.service_initializer import initialize_services, shutdown_services
initialize_services(progress_callback=None, fast_startup=True) -> bool
shutdown_services() -> None

# VnPy引擎访问
get_main_engine() -> MainEngine
get_event_engine() -> EventEngine
get_china_stock_engine() -> ChinaStockEngine
set_main_engine(engine: MainEngine)
set_event_engine(engine: EventEngine)
set_china_stock_engine(engine: ChinaStockEngine)
```

> ⚠️ **使用建议（v1.5+）**：上述 `set_*` 系列方法仅为遗留代码兼容入口。新代码应通过 `backend.startup.context.StartupContext` 暴露的 `service_registry` / `service_manager` 访问引擎实例，保持“单一事实来源”。

---

### 2. `config.py` - 配置管理系统

**功能定位：**
- 使用 Pydantic BaseSettings 提供统一配置管理
- 支持从 JSON 文件（`config/terminal_config.json`）和环境变量加载配置
- 提供数据库、VnPy、API、日志、AI、自适应、启动、监控等多种配置类
- 支持配置的动态更新和运行时能力管理

**核心接口：**
```python
# 全局配置管理
get_settings() -> Settings
init_settings(config_file: Optional[str] = None) -> Settings

# 运行时能力管理
update_capabilities(values: Dict[str, Any]) -> None
get_capabilities() -> Dict[str, Any]

# 配置类
class Settings(BaseSettings):
    database: DatabaseConfig
    vnpy: VnPyConfig
    api: APIConfig
    logging: LoggingConfig
    ai: AIConfig
    adaptive: AdaptiveConfig
    startup: StartupConfig
    monitor: MonitorConfig
```

---

### 3. `models.py` - 统一数据模型

**功能定位：**
- 定义系统所有核心数据模型，提供统一的数据表示
- 使用 `dataclasses` 定义轻量级核心数据结构
- 使用 `pydantic.BaseModel` 定义复杂的 API 和业务模型
- 提供数据模型管理器（`DataModelManager`）用于内存缓存

**核心数据类型：**

**市场数据模型：**
- `UnifiedMarketData` - 统一行情数据
- `SymbolInfo` - 品种信息

**交易数据模型：**
- `UnifiedOrder` - 统一委托单
- `UnifiedTrade` - 统一成交记录
- `UnifiedPosition` - 统一持仓
- `UnifiedAccount` - 统一账户

**业务模型：**
- `DownloadTask` - 数据下载任务
- `DataSourceConfig` - 数据源配置
- `ChartConfig` - 图表配置
- `StrategyFile` - 策略文件
- `BacktestConfig` - 回测配置
- `AIChatMessage` - AI聊天消息
- `GatewayConfig` - 网关配置
- `Portfolio` - 投资组合
- `SystemMetric` - 系统指标
- `AlertRule` - 告警规则
- `LogEntry` - 日志条目

**核心接口：**
```python
# 数据模型管理
get_data_model_manager() -> DataModelManager

class DataModelManager:
    def update_market_data(symbol: str, data: UnifiedMarketData)
    def get_market_data(symbol: str) -> Optional[UnifiedMarketData]
    def update_order(order_id: str, order: UnifiedOrder)
    def get_order(order_id: str) -> Optional[UnifiedOrder]
    def update_position(key: str, position: UnifiedPosition)
    def get_positions() -> Dict[str, UnifiedPosition]
    # ... 更多缓存管理方法
```

---

### 4. `service_base.py` - 服务基类

**功能定位：**
- 提供抽象基类 `BaseService`，强制所有服务实现统一接口
- 提供 `DataConverter` 工具类，统一 VnPy 数据对象到统一数据模型的转换
- 提供 `LoggerMixin` 混入类，为所有服务提供标准化日志功能
- 定义服务状态枚举（`ServiceStatus`）

**核心接口：**
```python
# 服务基类
class BaseService(ABC):
    @abstractmethod
    def initialize() -> bool

    @abstractmethod
    def shutdown() -> bool

    @abstractmethod
    def health_check() -> Dict[str, Any]

    def get_status() -> ServiceStatus
    def get_last_error() -> Optional[str]

# 数据转换器
class DataConverter:
    @staticmethod
    def to_unified_market_data(vnpy_data) -> UnifiedMarketData
    @staticmethod
    def to_unified_order(vnpy_order: OrderData) -> UnifiedOrder
    @staticmethod
    def to_unified_trade(vnpy_trade: TradeData) -> UnifiedTrade
    @staticmethod
    def to_unified_position(vnpy_position: PositionData) -> UnifiedPosition
    @staticmethod
    def to_unified_account(vnpy_account: AccountData) -> UnifiedAccount

# 日志混入
class LoggerMixin:
    def log_info(message: str, **kwargs)
    def log_warning(message: str, **kwargs)
    def log_error(message: str, exc_info=True, **kwargs)
    def log_debug(message: str, **kwargs)
```

---

## 🚀 Services 业务服务模块

业务服务模块实现终端的6大核心功能界面，所有服务继承自 `BaseService`。

### 1. `system_manager_service.py` - 系统管理服务

**功能定位：**
- **日志管理**：日志记录、查询、统计、清理（使用 `LogManager` 和 `LogDatabase`）
- **告警管理**：告警规则引擎、告警生命周期管理（使用 `AlertEngine` 和 `AlertDatabase`）
- **性能监控**：系统性能指标收集、阈值检查（使用 `PerformanceMonitor`）
- **健康检查**：系统健康状态检查、环境检查、进程心跳监控（使用 `HealthChecker`）
- **进程监控**：三进程架构下的监控进程和数据进程健康检查（集成IPC管道心跳检测）
- **异步任务管理**：后台任务调度和执行（使用 `AsyncTaskManager`）
- **测试运行**：单元测试运行和结果管理（使用 `TestRunner`）

**核心接口：**
```python
class SystemManagerService(BaseService):
    # 日志管理
    def get_log_stats() -> Dict[str, Any]
    def cleanup_old_logs(retention_days: int = 30) -> int
    def delete_all_logs() -> int
    def delete_logs_by_ids(log_ids: List[int]) -> int

    # 告警管理
    def add_alert_rule(rule: AlertRule) -> None
    def remove_alert_rule(rule_id: str) -> None
    def get_all_alert_rules() -> List[AlertRule]
    def evaluate_alert_rules(context: Dict[str, Any]) -> List[Alert]
    def acknowledge_alert(alert_id: str, note: str = "") -> bool
    def resolve_alert(alert_id: str, note: str = "") -> bool
    def get_all_alerts() -> List[Alert]

    # 性能监控
    def start_performance_monitoring(interval: float = 5.0) -> None
    def stop_performance_monitoring() -> None
    def get_performance_metrics(category: str = None, hours: int = 1) -> Dict[str, Any]
    def get_monitoring_alerts(limit: int = 100) -> List[Dict[str, Any]]

    # 健康检查
    def check_system_health() -> Dict[str, Any]
    def get_health_check_history(limit: int = 10) -> List[Dict[str, Any]]

    # 异步任务
    def submit_async_task(func: Callable, *args, **kwargs) -> str
    def get_task_result(task_id: str) -> Any
    def cancel_task(task_id: str) -> bool
```

---

### 2. `data_center_service.py` - 数据中心服务

**功能定位：**
- **品种列表管理**：品种列表加载、缓存、刷新、验证（去除未上市品种）
- **数据下载**：历史数据下载、增量下载、下载任务管理（启动、停止、暂停、恢复）
- **数据质量**：数据质量扫描、数据断点检测、自动修复
- **实时推送**：实时行情推送、数据录制
- **数据源管理**：TDX轮询网关、虚拟推送网关、数据源连接管理
- **服务器池管理**：TDX服务器池测速、配置管理

> 📌 **三进程提示**：自 v0.50 起，数据进程负责执行上述重型任务。UI 进程中的 `DataCenterService` 仅保留轻量代理和降级逻辑，通过 native IPC 将请求转发到独立的 `data_process_main.py`。当数据进程不可用时，代理会自动降级为只读缓存模式，并在 Terminal 输出 `WARNING` 级别日志提示。

**核心接口：**
```python
class DataCenterService(BaseService):
    # 品种列表管理
    def reload_symbol_list(force: bool = False) -> Dict[str, Any]
    def refresh_symbol_list() -> Dict[str, Any]
    def get_symbols_from_cache() -> List[Dict[str, Any]]
    def clear_symbol_cache() -> Dict[str, Any]
    def has_symbol_cache() -> bool

    # 本地数据索引
    def get_local_data_index() -> List[Dict[str, Any]]

    # 数据下载
    def start_incremental_download(start_date: str) -> Dict[str, Any]
    def get_download_progress(task_id: str = None) -> Dict[str, Any]
    def stop_download(task_id: str = None) -> Dict[str, Any]
    def pause_download(task_id: str = None) -> Dict[str, Any]
    def resume_download(task_id: str = None) -> Dict[str, Any]
    def check_symbol_exists(symbol: str) -> bool

    # 数据质量
    def get_data_freshness_overview() -> Dict[str, Any]
    def get_data_quality_overview() -> Dict[str, Any]
    def trigger_data_quality_scan(force_refresh: bool = False) -> bool
    def auto_repair_data(symbol: str, issues: List[str]) -> Dict[str, Any]
    def scan_errors_missing_only() -> Dict[str, Any]
    def delete_invalid_symbols() -> Dict[str, Any]

    # 实时推送和录制
    def start_realtime_push(symbols: List[str] = None) -> Dict[str, Any]
    def stop_realtime_push() -> Dict[str, Any]
    def start_data_recording(custom_path: str = None) -> Dict[str, Any]
    def stop_data_recording() -> Dict[str, Any]
    def get_recording_status() -> Dict[str, Any]
    def get_recorded_data(symbol: str, date: str) -> Optional[List[Dict[str, Any]]]

    # 数据源管理
    def get_all_datafeed_status() -> Dict[str, Any]
    def disconnect_datafeed(datafeed_type: str) -> Dict[str, Any]

    # TDX轮询网关
    def start_polling_gateway(config: Dict[str, Any]) -> Dict[str, Any]
    def stop_polling_gateway() -> Dict[str, Any]
    def get_polling_gateway_status() -> Dict[str, Any]

    # 虚拟推送网关
    def start_virtual_gateway(config: Dict[str, Any]) -> Dict[str, Any]
    def stop_virtual_gateway() -> Dict[str, Any]
    def get_virtual_gateway_status() -> Dict[str, Any]

    # 服务器池管理
    def get_server_status() -> Dict[str, Any]
    def retest_server_pool() -> Dict[str, Any]
    def get_server_pool_config() -> Dict[str, Any]
    def set_server_pool_size(size: int) -> Dict[str, Any]
```

---

### 3. `market_board_service.py` - 行情看板服务

**功能定位：**
- **技术指标计算**：集成 talib 库，提供 SMA、EMA、MACD、RSI、BBANDS、KDJ 等技术指标计算
- **历史数据查询**：代理查询历史 K 线数据，委托给 `data_module_vnpy` 或 `DataCenterService`
- **数据可视化支持**：为前端图表提供数据支持

**核心接口：**
```python
class MarketBoardService(BaseService):
    # 历史数据查询
    def query_historical_data(
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = "1d",
        check_gaps: bool = False
    ) -> Dict[str, Any]

    # 技术指标计算
    def calculate_indicator(
        data: List[float],
        indicator_name: str,
        params: Optional[Dict[str, Any]] = None
    ) -> Optional[Union[List[float], Tuple[List[float], ...]]]

    # 支持的技术指标：
    # - SMA: 简单移动平均
    # - EMA: 指数移动平均
    # - MACD: 平滑异同移动平均线
    # - RSI: 相对强弱指标
    # - BBANDS: 布林带
    # - KDJ: 随机指标
```

---

### 4. `strategy_center_service.py` - 策略中心服务

**功能定位：**
- **策略文件管理**：策略文件的创建、读取、更新、删除、重命名
- **策略类型识别**：动态识别策略类型（CTA、Algo、Portfolio、Script、Spread、Option）
- **策略信息解析**：解析策略类名、参数、继承关系
- **回测功能**：集成 `vnpy_ctabacktester`，支持后台回测和结果渲染
- **模板支持**：提供各类策略模板

**核心接口：**
```python
class StrategyCenterService(BaseService):
    # 策略文件管理
    def list_strategy_files(directory: str = "") -> Dict[str, Any]
    def create_strategy_file(file_path: str, template_type: str = None) -> Dict[str, Any]
    def read_strategy_file(file_path: str) -> Dict[str, Any]
    def update_strategy_file(file_path: str, content: str) -> Dict[str, Any]
    def delete_strategy_file(file_path: str) -> Dict[str, Any]
    def rename_strategy_file(old_path: str, new_path: str) -> Dict[str, Any]

    # 策略信息
    def get_available_strategies(
        strategy_folder: str = None,
        engine_type: str = None
    ) -> Dict[str, Any]
    def identify_strategy_type(file_path: str) -> Dict[str, Any]
    def load_strategy_module_info(file_path: str) -> Dict[str, Any]

    # 回测功能
    def start_backtest(strategy_file: str, config: Dict[str, Any]) -> Dict[str, Any]
    def render_backtest_result(task_id: str, strategy_type: str = "ctastrategy") -> Dict[str, Any]
```

---

### 5. `ai_assistant_service.py` - AI 助手服务

**功能定位：**
- **AI 对话**：集成 DeepSeek AI API，提供智能对话功能
- **策略生成**：根据自然语言描述生成策略代码
- **策略优化**：优化现有策略代码性能和可读性
- **策略解释**：解释策略代码逻辑和功能
- **策略调试**：根据错误信息辅助调试策略
- **文件操作工具**：AI 可调用的文件读写删除工具（限定在 `strategies/user_strategies` 目录）

**核心接口：**
```python
class AIAssistantService(BaseService):
    # AI对话
    def chat(user_message: str, context: Dict[str, Any] = None) -> Dict[str, Any]

    # 策略开发辅助
    def generate_strategy_code(
        strategy_description: str,
        strategy_type: str = "ctastrategy"
    ) -> Dict[str, Any]
    def optimize_strategy_code(strategy_code: str) -> Dict[str, Any]
    def explain_strategy_code(strategy_code: str) -> Dict[str, Any]
    def debug_strategy_error(
        strategy_code: str,
        error_message: str
    ) -> Dict[str, Any]

    # AI工具调用（内部）
    def _tool_read_file(file_path: str) -> str
    def _tool_write_file(file_path: str, content: str) -> None
    def _tool_delete_file(file_path: str) -> None
    def _tool_list_strategy_files() -> List[str]
```

---

### 6. `trading_gateway_service.py` - 交易网关服务

**功能定位：**
- **网关管理**：支持多种 VnPy 网关（CTP、IB、PaperAccount、TradeX 等）
- **连接管理**：网关连接、断开、状态查询
- **策略部署**：策略加载、部署、启动、停止、移除
- **交易监控**：实时获取委托、成交、持仓、账户数据
- **风险控制**：集成 VnPy 风控引擎，提供风险参数配置和状态查询
- **动态适配**：根据策略类型动态加载对应的 VnPy 策略应用

**核心接口：**
```python
class TradingGatewayService(BaseService):
    # 网关管理
    def get_gateway_types() -> List[Dict[str, Any]]
    def create_gateway(gateway_name: str, gateway_type: str, config: Dict[str, Any]) -> Dict[str, Any]
    def connect_gateway(gateway_name: str, password: str = None) -> Dict[str, Any]
    def disconnect_gateway(gateway_name: str) -> Dict[str, Any]
    def delete_gateway(gateway_name: str) -> Dict[str, Any]
    def list_gateways() -> List[Dict[str, Any]]

    # 策略部署
    def get_available_strategies(engine_type: str = None) -> Dict[str, Any]
    def load_strategy_from_file(
        gateway_name: str,
        strategy_name: str,
        file_path: str,
        strategy_params: Dict[str, Any]
    ) -> Dict[str, Any]
    def deploy_strategy(
        gateway_name: str,
        strategy_name: str,
        strategy_class: str,
        strategy_params: Dict[str, Any]
    ) -> Dict[str, Any]
    def start_strategy(gateway_name: str, strategy_name: str) -> Dict[str, Any]
    def stop_strategy(gateway_name: str, strategy_name: str) -> Dict[str, Any]
    def remove_strategy(gateway_name: str, strategy_name: str) -> Dict[str, Any]
    def start_all_strategies(gateway_name: str) -> Dict[str, Any]
    def stop_all_strategies(gateway_name: str) -> Dict[str, Any]
    def list_strategies(gateway_name: str) -> Dict[str, Any]

    # 交易监控
    def get_monitoring_data(gateway_name: str) -> Dict[str, Any]
    def get_single_strategy_gateways() -> List[str]
    def get_strategy_monitoring_data(gateway_name: str, strategy_name: str) -> Dict[str, Any]

    # 风险控制
    def get_risk_status() -> Dict[str, Any]
    def update_risk_parameters(parameters: Dict[str, Any]) -> Dict[str, Any]
    def set_risk_active(active: bool) -> Dict[str, Any]

    # 动态策略适配
    def identify_strategy_type(file_path: str) -> Dict[str, Any]
    def get_monitor_template_for_strategy(strategy_type: str) -> str
```

---

### 7. `portfolio_service.py` - 组合投资服务

**功能定位：**
- **组合管理**：自动识别组合（单网关多策略）、创建自定义组合（虚拟网关）
- **实时盈亏计算**：持仓盈亏、交易盈亏、总盈亏
- **历史绩效分析**：按日/周/月统计组合历史绩效
- **风险指标计算**：VaR、CVaR、最大回撤、夏普比率、波动率
- **相关性分析**：计算组合内资产的相关性矩阵
- **事件驱动更新**：监听 VnPy 事件，实时更新持仓、账户、成交数据

**核心接口：**
```python
class PortfolioService(BaseService):
    # 组合管理
    def create_custom_portfolio(
        portfolio_name: str,
        gateway_names: List[str],
        weights: Dict[str, float] = None
    ) -> Dict[str, Any]
    def delete_custom_portfolio(portfolio_name: str) -> Dict[str, Any]
    def list_portfolios() -> Dict[str, Any]

    # 实时盈亏
    def calculate_realtime_pnl(portfolio_name: str) -> Dict[str, Any]
    def get_portfolio_monitoring(portfolio_name: str) -> Dict[str, Any]

    # 历史绩效
    def get_historical_performance(
        portfolio_name: str,
        start_date: str = None,
        end_date: str = None,
        period: str = "daily"
    ) -> Dict[str, Any]
    def calculate_period_statistics(
        portfolio_name: str = None,
        period_type: str = "daily",
        start_date: str = None,
        end_date: str = None
    ) -> Dict[str, Any]

    # 风险指标
    def calculate_portfolio_risk_metrics(
        portfolio_name: str,
        price_history: List[float],
        confidence_level: float = 0.95
    ) -> Dict[str, Any]
    def calculate_correlation_matrix(
        portfolio_name: str,
        returns_data: Dict[str, List[float]]
    ) -> Dict[str, Any]

    # 数据持久化
    def save_trade_to_history(...) -> None
    def save_account_snapshot(...) -> None
```

---

### 8. `database_adapter.py` - 数据库适配器

**功能定位：**
- 提供统一的数据库访问接口
- 支持标准 `sqlite3`（`DatabaseManager`）和 `vnpy_sqlite`（`SQLiteManager`）两种实现
- 管理下载历史、本地数据索引、失效品种、系统表等

**核心接口：**
```python
# 全局访问
get_db_manager() -> DatabaseManager
get_sqlite_manager() -> SQLiteManager
get_database_manager(use_vnpy: bool = False) -> Union[DatabaseManager, SQLiteManager]

# 数据库管理器
class DatabaseManager:
    def save_download_history(task_data: Dict[str, Any])
    def get_download_history(limit: int = 100) -> List[Dict[str, Any]]
    def upsert_local_data_index(symbol: str, ...)
    def get_local_data_index() -> List[Dict[str, Any]]
    def get_invalid_symbols() -> List[str]
    def add_invalid_symbol(symbol: str, reason: str)
    # ... 更多数据库操作方法

class SQLiteManager:
    # 与 DatabaseManager 类似的接口，使用 vnpy_sqlite 实现
```

---

### 9. `vnpy_imports.py` - VnPy 导入适配器

**功能定位：**
- 集中管理所有 VnPy 相关的导入
- 提供可用性标志（`VNPY_AVAILABLE`、`CTA_ENGINE_AVAILABLE` 等）
- 提供工具函数（日志配置、数据转换）

**核心导出：**
```python
# VnPy核心
MainEngine, EventEngine, Event
TickData, BarData, OrderData, TradeData, PositionData, AccountData
EVENT_TICK, EVENT_ORDER, EVENT_TRADE, EVENT_POSITION, EVENT_ACCOUNT, EVENT_LOG

# VnPy策略引擎
CTA_ENGINE, ALGO_ENGINE, PORTFOLIO_ENGINE
CTA_ENGINE_AVAILABLE, ALGO_ENGINE_AVAILABLE, PORTFOLIO_ENGINE_AVAILABLE

# VnPy网关
CTP_GATEWAY, IB_GATEWAY, PAPER_ACCOUNT_GATEWAY
CTP_GATEWAY_AVAILABLE, IB_GATEWAY_AVAILABLE, PAPERACCOUNT_GATEWAY_AVAILABLE

# VnPy数据源
TUSHARE_DATAFEED, RQDATA_DATAFEED
TUSHARE_DATAFEED_AVAILABLE, RQDATA_DATAFEED_AVAILABLE

# 工具函数
setup_logging(name: str = "terminal", level: str = "INFO") -> logging.Logger
vnpy_to_pandas(vnpy_data_list: List[Any], data_type: str = "bar") -> Optional[pd.DataFrame]

# 数据处理库
pd, np, PANDAS_AVAILABLE, NUMPY_AVAILABLE

# 系统监控
psutil, PSUTIL_AVAILABLE
```

---

## 🔧 Infrastructure 底层基础设施

### infrastructure/system_vnpy/ - 系统基础设施模块

提供系统级的基础设施服务，包括模块生命周期管理、延迟日志初始化、依赖管理和热重载功能。

#### 1. `lazy_logger.py` - LazyLogger延迟初始化系统

**功能定位：**
- 解决模块导入时同步调用复杂logger初始化导致的阻塞问题
- 实现带日志缓冲的延迟logger初始化，支持<1秒的模块导入时间
- 提供异步日志缓冲和批量刷新机制

**核心接口：**
```python
# LazyLogger管理
get_lazy_logger(name: str) -> LazyLogger
initialize_all_loggers() -> None
flush_buffered_logs() -> None

# LazyLogger类
class LazyLogger:
    def get_logger() -> logging.Logger
    def buffer_log(level: int, message: str, **kwargs)
    def async_flush() -> Awaitable[None]
```

#### 2. `module_lifecycle.py` - 模块生命周期管理器

**功能定位：**
- 解决Python同步import阻塞整个进程的问题
- 实现异步生命周期管理：导入→注入→初始化→注册
- 支持模块初始化失败不影响其他模块正常工作

**核心接口：**
```python
# 生命周期管理器
get_module_lifecycle_manager() -> ModuleLifecycleManager
initialize_all_modules() -> Awaitable[bool]
reload_module(module_name: str) -> Awaitable[bool]

# 生命周期状态
class ModuleLifecycleState(Enum):
    UNLOADED = "unloaded"
    IMPORTED = "imported"
    INJECTED = "injected"
    INITIALIZING = "initializing"
    INITIALIZED = "initialized"
    FAILED = "failed"
```

#### 3. `module_dependency.py` - 轻量级依赖管理系统

**功能定位：**
- 提供模块依赖解析、循环依赖检测、依赖注入等功能
- 支持可选依赖、版本兼容性检查、动态依赖管理
- 建立轻量级的服务注册和发现机制

**核心接口：**
```python
# 依赖解析器
get_dependency_resolver() -> DependencyResolver
resolve_dependencies(modules: List[str]) -> DependencyResolutionResult
check_circular_dependencies(modules: List[str]) -> List[List[str]]

# 依赖规范
class DependencySpec:
    name: str
    type: DependencyType
    version_constraint: Optional[str]
    optional: bool

# 便捷函数
required(module_name: str, version_spec: Optional[str] = None) -> DependencySpec
optional(module_name: str, version_spec: Optional[str] = None) -> DependencySpec
```

#### 4. `native_module_optimizer.py` - Native模块导入优化器

**功能定位：**
- 优化18个native模块导入时间，实现<0.5秒导入
- 移除logger阻塞，提供并行导入能力
- 支持模块导入性能监控和优化建议

**核心接口：**
```python
# Native模块优化器
get_native_module_optimizer() -> NativeModuleOptimizer
optimize_native_imports() -> Awaitable[bool]
get_import_performance_stats() -> Dict[str, float]

# 模块规范
class NativeModuleSpec:
    name: str
    import_path: str
    optimization_level: int
    dependencies: List[str]
```

#### 5. `module_hot_reload.py` - 模块热重载管理器

**功能定位：**
- 支持运行时模块热重载，无需重启应用
- 提供安全的模块替换、状态迁移、依赖更新等功能
- 支持文件变化监控和自动重载触发

**核心接口：**
```python
# 热重载管理器
get_module_hot_reload_manager() -> ModuleHotReloadManager
enable_hot_reload(module_name: str, watch_path: Optional[str] = None) -> None
disable_hot_reload(module_name: str) -> None
reload_module(module_name: str, trigger: ReloadTrigger) -> Awaitable[ReloadResult]

# 重载事件
class ReloadEvent:
    module_name: str
    trigger: ReloadTrigger
    timestamp: datetime
    reason: str
```

---

### infrastructure/data_module_vnpy/ - VnPy数据模块

提供VnPy框架的数据获取、行情处理、交易接口等能力。

### infrastructure/native/ - Native性能扩展

提供高性能的底层扩展，包括异步I/O、跨进程通信、数值计算等。

### infrastructure/system_vnpy/ - 系统基础设施模块

提供系统级的基础设施服务，包括模块生命周期管理、延迟日志初始化、依赖管理和热重载功能。

**核心组件：**
- `lazy_logger.py` - LazyLogger延迟初始化系统
- `module_lifecycle.py` - 模块生命周期管理器
- `module_dependency.py` - 轻量级依赖管理系统
- `native_module_optimizer.py` - Native模块导入优化器
- `module_hot_reload.py` - 模块热重载管理器
- [其他现有系统组件...]

---

## ⚡ Startup 启动编排（v1.5+）

- **阶段总控**：`StartupOrchestrator`（`backend/startup/orchestrator.py`）统一执行 `EnvSetupStage → LoggingInitStage → QtFrameworkStage → BackendInitStage → UIActivationStage`，并维护全局唯一的 `StartupContext`。
- **启动计划**：`StartupPlan` + `ProcessSupervisor` 通过 `startup_plan.json` 描述三进程 DAG，基于 `asyncio.TaskGroup` 并发调度 `MonitorLauncherWorker`、`DataLauncherWorker`、`BackendInitializerWorker`、`CacheValidatorWorker`。
- **进程生命周期**：`ProcessOrchestrator`（`backend/startup/processes/`）封装状态机（`ProcessState`）、依赖拓扑、重启策略和 Watchdog，供启动阶段与运行期统一管理监控/数据等子进程。
- **原生执行器**：`NativeStartupRuntime`（`native_support.py`）整合原生线程池、`HighPerfEvent` 与 Qt 主线程桥接，支持将 Portfolio/System/Market 等重量级服务后台并行初始化，并提供 `service_tracker.snapshot()` 输出 ready/pending/failed 视图。
- **上下文中心**：`StartupContext`（`context.py`）集中记录事件引擎、主引擎、服务注册表、日志队列、原生运行时、健康快照、UI 预加载任务等信息，是后续阶段和主进程的核心依赖容器。
- **服务初始化**：`ServiceInitializer`（`initializers/service_initializer.py`）迁移至 `backend.startup`，增加类别调度与就绪追踪；`backend.core.base.initialize_services` 仍保留惰性桥接并发出 `DeprecationWarning`。
- **UI 启动桥接**：`backend/startup/ui_startup/` 中的 `StartupCoordinator`、`BootOrchestrator` 与 `backend/startup/health/ui_integration.py` 提供的健康事件桥接，负责 Splash、启动日志、就绪事件与主窗口展示的联动，替换旧版 `ui/startup_coordinator.py`。
- **健康监控**：`backend/startup/health/` 提供启动期健康检查、事件回放、UI 侧进度 API，并复用 `StartupContext.service_tracker` 展示原生执行器统计。

> ✅ **推荐入口**：`python start_new.py`；旧版 `start_async_fixed.py` 仅保留用于特定诊断场景。

---

## 🔗 三进程架构与服务依赖关系

### 三进程划分 (v0.50 架构)

```
┌─────────────────────────────────────────────────────────────┐
│                    UI进程 (主进程)                          │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ UI层 + 业务服务层                                      │ │
│  │ - MainWindow (PySide6)                                 │ │
│  │ - MarketBoardService                                   │ │
│  │ - TradingGatewayService                                │ │
│  │ - PortfolioService                                     │ │
│  │ - StrategyCenterService                                │ │
│  │ - AIAssistantService                                   │ │
│  │ - SystemManagerService                                 │ │
│  │ - DataCenterService (代理层)                           │ │
│  └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
         │                                │
         │ native_ipc                     │ native_ipc
         │ (data_query,                  │ (monitor_alerts,
         │  data_calculation)            │  monitor_status,
         │                                │  monitor_query)
         ↓                                ↓
┌──────────────────────┐      ┌──────────────────────┐
│   数据进程           │      │   监控进程           │
│  ┌────────────────┐ │      │  ┌────────────────┐ │
│  │ ChinaStockEngine│ │      │  │MonitoringProcess│ │
│  │ UnifiedDataMgr │ │      │  │ SystemMonitor  │ │
│  │ LoadBalancer   │ │      │  │ ProcessMonitor │ │
│  │ ServerPoolMgr  │ │      │  │ HardwareMonitor│ │
│  └────────────────┘ │      │  └────────────────┘ │
└──────────────────────┘      └──────────────────────┘
         │                                │
         │                                │
         ↓                                ↓
┌─────────────────────────────────────────────────────────────┐
│              Infrastructure层（底层基础设施）                │
│  ├── native_ipc (Windows Named Pipe + IOCP 跨进程通信)      │
│  ├── native_iocp (异步文件I/O)                               │
│  ├── native_collections (高性能容器: LRU缓存、优先队列)      │
│  ├── native_memory (零拷贝内存操作)                          │
│  ├── native_serialization (批量序列化)                       │
│  ├── native_compute (批量数值运算、哈希计算)                 │
│  ├── native_conversion (批量类型转换)                        │
│  ├── native_gil (无锁队列、无锁哈希表)                       │
│  ├── tdx_asyncio (通达信异步客户端)                          │
│  └── VnPy框架                                                │
└─────────────────────────────────────────────────────────────┘
```

### 启动阶段与Worker职责对照 (v0.50 三进程)

| 阶段 | 主要组件 | 关键Worker/流程 | 重要输出 |
|------|----------|----------------|----------|
| 阶段0 `EnvSetupStage` | 环境变量、路径、DPI 配置 | - | Terminal 输出阶段标记，禁用字节码 |
| 阶段1 `LoggingInitStage` | LoggingHub、MultiProcessLogCollector | - | 生成 `application_startup_*.log`，注册跨进程日志队列 |
| 阶段2 `QtFrameworkStage` | QApplication、EventEngine、MainEngine | - | 预创建事件引擎与主引擎，为后续 Worker 提供上下文 |
| 阶段3 `BackendInitStage` | 三进程并行启动 | `MonitorLauncherWorker`：拉起 `monitor_system.py` 并建立 `monitor_*` 管道;<br>`DataLauncherWorker`：运行 `data_process_main.py`，写入 `data_process_ready.signal`，回放日志队列;<br>`BackendInitializerWorker`：在主进程注册业务服务骨架，等待数据进程 Level 2 | Terminal Stage 3 分支 A/B/C 输出；UI 预加载任务启动 |
| 阶段4 `UIActivationStage` | MainWindow、模块视图 | - | 绑定服务代理，展示主窗口 |

> 以上阶段由 `start_new.py` 驱动，Terminal 仅展示 `STAGE_NODE`、`WARNING+` 级别日志，完整调试信息写入 `logs/application_startup_YYYYMMDD_HHMMSS.log`。

#### Terminal输出策略（最佳实践）
- 控制台仅展示“开始 → 成果 → 结束”，异常展示`WARNING/ERROR/CRITICAL`；详细`DEBUG/INFO`写入事件日志文件。
- 初始化前日志由`MemoryHandler`拦截并在`LoggingInitStage`重放，保证不丢失。
- 多进程乱序日志通过`OrderedLogQueue`编排后按序展示；子进程日志由`MultiProcessLogCollector`汇聚。
- 数据进程（`DataLauncherWorker`）承担“8步缓存验证”，主进程实时回放进度（`STAGE_NODE`）。
- 参考：`启动完整设计文档.md` 与 `backend/infrastructure/system_vnpy/统一日志系统说明文档.md`。

### 关键架构特点

**1. 三进程隔离**
- UI进程:处理用户交互和业务逻辑
- 数据进程:专注于高性能数据处理
- 监控进程:独立监控系统资源

**2. native_ipc通信**
- 替代传统的线程/队列通信
- 基于Windows Named Pipe + IOCP
- 真正的异步跨进程通信
- 延迟<10ms

**3. C扩展性能优化**
- native_iocp:文件I/O性能提升60%
- native_collections:LRU缓存性能提升80%
- native_ipc:跨进程通信延迟降低70%
- native_serialization:序列化性能提升50%
- native_vnpy_conversion:批量行情/订单转换平均耗时降低75%

### 原生扩展集成注意事项（v0.50+）

- `native_vnpy_conversion` 已在 `backend/core/service_base.py` 的 `DataConverter.batch_convert_vnpy_data` 中自动探测。默认启用（环境变量 `NATIVE_VNPY_CONVERSION=1`），当扩展缺失或显式关闭时会回退到纯 Python 实现；输出格式固定为 `dict`，可通过 `NATIVE_VNPY_CONVERSION_OUTPUT=dict` 显式声明。
- `HighPerfLRUCache` 的 `get()` 方法在键不存在时抛出 `KeyError`（与标准字典保持一致）。`DataModelManager`、`DataCenterService` 等模块已增加兼容处理，二次开发时需注意使用 `try/except KeyError` 或封装的 `_safe_cache_get()`、`_task_get()` 等方法，避免因为缺失键导致服务初始化失败。
- 降级路径仍可用：当原生扩展未编译时，代码自动切换到 Python 实现，并输出 `WARNING` 日志提示。建议通过 `backend/infrastructure/native/compile_all.bat` 或 `python setup.py build_ext --inplace` 编译最新扩展。

### 服务依赖关系 (UI进程内)

```
UI层
  ↓
Services层（业务服务）
  ├── SystemManagerService
  ├── DataCenterService (代理层) ──[native_ipc]──> 数据进程
  ├── MarketBoardService → DataCenterService
  ├── StrategyCenterService
  ├── AIAssistantService → StrategyCenterService
  ├── TradingGatewayService → StrategyCenterService
  └── PortfolioService → TradingGatewayService
  ↓
Core层（核心基础）
  ├── base.py (ServiceManager, 全局引擎)
  ├── config.py (配置管理)
  ├── models.py (数据模型)
  └── service_base.py (服务基类)
```

---

## 📝 开发规范

### 1. 服务开发规范

所有业务服务必须：
- 继承自 `BaseService` 抽象基类
- 实现 `initialize()`、`shutdown()`、`health_check()` 方法
- 使用 `LoggerMixin` 进行日志记录
- 使用 `DataConverter` 进行数据转换

### 2. 数据模型规范

- 核心轻量数据使用 `@dataclass` 定义
- API 和业务模型使用 `pydantic.BaseModel` 定义
- 所有模型统一在 `core/models.py` 中定义

### 3. 配置管理规范

- 所有配置项定义在 `core/config.py` 的 `Settings` 类中
- 使用 `get_settings()` 获取全局配置
- 配置文件路径：`config/terminal_config.json`

### 4. 日志规范

- 使用 `LoggerMixin` 提供的日志方法
- 日志自动写入数据库（由 `LogRecordHandler` 处理）
- 日志级别：DEBUG、INFO、WARNING、ERROR、CRITICAL

### 5. 错误处理规范

- 服务方法返回 `Dict[str, Any]` 格式，包含 `success`、`message`、`data` 字段
- 使用 `try-except` 捕获异常，记录错误日志并返回友好的错误信息

---

## 🚀 快速开始

### 初始化服务（推荐流程）

```python
from backend.startup.context import StartupContext
from backend.startup.initializers.service_initializer import ServiceInitializer

# 1. 创建启动上下文（集中管理所有依赖）
context = StartupContext()

# 2. 构建服务初始化器（传入上下文和服务管理器）
initializer = ServiceInitializer(
    service_manager=context.service_manager,
    context=context,
)

# 3. 根据需求选择初始化模式
initializer.initialize_all_services()      # 完整启动（推荐）
# initializer.initialize_core_services()  # 快速启动，仅加载核心服务

# 4. 记录上下文，后续流程通过 context 访问引擎/服务
service_manager = context.service_manager
service_registry = context.service_registry

# 5. 关闭流程（可选：在程序退出时调用）
initializer.shutdown_services()
```

### 使用服务

```python
# 推荐：通过ServiceRegistry解析，遵循依赖注入模式
data_center = service_registry.resolve_optional("data_center_service")
trading_gateway = service_registry.resolve_optional("trading_gateway_service")

# 兼容：仍可通过ServiceManager获取（将逐步淘汰）
fallback = service_manager.get_service("data_center_service", silent=True)

# 调用服务方法
if data_center:
    result = data_center.refresh_symbol_list()
    if result["success"]:
        symbols = result["data"]

# ⚠️ 说明：`backend.core.base.get_*` 等全局方法仅用于兼容旧代码，
# 新代码应通过 `StartupContext`/`ServiceRegistry` 获取依赖。
```

### 访问配置

```python
from backend.core.config import get_settings

settings = get_settings()
db_path = settings.database.path
api_port = settings.api.port
```

### 使用数据模型

```python
from backend.core.models import UnifiedMarketData, get_data_model_manager

# 创建统一行情数据
market_data = UnifiedMarketData(
    symbol="000001.SZ",
    datetime=datetime.now(),
    last_price=10.5,
    volume=1000000
)

# 使用数据模型管理器
dm_manager = get_data_model_manager()
dm_manager.update_market_data("000001.SZ", market_data)
```

---

## 📚 更多文档

- **需求文档**：`docs/1.权威需求文档/`
- **底层功能包文档**：`docs/2.底层被调用功能包介绍文档/`
- **功能映射文档**：`docs/3.需求与底层功能映射/`

---

## 📧 联系方式

如有问题或建议，请联系开发团队。

