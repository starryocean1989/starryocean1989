# -*- coding: utf-8 -*-
# data_module_vnpy 新架构业务细节文档

**版本**: v3.0 (基于新架构最佳实践)
**创建日期**: 2025-01-02
**文档目标**: 定义新架构下的业务流程规则细节，补全技术架构文档缺失的业务逻辑

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

### 1.1 品种分类规则

#### 1.1.1 市场分类标准

**上证A股分类规则**：
```python
# 市场代码：market=1
# 代码规则：以60或68开头的6位数字
def is_shanghai_a_stock(code: str) -> bool:
    return len(code) == 6 and code.isdigit() and (code.startswith('60') or code.startswith('68'))
```

**深证A股分类规则**：
```python
# 市场代码：market=0  
# 代码规则：以00或30开头的6位数字
def is_shenzhen_a_stock(code: str) -> bool:
    return len(code) == 6 and code.isdigit() and (code.startswith('00') or code.startswith('30'))
```

**北证A股分类规则**：
```python
# 市场代码：market=2
# 代码规则：以8、4或920开头的6位数字
def is_beijing_a_stock(code: str) -> bool:
    if len(code) == 6 and code.isdigit():
        return code.startswith('8') or code.startswith('4') or code.startswith('920')
    return False
```

**T+0基金分类规则**：
```python
# 代码规则：以511、159、512、513、515、516、518开头
def is_t0_fund(code: str) -> bool:
    prefixes = ['511', '159', '512', '513', '515', '516', '518']
    return len(code) == 6 and code.isdigit() and any(code.startswith(p) for p in prefixes)
```

**可转债分类规则**：
```python
# 代码规则：以11或12开头的6位数字
def is_convertible_bond(code: str) -> bool:
    return len(code) == 6 and code.isdigit() and (code.startswith('11') or code.startswith('12'))
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
    (2, "北证A股")   # 北京市场
]
```

**错误处理规则**：
- **网络超时**：3秒超时，最多重试3次
- **API异常**：记录错误日志，使用缓存数据
- **数据格式错误**：跳过异常记录，继续处理其他数据

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
- **名称清理**：去除特殊字符和多余空格
- **市场验证**：确保市场代码在有效范围内(0,1,2)

---

## 二、数据下载业务规则

### 2.1 下载策略规则

#### 2.1.1 两段式下载策略

**第一阶段：IPv4池下载**：
- **适用场景**：绝大部分K线数据下载
- **服务器选择**：优先使用IPv4服务器池
- **并发控制**：根据负载均衡器动态调整
- **切换条件**：剩余任务数 ≤ 切换阈值时进入第二阶段

**第二阶段：IPv6池下载**：
- **适用场景**：剩余少量任务或IPv4池性能不佳时
- **服务器选择**：使用IPv6服务器池
- **降级策略**：IPv6不可用时自动回退到IPv4池
- **性能监控**：实时监控IPv6连接质量

**切换阈值计算**：
```python
def calculate_switch_threshold(total_tasks: int, ipv4_servers: int, ipv6_servers: int) -> int:
    """计算两段式下载的切换阈值"""
    # 基础阈值：总任务数的10%
    base_threshold = max(100, int(total_tasks * 0.1))
    
    # 根据服务器数量调整
    if ipv6_servers > ipv4_servers:
        # IPv6服务器更多，提前切换
        return int(base_threshold * 1.5)
    elif ipv6_servers < ipv4_servers * 0.5:
        # IPv6服务器较少，延后切换
        return int(base_threshold * 0.5)
    else:
        return base_threshold
```

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

**进度同步规则**：
- **进度报告频率**：每完成100个任务或每5秒报告一次
- **跨进程同步**：使用native_ipc进行进度同步
- **异常处理**：进程异常时其他进程继续执行

---

## 三、数据验证业务规则

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
            errors.append({
                "type": "high_less_than_low",
                "message": f"最高价小于最低价，共{len(invalid_high_low)}条",
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
    
    # 1. 获取期间内所有交易日
    expected_trading_days = get_trading_days_in_range(start_date, end_date, context.trading_days)
    
    # 2. 获取实际数据日期
    if df.empty:
        return expected_trading_days, ["数据为空"]
    
    actual_dates = set(df['datetime'].dt.date)
    
    # 3. 找出缺失的交易日
    missing_dates = [d for d in expected_trading_days if d not in actual_dates]
    
    # 4. 生成缺失原因分析
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
        # 计算交易日滞后
        gap_days = count_trading_days_between(latest_data_date, latest_trading_day, context.trading_days)
    
    # 4. 判断新鲜度
    is_fresh = gap_days <= context.freshness_days_warning
    
    # 5. 计算新鲜度评分
    if gap_days == 0:
        freshness_score = 100.0
    elif gap_days <= context.freshness_days_warning:
        freshness_score = max(70.0, 100.0 - gap_days * 5)
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
    # 1. 获取IPO日期数据
    ipo_cache = get_ipo_cache()
    ipo_dates = {}
    for symbol in get_all_symbols():
        ipo_date, _ = ipo_cache.get(symbol)
        if ipo_date:
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

---

## 四、缓存管理业务规则

### 4.1 日期失效缓存机制

#### 4.1.1 缓存失效规则

**时间失效判断**：
```python
def is_cache_valid(cache_date: str, use_network_time: bool = True) -> bool:
    """判断缓存是否有效（基于日期）"""
    if not cache_date:
        return False
    
    try:
        # 解析缓存日期
        cached_date = datetime.strptime(cache_date, "%Y-%m-%d").date()
        
        # 获取当前日期（优先使用网络时间）
        if use_network_time:
            current_date = get_real_date()  # 网络时间
        else:
            current_date = date.today()     # 系统时间
        
        # 缓存有效条件：缓存日期 >= 当前日期
        return cached_date >= current_date
        
    except (ValueError, TypeError):
        return False
```

**缓存文件格式标准**：
```python
# 标准缓存文件结构
CACHE_FILE_TEMPLATE = {
    "_meta": {
        "cache_date": "YYYY-MM-DD",    # 缓存创建日期
        "version": "x.x",              # 数据版本
        "created_at": "YYYY-MM-DD HH:MM:SS",  # 创建时间戳
        "expires_at": "YYYY-MM-DD 23:59:59"   # 失效时间
    },
    "data": {}  # 实际缓存数据
}
```

#### 4.1.2 缓存更新策略

**自动更新规则**：
- **触发条件**：缓存失效或强制刷新
- **更新时机**：每日首次访问时检查
- **原子操作**：使用临时文件+重命名确保原子性
- **并发控制**：文件锁防止并发写入

**缓存清理规则**：
```python
def cleanup_expired_caches(cache_dir: Path) -> int:
    """清理过期缓存文件"""
    cleaned_count = 0
    current_date = get_real_date()
    
    for cache_file in cache_dir.glob("*.json"):
        try:
            # 读取缓存元数据
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            cache_date = data.get("_meta", {}).get("cache_date")
            if cache_date:
                cached_date = datetime.strptime(cache_date, "%Y-%m-%d").date()
                
                # 删除超过7天的过期缓存
                if (current_date - cached_date).days > 7:
                    cache_file.unlink()
                    cleaned_count += 1
                    
        except Exception as e:
            logger.warning(f"清理缓存文件失败 {cache_file}: {e}")
    
    return cleaned_count
```

### 4.2 LRU缓存规则

#### 4.2.1 缓存容量管理

**容量配置规则**：
```python
# 不同类型缓存的容量配置
CACHE_CAPACITY_CONFIG = {
    "preload_cache": 64,        # 预加载缓存：64个品种
    "symbol_cache": 1000,       # 品种信息缓存：1000条
    "validation_cache": 500,    # 验证结果缓存：500条
    "server_pool_cache": 1,     # 服务器池缓存：1份（单例）
    "ipo_date_cache": 10000     # IPO日期缓存：10000条
}
```

**淘汰策略规则**：
```python
def evict_lru_items(cache: LRUCacheManager, target_size: int) -> int:
    """LRU淘汰策略"""
    evicted_count = 0
    
    while len(cache) > target_size:
        # 1. 找到最久未使用的项
        lru_key = cache.get_lru_key()
        
        # 2. 检查是否有保护标记
        if cache.is_protected(lru_key):
            # 跳过受保护的项，寻找下一个
            continue
        
        # 3. 执行淘汰
        evicted_value = cache.delete(lru_key)
        evicted_count += 1
        
        # 4. 触发淘汰回调
        if cache.on_evict:
            cache.on_evict(lru_key, evicted_value)
    
    return evicted_count
```

#### 4.2.2 TTL过期管理

**TTL检查规则**：
```python
def check_ttl_expiration(cache: LRUCacheManager) -> List[str]:
    """检查TTL过期项"""
    expired_keys = []
    current_time = time.time()
    
    for key, (value, access_time, ttl) in cache._data.items():
        if ttl and (current_time - access_time) > ttl:
            expired_keys.append(key)
    
    # 批量删除过期项
    for key in expired_keys:
        cache.delete(key)
    
    return expired_keys
```

**TTL配置规则**：
```python
# 不同数据类型的TTL配置
TTL_CONFIG = {
    "kline_data": 3600,         # K线数据：1小时
    "symbol_info": 86400,       # 品种信息：24小时
    "validation_result": 1800,  # 验证结果：30分钟
    "server_list": 86400,       # 服务器列表：24小时
    "ipo_date": None            # IPO日期：永不过期
}
```

### 4.3 预加载缓存规则

#### 4.3.1 预加载策略

**预加载品种选择**：
```python
def select_preload_symbols(config: Dict, access_history: Dict) -> List[str]:
    """选择预加载品种"""
    # 1. 配置指定的品种（优先级最高）
    configured_symbols = config.get("chinastock.preload_symbols", [])
    
    # 2. 热门品种（基于访问频率）
    hot_symbols = get_hot_symbols_by_access(access_history, limit=20)
    
    # 3. 重要指数成分股
    index_symbols = ["000001", "000002", "600000", "600036", "600519"]
    
    # 4. 合并去重，限制总数
    all_symbols = list(dict.fromkeys(configured_symbols + hot_symbols + index_symbols))
    max_preload = config.get("chinastock.max_preload_cache", 64)
    
    return all_symbols[:max_preload]
```

**预加载时机规则**：
- **启动预加载**：系统启动后延迟5秒开始
- **增量预加载**：检测到新的热门品种时触发
- **定时预加载**：每小时检查一次预加载状态
- **手动预加载**：用户查询时触发相关品种预加载

#### 4.3.2 预加载数据管理

**数据周期优先级**：
```python
# 预加载数据的周期优先级
PRELOAD_INTERVAL_PRIORITY = [
    "1d",    # 日线（最高优先级）
    "5m",    # 5分钟线
    "1m"     # 1分钟线（最低优先级）
]
```

**预加载更新规则**：
```python
def update_preload_cache(symbol: str, interval: str, df: pd.DataFrame) -> bool:
    """更新预加载缓存"""
    cache_key = f"{symbol}_{interval}"
    
    # 1. 检查数据质量
    if df.empty or len(df) < 10:
        logger.warning(f"数据质量不足，跳过预加载: {cache_key}")
        return False
    
    # 2. 数据截取（只保留最近的数据）
    if len(df) > 1000:
        df = df.tail(1000)  # 只保留最近1000条
    
    # 3. 更新缓存
    preload_service.add_to_cache(symbol, interval, df)
    
    # 4. 记录访问统计
    access_tracker.record_preload(symbol, interval)
    
    return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
```

### 4.4 跨进程缓存同步

#### 4.4.1 缓存同步规则

**同步触发条件**：
- **缓存更新**：本地缓存发生变更时
- **定时同步**：每5分钟进行一次同步检查
- **进程启动**：新进程启动时拉取最新缓存
- **手动同步**：管理员触发的强制同步

**同步数据格式**：
```python
# 缓存同步消息格式
CACHE_SYNC_MESSAGE = {
    "action": "sync_cache",
    "cache_type": "preload|symbol|validation",
    "operation": "update|delete|clear",
    "data": {
        "key": "cache_key",
        "value": "cache_value",
        "timestamp": "sync_timestamp"
    },
    "source_process": "process_id"
}

---

## 五、负载均衡业务规则

### 5.1 木桶理论压力评估

#### 5.1.1 压力评分计算规则

**木桶理论核心原则**：
```python
def calculate_system_pressure_score(system_metrics: Dict) -> Dict[str, Any]:
    """基于木桶理论计算系统压力评分"""
    
    # 1. 计算各维度评分（0-100分，分数越低压力越大）
    cpu_score = calculate_cpu_score(system_metrics)
    memory_score = calculate_memory_score(system_metrics)
    disk_score = calculate_disk_score(system_metrics)
    network_score = calculate_network_score(system_metrics)
    
    # 2. 木桶理论：系统性能 = min(各维度性能)
    # 关键：只看最短的那块板，不是加权平均
    bottleneck_score = min(cpu_score, memory_score, disk_score, network_score)
    
    # 3. 确定瓶颈资源
    if bottleneck_score == cpu_score:
        bottleneck_resource = "cpu"
    elif bottleneck_score == memory_score:
        bottleneck_resource = "memory"
    elif bottleneck_score == disk_score:
        bottleneck_resource = "disk"
    else:
        bottleneck_resource = "network"
    
    return {
        "pressure_score": 100 - bottleneck_score,  # 转换为压力分数
        "bottleneck": bottleneck_resource,
        "resource_scores": {
            "cpu": cpu_score,
            "memory": memory_score, 
            "disk": disk_score,
            "network": network_score
        },
        "scale_suggestion": calculate_scale_factor(bottleneck_score)
    }
```

**CPU压力评分规则**：
```python
def calculate_cpu_score(metrics: Dict) -> float:
    """计算CPU压力评分"""
    cpu_percent = metrics.get("cpu_percent", 0.0)
    
    # CPU详细指标
    cpu_detailed = metrics.get("cpu_detailed", {})
    context_switches = cpu_detailed.get("context_switches_per_sec", 0)
    interrupts = cpu_detailed.get("interrupts_per_sec", 0)
    
    # 基础CPU使用率评分（0-100）
    cpu_usage_score = max(0, 100 - cpu_percent)
    
    # 上下文切换压力评分（经验值：>50000/秒为高压）
    ctx_pressure = min(100, context_switches / 500)  # 归一化到0-100
    ctx_score = max(0, 100 - ctx_pressure)
    
    # 中断压力评分（经验值：>20000/秒为高压）
    int_pressure = min(100, interrupts / 200)  # 归一化到0-100
    int_score = max(0, 100 - int_pressure)
    
    # 加权计算最终CPU评分
    final_score = (
        cpu_usage_score * 0.6 +    # CPU使用率权重60%
        ctx_score * 0.25 +         # 上下文切换权重25%
        int_score * 0.15           # 中断权重15%
    )
    
    return max(0, min(100, final_score))
```

**内存压力评分规则**：
```python
def calculate_memory_score(metrics: Dict) -> float:
    """计算内存压力评分"""
    memory_percent = metrics.get("memory_percent", 0.0)
    
    # 内存子系统指标
    memory_subsystem = metrics.get("memory_subsystem", {})
    swap_in_kbps = memory_subsystem.get("swap_in_kbps", 0)
    swap_out_kbps = memory_subsystem.get("swap_out_kbps", 0)
    
    # 基础内存使用率评分
    memory_usage_score = max(0, 100 - memory_percent)
    
    # 交换分区压力评分（经验值：>256MB/s为高压）
    swap_pressure = max(swap_in_kbps, swap_out_kbps) / 256000  # 256MB/s
    swap_score = max(0, 100 - min(100, swap_pressure * 100))
    
    # 加权计算最终内存评分
    final_score = (
        memory_usage_score * 0.8 +  # 内存使用率权重80%
        swap_score * 0.2            # 交换分区权重20%
    )
    
    return max(0, min(100, final_score))
```

#### 5.1.2 并发调整级别

**压力等级划分**：
```python
def get_pressure_level_config(pressure_score: float) -> Dict[str, Any]:
    """根据压力评分确定调整级别"""
    
    if pressure_score <= 30:
        return {
            "level": "normal",
            "scale_factor": 1.6,        # 可以增加60%并发
            "description": "系统压力正常，可适度增加并发"
        }
    elif pressure_score <= 50:
        return {
            "level": "medium", 
            "scale_factor": 1.0,        # 保持当前并发
            "description": "系统压力中等，维持当前并发"
        }
    elif pressure_score <= 70:
        return {
            "level": "high",
            "scale_factor": 0.7,        # 减少30%并发
            "description": "系统压力较高，需要降低并发"
        }
    else:
        return {
            "level": "critical",
            "scale_factor": 0.3,        # 减少70%并发
            "description": "系统压力严重，大幅降低并发"
        }
```

### 5.2 智能防抖机制

#### 5.2.1 防抖决策规则

**防抖间隔计算**：
```python
class IntelligentDebounceManager:
    """智能防抖管理器"""
    
    def __init__(self):
        self._evaluation_history = deque(maxlen=3)  # 保存最近3次评估结果
        self._base_interval = 1.0      # 基础间隔：1秒
        self._extended_interval = 3.0  # 扩展间隔：3秒
    
    def calculate_next_interval(self, current_action: str) -> float:
        """计算下次评估间隔"""
        self._evaluation_history.append(current_action)
        
        if len(self._evaluation_history) < 3:
            return self._base_interval
        
        # 获取最近3次评估结果
        prev_3, prev_2, prev_1 = list(self._evaluation_history)
        
        # 检查特定模式
        pattern_1 = (prev_3 == "increase" and prev_2 == "decrease" and prev_1 == "increase")
        pattern_2 = (prev_3 == "decrease" and prev_2 == "increase" and prev_1 == "decrease")
        
        if pattern_1 or pattern_2:
            # 检测到震荡模式，使用扩展间隔
            return self._extended_interval
        else:
            # 其他情况使用基础间隔
            return self._base_interval
```

**评估决策逻辑**：
```python
def should_evaluate_now(self, current_time: float, last_evaluation_time: float) -> bool:
    """判断是否应该进行评估"""
    
    # 1. 检查基础时间间隔
    time_elapsed = current_time - last_evaluation_time
    required_interval = self.get_required_interval()
    
    if time_elapsed < required_interval:
        return False
    
    # 2. 检查系统状态变化
    if self.has_significant_change():
        # 系统状态显著变化，立即评估
        return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
    
    # 3. 检查紧急情况
    if self.is_emergency_situation():
        # 紧急情况，忽略防抖
        return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
    
    return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
```

#### 5.2.2 动态调整策略

**调整幅度限制**：
```python
def calculate_safe_adjustment(current_config: Dict, suggested_config: Dict) -> Dict:
    """计算安全的调整幅度"""
    
    # 单次调整限制
    MAX_SCALE_CHANGE = 0.3  # 最大30%变化
    MIN_SCALE_CHANGE = 0.05 # 最小5%变化（死区）
    
    current_scale = current_config.get("scale_factor", 1.0)
    suggested_scale = suggested_config.get("scale_factor", 1.0)
    
    # 计算调整幅度
    scale_change = suggested_scale - current_scale
    
    # 应用死区
    if abs(scale_change) < MIN_SCALE_CHANGE:
        adjusted_scale = current_scale  # 变化太小，不调整
    else:
        # 应用最大变化限制
        if scale_change > MAX_SCALE_CHANGE:
            adjusted_scale = current_scale + MAX_SCALE_CHANGE
        elif scale_change < -MAX_SCALE_CHANGE:
            adjusted_scale = current_scale - MAX_SCALE_CHANGE
        else:
            adjusted_scale = suggested_scale
    
    # 确保在合理范围内
    adjusted_scale = max(0.3, min(1.6, adjusted_scale))
    
    return {
        **suggested_config,
        "scale_factor": adjusted_scale,
        "adjustment_applied": abs(adjusted_scale - current_scale) > 0.01
    }
```

### 5.3 任务类型适配规则

#### 5.3.1 网络任务配置

**网络任务特征识别**：
```python
def configure_network_task(task: NetworkTask, pressure_eval: Dict) -> Dict:
    """配置网络任务参数"""
    
    bottleneck = pressure_eval["bottleneck"]
    scale_factor = pressure_eval["scale_factor"]
    
    # 基础配置
    base_processes = min(8, max(2, cpu_count() // 2))
    base_coroutines_per_process = 50
    
    # 根据瓶颈调整
    if bottleneck == "network":
        # 网络瓶颈：减少连接数，增加超时时间
        processes = max(2, int(base_processes * 0.7))
        coroutines_per_process = max(20, int(base_coroutines_per_process * 0.6))
        connection_timeout = 5.0
        
    elif bottleneck == "cpu":
        # CPU瓶颈：减少进程数
        processes = max(2, int(base_processes * 0.5))
        coroutines_per_process = base_coroutines_per_process
        connection_timeout = 3.0
        
    else:
        # 其他瓶颈：标准配置
        processes = base_processes
        coroutines_per_process = base_coroutines_per_process
        connection_timeout = 3.0
    
    # 应用缩放因子
    final_processes = max(2, int(processes * scale_factor))
    final_coroutines = max(10, int(coroutines_per_process * scale_factor))
    
    return {
        "max_processes": final_processes,
        "coroutines_per_process": final_coroutines,
        "total_connections": final_processes * final_coroutines,
        "connection_timeout": connection_timeout,
        "batch_size": 100
    }
```

#### 5.3.2 本地处理任务配置

**磁盘IO任务配置**：
```python
def configure_disk_task(task: LocalProcessingTask, pressure_eval: Dict) -> Dict:
    """配置磁盘IO任务参数"""
    
    bottleneck = pressure_eval["bottleneck"]
    scale_factor = pressure_eval["scale_factor"]
    
    if bottleneck == "disk":
        # 磁盘瓶颈：多进程并行，小批次
        base_workers = cpu_count()
        batch_size = min(1000, int(2000 * scale_factor))
        
    elif bottleneck == "memory":
        # 内存瓶颈：少进程，更小批次
        base_workers = max(2, cpu_count() // 2)
        batch_size = max(100, int(500 * scale_factor))
        
    else:
        # CPU瓶颈或平衡状态
        base_workers = max(2, int(cpu_count() * 0.8))
        batch_size = 1000
    
    # 应用缩放因子
    final_workers = max(2, int(base_workers * scale_factor))
    
    return {
        "max_workers": final_workers,
        "batch_size": batch_size,
        "queue_size": batch_size * 10,
        "worker_timeout": 30.0
    }

---

## 六、IPO日期管理业务规则

### 6.1 IPO日期获取规则

#### 6.1.1 数据源和格式

**IPO日期数据源**：
- **主要来源**：TDX财务数据接口
- **字段名称**：finance_info.ipo_date
- **数据格式**：整数时间戳（YYYYMMDD格式，如20100101）
- **特殊值处理**：0表示无IPO日期，小于19900000的值视为无效

**IPO日期解析规则**：
```python
def parse_ipo_date(ipo_timestamp: int) -> Optional[date]:
    """解析IPO日期时间戳"""
    
    # 1. 基础验证
    if not ipo_timestamp or ipo_timestamp == 0:
        return None
    
    # 2. 有效性检查（最早1990年）
    if ipo_timestamp < 19900000:
        logger.debug(f"IPO日期无效（值={ipo_timestamp}），可能是未上市品种")
        return None
    
    # 3. 格式转换
    try:
        ipo_str = str(ipo_timestamp).zfill(8)  # 补齐8位
        if len(ipo_str) == 8:
            return datetime.strptime(ipo_str, "%Y%m%d").date()
    except ValueError as e:
        logger.warning(f"IPO日期格式错误: {ipo_timestamp} ({e})")
        return None
    
    return None
```

#### 6.1.2 批量获取策略

**分批下载规则**：
```python
def batch_download_ipo_dates(symbols: List[str], batch_size: int = 100) -> Dict[str, Any]:
    """批量下载IPO日期"""
    
    results = {
        "success": True,
        "total": len(symbols),
        "cached": 0,
        "downloaded": 0,
        "succeeded": 0,
        "failed": 0,
        "data": {},
        "unlisted": []
    }
    
    # 1. 检查缓存命中
    ipo_cache = get_ipo_cache()
    symbols_to_download = []
    
    for symbol in symbols:
        ipo_date, is_cached = ipo_cache.get(symbol)
        if is_cached:
            results["cached"] += 1
            if ipo_date:
                results["data"][symbol] = ipo_date
        else:
            symbols_to_download.append(symbol)
    
    # 2. 分批下载未缓存的品种
    for i in range(0, len(symbols_to_download), batch_size):
        batch_symbols = symbols_to_download[i:i + batch_size]
        batch_results = download_ipo_batch(batch_symbols)
        
        # 合并结果
        results["downloaded"] += batch_results["downloaded"]
        results["succeeded"] += batch_results["succeeded"] 
        results["failed"] += batch_results["failed"]
        results["data"].update(batch_results["data"])
        results["unlisted"].extend(batch_results["unlisted"])
    
    return results
```

**并发下载控制**：
```python
def download_ipo_batch_concurrent(symbols: List[str]) -> Dict[str, Any]:
    """并发下载IPO日期批次"""
    
    # 获取负载均衡配置
    load_balancer = LoadBalancer.get_instance()
    task = IPODownloadTask(symbols=symbols)
    config = load_balancer.get_optimal_config(task)
    
    # 应用并发限制
    max_processes = config["max_processes"]
    coroutines_per_process = config["coroutines_per_process"]
    
    # 分配任务到进程
    process_tasks = split_symbols_for_processes(symbols, max_processes)
    
    # 启动多进程下载
    with ProcessPoolExecutor(max_workers=max_processes) as executor:
        futures = []
        for process_id, process_symbols in enumerate(process_tasks):
            if process_symbols:  # 跳过空任务
                future = executor.submit(
                    download_ipo_worker,
                    process_id,
                    process_symbols,
                    coroutines_per_process
                )
                futures.append(future)
        
        # 收集结果
        all_results = []
        for future in as_completed(futures):
            try:
                result = future.result(timeout=300)  # 5分钟超时
                all_results.append(result)
            except Exception as e:
                logger.error(f"IPO下载进程异常: {e}")
    
    # 合并所有进程的结果
    return merge_ipo_results(all_results)
```

### 6.2 IPO缓存管理规则

#### 6.2.1 两级缓存架构

**内存缓存规则**：
```python
class IPODateCache:
    """IPO日期两级缓存管理器"""
    
    def __init__(self):
        # 内存缓存：{symbol: date}
        self._memory_cache: Dict[str, Optional[date]] = {}
        
        # 原始数据缓存：{symbol: raw_timestamp}
        self._raw_ipo_dates: Dict[str, int] = {}
        
        # 缓存统计
        self._cache_stats = {
            "hit_count": 0,
            "miss_count": 0,
            "update_count": 0
        }
    
    def get(self, symbol: str) -> Tuple[Optional[date], bool]:
        """获取IPO日期"""
        if symbol in self._memory_cache:
            self._cache_stats["hit_count"] += 1
            return self._memory_cache[symbol], True
        else:
            self._cache_stats["miss_count"] += 1
            return None, False
    
    def set(self, symbol: str, finance_info: Dict) -> None:
        """设置IPO日期"""
        raw_ipo_date = finance_info.get("ipo_date", 0)
        ipo_date = self._parse_ipo_date(raw_ipo_date)
        
        self._memory_cache[symbol] = ipo_date
        if raw_ipo_date:
            self._raw_ipo_dates[symbol] = raw_ipo_date
        
        self._cache_stats["update_count"] += 1
```

**文件缓存规则**：
```python
def save_ipo_cache_to_file(cache: IPODateCache, cache_file: Path) -> bool:
    """保存IPO缓存到文件"""
    
    try:
        # 构建缓存数据
        cache_data = {
            "_meta": {
                "cache_date": get_real_date().strftime("%Y-%m-%d"),
                "version": "1.0",
                "count": len(cache._memory_cache),
                "created_at": datetime.now().isoformat()
            },
            "ipo_dates": {}
        }
        
        # 转换日期对象为字符串
        for symbol, ipo_date in cache._memory_cache.items():
            if ipo_date is not None:
                cache_data["ipo_dates"][symbol] = ipo_date.strftime("%Y-%m-%d")
            else:
                cache_data["ipo_dates"][symbol] = None
        
        # 原子写入（临时文件+重命名）
        temp_file = cache_file.with_suffix('.tmp')
        with open(temp_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        
        # 原子重命名
        temp_file.replace(cache_file)
        
        logger.info(f"IPO缓存已保存: {len(cache._memory_cache)}条记录")
        return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
        
    except Exception as e:
        logger.error(f"保存IPO缓存失败: {e}")
        return False
```

#### 6.2.2 缓存更新策略

**增量更新规则**：
```python
def incremental_update_ipo_cache(all_symbols: List[str]) -> Dict[str, int]:
    """增量更新IPO缓存"""
    
    ipo_cache = get_ipo_cache()
    
    # 1. 识别新增品种
    cached_symbols = set(ipo_cache._memory_cache.keys())
    current_symbols = set(all_symbols)
    
    new_symbols = current_symbols - cached_symbols
    removed_symbols = cached_symbols - current_symbols
    
    # 2. 下载新增品种的IPO日期
    update_stats = {
        "new_added": 0,
        "removed": 0,
        "updated": 0,
        "failed": 0
    }
    
    if new_symbols:
        logger.info(f"发现{len(new_symbols)}个新品种，开始下载IPO日期")
        download_results = batch_download_ipo_dates(list(new_symbols))
        
        update_stats["new_added"] = download_results["succeeded"]
        update_stats["failed"] = download_results["failed"]
    
    # 3. 清理已删除的品种
    for symbol in removed_symbols:
        if symbol in ipo_cache._memory_cache:
            del ipo_cache._memory_cache[symbol]
            update_stats["removed"] += 1
    
    # 4. 保存更新后的缓存
    if update_stats["new_added"] > 0 or update_stats["removed"] > 0:
        ipo_cache.batch_save()
    
    return update_stats
```

### 6.3 未上市品种处理规则

#### 6.3.1 未上市品种识别

**识别标准**：
```python
def identify_unlisted_symbols(ipo_results: Dict[str, Any]) -> List[str]:
    """识别未上市品种"""
    
    unlisted_symbols = []
    
    for symbol, ipo_info in ipo_results.items():
        # 1. IPO日期为None（解析失败或无效值）
        if ipo_info.get("ipo_date") is None:
            raw_value = ipo_info.get("raw_ipo_date", 0)
            
            # 2. 原始值非零但无效（如70这种值）
            if raw_value != 0 and raw_value < 19900000:
                unlisted_symbols.append(symbol)
                logger.debug(f"品种{symbol}未上市（IPO日期={raw_value}）")
        
        # 3. IPO日期在未来（可能是预上市）
        elif ipo_info.get("ipo_date"):
            ipo_date = ipo_info["ipo_date"]
            current_date = get_real_date()
            
            if ipo_date > current_date:
                unlisted_symbols.append(symbol)
                logger.debug(f"品种{symbol}未上市（IPO日期={ipo_date}在未来）")
    
    return unlisted_symbols
```

#### 6.3.2 未上市品种记录

**记录文件格式**：
```python
def save_unlisted_symbols(unlisted_symbols: List[str], output_file: Path) -> bool:
    """保存未上市品种记录"""
    
    try:
        unlisted_data = {
            "_meta": {
                "generated_date": get_real_date().strftime("%Y-%m-%d"),
                "generated_time": datetime.now().isoformat(),
                "count": len(unlisted_symbols),
                "description": "未上市品种列表（IPO日期无效或在未来）"
            },
            "unlisted_symbols": unlisted_symbols
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(unlisted_data, f, ensure_ascii=False, indent=2)
        
        logger.info(f"未上市品种记录已保存: {len(unlisted_symbols)}个品种")
        return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
        
    except Exception as e:
        logger.error(f"保存未上市品种记录失败: {e}")
        return False
```

**品种过滤应用**：
```python
def filter_listed_symbols(all_symbols: List[str], unlisted_file: Path) -> List[str]:
    """过滤掉未上市品种"""
    
    # 1. 加载未上市品种列表
    unlisted_symbols = set()
    if unlisted_file.exists():
        try:
            with open(unlisted_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                unlisted_symbols = set(data.get("unlisted_symbols", []))
        except Exception as e:
            logger.warning(f"加载未上市品种列表失败: {e}")
    
    # 2. 过滤品种列表
    listed_symbols = [s for s in all_symbols if s not in unlisted_symbols]
    
    filtered_count = len(all_symbols) - len(listed_symbols)
    if filtered_count > 0:
        logger.info(f"已过滤{filtered_count}个未上市品种")
    
    return listed_symbols

---

## 七、数据质量管理业务规则

### 7.1 质量扫描策略

#### 7.1.1 混合异步扫描模式

**扫描模式选择规则**：
```python
def select_scan_mode(file_count: int, file_sizes: List[int]) -> Dict[str, Any]:
    """选择最优扫描模式"""
    
    # 计算文件统计信息
    total_size_mb = sum(file_sizes) / (1024 * 1024)
    avg_size_mb = total_size_mb / len(file_sizes) if file_sizes else 0
    large_files = len([s for s in file_sizes if s > 50 * 1024 * 1024])  # >50MB
    
    # 模式选择逻辑
    if file_count <= 100:
        # 小规模：协程模式
        return {
            "mode": "coroutine_only",
            "max_coroutines": min(file_count, 500),
            "use_threads": False,
            "use_processes": False
        }
    
    elif file_count <= 1000 and large_files < file_count * 0.1:
        # 中规模，小文件为主：协程+线程
        return {
            "mode": "coroutine_thread",
            "max_coroutines": 500,
            "max_threads": 50,
            "use_processes": False
        }
    
    else:
        # 大规模或大文件较多：混合模式
        return {
            "mode": "hybrid",
            "max_coroutines": 500,
            "max_threads": 50,
            "max_processes": min(16, max(4, cpu_count())),
            "process_threshold_mb": 50  # 超过50MB的文件用进程处理
        }
```

**任务分配规则**：
```python
def distribute_scan_tasks(files: List[Path], scan_config: Dict) -> Dict[str, List[Path]]:
    """分配扫描任务到不同执行器"""
    
    task_distribution = {
        "coroutine_tasks": [],
        "thread_tasks": [],
        "process_tasks": []
    }
    
    mode = scan_config["mode"]
    process_threshold = scan_config.get("process_threshold_mb", 50) * 1024 * 1024
    
    for file_path in files:
        try:
            file_size = file_path.stat().st_size
            
            if mode == "hybrid" and file_size > process_threshold:
                # 大文件用进程处理
                task_distribution["process_tasks"].append(file_path)
            elif mode in ["hybrid", "coroutine_thread"] and len(task_distribution["thread_tasks"]) < scan_config.get("max_threads", 50):
                # 中等文件用线程处理
                task_distribution["thread_tasks"].append(file_path)
            else:
                # 小文件用协程处理
                task_distribution["coroutine_tasks"].append(file_path)
                
        except OSError:
            # 文件访问异常，分配给协程处理
            task_distribution["coroutine_tasks"].append(file_path)
    
    return task_distribution
```

#### 7.1.2 增量扫描优化

**文件变更检测**：
```python
class IncrementalScanManager:
    """增量扫描管理器"""
    
    def __init__(self, scan_record_file: Path):
        self.scan_record_file = scan_record_file
        self._file_records: Dict[str, Dict] = {}
        self._load_scan_records()
    
    def should_scan_file(self, file_path: Path) -> bool:
        """判断文件是否需要扫描"""
        
        try:
            # 获取文件信息
            stat = file_path.stat()
            file_key = str(file_path)
            
            # 检查是否有扫描记录
            if file_key not in self._file_records:
                return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。  # 新文件，需要扫描
            
            record = self._file_records[file_key]
            
            # 检查文件是否有变更
            if (stat.st_mtime != record.get("mtime") or 
                stat.st_size != record.get("size")):
                return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。  # 文件已变更，需要重新扫描
            
            # 检查扫描记录是否过期（24小时）
            last_scan = record.get("last_scan", 0)
            if time.time() - last_scan > 86400:
                return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。  # 扫描记录过期
            
            return False  # 无需扫描
            
        except OSError:
            return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。  # 文件访问异常，需要扫描
    
    def mark_file_scanned(self, file_path: Path, scan_result: Dict) -> None:
        """标记文件已扫描"""
        
        try:
            stat = file_path.stat()
            file_key = str(file_path)
            
            self._file_records[file_key] = {
                "mtime": stat.st_mtime,
                "size": stat.st_size,
                "last_scan": time.time(),
                "scan_result": {
                    "has_errors": scan_result.get("has_errors", False),
                    "error_count": scan_result.get("error_count", 0),
                    "quality_score": scan_result.get("quality_score", 0)
                }
            }
            
        except OSError as e:
            logger.warning(f"标记文件扫描状态失败 {file_path}: {e}")
```

### 7.2 质量评分规则

#### 7.2.1 综合质量评分

**质量评分计算**：
```python
def calculate_quality_score(validation_result: ValidationResult) -> float:
    """计算数据质量综合评分"""
    
    # 基础分数
    base_score = 100.0
    
    # 1. 格式错误扣分（严重）
    format_errors = len([e for e in validation_result.errors if e.get("severity") == "error"])
    base_score -= format_errors * 20  # 每个格式错误扣20分
    
    # 2. 逻辑错误扣分（中等）
    logic_errors = len([e for e in validation_result.errors if e.get("type", "").startswith("logic")])
    base_score -= logic_errors * 10  # 每个逻辑错误扣10分
    
    # 3. 完整性评分（基于缺失比例）
    completeness_score = validation_result.completeness_score or 0
    completeness_weight = 0.3
    base_score = base_score * (1 - completeness_weight) + completeness_score * completeness_weight
    
    # 4. 新鲜度评分（基于数据滞后）
    freshness_score = validation_result.freshness_score or 0
    freshness_weight = 0.2
    base_score = base_score * (1 - freshness_weight) + freshness_score * freshness_weight
    
    # 5. 警告扣分（轻微）
    warning_count = len([e for e in validation_result.errors if e.get("severity") == "warning"])
    base_score -= warning_count * 2  # 每个警告扣2分
    
    # 确保分数在合理范围内
    return max(0.0, min(100.0, base_score))
```

**质量等级划分**：
```python
def get_quality_level(quality_score: float) -> Dict[str, Any]:
    """根据质量评分确定质量等级"""
    
    if quality_score >= 90:
        return {
            "level": "excellent",
            "description": "数据质量优秀",
            "color": "green",
            "action": "无需处理"
        }
    elif quality_score >= 75:
        return {
            "level": "good", 
            "description": "数据质量良好",
            "color": "blue",
            "action": "建议关注"
        }
    elif quality_score >= 60:
        return {
            "level": "fair",
            "description": "数据质量一般", 
            "color": "yellow",
            "action": "需要改进"
        }
    elif quality_score >= 40:
        return {
            "level": "poor",
            "description": "数据质量较差",
            "color": "orange", 
            "action": "需要修复"
        }
    else:
        return {
            "level": "critical",
            "description": "数据质量严重问题",
            "color": "red",
            "action": "紧急修复"
        }
```

#### 7.2.2 质量趋势分析

**质量历史记录**：
```python
class QualityTrendAnalyzer:
    """质量趋势分析器"""
    
    def __init__(self, history_file: Path):
        self.history_file = history_file
        self._quality_history: List[Dict] = []
        self._load_history()
    
    def record_quality_snapshot(self, overview: QualityOverview) -> None:
        """记录质量快照"""
        
        snapshot = {
            "timestamp": time.time(),
            "date": get_real_date().strftime("%Y-%m-%d"),
            "quality_score": overview.quality_score,
            "total_symbols": overview.total_symbols,
            "missing_symbols": overview.missing_symbols,
            "outdated_symbols": overview.outdated_symbols,
            "error_count": overview.error_count,
            "warning_count": overview.warning_count
        }
        
        self._quality_history.append(snapshot)
        
        # 保持最近30天的记录
        cutoff_time = time.time() - 30 * 86400
        self._quality_history = [
            h for h in self._quality_history 
            if h["timestamp"] > cutoff_time
        ]
        
        self._save_history()
    
    def analyze_trend(self, days: int = 7) -> Dict[str, Any]:
        """分析质量趋势"""
        
        if len(self._quality_history) < 2:
            return {"trend": "insufficient_data"}
        
        # 获取指定天数内的记录
        cutoff_time = time.time() - days * 86400
        recent_records = [
            h for h in self._quality_history 
            if h["timestamp"] > cutoff_time
        ]
        
        if len(recent_records) < 2:
            return {"trend": "insufficient_data"}
        
        # 计算趋势
        scores = [r["quality_score"] for r in recent_records]
        first_score = scores[0]
        last_score = scores[-1]
        avg_score = sum(scores) / len(scores)
        
        score_change = last_score - first_score
        
        if score_change > 5:
            trend = "improving"
        elif score_change < -5:
            trend = "declining"
        else:
            trend = "stable"
        
        return {
            "trend": trend,
            "score_change": score_change,
            "current_score": last_score,
            "average_score": avg_score,
            "sample_count": len(recent_records),
            "analysis_period": days
        }
```

### 7.3 质量问题处理规则

#### 7.3.1 自动修复规则

**可自动修复的问题类型**：
```python
def auto_fix_quality_issues(symbol: str, interval: str, issues: List[Dict]) -> Dict[str, Any]:
    """自动修复质量问题"""
    
    fix_results = {
        "fixed_count": 0,
        "failed_count": 0,
        "actions_taken": []
    }
    
    for issue in issues:
        issue_type = issue.get("type")
        
        if issue_type == "missing_recent_data":
            # 自动触发增量下载
            try:
                trigger_incremental_download(symbol, interval)
                fix_results["fixed_count"] += 1
                fix_results["actions_taken"].append(f"触发{symbol}增量下载")
            except Exception as e:
                fix_results["failed_count"] += 1
                logger.error(f"自动修复失败 {symbol}: {e}")
        
        elif issue_type == "corrupted_file":
            # 自动重新下载
            try:
                trigger_full_redownload(symbol, interval)
                fix_results["fixed_count"] += 1
                fix_results["actions_taken"].append(f"重新下载{symbol}数据")
            except Exception as e:
                fix_results["failed_count"] += 1
                logger.error(f"自动修复失败 {symbol}: {e}")
        
        elif issue_type == "duplicate_records":
            # 自动去重
            try:
                deduplicate_data_file(symbol, interval)
                fix_results["fixed_count"] += 1
                fix_results["actions_taken"].append(f"去重{symbol}数据")
            except Exception as e:
                fix_results["failed_count"] += 1
                logger.error(f"自动修复失败 {symbol}: {e}")
    
    return fix_results
```

#### 7.3.2 质量告警规则

**告警触发条件**：
```python
def check_quality_alerts(overview: QualityOverview) -> List[Dict]:
    """检查质量告警条件"""
    
    alerts = []
    
    # 1. 整体质量评分告警
    if overview.quality_score < 60:
        alerts.append({
            "level": "warning" if overview.quality_score >= 40 else "critical",
            "type": "low_quality_score",
            "message": f"整体质量评分过低: {overview.quality_score:.1f}分",
            "threshold": 60,
            "current_value": overview.quality_score
        })
    
    # 2. 缺失品种比例告警
    missing_ratio = overview.missing_symbols / overview.total_symbols if overview.total_symbols > 0 else 0
    if missing_ratio > 0.1:  # 超过10%
        alerts.append({
            "level": "warning" if missing_ratio < 0.2 else "critical",
            "type": "high_missing_ratio",
            "message": f"缺失品种比例过高: {missing_ratio:.1%}",
            "threshold": 0.1,
            "current_value": missing_ratio
        })
    
    # 3. 过时数据比例告警
    outdated_ratio = overview.outdated_symbols / overview.total_symbols if overview.total_symbols > 0 else 0
    if outdated_ratio > 0.15:  # 超过15%
        alerts.append({
            "level": "warning" if outdated_ratio < 0.3 else "critical", 
            "type": "high_outdated_ratio",
            "message": f"过时数据比例过高: {outdated_ratio:.1%}",
            "threshold": 0.15,
            "current_value": outdated_ratio
        })
    
    # 4. 错误数量告警
    if overview.error_count > 100:
        alerts.append({
            "level": "warning" if overview.error_count < 500 else "critical",
            "type": "high_error_count", 
            "message": f"数据错误数量过多: {overview.error_count}个",
            "threshold": 100,
            "current_value": overview.error_count
        })
    
    return alerts

---

## 八、统一数据查询业务规则

### 8.1 四层数据融合查询

#### 8.1.1 查询优先级规则

**查询层级定义**：
```python
class UnifiedDataQueryEngine:
    """统一数据查询引擎"""
    
    QUERY_LAYERS = [
        "preload_cache",    # Layer 1: 预加载缓存（内存）
        "storage_files",    # Layer 2: 历史Parquet文件（磁盘）
        "recorded_data",    # Layer 3: 录制数据（如启用）
        "realtime_push"     # Layer 4: 实时推送（如已订阅）
    ]
    
    async def query_unified_async(self, symbol: str, interval: str, 
                                start_date: str, end_date: str,
                                check_gaps: bool = True) -> Optional[pd.DataFrame]:
        """异步统一查询（四层融合）"""
        
        query_context = {
            "symbol": symbol,
            "interval": interval,
            "start_date": start_date,
            "end_date": end_date,
            "query_time": time.time()
        }
        
        # Layer 1: 预加载缓存查询
        df = await self._query_preload_cache(query_context)
        if df is not None:
            logger.debug(f"命中预加载缓存: {symbol}_{interval}")
            return self._filter_by_date_range(df, start_date, end_date)
        
        # Layer 2: 历史Parquet文件查询
        df = await self._query_storage_files(query_context)
        if df is not None:
            logger.debug(f"命中存储文件: {symbol}_{interval}")
            # 更新预加载缓存
            await self._update_preload_cache(symbol, interval, df)
            return self._filter_by_date_range(df, start_date, end_date)
        
        # Layer 3: 录制数据查询（如启用）
        if self._is_recording_enabled():
            df = await self._query_recorded_data(query_context)
            if df is not None:
                logger.debug(f"命中录制数据: {symbol}_{interval}")
                return self._filter_by_date_range(df, start_date, end_date)
        
        # Layer 4: 实时推送查询（如已订阅）
        if self._is_subscribed(symbol):
            df = await self._query_realtime_data(query_context)
            if df is not None:
                logger.debug(f"命中实时数据: {symbol}_{interval}")
                return self._filter_by_date_range(df, start_date, end_date)
        
        # 所有层级都未命中
        if check_gaps:
            await self._handle_missing_data(query_context)
        
        return None
```

#### 8.1.2 缓存更新策略

**预加载缓存更新规则**：
```python
async def _update_preload_cache(self, symbol: str, interval: str, df: pd.DataFrame) -> bool:
    """更新预加载缓存"""
    
    # 1. 检查是否应该缓存
    if not self._should_cache_symbol(symbol):
        return False
    
    # 2. 数据质量检查
    if df.empty or len(df) < 10:
        logger.debug(f"数据质量不足，跳过缓存: {symbol}_{interval}")
        return False
    
    # 3. 数据截取（控制内存使用）
    cache_limit = self._get_cache_limit(interval)
    if len(df) > cache_limit:
        df = df.tail(cache_limit)  # 保留最新的数据
    
    # 4. 更新缓存
    cache_key = f"{symbol}_{interval}"
    self.preload_service.add_to_cache(symbol, interval, df.copy())
    
    # 5. 记录缓存统计
    self._record_cache_update(symbol, interval, len(df))
    
    return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。

def _get_cache_limit(self, interval: str) -> int:
    """获取不同周期的缓存限制"""
    limits = {
        "1m": 1440,   # 1分钟：1天数据
        "5m": 2016,   # 5分钟：7天数据  
        "15m": 1344,  # 15分钟：14天数据
        "30m": 1488,  # 30分钟：31天数据
        "1h": 1488,   # 1小时：62天数据
        "1d": 1000    # 日线：1000天数据
    }
    return limits.get(interval, 1000)
```

#### 8.1.3 数据缺失处理

**自动补全规则**：
```python
async def _handle_missing_data(self, query_context: Dict) -> None:
    """处理数据缺失"""
    
    symbol = query_context["symbol"]
    interval = query_context["interval"]
    start_date = query_context["start_date"]
    end_date = query_context["end_date"]
    
    # 1. 检查是否允许自动下载
    if not self._is_auto_download_enabled():
        logger.debug(f"自动下载已禁用，跳过补全: {symbol}_{interval}")
        return
    
    # 2. 检查下载频率限制
    if self._is_download_rate_limited(symbol):
        logger.debug(f"下载频率受限，跳过补全: {symbol}_{interval}")
        return
    
    # 3. 触发异步下载任务
    download_task = {
        "type": "gap_fill",
        "symbol": symbol,
        "interval": interval,
        "start_date": start_date,
        "end_date": end_date,
        "priority": "normal",
        "requester": "unified_query"
    }
    
    await self._submit_download_task(download_task)
    
    # 4. 记录缺失数据请求
    self._record_missing_data_request(symbol, interval, start_date, end_date)

def _is_download_rate_limited(self, symbol: str) -> bool:
    """检查下载频率限制"""
    
    # 获取该品种的最近下载记录
    last_download = self._get_last_download_time(symbol)
    if last_download is None:
        return False
    
    # 限制：同一品种5分钟内只能触发一次自动下载
    min_interval = 300  # 5分钟
    return (time.time() - last_download) < min_interval
```

### 8.2 数据订阅管理

#### 8.2.1 订阅生命周期

**订阅注册规则**：
```python
class SubscriptionManager:
    """数据订阅管理器"""
    
    def __init__(self):
        self._subscriptions: Dict[str, SubscriptionInfo] = {}
        self._subscription_lock = threading.RLock()
    
    async def subscribe_async(self, module: str, symbols: List[str], 
                            intervals: List[str] = None) -> bool:
        """异步订阅数据"""
        
        intervals = intervals or ["1d"]  # 默认订阅日线
        
        with self._subscription_lock:
            # 1. 创建订阅信息
            subscription = SubscriptionInfo(
                module=module,
                symbols=symbols,
                intervals=intervals,
                created_at=time.time(),
                last_update=time.time(),
                status="active"
            )
            
            # 2. 检查订阅冲突
            existing_sub = self._subscriptions.get(module)
            if existing_sub and existing_sub.status == "active":
                logger.warning(f"模块{module}已有活跃订阅，将被覆盖")
            
            # 3. 注册订阅
            self._subscriptions[module] = subscription
            
            # 4. 启动数据源（如需要）
            await self._start_data_sources(symbols, intervals)
            
            # 5. 跨进程同步订阅信息
            await self._sync_subscriptions_cross_process()
            
            # 6. 发布订阅事件
            self._publish_subscription_event("added", module, symbols, intervals)
            
            logger.info(f"订阅成功: 模块={module}, 品种数={len(symbols)}, 周期={intervals}")
            return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。

@dataclass
class SubscriptionInfo:
    """订阅信息"""
    module: str
    symbols: List[str]
    intervals: List[str]
    created_at: float

---

## 九、实时推送业务规则

### 9.1 TDX数据源规则

#### 9.1.1 轮询转推送机制

**轮询策略配置**：
```python
class TdxDataSource:
    """TDX数据源（轮询转推送）"""
    
    def __init__(self, gateway_name: str):
        self.gateway_name = gateway_name
        self._polling_config = {
            "interval_seconds": 3,      # 轮询间隔3秒
            "batch_size": 50,          # 每批查询50个品种
            "timeout_seconds": 5,       # 单次查询超时5秒
            "max_retries": 3,          # 最大重试3次
            "error_cooldown": 10       # 错误后冷却10秒
        }
        
        self._subscribed_symbols: Set[str] = set()
        self._last_data: Dict[str, TickData] = {}
        self._polling_task: Optional[asyncio.Task] = None
        self._is_running = False
    
    async def start_polling(self) -> bool:
        """启动轮询"""
        
        if self._is_running:
            logger.warning("TDX数据源已在运行")
            return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
        
        try:
            # 1. 初始化TDX连接
            self.tdx_api = AsyncTdxHq_API()
            await self.tdx_api.connect()
            
            # 2. 启动轮询任务
            self._polling_task = asyncio.create_task(self._polling_loop())
            self._is_running = True
            
            logger.info(f"TDX数据源已启动: 轮询间隔{self._polling_config['interval_seconds']}秒")
            return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
            
        except Exception as e:
            logger.error(f"启动TDX数据源失败: {e}")
            return False
    
    async def _polling_loop(self) -> None:
        """轮询主循环"""
        
        consecutive_errors = 0
        
        while self._is_running:
            try:
                # 1. 检查是否有订阅
                if not self._subscribed_symbols:
                    await asyncio.sleep(1.0)
                    continue
                
                # 2. 分批查询数据
                symbols_list = list(self._subscribed_symbols)
                batch_size = self._polling_config["batch_size"]
                
                for i in range(0, len(symbols_list), batch_size):
                    batch_symbols = symbols_list[i:i + batch_size]
                    await self._query_and_push_batch(batch_symbols)
                
                # 3. 重置错误计数
                consecutive_errors = 0
                
                # 4. 等待下次轮询
                await asyncio.sleep(self._polling_config["interval_seconds"])
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"TDX轮询异常 (连续{consecutive_errors}次): {e}")
                
                # 错误冷却
                cooldown = min(60, self._polling_config["error_cooldown"] * consecutive_errors)
                await asyncio.sleep(cooldown)
```

**数据变化检测**：
```python
async def _query_and_push_batch(self, symbols: List[str]) -> None:
    """查询并推送批次数据"""
    
    try:
        # 1. 批量查询实时数据
        quotes = await self.tdx_api.get_security_quotes(symbols)
        
        # 2. 处理每个品种的数据
        for quote in quotes:
            symbol = quote.get("code")
            if not symbol or symbol not in self._subscribed_symbols:
                continue
            
            # 3. 转换为TickData格式
            tick_data = self._convert_to_tick_data(quote)
            
            # 4. 检查数据是否有变化
            if self._has_data_changed(symbol, tick_data):
                # 5. 推送数据变化
                await self._push_tick_data(symbol, tick_data)
                
                # 6. 更新最后数据
                self._last_data[symbol] = tick_data
                
    except Exception as e:
        logger.error(f"查询推送批次数据失败: {e}")

def _has_data_changed(self, symbol: str, new_tick: TickData) -> bool:
    """检查数据是否有变化"""
    
    last_tick = self._last_data.get(symbol)
    if last_tick is None:
        return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。  # 首次数据，认为有变化
    
    # 检查关键字段是否变化
    key_fields = ["last_price", "volume", "turnover", "datetime"]
    
    for field in key_fields:
        if getattr(new_tick, field) != getattr(last_tick, field):
            return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
    
    return False
```

#### 9.1.2 VNPy Gateway集成

**Gateway标准实现**：
```python
class TdxPollingGateway(BaseGateway):
    """TDX轮询网关（符合VNPy Gateway标准）"""
    
    default_name = "TDX_POLLING"
    
    exchanges = [Exchange.SSE, Exchange.SZSE, Exchange.BSE]  # 支持的交易所
    
    def __init__(self, event_engine: EventEngine, gateway_name: str):
        super().__init__(event_engine, gateway_name)
        
        self.tdx_source = TdxDataSource(gateway_name)
        self._contract_map: Dict[str, ContractData] = {}
    
    def connect(self, setting: dict) -> None:
        """连接网关"""
        
        # 1. 解析配置
        polling_interval = setting.get("轮询间隔（秒）", 3)
        symbols_str = setting.get("品种列表", "")
        
        # 2. 解析品种列表
        symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]
        
        # 3. 配置TDX数据源
        self.tdx_source._polling_config["interval_seconds"] = polling_interval
        
        # 4. 启动连接
        asyncio.create_task(self._async_connect(symbols))
    
    async def _async_connect(self, symbols: List[str]) -> None:
        """异步连接"""
        
        try:
            # 1. 启动TDX数据源
            success = await self.tdx_source.start_polling()
            if not success:
                self.write_log("TDX数据源启动失败")
                return
            
            # 2. 订阅品种
            for symbol in symbols:
                await self.tdx_source.subscribe(symbol)
            
            # 3. 设置数据回调
            self.tdx_source.set_tick_callback(self._on_tick_data)
            
            self.write_log(f"TDX轮询网关连接成功，订阅{len(symbols)}个品种")
            
        except Exception as e:
            self.write_log(f"TDX轮询网关连接失败: {e}")
    
    def _on_tick_data(self, tick_data: TickData) -> None:
        """处理Tick数据回调"""
        
        # 1. 转换为VNPy标准格式
        vnpy_tick = TickData(
            symbol=tick_data.symbol,
            exchange=self._get_exchange_by_symbol(tick_data.symbol),
            datetime=tick_data.datetime,
            name=self._get_symbol_name(tick_data.symbol),
            last_price=tick_data.last_price,
            volume=tick_data.volume,
            turnover=tick_data.turnover,
            gateway_name=self.gateway_name
        )
        
        # 2. 推送到事件引擎
        self.on_tick(vnpy_tick)
```

### 9.2 虚拟数据源规则

#### 9.2.1 历史数据回放

**回放控制规则**：
```python
class VirtualDataSource:
    """虚拟数据源（历史数据回放）"""
    
    def __init__(self, gateway_name: str):
        self.gateway_name = gateway_name
        self._replay_config = {
            "start_time": None,         # 回放起始时间
            "end_time": None,          # 回放结束时间
            "speed_multiplier": 1.0,    # 回放速度倍数
            "interval_ms": 1000,       # 基础间隔1秒
            "auto_loop": False         # 是否自动循环
        }
        
        self._replay_state = {
            "status": "stopped",       # stopped, playing, paused
            "current_time": None,      # 当前回放时间
            "progress": 0.0,          # 回放进度 0-1
            "data_buffer": [],        # 数据缓冲区
            "buffer_index": 0         # 缓冲区索引
        }
        
        self._replay_task: Optional[asyncio.Task] = None
    
    async def start_replay(self, start_time: str, end_time: str, 
                          symbols: List[str], speed: float = 1.0) -> bool:
        """启动历史数据回放"""
        
        try:
            # 1. 解析时间参数
            start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
            
            # 2. 加载历史数据
            await self._load_replay_data(symbols, start_dt, end_dt)
            
            # 3. 配置回放参数
            self._replay_config.update({
                "start_time": start_dt,
                "end_time": end_dt,
                "speed_multiplier": speed
            })
            
            # 4. 启动回放任务
            self._replay_task = asyncio.create_task(self._replay_loop())
            self._replay_state["status"] = "playing"
            
            logger.info(f"虚拟数据源回放已启动: {start_time} -> {end_time}, 速度{speed}x")
            return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
            
        except Exception as e:
            logger.error(f"启动虚拟数据源回放失败: {e}")
            return False
    
    async def _replay_loop(self) -> None:
        """回放主循环"""
        
        while (self._replay_state["status"] == "playing" and 
               self._replay_state["buffer_index"] < len(self._replay_state["data_buffer"])):
            
            try:
                # 1. 获取当前数据
                current_data = self._replay_state["data_buffer"][self._replay_state["buffer_index"]]
                
                # 2. 推送数据
                await self._push_replay_data(current_data)
                
                # 3. 更新状态
                self._replay_state["buffer_index"] += 1
                self._update_replay_progress()
                
                # 4. 计算等待时间
                wait_time = self._calculate_wait_time(current_data)
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"回放循环异常: {e}")
                break
        
        # 回放结束处理
        if self._replay_config["auto_loop"]:
            await self._restart_replay()
        else:
            self._replay_state["status"] = "stopped"
            logger.info("虚拟数据源回放已结束")
```

**回放速度控制**：
```python
def _calculate_wait_time(self, current_data: Dict) -> float:
    """计算等待时间"""
    
    # 1. 获取基础间隔
    base_interval = self._replay_config["interval_ms"] / 1000.0
    
    # 2. 应用速度倍数
    speed = self._replay_config["speed_multiplier"]
    actual_interval = base_interval / speed
    
    # 3. 考虑数据时间间隔
    if self._replay_state["buffer_index"] > 0:
        prev_data = self._replay_state["data_buffer"][self._replay_state["buffer_index"] - 1]
        time_diff = (current_data["datetime"] - prev_data["datetime"]).total_seconds()
        
        # 使用实际时间间隔（但不超过最大间隔）
        actual_interval = min(actual_interval, time_diff / speed)
    
    # 4. 确保最小间隔
    return max(0.01, actual_interval)  # 最小10ms

async def pause_replay(self) -> None:
    """暂停回放"""
    if self._replay_state["status"] == "playing":
        self._replay_state["status"] = "paused"
        logger.info("虚拟数据源回放已暂停")

async def resume_replay(self) -> None:
    """恢复回放"""
    if self._replay_state["status"] == "paused":
        self._replay_state["status"] = "playing"
        logger.info("虚拟数据源回放已恢复")

async def set_replay_speed(self, speed: float) -> None:
    """设置回放速度"""
    self._replay_config["speed_multiplier"] = max(0.1, min(10.0, speed))
    logger.info(f"回放速度已设置为: {speed}x")
```

### 9.3 数据推送规则

#### 9.3.1 推送频率控制

**推送节流规则**：
```python
class DataPushThrottler:
    """数据推送节流器"""
    
    def __init__(self):
        self._push_limits = {
            "tick": 100,      # Tick数据：最多100次/秒
            "bar": 10,        # Bar数据：最多10次/秒
            "order": 50,      # 订单数据：最多50次/秒
            "trade": 50       # 成交数据：最多50次/秒
        }
        
        self._push_counters: Dict[str, Dict] = {}
        self._last_reset_time = time.time()
    
    def can_push(self, data_type: str, symbol: str = None) -> bool:
        """检查是否可以推送"""
        
        current_time = time.time()
        
        # 1. 每秒重置计数器
        if current_time - self._last_reset_time >= 1.0:
            self._reset_counters()
            self._last_reset_time = current_time
        
        # 2. 检查推送限制
        limit = self._push_limits.get(data_type, 10)
        counter_key = f"{data_type}_{symbol}" if symbol else data_type
        
        current_count = self._push_counters.get(counter_key, 0)
        
        if current_count >= limit:
            return False
        
        # 3. 增加计数
        self._push_counters[counter_key] = current_count + 1
        return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
    
    def _reset_counters(self) -> None:
        """重置推送计数器"""
        self._push_counters.clear()
```

#### 9.3.2 推送质量保证

**数据完整性检查**：
```python
async def _push_tick_data(self, symbol: str, tick_data: TickData) -> None:
    """推送Tick数据（带质量检查）"""
    
    # 1. 数据完整性检查
    if not self._validate_tick_data(tick_data):
        logger.warning(f"Tick数据验证失败，跳过推送: {symbol}")
        return
    
    # 2. 推送频率检查
    if not self.push_throttler.can_push("tick", symbol):
        logger.debug(f"推送频率超限，跳过: {symbol}")
        return
    
    # 3. 数据去重检查
    if self._is_duplicate_tick(symbol, tick_data):
        logger.debug(f"重复Tick数据，跳过推送: {symbol}")
        return
    
    # 4. 推送数据
    try:
        event = Event(EVENT_TICK, tick_data)
        self.event_engine.put(event)
        
        # 5. 记录推送统计
        self._record_push_stats(symbol, "tick", True)
        
    except Exception as e:
        logger.error(f"推送Tick数据失败 {symbol}: {e}")
        self._record_push_stats(symbol, "tick", False)

def _validate_tick_data(self, tick_data: TickData) -> bool:
    """验证Tick数据完整性"""
    
    # 1. 必需字段检查
    required_fields = ["symbol", "datetime", "last_price"]
    for field in required_fields:
        if not hasattr(tick_data, field) or getattr(tick_data, field) is None:
            return False
    
    # 2. 数据合理性检查
    if tick_data.last_price <= 0:
        return False
    
    if hasattr(tick_data, "volume") and tick_data.volume < 0:
        return False
    
    # 3. 时间合理性检查
    current_time = datetime.now()
    if tick_data.datetime > current_time + timedelta(minutes=5):
        return False  # 未来时间超过5分钟
    
    return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
```
    last_update: float
    status: str  # active, paused, cancelled
    data_source: Optional[str] = None
    push_count: int = 0
    last_push: Optional[float] = None
```

**订阅清理规则**：
```python
async def cleanup_expired_subscriptions(self) -> int:
    """清理过期订阅"""
    
    cleaned_count = 0
    current_time = time.time()
    
    with self._subscription_lock:
        expired_modules = []
        
        for module, subscription in self._subscriptions.items():
            # 1. 检查订阅是否过期（24小时无更新）
            if (current_time - subscription.last_update) > 86400:
                expired_modules.append(module)
                continue
            
            # 2. 检查模块是否仍然存在
            if not self._is_module_active(module):
                expired_modules.append(module)
                continue
        
        # 3. 清理过期订阅
        for module in expired_modules:
            await self.unsubscribe_async(module)
            cleaned_count += 1
    
    if cleaned_count > 0:
        logger.info(f"清理了{cleaned_count}个过期订阅")
    
    return cleaned_count
```

#### 8.2.2 跨进程订阅同步

**订阅同步规则**：
```python
async def _sync_subscriptions_cross_process(self) -> None:
    """跨进程同步订阅信息"""
    
    try:
        # 1. 准备同步数据
        sync_data = {
            "action": "sync_subscriptions",
            "subscriptions": {},
            "timestamp": time.time()
        }
        
        # 2. 序列化订阅信息
        for module, subscription in self._subscriptions.items():
            sync_data["subscriptions"][module] = {
                "symbols": subscription.symbols,
                "intervals": subscription.intervals,
                "status": subscription.status,
                "last_update": subscription.last_update
            }
        
        # 3. 通过native_ipc发送同步消息
        from backend.infrastructure.native_ipc import AsyncIPCPipe
        
        async with AsyncIPCPipe.server("subscription_sync") as pipe:
            message = json.dumps(sync_data).encode()
            await pipe.write(message)
        
        logger.debug(f"订阅信息已同步到子进程: {len(sync_data['subscriptions'])}个订阅")
        
    except Exception as e:
        logger.error(f"跨进程订阅同步失败: {e}")

async def receive_subscription_sync(self) -> None:
    """接收订阅同步（子进程）"""
    
    try:
        from backend.infrastructure.native_ipc import AsyncIPCPipe
        
        async with AsyncIPCPipe.client("subscription_sync") as pipe:
            data = await pipe.read()
            sync_data = json.loads(data.decode())
            
            if sync_data.get("action") == "sync_subscriptions":
                # 更新本地订阅信息
                self._update_local_subscriptions(sync_data["subscriptions"])
                logger.debug("已接收订阅同步更新")
                
    except Exception as e:
        logger.error(f"接收订阅同步失败: {e}")
```

### 8.3 智能预加载规则

#### 8.3.1 预加载触发条件

**预加载策略**：
```python
class IntelligentPreloader:
    """智能预加载器"""
    
    def __init__(self):
        self._access_history: Dict[str, AccessStats] = {}
        self._preload_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._preload_worker_running = False
    
    def record_access(self, symbol: str, interval: str) -> None:
        """记录数据访问"""
        
        access_key = f"{symbol}_{interval}"
        current_time = time.time()
        
        if access_key not in self._access_history:
            self._access_history[access_key] = AccessStats(
                symbol=symbol,
                interval=interval,
                access_count=0,
                last_access=0,
                first_access=current_time
            )
        
        stats = self._access_history[access_key]
        stats.access_count += 1
        stats.last_access = current_time
        
        # 触发预加载检查
        if self._should_trigger_preload(stats):
            asyncio.create_task(self._schedule_preload(symbol, interval))
    
    def _should_trigger_preload(self, stats: AccessStats) -> bool:
        """判断是否应该触发预加载"""
        
        # 1. 访问频率检查（最近1小时内访问3次以上）
        recent_threshold = time.time() - 3600  # 1小时
        if stats.access_count >= 3 and stats.last_access > recent_threshold:
            return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
        
        # 2. 热门品种检查（总访问次数超过10次）
        if stats.access_count >= 10:
            return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
        
        # 3. 连续访问检查（5分钟内访问2次）
        if stats.access_count >= 2:
            time_span = stats.last_access - stats.first_access
            if time_span < 300:  # 5分钟
                return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
        
        return False

@dataclass
class AccessStats:
    """访问统计"""
    symbol: str
    interval: str
    access_count: int
    last_access: float
    first_access: float
```

#### 8.3.2 预加载执行规则

**预加载任务调度**：
```python
async def _schedule_preload(self, symbol: str, interval: str) -> None:
    """调度预加载任务"""
    
    # 1. 检查是否已在预加载队列中
    if self._is_in_preload_queue(symbol, interval):
        return
    
    # 2. 检查缓存是否已存在
    if self.preload_service.is_cached(symbol, interval):
        return
    
    # 3. 创建预加载任务
    preload_task = PreloadTask(
        symbol=symbol,
        interval=interval,
        priority=self._calculate_preload_priority(symbol, interval),
        created_at=time.time()
    )
    
    # 4. 添加到预加载队列
    try:
        await self._preload_queue.put(preload_task)
        logger.debug(f"预加载任务已调度: {symbol}_{interval}")
    except asyncio.QueueFull:
        logger.warning(f"预加载队列已满，跳过: {symbol}_{interval}")

async def _preload_worker(self) -> None:
    """预加载工作协程"""
    
    while self._preload_worker_running:
        try:
            # 1. 获取预加载任务（带超时）
            task = await asyncio.wait_for(
                self._preload_queue.get(), 
                timeout=10.0
            )
            
            # 2. 执行预加载
            success = await self._execute_preload(task)
            
            # 3. 标记任务完成
            self._preload_queue.task_done()
            
            if success:
                logger.debug(f"预加载完成: {task.symbol}_{task.interval}")
            else:
                logger.warning(f"预加载失败: {task.symbol}_{task.interval}")
            
            # 4. 控制预加载频率
            await asyncio.sleep(0.1)  # 100ms间隔
            
        except asyncio.TimeoutError:
            # 队列空闲，继续等待
            continue
        except Exception as e:
            logger.error(f"预加载工作协程异常: {e}")
            await asyncio.sleep(1.0)  # 异常后等待1秒

@dataclass
class PreloadTask:
    """预加载任务"""
    symbol: str
    interval: str
    priority: int
    created_at: float

---

## 九、实时推送业务规则

### 9.1 TDX数据源规则

#### 9.1.1 轮询转推送机制

**轮询策略配置**：
```python
class TdxDataSource:
    """TDX数据源（轮询转推送）"""
    
    def __init__(self, gateway_name: str):
        self.gateway_name = gateway_name
        self._polling_config = {
            "interval_seconds": 3,      # 轮询间隔3秒
            "batch_size": 50,          # 每批查询50个品种
            "timeout_seconds": 5,       # 单次查询超时5秒
            "max_retries": 3,          # 最大重试3次
            "error_cooldown": 10       # 错误后冷却10秒
        }
        
        self._subscribed_symbols: Set[str] = set()
        self._last_data: Dict[str, TickData] = {}
        self._polling_task: Optional[asyncio.Task] = None
        self._is_running = False
    
    async def start_polling(self) -> bool:
        """启动轮询"""
        
        if self._is_running:
            logger.warning("TDX数据源已在运行")
            return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
        
        try:
            # 1. 初始化TDX连接
            self.tdx_api = AsyncTdxHq_API()
            await self.tdx_api.connect()
            
            # 2. 启动轮询任务
            self._polling_task = asyncio.create_task(self._polling_loop())
            self._is_running = True
            
            logger.info(f"TDX数据源已启动: 轮询间隔{self._polling_config['interval_seconds']}秒")
            return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
            
        except Exception as e:
            logger.error(f"启动TDX数据源失败: {e}")
            return False
    
    async def _polling_loop(self) -> None:
        """轮询主循环"""
        
        consecutive_errors = 0
        
        while self._is_running:
            try:
                # 1. 检查是否有订阅
                if not self._subscribed_symbols:
                    await asyncio.sleep(1.0)
                    continue
                
                # 2. 分批查询数据
                symbols_list = list(self._subscribed_symbols)
                batch_size = self._polling_config["batch_size"]
                
                for i in range(0, len(symbols_list), batch_size):
                    batch_symbols = symbols_list[i:i + batch_size]
                    await self._query_and_push_batch(batch_symbols)
                
                # 3. 重置错误计数
                consecutive_errors = 0
                
                # 4. 等待下次轮询
                await asyncio.sleep(self._polling_config["interval_seconds"])
                
            except Exception as e:
                consecutive_errors += 1
                logger.error(f"TDX轮询异常 (连续{consecutive_errors}次): {e}")
                
                # 错误冷却
                cooldown = min(60, self._polling_config["error_cooldown"] * consecutive_errors)
                await asyncio.sleep(cooldown)
```

**数据变化检测**：
```python
async def _query_and_push_batch(self, symbols: List[str]) -> None:
    """查询并推送批次数据"""
    
    try:
        # 1. 批量查询实时数据
        quotes = await self.tdx_api.get_security_quotes(symbols)
        
        # 2. 处理每个品种的数据
        for quote in quotes:
            symbol = quote.get("code")
            if not symbol or symbol not in self._subscribed_symbols:
                continue
            
            # 3. 转换为TickData格式
            tick_data = self._convert_to_tick_data(quote)
            
            # 4. 检查数据是否有变化
            if self._has_data_changed(symbol, tick_data):
                # 5. 推送数据变化
                await self._push_tick_data(symbol, tick_data)
                
                # 6. 更新最后数据
                self._last_data[symbol] = tick_data
                
    except Exception as e:
        logger.error(f"查询推送批次数据失败: {e}")

def _has_data_changed(self, symbol: str, new_tick: TickData) -> bool:
    """检查数据是否有变化"""
    
    last_tick = self._last_data.get(symbol)
    if last_tick is None:
        return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。  # 首次数据，认为有变化
    
    # 检查关键字段是否变化
    key_fields = ["last_price", "volume", "turnover", "datetime"]
    
    for field in key_fields:
        if getattr(new_tick, field) != getattr(last_tick, field):
            return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
    
    return False
```

#### 9.1.2 VNPy Gateway集成

**Gateway标准实现**：
```python
class TdxPollingGateway(BaseGateway):
    """TDX轮询网关（符合VNPy Gateway标准）"""
    
    default_name = "TDX_POLLING"
    
    exchanges = [Exchange.SSE, Exchange.SZSE, Exchange.BSE]  # 支持的交易所
    
    def __init__(self, event_engine: EventEngine, gateway_name: str):
        super().__init__(event_engine, gateway_name)
        
        self.tdx_source = TdxDataSource(gateway_name)
        self._contract_map: Dict[str, ContractData] = {}
    
    def connect(self, setting: dict) -> None:
        """连接网关"""
        
        # 1. 解析配置
        polling_interval = setting.get("轮询间隔（秒）", 3)
        symbols_str = setting.get("品种列表", "")
        
        # 2. 解析品种列表
        symbols = [s.strip() for s in symbols_str.split(",") if s.strip()]
        
        # 3. 配置TDX数据源
        self.tdx_source._polling_config["interval_seconds"] = polling_interval
        
        # 4. 启动连接
        asyncio.create_task(self._async_connect(symbols))
    
    async def _async_connect(self, symbols: List[str]) -> None:
        """异步连接"""
        
        try:
            # 1. 启动TDX数据源
            success = await self.tdx_source.start_polling()
            if not success:
                self.write_log("TDX数据源启动失败")
                return
            
            # 2. 订阅品种
            for symbol in symbols:
                await self.tdx_source.subscribe(symbol)
            
            # 3. 设置数据回调
            self.tdx_source.set_tick_callback(self._on_tick_data)
            
            self.write_log(f"TDX轮询网关连接成功，订阅{len(symbols)}个品种")
            
        except Exception as e:
            self.write_log(f"TDX轮询网关连接失败: {e}")
    
    def _on_tick_data(self, tick_data: TickData) -> None:
        """处理Tick数据回调"""
        
        # 1. 转换为VNPy标准格式
        vnpy_tick = TickData(
            symbol=tick_data.symbol,
            exchange=self._get_exchange_by_symbol(tick_data.symbol),
            datetime=tick_data.datetime,
            name=self._get_symbol_name(tick_data.symbol),
            last_price=tick_data.last_price,
            volume=tick_data.volume,
            turnover=tick_data.turnover,
            gateway_name=self.gateway_name
        )
        
        # 2. 推送到事件引擎
        self.on_tick(vnpy_tick)
```

### 9.2 虚拟数据源规则

#### 9.2.1 历史数据回放

**回放控制规则**：
```python
class VirtualDataSource:
    """虚拟数据源（历史数据回放）"""
    
    def __init__(self, gateway_name: str):
        self.gateway_name = gateway_name
        self._replay_config = {
            "start_time": None,         # 回放起始时间
            "end_time": None,          # 回放结束时间
            "speed_multiplier": 1.0,    # 回放速度倍数
            "interval_ms": 1000,       # 基础间隔1秒
            "auto_loop": False         # 是否自动循环
        }
        
        self._replay_state = {
            "status": "stopped",       # stopped, playing, paused
            "current_time": None,      # 当前回放时间
            "progress": 0.0,          # 回放进度 0-1
            "data_buffer": [],        # 数据缓冲区
            "buffer_index": 0         # 缓冲区索引
        }
        
        self._replay_task: Optional[asyncio.Task] = None
    
    async def start_replay(self, start_time: str, end_time: str, 
                          symbols: List[str], speed: float = 1.0) -> bool:
        """启动历史数据回放"""
        
        try:
            # 1. 解析时间参数
            start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
            
            # 2. 加载历史数据
            await self._load_replay_data(symbols, start_dt, end_dt)
            
            # 3. 配置回放参数
            self._replay_config.update({
                "start_time": start_dt,
                "end_time": end_dt,
                "speed_multiplier": speed
            })
            
            # 4. 启动回放任务
            self._replay_task = asyncio.create_task(self._replay_loop())
            self._replay_state["status"] = "playing"
            
            logger.info(f"虚拟数据源回放已启动: {start_time} -> {end_time}, 速度{speed}x")
            return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
            
        except Exception as e:
            logger.error(f"启动虚拟数据源回放失败: {e}")
            return False
    
    async def _replay_loop(self) -> None:
        """回放主循环"""
        
        while (self._replay_state["status"] == "playing" and 
               self._replay_state["buffer_index"] < len(self._replay_state["data_buffer"])):
            
            try:
                # 1. 获取当前数据
                current_data = self._replay_state["data_buffer"][self._replay_state["buffer_index"]]
                
                # 2. 推送数据
                await self._push_replay_data(current_data)
                
                # 3. 更新状态
                self._replay_state["buffer_index"] += 1
                self._update_replay_progress()
                
                # 4. 计算等待时间
                wait_time = self._calculate_wait_time(current_data)
                await asyncio.sleep(wait_time)
                
            except Exception as e:
                logger.error(f"回放循环异常: {e}")
                break
        
        # 回放结束处理
        if self._replay_config["auto_loop"]:
            await self._restart_replay()
        else:
            self._replay_state["status"] = "stopped"
            logger.info("虚拟数据源回放已结束")
```

**回放速度控制**：
```python
def _calculate_wait_time(self, current_data: Dict) -> float:
    """计算等待时间"""
    
    # 1. 获取基础间隔
    base_interval = self._replay_config["interval_ms"] / 1000.0
    
    # 2. 应用速度倍数
    speed = self._replay_config["speed_multiplier"]
    actual_interval = base_interval / speed
    
    # 3. 考虑数据时间间隔
    if self._replay_state["buffer_index"] > 0:
        prev_data = self._replay_state["data_buffer"][self._replay_state["buffer_index"] - 1]
        time_diff = (current_data["datetime"] - prev_data["datetime"]).total_seconds()
        
        # 使用实际时间间隔（但不超过最大间隔）
        actual_interval = min(actual_interval, time_diff / speed)
    
    # 4. 确保最小间隔
    return max(0.01, actual_interval)  # 最小10ms

async def pause_replay(self) -> None:
    """暂停回放"""
    if self._replay_state["status"] == "playing":
        self._replay_state["status"] = "paused"
        logger.info("虚拟数据源回放已暂停")

async def resume_replay(self) -> None:
    """恢复回放"""
    if self._replay_state["status"] == "paused":
        self._replay_state["status"] = "playing"
        logger.info("虚拟数据源回放已恢复")

async def set_replay_speed(self, speed: float) -> None:
    """设置回放速度"""
    self._replay_config["speed_multiplier"] = max(0.1, min(10.0, speed))
    logger.info(f"回放速度已设置为: {speed}x")
```

### 9.3 数据推送规则

#### 9.3.1 推送频率控制

**推送节流规则**：
```python
class DataPushThrottler:
    """数据推送节流器"""
    
    def __init__(self):
        self._push_limits = {
            "tick": 100,      # Tick数据：最多100次/秒
            "bar": 10,        # Bar数据：最多10次/秒
            "order": 50,      # 订单数据：最多50次/秒
            "trade": 50       # 成交数据：最多50次/秒
        }
        
        self._push_counters: Dict[str, Dict] = {}
        self._last_reset_time = time.time()
    
    def can_push(self, data_type: str, symbol: str = None) -> bool:
        """检查是否可以推送"""
        
        current_time = time.time()
        
        # 1. 每秒重置计数器
        if current_time - self._last_reset_time >= 1.0:
            self._reset_counters()
            self._last_reset_time = current_time
        
        # 2. 检查推送限制
        limit = self._push_limits.get(data_type, 10)
        counter_key = f"{data_type}_{symbol}" if symbol else data_type
        
        current_count = self._push_counters.get(counter_key, 0)
        
        if current_count >= limit:
            return False
        
        # 3. 增加计数
        self._push_counters[counter_key] = current_count + 1
        return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
    
    def _reset_counters(self) -> None:
        """重置推送计数器"""
        self._push_counters.clear()
```

#### 9.3.2 推送质量保证

**数据完整性检查**：
```python
async def _push_tick_data(self, symbol: str, tick_data: TickData) -> None:
    """推送Tick数据（带质量检查）"""
    
    # 1. 数据完整性检查
    if not self._validate_tick_data(tick_data):
        logger.warning(f"Tick数据验证失败，跳过推送: {symbol}")
        return
    
    # 2. 推送频率检查
    if not self.push_throttler.can_push("tick", symbol):
        logger.debug(f"推送频率超限，跳过: {symbol}")
        return
    
    # 3. 数据去重检查
    if self._is_duplicate_tick(symbol, tick_data):
        logger.debug(f"重复Tick数据，跳过推送: {symbol}")
        return
    
    # 4. 推送数据
    try:
        event = Event(EVENT_TICK, tick_data)
        self.event_engine.put(event)
        
        # 5. 记录推送统计
        self._record_push_stats(symbol, "tick", True)
        
    except Exception as e:
        logger.error(f"推送Tick数据失败 {symbol}: {e}")
        self._record_push_stats(symbol, "tick", False)

def _validate_tick_data(self, tick_data: TickData) -> bool:
    """验证Tick数据完整性"""
    
    # 1. 必需字段检查
    required_fields = ["symbol", "datetime", "last_price"]
    for field in required_fields:
        if not hasattr(tick_data, field) or getattr(tick_data, field) is None:
            return False
    
    # 2. 数据合理性检查
    if tick_data.last_price <= 0:
        return False
    
    if hasattr(tick_data, "volume") and tick_data.volume < 0:
        return False
    
    # 3. 时间合理性检查
    current_time = datetime.now()
    if tick_data.datetime > current_time + timedelta(minutes=5):
        return False  # 未来时间超过5分钟
    
    return True

---

## 十、文件监控业务规则

### 10.1 实时文件监控

#### 10.1.1 监控范围和策略

**监控目录配置**：
```python
class DataFileWatcher:
    """数据文件监控器"""
    
    def __init__(self, watch_dir: Path, event_engine: EventEngine):
        self.watch_dir = watch_dir
        self.event_engine = event_engine
        
        # 监控配置
        self._watch_config = {
            "recursive": True,              # 递归监控子目录
            "file_patterns": ["*.parquet"], # 监控文件模式
            "ignore_patterns": [            # 忽略模式
                "*.tmp", "*.temp", "*.lock", 
                "*~", ".DS_Store", "Thumbs.db"
            ],
            "debounce_seconds": 2.0,       # 防抖延迟2秒
            "batch_events": True,          # 批量处理事件
            "max_batch_size": 100          # 最大批次大小
        }
        
        # 监控状态
        self._observer: Optional[Observer] = None
        self._event_handler: Optional[FileSystemEventHandler] = None
        self._is_running = False
        
        # 防抖机制
        self._pending_events: Dict[str, Dict] = {}
        self._debounce_timers: Dict[str, asyncio.Handle] = {}
    
    def start_monitoring(self) -> bool:
        """启动文件监控"""
        
        if self._is_running:
            logger.warning("文件监控已在运行")
            return True
        
        try:
            # 1. 创建事件处理器
            self._event_handler = DataFileEventHandler(self)
            
            # 2. 创建监控器
            self._observer = Observer()
            self._observer.schedule(
                self._event_handler,
                str(self.watch_dir),
                recursive=self._watch_config["recursive"]
            )
            
            # 3. 启动监控
            self._observer.start()
            self._is_running = True
            
            logger.info(f"文件监控已启动: {self.watch_dir}")
            return True
            
        except Exception as e:
            logger.error(f"启动文件监控失败: {e}")
            return False
```

**文件过滤规则**：
```python
def _should_monitor_file(self, file_path: Path) -> bool:
    """判断是否应该监控文件"""
    
    file_name = file_path.name
    
    # 1. 检查文件模式匹配
    patterns = self._watch_config["file_patterns"]
    if patterns and not any(fnmatch.fnmatch(file_name, pattern) for pattern in patterns):
        return False
    
    # 2. 检查忽略模式
    ignore_patterns = self._watch_config["ignore_patterns"]
    if any(fnmatch.fnmatch(file_name, pattern) for pattern in ignore_patterns):
        return False
    
    # 3. 检查文件大小（跳过空文件）
    try:
        if file_path.stat().st_size == 0:
            return False
    except OSError:
        return False
    
    # 4. 检查文件扩展名
    if file_path.suffix.lower() not in [".parquet", ".json"]:
        return False
    
    return True
```

#### 10.1.2 防抖机制实现

**事件防抖规则**：
```python
class DataFileEventHandler(FileSystemEventHandler):
    """数据文件事件处理器（带防抖）"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self.logger = logging.getLogger(__name__)
    
    def on_modified(self, event):
        """文件修改事件"""
        if not event.is_directory:
            self._handle_file_event("modified", event.src_path)
    
    def on_created(self, event):
        """文件创建事件"""
        if not event.is_directory:
            self._handle_file_event("created", event.src_path)
    
    def on_deleted(self, event):
        """文件删除事件"""
        if not event.is_directory:
            self._handle_file_event("deleted", event.src_path)
    
    def on_moved(self, event):
        """文件移动事件"""
        if not event.is_directory:
            self._handle_file_event("moved", event.dest_path, event.src_path)
    
    def _handle_file_event(self, event_type: str, file_path: str, old_path: str = None):
        """处理文件事件（带防抖）"""
        
        file_path_obj = Path(file_path)
        
        # 1. 检查是否应该监控
        if not self.watcher._should_monitor_file(file_path_obj):
            return
        
        # 2. 创建事件数据
        event_data = {
            "type": event_type,
            "file_path": file_path,
            "old_path": old_path,
            "timestamp": time.time(),
            "file_size": self._get_file_size(file_path_obj)
        }
        
        # 3. 应用防抖机制
        self._debounce_event(file_path, event_data)
    
    def _debounce_event(self, file_path: str, event_data: Dict):
        """防抖处理事件"""
        
        # 1. 取消之前的定时器
        if file_path in self.watcher._debounce_timers:
            self.watcher._debounce_timers[file_path].cancel()
        
        # 2. 更新待处理事件
        self.watcher._pending_events[file_path] = event_data
        
        # 3. 设置新的防抖定时器
        loop = asyncio.get_event_loop()
        timer = loop.call_later(
            self.watcher._watch_config["debounce_seconds"],
            self._process_debounced_event,
            file_path
        )
        self.watcher._debounce_timers[file_path] = timer
    
    def _process_debounced_event(self, file_path: str):
        """处理防抖后的事件"""
        
        # 1. 获取事件数据
        event_data = self.watcher._pending_events.pop(file_path, None)
        if not event_data:
            return
        
        # 2. 清理定时器
        self.watcher._debounce_timers.pop(file_path, None)
        
        # 3. 处理事件
        asyncio.create_task(self._async_process_event(event_data))
```

### 10.2 文件变更处理

#### 10.2.1 变更类型识别

**变更分析规则**：
```python
async def _async_process_event(self, event_data: Dict):
    """异步处理文件事件"""
    
    event_type = event_data["type"]
    file_path = Path(event_data["file_path"])
    
    try:
        if event_type == "created":
            await self._handle_file_created(file_path, event_data)
        elif event_type == "modified":
            await self._handle_file_modified(file_path, event_data)
        elif event_type == "deleted":
            await self._handle_file_deleted(file_path, event_data)
        elif event_type == "moved":
            await self._handle_file_moved(file_path, event_data)
            
    except Exception as e:
        self.logger.error(f"处理文件事件失败 {file_path}: {e}")

async def _handle_file_modified(self, file_path: Path, event_data: Dict):
    """处理文件修改事件"""
    
    # 1. 解析文件信息
    file_info = self._parse_data_file_path(file_path)
    if not file_info:
        return
    
    # 2. 检查修改类型
    modification_type = await self._detect_modification_type(file_path, event_data)
    
    # 3. 根据修改类型处理
    if modification_type == "data_update":
        # 数据更新：触发质量重新扫描
        await self._trigger_quality_rescan(file_info["symbol"], file_info["interval"])
        
        # 清除相关缓存
        await self._invalidate_cache(file_info["symbol"], file_info["interval"])
        
    elif modification_type == "file_corruption":
        # 文件损坏：记录错误并触发修复
        await self._handle_file_corruption(file_info["symbol"], file_info["interval"])
        
    # 4. 发布文件变更事件
    await self._publish_file_change_event(file_path, modification_type, file_info)

def _parse_data_file_path(self, file_path: Path) -> Optional[Dict]:
    """解析数据文件路径"""
    
    try:
        # 标准路径格式: data/kline/{interval}/{symbol}.parquet
        parts = file_path.parts
        
        if len(parts) >= 3 and parts[-3] == "kline":
            interval = parts[-2]
            symbol = file_path.stem  # 文件名不含扩展名
            
            return {
                "symbol": symbol,
                "interval": interval,
                "file_type": "kline_data"
            }
    except Exception as e:
        self.logger.debug(f"解析文件路径失败 {file_path}: {e}")
    
    return None
```

#### 10.2.2 自动修复机制

**文件损坏检测**：
```python
async def _detect_modification_type(self, file_path: Path, event_data: Dict) -> str:
    """检测文件修改类型"""
    
    try:
        # 1. 检查文件是否可读
        if not file_path.exists():
            return "file_deleted"
        
        # 2. 检查文件大小
        current_size = file_path.stat().st_size
        if current_size == 0:
            return "file_corruption"
        
        # 3. 尝试读取文件头部
        try:
            if file_path.suffix == ".parquet":
                # 检查Parquet文件完整性
                df = pd.read_parquet(file_path, nrows=1)
                if df.empty:
                    return "file_corruption"
            elif file_path.suffix == ".json":
                # 检查JSON文件完整性
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
        except Exception:
            return "file_corruption"
        
        # 4. 检查文件大小变化
        previous_size = event_data.get("previous_size", 0)
        if current_size > previous_size:
            return "data_update"
        elif current_size < previous_size:
            return "data_truncation"
        else:
            return "metadata_update"
            
    except Exception as e:
        self.logger.error(f"检测文件修改类型失败 {file_path}: {e}")
        return "unknown_change"

async def _handle_file_corruption(self, symbol: str, interval: str):
    """处理文件损坏"""
    
    self.logger.error(f"检测到文件损坏: {symbol}_{interval}")
    
    # 1. 记录损坏事件
    corruption_event = {
        "symbol": symbol,
        "interval": interval,
        "detected_at": time.time(),
        "auto_repair_attempted": False
    }
    
    # 2. 尝试自动修复
    try:
        # 从备份恢复（如果有）
        backup_restored = await self._restore_from_backup(symbol, interval)
        
        if not backup_restored:
            # 触发重新下载
            await self._trigger_redownload(symbol, interval)
            corruption_event["auto_repair_attempted"] = True
            
    except Exception as e:
        self.logger.error(f"自动修复失败 {symbol}_{interval}: {e}")
    
    # 3. 发布损坏事件
    event = Event(EVENT_FILE_CORRUPTION, corruption_event)
    self.watcher.event_engine.put(event)
```

### 10.3 监控性能优化

#### 10.3.1 批量事件处理

**事件批处理规则**：
```python
class BatchEventProcessor:
    """批量事件处理器"""
    
    def __init__(self, watcher: DataFileWatcher):
        self.watcher = watcher
        self._event_batch: List[Dict] = []
        self._batch_timer: Optional[asyncio.Handle] = None
        self._batch_lock = asyncio.Lock()
    
    async def add_event(self, event_data: Dict):
        """添加事件到批次"""
        
        async with self._batch_lock:
            self._event_batch.append(event_data)
            
            # 检查是否达到批次大小
            max_batch_size = self.watcher._watch_config["max_batch_size"]
            if len(self._event_batch) >= max_batch_size:
                await self._process_batch()
            else:
                # 设置批次处理定时器
                self._schedule_batch_processing()
    
    def _schedule_batch_processing(self):
        """调度批次处理"""
        
        # 取消之前的定时器
        if self._batch_timer:
            self._batch_timer.cancel()
        
        # 设置新定时器（1秒后处理）
        loop = asyncio.get_event_loop()
        self._batch_timer = loop.call_later(1.0, self._trigger_batch_processing)
    
    def _trigger_batch_processing(self):
        """触发批次处理"""
        asyncio.create_task(self._process_batch())
    
    async def _process_batch(self):
        """处理事件批次"""
        
        async with self._batch_lock:
            if not self._event_batch:
                return
            
            # 1. 获取当前批次
            current_batch = self._event_batch.copy()
            self._event_batch.clear()
            
            # 2. 取消定时器
            if self._batch_timer:
                self._batch_timer.cancel()
                self._batch_timer = None
        
        # 3. 处理批次事件
        await self._process_event_batch(current_batch)
    
    async def _process_event_batch(self, events: List[Dict]):
        """处理事件批次"""
        
        # 1. 按文件分组事件
        file_groups = {}
        for event in events:
            file_path = event["file_path"]
            if file_path not in file_groups:
                file_groups[file_path] = []
            file_groups[file_path].append(event)
        
        # 2. 并发处理各文件的事件
        tasks = []
        for file_path, file_events in file_groups.items():
            task = self._process_file_events(file_path, file_events)
            tasks.append(task)
        
        # 3. 等待所有任务完成
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 4. 处理异常
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                file_path = list(file_groups.keys())[i]
                self.watcher.logger.error(f"批量处理文件事件失败 {file_path}: {result}")
```

#### 10.3.2 监控资源控制

**资源使用限制**：
```python
class MonitoringResourceController:
    """监控资源控制器"""
    
    def __init__(self):
        self._resource_limits = {
            "max_concurrent_scans": 10,     # 最大并发扫描数
            "max_memory_usage_mb": 500,     # 最大内存使用500MB
            "scan_timeout_seconds": 30,     # 扫描超时30秒
            "max_events_per_second": 1000   # 最大事件处理速率
        }
        
        self._current_usage = {
            "concurrent_scans": 0,
            "memory_usage_mb": 0,
            "events_this_second": 0,
            "last_reset_time": time.time()
        }
        
        self._resource_lock = asyncio.Semaphore(
            self._resource_limits["max_concurrent_scans"]
        )
    
    async def acquire_scan_resource(self) -> bool:
        """获取扫描资源"""
        
        # 1. 检查内存使用
        if self._get_memory_usage() > self._resource_limits["max_memory_usage_mb"]:
            logger.warning("内存使用超限，拒绝新的扫描任务")
            return False
        
        # 2. 检查事件处理速率
        if not self._check_event_rate_limit():
            logger.warning("事件处理速率超限，拒绝新的扫描任务")
            return False
        
        # 3. 获取并发资源
        try:
            await asyncio.wait_for(
                self._resource_lock.acquire(),
                timeout=5.0
            )
            self._current_usage["concurrent_scans"] += 1
            return True
        except asyncio.TimeoutError:
            logger.warning("获取扫描资源超时")
            return False
    
    def release_scan_resource(self):
        """释放扫描资源"""
        self._current_usage["concurrent_scans"] -= 1
        self._resource_lock.release()
    
    def _check_event_rate_limit(self) -> bool:
        """检查事件处理速率限制"""
        
        current_time = time.time()
        
        # 每秒重置计数器
        if current_time - self._current_usage["last_reset_time"] >= 1.0:
            self._current_usage["events_this_second"] = 0
            self._current_usage["last_reset_time"] = current_time
        
        # 检查速率限制
        if self._current_usage["events_this_second"] >= self._resource_limits["max_events_per_second"]:
            return False
        
        self._current_usage["events_this_second"] += 1
        return True
```

---

## 总结

本文档详细定义了data_module_vnpy新架构下的业务流程规则细节，涵盖了：

1. **品种管理**：分类规则、缓存机制、API调用策略
2. **数据下载**：两段式下载、并发控制、增量更新
3. **数据验证**：格式验证、逻辑验证、完整性检查
4. **缓存管理**：LRU缓存、TTL机制、跨进程同步
5. **负载均衡**：木桶理论、智能防抖、动态调整
6. **IPO管理**：日期解析、缓存策略、未上市品种处理
7. **质量管理**：混合扫描、质量评分、自动修复
8. **统一查询**：四层融合、智能预加载、缺失处理
9. **实时推送**：轮询转推送、VNPy集成、虚拟回放
10. **文件监控**：实时监控、防抖机制、批量处理

这些业务规则确保了新架构在保持技术先进性的同时，完整保留了所有业务逻辑和用户需求。所有规则都基于现有代码的实际实现，并针对新架构进行了优化和扩展。
```
```
```
```
```
```
```
