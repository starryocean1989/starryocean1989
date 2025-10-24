# -*- coding: utf-8 -*-
# data_module_vnpy - 中国A股量化数据管理模块

**版本**: v3.0.0
**最后更新**: 2025-10-23
**架构**: 基于 VNPy + TDX异步接口

---

## 📑 目录

- [模块简介](#模块简介)
- [核心定位](#核心定位)
- [架构总览](#架构总览)
- [目录结构](#目录结构)
- [核心组件](#核心组件)
- [功能特性](#功能特性)
- [技术架构](#技术架构)
- [上下游调用](#上下游调用)
- [快速开始](#快速开始)
- [API参考](#api参考)
- [配置说明](#配置说明)
- [性能优化](#性能优化)
- [维护指南](#维护指南)

---

## 模块简介

`data_module_vnpy` 是一个企业级的中国A股数据管理模块，完全集成到 VNPy 量化交易框架中，提供从数据获取、存储、质量管理到实时推送的全链路数据服务。

### 核心能力

- ✅ **品种管理**: 自动获取和分类上证/深证/北证A股、ETF、可转债等
- ✅ **数据下载**: 多进程+异步协程架构，智能负载均衡
- ✅ **质量管理**: 实时数据质量监控、自动校验和修复
- ✅ **智能缓存**: 统一缓存管理，日期失效机制
- ✅ **实时推送**: 轮询转推送、虚拟回放、外部网关适配
- ✅ **统一查询**: 四层数据融合（历史+录制+实时+预加载）

### 技术特色

- 🚀 **纯异步架构**: 基于 `tdx_asyncio` 的纯异步实现
- 🎯 **智能负载均衡**: 根据系统资源动态调整并发配置
- 🔄 **两段式下载**: 热备服务器池，优化下载性能
- 📊 **企业级监控**: 集成系统监控，木桶理论评分模型
- 🧠 **自适应配置**: CPU/内存/网络自动评估和优化

---

## 核心定位

**data_module_vnpy 提供历史数据、实时数据集成式的数据服务，供各个功能模块使用。**

作为系统的数据中枢，本模块为以下上层模块提供数据支撑：
- **行情看板**: 实时行情展示和K线图表
- **数据中心**: 数据下载、品种管理、质量监控
- **策略中心**: 策略回测和实盘交易
- **交易网关**: CTP、IB等外部网关的数据适配

---

## 架构总览

```
┌─────────────────────────────────────────────────────────────┐
│                    上层应用（UI层）                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │行情看板  │  │数据中心  │  │策略中心  │  │交易网关  │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
└───────┼─────────────┼─────────────┼─────────────┼──────────┘
        │             │             │             │
        └─────────────┴─────────────┴─────────────┘
                      │
        ┌─────────────▼──────────────────────────────────────┐
        │         服务层 (Service Layer)                      │
        │  ┌─────────────────────────────────────────────┐   │
        │  │  DataCenterService                          │   │
        │  │  - 品种列表管理                              │   │
        │  │  - 数据下载任务调度                          │   │
        │  │  - 数据查询接口                              │   │
        │  └──────────────────┬──────────────────────────┘   │
        └─────────────────────┼────────────────────────────────┘
                              │
        ┌─────────────────────▼────────────────────────────────┐
        │     核心引擎 (ChinaStockEngine)                       │
        │  ┌─────────────────────────────────────────────┐    │
        │  │  协调所有功能模块，提供统一的数据管理接口    │    │
        │  └──────────────────┬──────────────────────────┘    │
        └─────────────────────┼──────────────────────────────────┘
                              │
        ┌─────────────────────▼────────────────────────────────┐
        │          data_module_vnpy 内部架构                    │
        ├──────────────────────────────────────────────────────┤
        │                                                       │
        │  ┌─────────────────────────────────────────────┐    │
        │  │  data_acquisition (远程数据获取)            │    │
        │  │  ├─ symbol_management.py  品种管理          │    │
        │  │  └─ data_fetcher.py       多进程下载        │    │
        │  └─────────────────────────────────────────────┘    │
        │                                                       │
        │  ┌─────────────────────────────────────────────┐    │
        │  │  local_data (本地数据管理)                  │    │
        │  │  ├─ data_quality.py       质量管理          │    │
        │  │  └─ unified_data_manager.py 统一管理        │    │
        │  └─────────────────────────────────────────────┘    │
        │                                                       │
        │  ┌─────────────────────────────────────────────┐    │
        │  │  load_balancer (负载均衡)                   │    │
        │  │  ├─ server_pool_manager.py 服务器池         │    │
        │  │  └─ core.py               负载均衡器        │    │
        │  └─────────────────────────────────────────────┘    │
        │                                                       │
        │  ┌─────────────────────────────────────────────┐    │
        │  │  data_readers (本地文件读取)                │    │
        │  │  └─ tdx_reader.py         通达信文件读取    │    │
        │  └─────────────────────────────────────────────┘    │
        │                                                       │
        │  ┌─────────────────────────────────────────────┐    │
        │  │  共享组件                                    │    │
        │  │  ├─ config.py             配置管理          │    │
        │  │  ├─ cache_manager.py      缓存管理          │    │
        │  │  └─ events.py             事件系统          │    │
        │  └─────────────────────────────────────────────┘    │
        │                                                       │
        └───────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────▼────────────────────────────────┐
        │          底层依赖                                     │
        │  ┌──────────────┐  ┌──────────────┐                 │
        │  │ tdx_asyncio  │  │    VNPy      │                 │
        │  │ 纯异步TDX接口 │  │  事件引擎    │                 │
        │  └──────────────┘  └──────────────┘                 │
        └───────────────────────────────────────────────────────┘
```

---

## 目录结构

```
data_module_vnpy/
│
├── 📄 核心文件
│   ├── __init__.py                     # 模块导出接口
│   ├── core.py                         # ChinaStockEngine 核心引擎
│   ├── config.py                       # 配置管理器
│   ├── cache_manager.py                # 统一缓存管理（日期失效机制）
│   ├── events.py                       # 事件发布器
│   └── README.md                       # 本文档
│
├── 📁 data_acquisition/                # 远程数据获取模块
│   ├── __init__.py
│   ├── symbol_management.py            # 品种列表获取和分类
│   │   ├── SymbolLoader               # 品种加载器（1424行）
│   │   └── BlockParser                # 板块解析器
│   └── data_fetcher.py                 # K线数据下载
│       ├── MultiProcessStockFetcher   # 多进程下载器（2768行）
│       ├── download_incremental_unified # 统一下载接口
│       └── download_ipo_dates         # IPO日期批量下载
│
├── 📁 local_data/                      # 本地数据管理模块
│   ├── __init__.py
│   ├── data_quality.py                 # 数据质量管理（3486行）
│   │   ├── IPODateCache               # IPO日期缓存
│   │   ├── StorageManager             # 存储管理（Parquet）
│   │   ├── DataValidator              # 数据校验
│   │   ├── DataSensor                 # 数据质量感知
│   │   ├── DataFileWatcher            # 文件监控
│   │   └── HealthChecker              # 系统健康检查
│   ├── unified_data_manager.py         # 统一数据管理（2286行）
│   │   ├── UnifiedDataManager         # 四层数据融合
│   │   ├── PreloadService             # 智能预加载
│   │   ├── TdxDataSource              # TDX数据源（轮询转推送）
│   │   └── VirtualDataSource          # 虚拟数据源（历史回放）
│   └── intelligent_adaptive_tuner.py   # 智能自适应调优器
│
├── 📁 load_balancer/                   # 负载均衡模块
│   ├── __init__.py
│   ├── README.md                       # 负载均衡详细文档
│   ├── core.py                         # LoadBalancer 核心（单例）
│   ├── server_pool_manager.py          # 服务器池管理器
│   ├── tasks.py                        # 任务基类定义
│   ├── monitors.py                     # 系统监控指标获取
│   ├── evaluators.py                   # 资源压力评估器
│   └── configs.py                      # 动态配置计算器
│
├── 📁 data_readers/                    # 本地文件读取模块
│   ├── __init__.py
│   ├── base_reader.py                  # 读取器基类
│   ├── tdx_reader.py                   # 通达信文件读取器
│   └── bj_decoder.py                   # 北交所数据解码器
│
└── 📄 配置和依赖
    ├── requirements.txt                # Python依赖包
    └── UNIFIED_DATA_MANAGER_API.md     # 统一数据管理器API文档
```

### 文件统计

| 模块 | 文件数 | 代码行数 | 核心类数 |
|------|--------|----------|----------|
| **核心文件** | 5个 | ~2000行 | 6个 |
| **data_acquisition** | 2个 | ~4200行 | 5个 |
| **local_data** | 3个 | ~6000行 | 15个 |
| **load_balancer** | 7个 | ~3000行 | 10个 |
| **data_readers** | 3个 | ~800行 | 3个 |
| **总计** | **20个** | **~16000行** | **39个类** |

---

## 核心组件

### 1. ChinaStockEngine - 核心引擎

`core.py` (1149行)

**职责**: 作为整个模块的中枢，协调所有功能组件，提供统一的对外接口。

**核心功能**:
- ✅ 集成所有子模块（品种管理、数据下载、质量管理、统一查询）
- ✅ 智能缓存验证流程（启动时7步验证，2-3秒启动）
- ✅ 生命周期管理（初始化、启动、停止、健康检查）
- ✅ 事件协调（日志、进度、数据质量、下载状态）
- ✅ 配置管理（统一配置接口）

**关键方法**:
```python
# 品种管理
engine.reload_stock_list()          # 重新加载品种列表
engine.get_market_stocks("上证A股")  # 获取指定市场品种

# 数据下载
engine.download_incremental("2024-01-01")  # 增量下载

# 数据查询
engine.query_data("000001", "1d", "2024-01-01", "2024-12-31")

# 质量管理
engine.trigger_data_quality_scan()  # 触发质量扫描
engine.get_data_quality_overview()  # 获取质量概览

# 系统管理
engine.healthcheck()                # 健康检查
```

**上游调用者**:
- `backend/core/base.py` - ServiceInitializer 在系统启动时创建
- `backend/services/data_center_service.py` - DataCenterService 调用其方法
- `ui/modules/data_center_view.py` - 数据中心UI直接调用

---

### 2. SymbolLoader - 品种管理器

`data_acquisition/symbol_management.py` (1424行)

**职责**: 品种列表的获取、分类、缓存和解析。

**核心功能**:
- ✅ 从 TDX API 获取完整品种列表（沪深两市）
- ✅ 从通达信配置文件解析北交所品种和可转债
- ✅ 智能分类（上证A股、深证A股、北证A股、T+0基金、可转债）
- ✅ 本地缓存管理（JSON格式，日期失效机制）
- ✅ 增量更新机制（自动检测新增/退市品种）
- ✅ IPO日期集成（品种信息包含上市日期）

**分类逻辑**:
```python
上证A股: market=1, code以60/68开头
深证A股: market=0, code以00/30开头
北证A股: market=2, code以8/4/920开头（从配置文件）
T+0基金: code以511/159/512/513/515/516/518等开头
可转债: code以11/12开头（从tdxstat2.cfg）
```

**关键方法**:
```python
loader = SymbolLoader(event_engine)

# 重新加载并分类
result = loader.reload_and_classify()
# 返回: {"success": True, "total": 5200, "classified": {...}}

# 提取品种代码
all_codes = loader.extract_all_codes()
market_codes = loader.extract_codes_by_market(["上证A股"])

# 获取缓存数据
cache = loader.get_cached_data()
```

**数据格式**:
```python
{
    "cache_date": "2025-10-23",
    "data": {
        "classified": {
            "上证A股": [
                {
                    "code": "600000",
                    "name": "浦发银行",
                    "market": 1,
                    "ipo_date": "1999-11-10"  # 集成IPO日期
                },
                ...
            ],
            ...
        },
        "total_count": 5200
    }
}
```

---

### 3. MultiProcessStockFetcher - 数据下载器

`data_acquisition/data_fetcher.py` (2768行)

**职责**: 高性能的多进程+异步协程K线数据下载。

**核心功能**:
- ✅ 多进程架构（充分利用多核CPU）
- ✅ 纯异步协程（单进程内高并发）
- ✅ 智能负载均衡（根据系统资源动态调整）
- ✅ 两段式下载（乱序服务器池 + 热备服务器池）
- ✅ IPO日期批量下载（复用下载架构）
- ✅ 实时进度推送（UI实时显示）
- ✅ 断点续传（支持暂停/恢复）

**性能指标**:
| 系统配置 | 并发数 | 5000股票×3周期 | 耗时 |
|---------|--------|---------------|------|
| 8核CPU  | 320连接 | 15000任务 | ~3分钟 |
| 12核CPU | 480连接 | 15000任务 | ~2分钟 |
| 16核CPU | 640连接 | 15000任务 | ~1.5分钟 |

**关键方法**:
```python
fetcher = MultiProcessStockFetcher(event_engine)

# 增量下载（推荐）
result = fetcher.download_incremental_kline(
    symbols=["000001", "600000"],
    start_date="2024-01-01",
    intervals=["1d", "5m", "1m"],
    use_adaptive=True,      # 自适应配置
    use_two_phase=True      # 两段式下载
)

# IPO日期批量下载
result = download_ipo_dates(
    symbols=all_symbols,
    force_refresh=False,    # 增量模式
    use_adaptive=True
)

# 控制下载
fetcher.stop_download()
fetcher.pause_download()
fetcher.resume_download()
progress = fetcher.get_download_progress()
```

**两段式下载机制**:
```
阶段1: 使用650+个乱序服务器，高速下载至剩余5%
      ↓
预热: 连接30个热备服务器（不同券商）
      ↓
阶段2: 使用30个热备服务器，精准完成剩余任务
```

---

### 4. DataSensor - 数据质量感知器

`local_data/data_quality.py` (3486行)

**职责**: 全方位的数据质量监控、校验和报告。

**核心功能**:
- ✅ 四维度检查（品种缺失、历史缺失、逻辑错误、格式错误）
- ✅ 混合异步架构（协程+线程+进程，最大2000并发）
- ✅ 智能自适应扫描（根据文件大小选择处理方式）
- ✅ 增量推送机制（500ms最小间隔，避免UI卡顿）
- ✅ IPO日期缓存管理（两级缓存，95%+命中率）
- ✅ 文件监控（实时检测数据变化）

**质量指标**:
```python
class QualityOverview:
    quality_score: float           # 总体质量分数 (0-100)
    total_symbols: int             # 总品种数
    missing_symbols: int           # 品种缺失数
    outdated_symbols: int          # 数据过时数
    avg_gap_days: float           # 平均滞后天数
    max_gap_days: int             # 最大滞后天数
    error_count: int              # 错误数量
    warning_count: int            # 警告数量
```

**关键方法**:
```python
sensor = DataSensor(event_engine)

# 触发质量扫描
overview = sensor.trigger_scan_with_symbols(
    symbol_loader=symbol_loader,
    force_refresh=True
)

# 获取质量概览
overview = sensor.get_quality_overview()

# 启动文件监控
sensor.start_file_watcher()

# 检查单个品种
validation = sensor.validate_symbol("000001")
```

**混合异步架构**:
```
├─ 协程层: 小文件 (<1MB)  → asyncio pool (2000并发)
├─ 线程层: 中等文件 (1-10MB) → ThreadPoolExecutor (50线程)
└─ 进程层: 大文件 (>10MB)    → ProcessPoolExecutor (16进程)
```

---

### 5. UnifiedDataManager - 统一数据管理器

`local_data/unified_data_manager.py` (2286行)

**职责**: 多源数据融合、统一查询、实时推送。

**核心功能**:
- ✅ 四层数据融合（历史Parquet + 录制数据 + 实时推送 + 预加载缓存）
- ✅ 智能预加载（常用品种自动预加载，亚秒级响应）
- ✅ TDX数据源（轮询转推送，符合VNPy Gateway标准）
- ✅ 虚拟数据源（历史回放，用于回测）
- ✅ 订阅管理（多模块订阅，去重优化）
- ✅ 自动补全（检测数据缺失，自动触发下载）

**查询优先级**:
```
1. 预加载缓存 (内存, 最快)
   ↓ 未命中
2. 历史Parquet文件 (磁盘, 快)
   ↓ 未命中
3. 录制数据 (如果启用)
   ↓ 未命中
4. 实时推送 (如果已订阅)
```

**关键方法**:
```python
manager = UnifiedDataManager(china_stock_engine)

# 统一查询（自动融合）
data = manager.query_unified(
    symbol="000001",
    interval="1d",
    start_date="2024-01-01",
    end_date="2024-12-31",
    check_gaps=True  # 自动检测缺失
)

# 订阅管理
manager.subscribe(module="strategy", symbols=["000001", "600000"])
manager.unsubscribe(module="strategy")

# 预加载服务
manager.preload_symbols(["000001", "600000"], intervals=["1d", "5m"])
```

**TDX数据源（轮询转推送）**:
```python
tdx_source = TdxDataSource(gateway_name="TDX_POLLING")
tdx_source.connect({
    "轮询间隔（秒）": 3,
    "品种列表": "000001,600000"
})
# 自动推送 TickData/BarData 到 VNPy 事件引擎
```

---

### 6. LoadBalancer - 智能负载均衡器

`load_balancer/core.py` + 相关模块 (~3000行)

**职责**: 根据系统资源动态调整任务并发配置。

**核心功能**:
- ✅ 单例模式（全局唯一实例）
- ✅ 混合监控（事件订阅 + ZMQ查询 + 智能fallback）
- ✅ 木桶理论评分（CPU 40分 + 内存 30分 + 磁盘 15分 + 网络 15分）
- ✅ 动态缩放（0.3-1.6倍并发调整）
- ✅ 智能缓存（3秒TTL，减少评估开销）
- ✅ 任务标准化（8个标准任务类型）

**评分模型**:
```
总分 = min(CPU分40, 内存分30, 磁盘分15, 网络分15) × 评分因子

压力级别:
- 0-30分: 紧急 (0.3x并发)
- 31-50分: 高压 (0.5x-0.7x并发)
- 51-70分: 中等 (0.8x-1.0x并发)
- 71-100分: 正常 (1.0x-1.6x并发)
```

**标准任务类型**:
```python
# 网络任务 (4个)
- ServerPoolTestTask      # 服务器池测速
- KlineDownloadTask       # K线批量下载
- IPODownloadTask         # IPO日期下载
- RealtimePollingTask     # 实时行情轮询

# 本地处理任务 (4个)
- DataQualityScanTask     # 数据质量扫描
- TdxBatchReadTask        # TDX文件批量读取
- VirtualReplayTask       # 虚拟推送回放
- PreloadTask             # 数据预加载
```

**关键方法**:
```python
load_balancer = LoadBalancer(event_engine)

# 定义任务
task = KlineDownloadTask("kline_download", task_count=15000)

# 获取最优配置
config = load_balancer.get_optimal_config(task)
# 返回: {
#     "processes": 16,
#     "coroutines_per_process": 40,
#     "total_connections": 640,
#     "pressure_score": 85.3,
#     "scale_factor": 1.2,
#     "reason": "系统正常，提升20%并发"
# }

# 执行任务
result = task.execute(config)
```

---

### 7. ServerPoolManager - 服务器池管理器

`load_balancer/server_pool_manager.py` (1100行)

**职责**: 通达信服务器的测速、排序、故障剔除和热备管理。

**核心功能**:
- ✅ 多进程并行测速（3进程×50协程，5-10秒完成）
- ✅ 智能排序（按响应时间排序，故障服务器剔除）
- ✅ 热备服务器池（30个不同券商的最快服务器）
- ✅ 两段式下载支持（乱序池 + 热备池）
- ✅ 缓存机制（次日0时失效）
- ✅ 线程安全（多线程获取服务器）

**关键方法**:
```python
# 全局单例
from backend.infrastructure.data_module_vnpy import server_pool_manager

# 启动时测速
server_pool_manager.start()  # 5-10秒，可并发执行

# 获取最快的服务器
best = server_pool_manager.get_best_server()

# 获取前N个服务器
top10 = server_pool_manager.get_servers(count=10)

# 获取打乱后的服务器（用于下载）
servers = server_pool_manager.get_servers_shuffled()

# 检查缓存状态
is_valid = server_pool_manager.is_cache_valid()
stats = server_pool_manager.get_stats()
```

**测速性能**:
```
输入: 132个服务器
进程: 3个（CPU并行）
协程: 50×3=150个（I/O并行）
超时: 2秒/服务器
耗时: 5-10秒

输出: 54个可用服务器（按速度排序）
最快: 123.125.108.90:7709
Top3: 123.125.108.90, 123.125.108.14, 124.70.176.52
```

---

## 功能特性

### 🎯 品种管理

#### 支持的品种类型
- ✅ **上证A股**: 60xxxx, 68xxxx（科创板）
- ✅ **深证A股**: 00xxxx, 30xxxx（创业板）
- ✅ **北证A股**: 8xxxxx, 4xxxxx, 920xxx（从配置文件）
- ✅ **T+0基金**: 511xxx, 159xxx, 512xxx, 513xxx, 515xxx, 516xxx, 518xxx
- ✅ **可转债**: 11xxxx（深市）, 12xxxx（沪市）

#### 核心能力
- 自动获取完整品种列表（~5200个）
- 智能分类和标签
- IPO日期集成
- 增量更新机制
- 本地缓存（次日0时失效）
- 通达信板块文件解析

---

### 🚀 数据下载

#### 多维度下载
- ✅ **增量下载**: 从指定日期开始增量更新
- ✅ **全量下载**: 从IPO日期开始全量下载
- ✅ **多周期支持**: 日线(1d)、5分钟(5m)、1分钟(1m)
- ✅ **批量下载**: 支持数千品种并行下载

#### 性能优化
```
传统方案 (单进程单线程):
5000品种 × 3周期 = 15000任务
耗时: ~6小时

优化方案1 (多线程):
50线程并发
耗时: ~40分钟

优化方案2 (多进程+异步):
16进程 × 40协程 = 640并发
耗时: ~1.5分钟  ✅ 性能提升240倍！
```

#### 智能特性
- **自适应配置**: 根据CPU/内存自动调整并发数
- **两段式下载**: 乱序池高速下载 + 热备池精准完成
- **断点续传**: 支持暂停/恢复
- **实时进度**: UI实时显示下载进度
- **故障重试**: 自动重试失败任务
- **服务器轮换**: 避免单一服务器压力过大

---

### 📊 数据质量管理

#### 四维度检查
1. **品种缺失检查**: 检测本地没有数据的品种
2. **历史缺失检查**: 检测数据不完整的品种（未覆盖到最新交易日）
3. **逻辑错误检查**: 检测数据异常（如价格为0、交易量异常等）
4. **格式错误检查**: 检测文件损坏或格式错误

#### 质量评分
```python
质量分数 = (1 - 缺失率) × 100

评级标准:
90-100分: 优秀 ✅
70-89分:  良好 ⚠️
50-69分:  中等 ⚠️
0-49分:   差   ❌
```

#### 智能扫描
- **混合异步架构**: 协程+线程+进程，最大2000并发
- **自适应模式**: 根据文件大小选择处理方式
- **增量推送**: 500ms最小间隔，避免UI卡顿
- **文件监控**: 实时检测数据变化
- **自动修复**: 检测到问题自动触发下载

---

### 🎨 统一数据管理

#### 四层数据融合
```
查询优先级:
1. 预加载缓存 (内存)     → 亚秒级响应
2. 历史Parquet (磁盘)    → 秒级响应
3. 录制数据 (如启用)      → 秒级响应
4. 实时推送 (如已订阅)    → 实时推送
```

#### 智能预加载
- 常用品种自动预加载（可配置）
- LRU缓存淘汰策略
- 最大缓存64个品种（可配置）
- 支持多周期预加载

#### 订阅管理
- 多模块订阅支持
- 自动去重优化
- 订阅数量统计
- 动态订阅/取消订阅

---

### 🔄 实时数据推送

#### TDX数据源（轮询转推送）
```python
# 符合VNPy Gateway标准
tdx_source = TdxDataSource(gateway_name="TDX_POLLING")
tdx_source.connect({
    "轮询间隔（秒）": 3,
    "品种列表": "000001,600000,600519"
})

# 自动推送到VNPy事件引擎
# - EVENT_TICK (实时行情)
# - EVENT_BAR (K线数据)
```

#### 虚拟数据源（历史回放）
```python
# 用于策略回测
virtual_source = VirtualDataSource(gateway_name="VIRTUAL")
virtual_source.connect({
    "起始时间": "2024-01-01 09:30:00",
    "回放速度": 2.0,  # 2倍速
    "品种列表": "000001,600000"
})

# 按历史时间顺序推送
# 支持暂停/恢复/快进
```

---

### ⚙️ 配置管理

#### 统一缓存机制
```python
from backend.infrastructure.data_module_vnpy.cache_manager import DailyCacheManager

# 保存缓存（自动带日期）
DailyCacheManager.save_with_date(data, "my_cache.json")

# 加载缓存（自动验证日期）
data, cache_date, is_valid = DailyCacheManager.load_with_validation("my_cache.json")

# 缓存文件格式
{
    "cache_date": "2025-10-23",
    "data": { ... }
}
```

#### 失效策略
- 次日0时自动失效
- 确保数据时效性
- 避免过期数据干扰

---

## 上下游调用

### 下游依赖

```
data_module_vnpy
    ├─> tdx_asyncio (纯异步TDX接口)
    │   ├─ AsyncTdxHq_API (异步行情API)
    │   ├─ AsyncSmartIPPool (智能连接池)
    │   └─ TradingCalendar (交易日历)
    │
    ├─> VNPy (量化交易框架)
    │   ├─ EventEngine (事件引擎)
    │   ├─ BaseEngine (引擎基类)
    │   └─ BaseGateway (网关基类)
    │
    └─> Python标准库
        ├─ asyncio (异步IO)
        ├─ multiprocessing (多进程)
        ├─ threading (多线程)
        ├─ pandas (数据处理)
        └─ pyarrow (Parquet文件)
```

### 上游调用者

#### 1. UI层调用

```
ui/modules/
├─ data_center_view.py          # 数据中心界面
│  ├─ 品种管理
│  ├─ 数据下载
│  ├─ 质量监控
│  └─ 数据查询
│
├─ market_board_view.py          # 行情看板界面
│  └─ 实时行情展示
│
└─ strategy_center_view.py       # 策略中心界面
   └─ 策略回测数据查询
```

**调用方式**:
```python
# UI通过全局访问器获取引擎
from backend.core.base import get_china_stock_engine

engine = get_china_stock_engine()
if engine:
    # 调用引擎方法
    result = engine.reload_stock_list()
    data = engine.query_data("000001", "1d", "2024-01-01")
```

#### 2. 服务层调用

```
backend/services/
├─ data_center_service.py        # 数据中心服务
│  ├─ _ensure_china_stock_engine()
│  ├─ reload_symbol_list()
│  ├─ start_incremental_download()
│  └─ query_historical_data()
│
├─ trading_gateway_service.py    # 交易网关服务
│  └─ 使用TdxDataSource作为行情源
│
└─ strategy_center_service.py    # 策略中心服务
   └─ 使用UnifiedDataManager查询数据
```

**调用方式**:
```python
class DataCenterService(BaseService):
    def _ensure_china_stock_engine(self):
        """获取ChinaStockEngine实例"""
        from backend.core.base import get_china_stock_engine
        self.china_stock_engine = get_china_stock_engine()

    def reload_symbol_list(self) -> Dict[str, Any]:
        """重新加载品种列表"""
        if self.china_stock_engine:
            result = self.china_stock_engine.reload_stock_list()
            return result
        return {"success": False, "message": "引擎未就绪"}
```

#### 3. 核心层调用

```
backend/core/
└─ base.py                       # 系统初始化器
   └─ ServiceInitializer
      ├─ _initialize_vnpy_core()       # 阶段1: 初始化VNPy
      ├─ _initialize_data_services()   # 阶段2: 创建ChinaStockEngine
      ├─ _initialize_trading_services() # 阶段3: 初始化交易服务
      └─ _initialize_auxiliary_services() # 阶段4: 初始化辅助服务
```

**初始化流程**:
```python
def _initialize_data_services(self) -> bool:
    """阶段2: 初始化数据引擎"""
    from backend.infrastructure.data_module_vnpy.core import ChinaStockEngine

    # 创建引擎
    self.china_stock_engine = ChinaStockEngine(
        self.main_engine,
        self.event_engine
    )

    # 注册到全局
    set_china_stock_engine(self.china_stock_engine)

    return True
```

### 调用链路图

```
用户操作 (UI点击)
    ↓
UI视图 (data_center_view.py)
    ├─ 直接调用: engine.reload_stock_list()
    └─ 或通过服务: data_center_service.reload_symbol_list()
        ↓
服务层 (data_center_service.py)
    └─ 调用: china_stock_engine.reload_stock_list()
        ↓
核心引擎 (ChinaStockEngine)
    └─ 委托: symbol_loader.reload_and_classify()
        ↓
品种管理器 (SymbolLoader)
    ├─ 调用: AsyncTdxHq_API.get_security_list()
    ├─ 解析: TdxConfigFileParser
    ├─ 分类: 按规则分类品种
    ├─ 缓存: DailyCacheManager.save_with_date()
    └─ 推送: EventEngine.put(EVENT_CHINASTOCK_LOG)
        ↓
事件引擎 (EventEngine)
    └─ 通知: 所有订阅者（UI、服务）
```

---

## 快速开始

### 安装依赖

```bash
# 安装Python依赖
pip install -r requirements.txt

# 主要依赖包
- vnpy>=4.1.0
- pandas>=1.5.0
- pyarrow>=10.0.0
- watchdog>=3.0.0
- psutil>=5.9.0
```

### 基本使用

#### 方式1: 通过VNPy引擎（推荐）

```python
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from backend.infrastructure.data_module_vnpy import ChinaStockApp

# 1. 创建VNPy主引擎
event_engine = EventEngine()
main_engine = MainEngine(event_engine)

# 2. 添加中国A股数据管理应用
engine = main_engine.add_app(ChinaStockApp)

# 3. 使用数据管理功能
result = engine.reload_stock_list()
engine.download_incremental("2024-01-01")
data = engine.query_data("000001", "1d", "2024-01-01", "2024-12-31")
```

#### 方式2: 直接使用功能模块

```python
from backend.infrastructure.data_module_vnpy import (
    SymbolLoader,
    MultiProcessStockFetcher,
    UnifiedDataManager
)

# 品种管理（不依赖VNPy）
symbol_loader = SymbolLoader()  # 不传event_engine
result = symbol_loader.reload_and_classify()
symbols = symbol_loader.extract_all_codes()

# 数据下载
fetcher = MultiProcessStockFetcher()
results = fetcher.download_incremental_kline(
    symbols=["600000", "000001"],
    start_date="2024-01-01",
    intervals=["1d", "5m"]
)
```

---

## API参考

### ChinaStockEngine

#### 品种管理

```python
# 重新加载品种列表
result = engine.reload_stock_list()
# 返回: {"success": bool, "total_count": int, "empty_categories": List[str]}

# 读取本地缓存
stock_list = engine.refresh_stock_list()

# 获取指定市场品种
shanghai_stocks = engine.get_market_stocks("上证A股")
shenzhen_stocks = engine.get_market_stocks("深证A股")

# 获取所有分类品种
all_stocks = engine.get_all_market_stocks()

# 清除缓存
engine.clear_symbol_cache()
```

#### 数据下载

```python
# 增量下载（从指定日期开始）
success = engine.download_incremental("2024-01-01")

# 下载指定市场
success = engine.download_incremental("2024-01-01", ["上证A股", "深证A股"])

# 下载控制
engine.stop_download()   # 停止下载
engine.pause_download()  # 暂停下载
engine.resume_download() # 恢复下载

# 获取下载进度
progress = engine.get_download_progress()
# 返回: {
#     "is_downloading": bool,
#     "completed": int,
#     "total": int,
#     "progress_percent": float,
#     ...
# }
```

#### 数据查询

```python
# 单品种查询
data = engine.query_data(
    symbol="000001",
    interval="1d",
    start_date="2024-01-01",
    end_date="2024-12-31"
)

# 多品种查询
result = engine.query_data(
    symbols=["000001", "600000"],
    frequency="5m",
    start_date="2024-01-01"
)
# 返回: {"success": bool, "data": {symbol: [...]}, "interval": str}
```

#### 质量管理

```python
# 触发质量扫描
overview = engine.trigger_data_quality_scan(force_refresh=True)

# 获取质量概览
overview = engine.get_data_quality_overview()
# 返回: QualityOverview对象

# 扫描损坏文件
result = engine.scan_corrupted_files(auto_delete=True)
# 返回: {"corrupted": [...], "deleted": [...]}

# 获取校验结果
validation = engine.get_validation_result()
```

#### 系统管理

```python
# 健康检查
result = engine.healthcheck()
# 返回: {"ready": bool, "message": str, "details": {...}}

# 配置管理
config = engine.get_config()
engine.update_config({"chinastock.server_pool_size": 10})
```

---

### SymbolLoader

```python
from backend.infrastructure.data_module_vnpy.data_acquisition.symbol_management import SymbolLoader

# 创建加载器
loader = SymbolLoader(event_engine)  # 带事件推送
# 或
loader = SymbolLoader()  # 纯数据处理

# 重新加载并分类
result = loader.reload_and_classify()
# 返回: {
#     "success": bool,
#     "total_count": int,
#     "classified": {
#         "上证A股": [...],
#         "深证A股": [...],
#         ...
#     }
# }

# 提取品种代码
all_codes = loader.extract_all_codes()
market_codes = loader.extract_codes_by_market(["上证A股", "深证A股"])

# 获取缓存数据
cache = loader.get_cached_data()
```

---

### MultiProcessStockFetcher

```python
from backend.infrastructure.data_module_vnpy.data_acquisition.data_fetcher import (
    MultiProcessStockFetcher,
    download_incremental_unified,
    download_ipo_dates
)

# 创建下载器
fetcher = MultiProcessStockFetcher(event_engine=event_engine)

# K线下载
results = fetcher.download_incremental_kline(
    symbols=["000001", "000002"],
    start_date="2024-01-01",
    intervals=["1d", "5m", "1m"],
    use_adaptive=True,      # 自适应配置（默认）
    use_two_phase=True      # 两段式下载（默认）
)
# 返回: Dict[str, pd.DataFrame]  # 键格式: "品种_周期"

# 统一下载接口（推荐）
result = download_incremental_unified(
    symbols=["600000", "000001"],
    start_date="2024-01-01",
    intervals=["1d", "5m"],
    symbol_loader=symbol_loader,  # 可选，自动提取品种
    market_types=["上证A股"],       # 市场类型筛选
)
# 返回: {
#     "success": bool,
#     "total_tasks": int,
#     "completed": int,
#     "saved_count": int,
#     "message": str
# }

# IPO日期批量下载
result = download_ipo_dates(
    symbols=all_symbols,
    force_refresh=False,    # 增量模式
    use_adaptive=True
)
# 返回: {
#     "success": bool,
#     "total": int,
#     "cached": int,
#     "downloaded": int,
#     "succeeded": int,
#     "data": {symbol: date}
# }
```

---

### UnifiedDataManager

```python
from backend.infrastructure.data_module_vnpy.local_data.unified_data_manager import (
    UnifiedDataManager,
    PreloadService
)

# 创建管理器
manager = UnifiedDataManager(china_stock_engine)

# 统一查询（自动融合四层数据）
data = manager.query_unified(
    symbol="000001",
    interval="1d",
    start_date="2024-01-01",
    end_date="2024-12-31",
    check_gaps=True  # 自动检测缺失并补全
)

# 订阅管理
manager.subscribe(module="strategy", symbols=["000001", "600000"])
manager.unsubscribe(module="strategy")
subscriptions = manager.get_subscriptions()

# 预加载服务
manager.preload_symbols(["000001", "600000"], intervals=["1d", "5m"])
```

---

## 配置说明

### 配置文件位置

```
vt_setting.json  # VNPy全局配置文件
```

### 主要配置项

```python
{
    # 基础配置
    "chinastock.cache_dir": "./data/cache",      # 缓存目录
    "chinastock.data_dir": "./data/kline",       # K线数据目录
    "chinastock.tdx_dir": "C:/new_tdx",         # 通达信目录

    # 服务器池配置
    "chinastock.server_pool.server_count": 132,  # 测速服务器数量
    "chinastock.server_pool.use_multiprocess": true,  # 使用多进程测速
    "chinastock.server_pool.test_timeout": 2.0,  # 测速超时（秒）

    # 热备服务器配置
    "chinastock.standby_servers.count": 30,  # 热备服务器数量
    "chinastock.standby_servers.warmup_timeout": 1.5,  # 预热超时

    # 两段式下载配置
    "chinastock.two_phase_download.enabled": true,  # 启用两段式
    "chinastock.two_phase_download.threshold_ratio": 0.05,  # 阈值比例5%
    "chinastock.two_phase_download.min_threshold": 100,  # 最小阈值100任务

    # 数据质量扫描配置
    "chinastock.quality_scan.enable_adaptive": true,  # 启用自适应
    "chinastock.quality_scan.max_async_workers": 2000,  # 协程最大并发
    "chinastock.quality_scan.max_thread_workers": 50,  # 线程最大并发
    "chinastock.quality_scan.max_process_workers": 16,  # 进程最大并发

    # 预加载配置
    "chinastock.preload.enabled": true,  # 启用预加载
    "chinastock.preload.max_cache_symbols": 64,  # 最大缓存品种数
    "chinastock.preload.intervals": ["1d", "5m"],  # 预加载周期
    "chinastock.preload.frequently_used_symbols": [  # 常用品种
        "000001", "000002", "600000", "600519"
    ]
}
```

### 代码配置

```python
from backend.infrastructure.data_module_vnpy.config import config_manager

# 获取配置
cache_dir = config_manager.get_cache_dir()
data_dir = config_manager.get_data_dir()

# 设置配置
config_manager.set("chinastock.server_pool_size", 10)

# 批量更新
config_manager.update_config({
    "chinastock.server_pool_size": 10,
    "chinastock.timeout": 30
})
```

---

## 性能优化

### 启动性能

| 场景 | 优化前 | 优化后 | 提升 |
|------|-------|-------|------|
| 首次启动 | 9-12秒 | 9-10秒 | 持平 |
| 常规启动 | 9-12秒 | **2-3秒** | **70%+** |
| 次日首次启动 | 9-12秒 | 9-10秒 | 持平 |

**优化点**:
- 智能缓存验证（次日0时失效）
- 并行组件初始化
- 延迟数据质量扫描

---

### 下载性能

| 系统配置 | 并发数 | 5000股票×3周期 | 耗时 | 提升 |
|---------|--------|---------------|------|------|
| 传统方案 | 单进程单线程 | 15000任务 | ~6小时 | - |
| 多线程 | 50线程 | 15000任务 | ~40分钟 | 9倍 |
| **多进程+异步** | **640连接** | **15000任务** | **~1.5分钟** | **240倍** |

**优化点**:
- 多进程架构（充分利用多核CPU）
- 纯异步协程（单进程内高并发）
- 智能负载均衡（根据系统资源动态调整）
- 两段式下载（热备服务器优化）

---

### 质量扫描性能

| 品种数 | 文件数 | 传统方案 | 混合异步架构 | 提升 |
|-------|-------|---------|-------------|------|
| 5000  | 15000 | ~120秒  | **~15秒**   | **8倍** |

**优化点**:
- 混合异步架构（协程+线程+进程）
- 智能自适应（根据文件大小选择处理方式）
- 最大2000并发
- 增量推送（避免UI卡顿）

---

## 维护指南

### 日志配置

日志文件位置: `logs/terminal_v0.50.log`

```python
import logging

# 设置日志级别
logging.getLogger("backend.infrastructure.data_module_vnpy").setLevel(logging.DEBUG)
```

### 缓存清理

```python
from backend.infrastructure.data_module_vnpy.cache_manager import DailyCacheManager

# 删除特定缓存
DailyCacheManager.delete_cache("stock_list_classified.json")

# 获取缓存信息
info = DailyCacheManager.get_cache_info("stock_list_classified.json")
```

### 常见问题

#### 1. 服务器池缓存失效

**问题**: 下载时提示"服务器池缓存不可用"

**解决**:
```python
# 方式1: 通过UI手动测速
# 打开"系统管理" → 点击"测速服务器"

# 方式2: 通过代码触发
from backend.infrastructure.data_module_vnpy import server_pool_manager
server_pool_manager.start()  # 等待5-10秒
```

#### 2. 品种列表缺失

**问题**: 数据下载时提示"品种列表为空"

**解决**:
```python
# 重新加载品种列表
result = engine.reload_stock_list()
```

#### 3. 数据质量扫描卡顿

**问题**: 质量扫描导致系统卡顿

**解决**:
```python
# 调整并发配置
config_manager.update_config({
    "chinastock.quality_scan.max_async_workers": 1000,  # 降低协程数
    "chinastock.quality_scan.max_thread_workers": 20    # 降低线程数
})
```

---

## 技术债务和TODO

### 已完成 ✅

- [x] 从 mootdx 迁移到 tdx_asyncio 纯异步架构
- [x] 智能负载均衡器集成
- [x] 两段式下载机制
- [x] 统一缓存管理（日期失效机制）
- [x] IPO日期批量下载
- [x] 混合异步数据质量扫描
- [x] 文件监控和自动修复

### 计划中 📋

- [ ] 增加数据校验规则（更多逻辑错误检测）
- [ ] 支持更多周期（周线、月线）
- [ ] 增加数据导出功能（CSV、Excel）
- [ ] Web界面支持
- [ ] 数据压缩优化（减少存储空间）

---

## 许可证

本模块为内部使用，未开源。

---

## 联系方式

如有问题或建议，请联系开发团队。

---

**文档版本**: v3.0.0
**生成日期**: 2025-10-23
**文档状态**: ✅ 完整

---

_文档生成完毕_

