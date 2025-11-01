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
