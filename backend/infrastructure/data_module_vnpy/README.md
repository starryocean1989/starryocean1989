# -*- coding: utf-8 -*-
# data_module_vnpy - 中国A股量化数据管理模块 (AI工具组合文档)

**版本**: v2.0.0 (激进合并版)
**架构**: VNPy + TDX异步接口
**文件数**: 6个核心文件 (20个→6个, 减少70%)
**代码量**: 22,769行

---

## 快速索引

### 核心定位
中国A股数据管理中枢，提供品种管理、数据获取、质量监控、统一查询、实时推送的全链路数据服务。

### 技术特点
- 纯异步架构（tdx_asyncio）
- 多进程+协程并发（最大2000并发）
- 智能负载均衡（木桶理论评分）
- 四层数据融合（内存+磁盘+录制+实时）
- AI Debug友好（相关功能集中在单文件）

---

## 文件结构 (v2.0激进合并版)

```
data_module_vnpy/
├── __init__.py (158行)              # API统一导出
├── data_module.py (2671行)          # 核心引擎+配置+事件+缓存+时间同步
├── data_acquisition.py (6005行)     # 品种管理+数据下载+TDX读取
├── data_management.py (3606行)      # 统一管理+验证器+缓存内存+调优器
├── data_quality.py (4085行)         # 质量管理+IPO缓存+文件监控+健康检查
├── load_balancer.py (6244行)        # 负载均衡+服务器池+资源监控+参数调优
└── requirements.txt                 # Python依赖
```

### 合并映射

| 新文件 | 原文件来源 | 合并数 | 核心类数 |
|--------|-----------|--------|---------|
| data_module.py | core.py + config.py + events.py + cache_manager.py + validation_worker.py + network_time.py | 6→1 | 7个 |
| data_acquisition.py | data_acquisition.py + task_logger.py + symbol_management.py + data_fetcher.py + data_readers.py + base_reader.py + bj_decoder.py + tdx_reader.py + tdx_dynamic_executor.py | 9→1 | 12个 |
| data_management.py | intelligent_adaptive_tuner.py + cache_and_memory.py + validators.py + unified_data_manager.py | 4→1 | 15个 |
| data_quality.py | data_quality.py + storage_manager.py + data_validator.py + data_sensor.py + file_watcher.py + health_checker.py + ipo_cache.py | 7→1 | 8个 |
| load_balancer.py | load_balancer.py + server_pool_manager.py + task_queue_manager.py + resource_monitor.py + execution_model.py + parameter_tuner.py | 6→1 | 15个 |

---

## 核心组件与API

### 1. data_module.py - 核心基础设施

#### ChinaStockEngine (核心引擎)
**职责**: 整个模块的中枢，协调所有功能组件

**核心方法**:
```python
# 生命周期
__init__(main_engine, event_engine)
healthcheck() -> Dict[str, Any]
is_ready() -> bool

# 品种管理
reload_stock_list() -> Dict[str, Any]
get_market_stocks(market_type: str) -> List[Dict]

# 数据下载
download_incremental(start_date: str, intervals: List[str]) -> Dict
download_history(symbols: List[str], intervals: List[str]) -> Dict

# 数据查询
query_data(symbol: str, interval: str, start: str, end: str) -> pd.DataFrame

# 质量管理
trigger_data_quality_scan() -> Dict
get_data_quality_overview() -> Dict

# TDX本地读取
read_tdx_data(symbols: List[str], data_type: str, market: str) -> Dict
```

#### ConfigManager (配置管理)
**职责**: 统一配置管理，路径自动标准化

**核心方法**:
```python
get(key: str, default: Any) -> Any
set(key: str, value: Any) -> bool
get_cache_dir() -> Path                    # 缓存目录
get_data_dir() -> Path                     # 数据目录（Parquet）
get_db_file() -> Path                      # 数据库文件
get_tdx_dir() -> Path                      # 通达信目录
get_tdx_reader_root_dir() -> Path          # TDX数据目录
get_config_file() -> Path                  # 配置文件路径
```

#### Event System (事件系统)
**事件常量**:
```python
APP_NAME = "ChinaStockData"
EVENT_CHINASTOCK_LOG                       # 日志事件
EVENT_CHINASTOCK_VALIDATION                # 验证事件
EVENT_CHINASTOCK_DOWNLOAD                  # 下载事件
EVENT_DATA_QUALITY_UPDATE                  # 质量更新事件
EVENT_SYMBOL_CACHE_LOADED                  # 品种缓存加载
EVENT_IPO_CACHE_UPDATED                    # IPO缓存更新
EVENT_VALIDATION_COMPLETED                 # 验证完成
EVENT_DATA_METRICS_UPDATED                 # 数据指标更新
```

**事件发布器**:
```python
EventPublisher(event_engine)               # 通用事件发布
ValidationEventPublisher(event_engine)     # 验证事件发布
DownloadEventPublisher(event_engine)       # 下载事件发布
QualityEventPublisher(event_engine)        # 质量事件发布
```

#### DailyCacheManager (缓存管理)
**职责**: 统一缓存管理，日期失效机制

**核心方法**:
```python
@staticmethod
save_with_date(data: Any, cache_file: Path) -> bool
load_with_validation(cache_file: Path) -> Tuple[Any, str, bool]
clear_cache(cache_file: Path) -> bool
get_cache_date(cache_file: Path) -> Optional[str]
```

#### NetworkTimeSync (网络时间同步)
**职责**: 从NTP服务器同步真实时间

**核心方法**:
```python
@classmethod
get_instance() -> NetworkTimeSync
sync_time() -> bool
get_network_time() -> datetime
get_network_date() -> date
get_time_offset() -> Optional[float]
get_stats() -> Dict
```

#### DataValidationWorker (Qt工作线程)
**职责**: 后台数据验证，避免阻塞UI

**信号**:
```python
progress_updated = Signal(str, int)        # 进度更新(消息, 百分比)
validation_completed = Signal(dict)        # 验证完成(结果)
error_occurred = Signal(str)               # 错误发生(消息)
```

---

### 2. data_acquisition.py - 数据获取与读取

#### SymbolLoader (品种管理)
**职责**: 品种列表获取、分类、缓存

**核心方法**:
```python
__init__(event_engine=None)
load_from_api() -> Dict[str, Any]          # 从API加载
load_from_cache() -> Optional[Dict]        # 从缓存加载
reload_and_classify() -> Dict              # 重新加载并分类
get_all_classified() -> Dict               # 获取所有分类
extract_all_codes() -> List[str]           # 提取所有代码
extract_codes_by_market(markets: List[str]) -> List[str]  # 按市场提取
update_ipo_dates_and_remove_unlisted(ipo_data: Dict, unlisted: List[str]) -> Tuple[bool, Dict]
```

**品种分类**:
- 上证A股: market=1, code以60/68开头
- 深证A股: market=0, code以00/30开头
- 北证A股: market=2, code以8/4/920开头
- T+0基金: code以511/159/512/513/515/516/518开头
- 可转债: code以11/12开头

#### MultiProcessStockFetcher (多进程下载)
**职责**: 高性能多进程+异步K线下载

**核心方法**:
```python
__init__(event_engine=None)
download_incremental_kline(symbols: List[str], start_date: str, intervals: List[str], use_adaptive: bool, use_two_phase: bool) -> Dict
download_history_kline(symbols: List[str], intervals: List[str], use_adaptive: bool) -> Dict
download_ipo_dates_multiprocess(symbols_with_markets: List[Tuple], progress_callback, use_adaptive: bool, ipo_cache) -> Dict
stop_download() -> None
pause_download() -> None
resume_download() -> None
get_download_progress() -> Dict
```

**性能参数**:
- 进程数: 4-32 (根据CPU核心数)
- 协程数/进程: 20-80
- 总并发: 最大2000连接
- 两段式下载: 乱序池(650+服务器) → 热备池(30个最快)

#### download_ipo_dates (IPO日期批量下载)
**职责**: IPO日期批量下载和缓存

**函数签名**:
```python
download_ipo_dates(symbols: List[str], progress_callback=None, use_multiprocess: bool = True, ipo_cache=None) -> Dict[str, Any]
```

**返回结构**:
```python
{
    "success": bool,
    "total": int,              # 总品种数
    "cached": int,             # 缓存命中数
    "downloaded": int,         # 新下载数
    "succeeded": int,          # 成功数
    "failed": int,             # 失败数
    "data": {symbol: ipo_date},  # IPO日期数据
    "unlisted": [symbol, ...]    # 未上市品种
}
```

#### TdxBinaryReader (TDX文件读取)
**职责**: 读取通达信本地二进制K线数据

**核心方法**:
```python
__init__(tdx_dir: Path)
process_batch(symbols: List[str], data_type: str, market: str, progress_callback=None) -> Dict
read_single(symbol: str, data_type: str, market: str) -> Optional[pd.DataFrame]
```

**支持的数据类型**:
- day: 日线 (vipdoc/{market}/lday/{symbol}.day)
- 5min: 5分钟 (vipdoc/{market}/fzline/{symbol}.lc5)
- 1min: 1分钟 (vipdoc/{market}/minline/{symbol}.lc1)

**市场代码**: sh(上证), sz(深证), bj(北证)

#### TdxDynamicExecutor (动态执行器)
**职责**: 多进程+协程池并发读取TDX文件

**核心方法**:
```python
__init__(tdx_dir: Path)
execute(tasks: List[TdxLocalReadTask], progress_callback=None, max_workers: int = 4, coroutines_per_worker: int = 20) -> List[ExecutionResult]
```

#### BjStockDecoder (北证解码器)
**职责**: 北交所数据格式转换

**核心方法**:
```python
@staticmethod
decode_bj_stock(df: pd.DataFrame) -> pd.DataFrame
```

#### TaskDetailLogger (任务日志)
**职责**: K线下载任务详细日志记录

**核心方法**:
```python
__init__(worker_id: int, log_dir: str)
log_download_result(symbol: str, interval: str, result: bool, error: str, server: str, elapsed: float) -> None
finalize() -> Dict[str, Any]
```

---

### 3. data_management.py - 数据管理中枢

#### UnifiedDataManager (统一数据管理)
**职责**: 四层数据融合（内存+磁盘+录制+实时）

**核心方法**:
```python
__init__(china_stock_engine)
query_unified(symbol: str, interval: str, start_date: str, end_date: str, check_gaps: bool) -> Optional[pd.DataFrame]
subscribe(module: str, symbols: List[str]) -> bool
unsubscribe(module: str) -> bool
get_subscriptions() -> Dict
preload_symbols(symbols: List[str], intervals: List[str]) -> bool
```

**查询优先级**: 预加载缓存 → 历史Parquet → 录制数据 → 实时推送

#### PreloadService (预加载服务)
**职责**: 常用品种智能预加载

**核心方法**:
```python
__init__(storage_manager, max_cache_size: int = 64)
preload(symbols: List[str], intervals: List[str]) -> Dict
get_from_cache(symbol: str, interval: str) -> Optional[pd.DataFrame]
clear_cache() -> None
get_stats() -> Dict
```

#### TdxDataSource (TDX数据源)
**职责**: 轮询转推送，符合VNPy Gateway标准

**核心方法**:
```python
__init__(gateway_name: str)
connect(setting: Dict) -> bool
subscribe(req: SubscribeRequest) -> None
unsubscribe(symbol: str) -> None
close() -> None
```

**配置参数**:
```python
{
    "轮询间隔（秒）": 3,
    "品种列表": "000001,600000"
}
```

#### VirtualDataSource (虚拟数据源)
**职责**: 历史数据回放，用于回测

**核心方法**:
```python
__init__(gateway_name: str)
connect(setting: Dict) -> bool
start_replay() -> bool
pause_replay() -> None
resume_replay() -> None
set_speed(speed: float) -> None
```

**配置参数**:
```python
{
    "起始时间": "2024-01-01 09:30:00",
    "回放速度": 2.0,
    "品种列表": "000001,600000"
}
```

#### StatelessValidator (无状态验证器)
**职责**: 纯函数数据验证，支持多进程

**核心方法**:
```python
@staticmethod
validate_symbol(symbol: str, interval: str, df: pd.DataFrame, context: ValidationContext) -> StatelessValidationResult
validate_format(df: pd.DataFrame) -> List[Dict]
validate_logic(df: pd.DataFrame) -> List[Dict]
validate_completeness(df: pd.DataFrame, symbol: str, date_range: Tuple, context: ValidationContext) -> Tuple[List[date], List[str]]
validate_freshness(df: pd.DataFrame, date_range: Tuple, context: ValidationContext) -> List[str]
calculate_freshness_score(date_range: Tuple, context: ValidationContext) -> float
calculate_completeness_score(df: pd.DataFrame, missing_dates: List[date], date_range: Tuple, context: ValidationContext) -> float
```

#### ValidationContext (验证上下文)
**职责**: 验证所需的共享数据

**属性**:
```python
ipo_dates: Dict[str, date]              # IPO日期字典
trading_days: Set[date]                 # 交易日集合
latest_trading_day: date                # 最新交易日
base_date: date                         # 基准日期
min_records_threshold: int = 100        # 最小记录数
freshness_days_warning: int = 7         # 滞后警告阈值
freshness_days_error: int = 30          # 滞后错误阈值
```

#### GPUValidator (GPU加速验证)
**职责**: GPU加速数据验证（可选）

**核心方法**:
```python
@staticmethod
is_gpu_available() -> bool
validate_with_gpu(df: pd.DataFrame) -> Dict
```

#### IncrementalScanManager (增量扫描)
**职责**: 智能增量扫描，跳过已验证文件

**核心方法**:
```python
__init__(scan_record_file: Path)
should_scan(file_path: Path) -> bool
mark_scanned(file_path: Path, checksum: str) -> None
clear_records() -> None
```

#### LRUCacheManager (LRU缓存)
**职责**: LRU缓存管理，支持TTL

**核心方法**:
```python
__init__(capacity: int = 1000, ttl: Optional[float] = None, on_evict: Optional[Callable] = None)
get(key: K, default: Optional[V] = None) -> Optional[V]
set(key: K, value: V) -> None
exists(key: K) -> bool
delete(key: K) -> bool
clear() -> None
get_stats() -> CacheStats
```

#### SharedMemoryManager (共享内存)
**职责**: 多进程数据共享

**核心方法**:
```python
__init__()
start() -> None
stop() -> None
prepare_shared_data(ipo_dates: Dict, trading_days: Set, latest_trading_day: date, base_date: date) -> None
get_validation_context() -> ValidationContext
get_shared_data_info() -> Dict
```

#### IntelligentAdaptiveTuner (智能调优)
**职责**: 多维压力评分，动态并发调节

**核心方法**:
```python
__init__(base_async_workers: int, base_thread_workers: int, base_process_workers: int, weights: Dict, ema_alpha: float, adjust_step_max: float, deadband: float, cooldown_sec: float)
suggest_scale(sys_data: Dict[str, Any]) -> Tuple[float, str]
```

**压力评分维度**:
- CPU: 40% (cpu_percent, context_switches, interrupts)
- 内存: 25% (mem_percent, swap_percent)
- 存储: 25% (disk_usage, io_wait)
- 网络: 15% (bandwidth_usage, packet_loss)

---

### 4. data_quality.py - 数据质量管理

#### DataSensor (数据质量感知)
**职责**: 全方位数据质量监控

**核心方法**:
```python
__init__(event_engine)
trigger_scan_with_symbols(symbol_loader, force_refresh: bool) -> QualityOverview
get_quality_overview() -> Optional[QualityOverview]
validate_symbol(symbol: str, interval: str) -> Optional[StatelessValidationResult]
start_file_watcher() -> None
stop_file_watcher() -> None
```

**扫描模式**:
- 混合异步: 协程+线程+进程，最大2000并发
- 自适应: 根据文件大小选择处理方式
- 增量推送: 500ms最小间隔

#### DataValidator (数据验证器)
**职责**: 数据校验和质量评分

**核心方法**:
```python
__init__()
validate_single(symbol: str, interval: str, df: pd.DataFrame) -> ValidationSummary
validate_batch(tasks: List[Tuple]) -> List[ValidationSummary]
```

#### StorageManager (存储管理)
**职责**: Parquet文件读写和管理

**核心方法**:
```python
__init__()
save_data(symbol: str, interval: str, df: pd.DataFrame) -> bool
load_data(symbol: str, interval: str, start_date: Optional[str], end_date: Optional[str]) -> Optional[pd.DataFrame]
delete_data(symbol: str, interval: str) -> bool
get_data_path(symbol: str, interval: str) -> Path
list_symbols(interval: str) -> List[str]
scan_and_repair_corrupted_files(progress_callback=None) -> Dict
```

**目录结构**:
```
data/kline/{interval}/{symbol}.parquet
例如: data/kline/1d/000001.parquet
```

#### DataFileWatcher (文件监控)
**职责**: 实时监控数据变化

**核心方法**:
```python
__init__(watch_dir: Path, event_engine, callback: Callable)
start() -> None
stop() -> None
```

#### HealthChecker (健康检查)
**职责**: 系统健康状态检查

**核心方法**:
```python
@staticmethod
check_system_health() -> Dict[str, Any]
check_tdx_connection() -> bool
check_storage_health() -> Dict
check_cache_validity() -> Dict
```

#### IPODateCache (IPO日期缓存)
**职责**: IPO日期两级缓存（内存+文件）

**核心方法**:
```python
__init__(cache_file: Path = None)
get(symbol: str) -> Tuple[Optional[date], bool]
set(symbol: str, ipo_date: Optional[date]) -> None
batch_save() -> None
load_from_file() -> None
clear() -> None
get_stats() -> Dict
```

**缓存性能**: 95%+命中率

#### QualityOverview (质量概览)
**数据结构**:
```python
@dataclass
class QualityOverview:
    quality_score: float          # 总体质量分 (0-100)
    total_symbols: int            # 总品种数
    missing_symbols: int          # 品种缺失数
    outdated_symbols: int         # 数据过时数
    avg_gap_days: float          # 平均滞后天数
    max_gap_days: int            # 最大滞后天数
    error_count: int             # 错误数量
    warning_count: int           # 警告数量
    scan_time: datetime          # 扫描时间
```

---

### 5. load_balancer.py - 智能负载均衡

#### LoadBalancer (负载均衡器)
**职责**: 根据系统资源动态调整并发配置

**核心方法**:
```python
@classmethod
get_instance(cls, event_engine=None) -> LoadBalancer
get_optimal_config(task: BaseTask) -> Dict[str, Any]
get_current_pressure() -> float
force_refresh_pressure() -> float
```

**评分模型** (木桶理论):
```python
总分 = min(CPU分40, 内存分30, 磁盘分15, 网络分15) × 评分因子

压力级别:
0-30分: 紧急 (0.3x并发)
31-50分: 高压 (0.5x-0.7x并发)
51-70分: 中等 (0.8x-1.0x并发)
71-100分: 正常 (1.0x-1.6x并发)
```

#### ServerPoolManager (服务器池)
**职责**: TDX服务器测速、排序、热备管理

**核心方法**:
```python
@classmethod
get_instance(cls) -> ServerPoolManager
start() -> bool
get_best_server() -> Optional[Tuple[str, int]]
get_servers(count: int = 10, force_ipv4: bool = False) -> List[Tuple[str, int]]
get_servers_shuffled() -> List[Tuple[str, int]]
is_cache_valid() -> bool
get_stats() -> Dict
```

**测速性能**:
- 输入: ~800个服务器
- 进程: 3个
- 协程: 150个 (50×3)
- 耗时: 6-12秒
- 输出: 60+个可用服务器（按速度排序）

#### TaskQueueManager (任务队列)
**职责**: 任务队列管理和调度

**核心方法**:
```python
__init__(max_queue_size: int = 10000)
add_task(task: BaseTask) -> bool
get_task() -> Optional[BaseTask]
get_queue_stats() -> Dict
clear() -> None
```

#### ResourceMonitor (资源监控)
**职责**: 系统资源实时监控

**核心方法**:
```python
@staticmethod
get_system_stats() -> Dict[str, Any]
get_cpu_stats() -> Dict
get_memory_stats() -> Dict
get_disk_stats() -> Dict
get_network_stats() -> Dict
```

**监控指标**:
```python
{
    "cpu_percent": float,           # CPU使用率%
    "memory_percent": float,        # 内存使用率%
    "disk_usage_percent": float,    # 磁盘使用率%
    "network_bandwidth_mbps": float,# 网络带宽Mbps
    "context_switches_per_sec": int,# 上下文切换/秒
    "interrupts_per_sec": int,      # 中断/秒
    "swap_percent": float,          # 交换区使用率%
    "io_wait_percent": float,       # IO等待%
    "packet_loss_rate": float       # 丢包率
}
```

#### ExecutionModel (执行模型)
**职责**: 多进程/流式执行模型

**核心方法**:
```python
@staticmethod
execute_multiprocess(tasks: List, worker_func: Callable, num_workers: int) -> List
execute_streaming(tasks: List, worker_func: Callable, batch_size: int) -> Iterator
```

#### ParameterTuner (参数调优)
**职责**: 自动参数优化

**核心方法**:
```python
@staticmethod
tune_download_params(pressure_score: float, task_count: int) -> Dict
tune_scan_params(pressure_score: float, file_count: int) -> Dict
tune_tdx_read_params(pressure_score: float, symbol_count: int) -> Dict
```

#### ApplicationLevelLimiter (应用级限制器)
**职责**: 磁盘I/O硬限制保护

**配置参数**:
```python
ApplicationLevelLimiter(
    # CPU/内存限制
    small_task_cpu_limit: float = 30.0,
    large_task_cpu_limit: float = 80.0,

    # 磁盘限制（类型化）
    disk_hdd_busy_limit: float = 75.0,      # HDD使用率限制
    disk_ssd_busy_limit: float = 85.0,      # SSD使用率限制
    disk_nvme_busy_limit: float = 90.0,     # NVMe使用率限制

    # 延迟熔断
    disk_hdd_latency_critical: float = 50.0,   # HDD延迟>50ms拒绝
    disk_ssd_latency_critical: float = 20.0,   # SSD延迟>20ms拒绝
    disk_nvme_latency_critical: float = 10.0   # NVMe延迟>10ms拒绝
)
```

**保护策略**:
- 物理磁盘监控（而非逻辑分区）
- 自动检测磁盘类型（NVMe/SSD/HDD）
- 标记系统盘（包含C:的物理磁盘）
- 超限拒绝新任务

#### 标准任务类型
```python
# 网络任务 (4个)
ServerPoolTestTask          # 服务器池测速
KlineDownloadTask           # K线批量下载
IPODownloadTask             # IPO日期下载
RealtimePollingTask         # 实时行情轮询

# 本地处理任务 (4个)
DataQualityScanTask         # 数据质量扫描
TdxBatchReadTask            # TDX文件批量读取
VirtualReplayTask           # 虚拟推送回放
PreloadTask                 # 数据预加载
```

---

## 功能特性速查

### 品种管理
- 支持类型: 上证A股, 深证A股, 北证A股, T+0基金, 可转债
- 总数: ~5200个品种
- 缓存: 日期失效机制（次日0时）
- IPO集成: 每个品种包含上市日期
- 增量更新: 自动检测新增/退市

### 数据下载
- 架构: 多进程(4-32) + 协程(20-80/进程) = 最大2000并发
- 模式: 增量下载 / 全量下载
- 周期: 日线(1d) / 5分钟(5m) / 1分钟(1m)
- 优化: 两段式下载（乱序池 → 热备池）
- 性能: 5000品种×3周期 ≈ 1.5-3分钟

### 数据质量
- 检查维度: 品种缺失 / 历史缺失 / 逻辑错误 / 格式错误
- 扫描模式: 混合异步（协程+线程+进程）
- 最大并发: 2000个文件同时验证
- 增量推送: 500ms最小间隔
- 文件监控: 实时检测变化

### 统一数据管理
- 数据融合: 预加载缓存 → 历史Parquet → 录制数据 → 实时推送
- 预加载: LRU缓存，最大64品种
- 订阅管理: 多模块订阅，自动去重
- 自动补全: 检测缺失自动下载

### 实时推送
- TDX数据源: 轮询转推送，符合VNPy Gateway标准
- 虚拟数据源: 历史回放，支持倍速/暂停/恢复
- 推送事件: EVENT_TICK / EVENT_BAR

### 智能负载均衡
- 评分模型: 木桶理论（CPU40% + 内存30% + 磁盘15% + 网络15%）
- 动态调整: 0.3x - 1.6x并发缩放
- 缓存机制: 3秒TTL
- 磁盘保护: 类型化阈值（HDD 75% / SSD 85% / NVMe 90%）
- IO熔断: 延迟超限拒绝任务

---

## 调用链路

### 初始化链路
```
backend/core/base.py (ServiceInitializer)
    ↓ _initialize_data_services()
ChinaStockEngine(main_engine, event_engine)
    ↓ __init__
初始化子组件: SymbolLoader, MultiProcessStockFetcher, StorageManager, DataValidator, DataSensor, UnifiedDataManager
    ↓ 注册到全局
set_china_stock_engine(engine)
```

### 品种加载链路
```
UI: data_center_view.py
    ↓ 用户点击"重新加载品种列表"
DataCenterService.reload_symbol_list()
    ↓ 调用引擎
ChinaStockEngine.reload_stock_list()
    ↓ 委托
SymbolLoader.reload_and_classify()
    ↓ 调用TDX API
AsyncTdxHq_API.get_security_list()
    ↓ 解析和分类
分类逻辑 + TdxConfigFileParser
    ↓ 缓存
DailyCacheManager.save_with_date()
    ↓ 推送事件
EventEngine.put(EVENT_SYMBOL_CACHE_LOADED)
```

### 数据下载链路
```
UI: data_center_view.py
    ↓ 用户点击"增量下载"
DataCenterService.start_incremental_download()
    ↓ 调用引擎
ChinaStockEngine.download_incremental(start_date, intervals)
    ↓ 委托
MultiProcessStockFetcher.download_incremental_kline()
    ↓ 获取配置
LoadBalancer.get_optimal_config(KlineDownloadTask)
    ↓ 多进程+协程下载
多进程(16) × 协程(40) = 640并发
    ↓ TDX API
AsyncTdxHq_API.get_security_bars()
    ↓ 保存数据
StorageManager.save_data(symbol, interval, df)
    ↓ 推送进度
EventEngine.put(EVENT_CHINASTOCK_DOWNLOAD)
```

### 数据查询链路
```
UI: market_board_view.py
    ↓ 用户请求K线图
ChinaStockEngine.query_data(symbol, interval, start, end)
    ↓ 委托
UnifiedDataManager.query_unified(symbol, interval, start, end)
    ↓ 四层查询
1. PreloadService.get_from_cache() → 命中返回
2. StorageManager.load_data() → 命中返回
3. 录制数据（如启用）→ 命中返回
4. 实时推送（如已订阅）→ 推送
    ↓ 缺失检测
check_gaps=True → 触发自动下载
```

### 质量扫描链路
```
UI: data_center_view.py
    ↓ 用户点击"数据质量扫描"
DataCenterService.trigger_data_quality_scan()
    ↓ 调用引擎
ChinaStockEngine.trigger_data_quality_scan()
    ↓ 委托
DataSensor.trigger_scan_with_symbols(symbol_loader, force_refresh)
    ↓ 获取配置
LoadBalancer.get_optimal_config(DataQualityScanTask)
    ↓ 混合异步扫描
协程(500) + 线程(50) + 进程(16) = 最大2000并发
    ↓ 验证
StatelessValidator.validate_symbol(symbol, interval, df, context)
    ↓ 推送结果
EventEngine.put(EVENT_DATA_QUALITY_UPDATE)
```

---

## 性能指标

### 启动性能
- 冷启动: 8-12秒（含服务器池测速）
- 热启动: 2-3秒（缓存命中）
- 智能缓存验证: 7步流程，增量模式

### 下载性能
| 品种数×周期 | 并发配置 | 耗时 | 性能提升 |
|-----------|---------|------|---------|
| 5000×3 (15000任务) | 单线程 | ~6小时 | 基准 |
| 5000×3 | 50线程 | ~40分钟 | 9倍 |
| 5000×3 | 16进程×40协程 | ~1.5分钟 | 240倍 |

### 质量扫描性能
| 文件数 | 扫描模式 | 耗时 |
|-------|---------|------|
| 1000 | 单线程 | ~30秒 |
| 1000 | 混合异步(2000并发) | ~3秒 |
| 5000 | 混合异步(2000并发) | ~15秒 |

### TDX本地读取性能
| 品种数 | 旧架构(单线程) | 新架构(4进程×20协程) | 提升 |
|-------|---------------|---------------------|------|
| 1000 | ~30秒 | ~8秒 | 3.7倍 |
| 5000 | ~150秒 | ~40秒 | 3.7倍 |

---

## 配置说明

### 配置文件位置
```python
config/terminal_config.json
```

### 主要配置项
```python
{
    "chinastock": {
        "cache_dir": "data/cache",                    # 缓存目录
        "data_dir": "data/kline",                     # 数据目录
        "tdx_dir": "C:/通达信",                       # 通达信安装目录
        "tdx_reader_root_dir": "C:/通达信/vipdoc",   # TDX数据目录
        "server_pool_size": 30,                       # 热备服务器数量
        "polling_gateway_enabled": false,             # 轮询网关启用
        "polling_interval": 3,                        # 轮询间隔(秒)
        "preload_symbols": ["000001", "600000"],     # 预加载品种
        "max_preload_cache": 64                       # 最大预加载数
    }
}
```

### 代码配置
```python
from backend.infrastructure.data_module_vnpy.data_module import config_manager

# 获取配置
cache_dir = config_manager.get_cache_dir()
tdx_dir = config_manager.get_tdx_dir()

# 设置配置
config_manager.set("chinastock.server_pool_size", 50)
```

---

## 依赖项

### Python依赖
```
vnpy>=4.1.0                    # VNPy量化框架
pandas>=1.5.0                  # 数据处理
pyarrow>=10.0.0                # Parquet文件
watchdog>=3.0.0                # 文件监控
psutil>=5.9.0                  # 系统资源监控
ntplib>=0.4.0                  # NTP时间同步
asyncio (标准库)                # 异步IO
multiprocessing (标准库)        # 多进程
threading (标准库)              # 多线程
```

### 内部依赖
```
backend/infrastructure/tdx_asyncio     # 纯异步TDX接口
backend/infrastructure/system_vnpy     # 系统监控
backend/core/base                      # 核心基础
```

---

## 维护指南

### 日志系统
```python
# 专用logger
logger_engine = logging.getLogger("backend.data_module.engine")
logger_download = logging.getLogger("backend.data_module.download")
logger_alert = logging.getLogger("backend.data_module.alert")
logger_network_time = logging.getLogger("backend.data_module.network_time")
```

### 缓存管理
```python
# 清理品种列表缓存
config_manager.get_cache_dir() / "stock_list_classified.json"

# 清理服务器池缓存
config_manager.get_cache_dir() / "server_pool_cache.json"

# 清理交易日历缓存
config_manager.get_cache_dir() / "trading_calendar.json"

# 清理IPO日期缓存
config_manager.get_cache_dir() / "ipo_dates_cache.json"
```

### 数据修复
```python
# 扫描并修复损坏的Parquet文件
storage_manager = StorageManager()
result = storage_manager.scan_and_repair_corrupted_files(progress_callback)

# 重新下载单个品种
engine.download_history(["000001"], ["1d"])

# 清除质量扫描记录
sensor = DataSensor(event_engine)
sensor.incremental_scan_manager.clear_records()
```

---

## 常见问题

### Q1: 服务器池测速失败？
A: 检查网络连接，确保能访问TDX服务器。可通过`server_pool_manager.get_stats()`查看测速结果。

### Q2: 下载速度慢？
A: 检查LoadBalancer配置，确认系统资源充足。可通过`load_balancer.get_current_pressure()`查看压力分数。

### Q3: 数据质量分数低？
A: 运行增量下载补全缺失数据。可通过`engine.get_data_quality_overview()`查看详细问题。

### Q4: 预加载不生效？
A: 检查配置文件中`preload_symbols`和`max_preload_cache`设置。

### Q5: 磁盘I/O超限？
A: LoadBalancer会自动保护，拒绝新任务。检查磁盘使用率和IO延迟。

---

## 版本历史

### v2.0.0 (激进合并版) - 2025-10-29
- 激进合并: 20个文件 → 6个核心文件（减少70%）
- AI Debug友好: 相关功能集中在单文件
- 性能优化: IPO下载流程简化，复用实例
- 向后兼容: 100% API兼容

### v1.0.0 (初始版本)
- 基础功能实现
- 多文件架构

---

## 许可证

MIT License

---

## 联系方式

项目地址: backend/infrastructure/data_module_vnpy/
文档版本: v2.0.0
最后更新: 2025-10-29
