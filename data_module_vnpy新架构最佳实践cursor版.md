# -*- coding: utf-8 -*-
# data_module_vnpy 新架构最佳实践设计文档 (Cursor版)

**版本**: v3.0 (彻底重构版)
**创建日期**: 2025-01-02
**文档目标**: 提供高粒度、详细的新架构设计，覆盖所有技术细节和实施方案

> **📖 文档分工**：
> - **本文档**：专注于架构设计、技术选型、性能目标、组件设计
> - **业务细节文档**：专注于业务流程、规则细节、实现逻辑、算法描述
> 
> 两文档遵循单一事实原则，互相引用但不重复内容。

---

## 📋 目录

- [一、架构设计总览](#一架构设计总览)
- [二、核心文件设计](#二核心文件设计)
- [三、native_iocp深度集成方案](#三native_iocp深度集成方案)
- [四、native_ipc深度集成方案](#四native_ipc深度集成方案)
- [五、智能负载机制优化](#五智能负载机制优化)
- [六、统一数据管理器优化](#六统一数据管理器优化)
- [七、事件驱动架构优化](#七事件驱动架构优化)
- [八、文件组织优化](#八文件组织优化)
- [九、向后兼容性](#九向后兼容性)
- [十、性能目标与指标](#十性能目标与指标)
- [十一、实施计划](#十一实施计划)
- [十二、风险评估与应对](#十二风险评估与应对)
- [十三、后续优化方向](#十三后续优化方向)

---

## 一、架构设计总览

### 1.1 设计目标与约束

#### 1.1.1 技术栈约束

新架构必须严格符合以下技术栈要求：

1. **操作系统**: Windows 平台专属
   - 充分利用Windows IOCP机制（native_iocp）
   - 充分利用Windows Named Pipe机制（native_ipc）
   - 优化Windows文件系统特性

2. **编程语言**: Python 3.10+
   - 全面采用asyncio异步编程
   - 支持类型提示（Type Hints）
   - 兼容现有Python生态

3. **UI框架**: PySide6 (Qt6)
   - 事件驱动集成（EventEngine）
   - 异步UI更新（qasync）
   - 线程安全保证

4. **量化框架**: VnPy 4.x
   - 符合VnPy Gateway标准
   - 事件驱动架构（EventEngine）
   - 数据模型兼容（TickData、BarData等）

5. **日志系统**: 统一日志系统（LoggingHub）
   - 四层路由（场景→模块→阶段→全局）
   - AI日志支持
   - 进度节流

6. **底层机制**:
   - **智能负载机制**: 木桶理论评分，动态并发调整
   - **统一数据管理器**: 四层数据融合（内存+磁盘+录制+实时）
   - **native_iocp机制**: 真异步文件I/O（已集成，需深化）
   - **native_ipc机制**: 真异步跨进程通信（替代ZMQ，不影响UI调用）

#### 1.1.2 功能完整性约束

新架构必须保持当前data_module_vnpy的所有功能：

1. **品种管理**
   - 品种列表加载、分类、缓存
   - 品种分类（上证/深证/北证/T+0基金/可转债）
   - IPO日期集成
   - 自动去除未上市品种

2. **数据下载**
   - 增量下载、全量下载
   - 多进程+协程并发（最大2000并发）
   - 两段式下载策略（IPv4池→IPv6池，IPv6不可用时回退到IPv4池）
   - 支持暂停/恢复/取消

3. **数据读取**
   - Parquet格式读取（异步化）
   - TDX本地文件读取（异步化）
   - 北证解码器

4. **数据质量管理**
   - 数据质量扫描（混合异步）
   - 数据验证（无状态、多进程）
   - 文件监控（实时变化检测）
   - 健康检查

5. **统一数据输出**
   - 四层数据融合查询
   - 预加载缓存
   - 自动补全缺失数据
   - 实时推送（TDX数据源、虚拟数据源）

6. **实时数据网关**
   - TDX轮询网关（符合VnPy Gateway标准）
   - 虚拟推送网关（历史回放）
   - 本地数据感知

#### 1.1.3 架构质量约束

1. **文件组织偏好**
   - 少文件数量：当前7个文件 → 6个核心文件
   - 大文件规模：4000-8000行/文件
   - Debug上下文友好：相关功能集中在单文件

2. **代码质量要求**
   - 清晰的Part分区标记
   - 完整的类型提示
   - 详细的docstring
   - 向后兼容100%API

### 1.2 核心架构原则

#### 1.2.1 事件驱动架构

**原则描述**：所有组件通过vnpy EventEngine进行松耦合通信。

**实现要点**：
- 所有异步操作完成后发布事件
- 事件分类：下载事件、验证事件、质量事件、订阅事件
- 事件数据包含完整的上下文信息
- 支持跨进程事件分发（通过native_ipc）

**架构图**：
```
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│ DataSensor  │───Publish──→│ EventEngine │←──Subscribe──│ UnifiedData │
└─────────────┘              └─────────────┘              └─────────────┘
      │                            │                            │
      │                            │                            │
┌─────────────┐      ┌─────────────┐      ┌─────────────┐
│ MultiProcess│───Publish──→│ EventEngine │←──Subscribe──│ UI Layer    │
│  Fetcher    │              └─────────────┘              └─────────────┘
└─────────────┘
```

#### 1.2.2 异步优先原则

**原则描述**：全面使用asyncio，关键路径使用native_iocp/native_ipc。

**实现要点**：
- 所有I/O操作使用async/await
- 文件读写使用native_iocp（真异步，无线程池）
- 跨进程通信使用native_ipc（真异步，无线程池）
- CPU密集型操作仍使用多进程+协程

**异步化层次**：
```
Level 1: 同步I/O（旧代码，逐步迁移）
Level 2: asyncio + 线程池（过渡方案）
Level 3: asyncio + native_iocp（目标方案）
Level 4: asyncio + native_ipc（跨进程通信）
```

#### 1.2.3 智能负载均衡

**原则描述**：基于木桶理论的动态并发调整。

**实现要点**：
- 实时监控系统资源（CPU占用、内存占用、磁盘IO）
- **木桶理论**：只关注最短的那块板，系统性能 = min(CPU使用率, 内存使用率, 磁盘IO使用率)
  - **关键**：木桶理论不是加权评分，而是只看最短的板（min操作）
  - **监控指标**：CPU占用、内存占用、磁盘IO（通过协程任务队列和任务延迟观察）
- 动态调整并发数（0.3x - 1.6x缩放）
- **防抖机制**：智能防抖，基础调整间隔1秒，特定模式3秒

**负载均衡流程图**：
```
任务提交
    ↓
LoadBalancer.get_optimal_config()
    ↓
获取系统资源指标（ResourceMonitor）
    ↓
计算压力评分（木桶理论）
    ↓
计算最优配置（DynamicConfigCalculator）
    ↓
返回并发配置（进程数、协程数）
    ↓
任务执行（MultiProcessStockFetcher）
```

#### 1.2.4 统一数据管理

**原则描述**：四层数据融合查询，自动补全缺失。

**实现要点**：
- 查询优先级：预加载缓存 → 历史Parquet → 录制数据 → 实时推送
- 自动检测缺失数据并触发下载
- 跨进程缓存同步（使用native_ipc）
- 智能预加载常用品种

**四层数据融合架构**：
```
查询请求
    ↓
Layer 1: PreloadService（内存LRU缓存）
    ├─ 命中 → 返回
    └─ 未命中 ↓
Layer 2: StorageManager（Parquet磁盘文件）
    ├─ 命中 → 返回 + 更新预加载缓存
    └─ 未命中 ↓
Layer 3: 录制数据（如启用录制）
    ├─ 命中 → 返回
    └─ 未命中 ↓
Layer 4: 实时推送（如已订阅）
    ├─ 有数据 → 推送 + 返回
    └─ 无数据 ↓
缺失检测 → 自动触发下载
```

#### 1.2.5 进程隔离原则

**原则描述**：关键组件支持独立进程，通过native_ipc通信。

**实现要点**：
- 监控进程独立运行（替代当前ZMQ方案）
- 多进程下载的进度同步（使用native_ipc队列）
- 数据订阅的跨进程同步
- 事件分发的跨进程支持

**进程架构图**：
```
┌─────────────────┐
│   主进程         │
│  (Main Process) │
│                 │
│ - ChinaStock    │
│ - UI Services   │
│ - EventEngine   │
└────────┬────────┘
         │ native_ipc
         │ (AsyncIPCPipe)
         ↓
┌─────────────────┐
│   监控进程       │
│ (Monitor Process)│
│                 │
│ - ResourceMonitor│
│ - SystemMonitor │
│ - AlertEngine   │
└─────────────────┘
```

#### 1.2.6 AI Debug友好

**原则描述**：相关功能集中在单文件，清晰分区。

**实现要点**：
- 按业务领域组织文件（而非技术层次）
- 每个文件使用Part分区标记
- 相关类和函数放在同一Part
- 避免过多的跨文件跳转

**文件分区示例**：
```python
# ==============================================================================
# Part 1: 核心引擎
# ==============================================================================
class ChinaStockEngine:
    ...

# ==============================================================================
# Part 2: 配置管理
# ==============================================================================
class ConfigManager:
    ...
```

### 1.3 新文件组织结构

#### 1.3.1 文件结构对比

**当前架构（v2.1）**：
```
data_module_vnpy/
├── __init__.py (158行)
├── data_module.py (2671行)          # 核心引擎+配置+事件+缓存+时间同步
├── data_acquisition.py (6005行)     # 品种管理+数据下载+TDX读取
├── data_management.py (3606行)      # 统一管理+验证器+缓存内存+调优器
├── data_quality.py (5730行)         # 质量管理+IPO缓存+文件监控+健康检查
├── load_balancer.py (6244行)        # 负载均衡+服务器池+资源监控
├── ipc_queue_adapter.py (246行)    # IPC队列适配器
└── requirements.txt
```

**新架构（v3.0）**：
```
data_module_vnpy/
├── __init__.py                        # API统一导出（~200行）
├── core_engine.py                     # 核心引擎+配置+事件+时间同步（~4000行）
├── data_acquisition.py                # 品种管理+数据下载+TDX读取（~8000行）
├── data_storage.py                    # 存储管理+异步I/O+缓存（~5000行）
├── data_quality.py                    # 质量管理+监控+验证（~6000行）
├── data_runtime.py                    # 运行时管理+统一查询+实时推送（~6000行）
├── load_balancer.py                   # 负载均衡+服务器池+资源监控（~7000行）
└── requirements.txt                   # Python依赖
```

**变化说明**：
- 文件数：7个 → 6个（减少1个文件）
- 合并策略：
  - `data_module.py` → `core_engine.py`（重命名，功能保持一致）
  - `data_management.py` → 拆分到`data_storage.py`和`data_runtime.py`（按职责拆分）
  - `ipc_queue_adapter.py` → 功能整合到各模块中（不再独立文件）
- 文件规模：每个文件4000-8000行，便于AI Debug

#### 1.3.2 文件职责划分

| 文件 | 核心职责 | 包含组件 | 代码行数 |
|------|---------|---------|---------|
| `core_engine.py` | 核心引擎与基础设施 | ChinaStockEngine, ConfigManager, EventPublisher系列, DailyCacheManager, NetworkTimeSync | ~4000行 |
| `data_acquisition.py` | 数据获取 | SymbolLoader, MultiProcessStockFetcher, TdxBinaryReader, TdxDynamicExecutor | ~8000行 |
| `data_storage.py` | 存储管理 | StorageManager, PreloadService, LRUCacheManager, SharedMemoryManager | ~5000行 |
| `data_quality.py` | 数据质量管理 | DataSensor, StatelessValidator, DataFileWatcher, HealthChecker, IPODateCache | ~6000行 |
| `data_runtime.py` | 运行时管理 | UnifiedDataManager, TdxDataSource, VirtualDataSource, SubscriptionManager | ~6000行 |
| `load_balancer.py` | 负载均衡 | LoadBalancer, ServerPoolManager, ResourceMonitor, DynamicConfigCalculator | ~7000行 |

---

## 二、核心文件设计

### 2.1 core_engine.py - 核心引擎与基础设施

#### 2.1.1 文件定位

**核心职责**：整个数据模块的中枢，提供统一入口和基础设施服务。

**设计原则**：
- 引擎作为唯一对外接口，协调所有功能组件
- 基础设施组件（配置、事件、缓存、时间）集中管理
- 保持轻量级，不包含业务逻辑

#### 2.1.2 组件清单

**Part 1: 网络时间同步（NetworkTimeSync）**
- 功能：从NTP服务器同步真实时间
- 用途：数据新鲜度计算、缓存验证
- 实现：单例模式，线程安全，1小时TTL缓存

**Part 2: 缓存管理（DailyCacheManager）**
- 功能：日期失效机制的缓存管理
- 用途：品种列表缓存、服务器池缓存、交易日历缓存
- 实现：静态方法，日期验证，自动清理

**Part 3: 配置管理（ConfigManager）**
- 功能：统一配置管理，路径自动标准化
- 用途：所有模块的配置访问
- 实现：单例模式，配置热更新支持，类型转换

**Part 4: 事件系统（EventPublisher系列）**
- 功能：分类事件发布
- 包含：
  - `EventPublisher`：通用事件发布
  - `ValidationEventPublisher`：验证事件发布
  - `DownloadEventPublisher`：下载事件发布
  - `QualityEventPublisher`：质量事件发布
  - `SubscriptionEventPublisher`：订阅事件发布（新增）

**Part 5: 核心引擎（ChinaStockEngine）**
- 功能：整个模块的统一入口
- 职责：
  - 初始化所有子组件
  - 提供统一API接口
  - 协调组件间交互
  - 健康检查和状态管理

#### 2.1.3 详细设计

##### Part 1: 网络时间同步（NetworkTimeSync）

**类设计**：
```python
class NetworkTimeSync:
    """网络时间同步器（线程安全单例）"""

    # 类变量
    _instance: Optional["NetworkTimeSync"] = None
    _lock: threading.Lock = threading.Lock()

    # NTP服务器列表（国内优先）
    NTP_SERVERS: List[str] = [
        "ntp.aliyun.com",
        "ntp.tencent.com",
        "cn.ntp.org.cn",
        ...
    ]

    def __init__(self):
        self.ntp_client: Optional[ntplib.NTPClient] = None
        self._cached_offset: Optional[float] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl: int = 3600  # 1小时
        self._sync_lock: threading.Lock = threading.Lock()
        ...

    @classmethod
    def get_instance(cls) -> "NetworkTimeSync":
        """获取单例实例（线程安全）"""
        ...

    def sync_time(self, timeout: float = 3.0) -> Tuple[bool, Optional[float]]:
        """从NTP服务器同步时间"""
        ...

    def get_real_datetime(self) -> datetime:
        """获取真实的当前时间（网络时间）"""
        ...

    def get_real_date(self) -> date:
        """获取真实的当前日期"""
        ...

    def get_time_offset(self) -> Optional[float]:
        """获取当前时间偏移量"""
        ...

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        ...
```

**native_iocp集成点**：
- 当前无文件I/O需求
- （预留）缓存时间偏移量的异步文件写入

**native_ipc集成点**：
- （预留）跨进程时间同步状态通知

##### Part 2: 缓存管理（DailyCacheManager）

**类设计**：
```python
class DailyCacheManager:
    """统一缓存管理，日期失效机制"""

    @staticmethod
    def save_with_date(data: Any, cache_file: Path) -> bool:
        """保存数据并记录日期"""
        ...

    @staticmethod
    def load_with_validation(cache_file: Path) -> Tuple[Any, str, bool]:
        """加载数据并验证日期有效性"""
        ...

    @staticmethod
    def clear_cache(cache_file: Path) -> bool:
        """清理缓存文件"""
        ...

    @staticmethod
    def get_cache_date(cache_file: Path) -> Optional[str]:
        """获取缓存日期"""
        ...

    @staticmethod
    async def save_with_date_async(data: Any, cache_file: Path) -> bool:
        """异步保存数据（使用native_iocp）"""
        ...

    @staticmethod
    async def load_with_validation_async(cache_file: Path) -> Tuple[Any, str, bool]:
        """异步加载数据（使用native_iocp）"""
        ...
```

**native_iocp集成点**：
- **核心**：所有缓存文件的异步读写
- 实现：使用`compat_aopen`进行异步文件操作
- 降级：native_iocp不可用时使用`aiofiles`

**native_ipc集成点**：
- （预留）跨进程缓存失效通知

##### Part 3: 配置管理（ConfigManager）

**类设计**：
```python
class ConfigManager:
    """统一配置管理，路径自动标准化"""

    _instance: Optional["ConfigManager"] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._config_file: Path = ...
        self._load_config()
        ...

    @classmethod
    def get_instance(cls) -> "ConfigManager":
        """获取单例实例"""
        ...

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        ...

    def set(self, key: str, value: Any) -> bool:
        """设置配置项"""
        ...

    def get_cache_dir(self) -> Path:
        """获取缓存目录（自动标准化）"""
        ...

    def get_data_dir(self) -> Path:
        """获取数据目录（Parquet）"""
        ...

    def get_db_file(self) -> Path:
        """获取数据库文件"""
        ...

    def get_tdx_dir(self) -> Path:
        """获取通达信目录"""
        ...

    def reload_config(self) -> bool:
        """重新加载配置"""
        ...
```

**native_iocp集成点**：
- （预留）配置文件的异步读写

**native_ipc集成点**：
- **核心**：配置热更新的跨进程通知
- 实现：当配置更新时，通过native_ipc通知所有子进程

##### Part 4: 事件系统（EventPublisher系列）

**类设计**：
```python
class EventPublisher:
    """通用事件发布器"""

    def __init__(self, event_engine: EventEngine):
        self.event_engine = event_engine
        ...

    def publish(self, event_type: str, data: Any) -> None:
        """发布事件"""
        event = Event(event_type, data)
        self.event_engine.put(event)

class ValidationEventPublisher(EventPublisher):
    """验证事件发布器"""

    EVENT_CHINASTOCK_VALIDATION = "eChinastockValidation"
    EVENT_VALIDATION_COMPLETED = "eValidationCompleted"

    def publish_validation_progress(self, symbol: str, progress: int) -> None:
        """发布验证进度"""
        ...

    def publish_validation_result(self, result: Dict) -> None:
        """发布验证结果"""
        ...

class DownloadEventPublisher(EventPublisher):
    """下载事件发布器"""

    EVENT_CHINASTOCK_DOWNLOAD = "eChinastockDownload"

    def publish_download_progress(self, progress: Dict) -> None:
        """发布下载进度"""
        ...

class QualityEventPublisher(EventPublisher):
    """质量事件发布器"""

    EVENT_DATA_QUALITY_UPDATE = "eDataQualityUpdate"

    def publish_quality_update(self, overview: QualityOverview) -> None:
        """发布质量更新"""
        ...

class SubscriptionEventPublisher(EventPublisher):
    """订阅事件发布器（新增）"""

    EVENT_SUBSCRIPTION_ADDED = "eSubscriptionAdded"
    EVENT_SUBSCRIPTION_REMOVED = "eSubscriptionRemoved"
    EVENT_SUBSCRIPTION_UPDATED = "eSubscriptionUpdated"

    def publish_subscription_added(self, module: str, symbols: List[str]) -> None:
        """发布订阅添加事件"""
        ...

    def publish_subscription_removed(self, module: str) -> None:
        """发布订阅移除事件"""
        ...
```

**native_ipc集成点**：
- **核心**：跨进程事件分发
- 实现：通过native_ipc将事件转发到子进程
- 用途：多进程下载的进度通知、质量扫描结果通知

##### Part 5: 核心引擎（ChinaStockEngine）

**类设计**：
```python
class ChinaStockEngine:
    """中国股票数据引擎（核心引擎）"""

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine):
        self.main_engine = main_engine
        self.event_engine = event_engine

        # 初始化配置管理
        self.config_manager = ConfigManager.get_instance()

        # 初始化事件发布器
        self.download_publisher = DownloadEventPublisher(event_engine)
        self.validation_publisher = ValidationEventPublisher(event_engine)
        self.quality_publisher = QualityEventPublisher(event_engine)
        self.subscription_publisher = SubscriptionEventPublisher(event_engine)

        # 初始化子组件（延迟导入）
        self.symbol_loader: Optional[SymbolLoader] = None
        self.data_fetcher: Optional[MultiProcessStockFetcher] = None
        self.storage_manager: Optional[StorageManager] = None
        self.data_validator: Optional[StatelessValidator] = None
        self.data_sensor: Optional[DataSensor] = None
        self.unified_data_manager: Optional[UnifiedDataManager] = None
        self.load_balancer: Optional[LoadBalancer] = None

        # 状态管理
        self._is_ready: bool = False
        self._initialization_lock: threading.Lock = threading.Lock()
        ...

    def initialize(self) -> bool:
        """初始化所有子组件"""
        with self._initialization_lock:
            if self._is_ready:
                return True

            try:
                # 初始化网络时间同步
                NetworkTimeSync.get_instance().sync_time()

                # 初始化子组件
                self._initialize_components()

                self._is_ready = True
                return True
            except Exception as e:
                logger.error(f"引擎初始化失败: {e}", exc_info=True)
                return False

    def _initialize_components(self) -> None:
        """初始化所有子组件"""
        # 延迟导入避免循环依赖
        from .data_acquisition import SymbolLoader, MultiProcessStockFetcher
        from .data_storage import StorageManager
        from .data_quality import StatelessValidator, DataSensor
        from .data_runtime import UnifiedDataManager
        from .load_balancer import LoadBalancer

        # 初始化顺序很重要
        self.storage_manager = StorageManager()
        self.data_validator = StatelessValidator()
        self.symbol_loader = SymbolLoader(self.event_engine)
        self.data_fetcher = MultiProcessStockFetcher(self.event_engine)
        self.data_sensor = DataSensor(self.event_engine)
        self.unified_data_manager = UnifiedDataManager(self)
        self.load_balancer = LoadBalancer.get_instance(self.event_engine)

    # API接口（保持100%向后兼容）
    def reload_stock_list(self) -> Dict[str, Any]:
        """重新加载品种列表"""
        ...

    def download_incremental(self, start_date: str, intervals: List[str]) -> Dict:
        """增量下载"""
        ...

    def query_data(self, symbol: str, interval: str, start: str, end: str) -> pd.DataFrame:
        """查询数据（统一接口）"""
        ...

    def healthcheck(self) -> Dict[str, Any]:
        """健康检查"""
        ...

    def is_ready(self) -> bool:
        """检查是否就绪"""
        return self._is_ready
```

**native_iocp集成点**：
- 通过子组件间接使用（StorageManager、DailyCacheManager）

**native_ipc集成点**：
- （预留）引擎状态的跨进程查询
- 子组件的事件通过native_ipc跨进程分发

### 2.2 data_acquisition.py - 数据获取模块

> **业务规则参考**：品种管理规则、数据下载规则等业务逻辑请参考 [业务细节文档 - 一、品种管理业务规则](./data_module_vnpy新架构业务细节文档.md#一品种管理业务规则) 和 [二、数据下载业务规则](./data_module_vnpy新架构业务细节文档.md#二数据下载业务规则)

#### 2.2.1 文件定位

**核心职责**：负责所有数据的获取，包括品种管理、网络下载、本地TDX读取。

**设计原则**：
- 多进程+协程并发架构
- 智能负载均衡集成
- 支持暂停/恢复/取消
- 详细的进度报告和日志

#### 2.2.2 组件清单

**Part 1: 品种管理（SymbolLoader）**
- 功能：品种列表获取、分类、缓存
- 支持：上证/深证/北证/T+0基金/可转债分类

**Part 2: 数据下载（MultiProcessStockFetcher）**
- 功能：多进程+协程K线下载
- **下载策略**：
  - **单段式下载**：使用IPv4池
  - **两段式下载**：
    - **第一部分**：使用IPv4池（绝大部分下载使用IPv4池）
    - **第二部分**：使用IPv6池（当剩余任务数≤50时切换到IPv6池）
    - **降级策略**：如IPv6池不可用，则自动回退到IPv4池
  - **服务器池选择**：通过`ServerPoolManager.get_servers_shuffled(pool_type="ipv4"|"ipv6")`获取
- 特性：智能负载均衡、任务管理

**Part 3: IPO日期下载（download_ipo_dates）**
- 功能：批量下载IPO日期
- 特性：多进程并发、缓存机制

**Part 4: TDX本地读取（TdxBinaryReader + TdxDynamicExecutor）**
- 功能：读取通达信本地二进制文件
- 特性：多进程+协程并发读取、北证解码

**Part 5: 任务日志（TaskDetailLogger）**
- 功能：详细的下载任务日志记录
- 特性：按worker记录、性能统计

#### 2.2.3 详细设计

##### Part 1: 品种管理（SymbolLoader）

**类设计**：
```python
class SymbolLoader:
    """品种列表加载器"""

    def __init__(self, event_engine: Optional[EventEngine] = None):
        self.event_engine = event_engine
        self._symbol_cache: Optional[Dict] = None
        ...

    async def load_from_api_async(self) -> Dict[str, Any]:
        """从API异步加载品种列表"""
        # 调用tdx_asyncio接口
        ...

    async def load_from_cache_async(self) -> Optional[Dict]:
        """从缓存异步加载（使用native_iocp）"""
        cache_file = config_manager.get_cache_dir() / "stock_list_classified.json"
        return await DailyCacheManager.load_with_validation_async(cache_file)

    async def reload_and_classify_async(self) -> Dict:
        """重新加载并分类（异步版本）"""
        # 1. 从API加载
        # 2. 分类处理
        # 3. 缓存保存（使用native_iocp）
        ...
```

**native_iocp集成点**：
- **核心**：缓存文件的异步读写
- 实现：使用`DailyCacheManager.load_with_validation_async`

##### Part 2: 数据下载（MultiProcessStockFetcher）

**类设计**：
```python
class MultiProcessStockFetcher:
    """多进程+协程K线下载器"""

    def __init__(self, event_engine: Optional[EventEngine] = None):
        self.event_engine = event_engine
        self.load_balancer = LoadBalancer.get_instance(event_engine)
        self._download_state = DownloadState.IDLE
        ...

     async def download_incremental_kline_async(
         self,
         symbols: List[str],
         start_date: str,
         intervals: List[str],
         use_adaptive: bool = True,
         use_two_phase: bool = True
     ) -> Dict:
         """异步增量下载"""
         # 1. 获取最优配置（LoadBalancer）
         task = KlineDownloadTask(...)
         config = self.load_balancer.get_optimal_config(task)

         # 2. 多进程+协程下载
         #    - 第一部分：使用IPv4池（绝大部分下载）
         #    - 第二部分（如启用两段式）：使用IPv6池，如不可用则回退到IPv4池
         # 3. 使用native_ipc同步进度
         ...
```

**native_iocp集成点**：
- 任务日志文件的异步写入

**native_ipc集成点**：
- **核心**：多进程下载的进度同步
- 实现：通过AsyncIPCPipe在各进程间传递进度信息

##### Part 3-5: 其他组件（略，设计思路类似）

---

### 2.3 data_storage.py - 存储管理模块

#### 2.3.1 文件定位

**核心职责**：负责所有数据的存储、读取、缓存管理。

**设计原则**：
- 全面异步化（使用native_iocp）
- LRU缓存+TTL机制
- 预加载智能缓存
- 多进程共享数据

#### 2.3.2 组件清单

**Part 1: Parquet存储管理（StorageManager）**
- 功能：Parquet文件的读写管理
- **核心改进**：全面使用native_iocp异步I/O

**Part 2: 预加载服务（PreloadService）**
- 功能：常用品种智能预加载
- 特性：LRU缓存、TTL机制

**Part 3: LRU缓存管理（LRUCacheManager）**
- 功能：LRU缓存实现
- 特性：支持TTL、自动淘汰

**Part 4: 共享内存管理（SharedMemoryManager）**
- 功能：多进程数据共享
- 用途：验证上下文共享

#### 2.3.3 详细设计

##### Part 1: Parquet存储管理（StorageManager）

**类设计（重点：异步化改进）**：
```python
class StorageManager:
    """Parquet存储管理器（全面异步化）"""

    def __init__(self):
        self.config_manager = ConfigManager.get_instance()
        self.data_dir = self.config_manager.get_data_dir()
        ...

    async def save_data_async(
        self,
        symbol: str,
        interval: str,
        df: pd.DataFrame
    ) -> bool:
        """异步保存数据（使用native_iocp）"""
        file_path = self.get_data_path(symbol, interval)

        try:
            # 使用native_iocp异步写入
            from backend.infrastructure.native_iocp import compat_aopen
            from io import BytesIO

            # 先同步到内存
            buffer = BytesIO()
            df.to_parquet(buffer, engine='pyarrow', compression='snappy')
            data = buffer.getvalue()

            # 异步写入文件
            async with await compat_aopen(file_path, 'wb') as f:
                await f.write(data)

            return True
        except Exception as e:
            logger.error(f"保存数据失败: {e}", exc_info=True)
            return False

    async def load_data_async(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> Optional[pd.DataFrame]:
        """异步加载数据（使用native_iocp）"""
        file_path = self.get_data_path(symbol, interval)

        if not file_path.exists():
            return None

        try:
            # 使用native_iocp异步读取
            from backend.infrastructure.native_iocp import compat_aopen
            from io import BytesIO

            async with await compat_aopen(file_path, 'rb') as f:
                data = await f.read()

            # 解析Parquet
            df = pd.read_parquet(BytesIO(data))

            # 日期过滤
            if start_date or end_date:
                df = self._filter_by_date(df, start_date, end_date)

            return df
        except Exception as e:
            logger.error(f"加载数据失败: {e}", exc_info=True)
            return None

    # 向后兼容：保留同步版本
    def save_data(self, symbol: str, interval: str, df: pd.DataFrame) -> bool:
        """同步保存数据（向后兼容）"""
        return asyncio.run(self.save_data_async(symbol, interval, df))

    def load_data(self, symbol: str, interval: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> Optional[pd.DataFrame]:
        """同步加载数据（向后兼容）"""
        return asyncio.run(self.load_data_async(symbol, interval, start_date, end_date))
```

**native_iocp集成点**：
- **核心**：所有Parquet文件的异步读写
- 性能提升：预期50-80%提升
- 降级：native_iocp不可用时使用aiofiles

**native_ipc集成点**：
- （预留）多进程缓存同步

### 2.4 data_quality.py - 数据质量管理模块

> **业务规则参考**：数据验证规则、质量检查标准等业务逻辑请参考 [业务细节文档 - 三、数据验证业务规则](./data_module_vnpy新架构业务细节文档.md#三数据验证业务规则)

#### 2.4.1 文件定位

**核心职责**：负责数据质量管理，包括质量扫描、验证、监控、健康检查。

**设计原则**：
- 混合异步扫描（协程+线程+进程）
- 增量扫描优化
- 实时文件监控
- GPU加速验证（可选）

#### 2.4.2 组件清单

**Part 1: 数据质量感知（DataSensor）**
- 功能：全方位数据质量监控
- 特性：混合异步扫描、增量推送

**Part 2: 数据验证器（StatelessValidator）**
- 功能：无状态数据验证
- 特性：支持多进程、纯函数

**Part 3: 文件监控（DataFileWatcher）**
- 功能：实时监控数据文件变化
- 特性：防抖机制、事件发布

**Part 4: 健康检查（HealthChecker）**
- 功能：系统健康状态检查
- 特性：多维度检查、诊断建议

**Part 5: IPO日期缓存（IPODateCache）**
- 功能：IPO日期两级缓存
- 特性：内存+文件缓存、95%+命中率

#### 2.4.3 详细设计要点

**native_iocp集成点**：
- 质量扫描时的文件异步读取
- IPO缓存文件的异步读写

**native_ipc集成点**：
- **核心**：多进程验证结果的汇总
- 实现：通过AsyncIPCPipe收集各进程的验证结果
- 文件监控事件的跨进程推送

---

### 2.5 data_runtime.py - 运行时管理模块

#### 2.5.1 文件定位

**核心职责**：负责运行时数据管理，包括统一查询、实时推送、订阅管理。

**设计原则**：
- 四层数据融合查询
- 符合VnPy Gateway标准
- 事件驱动推送
- 智能预加载

#### 2.5.2 组件清单

**Part 1: 统一数据管理器（UnifiedDataManager）**
- 功能：四层数据融合查询
- **核心改进**：全面异步化查询

**Part 2: TDX数据源（TdxDataSource）**
- 功能：轮询转推送，符合VnPy Gateway标准
- 特性：定时轮询、事件推送

**Part 3: 虚拟数据源（VirtualDataSource）**
- 功能：历史数据回放
- 特性：支持倍速、暂停、恢复

**Part 4: 订阅管理器（SubscriptionManager）**
- 功能：数据订阅管理
- **核心改进**：跨进程订阅同步（使用native_ipc）

#### 2.5.3 详细设计

##### Part 1: 统一数据管理器（UnifiedDataManager）

**类设计（重点：异步化改进）**：
```python
class UnifiedDataManager:
    """统一数据管理器（四层数据融合，全面异步化）"""

    def __init__(self, china_stock_engine: ChinaStockEngine):
        self.engine = china_stock_engine
        self.storage_manager = china_stock_engine.storage_manager
        self.preload_service = PreloadService(self.storage_manager)
        ...

    async def query_unified_async(
        self,
        symbol: str,
        interval: str,
        start_date: str,
        end_date: str,
        check_gaps: bool = True
    ) -> Optional[pd.DataFrame]:
        """异步统一查询（四层融合）"""
        # Layer 1: 预加载缓存
        df = self.preload_service.get_from_cache(symbol, interval)
        if df is not None:
            return self._filter_by_date(df, start_date, end_date)

        # Layer 2: 历史Parquet（使用native_iocp异步读取）
        df = await self.storage_manager.load_data_async(
            symbol, interval, start_date, end_date
        )
        if df is not None:
            # 更新预加载缓存
            self.preload_service.add_to_cache(symbol, interval, df)
            return df

        # Layer 3: 录制数据（如启用）
        # ...

        # Layer 4: 实时推送（如已订阅）
        # ...

        # 缺失检测
        if check_gaps:
            await self._auto_download_missing(symbol, interval, start_date, end_date)

        return None

    # 向后兼容：保留同步版本
    def query_unified(
        self,
        symbol: str,
        interval: str,
        start_date: str,
        end_date: str,
        check_gaps: bool = True
    ) -> Optional[pd.DataFrame]:
        """同步统一查询（向后兼容）"""
        return asyncio.run(
            self.query_unified_async(symbol, interval, start_date, end_date, check_gaps)
        )
```

**native_iocp集成点**：
- **核心**：统一查询时的异步文件读取
- 通过StorageManager间接使用

**native_ipc集成点**：
- **核心**：订阅信息的跨进程同步
- 实现：当订阅变更时，通过native_ipc同步到所有相关进程

##### Part 4: 订阅管理器（SubscriptionManager）

**类设计（重点：native_ipc集成）**：
```python
class SubscriptionManager:
    """订阅管理器（支持跨进程同步）"""

    def __init__(self, event_engine: EventEngine):
        self.event_engine = event_engine
        self._subscriptions: Dict[str, List[str]] = {}  # module -> symbols
        self._ipc_sync_pipe: Optional[AsyncIPCPipe] = None
        ...

    async def subscribe_async(
        self,
        module: str,
        symbols: List[str]
    ) -> bool:
        """异步订阅（跨进程同步）"""
        self._subscriptions[module] = symbols

        # 本地事件发布
        event_publisher = SubscriptionEventPublisher(self.event_engine)
        event_publisher.publish_subscription_added(module, symbols)

        # 跨进程同步（使用native_ipc）
        await self._sync_subscriptions_to_processes()

        return True

    async def _sync_subscriptions_to_processes(self) -> None:
        """跨进程同步订阅信息"""
        from backend.infrastructure.native_ipc import AsyncIPCPipe

        if self._ipc_sync_pipe is None:
            self._ipc_sync_pipe = await AsyncIPCPipe.server("data_subscriptions")

        # 发送订阅信息到所有子进程
        sync_data = {
            "action": "sync_subscriptions",
            "subscriptions": self._subscriptions
        }
        await self._ipc_sync_pipe.write(
            json.dumps(sync_data).encode()
        )
```

**native_ipc集成点**：
- **核心**：订阅信息的跨进程同步
- 实现：通过AsyncIPCPipe在各进程间同步订阅状态

### 2.6 load_balancer.py - 负载均衡模块

#### 2.6.1 文件定位

**核心职责**：负责智能负载均衡，包括动态并发调整、服务器池管理、资源监控。

**设计原则**：
- **木桶理论**：只看最短的那块板（CPU占用、内存占用、磁盘IO），不是加权评分
- 动态并发调整（0.3x-1.6x缩放）
- **智能防抖机制**：基础间隔1秒，特定模式3秒
- 磁盘类型化保护

#### 2.6.2 组件清单

**Part 1: 负载均衡器（LoadBalancer）**
- 功能：根据系统资源动态调整并发配置
- 特性：木桶理论（只看最短板）、动态调整、智能防抖机制

**Part 2: 服务器池管理（ServerPoolManager）**
- 功能：TDX服务器测速、排序、热备管理
- **特性**：
  - 多进程测速、IPv4/IPv6分离
  - 两段式下载：第一部分使用IPv4池，第二部分使用IPv6池（不可用时回退到IPv4池）
  - 缓存机制

**Part 3: 资源监控（ResourceMonitor）**
- 功能：系统资源实时监控
- 特性：CPU、内存、磁盘、网络监控

**Part 4: 动态配置计算（DynamicConfigCalculator）**
- 功能：计算任务的最优并发配置
- 特性：基于压力评分、考虑任务类型

**Part 5: 参数调优器（ParameterTuner）**
- 功能：自动参数优化
- 特性：基于历史数据、预测性调整

#### 2.6.3 详细设计要点

**native_iocp集成点**：
- 服务器池缓存文件的异步读写
- 资源监控时的文件I/O异步检查

**native_ipc集成点**：
- **核心**：监控进程与主进程的通信（替代ZMQ）
- 实现：通过AsyncIPCPipe进行资源指标查询和配置同步

---

## 三、native_iocp深度集成方案

### 3.1 集成策略

#### 3.1.1 集成层次

**Level 1: 存储层全面异步化**
- StorageManager：所有Parquet文件读写使用native_iocp
- 性能提升：50-80% I/O性能提升

**Level 2: 缓存层异步化**
- DailyCacheManager：所有缓存文件读写使用native_iocp
- 包括：品种列表缓存、服务器池缓存、交易日历缓存、IPO日期缓存

**Level 3: TDX读取异步化**
- TdxBinaryReader：TDX本地文件读取使用native_iocp
- 性能提升：40-60%读取性能提升

**Level 4: 任务日志异步化**
- TaskDetailLogger：任务日志文件写入使用native_iocp

#### 3.1.2 自动降级机制

**降级策略**：
```python
try:
    from backend.infrastructure.native_iocp import compat_aopen
    _USE_IOCP = True
except ImportError:
    # 降级到aiofiles
    try:
        import aiofiles
        compat_aopen = aiofiles.open
        _USE_IOCP = False
    except ImportError:
        # 最终降级到同步I/O（不推荐）
        compat_aopen = None
        _USE_IOCP = False
```

### 3.2 关键集成点详解

#### 3.2.1 StorageManager异步化

**实现方案**：
```python
async def load_data_async(...) -> Optional[pd.DataFrame]:
    # 1. 使用native_iocp异步读取
    async with await compat_aopen(file_path, 'rb') as f:
        data = await f.read()

    # 2. 解析Parquet（CPU操作，非阻塞）
    df = pd.read_parquet(BytesIO(data))

    return df
```

**性能对比**：
- 同步I/O：~10ms/文件
- 异步I/O（native_iocp）：~2-5ms/文件
- 提升：50-80%

#### 3.2.2 TdxBinaryReader异步化

**实现方案**：
```python
async def read_single_async(...) -> Optional[pd.DataFrame]:
    # 1. 异步读取TDX二进制文件
    async with await compat_aopen(file_path, 'rb') as f:
        raw_data = await f.read()

    # 2. 解码（CPU操作）
    df = self._decode_tdx_binary(raw_data)

    return df
```

**性能提升**：
- 同步读取：~5-10ms/文件
- 异步读取：~2-4ms/文件
- 提升：40-60%

### 3.3 性能优化要点

1. **批量操作**：使用`asyncio.gather`并发读取多个文件
2. **缓冲区大小**：根据文件大小调整读取缓冲区
3. **错误处理**：完善异常处理和降级机制
4. **性能监控**：记录I/O性能指标，用于负载均衡

## 四、native_ipc深度集成方案

### 4.1 集成策略

#### 4.1.1 集成目标

**重要说明**：native_ipc是用于**替代现有ZMQ通信**，而非新增通信层。

**替代范围**：
- ✅ 监控进程 ↔ 主进程通信（替代ZMQ）
- ✅ 多进程下载进度同步（替代现有方案）
- ✅ 数据订阅的跨进程同步（新增功能）
- ✅ 实时推送事件的跨进程分发（新增功能）
- ❌ UI ↔ data_module_vnpy直接调用（保持不变）

**通信架构对比**：
```
当前架构：UI → data_module_vnpy ← ZMQ ← 监控进程
新架构：  UI → data_module_vnpy ← native_ipc ← 监控进程
```

**核心目标**：
1. 替代ZMQ：监控进程与主进程通信使用native_ipc
2. 跨进程数据同步：多进程下载的进度同步
3. 订阅管理同步：数据订阅的跨进程同步
4. 事件分发：实时推送事件的跨进程分发

#### 4.1.2 通信模式设计

**模式1: 请求-响应（REQ/REP）**
- 用途：监控数据查询、配置查询
- 实现：主进程作为服务端，子进程作为客户端

**模式2: 发布-订阅（PUB/SUB）**
- 用途：实时推送、事件分发
- 实现：一个发布端+多个订阅端（多个pipe实例）

**模式3: 任务队列**
- 用途：多进程任务分发、进度同步
- 实现：基于AsyncIPCPipe的队列适配器

### 4.2 关键集成点详解

#### 4.2.1 监控进程通信（替代ZMQ）

**当前方案（ZMQ）**：
```python
# ZMQ通信
zmq_context = zmq.Context()
alert_socket = zmq_context.socket(zmq.PUSH)
alert_socket.connect("tcp://127.0.0.1:5555")
alert_socket.send_json(alert_data)
```

**新方案（native_ipc）**：
```python
# native_ipc通信
from backend.infrastructure.native_ipc import AsyncIPCPipe

async def send_alert(alert_data: Dict):
    async with AsyncIPCPipe.client("monitor_alerts") as pipe:
        await pipe.write(json.dumps(alert_data).encode())
```

**优势**：
- 真异步：无线程池开销
- 更低延迟：<10ms（优于ZMQ）
- Windows专属：充分利用Windows IPC机制

#### 4.2.2 多进程进度同步

**实现方案**：
```python
class IPCProgressQueue:
    """基于native_ipc的进度队列"""

    def __init__(self, pipe_name: str):
        self.pipe_name = pipe_name
        self.pipe: Optional[AsyncIPCPipe] = None

    async def start_server(self):
        """启动服务端（主进程）"""
        self.pipe = await AsyncIPCPipe.server(self.pipe_name)

    async def send_progress(self, worker_id: int, progress: Dict):
        """发送进度（子进程）"""
        async with AsyncIPCPipe.client(f"{self.pipe_name}_{worker_id}") as pipe:
            data = {
                "worker_id": worker_id,
                "progress": progress,
                "timestamp": time.time()
            }
            await pipe.write(json.dumps(data).encode())

    async def receive_progress(self) -> Dict:
        """接收进度（主进程）"""
        if self.pipe is None:
            await self.start_server()
        data = await self.pipe.read()
        return json.loads(data.decode())
```

#### 4.2.3 数据订阅同步

**实现方案**：
```python
class SubscriptionSync:
    """订阅信息跨进程同步"""

    async def sync_subscriptions(self, subscriptions: Dict):
        """同步订阅信息到所有子进程"""
        from backend.infrastructure.native_ipc import AsyncIPCPipe

        # 主进程作为服务端
        async with AsyncIPCPipe.server("data_subscriptions") as server_pipe:
            sync_data = {
                "action": "sync_subscriptions",
                "subscriptions": subscriptions,
                "timestamp": time.time()
            }

            # 发送到所有已连接的客户端（子进程）
            await server_pipe.write(json.dumps(sync_data).encode())

    async def receive_subscription_sync(self) -> Dict:
        """接收订阅同步（子进程）"""
        async with AsyncIPCPipe.client("data_subscriptions") as client_pipe:
            data = await client_pipe.read()
            return json.loads(data.decode())
```

### 4.3 性能优化要点

1. **连接复用**：保持pipe连接，避免频繁创建
2. **批量传输**：合并多个小消息成一个大消息
3. **异步处理**：使用async/await，避免阻塞
4. **错误处理**：完善的异常处理和重连机制

## 五、智能负载机制优化

### 5.1 当前机制分析

#### 5.1.1 木桶理论评估

**核心原理**：木桶理论只看最短的那块板，不是加权评分。

**当前实现**：
- **监控指标**：CPU占用、内存占用、磁盘IO（通过协程任务队列和任务延迟观察）
- **木桶理论公式**：系统性能 = min(CPU使用率, 内存使用率, 磁盘IO使用率)
- **瓶颈识别**：得分最低的维度即为系统瓶颈
- **关键原则**：只关注最短的那块板，而不是加权求和

**并发调整级别**（基于最短板的压力评分）：
- 紧急（0-30分）：0.3x并发
- 高压（31-50分）：0.5x-0.7x并发
- 中等（51-70分）：0.8x-1.0x并发
- 正常（71-100分）：1.0x-1.6x并发

#### 5.1.2 动态并发调整与防抖机制

**当前机制**：
- 基于压力评分动态调整并发数
- **智能防抖机制**：减少评估开销，避免频繁调整
- 磁盘类型化保护（HDD/SSD/NVMe）

**防抖机制详细规则**：
- **基础调整间隔**：1秒
- **特殊情况（3秒间隔）**：只有在以下两种模式时才使用3秒
  1. `increase → decrease → increase`（先增后减再增）
  2. `decrease → increase → decrease`（先减后增再减）
- **决策逻辑**：
  - 观察前两次评估结果
  - 如果前两次都是`increase`或都是`decrease`，或者有`hold`，则第三次无条件1秒
  - 如果是`increase/decrease`交叉出现，则分析本次建议是否构成上述两种情况之一
    - 如果构成`increase → decrease → increase`或`decrease → increase → decrease`，则3秒
    - 否则1秒

### 5.2 优化方向

#### 5.2.1 防抖机制优化设计

**防抖机制实现方案**：
```python
class IntelligentDebounceManager:
    """智能防抖管理器"""

    def __init__(self):
        self._evaluation_history: Deque[str] = deque(maxlen=3)  # 保存最近3次评估结果
        self._base_interval: float = 1.0  # 基础间隔：1秒
        self._extended_interval: float = 3.0  # 扩展间隔：3秒

    def should_evaluate_now(self, current_time: float, last_evaluation_time: float) -> bool:
        """判断当前是否应该执行评估"""
        if len(self._evaluation_history) < 2:
            # 前两次评估，无条件1秒
            return (current_time - last_evaluation_time) >= self._base_interval

        # 获取前两次评估结果
        prev_2 = self._evaluation_history[-2]  # 倒数第二次
        prev_1 = self._evaluation_history[-1]  # 倒数第一次

        # 如果前两次都是increase或都是decrease，或者有hold，则第三次无条件1秒
        if prev_2 == prev_1 or prev_2 == "hold" or prev_1 == "hold":
            return (current_time - last_evaluation_time) >= self._base_interval

        # 如果是increase/decrease交叉出现，需要进一步分析
        if (prev_2 == "increase" and prev_1 == "decrease") or \
           (prev_2 == "decrease" and prev_1 == "increase"):
            # 需要等待本次建议结果，暂时不判断
            # 实际实现中会在本次评估完成后更新历史
            pass

        # 默认1秒
        return (current_time - last_evaluation_time) >= self._base_interval

    def record_evaluation_result(self, action: str) -> float:
        """记录评估结果，返回下次评估间隔"""
        self._evaluation_history.append(action)

        if len(self._evaluation_history) < 3:
            return self._base_interval

        # 检查是否构成特定模式
        prev_3 = self._evaluation_history[-3]  # 倒数第三次
        prev_2 = self._evaluation_history[-2]  # 倒数第二次
        prev_1 = self._evaluation_history[-1]  # 倒数第一次（本次）

        # 检查模式1: increase → decrease → increase
        if prev_3 == "increase" and prev_2 == "decrease" and prev_1 == "increase":
            return self._extended_interval  # 3秒

        # 检查模式2: decrease → increase → decrease
        if prev_3 == "decrease" and prev_2 == "increase" and prev_1 == "decrease":
            return self._extended_interval  # 3秒

        # 其他情况：1秒
        return self._base_interval
```

**决策逻辑流程图**：
```
评估请求
    ↓
检查历史记录（前两次）
    ↓
前两次都是increase/decrease 或 有hold？
    ├─ 是 → 无条件1秒
    └─ 否 → 检查是否交叉（increase/decrease）
        ↓
    记录本次评估结果
        ↓
    检查是否构成特定模式（前三次）
        ├─ increase → decrease → increase → 3秒
        ├─ decrease → increase → decrease → 3秒
        └─ 其他 → 1秒
```

#### 5.2.2 事件循环延迟监控

**新增监控指标**：
```python
class LoadBalancer:
    def get_optimal_config(self, task: BaseTask) -> Dict:
        # 新增：监控事件循环延迟
        event_loop_lag_ms = self._get_event_loop_lag()

        if event_loop_lag_ms > 100:  # 延迟>100ms
            # 降低并发，减少事件队列压力
            scale_factor *= 0.7
```

#### 5.2.3 native_iocp性能指标

**新增监控**：
- I/O延迟监控
- 异步I/O吞吐量监控
- 用于负载均衡的I/O性能评估

#### 5.2.4 native_ipc性能指标

**新增监控**：
- IPC通信延迟监控
- IPC吞吐量监控
- 用于负载均衡的IPC性能评估

#### 5.2.5 预测性调整

**实现方案**：
- 基于历史数据预测资源需求
- 提前调整并发配置
- 减少资源波动带来的性能损失

### 5.3 优化实施

1. **智能防抖机制实施**：替换现有的3秒TTL缓存机制，实现智能防抖
   - 基础调整间隔：1秒
   - 特定模式（increase→decrease→increase或decrease→increase→decrease）：3秒
   - 观察前两次评估结果，智能决策
2. **实时监控增强**：增加事件循环延迟、I/O延迟、IPC延迟监控
3. **动态调整优化**：基于多维度指标综合评估
4. **预测性调整**：使用历史数据进行预测
5. **性能指标集成**：将native_iocp/native_ipc性能指标纳入负载均衡

---

## 六、统一数据管理器优化

### 6.1 当前机制分析

#### 6.1.1 四层数据融合

**当前查询优先级**：
1. 预加载缓存（PreloadService）
2. 历史Parquet（StorageManager）
3. 录制数据（如启用录制）
4. 实时推送（如已订阅）

#### 6.1.2 预加载缓存

**当前实现**：
- LRU缓存，最大64品种
- TTL机制
- 自动更新

### 6.2 优化方向

#### 6.2.1 异步查询支持

**全面异步化**：
```python
# 新增：异步查询接口
async def query_unified_async(...) -> Optional[pd.DataFrame]:
    # 所有层级都支持异步
    # 使用native_iocp异步读取文件
```

#### 6.2.2 批量预加载

**并发预加载**：
```python
async def preload_batch_async(
    self,
    symbols: List[str],
    intervals: List[str]
) -> Dict:
    """并发预加载多个品种"""
    tasks = []
    for symbol in symbols:
        for interval in intervals:
            task = self._preload_single(symbol, interval)
            tasks.append(task)

    results = await asyncio.gather(*tasks)
    return results
```

#### 6.2.3 智能缓存策略

**优化方案**：
- 基于访问模式的LRU优化
- 访问频率加权缓存优先级
- 自动预测热点品种

#### 6.2.4 跨进程缓存同步

**使用native_ipc**：
```python
async def sync_cache_to_processes(self, cache_updates: Dict):
    """跨进程同步缓存更新"""
    from backend.infrastructure.native_ipc import AsyncIPCPipe

    async with AsyncIPCPipe.server("cache_updates") as pipe:
        await pipe.write(json.dumps(cache_updates).encode())
```

### 6.3 优化实施

1. **全面异步化**：所有查询接口支持async/await
2. **批量优化**：支持批量预加载和并发查询
3. **智能缓存**：基于访问模式的缓存优化
4. **跨进程同步**：使用native_ipc同步缓存状态

## 七、事件驱动架构优化

### 7.1 事件分类体系

#### 7.1.1 现有事件类型

**下载事件**：
- `EVENT_CHINASTOCK_DOWNLOAD`：下载进度事件

**验证事件**：
- `EVENT_CHINASTOCK_VALIDATION`：验证进度事件
- `EVENT_VALIDATION_COMPLETED`：验证完成事件

**质量事件**：
- `EVENT_DATA_QUALITY_UPDATE`：质量更新事件

**订阅事件（新增）**：
- `EVENT_SUBSCRIPTION_ADDED`：订阅添加事件
- `EVENT_SUBSCRIPTION_REMOVED`：订阅移除事件
- `EVENT_SUBSCRIPTION_UPDATED`：订阅更新事件

#### 7.1.2 事件发布器优化

**新增订阅事件发布器**：
```python
class SubscriptionEventPublisher(EventPublisher):
    """订阅事件发布器"""

    EVENT_SUBSCRIPTION_ADDED = "eSubscriptionAdded"
    EVENT_SUBSCRIPTION_REMOVED = "eSubscriptionRemoved"
    EVENT_SUBSCRIPTION_UPDATED = "eSubscriptionUpdated"

    def publish_subscription_added(self, module: str, symbols: List[str]) -> None:
        """发布订阅添加事件"""
        data = {
            "module": module,
            "symbols": symbols,
            "timestamp": time.time()
        }
        self.publish(self.EVENT_SUBSCRIPTION_ADDED, data)
```

### 7.2 跨进程事件分发

#### 7.2.1 使用native_ipc分发事件

**实现方案**：
```python
class CrossProcessEventDistributor:
    """跨进程事件分发器"""

    def __init__(self):
        self.event_pipe: Optional[AsyncIPCPipe] = None

    async def start_server(self):
        """启动事件服务端（主进程）"""
        self.event_pipe = await AsyncIPCPipe.server("event_distribution")

    async def distribute_event(self, event_type: str, event_data: Dict):
        """分发事件到所有子进程"""
        if self.event_pipe is None:
            await self.start_server()

        message = {
            "type": event_type,
            "data": event_data,
            "timestamp": time.time()
        }
        await self.event_pipe.write(json.dumps(message).encode())

    async def receive_event(self) -> Dict:
        """接收事件（子进程）"""
        async with AsyncIPCPipe.client("event_distribution") as pipe:
            data = await pipe.read()
            return json.loads(data.decode())
```

#### 7.2.2 事件过滤和路由

**实现方案**：
- 支持事件过滤：只分发特定类型的事件
- 支持事件路由：不同子进程接收不同的事件
- 支持事件聚合：合并多个小事件成一个大事件

### 7.3 事件性能优化

1. **事件节流**：高频事件进行节流处理
2. **事件批量**：合并多个事件成一批
3. **异步分发**：使用async/await分发事件
4. **错误处理**：完善的异常处理和重连机制

---

## 八、文件组织优化

### 8.1 合并原则

#### 8.1.1 按业务领域组织

**原则**：按业务领域组织文件，而非技术层次。

**示例**：
- ❌ 不按技术层次：`core.py`, `utils.py`, `helpers.py`
- ✅ 按业务领域：`data_acquisition.py`, `data_storage.py`, `data_quality.py`

#### 8.1.2 相关功能集中

**原则**：相关功能集中在同一文件，便于AI Debug。

**示例**：
- 品种管理 + 数据下载 + TDX读取 → `data_acquisition.py`
- 存储管理 + 异步I/O + 缓存 → `data_storage.py`

### 8.2 分区标记规范

#### 8.2.1 分区标记格式

**标准格式**：
```python
# ==============================================================================
# Part N: 功能名称
# ==============================================================================
# 功能描述
# ...

class ClassName:
    """类文档"""
    ...
```

#### 8.2.2 分区顺序

**建议顺序**：
1. Part 1: 核心类（最重要的类）
2. Part 2-N: 支持类（按依赖关系排序）
3. Part N+1: 工具函数
4. Part N+2: 全局变量和常量

### 8.3 文件规模控制

#### 8.3.1 目标规模

**每个文件**：4000-8000行
- 过小（<3000行）：合并相关文件
- 过大（>10000行）：考虑拆分（但需谨慎）

#### 8.3.2 拆分策略

**拆分原则**：
- 仅当文件>10000行且功能明显独立时拆分
- 拆分后仍保持相关功能在同一文件
- 避免过度拆分导致文件过多

### 8.4 AI Debug友好

#### 8.4.1 相关功能集中

- 相关类和函数放在同一Part
- 避免跨文件跳转过多

#### 8.4.2 清晰的命名

- 类和函数使用清晰的命名
- 避免缩写和不明确的命名

#### 8.4.3 完整的文档

- 每个类都有docstring
- 关键方法都有详细注释

## 九、向后兼容性

### 9.1 API兼容性

#### 9.1.1 100%向后兼容

**原则**：所有现有API保持100%兼容。

**实现策略**：
- 保留所有同步方法（向后兼容）
- 新增异步方法（*_async后缀）
- 同步方法内部调用异步方法

**示例**：
```python
# 向后兼容：保留同步方法
def load_data(self, ...) -> Optional[pd.DataFrame]:
    """同步加载数据（向后兼容）"""
    return asyncio.run(self.load_data_async(...))

# 新增：异步方法
async def load_data_async(self, ...) -> Optional[pd.DataFrame]:
    """异步加载数据（新架构）"""
    # 使用native_iocp异步读取
    ...
```

#### 9.1.2 API迁移指南

**迁移路径**：
1. 保持同步API：所有现有调用继续工作
2. 逐步迁移：新代码使用异步API
3. 完全迁移：未来版本可能废弃同步API（但会给足够时间）

### 9.2 降级策略

#### 9.2.1 native_iocp降级

**降级机制**：
```python
try:
    from backend.infrastructure.native_iocp import compat_aopen
    _USE_IOCP = True
except ImportError:
    # 降级到aiofiles
    try:
        import aiofiles
        compat_aopen = aiofiles.open
        _USE_IOCP = False
    except ImportError:
        # 最终降级到同步I/O
        compat_aopen = None
        _USE_IOCP = False
```

#### 9.2.2 native_ipc降级

**降级机制**：
```python
try:
    from backend.infrastructure.native_ipc import AsyncIPCPipe
    _USE_IPC = True
except ImportError:
    # 降级到ZMQ
    try:
        import zmq
        _USE_IPC = False
        _USE_ZMQ = True
    except ImportError:
        # 最终降级到线程队列
        _USE_IPC = False
        _USE_ZMQ = False
        _USE_THREAD_QUEUE = True
```

### 9.3 配置兼容性

#### 9.3.1 配置文件兼容

- 保持现有配置文件格式
- 新增配置项向后兼容
- 配置文件自动迁移（如需要）

#### 9.3.2 数据格式兼容

- 保持现有Parquet格式
- 保持现有缓存格式
- 保持现有数据库格式

---

## 十、性能目标与指标

### 10.1 I/O性能目标

#### 10.1.1 Parquet读取性能

**目标**：
- 同步I/O：~10ms/文件
- 异步I/O（native_iocp）：~2-5ms/文件
- **提升目标**：50-80%

#### 10.1.2 TDX读取性能

**目标**：
- 同步读取：~5-10ms/文件
- 异步读取（native_iocp）：~2-4ms/文件
- **提升目标**：40-60%

#### 10.1.3 缓存读取性能

**目标**：
- 同步缓存：~1-2ms/文件
- 异步缓存（native_iocp）：~0.5-1ms/文件
- **提升目标**：50%

### 10.2 并发性能目标

#### 10.2.1 最大并发数

**目标**：保持2000最大并发
- 当前：2000并发
- 新架构：2000并发（保持不变）

#### 10.2.2 响应延迟

**目标**：降低20-30%
- 当前：~50ms平均响应延迟
- 新架构：~35-40ms平均响应延迟

### 10.3 内存占用目标

#### 10.3.1 线程池开销

**目标**：消除线程池开销
- 当前：线程池开销 ~100MB
- 新架构：0MB（无线程池）

#### 10.3.2 总体内存

**目标**：降低10-15%
- 当前：~500MB
- 新架构：~425-450MB

### 10.4 通信性能目标

#### 10.4.1 IPC通信延迟

**目标**：<10ms（优于ZMQ）
- ZMQ：~15-20ms
- native_ipc：~5-10ms

#### 10.4.2 IPC吞吐量

**目标**：>100MB/s
- ZMQ：~80MB/s
- native_ipc：>100MB/s

### 10.5 性能监控指标

#### 10.5.1 I/O性能指标

- I/O延迟：监控每个文件操作的延迟
- I/O吞吐量：监控整体I/O吞吐量
- 缓存命中率：监控缓存命中率

#### 10.5.2 IPC性能指标

- IPC延迟：监控每次IPC通信的延迟
- IPC吞吐量：监控整体IPC吞吐量
- 连接数：监控活跃IPC连接数

## 十一、实施计划

### 11.1 阶段划分

#### 阶段1: 核心重构（2周）

**目标**：完成文件重组和合并，保持100%API兼容。

**任务清单**：
1. **文件重组**（3天）
   - 重命名`data_module.py` → `core_engine.py`
   - 拆分`data_management.py` → `data_storage.py` + `data_runtime.py`
   - 整合`ipc_queue_adapter.py`功能到各模块

2. **功能迁移**（5天）
   - 迁移各模块功能到新文件
   - 更新导入路径
   - 修复循环依赖

3. **API兼容性测试**（4天）
   - 编写兼容性测试用例
   - 验证所有现有API正常工作
   - 修复兼容性问题

4. **文档更新**（2天）
   - 更新README.md
   - 更新API文档
   - 更新示例代码

#### 阶段2: native_iocp集成（1周）

**目标**：全面异步化存储层和TDX读取，性能提升50-80%。

**任务清单**：
1. **StorageManager异步化**（2天）
   - 实现`save_data_async`和`load_data_async`
   - 使用native_iocp异步I/O
   - 添加降级机制

2. **DailyCacheManager异步化**（1天）
   - 实现异步缓存读写
   - 更新所有缓存操作

3. **TdxBinaryReader异步化**（2天）
   - 实现异步TDX文件读取
   - 更新多进程读取逻辑

4. **性能测试和优化**（2天）
   - 性能基准测试
   - 优化I/O操作
   - 验证性能提升目标

#### 阶段3: native_ipc集成（2周）

**目标**：替代ZMQ通信，实现跨进程数据同步。

**任务清单**：
1. **监控进程通信替换**（3天）
   - 替换ZMQ为native_ipc
   - 实现AsyncIPCPipe通信
   - 测试通信稳定性

2. **跨进程进度同步**（3天）
   - 实现IPCProgressQueue
   - 集成到多进程下载
   - 测试进度同步准确性

3. **订阅管理同步**（2天）
   - 实现SubscriptionSync
   - 集成到订阅管理
   - 测试订阅同步

4. **事件分发**（2天）
   - 实现CrossProcessEventDistributor
   - 集成到事件系统
   - 测试事件分发

5. **集成测试**（2天）
   - 全面集成测试
   - 性能对比测试
   - 稳定性测试

#### 阶段4: 优化和测试（1周）

**目标**：全面优化、测试和文档完善。

**任务清单**：
1. **性能优化**（2天）
   - 优化异步操作
   - 优化跨进程通信
   - 优化缓存策略

2. **全面测试**（3天）
   - 单元测试
   - 集成测试
   - 性能测试
   - 压力测试

3. **文档完善**（2天）
   - 更新架构文档
   - 更新API文档
   - 更新使用指南

### 11.2 里程碑

**M1: 核心重构完成**（2周后）
- 文件重组完成
- 功能迁移完成
- API兼容性验证通过

**M2: native_iocp集成完成**（3周后）
- 存储层异步化完成
- 性能提升达到目标
- 降级机制验证通过

**M3: native_ipc集成完成**（5周后）
- 监控进程通信替换完成
- 跨进程同步实现完成
- 性能优于ZMQ

**M4: 优化和测试完成**（6周后）
- 所有优化完成
- 全面测试通过
- 文档完善

### 11.3 风险控制

#### 11.3.1 技术风险

**风险**：native_iocp编译失败
- **应对**：自动降级到aiofiles，保证功能正常

**风险**：native_ipc兼容性问题
- **应对**：保留ZMQ备用方案，确保通信正常

#### 11.3.2 进度风险

**风险**：某个阶段延期
- **应对**：预留1周缓冲时间，必要时调整优先级

**风险**：性能目标未达成
- **应对**：分阶段验证，及时调整优化方向

## 十二、风险评估与应对

### 12.1 技术风险

#### 12.1.1 native_iocp编译失败

**风险描述**：
- Windows环境缺少Visual Studio Build Tools
- Python开发头文件缺失
- 编译配置错误

**应对措施**：
1. **自动降级**：native_iocp不可用时自动降级到aiofiles
2. **文档完善**：提供详细的编译指南和故障排查
3. **预编译版本**：考虑提供预编译的wheel包（未来）

**影响评估**：
- **严重性**：低（有降级方案）
- **可能性**：中（需要编译环境）

#### 12.1.2 native_ipc兼容性问题

**风险描述**：
- Named Pipe权限问题
- 跨进程通信稳定性问题
- 性能未达预期

**应对措施**：
1. **备用方案**：保留ZMQ备用，确保通信正常
2. **权限检查**：启动时检查权限，自动处理
3. **稳定性测试**：充分测试各种场景

**影响评估**：
- **严重性**：中（有备用方案）
- **可能性**：低（已充分验证）

#### 12.1.3 异步化带来的复杂性

**风险描述**：
- 异步代码调试困难
- 异常处理复杂
- 性能问题定位困难

**应对措施**：
1. **完善的错误处理**：所有异步操作都有异常处理
2. **详细的日志**：记录关键异步操作
3. **性能监控**：监控异步操作的性能

**影响评估**：
- **严重性**：中（影响开发效率）
- **可能性**：中（异步代码复杂度高）

### 12.2 性能风险

#### 12.2.1 性能目标未达成

**风险描述**：
- I/O性能提升未达50-80%
- IPC延迟未优于ZMQ
- 总体性能未达预期

**应对措施**：
1. **分阶段验证**：每个阶段都进行性能测试
2. **及时调整**：未达预期时及时调整优化方向
3. **性能基准**：建立性能基准，持续监控

**影响评估**：
- **严重性**：低（有调整空间）
- **可能性**：低（已有初步验证）

#### 12.2.2 内存占用未降低

**风险描述**：
- 异步操作可能增加内存占用
- 缓存策略可能增加内存
- 总体内存未达预期

**应对措施**：
1. **内存监控**：实时监控内存占用
2. **缓存优化**：优化缓存策略，控制内存
3. **内存分析**：使用工具分析内存占用

**影响评估**：
- **严重性**：低（次要目标）
- **可能性**：中（异步可能增加内存）

### 12.3 进度风险

#### 12.3.1 某个阶段延期

**风险描述**：
- 核心重构延期
- native_iocp集成延期
- native_ipc集成延期

**应对措施**：
1. **预留缓冲**：每个阶段预留1周缓冲时间
2. **优先级调整**：必要时调整优先级
3. **并行开发**：可并行的工作并行开发

**影响评估**：
- **严重性**：低（有缓冲时间）
- **可能性**：中（重构工作量较大）

#### 12.3.2 测试时间不足

**风险描述**：
- 集成测试时间不足
- 性能测试时间不足
- 压力测试时间不足

**应对措施**：
1. **自动化测试**：编写自动化测试用例
2. **持续测试**：每个阶段都进行测试
3. **测试计划**：提前规划测试时间

**影响评估**：
- **严重性**：中（影响质量）
- **可能性**：中（测试工作量较大）

### 12.4 兼容性风险

#### 12.4.1 API兼容性问题

**风险描述**：
- 某些API行为改变
- 返回值格式改变
- 异常类型改变

**应对措施**：
1. **兼容性测试**：编写全面的兼容性测试
2. **文档对照**：对照旧文档验证API
3. **向后兼容**：所有同步API保持不变

**影响评估**：
- **严重性**：高（影响现有代码）
- **可能性**：低（已充分规划）

### 12.5 风险应对总结

| 风险类型 | 严重性 | 可能性 | 应对策略 |
|---------|-------|-------|---------|
| native_iocp编译失败 | 低 | 中 | 自动降级 |
| native_ipc兼容性问题 | 中 | 低 | 备用方案 |
| 异步化复杂性 | 中 | 中 | 完善文档和测试 |
| 性能未达目标 | 低 | 低 | 分阶段验证 |
| 内存占用未降低 | 低 | 中 | 内存监控和优化 |
| 阶段延期 | 低 | 中 | 预留缓冲 |
| 测试时间不足 | 中 | 中 | 自动化测试 |
| API兼容性问题 | 高 | 低 | 兼容性测试 |

---

## 十三、后续优化方向

### 13.1 短期优化（3-6个月）

#### 13.1.1 GPU加速验证

**目标**：使用GPU加速数据验证，提升验证性能。

**实现方案**：
- 集成CUDA或OpenCL
- 批量验证数据
- 性能提升：10-100倍（取决于数据量）

#### 13.1.2 分布式存储支持

**目标**：支持分布式数据存储，提升存储容量和性能。

**实现方案**：
- 支持多磁盘存储
- 自动数据分片
- 负载均衡存储

#### 13.1.3 实时流处理

**目标**：支持实时数据流处理，提升实时性。

**实现方案**：
- 流式数据处理
- 实时指标计算
- 事件流处理

### 13.2 中期优化（6-12个月）

#### 13.2.1 AI集成

**目标**：使用AI预测数据质量，提前发现问题。

**实现方案**：
- 数据质量预测模型
- 异常检测算法
- 自动修复建议

#### 13.2.2 云存储集成

**目标**：支持云存储，提升数据安全性。

**实现方案**：
- 支持阿里云OSS、腾讯云COS
- 自动备份和恢复
- 数据加密传输

#### 13.2.3 多市场支持

**目标**：支持更多市场的数据，扩展应用范围。

**实现方案**：
- 支持港股、美股
- 支持期货、期权
- 统一数据模型

### 13.3 长期优化（12+个月）

#### 13.3.1 微服务架构

**目标**：支持微服务架构，提升可扩展性。

**实现方案**：
- 服务拆分
- 独立部署
- 服务治理

#### 13.3.2 容器化部署

**目标**：支持容器化部署，提升部署效率。

**实现方案**：
- Docker镜像
- Kubernetes编排
- 自动化部署

#### 13.3.3 边缘计算支持

**目标**：支持边缘计算，提升响应速度。

**实现方案**：
- 边缘节点部署
- 数据就近处理
- 智能路由

---

## 十四、总结

### 14.1 核心改进

本次架构重构的核心改进包括：

1. **文件组织优化**：7个文件 → 6个核心文件，按业务领域组织
2. **全面异步化**：使用native_iocp真异步I/O，性能提升50-80%
3. **跨进程通信优化**：使用native_ipc替代ZMQ，延迟降低，吞吐量提升
4. **智能负载均衡增强**：增加事件循环延迟、I/O延迟、IPC延迟监控
5. **统一数据管理优化**：支持异步查询、批量预加载、智能缓存、跨进程同步
6. **事件驱动架构优化**：新增订阅事件，支持跨进程事件分发
7. **100%向后兼容**：所有现有API保持不变，新增异步版本

### 14.2 技术亮点

1. **真异步I/O**：使用Windows IOCP机制，无线程池开销
2. **真异步IPC**：使用Windows Named Pipe机制，无线程池开销
3. **智能负载均衡**：基于木桶理论的动态并发调整（只看最短的板，不是加权评分）
4. **四层数据融合**：内存+磁盘+录制+实时，智能查询
5. **AI Debug友好**：相关功能集中在单文件，清晰分区

### 14.3 性能目标

- **I/O性能**：提升50-80%
- **IPC性能**：延迟降低，吞吐量提升
- **响应延迟**：降低20-30%
- **内存占用**：降低10-15%

### 14.4 实施计划

- **总时长**：6周（含缓冲）
- **4个阶段**：核心重构、native_iocp集成、native_ipc集成、优化和测试
- **4个里程碑**：每个阶段一个里程碑

### 14.5 风险控制

- **技术风险**：自动降级、备用方案
- **性能风险**：分阶段验证、及时调整
- **进度风险**：预留缓冲、优先级调整
- **兼容性风险**：兼容性测试、向后兼容

---

**文档完成！**

本设计文档涵盖了data_module_vnpy新架构的所有关键设计细节，包括：
- 架构设计总览
- 核心文件详细设计
- native_iocp深度集成方案
- native_ipc深度集成方案
- 智能负载机制优化
- 统一数据管理器优化
- 事件驱动架构优化
- 文件组织优化
- 向后兼容性设计
- 性能目标与指标
- 实施计划
- 风险评估与应对
- 后续优化方向

本设计文档为v3.0架构重构提供了完整的技术指导。

---

**文档版本**: v3.0 (彻底重构版)
**创建日期**: 2025-01-02
**文档状态**: 已完成
**下一步**: 根据本设计文档进行实施

