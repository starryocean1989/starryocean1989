# -*- coding: utf-8 -*-
# 统一数据管理器 API 文档

## 📋 概述

统一数据管理器（UnifiedDataManager）是数据管理中枢，集成了TDX数据源和虚拟数据源，提供查询式和订阅式两种数据服务方式。

## 🏗️ 架构变更

### 重命名和整合

| 原名称 | 新名称 | 说明 |
|-------|--------|------|
| `PollingGateway` | `TdxDataSource` | TDX数据源（请求/推送双模式） |
| `VirtualGateway` | `VirtualDataSource` | 虚拟数据源（回测模拟） |
| `gateways.py` | `unified_data_manager.py` | 合并到统一数据管理器 |

**向后兼容**：旧名称作为别名保留，现有代码无需修改即可运行。

### 文件位置

```
backend/infrastructure/data_module_vnpy/
├── local_data/
│   └── unified_data_manager.py  ← 新的统一位置
└── data_acquisition/
    └── gateways.py  ← 已删除
```

## 🚀 新特性：ServerPoolManager集成

### TdxDataSource架构升级

TdxDataSource已集成ServerPoolManager和真实tdx_asyncio API，实现：

1. **智能服务器选择**：自动测速并选择最优服务器
2. **权重轮询负载均衡**：根据响应时间分配请求
3. **真实API调用**：使用AsyncTdxHq_API.get_security_quotes()获取实时行情
4. **自动故障切换**：服务器失败时自动切换到下一个

### 权重轮询算法

```python
# 服务器响应时间 → 权重
response_times = [0.050, 0.100, 0.200]  # 秒
weights = [1/0.050, 1/0.100, 1/0.200]   # [20, 10, 5]
normalized = [20/35, 10/35, 5/35]       # [0.57, 0.29, 0.14]

# 最快服务器被选中概率为57%，次快29%，最慢14%
```

### 真实API调用流程

```
订阅请求 → TdxDataSource.subscribe()
          → 启动轮询线程
          → 每N秒轮询一次（默认3秒）
          → 权重轮询选择最优服务器
          → AsyncTdxHq_API.get_security_quotes()
          → 转换为vnpy TickData格式
          → EventEngine推送（EVENT_TICK）
          → 交易策略接收
```

### 配置示例

```python
# 启动TDX数据源（带服务器池）
manager.start_tdx_source({
    "polling_interval": 3.0,      # 轮询间隔（秒）
    "symbols": ["000001", "600000"],  # 订阅品种
    "max_servers": 5              # 使用最优的5个服务器
})
```

## 📚 核心类

### 1. UnifiedDataManager - 统一数据管理中枢

#### 初始化

```python
from backend.infrastructure.data_module_vnpy.local_data.unified_data_manager import UnifiedDataManager

manager = UnifiedDataManager(
    engine=china_stock_engine,
    preload_service=preload_service  # 可选
)
```

#### 查询式接口（给行情看板、策略中心）

##### get_kline_data() - K线数据查询

```python
# 查询单个品种的K线数据
df = manager.get_kline_data(
    symbol="000001",
    interval="1d",
    start_date="2025-01-01",
    end_date="2025-10-21",
    check_gaps=True,        # 检查缺口并自动下载
    use_preload=True        # 使用预加载缓存
)
```

**数据融合顺序**：
1. 预加载缓存
2. 本地存储
3. 录制数据
4. 实时数据
5. 自动去重和排序

##### get_multi_kline_data() - 批量查询

```python
# 批量查询多个品种
result = manager.get_multi_kline_data(
    symbols=["000001", "600000", "000002"],
    interval="1d",
    start_date="2025-01-01",
    end_date="2025-10-21"
)
# 返回: {"000001": DataFrame, "600000": DataFrame, ...}
```

##### query_unified() - 统一查询接口（兼容旧代码）

```python
# 单品种查询
df = manager.query_unified(
    symbol="000001",
    interval="1d",
    start_date="2025-01-01"
)

# 多品种查询
result = manager.query_unified(
    symbols=["000001", "600000"],
    interval="1d"
)
# 返回: {"success": True, "data": {...}, "interval": "1d"}
```

#### 订阅式接口（给交易策略）

##### subscribe() - 订阅实时数据

```python
# 订阅品种，自动路由到合适的数据源
success = manager.subscribe(
    module="trading_strategy",  # 模块标识
    symbols=["000001", "600000"]  # 品种列表
)
```

**自动路由规则**：
- `backtest`, `replay`, `virtual` → 虚拟数据源
- `trading`, `strategy` → TDX数据源
- 其他 → TDX数据源

##### unsubscribe() - 取消订阅

```python
# 取消特定品种的订阅
manager.unsubscribe(
    module="trading_strategy",
    symbols=["000001"]
)

# 取消该模块的所有订阅
manager.unsubscribe(
    module="trading_strategy",
    symbols=None
)
```

#### 数据源管理接口

##### start_tdx_source() - 启动TDX数据源

```python
# 启动TDX数据源（请求/推送双模式）
success = manager.start_tdx_source(config={
    "interval": 60,  # 轮询间隔（秒）
    "symbols": ["000001", "600000"]  # 订阅品种
})
```

##### stop_tdx_source() - 停止TDX数据源

```python
success = manager.stop_tdx_source()
```

##### start_virtual_source() - 启动虚拟数据源

```python
# 启动虚拟数据源（回测模拟）
success = manager.start_virtual_source(config={
    "start_datetime": "2025-01-01 09:30:00",  # 起始时间
    "speed": 1.0,  # 推送速度（1.0=实时，2.0=2倍速）
    "symbols": ["000001", "600000"]  # 订阅品种
})
```

##### stop_virtual_source() - 停止虚拟数据源

```python
success = manager.stop_virtual_source()
```

##### connect_external_gateway() - 连接外部网关

```python
# 连接外部交易网关（CTP、IB等）
from vnpy_ctp import CtpGateway

ctp_gateway = CtpGateway(event_engine, "CTP")
success = manager.connect_external_gateway("ctp_main", ctp_gateway)
```

### 2. TdxDataSource - TDX数据源（集成ServerPoolManager）

继承自 `vnpy.trader.gateway.BaseGateway`

#### 特点
- 集成ServerPoolManager（自动测速选择最优服务器）
- 权重轮询负载均衡（最快服务器优先）
- 真实API调用（AsyncTdxHq_API.get_security_quotes）
- 交易时间自动轮询，非交易时间停止
- 支持推送和请求双模式
- 自动故障切换

#### 核心属性
- `server_pool_manager`: ServerPoolManager实例
- `_api_connections`: AsyncTdxHq_API连接池（每个服务器一个连接）
- `_server_weights`: 服务器权重列表
- `_subscribed_symbols`: 已订阅品种集合
- `_polling_interval`: 轮询间隔（默认3秒）

#### 使用示例

```python
from backend.infrastructure.data_module_vnpy.local_data.unified_data_manager import TdxDataSource

# 创建并启动（自动连接最优服务器）
tdx_source = TdxDataSource.create_and_start(
    event_engine=event_engine,
    setting={
        "轮询间隔（秒）": 3,         # 轮询间隔（秒）
        "品种列表": "000001,600000",  # 订阅品种
        "最大服务器数": 5            # 使用最优的5个服务器
    }
)

# 订阅品种（动态添加）
from vnpy.trader.object import SubscribeRequest
from vnpy.trader.constant import Exchange

req = SubscribeRequest(symbol="000002", exchange=Exchange.SZSE)
tdx_source.subscribe(req)

# 取消订阅
tdx_source.unsubscribe(req)

# 关闭（自动关闭所有API连接）
tdx_source.close()
```

#### 配置说明

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|-------|------|
| `轮询间隔（秒）` | int | 3 | 轮询间隔，建议不低于3秒 |
| `品种列表` | str | "" | 逗号分隔的品种代码 |
| `最大服务器数` | int | 5 | 使用的最优服务器数量 |

### 3. VirtualDataSource - 虚拟数据源（增强回放控制）

继承自 `vnpy.trader.gateway.BaseGateway`

#### 特点
- 从本地数据库加载历史数据
- 模拟实时推送
- 可配置起始时间和推送速度（0.1x ~ 1000x）
- 支持暂停/恢复/跳转
- 支持历史回放

#### 核心属性
- `start_datetime`: 起始时间
- `push_speed`: 推送速度倍率（1.0=实时，10.0=10倍速）
- `historical_data`: 历史数据缓存（DataFrame格式）
- `push_positions`: 每个品种的推送位置索引
- `_is_paused`: 暂停状态

#### 使用示例

```python
from backend.infrastructure.data_module_vnpy.local_data.unified_data_manager import VirtualDataSource

# 创建并启动
virtual_source = VirtualDataSource.create_and_start(
    event_engine=event_engine,
    start_datetime="2025-01-01 09:30:00",
    speed=2.0,  # 2倍速
    symbols=["000001", "600000"]
)

# 回放控制
virtual_source.pause()                      # 暂停推送
virtual_source.resume()                     # 恢复推送
virtual_source.set_speed(10.0)              # 设置为10倍速
virtual_source.jump_to_datetime(
    datetime(2025, 1, 15, 9, 30)           # 跳转到指定时间
)

# 获取当前回放时间
current_time = virtual_source.get_current_datetime()

# 关闭
virtual_source.close()
```

#### 回放控制API

| 方法 | 参数 | 说明 |
|-----|------|------|
| `pause()` | - | 暂停推送 |
| `resume()` | - | 恢复推送 |
| `set_speed(speed)` | speed: float (0.1~1000) | 设置推送速度 |
| `jump_to_datetime(dt)` | dt: datetime | 跳转到指定时间 |
| `get_current_datetime()` | - | 获取当前回放时间 |

### 4. PreloadService - 预加载服务

#### 使用示例

```python
from backend.infrastructure.data_module_vnpy.local_data.unified_data_manager import PreloadService

# 创建预加载服务
preload_service = PreloadService(china_stock_engine)

# 启动服务
preload_service.start(prime=True)  # prime=True会预加载常用品种

# 手动触发预加载
preload_service.enqueue("000001", intervals=["1d", "5m"], priority=True)

# 获取缓存
df = preload_service.get_cached_dataframe("000001", "1d")

# 获取统计信息
stats = preload_service.get_stats()
# 返回: {"cache_hits": 100, "cache_misses": 5, "cached_symbols": 10, ...}

# 停止服务
preload_service.stop()
```

## 🔄 迁移指南

### 服务层迁移

#### DataCenterService

**旧代码（仍然有效）**：
```python
from backend.infrastructure.data_module_vnpy.data_acquisition.gateways import PollingGateway, VirtualGateway
```

**新代码（推荐）**：
```python
from backend.infrastructure.data_module_vnpy.local_data.unified_data_manager import (
    TdxDataSource,
    VirtualDataSource
)
```

**或使用别名（向后兼容）**：
```python
from backend.infrastructure.data_module_vnpy.local_data.unified_data_manager import (
    PollingGateway,  # 别名指向TdxDataSource
    VirtualGateway   # 别名指向VirtualDataSource
)
```

#### 方法调用

**旧方法（仍然有效）**：
- `data_center_service.start_polling_gateway(config)`
- `data_center_service.stop_polling_gateway()`
- `data_center_service.start_virtual_gateway(config)`
- `data_center_service.stop_virtual_gateway()`

**新方法（推荐）**：
- `unified_data_manager.start_tdx_source(config)`
- `unified_data_manager.stop_tdx_source()`
- `unified_data_manager.start_virtual_source(config)`
- `unified_data_manager.stop_virtual_source()`

### UI层迁移

#### 显示名称更新

| 原名称 | 新名称 |
|-------|--------|
| "轮询转推送" | "TDX数据源（请求/推送双模式）" |
| "虚拟推送" | "虚拟数据源（回测模拟）" |

UI代码无需修改接口调用，服务层已处理兼容性。

### 配置文件迁移

**旧配置**（仍然有效）：
```json
{
  "chinastock.polling_gateway.symbols": ["000001", "600000"],
  "chinastock.virtual_gateway.symbols": ["000001"]
}
```

**新配置**（推荐）：
```json
{
  "chinastock.tdx_source.symbols": ["000001", "600000"],
  "chinastock.virtual_source.symbols": ["000001"]
}
```

系统会自动兼容旧配置。

## ⚠️ 注意事项

### 1. 向后兼容性

- 所有旧代码保持100%兼容
- 旧的类名作为别名保留
- 旧的方法调用仍然有效
- 配置文件自动兼容

### 2. 推荐的最佳实践

```python
# ✅ 推荐：使用UnifiedDataManager统一管理
unified_manager = UnifiedDataManager(engine)

# 查询数据
df = unified_manager.get_kline_data("000001", interval="1d")

# 订阅数据
unified_manager.subscribe("trading_strategy", ["000001"])

# 启动数据源
unified_manager.start_tdx_source({"interval": 60})
```

```python
# ❌ 不推荐：直接使用数据源类（除非有特殊需求）
tdx_source = TdxDataSource(event_engine, "TDX")
tdx_source.connect(setting)
```

### 3. vnpy架构集成

- 数据源类继承自 `vnpy.trader.gateway.BaseGateway`
- 遵循vnpy事件驱动架构
- 使用vnpy标准的 `SubscribeRequest` 和 `TickData`
- 完全兼容vnpy的Gateway管理机制

## 📞 技术支持

如有问题，请参考：
- 源码：`backend/infrastructure/data_module_vnpy/local_data/unified_data_manager.py`
- 测试：`tests/test_unified_data_manager.py`（TODO）
- 文档：`backend/infrastructure/data_module_vnpy/README.md`

## 🔖 版本历史

### v2.0.0 (2025-10-21)
- ✅ 合并gateways.py到unified_data_manager.py
- ✅ 重命名PollingGateway → TdxDataSource
- ✅ 重命名VirtualGateway → VirtualDataSource
- ✅ 增强UnifiedDataManager功能
- ✅ 提供向后兼容别名
- ✅ 更新服务层和UI层
- ✅ 完整的API文档

---

**最后更新**: 2025-10-21
**维护者**: 开发团队

