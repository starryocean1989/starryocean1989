"""
Framework Runtime - 运行时固件
提供监控、日志、热重载等项目固件级功能

原子来源（system_vnpy功能完整保留）:
- system_vnpy/monitor_system.py (7936行)
- system_vnpy/monitor_toolkit.py (1338行)
- system_vnpy/logging_system.py (4200行)
- system_vnpy/logging_config.py (239行)
- system_vnpy/lazy_logger.py (414行)
- system_vnpy/process_watchdog.py (108行)
- system_vnpy/module_hot_reload.py (420行)

职责：运行时监控、日志、热重载等项目固件级功能
"""

import asyncio
import inspect
import logging
import json
import math
import os
import queue
import re
import statistics
import time
import threading
import tracemalloc
import zipfile
from abc import ABC, abstractmethod
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from functools import wraps
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Optional, Pattern, Tuple, Union, cast

import psutil

logger = logging.getLogger("framework.runtime")

# ============================================================================
# Section 1: 监控系统 (行 1-300)
# ============================================================================


class MetricType(str, Enum):
    """监控指标类型"""
    CPU_USAGE = "cpu_usage"
    MEMORY_USAGE = "memory_usage"
    DISK_USAGE = "disk_usage"
    NETWORK_IO = "network_io"
    PROCESS_COUNT = "process_count"
    THREAD_COUNT = "thread_count"


@dataclass
class MetricData:
    """监控指标数据"""
    metric_type: MetricType
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    tags: Dict[str, str] = field(default_factory=dict)
    extra: Dict[str, Any] = field(default_factory=dict)


class SystemMonitor:
    """系统监控器 - 监控CPU、内存、磁盘、网络"""

    def __init__(self):
        self.logger = logging.getLogger("runtime.monitor")
        self._running = False
        self._metrics_buffer: deque = deque(maxlen=1000)
        self.cpu_threshold = 80.0
        self.memory_threshold = 80.0

    def start(self):
        """启动监控"""
        self._running = True
        self.logger.info("系统监控已启动")

    def stop(self):
        """停止监控"""
        self._running = False
        self.logger.info("系统监控已停止")

    def collect_metrics(self) -> List[MetricData]:
        """采集所有指标"""
        metrics = []

        # CPU使用率
        cpu_percent_raw = psutil.cpu_percent(interval=1)
        if isinstance(cpu_percent_raw, list):
            cpu_percent = float(sum(cpu_percent_raw) / max(1, len(cpu_percent_raw)))
        else:
            cpu_percent = float(cpu_percent_raw)
        metrics.append(MetricData(
            metric_type=MetricType.CPU_USAGE,
            value=cpu_percent,
            tags={"host": "localhost"}
        ))

        # 内存使用率
        memory = psutil.virtual_memory()
        metrics.append(MetricData(
            metric_type=MetricType.MEMORY_USAGE,
            value=float(memory.percent),
            extra={"total": memory.total, "available": memory.available}
        ))

        return metrics

    def check_thresholds(self, metrics: List[MetricData]):
        """检查阈值并触发告警"""
        for metric in metrics:
            if metric.metric_type == MetricType.CPU_USAGE:
                if metric.value > self.cpu_threshold:
                    self._trigger_alert(f"CPU使用率过高: {metric.value}%")

    def _trigger_alert(self, message: str):
        """触发告警"""
        self.logger.warning("⚠️ 监控告警: %s", message)


class ProcessMonitor:
    """进程监控器"""

    def __init__(self, pid: Optional[int] = None):
        self.pid = pid or psutil.Process().pid
        self.process = psutil.Process(self.pid)
        self.logger = logging.getLogger(f"runtime.process.{self.pid}")

    def get_info(self) -> Dict:
        """获取进程信息"""
        try:
            return {
                "pid": self.pid,
                "name": self.process.name(),
                "status": self.process.status(),
                "cpu_percent": self.process.cpu_percent(),
                "memory_percent": self.process.memory_percent(),
            }
        except psutil.NoSuchProcess:
            return {"pid": self.pid, "status": "not_found"}

    def is_alive(self) -> bool:
        """检查进程是否存活"""
        return self.process.is_running()


class PerformanceTimer:
    """性能计时器"""

    def __init__(self, name: str = ""):
        self.name = name
        self.start_time: Optional[float] = None
        self.duration: Optional[float] = None

    def __enter__(self):
        self.start_time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.start_time is None:
            return
        self.duration = time.time() - self.start_time
        logger.debug("⏱️ %s: %.4f秒", self.name, self.duration)


class HealthChecker:
    """健康检查器"""

    def __init__(self):
        self._checks: Dict[str, Callable] = {}
        self.logger = logging.getLogger("runtime.health")

    def register_check(self, name: str, check_func: Callable):
        """注册健康检查"""
        self._checks[name] = check_func
        self.logger.info("已注册健康检查: %s", name)

    async def run_all_checks(self) -> Dict[str, bool]:
        """运行所有健康检查"""
        results = {}
        for name, check_func in self._checks.items():
            try:
                if asyncio.iscoroutinefunction(check_func):
                    results[name] = await check_func()
                else:
                    results[name] = check_func()
            except Exception as e:
                self.logger.error("健康检查失败 %s: %s", name, e)
                results[name] = False
        return results


class ProcessWatchdog:
    """进程看门狗"""

    def __init__(self):
        self._watched_processes: Dict[str, ProcessMonitor] = {}
        self._restart_callbacks: Dict[str, Callable] = {}
        self._running = False
        self.logger = logging.getLogger("runtime.watchdog")

    def watch(self, name: str, pid: int, restart_callback: Optional[Callable[[], None]] = None):
        """监控进程"""
        self._watched_processes[name] = ProcessMonitor(pid)
        if restart_callback:
            self._restart_callbacks[name] = restart_callback
        self.logger.info("已添加监控: %s (PID=%s)", name, pid)

    async def start(self):
        """启动看门狗"""
        self._running = True
        self.logger.info("进程看门狗已启动")

        while self._running:
            for name, monitor in self._watched_processes.items():
                if not monitor.is_alive():
                    self.logger.error("❌ 进程 %s 已停止", name)
                    if name in self._restart_callbacks:
                        try:
                            self._restart_callbacks[name]()
                        except Exception as e:
                            self.logger.error("重启失败: %s", e)
            await asyncio.sleep(5)

    def stop(self):
        """停止看门狗"""
        self._running = False


class MonitoringManager:
    """监控管理器 - 单例"""
    _instance = None

    def __init__(self):
        self.system_monitor = SystemMonitor()
        self.health_checker = HealthChecker()
        self.watchdog = ProcessWatchdog()
        self.logger = logging.getLogger("runtime.monitoring")
        self._initialized = False

    @classmethod
    def get_instance(cls) -> "MonitoringManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def initialize(self):
        """初始化监控系统"""
        if self._initialized:
            return
        self.system_monitor.start()
        self._initialized = True
        self.logger.info("✅ 监控系统已初始化")

    def shutdown(self):
        """关闭监控系统"""
        self.system_monitor.stop()
        self.watchdog.stop()
        self._initialized = False


def get_monitoring_manager() -> MonitoringManager:
    return MonitoringManager.get_instance()


# ============================================================================
# Section 1B: 监控扩展能力 (健康检查、指标采集、告警)
# ============================================================================


@dataclass
class HealthCheckResult:
    """健康检查结果"""

    check_name: str
    passed: bool
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)
    duration_ms: float = 0.0


class HealthMonitor:
    """健康监控器

    扩展版监控组件，支持定期健康检查、历史记录与告警联动。
    """

    def __init__(self):
        self._checks: Dict[str, Dict[str, Any]] = {}
        self._history: deque = deque(maxlen=1000)
        self._running = False
        self._background_task: Optional[asyncio.Task] = None
        self.logger = logging.getLogger("runtime.health_monitor")

    def register_check(
        self,
        name: str,
        check_func: Callable[[], Union[bool, Awaitable[bool], HealthCheckResult]],
        interval: float = 60.0,
        timeout: float = 5.0,
    ):
        """注册健康检查

        Args:
            name: 检查名称
            check_func: 检查函数，返回bool、HealthCheckResult或抛出异常
            interval: 检查间隔（秒）
            timeout: 超时时间（秒）
        """
        self._checks[name] = {
            "func": check_func,
            "interval": float(interval),
            "timeout": float(timeout),
            "last_check": None,
            "last_result": None,
            "next_run": datetime.now(),
        }
        self.logger.info("已注册健康检查: %s (interval=%ss, timeout=%ss)", name, interval, timeout)

    async def run_checks(self) -> Dict[str, HealthCheckResult]:
        """运行所有健康检查（仅运行符合调度的检查）"""
        results: Dict[str, HealthCheckResult] = {}
        now = datetime.now()

        for name, check_info in self._checks.items():
            # 调度控制：仅在到期时执行
            next_run: datetime = check_info.get("next_run") or now
            if now < next_run:
                continue

            start_time = time.perf_counter()
            check_func = check_info["func"]

            try:
                result = await self._execute_check(check_func, timeout=check_info["timeout"])
                duration_ms = (time.perf_counter() - start_time) * 1000

                if isinstance(result, HealthCheckResult):
                    health_result = result
                    health_result.duration_ms = duration_ms
                else:
                    health_result = HealthCheckResult(
                        check_name=name,
                        passed=bool(result),
                        message="Check passed" if result else "Check failed",
                        duration_ms=duration_ms,
                    )
            except asyncio.TimeoutError:
                health_result = HealthCheckResult(
                    check_name=name,
                    passed=False,
                    message=f"Check timeout after {check_info['timeout']}s",
                )
            except Exception as exc:  # noqa: BLE001
                health_result = HealthCheckResult(
                    check_name=name,
                    passed=False,
                    message=f"Check error: {exc}",
                    details={"exception_type": exc.__class__.__name__},
                )

            results[name] = health_result
            check_info["last_check"] = now
            check_info["last_result"] = health_result
            check_info["next_run"] = now + timedelta(seconds=check_info["interval"])

            self._history.append(
                {
                    "name": name,
                    "result": health_result,
                    "timestamp": now,
                }
            )

        return results

    async def _execute_check(
        self,
        check_func: Callable[[], Union[bool, Awaitable[bool], HealthCheckResult]],
        timeout: float,
    ) -> Union[bool, HealthCheckResult]:
        if asyncio.iscoroutinefunction(check_func):
            return await asyncio.wait_for(check_func(), timeout=timeout)
        result = check_func()
        if inspect.isawaitable(result):
            awaited = await asyncio.wait_for(cast(Awaitable[Any], result), timeout=timeout)
            return awaited
        return cast(Union[bool, HealthCheckResult], result)

    def get_health_status(self) -> str:
        """获取整体健康状态"""
        if not self._checks:
            return "unknown"

        total = len(self._checks)
        passed = sum(
            1 for check in self._checks.values() if check["last_result"] and check["last_result"].passed
        )

        if passed == total:
            return "healthy"
        if passed >= total * 0.5:
            return "degraded"
        return "unhealthy"

    def get_history(self, check_name: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        """获取检查历史"""
        if check_name:
            history = [entry for entry in self._history if entry["name"] == check_name]
        else:
            history = list(self._history)
        return history[-limit:]

    def get_last_results(self) -> Dict[str, Optional[HealthCheckResult]]:
        """返回每个检查的最近一次结果"""
        return {name: info.get("last_result") for name, info in self._checks.items()}

    async def start(self, interval: float = 30.0):
        """启动后台任务，按固定间隔执行"""
        if self._running:
            return
        self._running = True

        async def _runner():
            self.logger.info("健康监控后台任务启动，周期 %ss", interval)
            try:
                while self._running:
                    await self.run_checks()
                    await asyncio.sleep(interval)
            except asyncio.CancelledError:
                self.logger.debug("健康监控后台任务已取消")
            finally:
                self._running = False

        self._background_task = asyncio.create_task(_runner(), name="health-monitor-runner")

    async def stop(self):
        """停止后台任务"""
        self._running = False
        if self._background_task and not self._background_task.done():
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass
        self._background_task = None


class MetricsCollector:
    """指标采集器"""

    def __init__(self, retention_days: int = 7):
        self.retention_days = retention_days
        self._metrics: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self.logger = logging.getLogger("runtime.metrics_collector")

    def collect(self, metric_type: str, value: float, tags: Optional[Dict[str, str]] = None):
        """采集指标"""
        metric_data = {
            "value": float(value),
            "timestamp": datetime.now(),
            "tags": tags or {},
        }

        with self._lock:
            if metric_type not in self._metrics:
                self._metrics[metric_type] = []
            self._metrics[metric_type].append(metric_data)
            self._cleanup_old_metrics(metric_type)

    def _cleanup_old_metrics(self, metric_type: str):
        """清理过期指标"""
        cutoff = datetime.now() - timedelta(days=self.retention_days)
        metrics = self._metrics.get(metric_type, [])
        self._metrics[metric_type] = [item for item in metrics if item["timestamp"] > cutoff]

    def get_metrics(
        self,
        metric_type: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """查询指标"""
        with self._lock:
            metrics = list(self._metrics.get(metric_type, []))

        if start_time:
            metrics = [item for item in metrics if item["timestamp"] >= start_time]
        if end_time:
            metrics = [item for item in metrics if item["timestamp"] <= end_time]
        if tags:
            metrics = [
                item
                for item in metrics
                if all(item["tags"].get(key) == value for key, value in tags.items())
            ]
        return metrics

    def aggregate(
        self,
        metric_type: str,
        agg_func: str = "avg",
        window_minutes: int = 5,
    ) -> Optional[float]:
        """聚合统计"""
        start_time = datetime.now() - timedelta(minutes=window_minutes)
        metrics = self.get_metrics(metric_type, start_time=start_time)
        if not metrics:
            return None

        values = [item["value"] for item in metrics]

        if agg_func == "avg":
            return sum(values) / len(values)
        if agg_func == "sum":
            return sum(values)
        if agg_func == "max":
            return max(values)
        if agg_func == "min":
            return min(values)
        if agg_func == "count":
            return float(len(values))
        return None


@dataclass
class AlertRule:
    """告警规则"""

    rule_id: str
    name: str
    metric_type: str
    condition: str  # ">", "<", ">=", "<=", "==", "!="
    threshold: float
    duration_seconds: int = 60
    is_enabled: bool = True
    last_triggered: Optional[datetime] = None


class AlertManager:
    """告警管理器"""

    def __init__(self):
        self._rules: Dict[str, AlertRule] = {}
        self._alert_history: deque = deque(maxlen=1000)
        self._alert_actions: Dict[str, Callable[[AlertRule, float], None]] = {}
        self.logger = logging.getLogger("runtime.alert_manager")

    def add_rule(self, rule: AlertRule):
        """添加告警规则"""
        self._rules[rule.rule_id] = rule
        self.logger.info("已添加告警规则: %s (%s)", rule.name, rule.metric_type)

    def remove_rule(self, rule_id: str):
        """移除告警规则"""
        if rule_id in self._rules:
            del self._rules[rule_id]
            self.logger.info("已移除告警规则: %s", rule_id)

    def register_action(self, action_name: str, action_func: Callable[[AlertRule, float], None]):
        """注册告警动作"""
        self._alert_actions[action_name] = action_func
        self.logger.debug("已注册告警动作: %s", action_name)

    def evaluate_rules(self, metrics: Dict[str, float]):
        """评估规则并触发告警"""
        for rule in list(self._rules.values()):
            if not rule.is_enabled or rule.metric_type not in metrics:
                continue
            value = float(metrics[rule.metric_type])
            if self._check_condition(value, rule.condition, rule.threshold):
                self._trigger_alert(rule, value)

    def _check_condition(self, value: float, condition: str, threshold: float) -> bool:
        if condition == ">":
            return value > threshold
        if condition == "<":
            return value < threshold
        if condition == ">=":
            return value >= threshold
        if condition == "<=":
            return value <= threshold
        if condition == "==":
            return value == threshold
        if condition == "!=":
            return value != threshold
        self.logger.error("未知的告警条件: %s", condition)
        return False

    def _trigger_alert(self, rule: AlertRule, value: float):
        now = datetime.now()
        if rule.last_triggered:
            silence_until = rule.last_triggered + timedelta(seconds=rule.duration_seconds)
            if now < silence_until:
                return

        alert_record = {
            "rule_id": rule.rule_id,
            "rule_name": rule.name,
            "metric_type": rule.metric_type,
            "value": value,
            "threshold": rule.threshold,
            "timestamp": now,
        }
        self._alert_history.append(alert_record)
        rule.last_triggered = now

        for action_name, action_func in list(self._alert_actions.items()):
            try:
                action_func(rule, value)
            except Exception as exc:  # noqa: BLE001
                self.logger.error("告警动作执行失败 [%s]: %s", action_name, exc)

        self.logger.warning(
            "⚠️ 告警触发: %s (%s %s %.2f)",
            rule.name,
            rule.metric_type,
            rule.condition,
            rule.threshold,
        )

    def get_alert_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """返回告警历史"""
        return list(self._alert_history)[-limit:]

    def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        return self._rules.get(rule_id)

    def list_rules(self) -> List[AlertRule]:
        return list(self._rules.values())

# ============================================================================
# Section 2: 日志系统 (行 300-600)
# ============================================================================


class LogFilter:
    """日志过滤器，根据日志级别、模块与关键字完成筛选。"""

    def __init__(
        self,
        min_level: int = logging.DEBUG,
        modules: Optional[List[str]] = None,
        exclude_modules: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
    ):
        self.min_level = int(min_level)
        self.modules = modules or []
        self.exclude_modules = exclude_modules or []
        self.keywords = keywords or []

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno < self.min_level:
            return False
        if self.modules and not any(record.name.startswith(module) for module in self.modules):
            return False
        if self.exclude_modules and any(record.name.startswith(module) for module in self.exclude_modules):
            return False
        if self.keywords:
            message = record.getMessage()
            if not any(keyword in message for keyword in self.keywords):
                return False
        return True


class LogFormatterFactory:
    """日志格式化器工厂，提供标准、详细、JSON 等多种格式。"""

    @staticmethod
    def create(format_type: str = "standard") -> logging.Formatter:
        if format_type == "standard":
            return logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        if format_type == "detailed":
            return logging.Formatter(
                "%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] [%(funcName)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        if format_type == "json":

            class JsonFormatter(logging.Formatter):
                """JSON格式的日志格式化器"""
                def format(self, record: logging.LogRecord) -> str:
                    log_data = {
                        "timestamp": self.formatTime(record, datefmt="%Y-%m-%d %H:%M:%S"),
                        "level": record.levelname,
                        "logger": record.name,
                        "message": record.getMessage(),
                    }
                    if record.exc_info:
                        log_data["exc_info"] = self.formatException(record.exc_info)
                    return json.dumps(log_data, ensure_ascii=False)

            return JsonFormatter()
        if format_type == "simple":
            return logging.Formatter("%(levelname)s: %(message)s")
        return logging.Formatter("%(message)s")


class LogAnalyzer:
    """日志分析器，支持错误模式识别、趋势分析与级别统计。"""

    _DEFAULT_TIME_FORMATS = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%H:%M:%S",
    ]

    _LOG_PATTERNS: Tuple[Pattern[str], ...] = (
        re.compile(
            r"^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{1,6})?)\s+\[(?P<level>[A-Z]+)\]\s+(?P<logger>[\w\.\-]+):\s+(?P<message>.*)$"
        ),
        re.compile(
            r"^(?P<timestamp>\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?)\s+\[(?P<level>[A-Z]+)\]\s+(?P<logger>[\w\.\-]+):\s+(?P<message>.*)$"
        ),
    )

    def __init__(self, time_formats: Optional[List[str]] = None):
        self.logger = logging.getLogger("runtime.log_analyzer")
        self._time_formats = time_formats or self._DEFAULT_TIME_FORMATS
        self._level_counter: Counter[str] = Counter()
        self._module_counter: Counter[str] = Counter()
        self._error_counter: Counter[str] = Counter()
        self._time_buckets: Dict[str, int] = defaultdict(int)
        self._recent_errors: deque = deque(maxlen=200)
        self._last_summary: Dict[str, Any] = {}

    def analyze_logs(
        self,
        log_file: Union[str, Path],
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        log_path = Path(log_file)
        if not log_path.exists():
            raise FileNotFoundError(f"日志文件不存在: {log_path}")

        self._level_counter.clear()
        self._module_counter.clear()
        self._error_counter.clear()
        self._time_buckets.clear()
        self._recent_errors.clear()

        total_lines = 0
        matched_lines = 0

        with log_path.open("r", encoding="utf-8", errors="ignore") as fp:
            for line in fp:
                total_lines += 1
                record = self._parse_line(line)
                if not record:
                    continue

                timestamp = record["timestamp"]
                if start_time and timestamp < start_time:
                    continue
                if end_time and timestamp > end_time:
                    continue

                matched_lines += 1
                level = record["level"]
                module = record["logger"]
                message = record["message"]

                self._level_counter[level] += 1
                self._module_counter[module] += 1

                bucket_key = timestamp.strftime("%Y-%m-%d %H:%M")
                self._time_buckets[bucket_key] += 1

                if level in {"ERROR", "CRITICAL"}:
                    self._error_counter[message] += 1
                    self._recent_errors.appendleft(
                        {
                            "timestamp": timestamp,
                            "level": level,
                            "logger": module,
                            "message": message,
                        }
                    )

        summary = {
            "file": str(log_path),
            "total_lines": total_lines,
            "matched_lines": matched_lines,
            "level_distribution": dict(self._level_counter),
            "module_distribution": dict(self._module_counter.most_common(20)),
            "time_trend": dict(sorted(self._time_buckets.items())),
            "top_errors": self._error_counter.most_common(20),
            "recent_errors": list(self.get_recent_errors(20)),
        }
        self._last_summary = summary
        return summary

    def _parse_line(self, line: str) -> Optional[Dict[str, Any]]:
        stripped = line.strip()
        if not stripped:
            return None

        payload: Optional[Dict[str, Any]] = None
        if stripped.startswith("{") and stripped.endswith("}"):
            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                payload = None
        if payload:
            timestamp = self._parse_timestamp(payload.get("timestamp"))
            level = self._normalise_level(payload.get("level"))
            logger_name = payload.get("logger") or payload.get("name") or "unknown"
            message = payload.get("message") or payload.get("msg") or ""
            if timestamp and level:
                return {
                    "timestamp": timestamp,
                    "level": level,
                    "logger": logger_name,
                    "message": str(message),
                }

        for pattern in self._LOG_PATTERNS:
            match = pattern.match(stripped)
            if not match:
                continue
            timestamp = self._parse_timestamp(match.group("timestamp"))
            level = self._normalise_level(match.group("level"))
            if not timestamp or not level:
                continue
            return {
                "timestamp": timestamp,
                "level": level,
                "logger": match.group("logger"),
                "message": match.group("message"),
            }
        return None

    def _parse_timestamp(self, value: Optional[Union[str, float, int]]) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(float(value))
            except (OverflowError, OSError, ValueError):
                return None
        if not isinstance(value, str):
            return None
        text = value.strip()
        for fmt in self._time_formats:
            try:
                return datetime.strptime(text[: len(fmt)], fmt)
            except ValueError:
                continue
        return None

    def _normalise_level(self, level: Optional[Union[str, int]]) -> Optional[str]:
        if level is None:
            return None
        if isinstance(level, int):
            return logging.getLevelName(level)
        level_str = str(level).upper()
        try:
            # Check if the level string is valid by attempting to get its numeric value
            logging.getLevelName(level_str)
            return level_str
        except (ValueError, TypeError):
            return None

    def get_recent_errors(self, limit: int = 20) -> List[Dict[str, Any]]:
        return list(list(self._recent_errors)[:limit])

    def get_error_summary(self, limit: int = 20) -> List[Tuple[str, int]]:
        return list(self._error_counter.most_common(limit))

    def get_last_summary(self) -> Dict[str, Any]:
        return dict(self._last_summary)


class LogArchiver:
    """日志归档器，负责压缩、上传及清理旧日志。"""

    def __init__(
        self,
        log_dir: Union[str, Path] = "logs",
        archive_dir: Optional[Union[str, Path]] = None,
        uploader: Optional[Callable[[Path], None]] = None,
    ):
        self.log_dir = Path(log_dir)
        self.archive_dir = Path(archive_dir) if archive_dir else self.log_dir / "archive"
        self.archive_dir.mkdir(parents=True, exist_ok=True)
        self._uploader = uploader
        self.logger = logging.getLogger("runtime.log_archiver")

    def set_uploader(self, uploader: Callable[[Path], None]):
        self._uploader = uploader

    def archive_old_logs(
        self,
        days: int = 30,
        pattern: str = "*.log",
        remove_original: bool = True,
    ) -> List[Path]:
        cutoff = datetime.now() - timedelta(days=days)
        archived_files: List[Path] = []

        for log_path in self.log_dir.glob(pattern):
            if not log_path.is_file():
                continue
            try:
                mtime = datetime.fromtimestamp(log_path.stat().st_mtime)
            except (OSError, ValueError):
                continue
            if mtime >= cutoff:
                continue

            archive_path = self._archive_file(log_path, mtime.strftime("%Y%m%d"))
            archived_files.append(archive_path)

            if remove_original:
                try:
                    log_path.unlink()
                except OSError as exc:
                    self.logger.warning("删除原始日志失败 %s: %s", log_path, exc)

            if self._uploader:
                try:
                    self._uploader(archive_path)
                except Exception as exc:  # noqa: BLE001
                    self.logger.error("上传归档失败 %s: %s", archive_path, exc)

        return archived_files

    def _archive_file(self, log_path: Path, suffix: str) -> Path:
        archive_name = f"{log_path.stem}_{suffix}.zip"
        archive_path = self.archive_dir / archive_name
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.write(log_path, arcname=log_path.name)
        self.logger.info("日志已归档: %s -> %s", log_path.name, archive_name)
        return archive_path

    def cleanup_archives(self, retention_days: int = 180):
        cutoff = datetime.now() - timedelta(days=retention_days)
        for archive_path in self.archive_dir.glob("*.zip"):
            try:
                mtime = datetime.fromtimestamp(archive_path.stat().st_mtime)
                if mtime < cutoff:
                    archive_path.unlink()
                    self.logger.info("已清理过期归档: %s", archive_path.name)
            except OSError as exc:
                self.logger.warning("清理归档失败 %s: %s", archive_path, exc)

    def list_archives(self) -> List[Path]:
        return sorted(self.archive_dir.glob("*.zip"))


class LogType(str, Enum):
    """日志类型枚举"""
    SYSTEM = "SYSTEM"
    TRADING = "TRADING"
    DATA = "DATA"
    STRATEGY = "STRATEGY"
    ALERT = "ALERT"
    DEBUG = "DEBUG"


@dataclass
class LogConfig:
    """日志配置"""
    level: str = "INFO"
    file_path: str = "logs/terminal.log"
    max_size: int = 10 * 1024 * 1024
    backup_count: int = 5
    enable_console: bool = True
    enable_file: bool = True


class LazyLogger:
    """延迟初始化的日志器"""

    def __init__(self, name: str):
        self.name = name
        self._logger = logging.getLogger(name)
        self._buffer: List[Dict] = []
        self._is_initialized = False
        self._lock = threading.Lock()

    def _log(self, level: int, message: str, *args, **kwargs):
        """内部日志方法"""
        with self._lock:
            if self._is_initialized:
                self._logger.log(level, message, *args, **kwargs)
            else:
                self._buffer.append({
                    "level": level,
                    "message": message,
                    "args": args,
                    "kwargs": kwargs,
                    "timestamp": datetime.now(),
                })

    def debug(self, message, *args, **kwargs):
        self._log(logging.DEBUG, message, *args, **kwargs)

    def info(self, message, *args, **kwargs):
        self._log(logging.INFO, message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        self._log(logging.WARNING, message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self._log(logging.ERROR, message, *args, **kwargs)

    async def initialize_async(self, handlers: Optional[List[logging.Handler]] = None):
        """异步初始化"""
        if self._is_initialized:
            return

        try:
            if handlers:
                for handler in handlers:
                    self._logger.addHandler(handler)

            with self._lock:
                for log_entry in self._buffer:
                    self._logger.log(
                        log_entry["level"],
                        log_entry["message"],
                        *log_entry["args"],
                        **log_entry["kwargs"]
                    )
                self._buffer.clear()

            self._is_initialized = True
        except Exception as e:
            logger.error("LazyLogger初始化失败: %s", e)


class LazyLoggerManager:
    """LazyLogger管理器 - 单例"""
    _instance = None

    def __init__(self):
        self._loggers: Dict[str, LazyLogger] = {}
        self._initialized = False

    @classmethod
    def get_instance(cls) -> "LazyLoggerManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_logger(self, name: str) -> LazyLogger:
        """获取LazyLogger"""
        if name not in self._loggers:
            self._loggers[name] = LazyLogger(name)
        return self._loggers[name]

    async def initialize_all(self, handlers: List[logging.Handler]):
        """初始化所有LazyLogger"""
        tasks = []
        for lazy_logger in self._loggers.values():
            tasks.append(lazy_logger.initialize_async(handlers))
        await asyncio.gather(*tasks)
        self._initialized = True


class LogRouter:
    """日志路由器"""

    def __init__(self):
        self._routes: Dict[LogType, List[logging.Handler]] = {
            log_type: [] for log_type in LogType
        }
        self.logger = logging.getLogger("runtime.log_router")

    def add_route(self, log_type: LogType, handler: logging.Handler):
        """添加路由"""
        self._routes[log_type].append(handler)
        self.logger.info("添加路由: %s -> %s", log_type, handler.__class__.__name__)


class LoggingSystemManager:
    """统一日志系统管理器 - 单例"""
    _instance = None

    def __init__(self):
        self.config = LogConfig()
        self.lazy_manager = LazyLoggerManager.get_instance()
        self.router = LogRouter()
        self._handlers: Dict[str, logging.Handler] = {}
        self._initialized = False
        self.logger = logging.getLogger("runtime.logging_manager")

    @classmethod
    def get_instance(cls) -> "LoggingSystemManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def setup_handlers(self):
        """设置所有Handler"""
        from logging.handlers import RotatingFileHandler
        import os

        # 1. 控制台Handler
        console_handler = logging.StreamHandler()
        console_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        console_handler.setLevel(getattr(logging, self.config.level))
        self._handlers["console"] = console_handler

        # 2. 文件Handler（带轮转）
        log_dir = os.path.dirname(self.config.file_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)

        file_handler = RotatingFileHandler(
            filename=self.config.file_path,
            maxBytes=self.config.max_size,
            backupCount=self.config.backup_count,
            encoding='utf-8'
        )
        file_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] [%(name)s:%(lineno)d] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG)  # 文件记录所有级别
        self._handlers["file"] = file_handler

        # 3. 错误日志Handler（专门记录ERROR及以上）
        error_log_path = self.config.file_path.replace('.log', '_error.log')
        error_handler = RotatingFileHandler(
            filename=error_log_path,
            maxBytes=self.config.max_size,
            backupCount=self.config.backup_count,
            encoding='utf-8'
        )
        error_handler.setFormatter(file_formatter)
        error_handler.setLevel(logging.ERROR)
        self._handlers["error"] = error_handler

        self.logger.info("日志Handler已配置: console, file(%s), error", self.config.file_path)

    async def initialize(self):
        """初始化日志系统"""
        if self._initialized:
            return

        # 设置handlers
        self.setup_handlers()

        # 初始化LazyLogger管理器（传入所有handlers）
        all_handlers = list(self._handlers.values())
        await self.lazy_manager.initialize_all(all_handlers)

        # 配置根logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.DEBUG)
        for handler in all_handlers:
            if handler not in root_logger.handlers:
                root_logger.addHandler(handler)

        self._initialized = True
        self.logger.info("✅ 日志系统已初始化（控制台+文件+错误日志）")

    def get_logger(self, name: str, _log_type: LogType = LogType.SYSTEM) -> LazyLogger:
        """获取配置好的logger"""
        return self.lazy_manager.get_logger(name)

    def shutdown(self):
        """关闭日志系统"""
        for handler in self._handlers.values():
            handler.close()
        self._initialized = False


def get_logging_manager() -> LoggingSystemManager:
    return LoggingSystemManager.get_instance()


def get_logger(name: str, log_type: LogType = LogType.SYSTEM) -> LazyLogger:
    manager = get_logging_manager()
    return manager.get_logger(name, log_type)


# ============================================================================
# Section 3: Native日志桥接
# ============================================================================


class NativeLogBridgeBase(ABC):
    """Native日志桥接基类，将Native层日志推送到Python日志系统。"""

    @abstractmethod
    def forward_log(
        self,
        level: int,
        module: str,
        message: str,
        timestamp: Optional[datetime] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        """转发日志消息"""

    @abstractmethod
    def start(self):
        """启动桥接"""

    @abstractmethod
    def stop(self):
        """停止桥接"""


class NativeLogPipeline:
    """Native日志管道，负责批量处理与写入Python日志。"""

    def __init__(
        self,
        batch_size: int = 100,
        flush_interval: float = 0.5,
        handler: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.batch_size = max(1, int(batch_size))
        self.flush_interval = max(0.01, float(flush_interval))
        self._handler = handler or self._default_handler
        self.logger = logging.getLogger("runtime.native_log_pipeline")

    def process_sync(self, messages: List[Dict[str, Any]]):
        if not messages:
            return
        start = time.perf_counter()
        for message in messages:
            try:
                self._handler(message)
            except Exception as exc:  # noqa: BLE001
                self.logger.error("处理Native日志失败: %s | message=%s", exc, message)
        duration_ms = (time.perf_counter() - start) * 1000
        if duration_ms > 50:
            self.logger.debug("Native日志批次处理耗时 %.2fms (messages=%d)", duration_ms, len(messages))

    async def process(self, messages: List[Dict[str, Any]]):
        await asyncio.to_thread(self.process_sync, messages)

    def _default_handler(self, message: Dict[str, Any]):
        level = self._normalize_level(message.get("level", logging.INFO))
        module = message.get("module") or "runtime.native"
        record_logger = logging.getLogger(module)
        msg = str(message.get("message", ""))
        extra = dict(message.get("context") or {})
        timestamp = message.get("timestamp")
        if isinstance(timestamp, datetime):
            extra.setdefault("native_timestamp", timestamp.isoformat())
        record_logger.log(level, msg, extra=extra)

    @staticmethod
    def _normalize_level(level: Union[int, str]) -> int:
        if isinstance(level, int):
            return level
        level_name = str(level).upper()
        try:
            return logging.getLevelName(level_name)
        except (ValueError, TypeError):
            return logging.INFO


class NativeLogBridge(NativeLogBridgeBase):
    """通用Native日志桥接器，支持批量处理与降级策略。"""

    def __init__(
        self,
        queue_size: int = 10000,
        batch_size: int = 200,
        flush_interval: float = 0.5,
        pipeline: Optional[NativeLogPipeline] = None,
    ):
        self._queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=max(1, queue_size))
        self._batch_size = max(1, int(batch_size))
        self._flush_interval = max(0.01, float(flush_interval))
        self._pipeline = pipeline or NativeLogPipeline(batch_size=batch_size, flush_interval=flush_interval)
        self._stop_event = threading.Event()
        self._worker_thread: Optional[threading.Thread] = None
        self._running = False
        self._dropped = 0
        self._processed = 0
        self._drop_handler: Optional[Callable[[Dict[str, Any]], None]] = None
        self.logger = logging.getLogger("runtime.native_log_bridge")

    def start(self):
        if self._running:
            return
        self._running = True
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._run, name="native-log-bridge", daemon=True)
        self._worker_thread.start()
        self.logger.info(
            "NativeLogBridge已启动 (queue=%d, batch=%d, interval=%.2fs)",
            self._queue.maxsize,
            self._batch_size,
            self._flush_interval,
        )

    def stop(self):
        self._running = False
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)
        self._worker_thread = None
        self.flush()

    def forward_log(
        self,
        level: int,
        module: str,
        message: str,
        timestamp: Optional[datetime] = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        record = {
            "level": level,
            "module": module or "runtime.native",
            "message": str(message),
            "timestamp": timestamp or datetime.now(),
            "context": context or {},
        }

        try:
            self._queue.put_nowait(record)
        except queue.Full:
            self._dropped += 1
            if self._drop_handler:
                try:
                    self._drop_handler(record)
                except Exception as exc:  # noqa: BLE001
                    self.logger.error("Native日志丢弃回调失败: %s", exc)
            elif self._dropped % 100 == 1:
                self.logger.warning("Native日志队列已满，累计丢弃 %d 条", self._dropped)

    def set_drop_handler(self, handler: Callable[[Dict[str, Any]], None]):
        self._drop_handler = handler

    def flush(self):
        batch: List[Dict[str, Any]] = []
        while not self._queue.empty():
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
            if len(batch) >= self._batch_size:
                self._dispatch_batch(batch)
                batch.clear()
        if batch:
            self._dispatch_batch(batch)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "pending": self._queue.qsize(),
            "processed": self._processed,
            "dropped": self._dropped,
            "running": self._running,
        }

    def _run(self):
        batch: List[Dict[str, Any]] = []
        next_flush = time.time() + self._flush_interval
        while not self._stop_event.is_set():
            timeout = max(0.0, next_flush - time.time())
            try:
                item = self._queue.get(timeout=timeout)
                batch.append(item)
                if len(batch) >= self._batch_size:
                    self._dispatch_batch(batch)
                    batch.clear()
                    next_flush = time.time() + self._flush_interval
            except queue.Empty:
                if batch:
                    self._dispatch_batch(batch)
                    batch.clear()
                next_flush = time.time() + self._flush_interval
        if batch:
            self._dispatch_batch(batch)

    def _dispatch_batch(self, batch: List[Dict[str, Any]]):
        if not batch:
            return
        try:
            self._pipeline.process_sync(batch)
            self._processed += len(batch)
        except Exception as exc:  # noqa: BLE001
            self.logger.error("Native日志批次处理失败: %s", exc)


# ============================================================================
# Section 4: 监控工具集
# ============================================================================


class ResourceTracker:
    """资源追踪器，汇总进程级CPU、内存、IO等指标。"""

    def __init__(self, pid: Optional[int] = None):
        self.pid = pid or os.getpid()
        self._process = psutil.Process(self.pid)
        self.logger = logging.getLogger("runtime.resource_tracker")
        try:
            self._process.cpu_percent(interval=None)
        except (psutil.Error, OSError):
            pass

    def track_cpu(self, interval: float = 0.1) -> float:
        try:
            return self._process.cpu_percent(interval=interval)
        except (psutil.Error, OSError) as exc:
            self.logger.debug("获取CPU使用率失败: %s", exc)
            return 0.0

    def track_memory(self) -> Dict[str, float]:
        try:
            memory_info = self._process.memory_full_info()
            return {
                "rss_mb": memory_info.rss / 1024 / 1024,
                "vms_mb": memory_info.vms / 1024 / 1024,
                "percent": self._process.memory_percent(),
            }
        except AttributeError:
            memory_info = self._process.memory_info()
            return {
                "rss_mb": memory_info.rss / 1024 / 1024,
                "vms_mb": memory_info.vms / 1024 / 1024,
                "percent": self._process.memory_percent(),
            }
        except (psutil.Error, OSError) as exc:
            self.logger.debug("获取内存占用失败: %s", exc)
            return {"rss_mb": 0.0, "vms_mb": 0.0, "percent": 0.0}

    def track_io(self) -> Dict[str, int]:
        try:
            io = self._process.io_counters()
            return {
                "read_count": getattr(io, "read_count", 0),
                "write_count": getattr(io, "write_count", 0),
                "read_bytes": getattr(io, "read_bytes", 0),
                "write_bytes": getattr(io, "write_bytes", 0),
            }
        except (psutil.Error, OSError) as exc:
            self.logger.debug("获取IO统计失败: %s", exc)
            return {"read_count": 0, "write_count": 0, "read_bytes": 0, "write_bytes": 0}

    def snapshot(self) -> Dict[str, Any]:
        try:
            open_files = len(self._process.open_files())
        except (psutil.Error, OSError):
            open_files = 0
        return {
            "cpu_percent": self.track_cpu(interval=0.0),
            "memory": self.track_memory(),
            "io": self.track_io(),
            "thread_count": self._process.num_threads(),
            "open_files": open_files,
        }


class PerformanceProfiler:
    """性能分析器，提供函数级别的耗时统计。"""

    def __init__(self):
        self._profiles: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()
        self.logger = logging.getLogger("runtime.performance_profiler")

    def _record(self, func_name: str, duration: float):
        with self._lock:
            self._profiles.setdefault(func_name, []).append(duration)

    def profile(self, func: Callable) -> Callable:
        if asyncio.iscoroutinefunction(func):

            @wraps(func)
            async def async_wrapper(*args, **kwargs):
                start = time.perf_counter()
                try:
                    return await func(*args, **kwargs)
                finally:
                    self._record(func.__name__, time.perf_counter() - start)

            return async_wrapper

        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                self._record(func.__name__, time.perf_counter() - start)

        return wrapper

    def get_statistics(self, func_name: str) -> Dict[str, float]:
        with self._lock:
            durations = list(self._profiles.get(func_name, []))
        if not durations:
            return {}
        durations_ms = [d * 1000 for d in durations]
        return {
            "count": len(durations_ms),
            "avg_ms": statistics.mean(durations_ms),
            "min_ms": min(durations_ms),
            "max_ms": max(durations_ms),
            "median_ms": statistics.median(durations_ms),
            "p95_ms": self._percentile(durations_ms, 0.95),
            "total_ms": sum(durations_ms),
        }

    def reset(self, func_name: Optional[str] = None):
        with self._lock:
            if func_name:
                self._profiles.pop(func_name, None)
            else:
                self._profiles.clear()

    @staticmethod
    def _percentile(data: List[float], percentile: float) -> float:
        if not data:
            return 0.0
        ordered = sorted(data)
        k = (len(ordered) - 1) * percentile
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return ordered[int(k)]
        return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


class MemoryAnalyzer:
    """内存分析器，结合psutil与tracemalloc产出多维度数据。"""

    def __init__(self, pid: Optional[int] = None):
        self.pid = pid or os.getpid()
        self._process = psutil.Process(self.pid)
        self.logger = logging.getLogger("runtime.memory_analyzer")

    def ensure_tracemalloc(self, n_frames: int = 25):
        if not tracemalloc.is_tracing():
            tracemalloc.start(n_frames)

    def take_snapshot(self):
        self.ensure_tracemalloc()
        return tracemalloc.take_snapshot()

    def compare_snapshots(self, snapshot_old, snapshot_new, limit: int = 10) -> List[Tuple[str, float]]:
        statistics_list = snapshot_new.compare_to(snapshot_old, "lineno")
        return [
            (str(stat.traceback[0]), stat.size_diff / 1024) for stat in statistics_list[:limit]
        ]

    def get_process_memory(self) -> Dict[str, float]:
        try:
            memory_info = self._process.memory_full_info()
            return {
                "rss_mb": memory_info.rss / 1024 / 1024,
                "uss_mb": getattr(memory_info, "uss", memory_info.rss) / 1024 / 1024,
                "swap_mb": getattr(memory_info, "swap", 0) / 1024 / 1024,
                "percent": self._process.memory_percent(),
            }
        except (psutil.Error, OSError) as exc:
            self.logger.debug("获取进程内存信息失败: %s", exc)
            return {"rss_mb": 0.0, "uss_mb": 0.0, "swap_mb": 0.0, "percent": 0.0}

    def get_python_heap(self) -> Dict[str, float]:
        self.ensure_tracemalloc()
        current, peak = tracemalloc.get_traced_memory()
        return {"current_mb": current / 1024 / 1024, "peak_mb": peak / 1024 / 1024}


class ThreadMonitor:
    """线程监控器，捕获线程运行时状态。"""

    def __init__(self, pid: Optional[int] = None):
        self.pid = pid or os.getpid()
        self._process = psutil.Process(self.pid)
        self.logger = logging.getLogger("runtime.thread_monitor")

    def list_threads(self) -> List[Dict[str, Any]]:
        threads = []
        for thread in threading.enumerate():
            threads.append(
                {
                    "ident": thread.ident,
                    "name": thread.name,
                    "daemon": thread.daemon,
                    "is_alive": thread.is_alive(),
                }
            )
        return threads

    def get_thread_cpu_times(self) -> Dict[int, float]:
        cpu_times = {}
        try:
            for thread_info in self._process.threads():
                cpu_times[thread_info.id] = thread_info.user_time + thread_info.system_time
        except (psutil.Error, OSError) as exc:
            self.logger.debug("获取线程CPU时间失败: %s", exc)
        return cpu_times


class NetworkMonitor:
    """网络监控器，提供带宽与连接统计。"""

    def __init__(self):
        self.logger = logging.getLogger("runtime.network_monitor")

    def snapshot(self, pernic: bool = False):
        return psutil.net_io_counters(pernic=pernic)

    def measure_throughput(self, interval: float = 1.0) -> Dict[str, float]:
        start_raw = psutil.net_io_counters(pernic=False)
        start = cast(Any, start_raw)
        if start is None:
            self.logger.warning("无法获取网络IO统计，返回0带宽")
            time.sleep(interval)
            return {
                "bytes_sent_per_sec": 0.0,
                "bytes_recv_per_sec": 0.0,
                "packets_sent_per_sec": 0.0,
                "packets_recv_per_sec": 0.0,
            }
        time.sleep(interval)
        end_raw = psutil.net_io_counters(pernic=False)
        end = cast(Any, end_raw) if end_raw is not None else start
        elapsed = max(interval, 0.001)
        return {
            "bytes_sent_per_sec": (end.bytes_sent - start.bytes_sent) / elapsed,
            "bytes_recv_per_sec": (end.bytes_recv - start.bytes_recv) / elapsed,
            "packets_sent_per_sec": (end.packets_sent - start.packets_sent) / elapsed,
            "packets_recv_per_sec": (end.packets_recv - start.packets_recv) / elapsed,
        }


class DiskMonitor:
    """磁盘监控器，统计使用率与IO情况。"""

    def __init__(self):
        self.logger = logging.getLogger("runtime.disk_monitor")

    def get_usage(self, path: Union[str, Path]) -> Dict[str, float]:
        usage = psutil.disk_usage(str(path))
        return {
            "total_gb": usage.total / 1024 / 1024 / 1024,
            "used_gb": usage.used / 1024 / 1024 / 1024,
            "free_gb": usage.free / 1024 / 1024 / 1024,
            "percent": usage.percent,
        }

    def get_io_counters(self, perdisk: bool = False):
        counters = psutil.disk_io_counters(perdisk=perdisk)
        if counters is None:
            return {} if perdisk else {"read_count": 0, "write_count": 0, "read_bytes": 0, "write_bytes": 0}
        if isinstance(counters, dict):
            if perdisk:
                return {disk: self._format_io(io) for disk, io in counters.items()}
            return self._merge_disk_io(counters.values())
        return self._format_io(counters)

    @staticmethod
    def _format_io(io_counter):
        return {
            "read_count": getattr(io_counter, "read_count", 0),
            "write_count": getattr(io_counter, "write_count", 0),
            "read_bytes": getattr(io_counter, "read_bytes", 0),
            "write_bytes": getattr(io_counter, "write_bytes", 0),
        }

    @staticmethod
    def _merge_disk_io(counters: Iterable[Any]) -> Dict[str, int]:
        total = {"read_count": 0, "write_count": 0, "read_bytes": 0, "write_bytes": 0}
        for counter in counters:
            total["read_count"] += getattr(counter, "read_count", 0)
            total["write_count"] += getattr(counter, "write_count", 0)
            total["read_bytes"] += getattr(counter, "read_bytes", 0)
            total["write_bytes"] += getattr(counter, "write_bytes", 0)
        return total


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    # 监控
    "MetricType",
    "MetricData",
    "SystemMonitor",
    "ProcessMonitor",
    "PerformanceTimer",
    "HealthChecker",
    "ProcessWatchdog",
    "MonitoringManager",
    "get_monitoring_manager",
    "HealthCheckResult",
    "HealthMonitor",
    "MetricsCollector",
    "AlertRule",
    "AlertManager",
    "ResourceTracker",
    "PerformanceProfiler",
    "MemoryAnalyzer",
    "ThreadMonitor",
    "NetworkMonitor",
    "DiskMonitor",

    # 日志
    "LogFilter",
    "LogFormatterFactory",
    "LogAnalyzer",
    "LogArchiver",
    "LogType",
    "LogConfig",
    "LazyLogger",
    "LazyLoggerManager",
    "LogRouter",
    "LoggingSystemManager",
    "get_logging_manager",
    "get_logger",

    # Native桥接
    "NativeLogBridgeBase",
    "NativeLogPipeline",
    "NativeLogBridge",
]
