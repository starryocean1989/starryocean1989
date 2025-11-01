# data_module_vnpy 新架构优化补充文档

## 一、背景分析

### 1.1 问题发现

经过深入代码审查，发现v3.0重构中存在**架构不一致**问题：

**关键发现**：
1. **native_iocp模块**：专为本地数据扫描和TDX数据reader设计
2. **本地数据扫描**：使用硬编码配置（8进程，2000协程），未接入LoadBalancer
3. **TDX数据reader**：同步读取，未使用多进程多协程架构
4. **LoadBalancer简化过度**：移除了任务类型系统，导致无法区分不同任务类型

### 1.2 native_iocp的设计初衷

**native_iocp模块的核心价值**：
- 真异步文件I/O（Windows IOCP）
- 无线程池开销
- 适用于**大量小文件**的并发读取
- 性能提升：40-60%（相比aiofiles）

**典型应用场景**：
1. **本地数据扫描**：扫描数千个Parquet文件，检查数据质量
2. **TDX数据reader**：读取数千个通达信本地二进制文件

### 1.3 架构不一致的影响

| 场景 | v3.0现状 | 问题 | 应有架构 |
|------|---------|------|---------|
| **K线下载** | LoadBalancer + 多进程多协程 | ✅ 正确 | 网络I/O密集，动态调整 |
| **本地数据扫描** | 硬编码8进程2000协程 | ❌ 不一致 | 磁盘I/O密集，应接入LoadBalancer |
| **TDX数据reader** | 同步读取 | ❌ 不一致 | 磁盘I/O密集，应接入LoadBalancer |

---

## 二、优化目标

### 2.1 恢复任务类型系统

**设计原则**：轻量级、类型安全、易扩展

```python
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any, List

class TaskCategory(str, Enum):
    """任务类别（轻量级枚举）"""
    NETWORK_DOWNLOAD = "network_download"    # K线下载（网络I/O密集）
    LOCAL_SCAN = "local_scan"                # 本地数据扫描（磁盘I/O密集）
    LOCAL_READ = "local_read"                # TDX数据读取（磁盘I/O密集）

@dataclass
class TaskConfig:
    """任务配置（简化版TaskMetrics）"""
    name: str                    # 任务名称
    category: TaskCategory       # 任务类别
    total_count: int             # 任务总数
    
    # 资源特征
    is_io_intensive: bool = True
    is_cpu_intensive: bool = False
    is_memory_intensive: bool = False
    
    # 预估资源
    estimated_memory_mb: float = 100.0
    estimated_duration_sec: float = 60.0
```

**优势**：
1. ✅ 轻量级：相比v2.1的TaskMetrics简化90%
2. ✅ 类型安全：使用Enum替代字符串
3. ✅ 易扩展：新增任务类型只需添加枚举值

### 2.2 恢复队列背压控制系统

**设计原则**：专注于磁盘I/O观察

```python
@dataclass
class QueueMetrics:
    """队列指标（观察磁盘I/O的关键指标）"""
    queue_name: str
    current_size: int          # 当前队列大小
    max_size: int              # 最大队列容量
    fill_rate: float           # 填充率（0-1）
    
    # 背压相关指标
    enqueue_lag_ms: float      # 入队延迟（毫秒）
    dequeue_lag_ms: float      # 出队延迟（毫秒）
    avg_task_time_ms: float    # 平均任务耗时（毫秒）
    
    # 告警阈值
    HIGH_FILL_RATE = 0.8       # 80%填充率告警
    CRITICAL_FILL_RATE = 0.95  # 95%填充率严重告警

class QueuePressureMonitor:
    """队列压力监控器（轻量级）"""
    
    def __init__(self):
        self._metrics_history = deque(maxlen=60)  # 保留60秒历史
    
    def record_metrics(self, metrics: QueueMetrics) -> None:
        """记录队列指标"""
        self._metrics_history.append(metrics)
    
    def get_pressure_level(self) -> str:
        """获取压力等级：normal/medium/high/critical"""
        if not self._metrics_history:
            return "normal"
        
        latest = self._metrics_history[-1]
        
        if latest.fill_rate >= QueueMetrics.CRITICAL_FILL_RATE:
            return "critical"
        elif latest.fill_rate >= QueueMetrics.HIGH_FILL_RATE:
            return "high"
        elif latest.fill_rate >= 0.6:
            return "medium"
        else:
            return "normal"
    
    def get_adjustment_factor(self) -> float:
        """获取调整系数（用于动态调整并发）"""
        pressure = self.get_pressure_level()
        
        # 根据压力等级返回调整系数
        if pressure == "critical":
            return 0.5  # 严重积压，减半
        elif pressure == "high":
            return 0.7  # 高压，减少30%
        elif pressure == "medium":
            return 0.9  # 中压，减少10%
        else:
            return 1.0  # 正常，不调整
```

**优势**：
1. ✅ 专注磁盘I/O观察：通过队列积压反映磁盘I/O瓶颈
2. ✅ 轻量级实现：相比v2.1简化80%
3. ✅ 与木桶理论结合：作为磁盘I/O的补充观察指标

### 2.3 LoadBalancer架构升级

**核心变化**：

```python
class LoadBalancer:
    """负载均衡器v3.1 - 支持任务类型区分和队列背压监控"""
    
    def __init__(self, config_manager: Optional[ConfigManager] = None):
        # 资源监控
        self.resource_monitor = ResourceMonitor()
        
        # 队列压力监控（新增）
        self.queue_monitor = QueuePressureMonitor()
        
        # 任务策略注册表（新增）
        self.task_strategies = TaskStrategyRegistry()
        
        # 动态配置计算器
        self.config_calculator = DynamicConfigCalculator()
        
        # 智能调优器
        self.adaptive_tuner = IntelligentAdaptiveTuner()
        
        # 防抖机制
        self._last_adjustment_time = 0
        self._adjustment_history = []
        self._base_interval = 1.0
        self._pattern_interval = 3.0
    
    def get_optimal_config(
        self, 
        task: TaskConfig,
        queue_metrics: Optional[QueueMetrics] = None
    ) -> Dict[str, Any]:
        """获取最优配置（支持任务类型和队列压力）"""
        
        # 1. 防抖检查
        current_time = time.time()
        interval = self._get_debounce_interval()
        if current_time - self._last_adjustment_time < interval:
            return self._get_cached_config()
        
        # 2. 资源监控（木桶理论）
        resource_metrics = self.resource_monitor.get_metrics()
        
        # 3. 队列压力监控（新增）
        if queue_metrics:
            self.queue_monitor.record_metrics(queue_metrics)
            queue_pressure = self.queue_monitor.get_adjustment_factor()
        else:
            queue_pressure = 1.0
        
        # 4. 获取任务策略
        strategy = self.task_strategies.get_strategy(task.category)
        
        # 5. 动态配置计算
        config = self.config_calculator.calculate(
            task_type=task.category.value,
            base_config=strategy,
            resource_metrics=resource_metrics
        )
        
        # 6. 智能调优
        config = self.adaptive_tuner.adjust(config, resource_metrics)
        
        # 7. 队列压力调整（新增）
        config = self._apply_queue_pressure(config, queue_pressure)
        
        # 8. 更新防抖历史
        self._update_adjustment_history(config)
        self._last_adjustment_time = current_time
        
        return config
    
    def _apply_queue_pressure(
        self, 
        config: Dict[str, Any], 
        queue_pressure: float
    ) -> Dict[str, Any]:
        """应用队列压力调整"""
        # 根据队列压力调整并发度
        config["processes"] = max(1, int(config["processes"] * queue_pressure))
        config["coroutines_per_process"] = max(
            10, 
            int(config["coroutines_per_process"] * queue_pressure)
        )
        config["queue_pressure_factor"] = queue_pressure
        
        return config
```

**新增木桶理论第四板**：

```python
class ResourceMonitor:
    """资源监控器 - 木桶理论四板"""
    
    def get_metrics(self) -> ResourceMetrics:
        """获取资源指标"""
        metrics = ResourceMetrics()
        
        # 板1: CPU
        metrics.cpu_percent = psutil.cpu_percent(interval=0.1)
        
        # 板2: 内存
        metrics.memory_percent = psutil.virtual_memory().percent
        
        # 板3: 磁盘I/O（原有逻辑）
        metrics.disk_io_percent = self._get_disk_io_percent()
        
        # 板4: 队列积压（新增，通过外部传入）
        # 注：由LoadBalancer.get_optimal_config()的queue_metrics参数传入
        
        # 确定瓶颈（木桶短板）
        resources = {
            "CPU": metrics.cpu_percent,
            "Memory": metrics.memory_percent,
            "DiskIO": metrics.disk_io_percent,
        }
        metrics.bottleneck = max(resources, key=lambda k: resources[k])
        
        return metrics
```

---

## 三、任务策略注册表设计

### 3.1 TaskStrategyRegistry

```python
class TaskStrategyRegistry:
    """任务策略注册表"""
    
    _strategies: Dict[TaskCategory, Dict[str, Any]] = {
        # K线下载：网络I/O密集
        TaskCategory.NETWORK_DOWNLOAD: {
            "base_processes": 4,
            "base_coroutines_per_process": 40,
            "max_processes": 8,
            "max_coroutines_per_process": 50,
            "resource_weights": {
                "cpu": 0.2,
                "memory": 0.3,
                "disk_io": 0.1,
                "network_io": 0.4,  # 网络I/O权重最高
            },
            "description": "网络下载任务（K线、IPO日期）",
        },
        
        # 本地数据扫描：磁盘I/O密集
        TaskCategory.LOCAL_SCAN: {
            "base_processes": 8,
            "base_coroutines_per_process": 2000,  # 协程数高（大量小文件）
            "max_processes": 16,
            "max_coroutines_per_process": 3000,
            "resource_weights": {
                "cpu": 0.2,
                "memory": 0.2,
                "disk_io": 0.5,  # 磁盘I/O权重最高
                "network_io": 0.1,
            },
            "description": "本地数据扫描（质量检查）",
        },
        
        # TDX数据读取：磁盘I/O密集
        TaskCategory.LOCAL_READ: {
            "base_processes": 4,
            "base_coroutines_per_process": 1000,
            "max_processes": 8,
            "max_coroutines_per_process": 1500,
            "resource_weights": {
                "cpu": 0.3,  # TDX解码需要CPU
                "memory": 0.2,
                "disk_io": 0.4,  # 磁盘I/O权重高
                "network_io": 0.1,
            },
            "description": "TDX本地文件读取",
        },
    }
    
    @classmethod
    def get_strategy(cls, category: TaskCategory) -> Dict[str, Any]:
        """获取任务策略"""
        return cls._strategies.get(
            category, 
            cls._strategies[TaskCategory.NETWORK_DOWNLOAD]
        )
```

---

## 四、本地数据扫描接入方案

### 4.1 当前问题

**文件**：`data_quality.py`
**类**：`HealthChecker`
**方法**：`_scan_detailed_quality_multiprocess_hybrid()`

**当前实现**：
```python
# ❌ 硬编码配置
num_processes = 8
max_coroutines = 2000

# 启动固定数量的进程
for i in range(num_processes):
    p = Process(target=_run_quality_scan_worker_multiprocess, args=(...))
    p.start()
```

### 4.2 优化方案

**接入LoadBalancer**：

```python
def _scan_detailed_quality_multiprocess_hybrid(
    self,
    local_symbols: List[str],
    intervals: List[str],
    progress_callback=None,
) -> Dict[str, Any]:
    """详细质量扫描（接入LoadBalancer）"""
    
    # 1. 创建任务配置
    total_tasks = len(local_symbols) * len(intervals)
    task = TaskConfig(
        name="quality_scan",
        category=TaskCategory.LOCAL_SCAN,
        total_count=total_tasks,
        is_io_intensive=True,  # 磁盘I/O密集
        is_cpu_intensive=False,
        estimated_memory_mb=500.0,
        estimated_duration_sec=total_tasks * 0.1,
    )
    
    # 2. 获取LoadBalancer最优配置
    from .load_balancer import get_load_balancer
    load_balancer = get_load_balancer()
    
    # 初始调用（无队列压力）
    lb_config = load_balancer.get_optimal_config(task, queue_metrics=None)
    
    num_processes = lb_config.get("processes", 8)
    max_coroutines = lb_config.get("coroutines_per_process", 2000)
    
    self.logger.info(
        f"📊 质量扫描配置: 进程={num_processes}, "
        f"协程={max_coroutines}, 压力={lb_config.get('pressure_score', 0):.1f}/100"
    )
    
    # 3. 创建队列（带队列监控）
    manager = Manager()
    task_queue = manager.Queue()
    result_queue = manager.Queue()
    metrics_queue = manager.Queue()  # 队列指标队列
    
    # 4. 启动进程（使用动态配置）
    processes = []
    for i in range(num_processes):
        p = Process(
            target=_run_quality_scan_worker_multiprocess,
            args=(
                i, task_queue, result_queue, metrics_queue,
                max_coroutines,  # 使用LoadBalancer计算的协程数
                # ... 其他参数
            ),
        )
        p.start()
        processes.append(p)
    
    # 5. 监控并动态调整（新增）
    self._monitor_and_adjust_quality_scan(
        task, load_balancer, task_queue, result_queue, 
        metrics_queue, processes, total_tasks
    )
    
    # ... 其余逻辑
```

**队列监控和动态调整**：

```python
def _monitor_and_adjust_quality_scan(
    self,
    task: TaskConfig,
    load_balancer: LoadBalancer,
    task_queue, result_queue, metrics_queue,
    processes: List[Process],
    total_tasks: int,
) -> None:
    """监控队列压力并动态调整"""
    
    last_adjust_time = time.time()
    adjust_interval = 5.0  # 每5秒检查一次
    
    completed = 0
    while completed < total_tasks:
        try:
            # 收集结果
            symbol, quality_dict = result_queue.get(timeout=1)
            completed += 1
            
            # 检查是否需要调整
            current_time = time.time()
            if current_time - last_adjust_time >= adjust_interval:
                # 创建队列指标
                queue_metrics = QueueMetrics(
                    queue_name="quality_scan",
                    current_size=task_queue.qsize(),
                    max_size=10000,
                    fill_rate=task_queue.qsize() / 10000.0,
                    enqueue_lag_ms=0,  # TODO: 实际测量
                    dequeue_lag_ms=0,  # TODO: 实际测量
                    avg_task_time_ms=0,  # TODO: 实际测量
                )
                
                # 重新获取配置（带队列压力）
                lb_config = load_balancer.get_optimal_config(task, queue_metrics)
                
                # 如果配置有变化，记录日志（暂不支持动态扩缩进程）
                new_processes = lb_config.get("processes", 8)
                new_coroutines = lb_config.get("coroutines_per_process", 2000)
                
                if new_processes != len(processes):
                    self.logger.info(
                        f"⚠️ LoadBalancer建议调整进程数: {len(processes)} → {new_processes} "
                        f"（当前不支持动态调整，下次扫描生效）"
                    )
                
                last_adjust_time = current_time
        
        except queue.Empty:
            continue
```

---

## 五、TDX数据reader接入方案

### 5.1 当前问题

**文件**：`data_acquisition.py`
**类**：`TdxDataReader`
**方法**：`fetch_async()`, `fetch_batch_async()`

**当前实现**：
```python
# ❌ 同步读取，单线程
async def fetch_async(self, symbol: str, data_type: str, market: str) -> pd.DataFrame:
    """读取单个TDX文件"""
    # 直接读取文件，无并发控制
    if market == "bj":
        df = self.bj_decoder.read_day_file(data_file)
    else:
        df = await read_day_data(data_file)
    
    return df

# ❌ 批量读取，无负载均衡
async def fetch_batch_async(self, symbols: List[str], ...) -> Dict[str, pd.DataFrame]:
    """批量读取（asyncio.gather）"""
    tasks = [self.fetch_async(s, data_type, market) for s in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return dict(zip(symbols, results))
```

### 5.2 优化方案

**设计思路**：
1. 改造为**多进程+多协程**架构
2. 接入LoadBalancer获取最优配置
3. 复用K线下载的worker模式

**新增方法**：`fetch_batch_multiprocess()`

```python
class TdxDataReader:
    """TDX数据读取器（v3.1 - 接入LoadBalancer）"""
    
    def fetch_batch_multiprocess(
        self,
        symbols: List[str],
        data_type: str = "day",
        market: Optional[str] = None,
        progress_callback=None,
    ) -> Dict[str, pd.DataFrame]:
        """多进程+多协程批量读取（接入LoadBalancer）"""
        
        total_tasks = len(symbols)
        
        # 1. 创建任务配置
        task = TaskConfig(
            name="tdx_read",
            category=TaskCategory.LOCAL_READ,
            total_count=total_tasks,
            is_io_intensive=True,
            is_cpu_intensive=True,  # TDX解码需要CPU
            estimated_memory_mb=total_tasks * 0.5,  # 每文件约0.5MB
            estimated_duration_sec=total_tasks * 0.01,  # 每文件约10ms
        )
        
        # 2. 获取LoadBalancer配置
        from .load_balancer import get_load_balancer
        load_balancer = get_load_balancer()
        lb_config = load_balancer.get_optimal_config(task, queue_metrics=None)
        
        num_processes = lb_config.get("processes", 4)
        max_coroutines = lb_config.get("coroutines_per_process", 1000)
        
        self.logger.info(
            f"📊 TDX读取配置: 进程={num_processes}, "
            f"协程={max_coroutines}, 总任务={total_tasks}"
        )
        
        # 3. 初始化多进程对象
        manager = Manager()
        task_queue = manager.Queue()
        result_queue = manager.Queue()
        
        # 填充任务队列
        for symbol in symbols:
            task_queue.put((symbol, data_type, market))
        
        # 4. 启动worker进程
        processes = []
        for i in range(num_processes):
            p = Process(
                target=_tdx_reader_worker,
                args=(
                    i, task_queue, result_queue,
                    self.source_path,  # TDX目录路径
                    max_coroutines,
                ),
            )
            p.start()
            processes.append(p)
        
        # 5. 收集结果
        results = {}
        completed = 0
        
        while completed < total_tasks:
            try:
                symbol, df = result_queue.get(timeout=1)
                results[symbol] = df
                completed += 1
                
                if progress_callback:
                    progress_callback(completed, total_tasks)
            
            except queue.Empty:
                # 检查进程状态
                if not any(p.is_alive() for p in processes):
                    self.logger.warning("所有进程已退出")
                    break
        
        # 6. 清理进程
        for p in processes:
            if p.is_alive():
                p.terminate()
                p.join(timeout=1)
        
        self.logger.info(f"✅ TDX读取完成: {len(results)}/{total_tasks}")
        return results
```

**Worker进程函数**：

```python
def _tdx_reader_worker(
    worker_id: int,
    task_queue,
    result_queue,
    tdx_root_path: Path,
    max_coroutines: int,
):
    """TDX读取器worker进程"""
    import asyncio
    
    # 配置子进程日志
    logger = _configure_subprocess_logging(worker_id, "tdx_read")
    
    # 运行异步事件循环
    asyncio.run(_tdx_reader_worker_async(
        worker_id, task_queue, result_queue, 
        tdx_root_path, max_coroutines, logger
    ))

async def _tdx_reader_worker_async(
    worker_id: int,
    task_queue,
    result_queue,
    tdx_root_path: Path,
    max_coroutines: int,
    logger,
):
    """TDX读取器异步worker"""
    
    # 创建TDX读取器实例
    reader = TdxDataReader(tdx_root_path)
    
    # 创建协程池（限制并发）
    semaphore = asyncio.Semaphore(max_coroutines)
    
    async def process_task():
        """处理单个任务"""
        while True:
            try:
                # 从队列获取任务（非阻塞）
                symbol, data_type, market = task_queue.get_nowait()
            except:
                break
            
            async with semaphore:
                try:
                    # 读取TDX文件（使用native_iocp）
                    df = await reader.fetch_async(symbol, data_type, market)
                    
                    # 返回结果
                    result_queue.put((symbol, df))
                
                except Exception as e:
                    logger.error(f"读取失败: {symbol}, {e}")
                    result_queue.put((symbol, pd.DataFrame()))
    
    # 启动多个协程任务
    tasks = [process_task() for _ in range(max_coroutines)]
    await asyncio.gather(*tasks, return_exceptions=True)
    
    logger.info(f"Worker {worker_id} 完成")
```

---

## 六、实施计划

### 6.1 Phase 1: LoadBalancer升级（优先级：高）

**文件**：`load_balancer.py`

**任务清单**：
- [x] 1.1 恢复任务类型系统（TaskCategory, TaskConfig）
- [x] 1.2 恢复队列压力监控（QueueMetrics, QueuePressureMonitor）
- [x] 1.3 创建任务策略注册表（TaskStrategyRegistry）
- [x] 1.4 升级LoadBalancer.get_optimal_config()
- [x] 1.5 更新DynamicConfigCalculator（支持任务策略）
- [x] 1.6 单元测试

**预期代码量**：+400行（load_balancer.py: 574行 → 974行）

### 6.2 Phase 2: K线下载适配（优先级：高）

**文件**：`data_acquisition.py`

**任务清单**：
- [x] 2.1 修改download_incremental_kline()，使用TaskConfig
- [x] 2.2 添加队列监控逻辑
- [x] 2.3 测试K线下载功能

**预期代码量**：+100行改动

### 6.3 Phase 3: 本地数据扫描接入（优先级：高）

**文件**：`data_quality.py`

**任务清单**：
- [x] 3.1 修改_scan_detailed_quality_multiprocess_hybrid()
- [x] 3.2 添加队列监控和动态调整逻辑
- [x] 3.3 测试数据扫描功能

**预期代码量**：+200行改动

### 6.4 Phase 4: TDX读取器接入（优先级：中）

**文件**：`data_acquisition.py`

**任务清单**：
- [x] 4.1 新增fetch_batch_multiprocess()方法
- [x] 4.2 新增_tdx_reader_worker()进程函数
- [x] 4.3 集成native_iocp异步文件读取
- [x] 4.4 测试TDX批量读取功能

**预期代码量**：+300行

### 6.5 Phase 5: 文档和测试（优先级：中）

**任务清单**：
- [x] 5.1 更新README.md
- [x] 5.2 补充API文档
- [x] 5.3 性能基准测试
- [x] 5.4 集成测试

---

## 七、性能预期

### 7.1 本地数据扫描

**当前性能（v3.0）**：
- 硬编码：8进程，2000协程
- 吞吐量：约150品种/秒（5000品种，耗时33秒）

**优化后预期（v3.1）**：
- LoadBalancer动态配置：8-16进程，2000-3000协程
- native_iocp加速：文件读取性能提升40-60%
- 队列压力监控：避免积压导致的性能下降
- **预期吞吐量**：200-250品种/秒（5000品种，耗时20-25秒）
- **性能提升**：30-40%

### 7.2 TDX数据读取

**当前性能（v3.0）**：
- 同步读取：单线程，asyncio.gather并发
- 吞吐量：约50文件/秒（1000文件，耗时20秒）

**优化后预期（v3.1）**：
- 多进程多协程：4进程，1000协程/进程
- native_iocp加速：文件读取性能提升40-60%
- LoadBalancer动态配置：根据资源自适应
- **预期吞吐量**：200-300文件/秒（1000文件，耗时3-5秒）
- **性能提升**：300-500%

---

## 八、风险评估

### 8.1 高风险项

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| LoadBalancer升级破坏K线下载 | 高 | 保持API向后兼容，充分测试 |
| 队列监控开销过大 | 中 | 轻量级实现，采样监控 |
| 多进程启动开销 | 中 | 进程池复用，延迟启动 |

### 8.2 中风险项

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| TDX读取器内存占用过高 | 中 | 限制最大协程数，批量处理 |
| 数据扫描动态调整不稳定 | 中 | 增大防抖间隔，谨慎调整 |

---

## 九、验收标准

### 9.1 功能验收

- [ ] K线下载功能正常（使用TaskConfig）
- [ ] 本地数据扫描接入LoadBalancer
- [ ] TDX批量读取性能达标
- [ ] 队列压力监控正常工作

### 9.2 性能验收

- [ ] 本地数据扫描性能提升≥30%
- [ ] TDX读取性能提升≥300%
- [ ] LoadBalancer配置合理性（通过日志验证）

### 9.3 稳定性验收

- [ ] 运行1小时无崩溃
- [ ] 极端负载场景（10000+任务）稳定
- [ ] 内存占用无明显增长

---

## 十、总结

本次优化补充方案的核心价值：

1. **架构一致性**：本地数据扫描、TDX读取统一接入LoadBalancer
2. **性能提升**：充分发挥native_iocp的性能优势
3. **智能调度**：根据任务类型定制负载均衡策略
4. **可观察性**：队列压力监控作为磁盘I/O的补充指标

**关键创新**：
- ✅ 轻量级任务类型系统（相比v2.1简化90%）
- ✅ 队列压力监控作为木桶理论第四板
- ✅ 任务策略注册表（易扩展）
- ✅ 本地I/O场景接入多进程多协程架构

**预期收益**：
- 本地数据扫描性能提升30-40%
- TDX读取性能提升300-500%
- 架构一致性提升，降低维护成本
