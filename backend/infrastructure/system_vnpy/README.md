# System VnPy 监控模块

> **版本**: v0.50
> **架构**: 监控进程V2 + 事件驱动
> **更新**: 2025-10-23

---

## 📋 目录

- [模块概述](#模块概述)
- [架构设计](#架构设计)
- [文件组织](#文件组织)
- [核心功能](#核心功能)
- [快速开始](#快速开始)
- [使用指南](#使用指南)
- [LibreHardwareMonitor 安装](#librehardwaremonitor-安装)
- [API 接口](#api-接口)
- [故障排除](#故障排除)
- [开发指南](#开发指南)

---

## 模块概述

**System VnPy** 是量化交易终端的系统监控模块，提供全面的硬件和业务性能监控能力。

### 主要特性

✅ **独立监控进程** - 避免影响主进程性能
✅ **混合并发架构** - asyncio + 线程池，高效采集
✅ **事件驱动通信** - 基于VNpy EventEngine，低延迟推送
✅ **智能分析引擎** - 瓶颈识别、场景分析、自适应阈值
✅ **硬件深度监控** - CPU温度、SMART健康、传感器数据
✅ **业务指标采集** - 量化场景专用指标统计
✅ **ZMQ通信** - 可靠的进程间数据传输

### 适用场景

- 🎯 量化交易系统性能监控
- 🎯 硬件健康状态跟踪
- 🎯 系统瓶颈诊断与优化
- 🎯 业务指标统计与分析

---

## 架构设计

### 进程架构

```
┌──────────────────────────────────────────────────────────────┐
│                       主进程 (Main Process)                   │
│  ┌────────────────────────────────────────────────────────┐  │
│  │           SystemManagerService (Backend)                │  │
│  │  • 管理监控进程生命周期                                 │  │
│  │  • 通过ZMQ查询监控数据                                  │  │
│  │  • 推送事件到EventEngine                                │  │
│  └────────────────┬────────────────────────────────────────┘  │
│                   │ ZMQ (REQ/REP)                             │
│                   ▼                                            │
│  ┌────────────────────────────────────────────────────────┐  │
│  │            SystemManagerView (Frontend UI)              │  │
│  │  • 订阅监控事件                                         │  │
│  │  • 实时更新UI组件                                       │  │
│  │  • 显示图表和统计                                       │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
                          ▲
                          │ ZMQ (tcp://127.0.0.1:5557)
                          ▼
┌──────────────────────────────────────────────────────────────┐
│                  监控进程 (Monitor Process)                   │
│  ┌────────────────────────────────────────────────────────┐  │
│  │       MonitoringProcessV2 (monitor_core.py)             │  │
│  │  • asyncio 事件循环（ZMQ通信、快速指标）                │  │
│  │  • 线程池（硬件传感器、SMART查询）                       │  │
│  │  • 定期数据持久化到SQLite                               │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                                │
│  监控组件：                                                     │
│  • SystemMonitor - 系统资源（CPU/内存/磁盘/网络）            │
│  • ProcessMonitor - 进程监控                                 │
│  • HardwareMonitor - 硬件传感器（温度/风扇）                 │
│  • SmartMonitor - 硬盘SMART健康                             │
│  • SystemBottleneckAnalyzer - 系统瓶颈分析                  │
│  • ScenarioAnalyzer - 量化场景分析                          │
│  • BusinessMetricsCollector - 业务指标采集                  │
│  • AdaptiveThresholdManager - 自适应阈值                    │
└──────────────────────────────────────────────────────────────┘
```

### 事件驱动架构

```
监控进程                SystemManagerService           UI组件
    │                          │                          │
    │  ZMQ查询监控数据          │                          │
    │ ─────────────────────>   │                          │
    │                          │                          │
    │  返回完整监控数据         │                          │
    │ <─────────────────────   │                          │
    │                          │                          │
    │                          │  拆分并推送事件           │
    │                          │ ───────────────────────> │
    │                          │  • SYSTEM_METRICS        │
    │                          │  • HARDWARE_SENSORS      │
    │                          │  • PROCESS_LIST          │
    │                          │  • SMART_STATUS          │
    │                          │  • BOTTLENECK_ANALYSIS   │
    │                          │                          │
    │                          │                     UI自动更新
```

---

## 文件组织

### 核心文件（已优化，减少25%）

```
system_vnpy/
├── __init__.py                  (139行) - 包导出和模块文档
├── monitor_core.py             (2432行) - 监控进程V2 + 系统分析器
├── monitors.py                 (2160行) - 基础监控 + 业务采集
├── managers.py                  (982行) - 服务/进程/安全管理
├── tools.py                    (1140行) - 诊断/文件/网络/性能工具
├── cleanup_monitor.py           (209行) - 维护清理工具 ⚙️
├── monitor_process_entry.py      (85行) - 监控进程启动入口 ⚙️
└── librehardwaremonitor/               - LibreHardwareMonitor集成
    ├── __init__.py               (14行)
    ├── lhm_extended.py          (367行) - 扩展硬件监控包装器
    ├── LibreHardwareMonitorLib.dll     - .NET库（需手动下载）
    └── HidSharp.dll                    - USB设备支持（需手动下载）
```

### 文件职责

| 文件 | 职责 | 主要类 |
|------|------|--------|
| **monitor_core.py** | 监控进程核心 + 系统分析 | MonitoringProcessV2, SystemBottleneckAnalyzer, ScenarioAnalyzer, AdaptiveThresholdManager, SmartMonitor |
| **monitors.py** | 基础监控工具 + 业务采集 | SystemMonitor, ProcessMonitor, ProcessBottleneckAnalyzer, BusinessMetricsCollector |
| **managers.py** | 管理功能 | ServiceHealthChecker, ProcessManager, SecurityManager |
| **tools.py** | 工具集合 | LogAnalyzer, NetworkTester, PerformanceOptimizer, FileOperations |
| **cleanup_monitor.py** | 维护工具 | 清理残留进程、释放端口 |
| **monitor_process_entry.py** | 启动入口 | 独立进程启动脚本 |

---

## 核心功能

### 1. 监控进程 V2 (MonitoringProcessV2)

**混合并发架构：**
- **asyncio 事件循环**: ZMQ通信、快速指标采集
- **线程池**: 阻塞任务（硬件传感器、SMART查询）
- **定期持久化**: 批量写入SQLite数据库

**监控能力：**
- ✅ 系统资源：CPU、内存、磁盘、网络
- ✅ 进程监控：资源占用、瓶颈识别
- ✅ 硬件传感器：CPU/GPU温度、风扇转速
- ✅ SMART健康：硬盘健康状态、坏道数量
- ✅ 网络监控：带宽、丢包率、连接数

### 2. 系统瓶颈分析 (SystemBottleneckAnalyzer)

**基于木桶理论的评分系统：**
- CPU维度：40分（使用率 + 上下文切换）
- 内存维度：30分（使用率 + Swap活动）
- 磁盘维度：15分（I/O延迟）
- 网络维度：15分（丢包率）

**输出：**
- 综合评分（0-100）
- 瓶颈维度识别
- 自适应并发缩放因子（0.3-1.6）
- 优化建议

### 3. 量化场景分析 (ScenarioAnalyzer)

**支持5大场景：**
1. 📥 数据下载 - 网络/磁盘瓶颈识别
2. 📊 实时行情 - 事件队列/延迟监控
3. 🔄 策略回测 - CPU/内存优化建议
4. ✏️ 策略编写 - 轻负载场景
5. 💹 实盘交易 - 订单响应/稳定性监控

**功能：**
- 自动场景识别
- 场景特定瓶颈分析
- 针对性优化建议

### 4. 自适应阈值 (AdaptiveThresholdManager)

**统计学习算法：**
- 基线计算（7天数据）
- 动态阈值（基线 + k×标准差）
- P95/P99 统计
- 自动异常检测

### 5. 业务指标采集 (BusinessMetricsCollector)

**支持指标：**
- 事件队列深度
- 订单响应时间
- K线计算耗时
- 数据查询延迟
- 并发任务计数

**特性：**
- 时间窗口统计（默认5分钟）
- P95/P99 计算
- 内存队列存储（可扩展到时序数据库）

---

## 快速开始

### 1. 环境准备

```bash
# 安装依赖
pip install psutil pythonnet zmq pySMART cryptography requests

# （可选）安装 LibreHardwareMonitor DLL
# 见下文"LibreHardwareMonitor 安装"章节
```

### 2. 启动监控进程

**方式1：通过 SystemManagerService（推荐）**

```python
from backend.services.system_manager_service import SystemManagerService

# SystemManagerService 会自动管理监控进程的启动和停止
service = SystemManagerService()
await service.initialize()
```

**方式2：独立启动（调试用）**

```bash
# 以管理员权限运行
python backend/infrastructure/system_vnpy/monitor_process_entry.py
```

### 3. 查询监控数据

**方式1：通过 SystemManagerService**

```python
from backend.services.system_manager_service import get_system_manager_service

service = get_system_manager_service()
data = service.get_monitoring_data()  # 获取完整监控数据
```

**方式2：订阅事件（UI组件）**

```python
from backend.core.base import get_event_engine
from backend.core.monitoring_events import EVENT_SYSTEM_METRICS

def on_system_metrics(event):
    metrics = event.data
    print(f"CPU: {metrics['cpu_percent']}%")
    print(f"内存: {metrics['memory_percent']}%")

event_engine = get_event_engine()
event_engine.register(EVENT_SYSTEM_METRICS, on_system_metrics)
```

**方式3：直接ZMQ查询（高级）**

```python
import zmq
import json

context = zmq.Context()
socket = context.socket(zmq.REQ)
socket.connect("tcp://127.0.0.1:5557")

socket.send_json({"action": "get_data"})
data = socket.recv_json()
print(json.dumps(data, indent=2, ensure_ascii=False))
```

---

## 使用指南

### 获取系统指标

```python
from backend.infrastructure.system_vnpy import SystemMonitor

monitor = SystemMonitor()
info = monitor.get_system_info()

print(f"CPU核心数: {info.cpu_count}")
print(f"总内存: {info.total_memory / (1024**3):.1f} GB")
print(f"系统: {info.os_type}")

usage = monitor.get_resource_usage()
print(f"CPU使用率: {usage.cpu_percent}%")
print(f"内存使用率: {usage.memory_percent}%")
```

### 进程监控

```python
from backend.infrastructure.system_vnpy import ProcessMonitor

monitor = ProcessMonitor()
processes = monitor.get_all_processes()

for proc in processes:
    if proc['type'] == 'python':
        print(f"{proc['name']}: CPU={proc['cpu_percent']}%, 内存={proc['memory_mb']}MB")
```

### 瓶颈分析

```python
from backend.infrastructure.system_vnpy import SystemBottleneckAnalyzer

analyzer = SystemBottleneckAnalyzer()
result = analyzer.analyze(monitoring_data)

print(f"综合评分: {result['total_score']}/100")
print(f"瓶颈维度: {result['bottleneck_dimension']}")
print(f"自适应因子: {result['adaptive_scale_factor']}")
print(f"优化建议:")
for suggestion in result['suggestions']:
    print(f"  • {suggestion}")
```

### 硬件监控（需要 LibreHardwareMonitor）

```python
from backend.infrastructure.system_vnpy.librehardwaremonitor import get_extended_lhm_wrapper

wrapper = get_extended_lhm_wrapper()
if wrapper.is_available():
    data = wrapper.get_all_sensor_data()

    # 温度
    for device, sensors in data['temperature'].items():
        print(f"{device}:")
        for sensor in sensors:
            print(f"  {sensor['label']}: {sensor['current']}°C")

    # 功耗
    for device, sensors in data['power'].items():
        print(f"{device}:")
        for sensor in sensors:
            print(f"  {sensor['label']}: {sensor['current']}W")
```

### 业务指标采集

```python
from backend.infrastructure.system_vnpy import get_business_metrics_collector

collector = get_business_metrics_collector()

# 记录指标
collector.record_metric('order_response_time_ms', 150.5, {'gateway': 'ctp'})
collector.record_metric('event_queue_depth', 1200)

# 任务计数
collector.increment_task('download')  # 开始任务
# ... 执行任务 ...
collector.decrement_task('download')  # 完成任务

# 获取统计
summary = collector.get_metrics_summary()
print(f"订单响应时间: P95={summary['order_response_time_ms']['p95']}ms")

tasks = collector.get_concurrent_tasks()
print(f"并发任务: 下载={tasks['download']}, 回测={tasks['backtest']}")
```

---

## LibreHardwareMonitor 安装

### 为什么需要？

LibreHardwareMonitor 提供深度硬件监控能力：
- 🌡️ CPU/GPU 温度（精确到每个核心）
- ⚡ 功耗监控
- 🔌 电压监控
- 🌀 风扇转速
- ⚙️ 时钟频率
- 📊 负载百分比

### 安装步骤

#### 1. 下载 LibreHardwareMonitor

访问官方发布页面：
```
https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases/latest
```

下载 `LibreHardwareMonitor-vX.X.X.zip`（建议 v0.9.4 或更高版本）

#### 2. 复制 DLL 文件

解压后，将以下文件复制到 `backend/infrastructure/system_vnpy/librehardwaremonitor/` 目录：

```
✅ LibreHardwareMonitorLib.dll  - 核心库（必需）
✅ HidSharp.dll                - USB设备支持（必需）
```

**注意**: 从 v0.9.4 开始，WinRing0 驱动已嵌入 DLL，无需额外文件！

#### 3. 验证安装

运行测试：
```python
from backend.infrastructure.system_vnpy.librehardwaremonitor import get_extended_lhm_wrapper

wrapper = get_extended_lhm_wrapper()
if wrapper.is_available():
    print("✅ LibreHardwareMonitor 安装成功！")
    data = wrapper.get_all_sensor_data()
    print(f"检测到 {len(data['temperature'])} 个温度设备")
else:
    print("❌ LibreHardwareMonitor 初始化失败")
```

### 系统要求

- ✅ Windows 10/11
- ✅ .NET Framework 4.8+ (Windows 自带)
- ✅ **管理员权限**（加载 WinRing0 驱动需要）
- ✅ pythonnet 包: `pip install pythonnet`

### 故障排除

**Q: 提示 "pythonnet未安装"**
```bash
pip install pythonnet
```

**Q: 提示 "LibreHardwareMonitorLib.dll未找到"**
- 检查 DLL 是否在正确目录
- 确认文件名拼写正确（区分大小写）

**Q: 提示 "无法加载WinRing0驱动"**
- 以管理员权限运行 Python
- 检查防病毒软件是否阻止驱动加载
- 确保使用 v0.9.4+ 版本（驱动已嵌入）

---

## API 接口

### ZMQ 通信协议

#### 查询监控数据（REQ/REP）

**端口**: `tcp://127.0.0.1:5557`

**请求**:
```json
{
    "action": "get_data"
}
```

**响应**:
```json
{
    "timestamp": "2025-10-23T10:00:00",
    "system": {
        "cpu_percent": 45.2,
        "memory_percent": 62.1,
        "disk_percent": 75.3,
        "network_speed": {"download_kbps": 5000, "upload_kbps": 1000},
        "cpu_detailed": {"context_switches_per_sec": 25000},
        "memory_subsystem": {"swap_in_kbps": 0, "swap_out_kbps": 0},
        "storage_subsystem": {"disks": {...}},
        "network_subsystem": {"packet_loss_rate_in": 0.001},
        "temperature": {"cpu": 55.0, "gpu": 60.0}
    },
    "hardware": {
        "temperature": {...},
        "power": {...},
        "fan": {...}
    },
    "process": [...],
    "smart": {...},
    "analysis": {
        "total_score": 85.5,
        "bottleneck_dimension": "network",
        "adaptive_scale_factor": 1.15,
        "suggestions": [...]
    },
    "scenario": {
        "scenario": "data_download",
        "scenario_name": "数据下载",
        "is_bottleneck": false,
        "optimization_hints": [...]
    },
    "thresholds": {
        "cpu_percent": {"p95": 78.5, "p99": 92.3},
        "memory_percent": {"p95": 68.2, "p99": 82.1}
    },
    "concurrent_tasks": {
        "download": 3,
        "backtest": 0,
        "trading": 0,
        "total": 3
    }
}
```

#### 查询健康状态

**请求**:
```json
{
    "action": "health_check"
}
```

**响应**:
```json
{
    "status": "healthy",
    "uptime": 3600.5,
    "last_update": "2025-10-23T10:00:00"
}
```

### 事件类型

监控数据会被拆分为以下事件类型推送到 EventEngine：

| 事件类型 | 常量 | 数据内容 |
|---------|------|---------|
| 系统指标 | `EVENT_SYSTEM_METRICS` | CPU、内存、磁盘、网络基础指标 |
| 硬件传感器 | `EVENT_HARDWARE_SENSORS` | 温度、功耗、风扇等 |
| 进程列表 | `EVENT_PROCESS_LIST` | 进程监控数据 |
| SMART状态 | `EVENT_SMART_STATUS` | 硬盘健康状态 |
| 瓶颈分析 | `EVENT_BOTTLENECK_ANALYSIS` | 瓶颈分析结果 |
| 场景分析 | `EVENT_SCENARIO_ANALYSIS` | 量化场景分析 |

---

## 故障排除

### 监控进程无法启动

**症状**: SystemManagerService 报告监控进程启动失败

**排查步骤**:
1. 检查端口占用：
   ```bash
   python backend/infrastructure/system_vnpy/cleanup_monitor.py
   ```

2. 查看日志：
   ```
   logs/monitor_process.log
   logs/monitor_stderr.log
   ```

3. 手动测试启动：
   ```bash
   python backend/infrastructure/system_vnpy/monitor_process_entry.py
   ```

### ZMQ 连接超时

**症状**: `zmq.error.Again: Resource temporarily unavailable`

**解决方案**:
1. 确认监控进程已启动
2. 检查防火墙是否阻止本地连接
3. 验证端口未被占用（5555, 5556, 5557）

### 硬件监控不可用

**症状**: 温度数据为空或 LibreHardwareMonitor 初始化失败

**解决方案**:
1. 以管理员权限运行
2. 确认 DLL 文件已正确放置
3. 安装 pythonnet: `pip install pythonnet`
4. 检查 .NET Framework 版本（需要 4.8+）

### SMART 监控失败

**症状**: `pySMART initialization failed`

**解决方案**:
1. 以管理员权限运行（Windows）
2. Linux: 安装 smartmontools: `sudo apt install smartmontools`
3. 确认硬盘支持 SMART

### 性能问题

**症状**: 监控进程CPU占用过高

**优化方案**:
1. 调整采集频率（默认2秒）
2. 禁用不需要的监控组件
3. 减少进程监控数量
4. 使用异步采集

---

## 开发指南

### 添加新的监控指标

1. **在监控进程中采集数据** (`monitor_core.py`):
```python
class MonitoringProcessV2:
    async def _collect_system_metrics(self):
        # 添加新指标
        new_metric = self._collect_new_metric()
        self.monitoring_data['system']['new_metric'] = new_metric
```

2. **定义事件类型** (`backend/core/monitoring_events.py`):
```python
EVENT_NEW_METRIC = "monitoring.new_metric"
```

3. **在 SystemManagerService 中分发事件**:
```python
def _dispatch_monitoring_events(self, data: Dict[str, Any]):
    if 'new_metric' in data.get('system', {}):
        self.event_engine.put(Event(
            EVENT_NEW_METRIC,
            data['system']['new_metric']
        ))
```

4. **在 UI 中订阅和显示**:
```python
def _register_monitoring_events(self):
    self.event_engine.register(EVENT_NEW_METRIC, self._on_new_metric)

def _on_new_metric(self, event: Event):
    data = event.data
    # 更新 UI
```

### 添加新的分析器

```python
class NewAnalyzer:
    """新分析器."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def analyze(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """分析逻辑."""
        # 实现分析算法
        return {
            "result": "...",
            "suggestions": [...]
        }

# 在 MonitoringProcessV2.__init__ 中初始化
self.new_analyzer = NewAnalyzer()

# 在数据采集中调用
analysis = self.new_analyzer.analyze(self.monitoring_data)
self.monitoring_data['new_analysis'] = analysis
```

### 扩展业务指标

```python
# 在业务服务中
from backend.infrastructure.system_vnpy import get_business_metrics_collector

collector = get_business_metrics_collector()

# 记录自定义指标
collector.record_metric('custom_metric', value, {'metadata': 'info'})

# 查询统计
summary = collector.get_metrics_summary()
custom_stats = summary.get('custom_metric', {})
```

### 调试技巧

1. **使用日志**:
```python
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
```

2. **独立测试监控进程**:
```bash
python backend/infrastructure/system_vnpy/monitor_process_entry.py
```

3. **ZMQ 手动测试**:
```python
import zmq
ctx = zmq.Context()
sock = ctx.socket(zmq.REQ)
sock.connect("tcp://127.0.0.1:5557")
sock.send_json({"action": "get_data"})
print(sock.recv_json())
```

4. **断点调试**:
   - 在 `monitor_core.py` 中设置断点
   - 核心逻辑集中在单文件，方便跟踪

---

## 参考文档

- [监控进程API接口.md](./监控进程API接口.md) - 详细的ZMQ协议规范
- [监控进程与主进程集成架构.md](./监控进程与主进程集成架构.md) - 架构设计文档
- [文件合并总结.md](./文件合并总结.md) - v0.50 重构记录

---

## 许可证

本模块为量化交易终端的一部分，遵循项目整体许可证。

---

## 更新日志

### v0.50 (2025-10-23)
- ✅ 重构文件组织，减少文件数量25%
- ✅ 合并系统分析器到 monitor_core.py
- ✅ 合并业务采集器到 monitors.py
- ✅ 解决命名冲突（ProcessBottleneckAnalyzer vs SystemBottleneckAnalyzer）
- ✅ 简化 librehardwaremonitor，只保留 ExtendedLHMWrapper
- ✅ 提升 debug 友好性

### v0.49 (2025-10-22)
- ✅ 修复 ZMQ 协程启动问题（启动屏障机制）
- ✅ 优化 ZMQ 响应速度（<1ms）
- ✅ 修复事件循环阻塞
- ✅ 降低 CPU 占用 15%

### v0.48 (2025-10-21)
- ✅ 实现事件驱动架构（VNpy EventEngine）
- ✅ 添加自适应阈值管理器
- ✅ 集成 SMART 监控
- ✅ 实现场景分析器

---

**📧 问题反馈**: 请在项目仓库提交 Issue

