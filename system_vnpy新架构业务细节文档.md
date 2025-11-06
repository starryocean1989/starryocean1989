# -*- coding: utf-8 -*-
# system_vnpy 新架构业务细节文档

**版本**: v1.0 (完整版)
**创建日期**: 2025-11-02
**文档目标**: 定义新架构下的业务流程规则细节、实现逻辑和微观架构设计

> **📖 文档分工**:
> - **本文档**:专注于业务流程、规则细节、实现逻辑、算法描述、微观架构设计
> - **架构设计文档**:专注于架构设计、技术选型、性能目标、组件设计

---

## 📋 核心内容索引

### 一、告警管理业务规则
### 二、阈值管理业务规则
### 三、进程监控业务规则
### 四、服务监控业务规则
### 五、业务指标采集业务规则
### 六、IPC通信业务规则
### 七、日志管理业务规则
### 八、性能分析业务规则
### 九、系统监控业务规则
### 十、硬件监控业务规则

---

## 一、告警管理业务规则

### 1.1 告警级别定义

**级别分类**（4级）：
```python
class AlertLevel(Enum):
    INFO = "INFO"              # 信息：一般通知
    WARNING = "WARNING"        # 警告：需要关注
    ERROR = "ERROR"           # 错误：需要处理
    CRITICAL = "CRITICAL"     # 严重：立即处理
```

**级别判定规则**：

| 告警类别 | INFO | WARNING | ERROR | CRITICAL |
|---------|------|---------|-------|----------|
| CPU使用率 | <60% | 60-80% | 80-95% | >95% |
| 内存使用率 | <60% | 60-80% | 80-95% | >95% |
| 磁盘使用率 | <70% | 70-85% | 85-95% | >95% |
| CPU温度 | <60°C | 60-80°C | 80-90°C | >90°C |
| SMART状态 | 正常 | 警告（重分配扇区>0） | - | 故障（预测失败） |
| 网络丢包率 | <1% | 1-5% | 5-10% | >10% |

### 1.2 告警触发规则

#### 1.2.1 触发条件

**阈值触发**：
```python
def check_threshold_alert(metric_name: str, current_value: float) -> Optional[Alert]:
    """检查阈值告警"""
    thresholds = {
        "cpu_percent": {"warning": 60, "error": 80, "critical": 95},
        "memory_percent": {"warning": 60, "error": 80, "critical": 95},
        "disk_percent": {"warning": 70, "error": 85, "critical": 95},
        "cpu_temp": {"warning": 60, "error": 80, "critical": 90}
    }

    if metric_name not in thresholds:
        return None

    config = thresholds[metric_name]
    if current_value >= config["critical"]:
        return Alert(level="CRITICAL", ...)
    elif current_value >= config["error"]:
        return Alert(level="ERROR", ...)
    elif current_value >= config["warning"]:
        return Alert(level="WARNING", ...)

    return None
```

**变化率触发**：
```python
def check_rate_change_alert(metric_name: str, current: float, previous: float) -> Optional[Alert]:
    """检查变化率告警（5分钟内变化>30%触发）"""
    if previous == 0:
        return None

    change_rate = abs(current - previous) / previous
    if change_rate > 0.3:  # 30%
        return Alert(level="WARNING", message=f"{metric_name}变化率异常: {change_rate:.1%}")

    return None
```

**状态触发**：
```python
def check_state_alert(component: str, state: str) -> Optional[Alert]:
    """检查状态告警"""
    critical_states = {
        "smart": ["故障", "FAILING"],
        "service": ["offline", "error"],
        "process": ["crashed", "zombie"]
    }

    if component in critical_states and state in critical_states[component]:
        return Alert(level="CRITICAL", component=component, state=state)

    return None
```

#### 1.2.2 防抖机制

**时间防抖**（避免频繁告警）：
```python
class AlertDebouncer:
    """告警防抖器"""

    def __init__(self, debounce_seconds: int = 60):
        self.debounce_seconds = debounce_seconds
        self._last_alert_time: Dict[str, float] = {}

    def should_alert(self, alert_key: str) -> bool:
        """判断是否应该发送告警"""
        now = time.time()
        last_time = self._last_alert_time.get(alert_key, 0)

        if now - last_time >= self.debounce_seconds:
            self._last_alert_time[alert_key] = now
            return True

        return False
```

**计数防抖**（连续N次才告警）：
```python
class CountDebouncer:
    """计数防抖器"""

    def __init__(self, threshold: int = 3):
        self.threshold = threshold
        self._counts: Dict[str, int] = {}

    def increment(self, alert_key: str) -> bool:
        """增加计数，返回是否达到阈值"""
        self._counts[alert_key] = self._counts.get(alert_key, 0) + 1

        if self._counts[alert_key] >= self.threshold:
            self._counts[alert_key] = 0  # 重置
            return True

        return False
```

### 1.3 告警推送规则

#### 1.3.1 推送渠道

**IPC推送**（主渠道）：
```python
async def send_alert_via_ipc(alert: Alert):
    """通过native_ipc推送告警到主进程"""
    pipe_name = "monitor_alerts"

    alert_data = {
        "type": "alert",
        "level": alert.level,
        "category": alert.category,
        "message": alert.message,
        "details": alert.details,
        "timestamp": alert.timestamp
    }

    try:
        async with await AsyncIPCPipe.connect_as_client(pipe_name, timeout=3.0) as pipe:
            await pipe.write_json(alert_data)
            logger.debug(f"告警已推送: {alert.message}")
    except Exception as e:
        logger.error(f"告警推送失败: {e}")
```

**事件推送**（主进程内）：
```python
def send_alert_via_event(alert: Alert, event_engine: EventEngine):
    """通过事件引擎推送告警"""
    event = Event(EVENT_ALERT_CREATED, alert.to_dict())
    event_engine.put(event)
```

**日志推送**（所有告警）：
```python
def log_alert(alert: Alert):
    """记录告警到日志系统"""
    logger_alert = logging.getLogger("monitor_process.alert")

    log_level = {
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL
    }[alert.level]

    logger_alert.log(log_level, f"[{alert.category}] {alert.message}", extra=alert.details)
```

#### 1.3.2 推送策略

**级别分流**：
```python
def route_alert(alert: Alert):
    """根据级别分流告警"""
    if alert.level == "CRITICAL":
        # 严重告警：IPC + 事件 + 日志 + UI对话框
        send_alert_via_ipc(alert)
        send_alert_via_event(alert, event_engine)
        log_alert(alert)
        # UI对话框由主进程处理

    elif alert.level == "ERROR":
        # 错误告警：IPC + 事件 + 日志
        send_alert_via_ipc(alert)
        send_alert_via_event(alert, event_engine)
        log_alert(alert)

    elif alert.level == "WARNING":
        # 警告告警：IPC + 日志
        send_alert_via_ipc(alert)
        log_alert(alert)

    else:
        # 信息告警：仅日志
        log_alert(alert)
```

**批量推送**（减少IPC调用）：
```python
class AlertBatcher:
    """告警批处理器"""

    def __init__(self, batch_size: int = 10, flush_interval: float = 5.0):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self._batch: List[Alert] = []
        self._last_flush_time = time.time()

    def add(self, alert: Alert):
        """添加告警到批次"""
        self._batch.append(alert)

        # 达到批次大小或超时，立即推送
        if len(self._batch) >= self.batch_size or \
           time.time() - self._last_flush_time >= self.flush_interval:
            self.flush()

    def flush(self):
        """推送批次"""
        if not self._batch:
            return

        # 批量推送
        for alert in self._batch:
            send_alert_via_ipc(alert)

        self._batch.clear()
        self._last_flush_time = time.time()
```

### 1.4 告警聚合规则

**相同告警聚合**：
```python
def aggregate_alerts(alerts: List[Alert], time_window: int = 300) -> List[Alert]:
    """聚合相同告警（5分钟窗口）"""
    aggregated = {}

    for alert in alerts:
        key = f"{alert.category}:{alert.message}"

        if key not in aggregated:
            aggregated[key] = alert
            aggregated[key].count = 1
        else:
            aggregated[key].count += 1
            aggregated[key].last_time = alert.timestamp

    return list(aggregated.values())
```

---

## 二、阈值管理业务规则

### 2.1 阈值配置规则

#### 2.1.1 配置文件结构

**文件位置**：`config/threshold_config.yaml`

**配置格式**：
```yaml
# 系统资源阈值
system_resources:
  cpu:
    warning: 60      # 警告阈值（%）
    error: 80        # 错误阈值（%）
    critical: 95     # 严重阈值（%）

  memory:
    warning: 60
    error: 80
    critical: 95

  disk:
    warning: 70
    error: 85
    critical: 95

# 硬件传感器阈值
hardware_sensors:
  cpu_temperature:
    warning: 60      # °C
    error: 80
    critical: 90

  gpu_temperature:
    warning: 65
    error: 85
    critical: 95

# 网络指标阈值
network:
  packet_loss:
    warning: 1       # %
    error: 5
    critical: 10

  latency:
    warning: 100     # ms
    error: 300
    critical: 1000

# 自适应阈值配置
adaptive:
  enabled: true
  learning_window: 100     # 学习窗口大小（样本数）
  std_multiplier: 2.0      # 标准差乘数
  min_samples: 10          # 最小样本数
```

#### 2.1.2 加载与验证

```python
class ThresholdConfigLoader:
    """阈值配置加载器"""

    @staticmethod
    async def load_config_async(config_file: Path) -> Dict[str, Any]:
        """异步加载配置（使用native_iocp）"""
        from backend.infrastructure.native.native_iocp import compat_aopen

        try:
            async with await compat_aopen(config_file, 'r', encoding='utf-8') as f:
                content = await f.read()
                config = yaml.safe_load(content)

                # 验证配置
                ThresholdConfigLoader.validate_config(config)
                return config

        except Exception as e:
            logger.error(f"加载阈值配置失败: {e}")
            return ThresholdConfigLoader.get_default_config()

    @staticmethod
    def validate_config(config: Dict[str, Any]):
        """验证配置有效性"""
        # 检查必需字段
        required_sections = ["system_resources", "hardware_sensors", "network"]
        for section in required_sections:
            if section not in config:
                raise ValueError(f"缺少必需配置节: {section}")

        # 检查阈值大小关系（warning < error < critical）
        for section in config.values():
            if isinstance(section, dict):
                for metric, thresholds in section.items():
                    if "warning" in thresholds and "error" in thresholds:
                        if thresholds["warning"] >= thresholds["error"]:
                            raise ValueError(f"{metric}: warning阈值必须小于error阈值")

                    if "error" in thresholds and "critical" in thresholds:
                        if thresholds["error"] >= thresholds["critical"]:
                            raise ValueError(f"{metric}: error阈值必须小于critical阈值")
```

### 2.2 自适应阈值算法

#### 2.2.1 统计学习算法

**滚动窗口统计**：
```python
class AdaptiveThresholdManager:
    """自适应阈值管理器（基于统计学习）"""

    def __init__(self, config: Dict[str, Any]):
        self.enabled = config.get("enabled", True)
        self.learning_window = config.get("learning_window", 100)
        self.std_multiplier = config.get("std_multiplier", 2.0)
        self.min_samples = config.get("min_samples", 10)

        # 历史数据（滚动窗口）
        self._history: Dict[str, deque] = {}

    def update_metric(self, metric_name: str, value: float):
        """更新指标数据"""
        if metric_name not in self._history:
            self._history[metric_name] = deque(maxlen=self.learning_window)

        self._history[metric_name].append(value)

    def get_threshold(self, metric_name: str) -> Tuple[float, float]:
        """获取动态阈值（均值，标准差）"""
        if metric_name not in self._history:
            return 0, 0

        samples = list(self._history[metric_name])
        if len(samples) < self.min_samples:
            return 0, 0

        mean = np.mean(samples)
        std = np.std(samples)

        return mean, std

    def check_threshold(self, metric_name: str, value: float) -> ThresholdResult:
        """检查阈值（基于动态学习）"""
        mean, std = self.get_threshold(metric_name)

        if std == 0:
            return ThresholdResult(status="unknown", deviation=0)

        # 计算偏离标准差的倍数
        deviation = (value - mean) / std

        # 判断告警级别
        if deviation > self.std_multiplier * 2:
            status = "critical"
        elif deviation > self.std_multiplier * 1.5:
            status = "error"
        elif deviation > self.std_multiplier:
            status = "warning"
        else:
            status = "normal"

        return ThresholdResult(
            status=status,
            deviation=deviation,
            mean=mean,
            std=std,
            threshold_high=mean + std * self.std_multiplier
        )
```

#### 2.2.2 混合模式（静态+自适应）

```python
class HybridThresholdManager:
    """混合阈值管理器（静态阈值 + 自适应学习）"""

    def __init__(self, static_config: Dict, adaptive_config: Dict):
        self.static_thresholds = static_config
        self.adaptive_manager = AdaptiveThresholdManager(adaptive_config)
        self.use_adaptive = adaptive_config.get("enabled", True)

    def check_threshold(self, metric_name: str, value: float) -> Alert:
        """检查阈值（优先使用静态，辅助自适应）"""
        # 1. 检查静态阈值
        static_result = self._check_static(metric_name, value)

        # 2. 如果启用自适应，进行学习
        if self.use_adaptive:
            self.adaptive_manager.update_metric(metric_name, value)
            adaptive_result = self.adaptive_manager.check_threshold(metric_name, value)

            # 3. 混合判断：静态阈值为主，自适应辅助
            if static_result and adaptive_result.status in ["warning", "error", "critical"]:
                # 两者都告警，取较高级别
                return max(static_result, adaptive_result, key=lambda x: x.level_priority)
            elif static_result:
                return static_result
            elif adaptive_result.status != "normal":
                # 静态未告警，但自适应检测到异常
                return Alert(
                    level="WARNING",
                    message=f"{metric_name}异常波动（自适应检测）",
                    details={"deviation": adaptive_result.deviation}
                )

        return static_result
```

---

## 三、进程监控业务规则

### 3.1 进程信息采集规则

#### 3.1.1 采集字段

**基础字段**：
```python
@dataclass
class ProcessMetrics:
    """进程指标"""
    pid: int
    name: str
    status: str              # running|sleeping|disk-sleep|zombie|stopped
    cpu_percent: float       # CPU使用率（%）
    memory_mb: float         # 内存占用（MB）
    memory_percent: float    # 内存使用率（%）
    num_threads: int         # 线程数
    num_fds: int            # 文件描述符数（Unix）或句柄数（Windows）
    create_time: float       # 创建时间（时间戳）
    cmdline: List[str]       # 命令行参数
```

**扩展字段**：
```python
@dataclass
class ExtendedProcessMetrics(ProcessMetrics):
    """扩展进程指标"""
    io_read_mb_s: float      # I/O读速度（MB/s）
    io_write_mb_s: float     # I/O写速度（MB/s）
    ctx_switches: int        # 上下文切换次数
    open_files: List[str]    # 打开的文件列表
    connections: List[Dict]  # 网络连接列表
```

#### 3.1.2 采集方式

**使用psutil采集**：
```python
class ProcessMonitor:
    """进程监控器"""

    def get_process_metrics(self) -> List[ProcessMetrics]:
        """获取所有进程指标"""
        import psutil

        metrics_list = []
        for proc in psutil.process_iter(['pid', 'name', 'status', 'cpu_percent',
                                          'memory_info', 'num_threads', 'create_time']):
            try:
                info = proc.info
                metrics = ProcessMetrics(
                    pid=info['pid'],
                    name=info['name'],
                    status=info['status'],
                    cpu_percent=info['cpu_percent'],
                    memory_mb=info['memory_info'].rss / 1024 / 1024,
                    memory_percent=proc.memory_percent(),
                    num_threads=info['num_threads'],
                    num_fds=proc.num_handles() if platform.system() == "Windows" else proc.num_fds(),
                    create_time=info['create_time'],
                    cmdline=proc.cmdline()
                )
                metrics_list.append(metrics)

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

        return metrics_list
```

### 3.2 Top进程分析规则

#### 3.2.1 排序规则

**按CPU排序**：
```python
def get_top_cpu_processes(metrics: List[ProcessMetrics], limit: int = 10) -> List[ProcessMetrics]:
    """获取CPU使用率最高的进程"""
    return sorted(metrics, key=lambda x: x.cpu_percent, reverse=True)[:limit]
```

**按内存排序**：
```python
def get_top_memory_processes(metrics: List[ProcessMetrics], limit: int = 10) -> List[ProcessMetrics]:
    """获取内存占用最高的进程"""
    return sorted(metrics, key=lambda x: x.memory_mb, reverse=True)[:limit]
```

**按I/O排序**：
```python
def get_top_io_processes(metrics: List[ExtendedProcessMetrics], limit: int = 10) -> List[ExtendedProcessMetrics]:
    """获取I/O最高的进程"""
    return sorted(metrics, key=lambda x: x.io_read_mb_s + x.io_write_mb_s, reverse=True)[:limit]
```

#### 3.2.2 异常进程检测

**僵尸进程检测**：
```python
def detect_zombie_processes(metrics: List[ProcessMetrics]) -> List[ProcessMetrics]:
    """检测僵尸进程"""
    return [m for m in metrics if m.status == 'zombie']
```

**高资源占用检测**：
```python
def detect_high_resource_processes(metrics: List[ProcessMetrics]) -> List[Alert]:
    """检测高资源占用进程"""
    alerts = []

    for m in metrics:
        if m.cpu_percent > 90:
            alerts.append(Alert(
                level="WARNING",
                message=f"进程CPU占用过高: {m.name} ({m.cpu_percent:.1f}%)"
            ))

        if m.memory_percent > 80:
            alerts.append(Alert(
                level="WARNING",
                message=f"进程内存占用过高: {m.name} ({m.memory_percent:.1f}%)"
            ))

    return alerts
```

---

## 四、服务监控业务规则

### 4.1 服务健康检查规则

#### 4.1.1 检查维度

**调用次数统计**：
```python
class ServiceCallTracker:
    """服务调用追踪器"""

    def __init__(self):
        self._call_counts: Dict[str, int] = {}
        self._success_counts: Dict[str, int] = {}
        self._error_counts: Dict[str, int] = {}

    def record_call(self, service_name: str, success: bool):
        """记录服务调用"""
        self._call_counts[service_name] = self._call_counts.get(service_name, 0) + 1

        if success:
            self._success_counts[service_name] = self._success_counts.get(service_name, 0) + 1
        else:
            self._error_counts[service_name] = self._error_counts.get(service_name, 0) + 1

    def get_success_rate(self, service_name: str) -> float:
        """获取成功率"""
        total = self._call_counts.get(service_name, 0)
        if total == 0:
            return 0.0

        success = self._success_counts.get(service_name, 0)
        return success / total
```

**响应时间监控**：
```python
class ResponseTimeMonitor:
    """响应时间监控器"""

    def __init__(self, window_size: int = 100):
        self._response_times: Dict[str, deque] = {}
        self.window_size = window_size

    def record_response_time(self, service_name: str, response_time_ms: float):
        """记录响应时间"""
        if service_name not in self._response_times:
            self._response_times[service_name] = deque(maxlen=self.window_size)

        self._response_times[service_name].append(response_time_ms)

    def get_avg_response_time(self, service_name: str) -> float:
        """获取平均响应时间"""
        if service_name not in self._response_times:
            return 0.0

        times = list(self._response_times[service_name])
        return sum(times) / len(times) if times else 0.0

    def get_p95_response_time(self, service_name: str) -> float:
        """获取P95响应时间"""
        if service_name not in self._response_times:
            return 0.0

        times = sorted(self._response_times[service_name])
        if not times:
            return 0.0

        index = int(len(times) * 0.95)
        return times[index]
```

#### 4.1.2 健康状态评估

```python
class ServiceHealthChecker:
    """服务健康检查器"""

    def check_service_health(self, service_name: str) -> Dict[str, Any]:
        """检查服务健康状态"""
        # 1. 获取统计数据
        success_rate = self.call_tracker.get_success_rate(service_name)
        avg_response_time = self.response_monitor.get_avg_response_time(service_name)
        p95_response_time = self.response_monitor.get_p95_response_time(service_name)

        # 2. 评估健康状态
        if success_rate < 0.9:
            status = "unhealthy"
            reason = f"成功率过低: {success_rate:.1%}"
        elif avg_response_time > 1000:
            status = "degraded"
            reason = f"响应时间过长: {avg_response_time:.0f}ms"
        elif p95_response_time > 3000:
            status = "degraded"
            reason = f"P95响应时间过长: {p95_response_time:.0f}ms"
        else:
            status = "healthy"
            reason = "正常"

        return {
            "service_name": service_name,
            "status": status,
            "reason": reason,
            "metrics": {
                "success_rate": success_rate,
                "avg_response_time_ms": avg_response_time,
                "p95_response_time_ms": p95_response_time
            }
        }
```

### 4.2 服务重启规则

#### 4.2.1 重启触发条件

**自动重启条件**：
```python
def should_restart_service(health_status: Dict) -> bool:
    """判断是否应该重启服务"""
    # 1. 连续5次检查失败
    if health_status.get("consecutive_failures", 0) >= 5:
        return True

    # 2. 成功率低于50%
    if health_status["metrics"]["success_rate"] < 0.5:
        return True

    # 3. 服务状态为offline或crashed
    if health_status["status"] in ["offline", "crashed"]:
        return True

    return False
```

#### 4.2.2 重启策略

**优雅重启**（带超时）：
```python
async def graceful_restart_service(service_name: str, timeout: int = 30) -> bool:
    """优雅重启服务"""
    try:
        # 1. 停止服务
        logger.info(f"正在停止服务: {service_name}")
        await stop_service(service_name, timeout=timeout // 2)

        # 2. 等待资源释放
        await asyncio.sleep(2)

        # 3. 启动服务
        logger.info(f"正在启动服务: {service_name}")
        await start_service(service_name, timeout=timeout // 2)

        # 4. 验证服务状态
        await asyncio.sleep(1)
        health = await check_service_health(service_name)

        if health["status"] == "healthy":
            logger.info(f"服务重启成功: {service_name}")
            return True
        else:
            logger.error(f"服务重启后状态异常: {service_name}")
            return False

    except Exception as e:
        logger.error(f"服务重启失败: {service_name} - {e}")
        return False
```

**指数退避重启**（失败后等待时间递增）：
```python
class ExponentialBackoffRestarter:
    """指数退避重启器"""

    def __init__(self, initial_delay: float = 1.0, max_delay: float = 60.0, max_retries: int = 5):
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self._retry_counts: Dict[str, int] = {}

    async def restart_with_backoff(self, service_name: str) -> bool:
        """带指数退避的重启"""
        retry_count = self._retry_counts.get(service_name, 0)

        if retry_count >= self.max_retries:
            logger.error(f"服务重启失败次数过多，放弃重启: {service_name}")
            return False

        # 计算等待时间（指数退避）
        delay = min(self.initial_delay * (2 ** retry_count), self.max_delay)
        logger.info(f"等待{delay:.1f}秒后重启服务: {service_name} (第{retry_count + 1}次尝试)")

        await asyncio.sleep(delay)

        # 尝试重启
        success = await graceful_restart_service(service_name)

        if success:
            # 重启成功，重置计数
            self._retry_counts[service_name] = 0
            return True
        else:
            # 重启失败，增加计数
            self._retry_counts[service_name] = retry_count + 1
            return False
```

---

## 五、业务指标采集业务规则

### 5.1 指标定义规则

#### 5.1.1 指标分类

**数据中心指标**：
```python
class DataCenterMetrics:
    """数据中心业务指标"""
    download_concurrency: int       # 下载并发数
    download_progress: float        # 下载进度（%）
    download_speed_mbps: float      # 下载速度（Mbps）
    cache_hit_rate: float          # 缓存命中率（%）
    data_quality_score: float      # 数据质量评分（0-100）
```

**交易网关指标**：
```python
class TradingGatewayMetrics:
    """交易网关业务指标"""
    order_queue_depth: int         # 订单队列深度
    order_response_time_ms: float  # 订单响应时间（ms）
    trade_count: int               # 成交数量
    error_count: int               # 错误数量
    connection_status: str         # 连接状态
```

**策略中心指标**：
```python
class StrategyCenterMetrics:
    """策略中心业务指标"""
    active_strategies: int         # 活跃策略数
    strategy_pnl: float           # 策略盈亏
    signal_count: int             # 信号数量
    execution_latency_ms: float   # 执行延迟（ms）
```

**事件引擎指标**：
```python
class EventEngineMetrics:
    """事件引擎业务指标"""
    event_queue_depth: int              # 事件队列深度
    event_processing_latency_ms: float  # 事件处理延迟（ms）
    events_processed_per_sec: int       # 每秒处理事件数
```

### 5.2 指标采集规则

#### 5.2.1 埋点方式

**主动上报**（业务代码主动调用）：
```python
from backend.infrastructure.system_vnpy.monitor_system import get_business_metrics_collector

# 在业务代码中埋点
collector = get_business_metrics_collector()
collector.record_metric("download_concurrency", 150)
collector.record_metric("cache_hit_rate", 85.5)
```

**被动采集**（监控系统主动查询）：
```python
class BusinessMetricsCollector:
    """业务指标采集器"""

    def collect_from_services(self, service_manager) -> Dict[str, Any]:
        """从各服务采集业务指标"""
        metrics = {}

        # 从数据中心服务采集
        if data_center := service_manager.get_service("data_center"):
            metrics["download_concurrency"] = data_center.get_concurrency()
            metrics["download_progress"] = data_center.get_progress()

        # 从交易网关服务采集
        if gateway := service_manager.get_service("trading_gateway"):
            metrics["order_queue_depth"] = gateway.get_order_queue_depth()
            metrics["connection_status"] = gateway.get_connection_status()

        return metrics
```

#### 5.2.2 采集频率

**实时指标**（1秒）：
- 事件队列深度
- 订单队列深度
- 下载并发数

**快速指标**（5秒）：
- 响应时间
- 成功率
- 错误数

**慢速指标**（30秒）：
- 数据质量评分
- 缓存命中率
- 策略盈亏

### 5.3 指标聚合规则

**时间窗口聚合**：
```python
class MetricsAggregator:
    """指标聚合器"""

    def aggregate_by_window(self, metrics: List[Dict], window_seconds: int = 60) -> Dict:
        """按时间窗口聚合指标"""
        now = time.time()
        cutoff = now - window_seconds

        # 过滤时间窗口内的指标
        windowed = [m for m in metrics if m["timestamp"] >= cutoff]

        # 聚合计算
        aggregated = {}
        for metric_name in set(m["name"] for m in windowed):
            values = [m["value"] for m in windowed if m["name"] == metric_name]

            aggregated[metric_name] = {
                "avg": np.mean(values),
                "min": np.min(values),
                "max": np.max(values),
                "p50": np.percentile(values, 50),
                "p95": np.percentile(values, 95),
                "p99": np.percentile(values, 99)
            }

        return aggregated
```

---

## 六、IPC通信业务规则

### 6.1 IPC管道通信规则

#### 6.1.1 三条管道定义

**告警管道**（alert_pipe）：
```python
# 方向：监控进程 → 主进程
# 模式：客户端模式（监控进程主动推送）
# 数据格式：JSON

{
    "type": "alert",
    "level": "WARNING|ERROR|CRITICAL",
    "category": "system|hardware|smart|business",
    "message": "告警消息",
    "details": {...},
    "timestamp": "2025-11-02T10:00:00"
}
```

**状态管道**（status_pipe）：
```python
# 方向：主进程 → 监控进程
# 模式：服务端模式（监控进程接收）
# 数据格式：JSON

{
    "type": "status_update",
    "service": "data_center|trading_gateway|...",
    "status": "online|offline|degraded",
    "metrics": {...},
    "timestamp": "2025-11-02T10:00:00"
}
```

**查询管道**（query_pipe）：
```python
# 方向：主进程 ↔ 监控进程
# 模式：服务端模式（监控进程响应查询）
# 查询格式：JSON

{
    "action": "get_system|get_hardware|get_smart|test_bandwidth|...",
    "params": {...}
}

# 响应格式：JSON
{
    "status": "success|error",
    "data": {...},
    "error": "错误信息（如有）",
    "timestamp": "2025-11-02T10:00:00"
}
```

#### 6.1.2 管道创建顺序（重要）

**问题**：并发创建多个管道时，服务端必须先调用read()或write()触发ConnectNamedPipe，否则客户端无法连接。

**解决方案**：分批顺序创建
```python
async def initialize_ipc_pipes(self):
    """初始化IPC管道（分批顺序创建）"""
    # 批次1：创建告警管道（客户端模式，监控进程无需等待）
    # 批次2：创建状态管道（服务端模式，需要触发连接）
    # 批次3：创建查询管道（服务端模式，需要触发连接）

    # 创建状态管道（服务端）
    self.status_pipe = await AsyncIPCPipe.create_as_server("monitor_status")

    # 触发连接（关键步骤）
    asyncio.create_task(self._handle_status_pipe())

    # 等待一小段时间，确保服务端就绪
    await asyncio.sleep(0.1)

    # 创建查询管道（服务端）
    self.query_pipe = await AsyncIPCPipe.create_as_server("monitor_query")
    asyncio.create_task(self._handle_query_pipe())

    await asyncio.sleep(0.1)

    logger.info("IPC管道初始化完成")
```

### 6.2 查询协议规则

#### 6.2.1 查询动作列表

**基础查询**：
- `get_system`：获取系统指标
- `get_hardware`：获取硬件传感器
- `get_smart`：获取SMART数据
- `get_bottleneck`：获取瓶颈分析
- `get_scenario`：获取场景分析
- `get_all`：获取所有数据

**测速查询**：
- `test_ping`：测试网络延迟（1-3秒）
- `test_bandwidth_full`：完整带宽测试（10-30秒）
- `get_bandwidth`：获取缓存的带宽信息

#### 6.2.2 超时处理

**查询超时**：5秒
```python
async def query_monitor_data(self, action: str, params: Dict = None) -> Optional[Dict]:
    """查询监控数据"""
    pipe_name = "monitor_query"

    query = {
        "action": action,
        "params": params or {}
    }

    try:
        async with await AsyncIPCPipe.connect_as_client(pipe_name, timeout=5.0) as pipe:
            # 发送查询
            await pipe.write_json(query)

            # 接收响应（超时5秒）
            response = await asyncio.wait_for(pipe.read_json(), timeout=5.0)

            if response["status"] == "success":
                return response["data"]
            else:
                logger.error(f"查询失败: {response.get('error')}")
                return None

    except asyncio.TimeoutError:
        logger.error(f"查询超时: {action}")
        return None
    except Exception as e:
        logger.error(f"查询异常: {e}")
        return None
```

### 6.3 错误处理与重连

**重试机制**：
```python
async def send_with_retry(pipe_name: str, data: Dict, max_retries: int = 3) -> bool:
    """带重试的发送"""
    for attempt in range(max_retries):
        try:
            async with await AsyncIPCPipe.connect_as_client(pipe_name, timeout=3.0) as pipe:
                await pipe.write_json(data)
                return True

        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(0.5 * (2 ** attempt))  # 指数退避
                logger.warning(f"IPC发送失败，重试{attempt + 1}/{max_retries}: {e}")
            else:
                logger.error(f"IPC发送失败，已达最大重试次数: {e}")
                return False
```

---

## 七、日志管理业务规则

### 7.0 统一日志系统模块

**模块位置**：`backend.infrastructure.system_vnpy.unified_log_system`

**说明**：
- 统一日志系统作为 `system_vnpy` 模块的核心组件
- 所有日志功能通过 `unified_log_system.py` 提供
- 通过 `get_logging_hub()` 函数获取 LoggingHub 实例
- 支持四层路由、AI日志、进度节流等完整功能

**导入方式**：
```python
from backend.infrastructure.system_vnpy.unified_log_system import (
    get_logging_hub,
    ai_log_process,
    LogType,
    UnifiedLogRecord,
)
```

### 7.1 日志分类规则

**日志类型**（根据 `backend.infrastructure.system_vnpy.unified_log_system` 模块）：
```python
class LogType(Enum):
    SYSTEM = "SYSTEM"              # 系统日志
    PROGRESS = "PROGRESS"          # 进度日志
    NOTIFICATION = "NOTIFICATION"  # 通知日志
    ALERT = "ALERT"               # 告警日志
    DEBUG = "DEBUG"               # 调试日志
```

**模块标识**：
- `system_manager`：系统管理模块

**场景标识**：
- `monitoring`：监控场景
- `bandwidth_test`：带宽测试场景

### 7.2 日志路由规则

**三层路由**（基于 `backend.infrastructure.system_vnpy.unified_log_system` 模块）：
```
Layer 3: 模块规则 (module_system_manager)
    ↓ 未匹配
Layer 2: 阶段规则 (stage_running)
    ↓ 未匹配
Layer 1: 全局规则 (global_defaults)
```

**输出目标**：
- `console`：控制台输出（INFO及以上）
- `file`：日志文件（DEBUG及以上）
- `event`：事件引擎（WARNING及以上）
- `ipc_alerts`：IPC告警推送（ERROR及以上）

### 7.3 日志规范

**关键资源等待日志**：
```python
# 等待服务器池就绪示例
timeout = 30
elapsed = 0
while not server_pool.is_ready():
    if elapsed == 0:
        logger.info(f"等待服务器池就绪（当前状态：{server_pool.get_status()}）")
    elif elapsed % 5 == 0:
        logger.info(f"仍在等待服务器池就绪... 已等待{elapsed}秒（当前状态：{server_pool.get_status()}）")

    await asyncio.sleep(1)
    elapsed += 1

    if elapsed >= timeout:
        logger.error(f"等待服务器池就绪超时（{timeout}秒）")
        break
```

---

## 八、性能分析业务规则

### 8.1 性能指标计算规则

**监控开销计算**：
```python
def calculate_monitoring_overhead() -> Dict[str, float]:
    """计算监控开销"""
    import psutil

    # 获取当前进程
    current_process = psutil.Process()

    # 计算CPU开销
    cpu_percent = current_process.cpu_percent(interval=0.1)

    # 计算内存开销
    memory_mb = current_process.memory_info().rss / 1024 / 1024

    # 计算I/O开销
    io_counters = current_process.io_counters()

    return {
        "cpu_percent": cpu_percent,
        "memory_mb": memory_mb,
        "io_read_mb": io_counters.read_bytes / 1024 / 1024,
        "io_write_mb": io_counters.write_bytes / 1024 / 1024
    }
```

**IPC延迟测试**：
```python
async def test_ipc_latency() -> float:
    """测试IPC通信延迟"""
    iterations = 100
    total_time = 0

    for _ in range(iterations):
        start = time.perf_counter()

        # 发送查询
        result = await query_monitor_data("get_system")

        elapsed = time.perf_counter() - start
        total_time += elapsed

    avg_latency_ms = (total_time / iterations) * 1000
    return avg_latency_ms
```

### 8.2 性能报告生成规则

**报告格式**：
```python
{
    "monitoring_overhead": {
        "cpu_percent": 1.5,
        "memory_mb": 85,
        "target_cpu": 2.0,     # 目标：<2%
        "target_memory": 100,  # 目标：<100MB
        "cpu_ok": true,
        "memory_ok": true
    },
    "ipc_performance": {
        "avg_latency_ms": 1.2,
        "p95_latency_ms": 2.5,
        "target_latency": 2.0,  # 目标：<2ms
        "latency_ok": true
    },
    "io_performance": {
        "config_load_ms": 15,
        "cache_write_ms": 8,
        "log_write_ms": 5,
        "target_config_load": 20,
        "target_cache_write": 10,
        "target_log_write": 10,
        "all_ok": true
    }
}
```

---

---

## 九、系统监控业务规则

### 9.1 系统指标采集规则

#### 9.1.1 CPU监控规则

**采集指标**：
- `cpu_percent`：CPU总使用率（%）
- `cpu_per_core`：每个核心使用率列表
- `cpu_freq`：CPU频率（MHz）
- `context_switches`：上下文切换次数（累计）
- `interrupts`：中断次数（累计）

**采集实现**：
```python
import psutil

def collect_cpu_metrics() -> Dict[str, Any]:
    """采集CPU指标"""
    # CPU使用率（0.1秒采样，避免阻塞）
    cpu_percent = psutil.cpu_percent(interval=0.1)

    # 每核心使用率
    cpu_per_core = psutil.cpu_percent(interval=0.1, percpu=True)

    # CPU频率
    freq = psutil.cpu_freq()
    cpu_freq = freq.current if freq else 0

    # CPU统计
    stats = psutil.cpu_stats()

    return {
        "cpu_percent": cpu_percent,
        "cpu_per_core": cpu_per_core,
        "cpu_freq": cpu_freq,
        "context_switches": stats.ctx_switches,
        "interrupts": stats.interrupts
    }
```

**采集频率**：
- 标准：1秒
- 高压力：2秒
- 严重压力：5秒

**变化率计算**（用于告警）：
```python
def calculate_cpu_change_rate(current: float, previous: float, interval: float) -> float:
    """计算CPU使用率变化率（%/秒）"""
    if interval == 0:
        return 0
    return (current - previous) / interval
```

#### 9.1.2 内存监控规则

**采集指标**：
- `memory_percent`：内存使用率（%）
- `memory_total_mb`：总内存（MB）
- `memory_available_mb`：可用内存（MB）
- `memory_used_mb`：已用内存（MB）
- `swap_percent`：交换空间使用率（%）
- `swap_total_mb`：总交换空间（MB）

**采集实现**：
```python
def collect_memory_metrics() -> Dict[str, Any]:
    """采集内存指标"""
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()

    return {
        "memory_percent": mem.percent,
        "memory_total_mb": mem.total / 1024 / 1024,
        "memory_available_mb": mem.available / 1024 / 1024,
        "memory_used_mb": mem.used / 1024 / 1024,
        "swap_percent": swap.percent,
        "swap_total_mb": swap.total / 1024 / 1024
    }
```

**内存泄漏检测**：
```python
class MemoryLeakDetector:
    """内存泄漏检测器"""

    def __init__(self, window_size: int = 60):
        self.window_size = window_size
        self._history = deque(maxlen=window_size)

    def check_leak(self, current_mb: float) -> Optional[Alert]:
        """检测内存泄漏（线性增长）"""
        self._history.append(current_mb)

        if len(self._history) < self.window_size:
            return None

        # 线性回归检测趋势
        x = np.arange(len(self._history))
        y = np.array(self._history)
        slope, _ = np.polyfit(x, y, 1)

        # 如果斜率>0.5（每分钟增长0.5MB），可能存在内存泄漏
        if slope > 0.5:
            return Alert(
                level="WARNING",
                message=f"检测到可能的内存泄漏（增长速率：{slope:.2f}MB/分钟）"
            )

        return None
```

#### 9.1.3 磁盘监控规则

**采集指标**：
- `disk_usage`：各分区使用率字典 {分区: 使用率%}
- `disk_io_read_bytes_s`：磁盘读速度（字节/秒）
- `disk_io_write_bytes_s`：磁盘写速度（字节/秒）
- `disk_io_read_count`：磁盘读次数（累计）
- `disk_io_write_count`：磁盘写次数（累计）
- `disk_queue_depth`：磁盘队列深度（估算）

**采集实现**：
```python
class DiskMonitor:
    """磁盘监控器"""

    def __init__(self):
        self._last_io_counters = None
        self._last_collect_time = None

    def collect_disk_metrics(self) -> Dict[str, Any]:
        """采集磁盘指标"""
        # 1. 磁盘使用率
        disk_usage = {}
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disk_usage[partition.device] = {
                    "mountpoint": partition.mountpoint,
                    "percent": usage.percent,
                    "total_gb": usage.total / 1024 / 1024 / 1024,
                    "used_gb": usage.used / 1024 / 1024 / 1024
                }
            except PermissionError:
                pass

        # 2. 磁盘I/O
        current_io = psutil.disk_io_counters()
        current_time = time.time()

        if self._last_io_counters:
            elapsed = current_time - self._last_collect_time
            read_bytes_s = (current_io.read_bytes - self._last_io_counters.read_bytes) / elapsed
            write_bytes_s = (current_io.write_bytes - self._last_io_counters.write_bytes) / elapsed
        else:
            read_bytes_s = 0
            write_bytes_s = 0

        self._last_io_counters = current_io
        self._last_collect_time = current_time

        return {
            "disk_usage": disk_usage,
            "disk_io_read_mb_s": read_bytes_s / 1024 / 1024,
            "disk_io_write_mb_s": write_bytes_s / 1024 / 1024,
            "disk_io_read_count": current_io.read_count,
            "disk_io_write_count": current_io.write_count
        }
```

**磁盘空间告警规则**：
```python
def check_disk_space_alerts(disk_usage: Dict) -> List[Alert]:
    """检查磁盘空间告警"""
    alerts = []

    for device, info in disk_usage.items():
        percent = info["percent"]

        if percent >= 95:
            alerts.append(Alert(
                level="CRITICAL",
                message=f"磁盘空间严重不足: {device} ({percent:.1f}%)"
            ))
        elif percent >= 85:
            alerts.append(Alert(
                level="ERROR",
                message=f"磁盘空间不足: {device} ({percent:.1f}%)"
            ))
        elif percent >= 70:
            alerts.append(Alert(
                level="WARNING",
                message=f"磁盘空间偏低: {device} ({percent:.1f}%)"
            ))

    return alerts
```

#### 9.1.4 网络监控规则

**采集指标**：
- `network_sent_bytes_s`：发送速度（字节/秒）
- `network_recv_bytes_s`：接收速度（字节/秒）
- `network_sent_packets`：发送包数（累计）
- `network_recv_packets`：接收包数（累计）
- `network_err_in`：接收错误数（累计）
- `network_err_out`：发送错误数（累计）
- `network_drop_in`：接收丢包数（累计）
- `network_drop_out`：发送丢包数（累计）

**采集实现**：
```python
class NetworkMonitor:
    """网络监控器"""

    def __init__(self):
        self._last_net_counters = None
        self._last_collect_time = None

    def collect_network_metrics(self) -> Dict[str, Any]:
        """采集网络指标"""
        current_net = psutil.net_io_counters()
        current_time = time.time()

        if self._last_net_counters:
            elapsed = current_time - self._last_collect_time
            sent_bytes_s = (current_net.bytes_sent - self._last_net_counters.bytes_sent) / elapsed
            recv_bytes_s = (current_net.bytes_recv - self._last_net_counters.bytes_recv) / elapsed
        else:
            sent_bytes_s = 0
            recv_bytes_s = 0

        self._last_net_counters = current_net
        self._last_collect_time = current_time

        return {
            "network_sent_mb_s": sent_bytes_s / 1024 / 1024,
            "network_recv_mb_s": recv_bytes_s / 1024 / 1024,
            "network_sent_packets": current_net.packets_sent,
            "network_recv_packets": current_net.packets_recv,
            "network_err_in": current_net.errin,
            "network_err_out": current_net.errout,
            "network_drop_in": current_net.dropin,
            "network_drop_out": current_net.dropout
        }
```

**丢包率计算**：
```python
def calculate_packet_loss_rate(metrics: Dict) -> float:
    """计算丢包率（%）"""
    total_packets = metrics["network_sent_packets"] + metrics["network_recv_packets"]
    if total_packets == 0:
        return 0

    total_drops = metrics["network_drop_in"] + metrics["network_drop_out"]
    loss_rate = (total_drops / total_packets) * 100

    return loss_rate
```

### 9.2 网络测试池规则

#### 9.2.1 延迟测试池（LatencyMonitor）

**配置文件**：`backend/infrastructure/system_vnpy/config/ping_servers.yaml`

**服务器来源**：门户网站、视频网站、体育网站等（约70+个）

**示例服务器**：百度、网易、腾讯、优酷、B站、政府网站等

**用途**：日常网络延迟监控

**测试频率**：每10秒自动测试一次

**测试方式**：GET请求 + 完整浏览器头部模拟真实用户访问

**实现逻辑**：
- 启动时并发测试所有服务器连通性，生成可用服务器表缓存
- 之后每10秒自动测试一次延迟，随机选择服务器
- 使用GET请求模拟真实浏览器访问，添加完整的User-Agent等头部信息

#### 9.2.2 带宽测试池（BandwidthMonitor）

**配置文件**：`backend/infrastructure/system_vnpy/config/speedtest_servers.yaml`

**服务器来源**：仅国内镜像站（约15个）

**示例服务器**：阿里云、腾讯云、华为云、清华、中科大等镜像站

**用途**：完整带宽测试（延迟 + 下载速度）

**测试频率**：仅在手动触发时执行（预计30-60秒）

**测试方式**：HEAD请求测延迟 + 流式下载测带宽

**实现逻辑**：
- 从服务器池中随机选择一个服务器
- 先执行延迟测试（HEAD请求）
- 延迟测试通过后，执行下载速度测试（流式下载，Range请求前10MB）
- 支持重试机制（最多3次）
- 仅使用国内镜像站，避免国际带宽测试受限于网络环境

### 9.3 系统信息采集规则

**采集时机**：
- 监控进程启动时采集一次
- 缓存结果，定期更新（如每小时）

**采集内容**：
```python
def get_system_info() -> Dict[str, Any]:
    """获取系统信息"""
    import platform

    return {
        # 操作系统
        "os_name": platform.system(),
        "os_version": platform.version(),
        "os_release": platform.release(),
        "os_arch": platform.machine(),

        # 启动时间
        "boot_time": datetime.fromtimestamp(psutil.boot_time()).isoformat(),
        "uptime_seconds": int(time.time() - psutil.boot_time()),

        # CPU信息
        "cpu_model": platform.processor(),
        "cpu_cores": psutil.cpu_count(logical=False),
        "cpu_threads": psutil.cpu_count(logical=True),
        "cpu_freq_max": psutil.cpu_freq().max if psutil.cpu_freq() else 0,

        # 内存信息
        "memory_total_mb": psutil.virtual_memory().total / 1024 / 1024,

        # 磁盘信息
        "disk_partitions": [
            {
                "device": p.device,
                "mountpoint": p.mountpoint,
                "fstype": p.fstype
            }
            for p in psutil.disk_partitions()
        ],

        # 网络信息
        "hostname": platform.node(),
        "python_version": platform.python_version()
    }
```

---

## 十、硬件监控业务规则

### 10.1 硬件传感器采集规则

#### 10.1.1 LibreHardwareMonitor集成规则

**优先级**：高（精度高，支持全面）

**依赖检查**：
```python
def check_libre_hardware_monitor() -> bool:
    """检查LibreHardwareMonitor是否可用"""
    try:
        import clr
        # 尝试加载LibreHardwareMonitor DLL
        # 返回True表示可用
        return True
    except Exception:
        return False
```

**传感器类型**：
- Temperature（温度）
- Power（功耗）
- Voltage（电压）
- Fan（风扇转速）
- Clock（频率）
- Load（负载）

**采集实现**（伪代码）：
```python
def collect_libre_sensors() -> Dict[str, List[SensorData]]:
    """从LibreHardwareMonitor采集传感器数据"""
    import clr
    # 加载LibreHardwareMonitor
    # ...

    sensors_by_type = {
        "temperature": [],
        "power": [],
        "voltage": [],
        "fan": [],
        "clock": [],
        "load": []
    }

    # 遍历所有硬件
    for hardware in computer.Hardware:
        hardware.Update()

        # 遍历所有传感器
        for sensor in hardware.Sensors:
            sensor_data = SensorData(
                name=sensor.Name,
                value=sensor.Value,
                unit=get_sensor_unit(sensor.SensorType),
                sensor_type=sensor.SensorType.ToString(),
                hardware_name=hardware.Name
            )

            type_key = sensor.SensorType.ToString().lower()
            if type_key in sensors_by_type:
                sensors_by_type[type_key].append(sensor_data)

    return sensors_by_type
```

#### 10.1.2 WMI降级方案

**优先级**：低（作为LibreHardwareMonitor不可用时的降级方案）

**支持的传感器**（有限）：
- CPU温度（部分CPU支持）
- 风扇转速（部分主板支持）

**采集实现**：
```python
def collect_wmi_sensors() -> Dict[str, List[SensorData]]:
    """从WMI采集传感器数据（降级方案）"""
    import wmi

    sensors_by_type = {
        "temperature": [],
        "fan": []
    }

    wmi_client = wmi.WMI(namespace="root\\OpenHardwareMonitor")

    # 尝试获取温度
    try:
        for sensor in wmi_client.Sensor():
            if "Temperature" in sensor.SensorType:
                sensors_by_type["temperature"].append(
                    SensorData(
                        name=sensor.Name,
                        value=float(sensor.Value),
                        unit="°C",
                        sensor_type="temperature",
                        hardware_name=sensor.Parent
                    )
                )
            elif "Fan" in sensor.SensorType:
                sensors_by_type["fan"].append(
                    SensorData(
                        name=sensor.Name,
                        value=float(sensor.Value),
                        unit="RPM",
                        sensor_type="fan",
                        hardware_name=sensor.Parent
                    )
                )
    except Exception as e:
        logger.warning(f"WMI传感器采集失败: {e}")

    return sensors_by_type
```

### 10.2 SMART硬盘监控规则

#### 10.2.1 WMI SMART数据采集规则

**数据源**：
- `Win32_DiskDrive`：硬盘基本信息
- `MSStorageDriver_FailurePredictStatus`：故障预测状态
- `MSStorageDriver_FailurePredictData`：SMART属性数据

**采集实现**：
```python
class WMISmartMonitor:
    """WMI SMART监控器"""

    def get_smart_data(self) -> Dict[str, DiskSmartData]:
        """获取所有硬盘的SMART数据"""
        import wmi

        # COM线程安全：每个线程独立的WMI实例
        wmi_client = wmi.WMI(namespace="root\\wmi")

        # 1. 获取硬盘基本信息
        disks_info = self._get_disks_basic_info()

        # 2. 获取故障预测状态
        predict_status = self._get_failure_predict_status(wmi_client)

        # 3. 获取SMART属性
        smart_attributes = self._get_failure_predict_data(wmi_client)

        # 4. 组合数据
        result = {}
        for disk_name, info in disks_info.items():
            # 获取SMART属性
            attributes = smart_attributes.get(disk_name, [])

            # 提取关键属性
            temperature = self._get_attribute_value(attributes, 194)  # ID 194: 温度
            power_on_hours = self._get_attribute_value(attributes, 9)  # ID 9: 通电时间
            reallocated = self._get_attribute_value(attributes, 5)  # ID 5: 重分配扇区
            pending = self._get_attribute_value(attributes, 197)  # ID 197: 待处理扇区

            # 评估健康状态
            assessment = self._assess_health(attributes, predict_status.get(disk_name, {}))

            result[disk_name] = DiskSmartData(
                disk_name=disk_name,
                model=info.get("model", "Unknown"),
                serial=info.get("serial", "Unknown"),
                disk_type=self._detect_disk_type(info.get("model", "")),
                assessment=assessment,
                attributes=attributes,
                temperature=temperature,
                power_on_hours=power_on_hours,
                reallocated_sectors=reallocated,
                pending_sectors=pending
            )

        return result
```

#### 10.2.2 SMART健康评估算法

**评估逻辑**：
```python
def _assess_health(
    self,
    attributes: List[SmartAttribute],
    predict_status: Dict
) -> str:
    """评估硬盘健康状态"""
    # 1. 检查WMI故障预测
    if predict_status.get("PredictFailure", False):
        return "故障"

    # 2. 检查关键SMART属性
    reallocated = self._get_attribute_raw_value(attributes, 5)
    pending = self._get_attribute_raw_value(attributes, 197)
    uncorrectable = self._get_attribute_raw_value(attributes, 187)

    # 3. 故障判定
    if reallocated and reallocated > 100:
        return "故障"
    if pending and pending > 50:
        return "故障"
    if uncorrectable and uncorrectable > 0:
        return "故障"

    # 4. 警告判定
    if reallocated and reallocated > 0:
        return "警告"
    if pending and pending > 0:
        return "警告"

    # 5. 正常
    return "正常"
```

#### 10.2.3 SMART告警规则

**告警触发条件**：

| 条件 | 告警级别 | 消息 |
|-----|---------|------|
| assessment = "故障" | CRITICAL | 硬盘即将故障，建议立即备份数据 |
| assessment = "警告" | WARNING | 硬盘存在重分配扇区或待处理扇区 |
| temperature > 60°C | WARNING | 硬盘温度过高 |
| temperature > 70°C | ERROR | 硬盘温度严重过高 |

**告警实现**：
```python
def process_smart_alerts(smart_data: Dict[str, DiskSmartData]):
    """处理SMART告警"""
    for disk_name, data in smart_data.items():
        # 1. 健康状态告警
        if data.assessment == "故障":
            logger_alert.critical(
                f"[SMART] 硬盘即将故障: {disk_name} ({data.model})",
                extra={
                    "reallocated_sectors": data.reallocated_sectors,
                    "pending_sectors": data.pending_sectors
                }
            )
        elif data.assessment == "警告":
            logger_alert.warning(
                f"[SMART] 硬盘健康警告: {disk_name} ({data.model})",
                extra={
                    "reallocated_sectors": data.reallocated_sectors,
                    "pending_sectors": data.pending_sectors
                }
            )

        # 2. 温度告警
        if data.temperature:
            if data.temperature > 70:
                logger_alert.error(
                    f"[SMART] 硬盘温度严重过高: {disk_name} ({data.temperature}°C)"
                )
            elif data.temperature > 60:
                logger_alert.warning(
                    f"[SMART] 硬盘温度过高: {disk_name} ({data.temperature}°C)"
                )
```

### 10.3 硬件监控采集频率规则

**标准频率**：
- 温度传感器：5秒
- 功耗传感器：5秒
- 风扇转速：5秒
- SMART数据：60秒

**降级频率**（高压力）：
- 温度传感器：10秒
- 功耗传感器：10秒
- 风扇转速：10秒
- SMART数据：120秒

**降级频率**（严重压力）：
- 温度传感器：20秒
- 功耗传感器：20秒
- 风扇转速：20秒
- SMART数据：300秒

---

### 9.4 监控频率管理规则

#### 9.4.1 固定频率策略（默认）

**设计原则**：
- 系统监控模块是底层基础设施，必须提供稳定可靠的监控数据
- **禁止**因为系统压力而降低监控频率（会导致监控盲区）
- 采集频率固定或用户可配置，但**不动态调整**
- 作为**数据提供者**，为LoadBalancer等模块提供稳定监控数据

**默认频率配置**：
```yaml
intervals:
  system_metrics: 1      # CPU、内存、磁盘、网络
  process_metrics: 2     # 进程监控
  hardware_sensors: 5    # 温度、风扇、功耗
  smart_data: 60        # SMART硬盘健康
  alert_evaluation: 3    # 告警评估
```

**性能保证**：
- CPU占用 < 2%
- 内存占用 < 100MB
- 磁盘I/O < 5MB/s

**实现示例**：
```python
class MonitoringProcessV2:
    """监控进程V2（固定频率模式）"""

    def __init__(self, config: Dict[str, Any]):
        # 从配置文件加载固定频率
        self.intervals = config["monitoring"]["intervals"]

        # 固定间隔，不动态调整
        self.system_interval = self.intervals["system_metrics"]      # 1秒
        self.process_interval = self.intervals["process_metrics"]    # 2秒
        self.hardware_interval = self.intervals["hardware_sensors"]  # 5秒
        self.smart_interval = self.intervals["smart_data"]          # 60秒
        self.alert_interval = self.intervals["alert_evaluation"]    # 3秒

    async def start(self):
        """启动监控进程（固定频率）"""
        # 启动4个并发任务，各自独立的固定间隔
        tasks = [
            asyncio.create_task(self._monitor_system_task()),      # 1秒一次
            asyncio.create_task(self._monitor_process_task()),     # 2秒一次
            asyncio.create_task(self._monitor_hardware_task()),    # 5秒一次
            asyncio.create_task(self._evaluate_alerts_task())      # 3秒一次
        ]

        await asyncio.gather(*tasks)

    async def _monitor_system_task(self):
        """系统监控任务（固定1秒间隔）"""
        while True:
            try:
                # 采集系统指标
                metrics = self.system_monitor.get_system_metrics()

                # 发布事件（供智能负载均衡模块消费）
                self.event_engine.put(Event(EVENT_SYSTEM_METRICS, metrics))

                # 固定间隔等待
                await asyncio.sleep(self.system_interval)

            except Exception as e:
                logger.error(f"系统监控任务异常: {e}")
                await asyncio.sleep(self.system_interval)
```

#### 9.4.2 用户配置模式

**配置文件**：`config/system_config.yaml`

**预设模式**：

| 模式 | system_metrics | hardware_sensors | 说明 |
|-----|----------------|------------------|------|
| 高频 | 1秒 | 5秒 | 默认模式，精确监控 |
| 标准 | 2秒 | 10秒 | 平衡模式 |
| 省资源 | 5秒 | 20秒 | 降低监控开销 |

**配置热更新**：
```python
class MonitoringProcessV2:
    """监控进程V2（支持配置热更新）"""

    async def reload_config(self):
        """重新加载配置（通过IPC接收主进程通知）"""
        new_config = await self.config_manager.load_config_async()

        # 更新采集间隔
        old_intervals = self.intervals.copy()
        self.intervals = new_config["monitoring"]["intervals"]

        # 记录配置变更
        logger.info(f"监控配置已更新: {old_intervals} -> {self.intervals}")

        # 注意：任务会在下一个周期使用新间隔，无需重启
```

**用户配置界面**（UI层提供）：
- 允许用户在设置界面调整采集频率
- 通过IPC通知监控进程重新加载配置
- 提供预设模式：高频（1秒）、标准（2秒）、省资源（5秒）

#### 9.4.3 禁止的策略

❌ **禁止根据系统压力动态调整监控频率**：

**错误做法**：
```python
# ❌ 错误：根据系统压力调整监控频率
if cpu_percent > 80:
    self.system_interval = 5  # 降低监控频率
```

**问题**：
1. 系统压力大时降低监控频率 → 导致监控数据不准确
2. 智能负载均衡模块依赖监控数据 → 错误的监控数据导致错误的决策
3. 形成负反馈循环 → 系统性能进一步下降

✅ **正确做法**：
```python
# ✅ 正确：监控频率固定，智能负载均衡根据监控数据调整业务并发配置

# 监控进程：固定1秒采集
 async def _monitor_system_task(self):
    while True:
        metrics = self.system_monitor.get_system_metrics()
        self.event_engine.put(Event(EVENT_SYSTEM_METRICS, metrics))
        await asyncio.sleep(1)  # 固定1秒

# LoadBalancer：根据监控数据调整业务并发
class LoadBalancer:
    def get_optimal_config(self, task: Task) -> Dict:
        pressure_score = self._calculate_pressure_score(self._latest_system_metrics)

        if pressure_score < 40:
            return {"max_workers": 4, "max_coroutines": 500}  # 降低业务并发
        else:
            return {"max_workers": 16, "max_coroutines": 2000}  # 提高业务并发
```

#### 9.4.4 与智能负载均衡的正确关系

**数据流向**：
```
监控进程 (数据提供者)
    ↓
    固定1秒采集系统指标
    ↓
    EVENT_SYSTEM_METRICS
    ↓
智能负载均衡 (数据消费者)
    ↓
    木桶理论评估系统压力
    ↓
    动态调整业务并发配置 (不是监控频率!)
    ↓
    DataCenter、策略中心等业务模块
```

**关键区别**：
- 监控进程：固定频率采集，不受系统压力影响
- 智能负载均衡：消费监控数据，调整**业务模块**的并发配置
- 业务模块：根据LoadBalancer提供的配置调整自己的并发数
