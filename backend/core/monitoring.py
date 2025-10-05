# -*- coding: utf-8 -*-
"""
监控和测试模块.

提供性能监控、单元测试、健康检查等功能.
"""

# 标准库导入（按字母顺序）
import gc
import io
import logging
import platform
import sys
import threading
import time
import unittest
from collections import defaultdict
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, TYPE_CHECKING

# 第三方库导入（按字母顺序）
import psutil

# 本地模块导入（按字母顺序）
from .models import get_data_model_manager
from .performance import get_performance_optimizer
from .test_integration import main as integration_main
from .test_performance import main as performance_main
from .vnpy_integration import TerminalEngine, VNPY_AVAILABLE, get_terminal_engine

if TYPE_CHECKING:
    from .shared_services import ConfigService


class PerformanceMonitor:
    """性能监控器."""

    def __init__(self, config_service: "ConfigService"):
        """初始化性能监控器."""
        self.config_service = config_service
        self.logger = logging.getLogger(__name__)

        # 监控数据
        self._metrics: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._alerts: List[Dict[str, Any]] = []
        self._thresholds: Dict[str, float] = {}

        # 监控状态（分组在一起减少实例属性数量）
        self._state = {
            "monitoring": False,
            "monitor_thread": None,
            "stop_event": threading.Event(),
        }

        # 初始化阈值
        self._init_thresholds()

    def _init_thresholds(self):
        """初始化监控阈值."""
        config = self.config_service.get("system", {})

        self._thresholds = {
            "cpu_percent": config.get("cpu_warning_threshold", 80.0),
            "memory_percent": config.get("memory_warning_threshold", 80.0),
            "response_time": config.get("response_time_threshold", 5.0),
            "error_rate": config.get("error_rate_threshold", 10.0),
            "memory_leak_threshold": (config.get("memory_leak_threshold", 100.0)),  # MB
        }

    def start_monitoring(self, interval: float = 5.0):
        """启动性能监控."""
        if self._state["monitoring"]:
            return

        self._state["monitoring"] = True
        self._state["stop_event"].clear()

        self._state["monitor_thread"] = threading.Thread(
            target=self._monitoring_loop, daemon=True
        )
        self._state["monitor_thread"].start()
        self.logger.info("性能监控已启动，间隔: %s秒", interval)

    def stop_monitoring(self):
        """停止性能监控."""
        if not self._state["monitoring"]:
            return

        self._state["monitoring"] = False
        self._state["stop_event"].set()

        if self._state["monitor_thread"]:
            self._state["monitor_thread"].join(timeout=5)

        self.logger.info("性能监控已停止")

    def _monitoring_loop(self, interval: float):
        """监控循环."""
        while not self._state["stop_event"].is_set():
            try:
                # 收集性能指标
                self._collect_metrics()

                # 检查阈值告警
                self._check_thresholds()

                # 保存历史数据
                self._cleanup_old_metrics()

                # 等待下次监控
                self._state["stop_event"].wait(interval)

            except (RuntimeError, OSError) as e:
                self.logger.error("监控循环异常: %s", e)
                time.sleep(interval)

    def _collect_metrics(self):
        """收集性能指标."""
        timestamp = datetime.now()

        try:
            # 系统性能指标
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage("/")

            system_metrics = {
                "timestamp": timestamp,
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_used_mb": memory.used / (1024 * 1024),
                "disk_percent": disk.percent,
                "disk_used_gb": disk.used / (1024 * 1024 * 1024),
            }

            self._metrics["system"].append(system_metrics)

            # 应用性能指标
            app_metrics = {
                "timestamp": timestamp,
                "python_objects": len(gc.get_objects()),
                "thread_count": threading.active_count(),
                "response_time": self._measure_response_time(),
                "error_count": self._get_error_count(),
            }

            self._metrics["application"].append(app_metrics)

            # 核心模块指标
            core_metrics = self._collect_core_metrics()
            if core_metrics:
                self._metrics["core"].append(core_metrics)

        except (RuntimeError, OSError, psutil.Error) as e:
            self.logger.error("收集性能指标失败: %s", e)

    def _measure_response_time(self) -> float:
        """测量响应时间."""
        start_time = time.time()

        # 模拟一些操作来测量响应时间
        for _ in range(1000):
            pass

        return (time.time() - start_time) * 1000  # 毫秒

    def _get_error_count(self) -> int:
        """获取错误计数（简化版）."""
        # 这里可以从日志或其他来源获取错误计数
        # 暂时返回0
        return 0

    def _collect_core_metrics(self) -> Optional[Dict[str, Any]]:
        """收集核心模块指标."""
        try:
            metrics = {}

            # 数据模型管理器指标
            data_manager = get_data_model_manager()
            if data_manager:
                stats = data_manager.get_statistics()
                metrics["data_model"] = stats

            # 性能优化器指标
            try:
                terminal_engine = get_terminal_engine()
                optimizer = get_performance_optimizer(terminal_engine)
                if optimizer:
                    perf_stats = optimizer.get_performance_stats()
                    metrics["performance"] = perf_stats
            except (RuntimeError, AttributeError):
                pass

            return metrics if metrics else None

        except (RuntimeError, OSError, psutil.Error) as e:
            self.logger.error("收集核心模块指标失败: %s", e)
            return None

    def _check_thresholds(self):
        """检查阈值告警."""
        try:
            if not self._metrics["system"]:
                return

            latest = self._metrics["system"][-1]

            # CPU告警
            if latest["cpu_percent"] > self._thresholds["cpu_percent"]:
                self._add_alert(
                    "cpu_warning",
                    "高CPU使用率",
                    f"CPU使用率 {latest['cpu_percent']:.1f}% "
                    f"超过阈值 {self._thresholds['cpu_percent']}%",
                )

            # 内存告警
            if latest["memory_percent"] > self._thresholds["memory_percent"]:
                self._add_alert(
                    "memory_warning",
                    "高内存使用率",
                    f"内存使用率 {latest['memory_percent']:.1f}% "
                    f"超过阈值 {self._thresholds['memory_percent']}%",
                )

            # 响应时间告警
            if (
                latest.get("response_time", 0)
                > self._thresholds["response_time"] * 1000
            ):
                self._add_alert(
                    "response_time_warning",
                    "响应时间过长",
                    (
                        f"响应时间 {latest.get('response_time', 0):.1f}ms "
                        f"超过阈值 "
                        f"{self._thresholds['response_time'] * 1000}ms"
                    ),
                )

        except (KeyError, TypeError, RuntimeError) as e:
            self.logger.error("检查阈值失败: %s", e)

    def _add_alert(self, alert_type: str, title: str, message: str):
        """添加告警."""
        alert = {
            "timestamp": datetime.now(),
            "type": alert_type,
            "title": title,
            "message": message,
            "resolved": False,
        }

        self._alerts.append(alert)

        # 限制告警数量
        if len(self._alerts) > 1000:
            self._alerts = self._alerts[-500:]

        self.logger.warning("监控告警: %s - %s", title, message)

    def _cleanup_old_metrics(self):
        """清理旧的监控数据."""
        cutoff_time = datetime.now() - timedelta(hours=24)  # 保留24小时数据

        for category in self._metrics:
            if category in self._metrics:
                self._metrics[category] = [
                    m
                    for m in self._metrics[category]
                    if (
                        isinstance(m, dict)
                        and m.get("timestamp")
                        and m["timestamp"] >= cutoff_time
                    )
                ]

    def get_metrics(
        self, category: Optional[str] = None, hours: int = 1
    ) -> Dict[str, Any]:
        """获取监控指标."""
        cutoff_time = datetime.now() - timedelta(hours=hours)

        if category:
            metrics = [
                m
                for m in self._metrics.get(category, [])
                if (
                    isinstance(m, dict)
                    and m.get("timestamp")
                    and m["timestamp"] >= cutoff_time
                )
            ]
            return {category: metrics}

        # 返回所有类别
        result = {}
        for cat, data in self._metrics.items():
            result[cat] = [
                m
                for m in data
                if (
                    isinstance(m, dict)
                    and m.get("timestamp")
                    and m["timestamp"] >= cutoff_time
                )
            ]

        return result

    def get_alerts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取告警列表."""
        return self._alerts[-limit:] if self._alerts else []

    def clear_alerts(self):
        """清空告警."""
        self._alerts.clear()
        self.logger.info("监控告警已清空")

    def get_summary(self) -> Dict[str, Any]:
        """获取监控摘要."""
        summary = {
            "monitoring_active": self._state["monitoring"],
            "total_alerts": len(self._alerts),
            "metrics_count": {
                category: len(metrics) for category, metrics in self._metrics.items()
            },
            "thresholds": self._thresholds.copy(),
        }

        # 最近的系统指标
        if self._metrics["system"]:
            latest_metrics = [
                m
                for m in self._metrics["system"]
                if isinstance(m, dict) and m.get("timestamp")
            ]
            if latest_metrics:
                latest = latest_metrics[-1]
                summary["latest_system_metrics"] = {
                    "cpu_percent": latest.get("cpu_percent", 0),
                    "memory_percent": latest.get("memory_percent", 0),
                    "timestamp": latest.get("timestamp"),
                }

        return summary

    @property
    def is_monitoring(self) -> bool:
        """是否正在监控."""
        return self._state["monitoring"]

    @property
    def metrics_count(self) -> int:
        """指标数量."""
        return sum(len(metrics) for metrics in self._metrics.values())

    @property
    def alerts_count(self) -> int:
        """告警数量."""
        return len(self._alerts)


class TestRunner:
    """测试运行器."""

    def __init__(self, config_service: "ConfigService"):
        """初始化测试运行器."""
        self.config_service = config_service
        self.logger = logging.getLogger(__name__)
        self._test_results: Dict[str, Any] = {}

    def run_unit_tests(self, test_module: Optional[str] = None) -> Dict[str, Any]:
        """运行单元测试."""
        start_time = time.time()

        # 发现测试
        if test_module:
            try:
                module = __import__(test_module, fromlist=[""])
                loader = unittest.TestLoader()
                suite = loader.loadTestsFromModule(module)
            except (ImportError, AttributeError) as e:
                self.logger.error("加载测试模块失败 %s: %s", test_module, e)
                return {"success": False, "error": str(e)}
        else:
            # 运行核心模块测试
            suite = unittest.TestSuite()

            # 发现所有测试文件
            test_files = [
                "backend.core.test_integration",
                "backend.core.test_performance",
            ]

            for test_file in test_files:
                try:
                    module = __import__(test_file, fromlist=[""])
                    loader = unittest.TestLoader()
                    module_suite = loader.loadTestsFromModule(module)
                    suite.addTests(module_suite)
                except (ImportError, AttributeError) as e:
                    self.logger.warning("加载测试文件失败 %s: %s", test_file, e)

        # 运行测试
        runner = unittest.TextTestRunner(verbosity=2, stream=TestStream())
        result = runner.run(suite)

        end_time = time.time()

        # 保存结果
        test_result = {
            "timestamp": datetime.now(),
            "duration": end_time - start_time,
            "tests_run": result.testsRun,
            "failures": len(result.failures),
            "errors": len(result.errors),
            "success": len(result.failures) == 0 and len(result.errors) == 0,
            "details": {
                "failures": [
                    {"test": str(test), "error": error}
                    for test, error in result.failures
                ],
                "errors": [
                    {"test": str(test), "error": error} for test, error in result.errors
                ],
            },
        }

        self._test_results[datetime.now().isoformat()] = test_result

        self.logger.info(
            "单元测试完成: %s 个测试, %s 个失败, %s 个错误",
            test_result["tests_run"],
            test_result["failures"],
            test_result["errors"],
        )

        return test_result

    def run_integration_tests(self) -> Dict[str, Any]:
        """运行集成测试."""
        start_time = time.time()

        try:
            # 运行集成测试
            # 捕获输出
            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()

            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                exit_code = integration_main()

            output = stdout_capture.getvalue()
            errors = stderr_capture.getvalue()

            success = exit_code == 0

            result = {
                "timestamp": datetime.now(),
                "duration": time.time() - start_time,
                "success": success,
                "exit_code": exit_code,
                "output": output,
                "errors": errors,
            }

            key = f"integration_{datetime.now().isoformat()}"
            self._test_results[key] = result

            if success:
                self.logger.info("集成测试通过")
            else:
                self.logger.error("集成测试失败: %s", errors)

            return result

        except (RuntimeError, OSError) as e:
            self.logger.error("运行集成测试失败: %s", e)
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(),
                "duration": time.time() - start_time,
            }

    def run_performance_tests(self) -> Dict[str, Any]:
        """运行性能测试."""
        start_time = time.time()

        try:
            # 运行性能测试
            # 捕获输出
            stdout_capture = io.StringIO()
            stderr_capture = io.StringIO()

            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                exit_code = performance_main()

            output = stdout_capture.getvalue()
            errors = stderr_capture.getvalue()

            success = exit_code == 0

            result = {
                "timestamp": datetime.now(),
                "duration": time.time() - start_time,
                "success": success,
                "exit_code": exit_code,
                "output": output,
                "errors": errors,
            }

            key = f"performance_{datetime.now().isoformat()}"
            self._test_results[key] = result

            if success:
                self.logger.info("性能测试通过")
            else:
                self.logger.error("性能测试失败: %s", errors)

            return result

        except (RuntimeError, OSError) as e:
            self.logger.error("运行性能测试失败: %s", str(e))
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(),
                "duration": time.time() - start_time,
            }

    def get_test_results(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取测试结果."""
        results = list(self._test_results.values())
        results.sort(key=lambda x: x.get("timestamp") or datetime.min, reverse=True)
        return results[:limit]

    def run_all_tests(self) -> Dict[str, Any]:
        """运行所有测试."""
        results = {}

        self.logger.info("开始运行全套测试")

        # 单元测试
        results["unit_tests"] = self.run_unit_tests()

        # 集成测试
        results["integration_tests"] = self.run_integration_tests()

        # 性能测试
        results["performance_tests"] = self.run_performance_tests()

        # 计算总体结果
        total_success = all(
            [
                results["unit_tests"].get("success", False),
                results["integration_tests"].get("success", False),
                results["performance_tests"].get("success", False),
            ]
        )

        summary = {
            "timestamp": datetime.now(),
            "total_success": total_success,
            "results": results,
        }

        if total_success:
            self.logger.info("🎉 全套测试通过！")
        else:
            self.logger.error("❌ 全套测试存在失败项")

        return summary

    @property
    def last_test_timestamp(self) -> Optional[datetime]:
        """最后测试时间戳."""
        if not self._test_results:
            return None
        last_key = max(self._test_results.keys())
        return self._test_results[last_key].get("timestamp")


class TestStream:
    """测试输出流."""

    def __init__(self):
        """初始化测试输出流."""
        self.content = []

    def write(self, text):
        """写入文本到输出流."""
        self.content.append(text)

    def flush(self):
        """刷新输出流（无操作）."""
        # 无操作 - 兼容StringIO接口

    def getvalue(self):
        """获取输出流的内容."""
        return "".join(self.content)


class HealthChecker:
    """健康检查器."""

    def __init__(self, terminal_engine: TerminalEngine):
        """初始化健康检查器."""
        self.terminal_engine = terminal_engine
        self.logger = logging.getLogger(__name__)
        self._check_results: Dict[str, Any] = {}

    def check_system_health(self) -> Dict[str, Any]:
        """检查系统健康状态."""
        checks = {
            "python": self._check_python_environment(),
            "memory": self._check_memory_usage(),
            "disk": self._check_disk_space(),
            "core_modules": self._check_core_modules(),
            "vnpy": (
                self._check_vnpy_connection()
                if VNPY_AVAILABLE
                else {"status": "unavailable", "message": "VNPY不可用"}
            ),
        }

        # 计算整体健康评分
        health_score = self._calculate_health_score(checks)

        result = {
            "timestamp": datetime.now(),
            "health_score": health_score,
            "status": (
                "healthy"
                if health_score >= 80
                else "warning" if health_score >= 60 else "critical"
            ),
            "checks": checks,
        }

        self._check_results[datetime.now().isoformat()] = result
        return result

    def _check_python_environment(self) -> Dict[str, Any]:
        """检查Python环境."""
        try:
            return {
                "status": "ok",
                "version": sys.version,
                "platform": platform.platform(),
                "python_bits": "64-bit" if sys.maxsize > 2**32 else "32-bit",
            }
        except (RuntimeError, OSError) as e:
            return {"status": "error", "error": str(e)}

    def _check_memory_usage(self) -> Dict[str, Any]:
        """检查内存使用."""
        try:
            memory = psutil.virtual_memory()
            threshold = 80  # 80%

            status = "ok" if memory.percent < threshold else "warning"

            return {
                "status": status,
                "percent": memory.percent,
                "used_mb": memory.used / (1024 * 1024),
                "available_mb": memory.available / (1024 * 1024),
            }
        except (RuntimeError, OSError, psutil.Error) as e:
            return {"status": "error", "error": str(e)}

    def _check_disk_space(self) -> Dict[str, Any]:
        """检查磁盘空间."""
        try:
            disk = psutil.disk_usage("/")
            threshold = 90  # 90%

            status = "ok" if disk.percent < threshold else "warning"

            return {
                "status": status,
                "percent": disk.percent,
                "used_gb": disk.used / (1024 * 1024 * 1024),
                "free_gb": disk.free / (1024 * 1024 * 1024),
            }
        except (RuntimeError, OSError, psutil.Error) as e:
            return {"status": "error", "error": str(e)}

    def _check_core_modules(self) -> Dict[str, Any]:
        """检查核心模块."""
        checks = {}

        try:
            # 检查数据模型管理器
            data_manager = get_data_model_manager()
            if data_manager:
                stats = data_manager.get_statistics()
                checks["data_manager"] = {"status": "ok", "stats": stats}
            else:
                checks["data_manager"] = {
                    "status": "error",
                    "error": "无法获取数据管理器",
                }
        except (RuntimeError, AttributeError) as e:
            checks["data_manager"] = {"status": "error", "error": str(e)}

        try:
            # 检查性能优化器
            optimizer = get_performance_optimizer(self.terminal_engine)
            if optimizer:
                stats = optimizer.get_performance_stats()
                checks["performance_optimizer"] = {"status": "ok", "stats": stats}
            else:
                checks["performance_optimizer"] = {
                    "status": "error",
                    "error": ("无法获取性能优化器"),
                }
        except (RuntimeError, AttributeError) as e:
            checks["performance_optimizer"] = {"status": "error", "error": str(e)}

        return checks

    def _check_vnpy_connection(self) -> Dict[str, Any]:
        """检查VNPY连接."""
        try:
            status = self.terminal_engine.get_status()
            return {
                "status": "ok",
                "vnpy_available": status.get("vnpy_available", False),
                "gateways": len(status.get("gateways", {})),
                "datafeeds": len(status.get("datafeeds", {})),
            }
        except (RuntimeError, AttributeError, ConnectionError) as e:
            return {"status": "error", "error": str(e)}

    def _calculate_health_score(self, checks: Dict[str, Any]) -> float:
        """计算健康评分."""
        scores = []

        # 系统检查评分
        for check_name in ["python", "memory", "disk"]:
            if checks.get(check_name, {}).get("status") == "ok":
                scores.append(100)
            elif checks.get(check_name, {}).get("status") == "warning":
                scores.append(60)
            else:
                scores.append(0)

        # 核心模块评分
        core_modules = checks.get("core_modules", {})
        if core_modules.get("data_manager", {}).get("status") == "ok":
            scores.append(100)
        else:
            scores.append(0)

        if core_modules.get("performance_optimizer", {}).get("status") == "ok":
            scores.append(100)
        else:
            scores.append(0)

        # VNPY评分
        if checks.get("vnpy", {}).get("status") == "ok":
            scores.append(100)
        else:
            scores.append(0)

        return (sum(scores) / len(scores)) if scores else 0

    def get_check_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取检查历史."""
        results = list(self._check_results.values())
        results.sort(key=lambda x: x.get("timestamp") or datetime.min, reverse=True)
        return results[:limit]

    @property
    def last_check_timestamp(self) -> Optional[datetime]:
        """最后检查时间戳."""
        if not self._check_results:
            return None
        last_key = max(self._check_results.keys())
        return self._check_results[last_key].get("timestamp")


class MonitoringManager:
    """监控管理器."""

    def __init__(
        self, config_service: "ConfigService", terminal_engine: TerminalEngine
    ):
        """初始化监控管理器."""
        self.config_service = config_service
        self.terminal_engine = terminal_engine
        self.logger = logging.getLogger(__name__)

        # 初始化组件
        self.performance_monitor = PerformanceMonitor(config_service)
        self.test_runner = TestRunner(config_service)
        self.health_checker = HealthChecker(terminal_engine)

        # 启动监控
        self.start_all_monitoring()

    def start_all_monitoring(self):
        """启动所有监控."""
        self.performance_monitor.start_monitoring()
        self.logger.info("监控管理器启动完成")

    def stop_all_monitoring(self):
        """停止所有监控."""
        self.performance_monitor.stop_monitoring()
        self.logger.info("监控管理器停止完成")

    def run_comprehensive_test(self) -> Dict[str, Any]:
        """运行综合测试."""
        self.logger.info("开始运行综合测试")

        # 健康检查
        health_result = self.health_checker.check_system_health()

        # 全套测试
        test_result = self.test_runner.run_all_tests()

        # 性能指标
        performance_metrics = self.performance_monitor.get_metrics(hours=1)

        # 综合报告
        report = {
            "timestamp": datetime.now(),
            "health": health_result,
            "tests": test_result,
            "performance": performance_metrics,
            "summary": {
                "health_score": health_result.get("health_score", 0),
                "tests_passed": test_result.get("total_success", False),
                "performance_ok": (len(performance_metrics.get("system", [])) > 0),
            },
        }

        self.logger.info(
            "综合测试完成 - 健康评分: %s", report["summary"]["health_score"]
        )
        return report

    def get_status(self) -> Dict[str, Any]:
        """获取监控状态."""
        return {
            "performance_monitor": {
                "active": self.performance_monitor.is_monitoring,
                "metrics_count": self.performance_monitor.metrics_count,
                "alerts_count": self.performance_monitor.alerts_count,
            },
            "health_checker": {"last_check": self.health_checker.last_check_timestamp},
            "test_runner": {"last_test": self.test_runner.last_test_timestamp},
        }


# 导出公共接口
__all__ = ["PerformanceMonitor", "TestRunner", "HealthChecker", "MonitoringManager"]
