# -*- coding: utf-8 -*-
# data_module_vnpy 新架构业务细节文档

**版本**: v3.0 (基于新架构最佳实践)
**创建日期**: 2025-01-02
**文档目标**: 定义新架构下的业务流程规则细节和实现逻辑

> **📖 文档分工**：
> - **本文档**：专注于业务流程、规则细节、实现逻辑、算法描述
> - **最佳实践文档**：专注于架构设计、技术选型、性能目标、组件设计
> 
> 两文档遵循单一事实原则，互相引用但不重复内容。

---

## 📋 目录

- [一、品种管理业务规则](#一品种管理业务规则)
- [二、数据下载业务规则](#二数据下载业务规则)
- [三、数据验证业务规则](#三数据验证业务规则)
- [四、缓存管理业务规则](#四缓存管理业务规则)
- [五、负载均衡业务规则](#五负载均衡业务规则)
- [六、IPO日期管理业务规则](#六IPO日期管理业务规则)
- [七、数据质量管理业务规则](#七数据质量管理业务规则)
- [八、统一数据查询业务规则](#八统一数据查询业务规则)
- [九、实时推送业务规则](#九实时推送业务规则)
- [十、文件监控业务规则](#十文件监控业务规则)
- [十一、native_iocp集成业务规则](#十一native_iocp集成业务规则)
- [十二、子进程日志配置业务规则](#十二子进程日志配置业务规则)
- [十三、背压控制与队列管理业务规则](#十三背压控制与队列管理业务规则)

---

## 一、品种管理业务规则

> **架构设计参考**：组件设计和技术架构请参考 [最佳实践文档 - 2.2 data_acquisition.py](./data_module_vnpy新架构最佳实践cursor版.md#22-data_acquisitionpy---数据获取模块)

### 1.1 品种分类规则

#### 1.1.1 市场分类标准

**上证A股分类规则**：
```python
# 市场代码：market=1
# 代码规则：以688（科创板）或60开头的6位数字
def is_shanghai_a_stock(code: str, market: int) -> bool:
    return (market == 1 and
            len(code) == 6 and
            code.isdigit() and
            (code.startswith('688') or code.startswith('60')))
```

**深证A股分类规则**：
```python
# 市场代码：market=0
# 代码规则：以000（主板）、001/002（中小板）、300/301（创业板）开头的6位数字
def is_shenzhen_a_stock(code: str, market: int) -> bool:
    return (market == 0 and
            len(code) == 6 and
            code.isdigit() and
            (code.startswith('000') or
             code.startswith('001') or
             code.startswith('002') or
             code.startswith('300') or
             code.startswith('301')))
```

**北证A股分类规则**：
```python
# 市场代码：market=2（硬编码值，不从API获取）
# 数据来源：从addedcode_bj.cfg配置文件解析，不从TDX API获取
# 解析规则：从配置文件读取代码和简称，添加固定市场代码2
def _get_beijing_stocks(config_parser: TdxConfigFileParser) -> List[Dict]:
    """获取北证A股（集合B → 集合I）"""
    # 从addedcode_bj.cfg解析
    beijing_stocks = config_parser.parse_addedcode_bj()
    result = []
    for stock in beijing_stocks:
        result.append({
            "code": stock["code"],
            "name": stock["name"],
            "market": 2  # 市场代码2为硬编码值
        })
    return result
```

**T+0基金分类规则**：
```python
# 数据来源：从spblock.dat配置文件获取市场+代码列表，再从TDX API匹配名称
# 匹配规则：从完整缓存（API获取的品种列表）中匹配名称
# 过滤规则：API中不存在的品种会被过滤（视为已退市/到期）
def _get_t0_funds(complete_df: pd.DataFrame, block_parser: BlockParser) -> List[Dict]:
    """获取T+0基金（集合C → 集合H）"""
    # 从spblock.dat获取市场+代码列表
    t0_fund_codes = block_parser.get_t0_fund_codes()
    result = []

    for fund in t0_fund_codes:
        market = int(fund["market"])
        code = str(fund["code"]).zfill(6)

        # 从完整缓存中匹配名称
        matched = complete_df[
            (complete_df["market"] == market) & (complete_df["code"] == code)
        ]

        if len(matched) > 0:
            name = str(matched.iloc[0].get("name", ""))
            result.append({"code": code, "name": name, "market": market})
        # API中无匹配的品种视为不存在（已退市/到期），直接跳过

    return result
```

**可转债分类规则**：
```python
# 数据来源：从tdxstat2.cfg配置文件获取市场+代码列表，再从TDX API匹配名称
# 匹配规则：从完整缓存中匹配名称，支持市场代码容错（交换市场代码0↔1）
# 过滤规则：如果有多个匹配，过滤掉指数和ETF；API中不存在的品种会被过滤
def _get_convertible_bonds(complete_df: pd.DataFrame, config_parser: TdxConfigFileParser) -> List[Dict]:
    """获取可转债（集合A → 集合G）"""
    # 从tdxstat2.cfg获取市场+代码列表
    convertible_codes_by_market = config_parser.parse_tdxstat2()
    result = []

    for market, codes in convertible_codes_by_market.items():
        mkt = int(market)
        for raw_code in codes:
            code = str(raw_code).zfill(6)

            # 尝试原始市场代码匹配
            matched = complete_df[
                (complete_df["market"] == mkt) & (complete_df["code"] == code)
            ]

            # 如果原始市场匹配不到，尝试交换市场代码（0↔1）
            if len(matched) == 0:
                alt_mkt = 1 if mkt == 0 else 0
                matched_alt = complete_df[
                    (complete_df["market"] == alt_mkt) & (complete_df["code"] == code)
                ]
                if len(matched_alt) > 0:
                    matched = matched_alt
                    mkt = alt_mkt  # 使用交换后的市场代码

            if len(matched) > 0:
                # 如果有多个匹配，过滤掉指数和ETF
                if len(matched) > 1:
                    non_index = matched[
                        ~matched["name"].str.contains("指数|ETF", na=False, regex=True)
                    ]
                    if len(non_index) > 0:
                        matched = non_index

                name = str(matched.iloc[0].get("name", ""))
                result.append({"code": code, "name": name, "market": mkt})
            # API中无匹配的品种视为不存在（已退市/到期），直接跳过

    return result
```

#### 1.1.2 品种过滤规则

**未上市品种过滤**：
- **规则**：IPO日期为None或无效日期的品种将被标记为未上市
- **判断标准**：
  - IPO日期原始值 < 19900000（如70这种无效值）
  - IPO日期解析失败
  - IPO日期为0或None
- **处理方式**：从品种列表中移除，记录到unlisted_symbols.json

**重复品种去重规则**：
- **规则**：同一品种代码只保留一条记录
- **去重时机**：在每个市场数据合并之前进行
- **实现方式**：使用`drop_duplicates(subset=["code"], keep="first")`
- **字段选择**：基于code字段去重
- **优先级**：按API返回顺序，保留第一条
- **日志记录**：重复品种会记录DEBUG级别日志

#### 1.1.3 品种缓存规则

**缓存文件结构**：
```json
{
    "_meta": {
        "cache_date": "2025-01-02",
        "version": "2.1",
        "total_count": 5200
    },
    "classified": {
        "上证A股": [{"code": "600000", "name": "浦发银行", "market": 1}],
        "深证A股": [{"code": "000001", "name": "平安银行", "market": 0}],
        "北证A股": [{"code": "830799", "name": "艾融软件", "market": 2}],
        "T+0基金": [{"code": "511990", "name": "华宝添益", "market": 1}],
        "可转债": [{"code": "110001", "name": "中行转债", "market": 1}]
    }
}
```

**缓存失效规则**：
- **时间失效**：每日0时自动失效（基于网络时间）
- **强制刷新**：用户手动触发重新加载
- **版本检查**：缓存版本不匹配时失效

### 1.2 品种列表获取规则

#### 1.2.1 API调用规则

**调用顺序**：
1. 优先从本地缓存加载（如果当日有效）
2. 缓存失效时调用TDX API获取最新数据
3. API失败时使用过期缓存（降级策略）

**API参数配置**：
```python
# 获取所有市场的品种列表
markets = [
    (0, "深证A股"),  # 深圳市场
    (1, "上证A股"),  # 上海市场
    (2, "北证A股")   # 北京市场（不从API获取，从配置文件解析）
]
```

**API分页获取规则**：
- **分页机制**：每页最多1000条，使用`start`参数控制起始位置
- **获取方式**：串行分页请求，递增获取所有页
- **结束条件**：当返回数据少于1000条时，说明已获取完所有数据
- **重试机制**：每页请求最多重试3次
- **超时控制**：每次请求超时3秒，连接超时5秒

**服务器选择规则**：
- **服务器池分配**：每个市场有3个候选服务器（支持故障切换）
  - 深圳市场：使用服务器池索引[0, 2, 4]
  - 上海市场：使用服务器池索引[1, 3, 5]
- **故障切换机制**：当前服务器失败时自动切换到下一个候选服务器
- **错误处理**：所有服务器都失败时抛出异常

**并发获取规则**：
- **并发策略**：使用asyncio并发获取深圳和上海两个市场的数据
- **技术选型**：使用asyncio而非multiprocessing（避免Windows spawn死锁问题）
- **错误隔离**：单个市场失败不影响另一个市场（使用`return_exceptions=True`）
- **架构设计**：网络I/O密集型任务，asyncio比multiprocessing更高效

**错误处理规则**：
- **网络超时**：3秒超时，最多重试3次
- **API异常**：记录错误日志，使用缓存数据
- **数据格式错误**：跳过异常记录，继续处理其他数据
- **服务器故障**：自动切换到下一个候选服务器
- **所有服务器失败**：抛出异常，记录错误日志

#### 1.2.2 数据处理规则

**字段映射规则**：
```python
# TDX API返回字段 -> 内部字段映射
field_mapping = {
    'code': 'code',        # 品种代码
    'name': 'name',        # 品种名称
    'market': 'market'     # 市场代码
}
```

**数据清洗规则**：
- **代码标准化**：确保6位数字格式
  - **补齐方法**：使用`zfill(6)`左补0到6位
  - **补齐时机**：所有市场数据合并后进行
  - **类型转换**：代码需先转换为字符串类型才能使用zfill
- **名称清理**：去除特殊字符和多余空格
- **市场验证**：确保市场代码在有效范围内(0,1,2)

**数据验证规则**：
- **验证标准**：确保code和name都有效（非空且去除空格后不为空）
- **验证时机**：分类完成后对所有品种进行验证
- **过滤逻辑**：无效品种会被过滤，记录DEBUG级别日志
- **统计输出**：验证后会输出过滤统计信息（总过滤数、各类别统计）

**空集合检查规则**：
- **检查规则**：分类完成后检查每个分类是否为空集合
- **分类映射**：
  - "上证A股" → 集合E
  - "深证A股" → 集合F
  - "北证A股" → 集合I
  - "T+0基金" → 集合H
  - "可转债" → 集合G
- **警告日志**：空集合记录WARNING级别日志，提示排查问题
- **返回字段**：返回结果中包含`empty_categories`字段，列出为空的分类列表

### 1.3 品种管理实现细节

> **架构设计参考**：组件交互、状态管理、异步操作等架构设计请参考 [最佳实践文档 - 2.2 data_acquisition.py 详细设计](./data_module_vnpy新架构最佳实践cursor版.md#223-详细设计)

#### 1.3.1 业务流程实现

**品种加载完整流程**：
1. **缓存检查** → 检查本地缓存是否有效（基于日期）
2. **API调用** → 如缓存失效，调用TDX API获取最新数据
3. **数据分类** → 按市场规则分类品种
4. **缓存保存** → 保存分类结果到本地缓存
5. **事件发布** → 通知UI更新品种列表

#### 1.3.2 错误处理策略

**降级策略**：API失败 → 使用过期缓存 → 记录警告日志
**重试策略**：网络超时重试3次，每次3秒超时
**异常隔离**：单个品种分类失败不影响其他品种

---

## 二、数据下载业务规则

> **架构设计参考**：多进程架构、负载均衡等技术设计请参考 [最佳实践文档 - 2.2 data_acquisition.py](./data_module_vnpy新架构最佳实践cursor版.md#22-data_acquisitionpy---数据获取模块)

### 2.1 下载策略规则

#### 2.1.1 两段式下载策略

**第一阶段：IPv4池下载**：
- **适用场景**：绝大部分K线数据下载
- **服务器选择**：优先使用IPv4服务器池
- **并发控制**：根据负载均衡器动态调整
- **切换条件**：剩余任务数 ≤ 50时进入第二阶段

**第二阶段：IPv6池下载**：
- **适用场景**：剩余少量任务或IPv4池性能不佳时
- **服务器选择**：使用IPv6服务器池
- **降级策略**：IPv6不可用时自动回退到IPv4池
- **性能监控**：实时监控IPv6连接质量

**IPv6池降级机制详细说明**：

1. **降级触发条件**：
   - IPv6服务器池测速结果为空（所有IPv6服务器连接失败）
   - IPv6服务器池在运行时全部不可用
   - 调用`get_servers_shuffled(pool_type="ipv6", allow_fallback=True)`时自动检测

2. **降级执行逻辑**：
   ```python
   # 自动降级机制（在load_balancer.py中实现）
   if not selected_servers and allow_fallback:
       if pool_type == "ipv6" and self._sorted_servers_ipv4:
           self.logger.warning(
               "⚠️ IPv6服务器池为空，自动降级使用IPv4服务器池（%d个）",
               len(self._sorted_servers_ipv4)
           )
           selected_servers = self._sorted_servers_ipv4
   ```

3. **降级判定标准**：
   - **测速阶段**：IPv6服务器连接超时（2秒）或连接失败
   - **运行阶段**：IPv6池为空或所有IPv6服务器不可用
   - **自动检测**：每次获取服务器时实时检测池状态

4. **降级后行为**：
   - 自动使用IPv4服务器池继续下载
   - 记录降级日志，便于问题排查
   - 不影响下载任务的正常执行
   - 下次重启时重新测速IPv6池

**切换阈值设定**：
```python
# 固定阈值：剩余50个任务时切换到IPv6池
threshold = 50

# 切换逻辑：
# - 当剩余任务数 <= 50时，从IPv4池切换到IPv6池
# - 这个阈值是经过测试优化的固定值，不依赖总任务数
# - 确保IPv6池处理的是少量剩余任务，避免资源浪费
```

**切换检查实现**：
```python
# 第一阶段下载逻辑（检查任务队列大小）
async def phase1_download_loop(conn_id, client, server):
    while not stop_event.is_set():
        # 检查任务队列大小（每个协程独立检查）
        try:
            queue_size = task_queue.qsize()
            if queue_size <= threshold:
                logger.info(
                    "[Phase1] Worker %s 连接%s 达到阈值（剩余%s），停止",
                    worker_id, conn_id, queue_size
                )
                break
        except Exception:
            pass  # qsize() 可能在某些平台不可用（需要异常处理）
```

**切换规则说明**：
- **检查时机**：在每个连接的下载循环中进行切换检查（每个协程独立检查）
- **检查方式**：使用`task_queue.qsize()`检查剩余任务数
- **异常处理**：`qsize()`可能在某些平台不可用，需要异常处理（捕获异常后继续执行）
- **协程独立性**：每个协程独立判断是否切换到Phase2，无需全局协调
- **切换行为**：达到阈值后协程退出循环，Worker进程自动切换到Phase2

#### 2.1.2 服务器池管理规则

**服务器测速规则**：
- **测速频率**：每日首次启动时进行测速
- **缓存机制**：测速结果缓存到当日23:59:59
- **测速超时**：单个服务器测速超时2秒
- **并发测速**：3进程 × 50协程 = 150并发测速

**服务器排序规则**：
```python
def sort_servers_by_performance(test_results: Dict) -> List:
    """按性能排序服务器"""
    # 排序优先级：
    # 1. 连接成功的服务器优先
    # 2. 按响应时间升序排列
    # 3. 相同响应时间按IP字典序

    available_servers = []
    for server, response_time in test_results.items():
        if response_time > 0:  # 连接成功
            available_servers.append((server, response_time))

    # 按响应时间排序
    available_servers.sort(key=lambda x: (x[1], x[0]))
    return [server for server, _ in available_servers]
```

**服务器选择规则**：
- **最佳服务器**：选择响应时间最短的服务器
- **随机选择**：从前N个最佳服务器中随机选择（负载均衡）
- **故障转移**：服务器连接失败时自动切换到下一个

**服务器分配策略**：
```python
# 🔥 关键优化：使用随机起始位置，确保充分利用全部服务器
# 原问题：线性分配导致只使用前部分服务器，后续服务器从未被使用
import random

# 随机起始位置（确保不超出范围）
max_start = max(0, len(regular_servers) - connections_per_worker * 3)
start_idx = random.randint(0, max_start) if max_start > 0 else 0

# 准备3倍备用服务器（从随机位置开始轮询）
my_ipv4_servers = []
for i in range(connections_per_worker * 3):
    server_idx = (start_idx + i) % len(regular_servers)
    my_ipv4_servers.append(regular_servers[server_idx])
```

**服务器分配规则说明**：
- **随机起始位置**：每个worker使用随机起始位置分配服务器（避免线性分配导致的服务器使用不均）
- **备用机制**：每个worker分配3倍备用服务器（主用 + 备用），主用服务器失败时自动切换到备用
- **轮询方式**：从随机位置开始轮询，确保充分利用所有服务器（而非只使用前部分服务器）
- **负载均衡**：通过随机起始位置实现更好的负载均衡，避免所有worker集中在同一批服务器

#### 2.1.3 增量下载规则

**日期范围计算**：
```python
def calculate_download_range(start_date: str, symbol: str, interval: str) -> Tuple[date, date]:
    """计算增量下载的日期范围"""
    # 1. 解析起始日期
    start = datetime.strptime(start_date, "%Y-%m-%d").date()

    # 2. 获取品种的最新数据日期
    latest_date = get_latest_data_date(symbol, interval)

    # 3. 确定实际起始日期
    if latest_date and latest_date >= start:
        # 从最新数据的下一个交易日开始
        actual_start = get_next_trading_day(latest_date)
    else:
        # 从指定起始日期开始
        actual_start = start

    # 4. 结束日期为最新交易日
    end = get_latest_trading_day()

    return actual_start, end
```

**数据去重规则**：
- **时间戳去重**：相同时间戳的数据只保留最新的
- **合并策略**：新下载数据覆盖本地相同时间的数据
- **完整性检查**：确保数据连续性，发现缺失自动补全

### 2.2 并发控制规则

#### 2.2.1 动态并发调整

**基础并发配置**：
```python
# 默认并发配置
DEFAULT_CONFIG = {
    "max_processes": 16,        # 最大进程数
    "coroutines_per_process": 40,  # 每进程协程数
    "max_total_connections": 2000,  # 总连接数上限
    "batch_size": 100          # 批次大小
}
```

**负载均衡调整规则**：
- **CPU瓶颈**：减少进程数，增加每进程协程数
- **内存瓶颈**：减少批次大小，限制并发数
- **磁盘瓶颈**：减少总并发数，增加批次大小
- **网络瓶颈**：限制连接数，使用更保守的配置

#### 2.2.2 任务分配规则

**任务分片策略**：
```python
def split_tasks_for_processes(symbols: List[str], intervals: List[str], num_processes: int) -> List[List]:
    """将下载任务分配给多个进程"""
    # 1. 生成所有任务组合
    all_tasks = [(symbol, interval) for symbol in symbols for interval in intervals]

    # 2. 按品种代码哈希分配（确保同一品种的不同周期在同一进程）
    process_tasks = [[] for _ in range(num_processes)]
    for symbol, interval in all_tasks:
        process_idx = hash(symbol) % num_processes
        process_tasks[process_idx].append((symbol, interval))

    return process_tasks
```

**连接生命周期管理规则**：
```python
# 🆕 v3.7: 创建连接生命周期管理器
conn_manager = ConnectionLifecycleManager(worker_id, logger)

# 🆕 v3.7：使用ConnectionLifecycleManager批量创建连接
connection_list = await conn_manager.create_connections(
    servers=server_list_local,
    timeout=timeout,
    health_check=False,  # K线下载优先速度，不做健康检查
)

# 转换为字典（兼容现有代码）
connections = {server_list_local[i]: client for i, client in enumerate(connection_list)}
```

**连接管理规则说明**：
- **统一管理**：使用`ConnectionLifecycleManager`统一管理连接的创建和关闭
- **批量创建**：一次性批量创建所有连接（提高效率，减少连接建立时间）
- **健康检查**：K线下载不做健康检查（优先速度，健康检查会增加延迟）
- **错误处理**：连接创建失败时自动重试或跳过（记录DEBUG日志，不影响其他连接）
- **资源清理**：连接关闭时确保资源被正确释放（在finally块中处理）

**跨进程通信规则**：
```python
# 多进程共享对象（使用multiprocessing.Manager）
self.manager = Manager()
self.task_queue = self.manager.Queue()        # 任务队列
self.result_queue = self.manager.Queue()      # 结果队列
self.metrics_queue = self.manager.Queue()     # 监控指标队列（独立）
self.progress_queue = self.manager.Queue()    # 进度队列
self.stop_event = self.manager.Event()       # 停止事件
self.pause_event = self.manager.Event()      # 暂停事件
```

**通信规则说明**：
- **队列类型**：使用`multiprocessing.Manager.Queue`（而非native_ipc，Manager更成熟稳定）
- **队列分类**：
  - `task_queue`：待下载任务队列（主进程 → Worker进程）
  - `result_queue`：下载结果队列（Worker进程 → 主进程）
  - `metrics_queue`：监控指标队列（Worker进程 → 主进程，独立队列避免阻塞）
  - `progress_queue`：进度更新队列（Worker进程 → 主进程）
- **事件同步**：使用`Event`进行进程间同步（stop_event、pause_event）
- **背压控制**：队列满时使用`_safe_put_queue`跳过任务，记录为"skipped"（避免无限等待）

**监控指标收集规则**：
```python
# 🆕 v3.6: 启动lag监控（使用独立的metrics_queue）
lag_monitor_task = asyncio.create_task(
    LagMonitor.monitor_and_report(
        metrics_queue=metrics_queue,  # 使用独立的监控队列
        worker_id=worker_id,
        stop_event=stop_event,
        interval_seconds=0.3,  # 监控频率0.3秒
    )
)

# 主进程处理监控指标
while True:
    try:
        if self.metrics_queue:
            msg = self.metrics_queue.get_nowait()
            LagMonitor.process_lag_message(msg, self.load_balancer, self.logger)
    except queue.Empty:
        break
```

**监控规则说明**：
- **监控指标类型**：`event_loop_lag`（事件循环延迟），用于检测协程阻塞
- **收集频率**：0.3秒（高频监控，及时发现问题）
- **处理流程**：Worker进程收集 → metrics_queue → 主进程处理 → LoadBalancer动态调整
- **用途**：用于LoadBalancer动态调整并发数（根据event_loop_lag自动调整协程数）

**任务结果保存规则**：
```python
# 下载成功，保存结果
if data is not None and not data.empty:
    # 🆕 背压控制: 使用_safe_put_queue代替原来的无限等待
    success = await asyncio.to_thread(
        _safe_put_queue,
        result_queue,
        (f"{symbol}_{interval}", data.to_dict("records")),  # 结果格式
        timeout=1.0,
        queue_name="result_queue",
        worker_id=worker_id,
    )
    if success:
        await asyncio.to_thread(progress_queue.put, (symbol, interval, "success"))
        processed += 1
    else:
        # 队列满，跳过该任务
        await asyncio.to_thread(progress_queue.put, (symbol, interval, "skipped"))
```

**结果保存规则说明**：
- **结果格式**：`(symbol_interval, data_dict)`字典格式，主进程转换为DataFrame
- **保存时机**：主进程收集结果后保存到StorageManager（不在worker进程保存，避免多进程写冲突）
- **背压控制**：队列满时跳过任务，记录为"skipped"（避免无限等待，确保其他任务能继续执行）
- **主进程收集流程**：从result_queue收集结果 → 转换为DataFrame → 保存到Parquet文件（使用native_iocp异步写入）

**暂停/恢复机制规则**：
```python
# 等待暂停事件（每个协程循环检查）
while not pause_event.is_set():
    if stop_event.is_set():
        break
    await asyncio.sleep(0.1)  # 每0.1秒检查一次

def pause_download(self):
    """暂停当前下载任务"""
    if self.pause_event:
        self.pause_event.clear()  # 清除事件 = 暂停
        self.logger.info("已发送暂停信号")

def resume_download(self):
    """恢复暂停的下载任务"""
    if self.pause_event:
        self.pause_event.set()  # 设置事件 = 恢复
        self.logger.info("已发送恢复信号")
```

**暂停/恢复规则说明**：
- **暂停机制**：使用`pause_event.clear()`暂停所有协程（每个协程循环检查pause_event）
- **恢复机制**：使用`pause_event.set()`恢复所有协程（立即继续下载）
- **资源占用**：暂停时继续占用连接（不释放资源，恢复时无需重新创建连接）
- **检查频率**：每0.1秒检查一次pause_event（确保快速响应）
- **用户体验**：暂停时立即响应，恢复时立即继续下载（无需等待）

**停止机制规则**：
```python
def stop_download(self):
    """停止当前下载任务"""
    if self.stop_event:
        self.stop_event.set()  # 设置事件 = 停止
        self.logger.info("已发送停止信号")

# 在worker进程中检查停止事件
while not stop_event.is_set():
    # ... 下载逻辑 ...
    if stop_event.is_set():
        break
```

**停止规则说明**：
- **停止机制**：使用`stop_event.set()`停止所有协程（每个协程循环检查stop_event）
- **资源清理**：停止时确保连接被正确关闭（在finally块中处理），清理进程和队列
- **进程终止**：使用`terminate()`强制终止进程（每个进程join超时1秒，避免无限等待）
- **用户体验**：停止时立即响应，确保资源被正确释放

**错误处理和重试规则**：
```python
# 下载失败处理
except Exception as e:
    logger.debug(
        f"Worker {worker_id} 连接 {conn_id} 下载 {symbol}_{interval} 失败: {e}"
    )
    await asyncio.to_thread(progress_queue.put, (symbol, interval, "failed"))
    failed += 1

# 服务器连接失败，尝试下一个服务器
except Exception as e:
    logger.warning(
        "[Phase1] Worker %s 连接%s 服务器%s失败，尝试下一个服务器: %s",
        worker_id, conn_id, _current_server, e
    )
    # 切换到下一个备用服务器
    current_client = await _get_next_server_client(...)
```

**错误处理规则说明**：
- **错误类型**：下载失败、服务器连接失败、队列满
- **重试策略**：下载失败不重试（记录为failed，继续下一个任务），服务器连接失败自动切换到下一个备用服务器
- **故障切换**：自动切换到下一个备用服务器（无需人工干预）
- **日志记录**：错误日志记录为DEBUG级别（避免日志轰炸，只在必要时记录WARNING）

**进度监控超时规则**：
```python
def _monitor_progress_and_collect_results(self, total_tasks: int, progress_callback):
    """改进的监控和结果收集"""
    timeout_count = 0
    max_timeout_count = 600  # ✅ 60秒（600 * 0.1秒），给足时间下载

    while completed < total_tasks:
        try:
            progress_data = self.progress_queue.get(timeout=0.1)
            completed += 1
            timeout_count = 0  # 重置超时计数
        except queue.Empty:
            timeout_count += 1
            if timeout_count >= max_timeout_count:
                self.logger.warning(
                    f"进度监控超时（{max_timeout_count * 0.1}秒），已完成: {completed}/{total_tasks}"
                )
                # ✅ 检查所有进程状态并诊断
                alive_processes = [p for p in self.processes if p.is_alive()]
                if not alive_processes:
                    self.logger.warning("所有进程已结束，但任务未完成！强制退出监控")
                    break
                # ✅ 重置超时计数，继续等待（进程还在工作）
                timeout_count = 0
```

**进度监控规则说明**：
- **超时机制**：60秒无进度更新则检查进程状态（给足时间下载，避免误判）
- **进程状态检查**：超时后检查所有进程是否存活，如果全部死亡则退出监控
- **队列诊断**：超时时检查队列状态（task_queue、progress_queue、result_queue），帮助排查问题
- **错误处理**：进程仍在运行则重置超时计数，继续等待（避免误判为超时）

**任务详细日志记录规则**：
```python
# 初始化任务详细日志记录器
task_logger = TaskDetailLogger(worker_id=worker_id)

# 记录单个任务详情
task_logger.log_download_result(
    symbol=symbol,
    interval=interval,
    result=result,
    error=error,
    server=server,
    elapsed=elapsed_time,
    phase="Phase1",
)
```

**日志记录规则说明**：
- **日志格式**：CSV格式，包含symbol、interval、result、error、server、elapsed、phase等字段
- **保存位置**：按worker_id区分，保存到不同的日志文件（便于追踪不同进程的任务）
- **日志内容**：记录每个任务的详细信息（成功/失败、耗时、服务器、阶段等）
- **用途**：用于任务性能分析、错误排查、服务器质量评估（帮助优化下载策略）

**进度同步规则**：
- **进度报告频率**：每完成100个任务或每5秒报告一次
- **跨进程同步**：使用multiprocessing.Manager.Queue进行进度同步（而非native_ipc）
- **异常处理**：进程异常时其他进程继续执行（异常隔离）

### 2.3 数据下载实现细节

> **架构设计参考**：多进程架构、异步操作、错误处理等技术设计请参考 [最佳实践文档 - 2.2 data_acquisition.py 详细设计](./data_module_vnpy新架构最佳实践cursor版.md#223-详细设计)

#### 2.3.1 下载流程实现

**完整下载流程**：
1. **配置获取** → LoadBalancer获取最优并发配置
2. **任务分配** → 按品种哈希分配到不同进程
3. **两段式下载** → IPv4池主要下载，IPv6池处理剩余任务
4. **进度同步** → 跨进程实时同步下载进度
5. **结果收集** → 主进程收集并保存下载结果

#### 2.3.2 任务管理策略

**暂停/恢复机制**：通过共享事件控制所有协程的暂停和恢复
**停止机制**：优雅停止，确保资源正确释放
**进度监控**：60秒超时检查，避免无限等待

---

## 三、数据验证业务规则

> **架构设计参考**：验证器架构、多进程设计请参考 [最佳实践文档 - 2.4 data_quality.py](./data_module_vnpy新架构最佳实践cursor版.md#24-data_qualitypy---数据质量管理模块)

### 3.1 数据完整性验证

#### 3.1.1 格式验证规则

**DataFrame结构验证**：
```python
def validate_dataframe_format(df: pd.DataFrame) -> List[Dict]:
    """验证DataFrame格式"""
    errors = []

    # 1. 必需列检查
    required_columns = ['datetime', 'open', 'high', 'low', 'close', 'volume']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        errors.append({
            "type": "missing_columns",
            "message": f"缺少必需列: {missing_columns}",
            "severity": "error"
        })

    # 2. 数据类型检查
    if 'datetime' in df.columns:
        if not pd.api.types.is_datetime64_any_dtype(df['datetime']):
            errors.append({
                "type": "invalid_datetime",
                "message": "datetime列不是日期时间类型",
                "severity": "error"
            })

    # 3. 数值列检查
    numeric_columns = ['open', 'high', 'low', 'close', 'volume']
    for col in numeric_columns:
        if col in df.columns:
            if not pd.api.types.is_numeric_dtype(df[col]):
                errors.append({
                    "type": "invalid_numeric",
                    "message": f"{col}列不是数值类型",
                    "severity": "error"
                })
            # 4. 空值检查（补充遗漏规则）
            elif df[col].isna().any():
                # 记录每个包含空值的行的详细信息
                na_rows = df[df[col].isna()]
                for idx, row in na_rows.iterrows():
                    try:
                        idx_date = pd.Timestamp(idx).date() if pd.notna(idx) else None
                    except (ValueError, TypeError):
                        idx_date = None
                    errors.append({
                        "type": "format_error",
                        "column": col,
                        "date": idx_date,
                        "value": None,
                        "message": f"{col}列包含空值",
                        "severity": "error"
                    })

    return errors
```

**数据范围验证**：
```python
def validate_data_ranges(df: pd.DataFrame) -> List[Dict]:
    """验证数据范围合理性"""
    errors = []

    # 1. 价格合理性检查
    price_columns = ['open', 'high', 'low', 'close']
    for col in price_columns:
        if col in df.columns:
            # 价格不能为负数或零
            invalid_prices = df[df[col] <= 0]
            if not invalid_prices.empty:
                errors.append({
                    "type": "invalid_price_range",
                    "message": f"{col}列存在非正数价格，共{len(invalid_prices)}条",
                    "severity": "error"
                })

            # 价格不能超过合理上限（如10000元）
            extreme_prices = df[df[col] > 10000]
            if not extreme_prices.empty:
                errors.append({
                    "type": "extreme_price",
                    "message": f"{col}列存在极端价格(>10000)，共{len(extreme_prices)}条",
                    "severity": "warning"
                })

    # 2. 成交量检查
    if 'volume' in df.columns:
        negative_volume = df[df['volume'] < 0]
        if not negative_volume.empty:
            errors.append({
                "type": "negative_volume",
                "message": f"成交量存在负数，共{len(negative_volume)}条",
                "severity": "error"
            })

    return errors
```

#### 3.1.2 逻辑验证规则

**OHLC逻辑验证**：
```python
def validate_ohlc_logic(df: pd.DataFrame) -> List[Dict]:
    """验证OHLC价格逻辑关系"""
    errors = []

    if all(col in df.columns for col in ['open', 'high', 'low', 'close']):
        # 1. 最高价 >= 最低价
        invalid_high_low = df[df['high'] < df['low']]
        if not invalid_high_low.empty:
            # 记录每条错误的详细信息（补充遗漏规则）
            for idx, row in invalid_high_low.iterrows():
                try:
                    idx_date = pd.Timestamp(idx).date() if pd.notna(idx) else None
                except (ValueError, TypeError):
                    idx_date = None
                errors.append({
                    "type": "high_low_error",
                    "date": idx_date,
                    "high": row['high'],
                    "low": row['low'],
                    "message": f"最高价小于最低价: high={row['high']}, low={row['low']}",
                    "severity": "error"
                })

        # 2. 最高价 >= 开盘价和收盘价
        invalid_high_open = df[df['high'] < df['open']]
        invalid_high_close = df[df['high'] < df['close']]

        if not invalid_high_open.empty:
            errors.append({
                "type": "high_less_than_open",
                "message": f"最高价小于开盘价，共{len(invalid_high_open)}条",
                "severity": "error"
            })

        if not invalid_high_close.empty:
            errors.append({
                "type": "high_less_than_close",
                "message": f"最高价小于收盘价，共{len(invalid_high_close)}条",
                "severity": "error"
            })

        # 3. 最低价 <= 开盘价和收盘价
        invalid_low_open = df[df['low'] > df['open']]
        invalid_low_close = df[df['low'] > df['close']]

        if not invalid_low_open.empty:
            errors.append({
                "type": "low_greater_than_open",
                "message": f"最低价大于开盘价，共{len(invalid_low_open)}条",
                "severity": "error"
            })

        if not invalid_low_close.empty:
            errors.append({
                "type": "low_greater_than_close",
                "message": f"最低价大于收盘价，共{len(invalid_low_close)}条",
                "severity": "error"
            })

        # 4. 价格合理性检查（警告级别，补充遗漏规则）
        invalid_open = df[df['open'] <= 0]
        invalid_close = df[df['close'] <= 0]
        if not invalid_open.empty or not invalid_close.empty:
            warnings = []
            if not invalid_open.empty:
                warnings.append(f"存在开盘价<=0的情况，共{len(invalid_open)}条")
            if not invalid_close.empty:
                warnings.append(f"存在收盘价<=0的情况，共{len(invalid_close)}条")
            # 注意：此规则在新架构中应返回warnings列表，而非errors

    return errors
```

### 3.2 数据完整性验证

#### 3.2.1 时间连续性验证

**交易日缺失检查**：
```python
def validate_trading_day_completeness(df: pd.DataFrame, symbol: str,
                                    date_range: Tuple[date, date],
                                    context: ValidationContext) -> Tuple[List[date], List[str]]:
    """检查交易日数据完整性"""
    start_date, end_date = date_range

    # 1. 计算有效起始日期（智能起点计算算法，补充遗漏规则）
    effective_start = compute_effective_start_date(
        symbol=symbol,
        data_start=start_date,
        base_date=context.base_date,
        ipo_dates=context.ipo_dates
    )
    # 智能起点计算逻辑：
    # - 如果IPO日期可用，使用IPO日期
    # - 否则使用max(数据起点, 基准日期)
    # - 如果都不可用，使用默认值2020-01-01

    # 2. 确定检测终点（不能超过最近一个交易日）
    check_end_date = min(end_date, context.latest_trading_day)

    # 3. 验证日期范围（补充遗漏规则）
    if effective_start > check_end_date:
        # 日期范围异常，统计并记录（每1000个任务输出一次汇总）
        return [], ["日期范围异常: 有效起点大于检测终点"]

    # 4. 获取期间内所有交易日
    expected_trading_days = get_trading_days_in_range(effective_start, check_end_date, context.trading_days)

    # 5. 获取实际数据日期
    if df.empty:
        return list(expected_trading_days), ["数据为空"]

    actual_dates = set(df['datetime'].dt.date)

    # 6. 过滤停牌日期：通过成交量识别停牌（有价无量，补充遗漏规则）
    # 停牌特征：有价无量（价格存在但成交量为0或极低）
    # 停牌判断逻辑：
    # - 成交量 < 100股
    # - 前后交易日有正常成交量（>= 100股）
    # - 从expected_dates中排除，避免被统计为数据缺失
    if 'volume' in df.columns and expected_trading_days:
        zero_volume_dates = set()
        trading_dates_list = sorted(expected_trading_days)

        for date_val in actual_dates:
            if date_val not in expected_trading_days:
                continue

            # 查找该日期的成交量
            date_mask = df['datetime'].dt.date == date_val
            date_rows = df[date_mask]

            if not date_rows.empty:
                max_volume = date_rows['volume'].max()

                # 如果成交量 < 100股，检查前后交易日
                if max_volume < 100:
                    try:
                        date_idx = trading_dates_list.index(date_val)
                        has_normal_prev_volume = False
                        has_normal_next_volume = False

                        # 检查前一个交易日
                        if date_idx > 0:
                            prev_date = trading_dates_list[date_idx - 1]
                            if prev_date in actual_dates:
                                prev_mask = df['datetime'].dt.date == prev_date
                                prev_volume = df[prev_mask]['volume'].max()
                                if prev_volume >= 100:
                                    has_normal_prev_volume = True

                        # 检查后一个交易日
                        if date_idx < len(trading_dates_list) - 1:
                            next_date = trading_dates_list[date_idx + 1]
                            if next_date in actual_dates:
                                next_mask = df['datetime'].dt.date == next_date
                                next_volume = df[next_mask]['volume'].max()
                                if next_volume >= 100:
                                    has_normal_next_volume = True

                        # 如果前后交易日有正常成交量，当前日期可能是停牌
                        if has_normal_prev_volume or has_normal_next_volume:
                            zero_volume_dates.add(date_val)
                    except (ValueError, IndexError):
                        pass

        # 从expected_dates中排除有价无量的日期
        if zero_volume_dates:
            expected_trading_days = set(expected_trading_days) - zero_volume_dates
            expected_trading_days = sorted(expected_trading_days)

    # 7. 找出缺失的交易日
    missing_dates = [d for d in expected_trading_days if d not in actual_dates]

    # 8. 生成缺失原因分析
    missing_reasons = []
    if missing_dates:
        # 检查是否是IPO后的缺失
        ipo_date = context.ipo_dates.get(symbol)
        if ipo_date:
            pre_ipo_missing = [d for d in missing_dates if d < ipo_date]
            post_ipo_missing = [d for d in missing_dates if d >= ipo_date]

            if pre_ipo_missing:
                missing_reasons.append(f"IPO前缺失{len(pre_ipo_missing)}个交易日")
            if post_ipo_missing:
                missing_reasons.append(f"IPO后缺失{len(post_ipo_missing)}个交易日")
        else:
            missing_reasons.append(f"缺失{len(missing_dates)}个交易日")

    return missing_dates, missing_reasons
```

#### 3.2.2 数据新鲜度验证

**滞后天数计算**：
```python
def calculate_data_freshness(df: pd.DataFrame, context: ValidationContext) -> Dict[str, Any]:
    """计算数据新鲜度"""
    if df.empty:
        return {
            "gap_days": -1,
            "latest_date": None,
            "is_fresh": False,
            "freshness_score": 0.0
        }

    # 1. 获取数据最新日期
    latest_data_date = df['datetime'].dt.date.max()

    # 2. 获取最新交易日（使用网络时间）
    latest_trading_day = context.latest_trading_day

    # 3. 计算滞后天数
    if latest_data_date >= latest_trading_day:
        gap_days = 0  # 数据是最新的
    else:
        # 计算交易日滞后（性能优化版，补充遗漏规则）
        # 优化算法：使用日历天数 / 1.4 估算交易日天数
        # 这个估算对于判断数据是否过时（>1天）已经足够准确，避免每次都创建事件循环
        calendar_gap = (latest_trading_day - latest_data_date).days
        trading_gap = int(calendar_gap / 1.4)  # 粗略估算：日历天数 / 1.4 ≈ 交易日天数
        gap_days = max(0, trading_gap)

        # 注意：如果需要精确计算，可以使用count_trading_days_between，但性能较差

    # 4. 判断新鲜度（补充遗漏规则：允许1个交易日的延迟）
    # gap_days <= 1 为最新（允许1个交易日的延迟）
    is_fresh = gap_days <= 1

    # 5. 计算新鲜度评分
    if gap_days == 0:
        freshness_score = 100.0
    elif gap_days <= 1:  # 更新阈值，允许1个交易日延迟
        freshness_score = 95.0
    elif gap_days <= context.freshness_days_warning:
        freshness_score = max(70.0, 95.0 - (gap_days - 1) * 5)
    elif gap_days <= context.freshness_days_error:
        freshness_score = max(30.0, 70.0 - (gap_days - context.freshness_days_warning) * 10)
    else:
        freshness_score = 0.0

    return {
        "gap_days": gap_days,
        "latest_date": latest_data_date,
        "is_fresh": is_fresh,
        "freshness_score": freshness_score
    }
```

### 3.3 验证上下文管理

#### 3.3.1 共享数据准备

**ValidationContext构建规则**：
```python
def build_validation_context() -> ValidationContext:
    """构建验证上下文"""
    # 1. 获取IPO日期数据（补充遗漏规则：IPO日期验证）
    ipo_cache = get_ipo_cache()
    ipo_dates = {}
    today = get_real_date()  # 使用网络时间作为基准

    for symbol in get_all_symbols():
        ipo_date, _ = ipo_cache.get(symbol)
        if ipo_date:
            # IPO日期合法性验证（补充遗漏规则）
            # 规则1：不能超过今天+30天
            if ipo_date > today + timedelta(days=30):
                logger.warning(f"品种 {symbol} IPO日期异常（未来日期）: {ipo_date}，跳过")
                continue

            # 规则2：不能早于1990年
            if ipo_date.year < 1990:
                logger.warning(f"品种 {symbol} IPO日期异常（过早）: {ipo_date}，跳过")
                continue

            ipo_dates[symbol] = ipo_date

    # 2. 获取交易日历
    trading_days = get_trading_calendar()

    # 3. 获取最新交易日（使用网络时间）
    latest_trading_day = get_latest_trading_day()

    # 4. 设置基准日期
    base_date = get_real_date()  # 使用网络时间

    return ValidationContext(
        ipo_dates=ipo_dates,
        trading_days=set(trading_days),
        latest_trading_day=latest_trading_day,
        base_date=base_date,
        min_records_threshold=100,
        freshness_days_warning=7,
        freshness_days_error=30
    )
```

**智能起点计算算法**（补充遗漏规则）：
```python
def compute_effective_start_date(
    symbol: Optional[str],
    data_start: Optional[date],
    base_date: Optional[date],
    ipo_dates: Dict[str, date]
) -> date:
    """计算有效起始日期（智能起点计算算法）

    不使用推测，通过逻辑计算得出唯一正确值。

    逻辑：
    1. 如果IPO日期可用，使用IPO日期
    2. 否则使用max(数据起点, 基准日期)
    3. 如果都不可用，使用默认值2020-01-01

    Args:
        symbol: 品种代码（可选）
        data_start: 本地数据起点
        base_date: 配置的基准日期
        ipo_dates: IPO日期字典

    Returns:
        有效起始日期
    """
    # 1. 尝试获取IPO日期
    ipo_date = ipo_dates.get(symbol) if symbol else None

    # 2. 计算有效起点
    candidates = []

    if ipo_date:
        candidates.append(ipo_date)

    if data_start:
        candidates.append(data_start)

    if base_date:
        candidates.append(base_date)

    # 3. 选择最大值（最近的日期）
    if candidates:
        effective_start = max(candidates)
        return effective_start
    else:
        # 4. 所有都不可用，使用默认值
        default_date = date(2020, 1, 1)
        return default_date
```

**日期范围异常处理**（补充遗漏规则）：
```python
class DateRangeExceptionHandler:
    """日期范围异常处理器

    用于统计和记录日期范围异常，避免批量扫描时日志刷屏。
    规则：每1000个任务输出一次汇总信息。
    """
    def __init__(self):
        self.exception_count = 0
        self.exception_symbols = []

    def reset(self):
        """重置统计（在新的扫描任务开始时调用）"""
        self.exception_count = 0
        self.exception_symbols = []

    def record_exception(self, symbol: str):
        """记录异常"""
        self.exception_count += 1
        self.exception_symbols.append(symbol)

        # 每1000个任务输出一次汇总
        if self.exception_count % 1000 == 0:
            unique_symbols = len(set(self.exception_symbols[-1000:]))
            logger.warning(
                "日期范围异常统计: 已处理 %d 个任务，最近1000个任务中有 %d 个唯一品种异常",
                self.exception_count,
                unique_symbols
            )

    def log_final_stats(self):
        """输出最终的日期范围异常统计"""
        if self.exception_count > 0:
            unique_symbols = len(set(self.exception_symbols))
            logger.info(
                "日期范围异常最终统计: 共 %d 个任务异常，涉及 %d 个唯一品种",
                self.exception_count,
                unique_symbols
            )
            self.reset()

### 3.4 数据验证实现细节

> **架构设计参考**：组件交互、状态管理、多进程验证等架构设计请参考 [最佳实践文档 - 2.4 data_quality.py 详细设计](./data_module_vnpy新架构最佳实践cursor版.md#243-详细设计要点)

#### 3.4.1 验证流程实现

**完整验证流程**：
1. **扫描阶段** → 扫描所有数据文件，生成验证任务列表
2. **验证阶段** → 多进程并发验证数据质量
3. **结果汇总** → 收集验证结果，生成质量报告
4. **缓存更新** → 缓存验证结果，避免重复验证
5. **事件发布** → 通知UI更新质量看板

#### 3.4.2 验证状态管理

**验证状态流转**：空闲 → 扫描 → 验证 → 完成
**暂停/恢复**：支持验证过程中的暂停和恢复操作
**进度跟踪**：实时跟踪验证进度和错误统计

---

## 十一、native_iocp集成业务规则

> **架构设计参考**：native_iocp技术架构请参考 [最佳实践文档 - 3. native_iocp深度集成方案](./data_module_vnpy新架构最佳实践cursor版.md#三native_iocp深度集成方案)

### 11.1 三级降级策略

**降级层次设计**：

**Level 1: native_iocp真异步I/O（优先）**
- **技术实现**：Windows IOCP（I/O Completion Ports）
- **性能特征**：0延迟，真正的异步I/O，无线程池开销
- **适用场景**：Windows平台，native_iocp模块可用
- **触发条件**：`_USE_IOCP == True` 且 `compat_aopen is not None`

**Level 2: aiofiles异步I/O（降级）**
- **技术实现**：基于线程池的异步I/O模拟
- **性能特征**：~5ms延迟，线程池模拟异步
- **适用场景**：Windows平台，但native_iocp不可用
- **触发条件**：native_iocp导入失败或运行时异常

**Level 3: 同步I/O（最终降级）**
- **技术实现**：在asyncio executor中执行同步读写
- **性能特征**：~20ms延迟，阻塞I/O
- **适用场景**：aiofiles也不可用或发生异常
- **触发条件**：所有异步方案失败

#### 11.1.1 降级触发条件详细规则

**ImportError降级（模块级别）**：
```python
# 在模块加载阶段检测
try:
    from backend.infrastructure.native_iocp import compat_aopen
    _USE_IOCP = True
except ImportError:
    compat_aopen = None
    _USE_IOCP = False
    # 降级到Level 2或Level 3
```

**运行时异常降级（函数级别）**：
```python
async def _read_parquet_async(file_path: Union[str, Path]) -> pd.DataFrame:
    try:
        if _USE_IOCP and compat_aopen is not None:
            # Level 1: 尝试native_iocp
            file_obj = await compat_aopen(file_path, 'rb')
            # ... IOCP读取逻辑
    except Exception as e:
        logger.warning(f"native_iocp读取失败，降级到同步读取: {e}")
        # Level 3: 降级到同步读取（跳过Level 2以简化逻辑）
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, pd.read_parquet, file_path)
```

**降级判定标准**：
1. **模块不可用**：`ImportError` → 自动降级到Level 2/3
2. **文件打开失败**：`compat_aopen()` 异常 → 降级到Level 3
3. **读取异常**：`file_obj.read()` 异常 → 降级到Level 3
4. **解析异常**：`pyarrow.parquet.read_table()` 异常 → 降级到Level 3

### 11.2 日志记录规范

#### 11.2.1 降级日志规范

**WARNING级别：记录降级原因**
```python
logger.warning(
    "⚠️ native_iocp读取失败，降级到同步读取: %s",
    error_message
)
```

**记录内容要求**：
- 原因描述：具体的异常类型和消息
- 降级目标：明确降级到哪个Level
- 文件路径：失败的文件路径（DEBUG级别）

**INFO级别：记录实际使用的I/O模式**
```python
# 在StorageManager初始化时记录
if _USE_IOCP:
    logger.info("✓ 使用native_iocp真异步I/O（Level 1）")
else:
    logger.info("⚠️ native_iocp不可用，使用降级方案（Level 2/3）")
```

**DEBUG级别：记录性能监控数据**
```python
logger.debug(
    "文件读取性能: 文件=%s, 大小=%d MB, 耗时=%.3f秒, 模式=%s",
    file_path,
    file_size_mb,
    elapsed_time,
    io_mode  # "native_iocp" / "aiofiles" / "sync"
)
```

#### 11.2.2 日志输出位置

**AI日志文件**：
- 所有降级事件必须写入AI日志文件
- 文件路径：`C:\Users\USER\Desktop\terminal_v0.50\logs\data_storage_{timestamp}.log`
- 日志格式：包含时间戳、级别图标、模块名、详细消息

**终端日志**：
- WARNING级别降级日志输出到终端（根据terminal_mode配置）
- INFO级别初始化日志输出到终端
- DEBUG级别性能日志仅写入文件，不输出到终端

### 11.3 性能监控指标定义

#### 11.3.1 I/O模式性能基准

| I/O模式 | 延迟 | 吞吐量 | CPU占用 | 适用场景 |
|---------|------|--------|---------|----------|
| native_iocp | 0ms | 最高 | 最低 | Windows平台，生产环境 |
| aiofiles | ~5ms | 中等 | 中等 | 降级场景，兼容性优先 |
| 同步读取 | ~20ms | 最低 | 最高 | 最终降级，确保功能 |

#### 11.3.2 性能监控指标

**吞吐量指标**：
- **指标名称**：`io_throughput_mbps`
- **计算公式**：`file_size_mb / elapsed_time`
- **单位**：MB/s
- **记录频率**：每次文件读写操作

**延迟指标**：
- **指标名称**：`io_latency_ms`
- **计算公式**：`elapsed_time * 1000`
- **单位**：毫秒
- **记录频率**：每次文件读写操作

**模式使用统计**：
- **指标名称**：`io_mode_usage_count`
- **记录内容**：`{"native_iocp": count1, "aiofiles": count2, "sync": count3}`
- **统计周期**：每小时汇总一次

#### 11.3.3 性能监控实现示例

```python
import time
from pathlib import Path

async def _read_parquet_async_with_metrics(
    file_path: Union[str, Path]
) -> pd.DataFrame:
    """异步读取Parquet文件（带性能监控）"""
    start_time = time.time()
    file_size_mb = Path(file_path).stat().st_size / (1024 * 1024)
    io_mode = "unknown"
    
    try:
        if _USE_IOCP and compat_aopen is not None:
            # Level 1: native_iocp
            io_mode = "native_iocp"
            file_obj = await compat_aopen(file_path, 'rb')
            async with file_obj:
                data = await file_obj.read()
            
            import pyarrow.parquet as pq
            import io
            table = pq.read_table(io.BytesIO(data))
            df = table.to_pandas()
        else:
            # Level 3: 同步读取
            io_mode = "sync"
            loop = asyncio.get_event_loop()
            df = await loop.run_in_executor(None, pd.read_parquet, file_path)
        
        # 计算性能指标
        elapsed_time = time.time() - start_time
        throughput = file_size_mb / elapsed_time if elapsed_time > 0 else 0
        latency_ms = elapsed_time * 1000
        
        # 记录性能日志
        logger.debug(
            "文件读取性能: 文件=%s, 大小=%.2f MB, "
            "耗时=%.3f秒, 吞吐量=%.2f MB/s, 延迟=%.2f ms, 模式=%s",
            file_path, file_size_mb, elapsed_time, 
            throughput, latency_ms, io_mode
        )
        
        return df
        
    except Exception as e:
        elapsed_time = time.time() - start_time
        logger.warning(
            "异步读取Parquet失败，降级到同步读取: %s （耗时: %.3f秒）",
            e, elapsed_time
        )
        # 最终降级
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, pd.read_parquet, file_path)
```

### 11.4 应用场景详细说明

#### 11.4.1 Parquet文件异步读写

**应用位置**：`data_storage.py` - `StorageManager`

**读取场景**：
```python
class StorageManager:
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
            # 🚀 使用native_iocp异步读取
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
```

**写入场景**：
```python
    async def save_data_async(
        self,
        symbol: str,
        interval: str,
        df: pd.DataFrame
    ) -> bool:
        """异步保存数据（使用native_iocp）"""
        file_path = self.get_data_path(symbol, interval)
        
        try:
            # 🚀 使用native_iocp异步写入
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
```

#### 11.4.2 缓存文件异步读写

**应用位置**：`data_module.py` - `DailyCacheManager`

**异步保存缓存**：
```python
class DailyCacheManager:
    @staticmethod
    async def save_with_date_async(data: Any, cache_file: Path) -> bool:
        """异步保存数据并记录日期（使用native_iocp）"""
        try:
            from backend.infrastructure.native_iocp import compat_aopen
            import json
            
            # 构建缓存对象
            cache_obj = {
                "cache_date": DailyCacheManager.get_today(),
                "data": data
            }
            
            # 序列化为JSON
            json_data = json.dumps(
                cache_obj, 
                ensure_ascii=False, 
                indent=2, 
                default=str
            )
            
            # 🚀 使用native_iocp异步写入
            async with await compat_aopen(cache_file, 'w', encoding='utf-8') as f:
                await f.write(json_data)
            
            logger.debug("缓存已保存: %s (日期: %s)", cache_file, cache_obj["cache_date"])
            return True
            
        except Exception as e:
            logger.error("保存缓存失败 (%s): %s", cache_file, e, exc_info=True)
            return False
```

**异步加载缓存**：
```python
    @staticmethod
    async def load_with_validation_async(
        cache_file: Path
    ) -> Tuple[Optional[Any], Optional[str], bool]:
        """异步加载数据并验证日期（使用native_iocp）"""
        try:
            if not cache_file.exists():
                return None, None, False
            
            from backend.infrastructure.native_iocp import compat_aopen
            import json
            
            # 🚀 使用native_iocp异步读取
            async with await compat_aopen(cache_file, 'r', encoding='utf-8') as f:
                content = await f.read()
            
            if not content.strip():
                logger.warning("缓存文件为空: %s", cache_file)
                return None, None, False
            
            cache_obj = json.loads(content)
            data = cache_obj.get("data")
            cache_date = cache_obj.get("cache_date")
            
            # 验证日期
            is_valid = DailyCacheManager.is_cache_valid(cache_date)
            
            return data, cache_date, is_valid
            
        except Exception as e:
            logger.error("加载缓存失败: %s", e, exc_info=True)
            return None, None, False
```

#### 11.4.3 质量扫描文件异步读取

**应用位置**：`data_quality.py` - `DataSensor`

```python
async def _scan_symbol_quality_async(
    symbol: str, 
    intervals: List[str], 
    data_dir: str
) -> Optional[dict]:
    """异步扫描单个品种的质量（使用native_iocp）"""
    try:
        quality_dict = {"symbol": symbol, "intervals": {}}
        
        for interval in intervals:
            file_path = Path(data_dir) / interval / f"{symbol}.parquet"
            
            if not file_path.exists():
                quality_dict["intervals"][interval] = {"missing": True}
                continue
            
            # 🚀 使用native_iocp异步读取
            df = await _read_parquet_async(file_path)
            
            # 执行质量检查
            quality_result = validate_data_quality(df)
            quality_dict["intervals"][interval] = quality_result
        
        return quality_dict
        
    except Exception as e:
        logger.error(f"异步扫描品种 {symbol} 失败: {e}")
        return None
```

---

## 十二、子进程日志配置业务规则

> **架构设计参考**：日志系统架构请参考 [统一日志系统文档](../system_vnpy/系统监控完整集成指南.md)

### 12.1 LogHub统一路由接入流程

#### 12.1.1 四步接入流程

**Step 1: 获取LogHub实例**
```python
from backend.infrastructure.system_vnpy.unified_log_system import get_logging_hub

hub = get_logging_hub()
```

**功能说明**：
- 获取全局单例LogHub实例
- LogHub负责统一路由所有日志消息
- 支持3层路由架构（模块→阶段→全局）

**Step 2: 清理继承的handler**
```python
root_logger = logging.getLogger()
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)
    handler.close()
```

**功能说明**：
- 子进程会继承父进程的所有handler
- 必须清理旧handler，否则日志重复输出
- `handler.close()`确保资源释放

**Step 3: 添加LogHub到root logger**
```python
root_logger.addHandler(hub)
root_logger.setLevel(logging.DEBUG)
```

**功能说明**：
- 将LogHub作为唯一的handler添加到root logger
- 设置DEBUG级别确保捕获所有日志
- 通过LogHub的路由规则控制实际输出

**Step 4: 创建子进程专用logger**
```python
logger_name = f"subprocess.{task_type}.{worker_id}"
subprocess_logger = logging.getLogger(logger_name)
subprocess_logger.propagate = True
```

**功能说明**：
- 使用标准化命名格式标识子进程
- `propagate=True`让日志传播到root logger
- root logger的LogHub会处理所有传播的日志

#### 12.1.2 完整配置函数实现

```python
def _configure_subprocess_logging(
    worker_id: int, 
    task_type: str = "worker"
):
    """配置子进程日志系统，接入LogHub统一路由
    
    Args:
        worker_id: 子进程ID
        task_type: 任务类型（worker/quality_scan/ipo/finance等）
    
    Returns:
        配置好的logger实例
    """
    import logging
    import sys
    
    try:
        # Step 1: 获取LogHub实例
        from backend.infrastructure.system_vnpy.unified_log_system import get_logging_hub
        hub = get_logging_hub()
        
        # Step 2: 清理子进程继承的所有handler（避免重复输出）
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            handler.close()
        
        # Step 3: 将LogHub添加到root logger
        root_logger.addHandler(hub)
        root_logger.setLevel(logging.DEBUG)
        
        # Step 4: 创建子进程专用logger（带worker_id标识）
        logger_name = f"subprocess.{task_type}.{worker_id}"
        subprocess_logger = logging.getLogger(logger_name)
        subprocess_logger.propagate = True  # 让日志传播到root logger
        
        subprocess_logger.info(f"✅ 子进程 {worker_id} 日志系统已接入LogHub")
        return subprocess_logger
        
    except Exception as e:
        # 降级：如果LogHub配置失败，使用标准logger
        fallback_logger = logging.getLogger(__name__)
        fallback_logger.warning(
            f"⚠️ 子进程 {worker_id} LogHub配置失败，使用降级日志: {e}"
        )
        return fallback_logger
```

### 12.2 子进程日志命名规范

#### 12.2.1 命名格式标准

**格式定义**：`subprocess.{task_type}.{worker_id}`

**命名组成部分**：
1. **前缀**：`subprocess` - 标识这是子进程日志
2. **任务类型**：`{task_type}` - 标识任务的业务类型
3. **进程ID**：`{worker_id}` - 唯一标识具体的worker进程

#### 12.2.2 任务类型枚举

| task_type | 说明 | 应用场景 |
|-----------|------|----------|
| `worker` | K线下载进程 | 多进程+协程K线下载 |
| `quality_scan` | 质量扫描进程 | 多进程并发数据质量扫描 |
| `ipo` | IPO下载进程 | 批量IPO日期下载 |
| `finance` | 财务数据下载进程 | 批量财务数据下载 |
| `server_test` | 服务器测速进程 | 服务器池并发测速 |
| `tdx_read` | TDX本地读取进程 | 批量读取通达信本地文件 |

#### 12.2.3 命名示例

```python
# K线下载进程 Worker 0
logger_name = "subprocess.worker.0"

# K线下载进程 Worker 15
logger_name = "subprocess.worker.15"

# 质量扫描进程 Worker 2
logger_name = "subprocess.quality_scan.2"

# IPO下载进程 Worker 5
logger_name = "subprocess.ipo.5"

# 服务器测速进程 Worker 1
logger_name = "subprocess.server_test.1"
```

### 12.3 Handler清理机制

#### 12.3.1 清理原因详解

**问题背景**：
- Python的`multiprocessing`模块在创建子进程时会复制父进程的完整状态
- 父进程的所有logger和handler都会被继承到子进程
- 如果不清理，日志会同时被父进程和子进程的handler处理
- 导致日志重复输出、文件冲突、性能下降

**清理目标**：
1. 移除所有继承的FileHandler（避免文件写入冲突）
2. 移除所有继承的StreamHandler（避免终端重复输出）
3. 移除所有继承的LogHub handler（避免双重路由）

#### 12.3.2 清理实现详解

```python
# 获取root logger
root_logger = logging.getLogger()

# 遍历所有handler（使用切片复制，避免遍历时修改）
for handler in root_logger.handlers[:]:
    # 从root logger移除handler
    root_logger.removeHandler(handler)
    
    # 关闭handler，释放资源
    # - FileHandler: 关闭文件句柄
    # - StreamHandler: 刷新缓冲区
    # - SocketHandler: 关闭网络连接
    handler.close()
```

**关键点说明**：
1. **使用切片复制**：`handlers[:]` 创建列表副本，避免迭代时修改
2. **先移除后关闭**：确保handler不再处理新日志后再关闭
3. **必须close()**：释放文件句柄、网络连接等资源

#### 12.3.3 清理影响范围

**影响范围**：
- 仅影响当前子进程的logger配置
- 不影响父进程的logger配置
- 不影响其他子进程的logger配置

**清理后的状态**：
- root logger的handlers列表为空
- 所有旧handler资源已释放
- 准备添加新的LogHub handler

### 12.4 日志传播机制

#### 12.4.1 传播链路设计

```
子进程专用logger (subprocess.worker.0)
    ↓ propagate=True
root logger
    ↓ handlers=[LogHub]
LogHub (统一路由)
    ↓ 3层路由规则
    ├─ Layer 3: 模块规则 (subprocess.worker.*)
    ├─ Layer 2: 阶段规则 (downloading)
    └─ Layer 1: 全局规则 (兜底)
    ↓
    ├─ AI日志文件 (完整日志)
    ├─ 终端输出 (过滤后)
    └─ 系统日志文件
```

#### 12.4.2 propagate属性详解

**propagate=True（默认值，必须显式设置）**：
- 子进程logger产生的日志会传播到父logger
- 最终传播到root logger
- root logger的LogHub会处理所有传播的日志

**propagate=False（禁止传播，谨慎使用）**：
- 日志不会传播到父logger
- 必须为该logger添加独立的handler
- 通常不建议在子进程中使用

#### 12.4.3 日志级别设置规范

**root logger级别**：
```python
root_logger.setLevel(logging.DEBUG)
```
- 必须设置为DEBUG级别
- 确保所有级别的日志都能传递到LogHub
- LogHub通过路由规则控制实际输出

**子进程logger级别**：
```python
subprocess_logger = logging.getLogger(f"subprocess.{task_type}.{worker_id}")
# 不设置level，继承root logger的DEBUG级别
```
- 通常不单独设置level
- 继承root logger的DEBUG级别
- 通过LogHub路由规则控制输出

### 12.5 应用场景示例

#### 12.5.1 K线下载进程日志配置

```python
def _run_kline_download_worker(*args):
    """K线下载worker进程入口函数"""
    import warnings
    
    # 抑制ResourceWarning
    warnings.filterwarnings(
        "ignore", 
        category=ResourceWarning, 
        message=".*socket.*"
    )
    
    # 配置子进程日志
    logger = _configure_subprocess_logging(
        worker_id=args[0],  # 第一个参数是worker_id
        task_type="worker"
    )
    
    # 运行异步事件循环
    asyncio.run(_kline_download_worker_async(*args))
```

#### 12.5.2 质量扫描进程日志配置

```python
def _run_quality_scan_worker(*args):
    """质量扫描worker进程入口函数"""
    import warnings
    
    # 抑制ResourceWarning
    warnings.filterwarnings(
        "ignore", 
        category=ResourceWarning, 
        message=".*socket.*"
    )
    
    # 配置子进程日志
    logger = _configure_subprocess_logging(
        worker_id=args[0],
        task_type="quality_scan"
    )
    
    # 运行异步事件循环
    asyncio.run(_quality_scan_worker_async(*args))
```

#### 12.5.3 IPO下载进程日志配置

```python
def _run_ipo_download_worker(*args):
    """IPO下载worker进程入口函数"""
    # 配置子进程日志
    logger = _configure_subprocess_logging(
        worker_id=args[0],
        task_type="ipo"
    )
    
    # 运行异步事件循环
    asyncio.run(_ipo_download_worker_async(*args))
```

### 12.6 降级机制

#### 12.6.1 LogHub不可用时的降级

```python
try:
    from backend.infrastructure.system_vnpy.unified_log_system import get_logging_hub
    hub = get_logging_hub()
    # ... 正常配置流程
except Exception as e:
    # 降级：使用标准logger
    fallback_logger = logging.getLogger(__name__)
    fallback_logger.warning(
        f"⚠️ 子进程 {worker_id} LogHub配置失败，使用降级日志: {e}"
    )
    return fallback_logger
```

**降级行为**：
- 使用Python标准logging配置
- 日志输出到stderr
- 不支持AI日志文件
- 不支持3层路由规则

#### 12.6.2 降级日志记录要求

- 必须记录降级原因
- 使用WARNING级别
- 包含worker_id信息
- 包含异常详细信息

---

## 十三、背压控制与队列管理业务规则

> **架构设计参考**：背压控制架构请参考 [最佳实践文档 - 2.2 data_acquisition.py](./data_module_vnpy新架构最佳实践cursor版.md#22-data_acquisitionpy---数据获取模块)

### 13.1 队列跳过统计机制

#### 13.1.1 数据结构定义

**全局统计字典**：
```python
_queue_skip_stats = {
    "{queue_name}_{worker_id}": {
        "skip_count": int,      # 累计跳过次数
        "last_warning": int,    # 上次告警的skip_count值
    }
}
```

**线程安全锁**：
```python
_queue_skip_lock = threading.Lock()
```

**示例数据**：
```python
{
    "result_queue_0": {
        "skip_count": 156,
        "last_warning": 150
    },
    "progress_queue_3": {
        "skip_count": 23,
        "last_warning": 20
    }
}
```

#### 13.1.2 分级告警规则

**前3次：每次都记录WARNING**
```python
if skip_count <= 3:
    logger.warning(
        f"⚠️ 队列入队失败（{error_type}）: "
        f"队列={queue_name}, Worker={worker_id}, "
        f"累计跳过={skip_count}次, 超时={timeout}s"
    )
```

**第10次起：每10次记录一次WARNING**
```python
if skip_count % 10 == 1:
    logger.warning(
        f"⚠️ 队列入队失败（{error_type}）: "
        f"队列={queue_name}, Worker={worker_id}, "
        f"累计跳过={skip_count}次, 超时={timeout}s"
    )
```

**第100次：记录ERROR级别严重告警**
```python
if skip_count == 100:
    logger_alert.error(
        f"🔥 队列严重积压告警: "
        f"队列={queue_name}, Worker={worker_id}, "
        f"累计跳过={skip_count}次，消费者可能过慢！"
    )
```

**第500次起：每500次记录一次ERROR**
```python
if skip_count % 500 == 0:
    logger_alert.error(
        f"🔥 队列严重积压告警: "
        f"队列={queue_name}, Worker={worker_id}, "
        f"累计跳过={skip_count}次，消费者可能过慢！"
    )
```

#### 13.1.3 统计复位机制

**复位时机**：
1. 下载任务完成时调用`_reset_queue_skip_stats()`
2. 质量扫描完成时复位统计
3. IPO下载完成时复位统计

**复位实现**：
```python
def _reset_queue_skip_stats():
    """重置队列跳过统计"""
    with _queue_skip_lock:
        _queue_skip_stats.clear()
```

**复位日志**：
```python
logger.info("队列跳过统计已重置")
```

#### 13.1.4 统计查询接口

```python
def _get_queue_skip_stats() -> Dict[str, Dict[str, int]]:
    """获取队列跳过统计（用于监控）
    
    Returns:
        统计字典的副本
    """
    with _queue_skip_lock:
        return dict(_queue_skip_stats)
```

**使用示例**：
```python
# 在下载完成后查询统计
stats = _get_queue_skip_stats()
for queue_key, queue_stats in stats.items():
    logger.info(
        f"队列 {queue_key} 跳过统计: {queue_stats['skip_count']}次"
    )
```

### 13.2 安全入队函数实现

#### 13.2.1 函数签名

```python
def _safe_put_queue(
    q,
    item,
    timeout: float = 1.0,
    queue_name: str = "queue",
    worker_id: Optional[int] = None,
) -> bool:
    """安全入队，支持超时阻塞和跳过策略（背压控制）
    
    Args:
        q: 队列对象
        item: 要入队的数据
        timeout: 超时时间（秒）
        queue_name: 队列名称（用于日志）
        worker_id: Worker ID（用于统计）
    
    Returns:
        bool: True=入队成功, False=入队失败（队列满）
    """
```

#### 13.2.2 设计原理

**1. 阻塞等待（有超时）**：
- 队列满时等待timeout秒
- 而非立即失败或无限等待
- 给消费者一定的处理时间

**2. 超时跳过**：
- 超时后记录警告并丢弃任务
- 避免生产者阻塞影响其他任务
- 通过统计监控队列积压情况

**3. 统计监控**：
- 记录跳过次数，触发告警
- 帮助发现系统瓶颈
- 支持动态调整策略

#### 13.2.3 完整实现

```python
def _safe_put_queue(
    q,
    item,
    timeout: float = 1.0,
    queue_name: str = "queue",
    worker_id: Optional[int] = None,
) -> bool:
    """安全入队，支持超时阻塞和跳过策略（背压控制）"""
    import logging
    
    logger = logging.getLogger("backend.data_module.download")
    logger_alert = logging.getLogger("backend.data_module.alert")
    
    try:
        # 尝试入队（阻塞等待，最多timeout秒）
        q.put(item, timeout=timeout)
        return True
        
    except Exception as e:
        # 队列满或其他异常
        error_type = type(e).__name__
        
        # 统计跳过次数（线程安全）
        stats_key = (
            f"{queue_name}_{worker_id}" 
            if worker_id is not None 
            else queue_name
        )
        
        with _queue_skip_lock:
            if stats_key not in _queue_skip_stats:
                _queue_skip_stats[stats_key] = {
                    "skip_count": 0, 
                    "last_warning": 0
                }
            
            _queue_skip_stats[stats_key]["skip_count"] += 1
            skip_count = _queue_skip_stats[stats_key]["skip_count"]
            
            # 分级告警
            if skip_count % 10 == 1 or skip_count <= 3:
                logger.warning(
                    f"⚠️ 队列入队失败（{error_type}）: "
                    f"队列={queue_name}, Worker={worker_id}, "
                    f"累计跳过={skip_count}次, 超时={timeout}s"
                )
                _queue_skip_stats[stats_key]["last_warning"] = skip_count
            
            # 严重告警
            if skip_count == 100 or skip_count % 500 == 0:
                logger_alert.error(
                    f"🔥 队列严重积压告警: "
                    f"队列={queue_name}, Worker={worker_id}, "
                    f"累计跳过={skip_count}次，消费者可能过慢！"
                )
        
        return False
```

### 13.3 应用场景

#### 13.3.1 下载结果队列背压控制

```python
# 在K线下载worker中应用
async def kline_download_worker(worker_id, task_queue, result_queue, ...):
    while True:
        # 获取任务
        symbol, interval = await get_task_from_queue(task_queue)
        
        # 下载数据
        data = await download_kline(symbol, interval)
        
        # 🆕 背压控制：使用_safe_put_queue代替原来的无限等待
        success = await asyncio.to_thread(
            _safe_put_queue,
            result_queue,
            (symbol, interval, data),
            timeout=1.0,
            queue_name="result_queue",
            worker_id=worker_id,
        )
        
        if success:
            await asyncio.to_thread(progress_queue.put, (symbol, interval, "success"))
        else:
            # 队列满，跳过该任务
            await asyncio.to_thread(progress_queue.put, (symbol, interval, "skipped"))
```

#### 13.3.2 进度队列背压控制

```python
# 在质量扫描worker中应用
async def quality_scan_worker(worker_id, task_queue, result_queue, progress_queue, ...):
    while True:
        # 获取任务
        symbol = await get_task_from_queue(task_queue)
        
        # 扫描质量
        quality_dict = await scan_symbol_quality(symbol)
        
        # 上报进度（带背压控制）
        success = await asyncio.to_thread(
            _safe_put_queue,
            progress_queue,
            (symbol, "success"),
            timeout=0.5,  # 进度队列超时更短
            queue_name="progress_queue",
            worker_id=worker_id,
        )
        
        if not success:
            logger.debug(f"进度上报失败，跳过: {symbol}")
```

### 13.4 监控与诊断

#### 13.4.1 实时监控

```python
# 在主进程中定期查询统计
def monitor_queue_pressure():
    """监控队列压力"""
    stats = _get_queue_skip_stats()
    
    for queue_key, queue_stats in stats.items():
        skip_count = queue_stats["skip_count"]
        
        if skip_count > 100:
            logger_alert.warning(
                f"⚠️ 队列 {queue_key} 积压严重: {skip_count}次跳过"
            )
        elif skip_count > 10:
            logger.info(
                f"ℹ️ 队列 {queue_key} 有轻微积压: {skip_count}次跳过"
            )
```

#### 13.4.2 任务完成后诊断

```python
# 在下载任务完成后输出诊断信息
def log_queue_statistics():
    """输出队列统计信息（用于诊断）"""
    stats = _get_queue_skip_stats()
    
    if stats:
        logger.info("===== 队列跳过统计 =====")
        for queue_key, queue_stats in stats.items():
            logger.info(
                f"  {queue_key}: {queue_stats['skip_count']}次跳过"
            )
        logger.info("==========================")
    
    # 重置统计
    _reset_queue_skip_stats()
```

---

## 文档总结

本文档专注于data_module_vnpy新架构的业务流程规则和实现逻辑，包括：

### 核心业务规则
1. **品种管理规则**：分类标准、过滤规则、缓存机制
2. **数据下载规则**：两段式下载策略、并发控制、任务分配
3. **数据验证规则**：格式验证、逻辑验证、完整性检查

### 实现算法
- 智能起点计算算法
- 日期范围异常处理
- 停牌日期识别算法
- IPv6池降级机制

### 业务流程
- 品种加载完整流程
- 下载任务管理流程  
- 数据验证执行流程

> **技术架构参考**：详细的组件设计、异步操作、错误处理等技术架构请参考 [最佳实践文档](./data_module_vnpy新架构最佳实践cursor版.md)
