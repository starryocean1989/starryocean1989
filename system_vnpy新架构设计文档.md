# -*- coding: utf-8 -*-
# system_vnpy 新架构设计文档 (Cursor版)

**版本**: v1.0 (全面重构版)
**创建日期**: 2025-11-02
**文档目标**: 提供高粒度、详细的新架构设计，覆盖所有技术细节和实施方案

> **📖 文档分工**：
> - **本文档**：专注于架构设计、技术选型、性能目标、组件设计
> - **业务细节文档**：专注于业务流程、规则细节、实现逻辑、算法描述、微观架构设计
>
> 两文档遵循单一事实原则，互相引用但不重复内容。

---

## 📋 目录

- [一、架构设计总览](#一架构设计总览)
- [二、核心文件设计](#二核心文件设计)
- [三、native_iocp深度集成方案](#三native_iocp深度集成方案)
- [四、native_ipc深度集成方案](#四native_ipc深度集成方案)
- [五、智能负载机制集成](#五智能负载机制集成)
- [六、统一日志系统集成](#六统一日志系统集成)
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
   - 优化Windows WMI接口使用

2. **编程语言**: Python 3.10+
   - 全面采用asyncio异步编程
   - 支持类型提示（Type Hints）
   - 兼容现有Python生态

3. **UI框架**: PySide6 (Qt6)
   - 事件驱动集成（EventEngine）
   - 异步UI更新（qasync）
   - 线程安全保证

4. **量化框架**: VnPy 4.x
   - 符合VnPy EventEngine标准
   - 事件驱动架构
   - 服务模型兼容

5. **日志系统**: 统一日志系统（LoggingHub）
   - 四层路由（场景→模块→阶段→全局）
   - AI日志支持
   - 进度节流

6. **底层机制**:
   - **智能负载机制**: 木桶理论评分，动态并发调整
   - **native_iocp机制**: 真异步文件I/O
   - **native_ipc机制**: 真异步跨进程通信（替代ZMQ）

#### 1.1.2 功能完整性约束

新架构必须保持当前system_vnpy的所有功能：

1. **系统监控**
   - 系统指标监控（CPU、内存、磁盘、网络）
   - 硬件传感器监控（温度、风扇、电压）
   - SMART硬盘健康监控
   - 网络带宽测试

2. **业务监控**
   - 业务指标采集（下载并发、事件队列深度、K线计算耗时）
   - 场景识别（批量下载、实时交易、策略回测等）
   - 瓶颈分析（基于木桶理论）

3. **进程监控**
   - 进程信息采集（PID、CPU、内存、线程数）
   - Top进程分析

4. **服务监控**
   - 服务健康检查（调用次数、成功率、响应时间）
   - 服务重启管理

5. **日志告警**
   - 日志分析（错误模式识别）
   - 告警生成（多级别、多渠道）
   - 告警推送（通过native_ipc）

6. **独立进程运行**
   - 与主进程隔离
   - 通过native_ipc通信
   - 父进程监控（父进程退出时自动退出）

#### 1.1.3 架构质量约束

1. **文件组织偏好**
   - 少文件数量：当前3个核心文件
   - 大文件规模：2000-7000行/文件
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
- 所有监控数据通过事件发布
- 事件分类：系统事件、硬件事件、瓶颈事件、告警事件、业务事件
- 事件数据包含完整的上下文信息
- 支持跨进程事件分发（通过native_ipc）

**架构图**：
```
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  SystemMonitor  │──Publish→│  EventEngine   │←──Subscribe──│   UI Layer     │
└─────────────────┘      └─────────────────┘      └─────────────────┘
        │                        │                        │
        │                        │                        │
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│ HardwareMonitor │──Publish→│  EventEngine   │←──Subscribe──│ SystemManager  │
└─────────────────┘      └─────────────────┘      └─────────────────┘
        │                        │                        │
        │                        │                        │
┌─────────────────┐      ┌─────────────────┐      ┌─────────────────┐
│  SmartMonitor   │──Publish→│  EventEngine   │←──Subscribe──│  AlertEngine   │
└─────────────────┘      └─────────────────┘      └─────────────────┘
```

#### 1.2.2 异步优先原则

**原则描述**：全面使用asyncio，关键路径使用native_iocp/native_ipc。

**实现要点**：
- 所有I/O操作使用async/await
- 文件读写使用native_iocp（真异步，无线程池）
- 跨进程通信使用native_ipc（真异步，无线程池）
- 阻塞操作使用线程池隔离（WMI、psutil）

**异步化层次**：
```
Level 1: 同步I/O（旧代码，仅限WMI/psutil不可避免的阻塞调用）
Level 2: asyncio + 线程池（过渡方案，用于阻塞API隔离）
Level 3: asyncio + native_iocp（配置文件、日志文件、缓存文件）
Level 4: asyncio + native_ipc（跨进程通信）
```

#### 1.2.3 智能负载均衡

**原则描述**：基于木桶理论的动态资源调度。

**实现要点**：
- 实时监控系统资源（CPU占用、内存占用、磁盘IO）
- **木桶理论**：只关注最短的那块板，系统性能 = min(CPU使用率, 内存使用率, 磁盘IO使用率)
- 动态调整监控频率（降级策略）
- **防抖机制**：智能防抖，避免频繁调整

**负载均衡流程图**：
```
系统压力检测
    ↓
LoadBalancer评估
    ↓
获取系统资源指标（ResourceMonitor）
    ↓
计算压力评分（木桶理论）
    ↓
调整监控频率（降低采样率）
    ↓
监控任务执行（MonitoringProcessV2）
```

#### 1.2.4 独立进程隔离

**原则描述**：监控进程独立运行，避免影响主进程。

**实现要点**：
- 监控进程独立启动（替代当前ZMQ方案）
- 通过native_ipc通信
- 告警数据推送（alert_pipe）
- 状态同步（status_pipe）
- 查询响应（query_pipe）
- 父进程监控（父进程退出时自动退出）

**进程架构图**：
```
┌─────────────────────────┐
│      主进程              │
│   (Main Process)        │
│                         │
│ - MainEngine            │
│ - UI Services           │
│ - EventEngine           │
└────────┬────────────────┘
         │ native_ipc
         │ (AsyncIPCPipe × 3)
         ↓
┌─────────────────────────┐
│     监控进程             │
│  (Monitor Process)      │
│                         │
│ - SystemMonitor         │
│ - HardwareMonitor       │
│ - AlertEngine           │
│ - BottleneckAnalyzer    │
└─────────────────────────┘
```

#### 1.2.5 AI Debug友好

**原则描述**：相关功能集中在单文件，清晰分区。

**实现要点**：
- 按业务领域组织文件（而非技术层次）
- 每个文件使用Part分区标记
- 相关类和函数放在同一Part
- 避免过多的跨文件跳转

**文件分区示例**：
```python
# ==============================================================================
# Part 1: 阈值管理与硬件监控工厂
# ==============================================================================
class AdaptiveThresholdManager:
    ...

# ==============================================================================
# Part 2: 系统瓶颈分析与场景识别
# ==============================================================================
class SystemBottleneckAnalyzer:
    ...
```

### 1.3 新文件组织结构

#### 1.3.1 文件结构对比

**当前架构（v0.50）**：
```
system_vnpy/
├── __init__.py
├── system_toolkit.py (2233行)        # 工具包（管理员权限+错误计数器+事件定义+SMART监控）
├── monitor_system.py (6544行)        # 监控系统（监控进程+分析器+监控器）
├── unified_log_system.py (1409行)   # 日志系统（四层路由+AI日志）
├── config/
│   ├── speedtest_servers.yaml        # 网络测速配置
│   ├── rules_global.yaml             # 全局日志规则
│   ├── rules_stage.yaml              # 阶段日志规则
│   ├── rules_module.yaml             # 模块日志规则
│   └── rules_scenario.yaml           # 场景日志规则
└── 系统监控完整集成指南.md
```

**新架构（v1.0）**：
```
system_vnpy/
├── __init__.py                        # API统一导出（~200行）
├── core_engine.py                     # 核心引擎+配置+事件（~3000行）
├── monitor_system.py                  # 监控系统+分析器（~6000行）
├── monitor_toolkit.py                 # 监控工具集+SMART（~2500行）
├── config/
│   ├── system_config.yaml             # 系统监控配置
│   ├── threshold_config.yaml          # 阈值配置
│   ├── speedtest_servers.yaml         # 网络测速配置
│   ├── rules_global.yaml              # 全局日志规则
│   ├── rules_stage.yaml               # 阶段日志规则
│   ├── rules_module.yaml              # 模块日志规则
│   └── rules_scenario.yaml            # 场景日志规则
└── requirements.txt                   # Python依赖
```

**变化说明**：
- 文件数：3个核心 → 3个核心（保持不变）
- 重构策略：
  - `system_toolkit.py` → 拆分为 `core_engine.py` 和 `monitor_toolkit.py`（按职责拆分）
  - `monitor_system.py` → 保留并优化（监控核心）
  - `unified_log_system.py` → 移除（使用项目统一日志系统）
- 文件规模：每个文件2500-6000行，便于AI Debug
- 新增配置文件：system_config.yaml、threshold_config.yaml（增强可配置性）

#### 1.3.2 文件职责划分

| 文件 | 核心职责 | 包含组件 | 代码行数 |
|------|---------|---------|---------|
| `core_engine.py` | 核心引擎与基础设施 | SystemManagerEngine, ConfigManager, EventPublisher系列, CacheManager, EngineRegistry | ~3000行 |
| `monitor_system.py` | 监控系统与分析 | MonitoringProcessV2, SystemMonitor, HardwareMonitor, BottleneckAnalyzer, ScenarioAnalyzer, AlertEngine | ~6000行 |
| `monitor_toolkit.py` | 监控工具集 | SmartMonitor, BandwidthMonitor, ServiceHealthChecker, LogAnalyzer, PerformanceAnalyzer, 管理员权限工具 | ~2500行 |

---

## 二、核心文件设计

### 2.1 core_engine.py - 核心引擎与基础设施

#### 2.1.1 文件定位

**核心职责**：整个监控模块的中枢，提供统一入口和基础设施服务。

**设计原则**：
- 引擎作为唯一对外接口，协调所有功能组件
- 基础设施组件（配置、事件、缓存）集中管理
- 保持轻量级，不包含业务逻辑

#### 2.1.2 组件清单

**Part 1: 配置管理（ConfigManager）**
- 功能：统一配置管理，路径自动标准化
- 用途：所有模块的配置访问
- 实现：单例模式，配置热更新支持，类型转换

**Part 2: 缓存管理（CacheManager）**
- 功能：监控数据缓存
- 用途：系统指标缓存、测速结果缓存
- 实现：TTL缓存，自动清理

**Part 3: 事件系统（EventPublisher系列）**
- 功能：分类事件发布
- 包含：
  - `EventPublisher`：通用事件发布
  - `SystemEventPublisher`：系统监控事件
  - `HardwareEventPublisher`：硬件监控事件
  - `AlertEventPublisher`：告警事件
  - `BusinessEventPublisher`：业务监控事件

**Part 4: 引擎注册表（EngineRegistry）**
- 功能：管理所有子引擎实例
- 用途：统一生命周期管理
- 实现：单例模式，延迟初始化

**Part 5: 核心引擎（SystemManagerEngine）**
- 功能：整个模块的统一入口
- 职责：
  - 初始化所有子组件
  - 提供统一API接口
  - 协调组件间交互
  - 健康检查和状态管理
  - 启动/停止监控进程

#### 2.1.3 详细设计

##### Part 1: 配置管理（ConfigManager）

**类设计**：
```python
class ConfigManager:
    """统一配置管理"""

    _instance: Optional["ConfigManager"] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._config_file: Path = Path(__file__).parent / "config" / "system_config.yaml"
        self._threshold_file: Path = Path(__file__).parent / "config" / "threshold_config.yaml"
        self._load_config()

    @classmethod
    def get_instance(cls) -> "ConfigManager":
        """获取单例实例"""
        ...

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        ...

    def get_threshold_config(self) -> Dict[str, Any]:
        """获取阈值配置"""
        ...

    async def reload_config_async(self) -> bool:
        """异步重新加载配置（使用native_iocp）"""
        ...
```

**native_iocp集成点**：
- **核心**：配置文件的异步读写
- 实现：使用`compat_aopen`进行异步文件操作
- 降级：native_iocp不可用时使用`aiofiles`

**native_ipc集成点**：
- **核心**：配置热更新的跨进程通知
- 实现：当配置更新时，通过native_ipc通知监控进程

##### Part 2: 缓存管理（CacheManager）

**类设计**：
```python
class CacheManager:
    """监控数据缓存管理"""

    @staticmethod
    def save_monitor_data(data: Any, cache_key: str, ttl: int = 300) -> bool:
        """保存监控数据"""
        ...

    @staticmethod
    async def save_monitor_data_async(data: Any, cache_key: str, ttl: int = 300) -> bool:
        """异步保存监控数据（使用native_iocp）"""
        ...

    @staticmethod
    def load_monitor_data(cache_key: str) -> Tuple[Any, bool]:
        """加载监控数据，返回(数据, 是否有效)"""
        ...

    @staticmethod
    async def load_monitor_data_async(cache_key: str) -> Tuple[Any, bool]:
        """异步加载监控数据（使用native_iocp）"""
        ...
```

**native_iocp集成点**：
- **核心**：所有缓存文件的异步读写
- 实现：使用`compat_aopen`进行异步文件操作

##### Part 3: 事件系统（EventPublisher系列）

**类设计**：
```python
class EventPublisher:
    """通用事件发布器"""

    def __init__(self, event_engine: EventEngine):
        self.event_engine = event_engine

    def publish(self, event_type: str, data: Any) -> None:
        """发布事件"""
        event = Event(event_type, data)
        self.event_engine.put(event)

class SystemEventPublisher(EventPublisher):
    """系统监控事件发布器"""

    EVENT_SYSTEM_METRICS = "eSystemMetrics"
    EVENT_RESOURCE_USAGE = "eResourceUsage"

    def publish_system_metrics(self, metrics: Dict) -> None:
        """发布系统指标"""
        self.publish(self.EVENT_SYSTEM_METRICS, metrics)

class HardwareEventPublisher(EventPublisher):
    """硬件监控事件发布器"""

    EVENT_HARDWARE_SENSORS = "eHardwareSensors"
    EVENT_SMART_DATA = "eSmartData"

    def publish_hardware_sensors(self, sensors: Dict) -> None:
        """发布硬件传感器数据"""
        self.publish(self.EVENT_HARDWARE_SENSORS, sensors)

class AlertEventPublisher(EventPublisher):
    """告警事件发布器"""

    EVENT_ALERT_CREATED = "eAlertCreated"
    EVENT_ALERT_UPDATED = "eAlertUpdated"

    def publish_alert_created(self, alert: Dict) -> None:
        """发布告警创建事件"""
        self.publish(self.EVENT_ALERT_CREATED, alert)
```

**native_ipc集成点**：
- **核心**：跨进程事件分发
- 实现：通过native_ipc将事件转发到监控进程

##### Part 5: 核心引擎（SystemManagerEngine）

**类设计**：
```python
class SystemManagerEngine:
    """系统管理引擎（核心引擎）"""

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine):
        self.main_engine = main_engine
        self.event_engine = event_engine

        # 初始化配置管理
        self.config_manager = ConfigManager.get_instance()

        # 初始化事件发布器
        self.system_publisher = SystemEventPublisher(event_engine)
        self.hardware_publisher = HardwareEventPublisher(event_engine)
        self.alert_publisher = AlertEventPublisher(event_engine)

        # 监控进程引用
        self.monitor_process: Optional[subprocess.Popen] = None
        self._ipc_pipes: Dict[str, AsyncIPCPipe] = {}

        # 状态管理
        self._is_ready: bool = False
        self._initialization_lock: threading.Lock = threading.Lock()

    def initialize(self) -> bool:
        """初始化引擎"""
        ...

    async def start_monitoring_process(self) -> bool:
        """启动监控进程"""
        ...

    async def stop_monitoring_process(self) -> bool:
        """停止监控进程"""
        ...

    async def query_monitor_data(self, query_type: str) -> Optional[Dict]:
        """查询监控数据"""
        ...

    # API接口（保持100%向后兼容）
    def get_system_info(self) -> Dict[str, Any]:
        """获取系统信息"""
        ...

    def test_bandwidth(self) -> Dict[str, Any]:
        """测试网络带宽"""
        ...

    def healthcheck(self) -> Dict[str, Any]:
        """健康检查"""
        ...
```

**native_ipc集成点**：
- **核心**：与监控进程的所有通信
- 实现：
  - `alert_pipe`: 接收告警推送（服务端模式）
  - `status_pipe`: 发送状态更新（客户端模式）
  - `query_pipe`: 发送查询请求并接收响应（客户端模式）

### 2.2 monitor_system.py - 监控系统与分析

> **业务规则参考**：监控规则、阈值管理、瓶颈分析等业务逻辑请参考 [业务细节文档](./system_vnpy新架构业务细节文档.md)

#### 2.2.1 文件定位

**核心职责**：负责所有监控功能，包括系统监控、硬件监控、分析、告警。

**设计原则**：
- 独立进程运行
- 混合并发架构（asyncio + 线程池）
- 智能负载均衡集成
- 详细的日志和统计

#### 2.2.2 组件清单（保持当前架构）

**Part 0: 网络测速模块（NetworkSpeedTester）**
- 功能：基于公共测速站点的纯Python网络测速
- 特性：无第三方依赖、随机重试、超时保护

**Part 1: 阈值管理与硬件监控工厂**
- AdaptiveThresholdManager：自适应阈值管理
- HardwareMonitorFactory：硬件监控工厂

**Part 2: 系统瓶颈分析与场景识别**
- SystemBottleneckAnalyzer：系统瓶颈分析
- ScenarioAnalyzer：场景识别与优化建议

**Part 3: 监控进程V2**
- MonitoringProcessV2：混合并发监控进程
- SystemMonitor：系统监控器
- ResourceMonitor：资源监控器
- ProcessMonitor：进程监控器
- HardwareMonitor：硬件监控器
- BandwidthMonitor：带宽监控器
- BusinessMetricsCollector：业务指标采集器

**Part 4: 独立进程入口**
- main()：独立进程启动入口

#### 2.2.3 优化点

**原架构保留**：
- 混合并发架构（asyncio + 线程池）
- 四个并发任务（系统监控、进程监控、硬件监控、告警评估）
- native_ipc通信（三条管道）
- 两阶段就绪模型

**新增优化**：
- 智能负载均衡集成（动态调整监控频率）
- native_iocp日志写入（提升日志性能）
- 统一日志系统集成（四层路由）
- 配置文件化（阈值配置、监控配置）

### 2.3 monitor_toolkit.py - 监控工具集

#### 2.3.1 文件定位

**核心职责**：提供监控相关的工具类和辅助功能。

**设计原则**：
- 工具类独立性强
- 可单独测试
- 支持同步和异步接口

#### 2.3.2 组件清单

**Part 1: 管理员权限工具**
- is_admin()：检查管理员权限
- run_as_admin()：以管理员身份重启
- ensure_admin()：确保管理员权限
- check_admin_for_hardware_monitoring()：硬件监控权限检查

**Part 2: 错误计数器**
- ErrorCounter：周期性错误计数器（单例）

**Part 3: SMART监控**
- WMISmartMonitor：WMI SMART监控器
- SmartMonitor：SMART告警包装器
- DiskSmartData：SMART数据结构
- SmartAttribute：SMART属性

**Part 4: 服务工具**
- ServiceHealthChecker：服务健康检查
- ServiceRestarter：服务重启管理

**Part 5: 性能分析**
- PerformanceAnalyzer：性能瓶颈分析
- LogAnalyzer：日志分析

**Part 6: 网络工具**
- NetworkTester：网络连通性测试
- PortScanner：端口扫描

---

## 三、native_iocp深度集成方案

### 3.1 集成目标

**核心目标**：
- 所有配置文件读写使用native_iocp
- 所有缓存文件读写使用native_iocp
- 所有日志文件写入使用native_iocp
- 提升I/O性能50-80%

### 3.2 集成点清单

#### 3.2.1 配置文件读写

**文件列表**：
- `config/system_config.yaml`：系统配置
- `config/threshold_config.yaml`：阈值配置
- `config/speedtest_servers.yaml`：测速配置

**实现方式**：
```python
from backend.infrastructure.native_iocp import compat_aopen

async def load_config_async(config_file: Path) -> Dict:
    """异步加载配置文件"""
    async with await compat_aopen(config_file, 'r', encoding='utf-8') as f:
        content = await f.read()
        return yaml.safe_load(content)
```

#### 3.2.2 缓存文件读写

**缓存类型**：
- 系统指标缓存
- 带宽测试结果缓存
- SMART数据缓存

**实现方式**：
```python
async def save_cache_async(data: Any, cache_key: str) -> bool:
    """异步保存缓存"""
    cache_file = Path("cache") / f"{cache_key}.json"
    async with await compat_aopen(cache_file, 'w', encoding='utf-8') as f:
        await f.write(json.dumps(data, ensure_ascii=False, indent=2))
    return True
```

#### 3.2.3 日志文件写入

**日志类型**：
- 监控进程日志
- 告警日志
- 性能统计日志

**实现方式**：
```python
# 使用统一日志系统，底层自动使用native_iocp
logger.info("监控数据已采集")
```

### 3.3 降级策略

**降级条件**：
- native_iocp模块不可用
- 文件操作失败

**降级方案**：
```python
try:
    from backend.infrastructure.native_iocp import compat_aopen, IOCP_AVAILABLE
    if IOCP_AVAILABLE:
        # 使用native_iocp
        async with await compat_aopen(file_path, 'r') as f:
            ...
except ImportError:
    # 降级到aiofiles
    import aiofiles
    async with aiofiles.open(file_path, 'r') as f:
        ...
```

---

## 四、native_ipc深度集成方案

### 4.1 集成目标

**核心目标**：
- 替代当前ZMQ通信方案
- 提供三条异步管道（告警、状态、查询）
- 支持主进程与监控进程双向通信
- 降低通信延迟至1-2ms

### 4.2 管道设计

#### 4.2.1 告警管道（alert_pipe）

**方向**：监控进程 → 主进程
**模式**：客户端模式（监控进程主动推送）
**数据格式**：
```python
{
    "type": "alert",
    "level": "WARNING|ERROR|CRITICAL",
    "category": "system|hardware|smart|business",
    "message": "告警消息",
    "details": {...},
    "timestamp": "2025-11-02T10:00:00"
}
```

**实现**：
```python
# 监控进程侧
async def send_alert(alert_data: Dict):
    pipe_name = "monitor_alerts"
    async with await AsyncIPCPipe.connect_as_client(pipe_name) as pipe:
        await pipe.write_json(alert_data)
```

#### 4.2.2 状态管道（status_pipe）

**方向**：主进程 → 监控进程
**模式**：服务端模式（监控进程接收）
**数据格式**：
```python
{
    "type": "status_update",
    "service": "data_center|trading_gateway|...",
    "status": "online|offline|degraded",
    "metrics": {...},
    "timestamp": "2025-11-02T10:00:00"
}
```

**实现**：
```python
# 监控进程侧
async def receive_status_updates():
    pipe_name = "monitor_status"
    async with await AsyncIPCPipe.create_as_server(pipe_name) as pipe:
        while True:
            data = await pipe.read_json()
            process_status_update(data)
```

#### 4.2.3 查询管道（query_pipe）

**方向**：主进程 ↔ 监控进程
**模式**：服务端模式（监控进程响应查询）
**查询格式**：
```python
{
    "action": "get_system|get_hardware|get_smart|test_bandwidth|...",
    "params": {...}
}
```

**响应格式**：
```python
{
    "status": "success|error",
    "data": {...},
    "error": "错误信息（如有）",
    "timestamp": "2025-11-02T10:00:00"
}
```

**实现**：
```python
# 监控进程侧
async def handle_queries():
    pipe_name = "monitor_query"
    async with await AsyncIPCPipe.create_as_server(pipe_name) as pipe:
        while True:
            query = await pipe.read_json()
            response = process_query(query)
            await pipe.write_json(response)
```

### 4.3 通信协议

#### 4.3.1 消息格式

**JSON格式**（默认）：
- 适用于绝大多数场景
- 自动序列化/反序列化
- 支持嵌套结构

**二进制格式**（可选）：
- 适用于大数据量传输
- 使用msgpack序列化
- 性能提升30-50%

#### 4.3.2 错误处理

**超时机制**：
- 查询超时：5秒
- 告警推送超时：3秒
- 状态更新超时：3秒

**重试机制**：
- 查询失败：重试3次
- 告警推送失败：丢弃（记录日志）
- 状态更新失败：丢弃（记录日志）

**异常处理**：
```python
try:
    async with await AsyncIPCPipe.connect_as_client(pipe_name, timeout=5.0) as pipe:
        await pipe.write_json(data)
except IPCTimeout:
    logger.warning("IPC通信超时")
except IPCError as e:
    logger.error(f"IPC通信失败: {e}")
```

---

## 五、为智能负载均衡模块提供监控数据

### 5.1 数据提供目标

**核心定位**：
- 系统监控模块是**数据提供者**（Provider），不是数据消费者（Consumer）
- 以固定高频采集系统指标，保证监控数据的稳定性和可靠性
- 通过事件引擎发布监控数据，供LoadBalancer等模块消费
- **禁止**根据系统压力动态调整监控频率（会导致监控数据质量下降）

**设计原则**：
- ✅ 固定采集频率：系统指标1秒、硬件传感器5秒、SMART 60秒
- ✅ 用户可配置：通过配置文件调整采集频率（但运行时不动态变化）
- ✅ 底层优先级：监控开销必须<2% CPU，<100MB内存
- ✅ 独立进程运行：不受主进程业务压力影响
- ❌ 不使用智能负载均衡：避免形成负反馈循环

### 5.2 事件发布机制

**发布频率**（固定）：
- `EVENT_SYSTEM_METRICS`：每1秒发布一次（CPU、内存、磁盘、网络）
- `EVENT_HARDWARE_SENSORS`：每5秒发布一次（温度、风扇、功耗）
- `EVENT_BOTTLENECK_ANALYSIS`：每3秒发布一次（瓶颈分析结果）
- `EVENT_SMART_DATA`：每60秒发布一次（SMART硬盘健康数据）

**事件数据格式**：
```python
# EVENT_SYSTEM_METRICS 数据格式
{
    "cpu_percent": 45.2,
    "memory_percent": 60.5,
    "disk_io_read_mb_s": 10.5,
    "disk_io_write_mb_s": 8.3,
    "network_sent_mb_s": 2.1,
    "network_recv_mb_s": 5.6,
    "timestamp": 1234567890.123
}
```

### 5.3 与LoadBalancer的交互

**数据流向**：
```
┌─────────────────────┐
│  MonitoringProcess  │ (独立进程，固定1秒采集)
│  - 系统指标: 1秒    │
│  - 硬件传感器: 5秒  │
│  - CPU开销 < 2%    │
└──────────┬──────────┘
           │
           │ EVENT_SYSTEM_METRICS (每1秒发布)
           │ EVENT_HARDWARE_SENSORS (每5秒发布)
           ↓
┌─────────────────────┐
│    EventEngine      │
└──────────┬──────────┘
           │
           ├─→ UI层（显示监控数据）
           │
           ├─→ LoadBalancer（木桶理论评估）
           │   ↓
           │   动态调整业务并发数 ← 调整的是业务，不是监控！
           │   ├─→ DataCenter下载并发
           │   ├─→ 策略执行并发
           │   └─→ 其他业务模块并发
           │
           └─→ AlertEngine（生成告警）
```

**LoadBalancer如何使用监控数据**：
```python
class LoadBalancer:
    """智能负载均衡器（消费监控数据）"""
    
    def __init__(self, event_engine: EventEngine):
        self.event_engine = event_engine
        self._latest_system_metrics: Optional[Dict] = None
        
        # 订阅系统监控事件
        self.event_engine.register(EVENT_SYSTEM_METRICS, self._on_system_metrics)
    
    def _on_system_metrics(self, event: Event):
        """接收系统监控数据"""
        self._latest_system_metrics = event.data
    
    def get_optimal_config(self, task: Task) -> Dict[str, int]:
        """根据系统状态计算最优配置（调整业务并发，不是监控频率）"""
        if not self._latest_system_metrics:
            return self._get_default_config(task)
        
        # 使用木桶理论评估系统压力
        pressure_score = self._calculate_pressure_score(self._latest_system_metrics)
        
        # 根据压力动态调整业务并发数
        if pressure_score < 40:
            # 系统压力大，降低业务并发
            return {"max_workers": 4, "max_coroutines": 500}
        elif pressure_score < 60:
            return {"max_workers": 8, "max_coroutines": 1000}
        else:
            # 系统压力小，提高业务并发
            return {"max_workers": 16, "max_coroutines": 2000}
    
    def _calculate_pressure_score(self, metrics: Dict) -> float:
        """计算系统压力评分（木桶理论：取最小值）"""
        cpu_score = 100 - metrics.get("cpu_percent", 0)
        memory_score = 100 - metrics.get("memory_percent", 0)
        disk_io = metrics.get("disk_io_read_mb_s", 0) + metrics.get("disk_io_write_mb_s", 0)
        disk_score = max(0, 100 - (disk_io / 500 * 100))
        
        # 木桶理论：取最短板
        return min(cpu_score, memory_score, disk_score)
```

### 5.4 监控频率配置规则

**配置文件**：`config/system_config.yaml`

```yaml
monitoring:
  # 采集频率配置（固定或用户配置，不动态调整）
  intervals:
    system_metrics: 1        # 系统指标采集间隔（秒）
    process_metrics: 2       # 进程指标采集间隔（秒）
    hardware_sensors: 5      # 硬件传感器采集间隔（秒）
    smart_data: 60          # SMART数据采集间隔（秒）
    alert_evaluation: 3      # 告警评估间隔（秒）
  
  # 性能限制（保证监控开销可控）
  performance:
    max_cpu_percent: 2.0     # 最大CPU占用（%）
    max_memory_mb: 100       # 最大内存占用（MB）
    max_io_mb_s: 5          # 最大磁盘I/O（MB/s）
```

**预设模式**（用户可选）：

| 模式 | system_metrics | hardware_sensors | 说明 |
|-----|----------------|------------------|------|
| 高频 | 1秒 | 5秒 | 默认模式，精确监控 |
| 标准 | 2秒 | 10秒 | 平衡模式 |
| 省资源 | 5秒 | 20秒 | 降低监控开销 |

**配置热更新支持**：
- 用户在UI修改配置
- 通过IPC通知监控进程
- 监控进程重新加载配置
- 下一个采集周期生效（不影响当前周期）

---

## 六、统一日志系统集成

### 6.1 集成目标

**核心目标**：
- 所有日志通过LoggingHub路由
- 支持四层路由（场景→模块→阶段→全局）
- AI日志支持
- 进度节流

### 6.2 日志分类

**日志类型**：
- `SYSTEM`：系统日志
- `PROGRESS`：进度日志
- `NOTIFICATION`：通知日志
- `ALERT`：告警日志
- `DEBUG`：调试日志

**模块标识**：
- `system_manager`：系统管理模块

**场景标识**：
- `monitoring`：监控场景
- `bandwidth_test`：带宽测试场景

### 6.3 路由规则

**四层路由**：
1. **场景规则**：`scenario_monitoring`
2. **模块规则**：`module_system_manager`
3. **阶段规则**：`stage_running`
4. **全局规则**：`global_defaults`

**输出目标**：
- `console`：控制台输出
- `file`：日志文件
- `event`：事件引擎
- `ipc_alerts`：IPC告警推送

---

## 七、事件驱动架构优化

### 7.1 事件类型定义

**系统监控事件**：
- `EVENT_SYSTEM_METRICS`：系统指标
- `EVENT_HARDWARE_SENSORS`：硬件传感器
- `EVENT_BOTTLENECK_ANALYSIS`：瓶颈分析
- `EVENT_SMART_DATA`：SMART数据

**告警事件**：
- `EVENT_ALERT_CREATED`：告警创建
- `EVENT_ALERT_UPDATED`：告警更新

**业务事件**：
- `EVENT_BUSINESS_METRICS`：业务指标

### 7.2 事件发布

**发布方式**：
```python
# 系统指标事件
self.system_publisher.publish_system_metrics({
    "cpu_percent": 45.2,
    "memory_percent": 60.5,
    ...
})

# 告警事件
self.alert_publisher.publish_alert_created({
    "level": "WARNING",
    "category": "smart",
    "message": "硬盘温度过高",
    ...
})
```

### 7.3 事件订阅

**订阅方式**：
```python
# UI层订阅
self.event_engine.register(EVENT_SYSTEM_METRICS, self.on_system_metrics)

def on_system_metrics(self, event: Event):
    """处理系统指标事件"""
    metrics = event.data
    self.update_ui(metrics)
```

---

## 八、文件组织优化

### 8.1 Part分区规范

**分区原则**：
- 每个Part专注一个功能域
- Part之间耦合度低
- Part内聚合度高

**分区示例**：
```python
# ==============================================================================
# Part 1: 阈值管理与硬件监控工厂
# ==============================================================================

class AdaptiveThresholdManager:
    ...

class HardwareMonitorFactory:
    ...

# ==============================================================================
# Part 2: 系统瓶颈分析与场景识别
# ==============================================================================

class SystemBottleneckAnalyzer:
    ...

class ScenarioAnalyzer:
    ...
```

### 8.2 导入规范

**导入顺序**：
1. 标准库导入
2. 第三方库导入
3. 项目内导入
4. 相对导入

**导入示例**：
```python
# 标准库
import asyncio
import logging
from typing import Dict, List, Optional

# 第三方库
import psutil

# 项目内导入
from backend.core.base import MainEngine
from backend.infrastructure.native_iocp import compat_aopen

# 相对导入
from .monitor_toolkit import SmartMonitor
```

---

## 九、向后兼容性

### 9.1 API兼容性

**保持100%兼容**：
- 所有公开API签名保持不变
- 新增API不破坏现有调用

**兼容示例**：
```python
# 旧API（同步）
def get_system_info(self) -> Dict[str, Any]:
    """获取系统信息（同步版本，向后兼容）"""
    return asyncio.run(self.get_system_info_async())

# 新API（异步）
async def get_system_info_async(self) -> Dict[str, Any]:
    """获取系统信息（异步版本）"""
    ...
```

### 9.2 配置兼容性

**配置迁移**：
- 自动检测旧配置格式
- 自动转换为新格式
- 保留旧配置作为备份

### 9.3 数据兼容性

**数据格式兼容**：
- 事件数据格式保持不变
- 缓存数据格式兼容
- 日志格式兼容

---

## 十、性能目标与指标

### 10.1 性能目标

**I/O性能**：
- 配置文件读取：提升50-80%（native_iocp）
- 缓存文件读写：提升50-80%（native_iocp）
- 日志文件写入：提升30-50%（native_iocp）

**通信性能**：
- IPC通信延迟：< 2ms（native_ipc）
- 事件分发延迟：< 1ms

**监控性能**：
- 系统监控开销：< 2% CPU
- 硬件监控开销：< 1% CPU
- 内存占用：< 100MB

### 10.2 性能指标

**监控指标**：
```python
{
    "monitoring_overhead": {
        "cpu_percent": 1.5,
        "memory_mb": 85,
        "ipc_latency_ms": 1.2
    },
    "io_performance": {
        "config_load_ms": 15,
        "cache_write_ms": 8,
        "log_write_ms": 5
    }
}
```

---

## 十一、实施计划

### 11.1 实施阶段

**阶段1：核心重构（1周）**
- 创建新文件结构
- 实现ConfigManager、CacheManager
- 实现SystemManagerEngine框架

**阶段2：native_iocp集成（3天）**
- 配置文件异步读写
- 缓存文件异步读写
- 性能测试和优化

**阶段3：native_ipc集成（5天）**
- 实现三条管道通信
- 监控进程改造
- 通信测试和优化

**阶段4：智能负载集成（2天）**
- 实现负载评估
- 实现动态调整
- 压力测试

**阶段5：测试与验证（3天）**
- 单元测试
- 集成测试
- 性能测试
- 兼容性测试

### 11.2 里程碑

- M1：核心框架完成
- M2：native_iocp集成完成
- M3：native_ipc集成完成
- M4：所有功能完成
- M5：测试通过，正式发布

---

## 十二、风险评估与应对

### 12.1 技术风险

**风险1：native_iocp兼容性问题**
- 概率：中
- 影响：高
- 应对：实现降级方案（aiofiles）

**风险2：native_ipc稳定性问题**
- 概率：中
- 影响：高
- 应对：保留ZMQ作为备选方案

**风险3：性能达不到预期**
- 概率：低
- 影响：中
- 应对：逐步优化，分阶段发布

### 12.2 业务风险

**风险1：功能遗漏**
- 概率：中
- 影响：高
- 应对：详细的业务规则文档，逐项验证

**风险2：兼容性问题**
- 概率：低
- 影响：高
- 应对：完整的兼容性测试

---

## 十三、后续优化方向

### 13.1 短期优化

- GPU加速（SMART数据分析）
- 机器学习（异常检测）
- 预测性告警

### 13.2 长期优化

- 分布式监控
- 云端集成
- 可视化增强
