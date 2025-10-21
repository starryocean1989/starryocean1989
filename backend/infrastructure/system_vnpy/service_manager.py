# -*- coding: utf-8 -*-
"""
服务管理模块.

提供服务健康检查、服务重启等服务管理功能.
"""

import logging
import threading
import time
from typing import Any, Dict

import psutil

logger = logging.getLogger(__name__)


class ServiceHealthChecker:
    """增强版服务健康检查器 - 支持业务指标、资源占用、外部依赖检查."""

    def __init__(self):
        """初始化服务健康检查器."""
        self.logger = logging.getLogger(__name__)
        self._monitoring_interval = 2  # 默认2秒推送频率
        self._main_process = psutil.Process()

    def set_monitoring_interval(self, interval: int):
        """设置监控推送频率.

        Args:
            interval: 推送间隔（秒），范围1-10
        """
        self._monitoring_interval = max(1, min(10, interval))
        self.logger.info("监控推送频率已设置为 %d 秒", self._monitoring_interval)

    def get_monitoring_interval(self) -> int:
        """获取当前监控推送频率."""
        return self._monitoring_interval

    def quick_check(self, service_name: str, service_manager) -> Dict[str, Any]:
        """快速检查服务健康状态（增强版）.

        Args:
            service_name: 服务名称
            service_manager: 服务管理器实例

        Returns:
            Dict: 检查结果，包含基础指标、业务指标、资源占用
        """
        try:
            # 获取服务实例
            service = service_manager.get_service(service_name)

            if not service:
                return {
                    "service_name": service_name,
                    "status": "not_found",
                    "online": False,
                    "response_time_ms": 0,
                    "message": "服务未注册",
                    "call_count": 0,
                    "success_rate": 0.0,
                    "error_rate": 0.0,
                    "memory_mb": 0.0,
                    "thread_count": 0,
                }

            # 检查服务是否初始化
            is_initialized = getattr(service, "is_initialized", False)

            # 测量响应时间（通过调用health_check）
            start_time = time.time()
            try:
                health_result = service.health_check() if hasattr(service, "health_check") else {}
                response_time_ms = (time.time() - start_time) * 1000

                # 收集业务指标（从性能跟踪器获取）
                call_count = 0
                success_rate = 100.0
                error_rate = 0.0

                try:
                    from backend.services.system_manager_service import performance_tracker

                    # 尝试从性能跟踪器获取服务相关指标
                    all_metrics = performance_tracker.get_all_metrics()
                    # 查找与服务相关的指标
                    service_metrics = {}
                    for _category, metrics_list in all_metrics.items():
                        # metrics_list 是一个列表，包含多个指标字典
                        for metric_dict in metrics_list:
                            # 遍历字典中的每个指标
                            for metric_name, metric_value in metric_dict.items():
                                if service_name.replace("_service", "") in metric_name.lower():
                                    # 存储指标值（注意：这里的 metric_value 可能是数值，不是字典）
                                    if isinstance(metric_value, dict):
                                        service_metrics[metric_name] = metric_value

                    # 聚合业务指标
                    if service_metrics:
                        total_calls = sum(m.get("total_calls", 0) for m in service_metrics.values())
                        if total_calls > 0:
                            call_count = total_calls
                            # 计算平均成功率
                            success_rates = [
                                m.get("success_rate", 100) for m in service_metrics.values()
                            ]
                            success_rate = sum(success_rates) / len(success_rates)
                            error_rate = 100.0 - success_rate
                except Exception as e:
                    self.logger.debug("获取业务指标失败 %s: %s", service_name, e)

                # 收集资源占用指标
                memory_mb = 0.0
                thread_count = 0

                try:
                    # 获取当前进程的内存占用
                    memory_info = self._main_process.memory_info()
                    memory_mb = memory_info.rss / (1024 * 1024)

                    # 获取线程数
                    thread_count = threading.active_count()
                except Exception as e:
                    self.logger.debug("获取资源占用失败 %s: %s", service_name, e)

                return {
                    "service_name": service_name,
                    "status": "online",
                    "online": True,
                    "initialized": is_initialized,
                    "response_time_ms": round(response_time_ms, 2),
                    "health_details": health_result,
                    "message": "服务正常",
                    # 业务指标
                    "call_count": call_count,
                    "success_rate": round(success_rate, 2),
                    "error_rate": round(error_rate, 2),
                    # 资源占用
                    "memory_mb": round(memory_mb, 2),
                    "thread_count": thread_count,
                }
            except Exception as e:
                response_time_ms = (time.time() - start_time) * 1000
                return {
                    "service_name": service_name,
                    "status": "error",
                    "online": False,
                    "response_time_ms": round(response_time_ms, 2),
                    "message": f"健康检查失败: {str(e)}",
                    "call_count": 0,
                    "success_rate": 0.0,
                    "error_rate": 100.0,
                    "memory_mb": 0.0,
                    "thread_count": 0,
                }

        except Exception as e:
            self.logger.error("快速检查服务失败 %s: %s", service_name, e)
            return {
                "service_name": service_name,
                "status": "error",
                "online": False,
                "response_time_ms": 0,
                "message": f"检查失败: {str(e)}",
                "call_count": 0,
                "success_rate": 0.0,
                "error_rate": 100.0,
                "memory_mb": 0.0,
                "thread_count": 0,
            }

    def check_response_time(self, service_name: str, service_manager) -> float:
        """检查服务响应时间.

        Args:
            service_name: 服务名称
            service_manager: 服务管理器实例

        Returns:
            float: 响应时间（毫秒）
        """
        try:
            service = service_manager.get_service(service_name)
            if not service:
                return -1.0

            start_time = time.time()

            # 调用一个轻量级方法
            if hasattr(service, "health_check"):
                service.health_check()

            response_time_ms = (time.time() - start_time) * 1000
            return round(response_time_ms, 2)

        except Exception as e:
            self.logger.error("检查响应时间失败 %s: %s", service_name, e)
            return -1.0

    def check_external_dependencies(self) -> Dict[str, Any]:
        """检查外部依赖状态.

        Returns:
            Dict: 外部依赖检查结果
        """
        dependencies = {}

        # 1. 检查EventEngine
        try:
            from backend.core.base import get_event_engine

            event_engine = get_event_engine()
            if event_engine:
                dependencies["event_engine"] = {
                    "name": "VnPy EventEngine",
                    "status": "online",
                    "online": True,
                    "message": "事件引擎运行正常",
                }
            else:
                dependencies["event_engine"] = {
                    "name": "VnPy EventEngine",
                    "status": "offline",
                    "online": False,
                    "message": "事件引擎未初始化",
                }
        except Exception as e:
            dependencies["event_engine"] = {
                "name": "VnPy EventEngine",
                "status": "error",
                "online": False,
                "message": f"检查失败: {str(e)}",
            }

        # 2. 检查数据库连接
        try:
            import sqlite3
            from pathlib import Path
            from backend.infrastructure.data_module_vnpy.config import config_manager

            db_file = config_manager.get_db_file()
            if db_file.exists():
                # 尝试连接数据库
                conn = sqlite3.connect(str(db_file), timeout=1)
                conn.close()
                dependencies["database"] = {
                    "name": "SQLite数据库",
                    "status": "online",
                    "online": True,
                    "message": "数据库连接正常",
                }
            else:
                dependencies["database"] = {
                    "name": "SQLite数据库",
                    "status": "offline",
                    "online": False,
                    "message": "数据库文件不存在",
                }
        except Exception as e:
            dependencies["database"] = {
                "name": "SQLite数据库",
                "status": "error",
                "online": False,
                "message": f"连接失败: {str(e)}",
            }

        return dependencies

    def check_all_services(self, service_manager) -> Dict[str, Any]:
        """检查所有注册的服务（增强版 - 包含外部依赖）.

        Args:
            service_manager: 服务管理器实例

        Returns:
            Dict: 所有服务的检查结果，包含外部依赖状态
        """
        try:
            service_status = service_manager.get_service_status()
            results = []

            online_count = 0
            total_response_time = 0

            for service_name, _status in service_status.items():
                check_result = self.quick_check(service_name, service_manager)
                results.append(check_result)

                if check_result["online"]:
                    online_count += 1
                    total_response_time += check_result["response_time_ms"]

            total_count = len(results)
            health_score = (online_count / total_count * 100) if total_count > 0 else 0
            avg_response_time = (total_response_time / online_count) if online_count > 0 else 0

            # 检查外部依赖
            external_dependencies = self.check_external_dependencies()

            # 计算外部依赖健康度
            dep_online = sum(
                1 for dep in external_dependencies.values() if dep.get("online") is True
            )
            dep_total = len(external_dependencies)
            dep_health_score = (dep_online / dep_total * 100) if dep_total > 0 else 0

            # 综合健康评分（服务权重70%，依赖权重30%）
            overall_health_score = health_score * 0.7 + dep_health_score * 0.3

            return {
                "success": True,
                "total_services": total_count,
                "online_services": online_count,
                "health_score": round(overall_health_score, 1),
                "service_health_score": round(health_score, 1),
                "dependency_health_score": round(dep_health_score, 1),
                "avg_response_time_ms": round(avg_response_time, 2),
                "services": results,
                "external_dependencies": external_dependencies,
            }

        except Exception as e:
            self.logger.error("检查所有服务失败: %s", e)
            return {
                "success": False,
                "message": f"检查失败: {str(e)}",
                "services": [],
                "external_dependencies": {},
            }


class ServiceRestarter:
    """服务重启管理器."""

    def __init__(self):
        """初始化服务重启管理器."""
        self.logger = logging.getLogger(__name__)

    def restart_service(self, service_name: str, service_manager) -> Dict[str, Any]:
        """重启指定服务.

        Args:
            service_name: 服务名称
            service_manager: 服务管理器实例

        Returns:
            Dict: 重启结果
        """
        try:
            self.logger.info("开始重启服务: %s", service_name)

            # 获取服务实例
            service = service_manager.get_service(service_name)

            if not service:
                return {
                    "success": False,
                    "message": f"服务 {service_name} 未注册",
                }

            # 关闭服务
            if hasattr(service, "shutdown"):
                try:
                    service.shutdown()
                    self.logger.info("服务 %s 已关闭", service_name)
                except Exception as e:
                    self.logger.warning("关闭服务失败 %s: %s", service_name, e)

            # 等待一小段时间
            time.sleep(0.5)

            # 重新初始化服务
            if hasattr(service, "initialize"):
                try:
                    success = service.initialize()
                    if success:
                        self.logger.info("服务 %s 已重新初始化", service_name)
                        return {
                            "success": True,
                            "message": f"服务 {service_name} 重启成功",
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"服务 {service_name} 初始化失败",
                        }
                except Exception as e:
                    self.logger.error("初始化服务失败 %s: %s", service_name, e)
                    return {
                        "success": False,
                        "message": f"初始化失败: {str(e)}",
                    }
            else:
                return {
                    "success": False,
                    "message": f"服务 {service_name} 不支持重启",
                }

        except Exception as e:
            self.logger.error("重启服务失败 %s: %s", service_name, e)
            return {
                "success": False,
                "message": f"重启失败: {str(e)}",
            }

    def graceful_restart(
        self, service_name: str, service_manager, timeout: int = 30
    ) -> Dict[str, Any]:
        """优雅地重启服务（带超时控制）.

        Args:
            service_name: 服务名称
            service_manager: 服务管理器实例
            timeout: 超时时间（秒）

        Returns:
            Dict: 重启结果
        """
        try:
            self.logger.info("开始优雅重启服务: %s (timeout=%ds)", service_name, timeout)

            start_time = time.time()

            # 获取服务实例
            service = service_manager.get_service(service_name)

            if not service:
                return {
                    "success": False,
                    "message": f"服务 {service_name} 未注册",
                }

            # 优雅关闭
            if hasattr(service, "shutdown"):
                try:
                    service.shutdown()
                    self.logger.info("服务 %s 已优雅关闭", service_name)
                except Exception as e:
                    self.logger.warning("关闭服务失败 %s: %s", service_name, e)
                    # 继续执行，尝试重新初始化

            # 检查是否超时
            elapsed = time.time() - start_time
            if elapsed > timeout:
                return {
                    "success": False,
                    "message": f"关闭服务超时 ({elapsed:.1f}s)",
                }

            # 等待资源释放
            time.sleep(1)

            # 重新初始化
            if hasattr(service, "initialize"):
                try:
                    success = service.initialize()

                    elapsed = time.time() - start_time

                    if success:
                        self.logger.info(
                            "服务 %s 优雅重启成功 (耗时: %.1fs)",
                            service_name,
                            elapsed,
                        )
                        return {
                            "success": True,
                            "message": f"服务 {service_name} 优雅重启成功",
                            "elapsed_time": round(elapsed, 1),
                        }
                    else:
                        return {
                            "success": False,
                            "message": f"服务 {service_name} 初始化失败",
                            "elapsed_time": round(elapsed, 1),
                        }

                except Exception as e:
                    elapsed = time.time() - start_time
                    self.logger.error("初始化服务失败 %s: %s", service_name, e)
                    return {
                        "success": False,
                        "message": f"初始化失败: {str(e)}",
                        "elapsed_time": round(elapsed, 1),
                    }
            else:
                return {
                    "success": False,
                    "message": f"服务 {service_name} 不支持重启",
                }

        except Exception as e:
            elapsed = time.time() - start_time
            self.logger.error("优雅重启服务失败 %s: %s", service_name, e)
            return {
                "success": False,
                "message": f"重启失败: {str(e)}",
                "elapsed_time": round(elapsed, 1),
            }


# 导出类
__all__ = [
    "ServiceHealthChecker",
    "ServiceRestarter",
]
