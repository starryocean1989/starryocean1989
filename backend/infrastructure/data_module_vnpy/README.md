# data_module_vnpy - 中国A股数据管理模块

基于vnpy架构的量化交易数据管理模块，集成mootdx接口获取中国A股数据，支持品种列表获取、K线数据下载、数据存储、数据感知等功能。

## 功能特点

### 核心功能
- **品种列表获取**：支持上证A股、深证A股、北证A股、T+0基金、含可转债
- **K线数据下载**：全量下载和增量下载，支持日线、5分钟、1分钟，多服务器并行优化
- **数据存储**：Parquet列式压缩格式（zstd压缩），高效存储和查询
- **数据感知**：品种缺失、历史缺失、逻辑错误、格式错误检查
- **文件监控**：实时监控数据变化并推送结果
- **轮询转推送网关**：将轮询型数据源转换为推送型，符合vnpy Gateway标准（v2.0新增）
- **虚拟推送网关**：使用历史数据模拟实时推送，用于回测和测试（v2.0新增）
- **数据标准化读取**：读取通达信等本地数据文件并标准化保存（v2.0新增）

### 技术特点
- **vnpy标准架构**：完全集成vnpy生态系统
- **事件驱动**：基于vnpy事件引擎的异步通知
- **多线程处理**：并发下载和校验，提高效率
- **配置驱动**：所有参数均可配置
- **实时监控**：基于watchdog的文件系统监控

## 安装

### 依赖要求
```bash
pip install -r requirements.txt
```

### 依赖包
- vnpy>=4.1.0
- mootdx>=0.11.7
- pyarrow>=10.0.0
- watchdog>=3.0.0
- pandas>=1.5.0
- numpy>=1.21.0
- pytdx>=1.72

## 使用方法

### 基本集成
```python
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from data_module_vnpy import ChinaStockApp

# 创建vnpy主引擎
event_engine = EventEngine()
main_engine = MainEngine(event_engine)

# 添加中国A股数据管理应用
engine = main_engine.add_app(ChinaStockApp)

# 使用数据管理功能
```

### 主要功能调用

#### 1. 品种列表管理
```python
# 读取本地品种缓存
stock_list = engine.refresh_stock_list()

# 更新品种列表（调用API）
success = engine.reload_stock_list()

# 获取指定市场品种
shanghai_stocks = engine.get_market_stocks("上证A股")
shenzhen_stocks = engine.get_market_stocks("深证A股")
```

#### 2. K线数据下载
```python
# 全量下载K线数据
success = engine.download_full()

# 增量下载K线数据（从指定日期开始）
success = engine.download_incremental("2024-01-01")

# 下载指定市场数据
success = engine.download_full(["上证A股", "深证A股"])
```

#### 3. 数据查询
```python
# 查询K线数据
data = engine.query_data("000001", "1d", "2024-01-01", "2024-01-31")

# 查询指定品种所有周期
intervals = engine.storage_manager.list_intervals("000001")
```

#### 4. 数据感知
```python
# 获取数据校验结果
validation_result = engine.get_validation_result()

# 强制刷新校验结果
validation_result = engine.get_validation_result(force_refresh=True)

# 校验指定品种
result = engine.validator.validate_symbol("000001", "1d")
```

#### 5. 配置管理
```python
# 获取当前配置
config = engine.get_config()

# 更新配置
new_config = {
    "chinastock.cache_dir": "./data/cache",
    "chinastock.data_dir": "./data/kline",
    "chinastock.tdx_dir": "C:/通达信金融终端V7"
}
engine.update_config(new_config)
```

#### 6. 轮询转推送网关（v2.0新增）
```python
# 启动轮询网关
setting = {
    "轮询间隔（秒）": 60,
    "品种列表": "000001,600000,600036"  # 逗号分隔
}
engine.start_polling_gateway(setting)

# 停止轮询网关
engine.stop_polling_gateway()
```

#### 7. 虚拟推送网关（v2.0新增）
```python
# 启动虚拟网关（回放历史数据）
engine.start_virtual_gateway(
    start_datetime="2024-01-01 09:30:00",
    speed=2.0,  # 2倍速
    symbols=["000001", "600000"]
)

# 停止虚拟网关
engine.stop_virtual_gateway()
```

#### 8. 数据标准化读取（v2.0新增）
```python
# 读取通达信本地数据
symbols = ["000001", "000002", "600000"]
results = engine.read_tdx_data(
    symbols=symbols,
    data_type="day",  # 'day', '5min', '1min'
    market="sh"  # 'sh', 'sz', 'bj'
)

# 查看处理结果
for symbol, success in results.items():
    print(f"{symbol}: {'成功' if success else '失败'}")
```

## 配置说明

### 主要配置项

#### 基础配置
- `chinastock.cache_dir`: 品种列表缓存路径
- `chinastock.data_dir`: K线数据存储路径
- `chinastock.tdx_dir`: 通达信软件根目录
- `chinastock.base_date`: 数据感知基日
- `chinastock.max_workers`: 最大工作线程数
- `chinastock.timeout`: 请求超时时间（秒）
- `chinastock.retry_times`: 重试次数
- `chinastock.enable_watcher`: 是否启用文件监控
- `chinastock.watcher_interval`: 文件监控间隔（秒）

#### 轮询网关配置（v2.0新增）
- `chinastock.polling_gateway.enabled`: 是否自动启用轮询网关
- `chinastock.polling_gateway.interval`: 轮询间隔（秒，默认60）
- `chinastock.polling_gateway.symbols`: 订阅的品种列表（列表类型）

#### 虚拟网关配置（v2.0新增）
- `chinastock.virtual_gateway.enabled`: 是否自动启用虚拟网关
- `chinastock.virtual_gateway.start_datetime`: 虚拟推送起始时间（格式：YYYY-MM-DD HH:MM:SS）
- `chinastock.virtual_gateway.speed`: 推送速度倍数（1.0=实时，2.0=2倍速）

#### 数据读取器配置（v2.0新增）
- `chinastock.data_readers.tdx_root_dir`: 通达信软件根目录（用于读取本地数据）

### 配置方式
1. 通过vnpy的`vt_setting.json`文件配置
2. 通过代码调用`engine.update_config()`方法
3. 通过vnpy前端界面配置（需要实现UI）

## 事件系统

### 事件类型
- `EVENT_CHINASTOCK_LOG`: 日志事件
- `EVENT_CHINASTOCK_VALIDATION`: 数据感知结果
- `EVENT_CHINASTOCK_FILE_CHANGE`: 文件变化事件
- `EVENT_CHINASTOCK_DOWNLOAD`: 下载事件

### 事件监听
```python
def on_log_event(event):
    print(f"日志: {event.data['message']}")

def on_validation_event(event):
    summary = event.data['summary']
    print(f"校验结果: {summary['valid_symbols']}/{summary['total_symbols']} 有效")

# 注册事件监听
event_engine.register(EVENT_CHINASTOCK_LOG, on_log_event)
event_engine.register(EVENT_CHINASTOCK_VALIDATION, on_validation_event)
```

## 数据格式

### 品种分类
- **上证A股**: market=0, 代码以688/60开头
- **深证A股**: market=1, 代码以000/001/002/300/301开头
- **北证A股**: 从通达信板块文件"融资融券"中提取9开头品种
- **T+0基金**: 从通达信板块文件"T+0基金"中提取
- **含可转债**: 从通达信板块文件"含可转债"中提取

### K线数据格式
```python
# DataFrame列结构
{
    'datetime': datetime,    # 时间
    'open': float,          # 开盘价
    'high': float,          # 最高价
    'low': float,           # 最低价
    'close': float,         # 收盘价
    'volume': float,        # 成交量
    'symbol': str,          # 品种代码
    'interval': str         # K线周期
}
```

### 存储结构
```
data_dir/
├── 000001/           # 品种代码目录
│   ├── 1d/           # 日线数据
│   │   └── data.parquet
│   ├── 5m/           # 5分钟数据
│   │   └── data.parquet
│   └── 1m/           # 1分钟数据
│       └── data.parquet
└── 000002/
    └── ...
```

## 数据感知功能

### 检查类型
1. **品种缺失感知**: 对比最新品种列表缓存
2. **历史数据缺失**: 检查基日至今的连续性
3. **逻辑错误**: high < low, open/close 超出范围
4. **格式错误**: price/volume非数值

### 校验结果
```python
@dataclass
class ValidationResult:
    symbol: str                    # 品种代码
    interval: str                  # K线周期
    check_time: datetime          # 检查时间
    is_valid: bool                # 是否有效
    errors: List[str]             # 错误列表
    warnings: List[str]           # 警告列表
    record_count: int             # 记录数量
    date_range: Tuple[date, date] # 日期范围
    missing_dates: List[date]     # 缺失日期
    logic_errors: List[Dict]      # 逻辑错误
    format_errors: List[Dict]      # 格式错误
```

## 开发说明

### 模块结构（v2.0）
```
data_module_vnpy/
├── __init__.py              # 包导出（导出新增组件）
├── engine.py                # 主引擎（新增网关管理方法）
├── config.py                # 配置管理（新增配置项）
├── stock_fetcher.py         # 数据获取（优化多服务器并行注释）
├── block_parser.py          # 板块文件解析
├── storage.py               # 数据存储（增强zstd压缩）
├── validator.py             # 数据校验
├── file_watcher.py          # 文件监控
├── datetime_decoder.py      # 日期解码
├── polling_gateway.py       # ⭐ v2.0新增：轮询转推送网关
├── virtual_gateway.py       # ⭐ v2.0新增：虚拟推送网关
├── data_readers/            # ⭐ v2.0新增：数据标准化读取工具
│   ├── __init__.py
│   ├── base_reader.py       # 读取器基类
│   └── tdx_reader.py        # 通达信数据读取器
├── requirements.txt         # 依赖包
└── README.md               # 说明文档（更新v2.0内容）
```

### v2.0新功能说明

#### 1. 轮询转推送网关（polling_gateway.py）
将mootdx等轮询型数据源转换为推送型数据源，符合vnpy Gateway标准：
- **多服务器并行**：利用mootdx多个服务器IP实现并行请求
- **交易时间判断**：只在交易时间段（9:30-11:30, 13:00-15:00）轮询推送
- **订阅管理**：根据前端订阅的品种列表轮询
- **频率可配**：当前默认1分钟推送频率

#### 2. 虚拟推送网关（virtual_gateway.py）
使用历史数据模拟实时推送，用于非交易时段的回测和测试：
- **历史数据回放**：从StorageManager读取历史1分钟K线数据
- **时间模拟**：从配置的起始时间开始，按时间顺序推送
- **速度控制**：支持配置推送速度倍数（1.0=实时，2.0=2倍速）
- **vnpy标准**：符合vnpy Gateway接口规范

#### 3. 数据标准化读取工具（data_readers/）
读取本地各种格式的数据文件并标准化保存：
- **模块化设计**：每种数据类型一个独立的读取器文件
- **通达信支持**：读取通达信二进制数据（日线、5min线、1min线）
- **易于扩展**：继承BaseReader基类即可添加新数据类型
- **标准化保存**：自动转换为Parquet格式并保存

### 扩展开发
1. **添加新的数据源**: 在`stock_fetcher.py`中扩展
2. **添加新的存储格式**: 在`storage.py`中扩展
3. **添加新的校验规则**: 在`validator.py`中扩展
4. **添加新的监控功能**: 在`file_watcher.py`中扩展
5. **添加新的数据读取器**（v2.0）：在`data_readers/`目录下创建新文件，继承`BaseReader`基类
6. **自定义Gateway**（v2.0）：参考`polling_gateway.py`和`virtual_gateway.py`实现

## 注意事项

1. **编码处理**: 所有文件使用UTF-8编码
2. **错误处理**: 完善的异常捕获和日志记录
3. **多线程安全**: 使用线程锁保护共享资源
4. **配置驱动**: 所有路径和参数均可配置
5. **事件驱动**: 充分利用vnpy事件引擎实现异步通知

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request来改进这个项目。
