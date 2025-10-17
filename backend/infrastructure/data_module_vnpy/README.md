# data_module_vnpy - 中国A股数据管理模块

**版本**: v2.2.0（tdx_asyncio迁移版）
**最后更新**: 2025-10-17
**维护者**: 开发团队

基于vnpy架构的量化交易数据管理模块，集成**tdx_asyncio纯异步接口**获取中国A股数据，提供**历史数据、实时数据集成式的数据服务**，供各个功能模块使用。

## 🎯 核心定位

**data_module_vnpy提供历史数据、实时数据集成式的数据服务，供各个功能模块使用。**

## ⭐ 架构特点（v2.2迁移）

### 核心优化
- **纯异步架构**：从 mootdx 同步接口迁移到 tdx_asyncio 纯异步接口
- **性能提升**：避免 `asyncio.to_thread` 线程开销，提高并发效率
- **简化维护**：删除冗余的 ServerManager 和 TdxDateTimeDecoder 类
- **自动日期处理**：tdx_asyncio 协议层自动处理日期解码

### 模块化设计
- **Core纯接入层**：411行，所有方法1-5行极简代理调用
- **功能模块自治**：每个模块完全独立，可单独使用
- **事件自主推送**：各模块自己管理vnpy事件推送
- **业务逻辑下沉**：所有计算和判断在专门模块中

### 职责清晰
```
core.py (411行)           - vnpy接入层（纯代理）
symbol_management.py (987行) - 品种管理（含事件，使用 tdx_asyncio）
data_fetcher.py (1200行)    - 数据下载（纯异步，使用 tdx_asyncio）
data_quality.py (1233行)    - 数据质量（含文件监控）
unified_data_manager.py (446行) - 统一查询
gateways.py (742行)         - 网关管理
data_readers/tdx_reader.py  - 本地文件读取（使用 tdx_asyncio 读取器）
events.py (216行)           - 事件工具
health_checker.py (84行)    - 健康检查
lifecycle_manager.py (118行) - 生命周期管理
```

## 功能特点

### 核心功能
- **品种列表获取**：支持上证A股、深证A股、北证A股、T+0基金、可转债
- **K线数据下载**：增量下载，支持日线、5分钟、1分钟，多服务器并行优化
- **数据存储**：Parquet列式压缩格式（zstd压缩），高效存储和查询
- **数据感知**：品种缺失、历史缺失、逻辑错误、格式错误检查
- **文件监控**：实时监控数据变化并推送结果
- **轮询转推送网关**：将轮询型数据源转换为推送型，符合vnpy Gateway标准
- **虚拟推送网关**：使用历史数据模拟实时推送，用于回测和测试
- **数据标准化读取**：读取通达信等本地数据文件并标准化保存
- **统一数据管理器**：提供统一的数据查询接口，融合四层数据源
- **预加载服务**：智能预加载常用品种数据，提升查询响应速度

### 技术特点
- **纯异步架构**：基于 tdx_asyncio 的纯异步 API，高效并发
- **智能连接池**：使用 tdx_asyncio 的 AsyncSmartIPPool 管理连接
- **vnpy标准架构**：完全集成vnpy生态系统
- **事件驱动**：基于vnpy事件引擎的异步通知
- **模块自治**：各功能模块可独立使用（vnpy兼容可选）
- **多进程下载**：支持多服务器并行下载，自动任务分配（12进程×30连接=360并发）
- **配置驱动**：所有参数均可配置
- **实时监控**：基于watchdog的文件系统监控
- **四层数据融合**：历史数据、录制数据、实时数据、预加载缓存的智能融合
- **订阅管理**：统一管理各模块的数据订阅需求
- **自动补全**：智能检测数据缺失并自动触发下载

## 安装

### 依赖要求
```bash
pip install -r requirements.txt
```

### 依赖包
- vnpy>=4.1.0
- backend.infrastructure.tdx_asyncio（内部模块，纯异步tdx接口）
- pyarrow>=10.0.0
- watchdog>=3.0.0
- pandas>=1.5.0
- numpy>=1.21.0
- pytdx>=1.72（tdx_asyncio 可能依赖）

**注意**：v2.2.0 已从 mootdx 迁移到 tdx_asyncio，不再需要 mootdx 依赖。

## 快速开始

### 方式1：通过vnpy引擎使用（完整功能）

```python
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from backend.infrastructure.data_module_vnpy import ChinaStockApp

# 创建vnpy主引擎
event_engine = EventEngine()
main_engine = MainEngine(event_engine)

# 添加中国A股数据管理应用
engine = main_engine.add_app(ChinaStockApp)

# 使用数据管理功能（通过core.py代理）
result = engine.reload_stock_list()
engine.download_incremental("2024-01-01")
data = engine.query_data("000001", "1d", "2024-01-01", "2024-12-31")
```

### 方式2：直接使用功能模块（独立使用）

```python
from backend.infrastructure.data_module_vnpy import (
    SymbolLoader,
    download_incremental_unified,
    MultiProcessStockFetcher
)

# 品种管理（不依赖vnpy）
symbol_loader = SymbolLoader()  # 不传event_engine
result = symbol_loader.reload_and_classify()
symbols = symbol_loader.extract_all_codes()

# 数据下载（完全封装，一个函数搞定）
result = download_incremental_unified(
    symbols=["600000", "000001"],
    start_date="2024-01-01",
    num_servers=10,  # 服务器数量
    # 不传event_engine，不推送事件
)

# 或者自动提取品种
result = download_incremental_unified(
    symbols=[],  # 留空
    start_date="2024-01-01",
    num_servers=10,
    symbol_loader=symbol_loader,  # 自动提取品种
    market_types=["上证A股", "深证A股"]
)
```

## 主要功能调用

### 1. 品种列表管理

#### 通过Core.py（推荐）
```python
# 读取本地品种缓存
stock_list = engine.refresh_stock_list()

# 更新品种列表（调用API）
result = engine.reload_stock_list()
# 返回: {"success": bool, "total_count": int, "empty_categories": List[str]}

# 获取指定市场品种
shanghai_stocks = engine.get_market_stocks("上证A股")
shenzhen_stocks = engine.get_market_stocks("深证A股")

# 获取所有分类品种
all_stocks = engine.get_all_market_stocks()

# 清除缓存
engine.clear_symbol_cache()
```

#### 直接使用SymbolLoader
```python
from backend.infrastructure.data_module_vnpy.symbol_management import SymbolLoader

# 创建加载器（可选传入event_engine推送事件）
loader = SymbolLoader(event_engine)  # 带事件推送
# 或
loader = SymbolLoader()  # 纯数据处理

# 重新加载并分类（自动推送事件）
result = loader.reload_and_classify()

# 提取所有品种代码
all_codes = loader.extract_all_codes()

# 按市场类型提取品种
codes = loader.extract_codes_by_market(["上证A股", "深证A股"])
```

---

### 2. K线数据下载

#### 通过Core.py（推荐，带vnpy集成）
```python
# 增量下载K线数据（从指定日期开始）
success = engine.download_incremental("2024-01-01")

# 下载指定市场数据
success = engine.download_incremental("2024-01-01", ["上证A股", "深证A股"])

# 下载控制
engine.stop_download()   # 停止下载
engine.pause_download()  # 暂停下载
engine.resume_download() # 恢复下载

# 获取下载进度
progress = engine.get_download_progress()
# 返回: {"is_downloading": bool, "completed": int, "total": int, ...}
```

#### 直接使用统一下载函数（最灵活）
```python
from backend.infrastructure.data_module_vnpy.data_fetcher import download_incremental_unified
from backend.infrastructure.data_module_vnpy.symbol_management import SymbolLoader

# 完全自动化下载（推荐）
symbol_loader = SymbolLoader()
result = download_incremental_unified(
    symbols=[],  # 留空，自动提取
    start_date="2024-01-01",  # 开始日期
    num_servers=10,  # 服务器数量（1-30）
    symbol_loader=symbol_loader,  # 自动提取品种
    market_types=["上证A股", "深证A股"],  # 市场类型筛选
    # 所有参数封装在一个函数中！
)

# 手动指定品种下载
result = download_incremental_unified(
    symbols=["600000", "000001"],
    start_date="2024-01-01",
    num_servers=10,
)

# 返回详细结果
# {
#     "success": bool,
#     "total_tasks": int,
#     "completed": int,
#     "saved_count": int,
#     "skipped_count": int,
#     "failed_count": int,
#     "message": str
# }
```

#### 使用MultiProcessStockFetcher（异步控制）
```python
from backend.infrastructure.data_module_vnpy.data_fetcher import MultiProcessStockFetcher
from backend.infrastructure.data_module_vnpy.symbol_management import SymbolLoader

# 创建下载器（可选传入event_engine推送事件）
fetcher = MultiProcessStockFetcher(event_engine=event_engine)

# 启动异步下载
symbol_loader = SymbolLoader()
storage_manager = my_storage_manager

success = fetcher.start_incremental_download_async(
    start_date="2024-01-01",
    symbol_loader=symbol_loader,
    storage_manager=storage_manager,
    market_types=["上证A股"]
)

# 控制下载
fetcher.stop_download()
fetcher.pause_download()
fetcher.resume_download()
progress = fetcher.get_download_progress()
```

---

### 3. 数据查询

#### 通过Core.py（推荐）
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

#### 直接使用UnifiedDataManager
```python
# 获取统一数据管理器
manager = engine.get_unified_data_manager()

# 单品种查询（融合四层数据源）
data = manager.query_unified(
    symbol="000001",
    interval="1d",
    start_date="2024-01-01",
    check_gaps=True  # 自动检测缺失并补全
)

# 订阅管理
manager.subscribe(module="my_module", symbols=["000001", "600000"])
manager.unsubscribe(module="my_module")
```

---

### 4. 数据质量管理

#### 通过Core.py
```python
# 手动触发质量扫描
overview = engine.trigger_data_quality_scan(force_refresh=True)

# 获取质量概览
overview = engine.get_data_quality_overview()
# 返回: QualityOverview对象（quality_score, missing_symbols等）

# 扫描并修复损坏文件
result = engine.scan_corrupted_files(auto_delete=True)
# 返回: {"corrupted": [...], "deleted": [...]}

# 获取校验结果
validation = engine.get_validation_result()
```

#### 直接使用DataSensor
```python
from backend.infrastructure.data_module_vnpy.data_quality import DataSensor
from backend.infrastructure.data_module_vnpy.symbol_management import SymbolLoader

# 创建数据感知器
sensor = DataSensor(event_engine)

# 触发扫描（自动获取品种列表）
symbol_loader = SymbolLoader()
overview = sensor.trigger_scan_with_symbols(
    symbol_loader=symbol_loader,
    force_refresh=True
)

# 启动异步感知（后台扫描+文件监控）
sensor.start_sensing_async(symbol_loader)

# 停止感知
sensor.stop_sensing()
```

---

### 5. 网关管理

#### 通过Core.py（推荐）
```python
# 启动轮询网关
setting = {
    "轮询间隔（秒）": 60,
    "品种列表": "000001,600000"
}
success = engine.start_polling_gateway(setting)

# 启动虚拟网关（回放）
success = engine.start_virtual_gateway(
    start_datetime="2024-01-01 09:30:00",
    speed=2.0,
    symbols=["000001", "600000"]
)

# 停止网关
engine.stop_polling_gateway()
engine.stop_virtual_gateway()
```

#### 直接使用GatewayManager
```python
from backend.infrastructure.data_module_vnpy.gateways import GatewayManager

# 启动轮询网关
gateway = GatewayManager.start_polling(event_engine, setting={"轮询间隔（秒）": 60})

# 启动虚拟网关
gateway = GatewayManager.start_virtual(
    event_engine,
    start_datetime="2024-01-01 09:30:00",
    speed=2.0,
    symbols=["000001"]
)

# 停止网关
GatewayManager.stop_polling(gateway)
GatewayManager.stop_virtual(gateway)
```

---

### 6. 健康检查和配置

```python
# 健康检查
result = engine.healthcheck()
# 返回: {"ready": bool, "message": str, "details": {...}}

# 或直接使用
from backend.infrastructure.data_module_vnpy.health_checker import HealthChecker
result = HealthChecker.check_system_health()

# 配置管理
config = engine.get_config()
engine.update_config({"chinastock.server_pool_size": 10})
```

## 模块结构

```
data_module_vnpy/
│
├── 核心接入层
│   └── core.py (411行) - ChinaStockEngine（vnpy接入，纯代理）
│
├── 功能模块层（自治模块）
│   ├── symbol_management.py (987行) - 品种管理
│   │   ├── SymbolLoader - 品种加载、分类、缓存
│   │   ├── BlockParser - 板块解析
│   │   └── 自带事件推送 ✓
│   │
│   ├── data_fetcher.py (1200行) - 数据下载（纯异步）
│   │   ├── MultiProcessStockFetcher - 多进程下载器
│   │   ├── download_incremental_unified - 统一下载函数
│   │   ├── download_worker_async - 纯异步工作进程
│   │   ├── _download_single_kline_async - 纯异步单品种下载
│   │   ├── 使用 tdx_asyncio.AsyncTdxHq_API
│   │   ├── 使用 tdx_asyncio 智能IP池（HQ_HOSTS_ALL）
│   │   └── 自带事件推送 ✓
│   │
│   ├── data_quality.py (1233行) - 数据质量
│   │   ├── DataSensor - 数据感知
│   │   ├── StorageManager - 存储管理
│   │   ├── DataValidator - 数据校验
│   │   ├── DataFileWatcher - 文件监控
│   │   └── 自带事件推送 ✓
│   │
│   ├── unified_data_manager.py (446行) - 统一查询
│   │   └── UnifiedDataManager - 四层数据融合、订阅管理
│   │
│   ├── gateways.py (742行) - 网关管理
│   │   ├── GatewayManager - 网关生命周期管理
│   │   ├── PollingGateway - 轮询网关
│   │   ├── VirtualGateway - 虚拟网关
│   │   └── 自带事件推送 ✓
│   │
│   └── preload_service.py (188行) - 预加载服务
│       └── PreloadService - 智能预加载
│
├── 工具和基础设施层
│   ├── events.py (216行) - 事件工具
│   │   ├── 事件常量（EVENT_CHINASTOCK_LOG等）
│   │   ├── APP_NAME
│   │   ├── EventPublisher - 通用事件发布器
│   │   ├── ValidationEventPublisher - 校验事件
│   │   ├── DownloadEventPublisher - 下载事件
│   │   └── QualityEventPublisher - 质量事件
│   │
│   ├── health_checker.py (84行) - 健康检查
│   │   └── HealthChecker - 系统健康检查
│   │
│   ├── lifecycle_manager.py (118行) - 生命周期
│   │   └── LifecycleManager - 延迟初始化、组件关闭
│   │
│   ├── config.py - 配置管理
│   │   ├── ConfigManager - 配置读取/写入
│   │   └── TdxConfigFileParser - 通达信配置解析
│   │
│   └── data_readers/ - 数据读取器
│       ├── TdxBinaryReader - 通达信二进制文件读取
│       └── BaseReader - 读取器基类
│
└── __init__.py - 模块导出
```

## 调用关系

```
外部调用（Service层/UI层）
        ↓
┌───────────────────────┐
│   core.py (411行)     │ ← vnpy接入层（纯代理）
│  ChinaStockEngine     │
└───────────────────────┘
        ↓ 代理调用（1-5行）
┌───────────────────────────────────────────┐
│          功能模块层（自治）                 │
├───────────────────────────────────────────┤
│ symbol_management.py  │ data_fetcher.py   │
│ data_quality.py       │ gateways.py       │
│ unified_data_manager  │ preload_service   │
└───────────────────────────────────────────┘
        ↓ 依赖
┌───────────────────────────────────────────┐
│          工具和基础设施层                   │
├───────────────────────────────────────────┤
│ events.py            │ health_checker.py  │
│ lifecycle_manager.py │ config.py          │
│ data_readers/                             │
└───────────────────────────────────────────┘
```

## 配置说明

### 配置文件位置
配置保存在vnpy的 `vt_setting.json` 文件中。

### 主要配置项

```json
{
  "chinastock.cache_dir": "./data/cache",
  "chinastock.data_dir": "./data/kline",
  "chinastock.tdx_dir": "C:/通达信金融终端V7",
  "chinastock.server_pool_size": 5,
  "chinastock.watcher_enabled": false,
  "chinastock.watcher_interval": 5,
  "chinastock.polling_gateway.enabled": false,
  "chinastock.polling_gateway.interval": 60,
  "chinastock.virtual_gateway.enabled": false,
  "chinastock.preload.enabled": true,
  "chinastock.preload.auto_start": false,
  "chinastock.unified_manager.enabled": true,
  "chinastock.unified_manager.auto_download": true
}
```

### 配置说明

| 配置项 | 类型 | 默认值 | 说明 |
|--------|-----|--------|------|
| cache_dir | Path | ./data/cache | 品种列表缓存目录 |
| data_dir | Path | ./data/kline | K线数据存储目录 |
| tdx_dir | Path | 自动搜索 | 通达信软件根目录 |
| server_pool_size | int | 5 | 并行下载服务器数量（1-30） |
| watcher_enabled | bool | false | 是否启用文件监控 |
| polling_gateway.enabled | bool | false | 是否启用轮询网关 |
| virtual_gateway.enabled | bool | false | 是否启用虚拟网关 |
| preload.enabled | bool | true | 是否启用预加载服务 |
| unified_manager.enabled | bool | true | 是否启用统一数据管理器 |

## 事件系统

### 事件类型

模块支持以下vnpy事件：

| 事件类型 | 常量 | 说明 |
|---------|-----|------|
| 日志事件 | EVENT_CHINASTOCK_LOG | 通用日志消息 |
| 校验事件 | EVENT_CHINASTOCK_VALIDATION | 数据校验结果 |
| 下载事件 | EVENT_CHINASTOCK_DOWNLOAD | 下载状态和进度 |
| 质量事件 | EVENT_DATA_QUALITY_UPDATE | 数据质量更新 |
| 扫描事件 | EVENT_DATA_SCAN_COMPLETE | 质量扫描完成 |
| 文件事件 | EVENT_CHINASTOCK_FILE_CHANGE | 文件变化 |

### 订阅事件

```python
from backend.infrastructure.data_module_vnpy.events import EVENT_CHINASTOCK_DOWNLOAD

# 定义事件处理器
def process_download_event(event):
    data = event.data
    print(f"下载状态: {data['status']}, 数量: {data['count']}")

# 注册事件处理器
event_engine.register(EVENT_CHINASTOCK_DOWNLOAD, process_download_event)
```

## 高级用法

### 自定义下载参数

```python
from backend.infrastructure.data_module_vnpy.data_fetcher import download_incremental_unified

# 完全自定义下载
result = download_incremental_unified(
    symbols=["600000"],
    start_date="2024-01-01",
    intervals=["1d", "5m"],  # 自定义周期
    num_servers=15,  # 15个并行服务器
    symbol_loader=None,  # 不自动提取
    storage_callback=custom_storage_func,  # 自定义存储
    progress_callback=custom_progress_func,  # 自定义进度回调
    event_callback=custom_event_func  # 自定义事件回调
)
```

### 独立使用各模块（不依赖vnpy）

```python
# 1. 品种管理
from backend.infrastructure.data_module_vnpy.symbol_management import SymbolLoader
loader = SymbolLoader()  # 不传event_engine
codes = loader.extract_all_codes()

# 2. 数据下载
from backend.infrastructure.data_module_vnpy.data_fetcher import download_incremental_unified
result = download_incremental_unified(
    symbols=codes,
    start_date="2024-01-01",
    num_servers=10
    # 不传event_engine，不推送事件
)

# 3. 数据质量
from backend.infrastructure.data_module_vnpy.data_quality import DataSensor
sensor = DataSensor()  # 不传event_engine
overview = sensor.trigger_scan_with_symbols(loader)
```

## 架构设计原则

### 1. 单一职责
- 每个模块只负责一个功能领域
- Core只做vnpy接入，不包含业务逻辑

### 2. 模块自治
- 每个模块可独立使用
- 自己管理事件推送（可选）
- 不强依赖core或其他模块

### 3. 业务逻辑下沉
- 所有计算、判断、循环在专门模块
- Core方法只有1-5行代理调用
- 便于Debug和测试

### 4. 向后兼容
- Service层调用接口不变
- 只改变内部实现
- 平滑升级

## 性能优化

### 多服务器并行下载
```python
# 配置更多服务器加速下载
engine.update_config({"chinastock.server_pool_size": 20})

# 或直接指定
download_incremental_unified(
    symbols=["600000"],
    start_date="2024-01-01",
    num_servers=20  # 20个并行服务器
)
```

### 预加载服务
```python
# 启用预加载（在配置中）
{
    "chinastock.preload.enabled": true,
    "chinastock.preload.auto_start": true,
    "chinastock.preload.max_workers": 4,
    "chinastock.preload.cache_size": 100
}

# 手动刷新预加载
manager = engine.get_unified_data_manager()
manager.refresh_preload(["000001", "600000"], priority=True)
```

## 数据存储格式

### 目录结构
```
data/kline/
├── 000001/
│   ├── 1d.parquet
│   ├── 5m.parquet
│   └── 1m.parquet
├── 600000/
│   ├── 1d.parquet
│   ├── 5m.parquet
│   └── 1m.parquet
└── ...
```

### Parquet格式
- **压缩算法**：zstd（高压缩比）
- **列格式**：datetime, open, high, low, close, volume, turnover, symbol, interval
- **索引**：datetime列
- **优势**：高效压缩、快速查询、列式存储

## 重构成果

### v2.2.0 - tdx_asyncio迁移
- **data_fetcher.py**：从1591行减少到约1200行（-25%）
- **删除冗余类**：ServerManager（130行）、TdxDateTimeDecoder（90行）
- **性能提升**：纯异步API，避免线程开销
- **维护性**：统一使用 tdx_asyncio，简化依赖

### v2.1.0 - 模块化重构
- **Core精简**：从1459行减少到411行（-71.8%）
- **新增模块**：events.py, health_checker.py, lifecycle_manager.py
- **增强模块**：所有功能模块都vnpy兼容，可独立使用
- **删除冗余**：download_manager.py（已合并到data_fetcher.py）

### 代码质量
- ✅ 所有Core方法1-5行
- ✅ 业务逻辑100%下沉
- ✅ 无Linter错误
- ✅ 无循环导入
- ✅ Service层完全兼容
- ✅ 纯异步架构（v2.2.0）

## 常见问题

### Q1: 如何只下载指定日期范围的数据？
```python
# download_incremental_unified会自动计算bar数量
result = download_incremental_unified(
    symbols=["600000"],
    start_date="2024-01-01",  # 只需指定开始日期
    # 函数会自动计算到今天需要多少bar
)
```

### Q2: 如何配置服务器数量？
```python
# 方式1：通过配置
engine.update_config({"chinastock.server_pool_size": 15})

# 方式2：直接在下载函数中指定
download_incremental_unified(
    symbols=["600000"],
    start_date="2024-01-01",
    num_servers=15  # 直接指定
)
```

### Q3: 如何不依赖vnpy使用？
```python
# 所有功能模块都支持独立使用，不传event_engine即可
from backend.infrastructure.data_module_vnpy.symbol_management import SymbolLoader
from backend.infrastructure.data_module_vnpy.data_fetcher import download_incremental_unified

loader = SymbolLoader()  # 不传event_engine
result = download_incremental_unified(...)  # 不会推送vnpy事件
```

### Q4: Core.py还有业务逻辑吗？
```
没有！Core.py现在是纯vnpy接入层：
- 所有方法1-5行
- 只做组件初始化和代理调用
- 无任何业务判断、循环、计算
```

## 开发指南

### 添加新功能
1. 在对应的功能模块中添加（不要在core.py）
2. 如需vnpy集成，使用EventPublisher
3. 在core.py添加一行代理方法

### Debug技巧
- 业务逻辑在专门模块，直接打断点
- Core只是入口，跳过即可
- 每个模块可独立测试

### 测试建议
```python
# 单元测试（不依赖vnpy）
def test_symbol_loader():
    loader = SymbolLoader()  # 不传event_engine
    result = loader.reload_and_classify()
    assert result["success"]

# 集成测试（完整vnpy环境）
def test_with_engine():
    engine = create_china_stock_engine()
    result = engine.reload_stock_list()
    assert result["success"]
```

## 更新日志

### v2.2.0 (2025-10-17) - tdx_asyncio迁移版 🚀
**核心变更**：从 mootdx 同步接口迁移到 tdx_asyncio 纯异步接口

#### 主要改进
- ✅ **data_fetcher.py** 迁移
  - 删除 `ServerManager` 类（使用 tdx_asyncio.AsyncSmartIPPool）
  - 删除 `TdxDateTimeDecoder` 类（tdx_asyncio 协议层自动处理）
  - 重写 `download_worker_async` 使用 `AsyncTdxHq_API`
  - 新增 `_download_single_kline_async` 纯异步下载函数
  - 使用 `HQ_HOSTS_ALL` 服务器列表（前50个服务器）

- ✅ **symbol_management.py** 迁移
  - 重写 `_fetch_complete_stocks` 使用 `AsyncTdxHq_API.get_security_list()`
  - 支持分页获取品种列表（每次1000条）
  - 通过 `asyncio.run()` 保持向后兼容

- ✅ **data_readers/tdx_reader.py** 迁移
  - 替换 `mootdx.reader.Reader` 为 tdx_asyncio 异步读取器
  - 使用 `read_day_data()`, `read_minute_data()`, `read_lc5_data()`
  - 保持北证市场（bj）自定义解码器

- ✅ **依赖更新**
  - 移除 `mootdx>=0.11.7` 依赖
  - 改用内部 `tdx_asyncio` 模块

#### 性能优势
- 🚀 **纯异步 API**：避免 `asyncio.to_thread` 线程开销
- 🚀 **连接复用**：使用 tdx_asyncio 的智能连接池
- 🚀 **自动日期解码**：无需手动处理日期格式
- 🚀 **并发模型**：12进程×30连接=360个TCP并发连接

#### 架构优化
- 🎯 **代码简化**：删除约400行冗余代码
- 🎯 **维护性提升**：统一使用 tdx_asyncio API
- 🎯 **向后兼容**：外部接口完全不变

### v2.1.0 (2025-01-16) - 模块化重构版
- ✅ Core精简：从1459行减少到411行（-71.8%）
- ✅ 业务逻辑下沉：所有计算逻辑移到专门模块
- ✅ 模块自治：各模块可独立使用，自己管理事件
- ✅ 新增模块：events.py, health_checker.py, lifecycle_manager.py
- ✅ 合并冗余：download_manager.py合并到data_fetcher.py
- ✅ 统一接口：download_incremental_unified完全封装下载逻辑
- ✅ 向后兼容：Service层调用接口完全不变

### v2.0.0 (2025-01-15)
- 统一数据管理器集成
- 预加载服务支持
- 四层数据融合

### v1.0.0
- 基础功能实现

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request！

## 联系方式

项目主页：[项目链接]
