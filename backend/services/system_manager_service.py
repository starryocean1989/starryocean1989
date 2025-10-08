# -*- coding: utf-8 -*-
"""
系统管理服务.

提供系统监控和运维管理功能，包括：
- 系统状态监控（CPU、内存、磁盘、网络）
- 性能指标展示（数据处理、策略执行、交易执行）
- 告警管理（规则配置、通知、处理流程）
- 服务健康检查（数据服务、策略服务、交易服务）
- 系统配置管理（参数、数据库、网络、安全）
- 日志管理（收集、查询、分析、监控）
- 系统诊断（性能诊断、错误诊断、网络诊断）
- 工具注册系统
"""

import logging
import psutil
from typing import Any, Dict, List, Optional
from datetime import datetime
from pathlib import Path

from backend.services.base_service import BaseService


class SystemManagerService(BaseService):
    """系统管理服务.

    提供完整的系统监控和管理功能，支持8个子功能：
    1. 系统状态实时监控
    2. 性能指标展示
    3. 告警信息管理
    4. 服务健康检查
    5. 系统配置管理
    6. 日志管理
    7. 系统诊断
    8. 工具集合
    """

    def __init__(self):
        """初始化系统管理服务."""
        super().__init__()

        # 监控数据
        self.monitoring_data: Dict[str, Any] = {}

        # 告警规则
        self.alert_rules: List[Dict[str, Any]] = []

        # 告警历史
        self.alert_history: List[Dict[str, Any]] = []

        # 注册的工具
        self.registered_tools: Dict[str, Any] = {}

        self.logger.info("系统管理服务已创建")

    def _do_initialize(self) -> bool:
        """初始化系统管理服务."""
        try:
            self.logger.info("初始化系统管理服务...")

            # 初始化监控
            self._init_monitoring()

            # 加载默认告警规则
            self._load_default_alert_rules()

            return True

        except Exception as e:
            self._log_error("初始化", e)
            return False

    def _do_shutdown(self) -> bool:
        """关闭系统管理服务."""
        try:
            # 停止监控
            self._stop_monitoring()
            return True
        except Exception as e:
            self._log_error("关闭", e)
            return False

    def _do_health_check(self) -> Dict[str, Any]:
        """健康检查."""
        return {
            "monitoring_active": len(self.monitoring_data) > 0,
            "alert_rule_count": len(self.alert_rules),
            "tool_count": len(self.registered_tools),
        }

    def _init_monitoring(self):
        """初始化监控."""
        try:
            # 收集初始监控数据
            self.update_system_metrics()
            self.logger.info("✅ 系统监控初始化成功")
        except Exception as e:
            self.logger.error("系统监控初始化失败: %s", e)

    def _stop_monitoring(self):
        """停止监控."""
        self.monitoring_data.clear()

    def _load_default_alert_rules(self):
        """加载默认告警规则."""
        self.alert_rules = [
            {
                "name": "CPU使用率过高",
                "metric": "cpu_percent",
                "threshold": 90,
                "enabled": True,
            },
            {
                "name": "内存使用率过高",
                "metric": "memory_percent",
                "threshold": 90,
                "enabled": True,
            },
        ]

    # ==================== 系统状态监控 ====================

    def update_system_metrics(self) -> Dict[str, Any]:
        """更新系统指标.

        Returns:
            Dict: 系统指标
        """
        try:
            metrics = {
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_percent": psutil.virtual_memory().percent,
                "memory_available": psutil.virtual_memory().available,
                "disk_percent": psutil.disk_usage("/").percent,
                "network_sent": psutil.net_io_counters().bytes_sent,
                "network_recv": psutil.net_io_counters().bytes_recv,
                "timestamp": datetime.now().isoformat(),
            }

            self.monitoring_data = metrics

            # 检查告警
            self._check_alerts(metrics)

            return {
                "success": True,
                "metrics": metrics,
            }

        except Exception as e:
            self._log_error("更新系统指标", e)
            return {"success": False, "message": str(e)}

    def get_system_metrics(self) -> Dict[str, Any]:
        """获取系统指标.

        Returns:
            Dict: 系统指标
        """
        return {
            "success": True,
            "metrics": self.monitoring_data,
        }

    def _check_alerts(self, metrics: Dict[str, Any]):
        """检查告警条件.

        Args:
            metrics: 系统指标
        """
        for rule in self.alert_rules:
            if not rule.get("enabled", True):
                continue

            metric_name = rule["metric"]
            threshold = rule["threshold"]

            if metric_name in metrics and metrics[metric_name] > threshold:
                self._trigger_alert(rule, metrics[metric_name])

    def _trigger_alert(self, rule: Dict[str, Any], current_value: float):
        """触发告警.

        Args:
            rule: 告警规则
            current_value: 当前值
        """
        alert = {
            "rule_name": rule["name"],
            "metric": rule["metric"],
            "threshold": rule["threshold"],
            "current_value": current_value,
            "timestamp": datetime.now(),
        }

        self.alert_history.append(alert)

        # 限制历史记录大小
        if len(self.alert_history) > 1000:
            self.alert_history = self.alert_history[-500:]

        self.logger.warning(
            f"告警触发: {rule['name']} - 当前值 {current_value} 超过阈值 {rule['threshold']}"
        )

    # ==================== 服务健康检查 ====================

    def check_all_services(self) -> Dict[str, Any]:
        """检查所有服务健康状态.

        Returns:
            Dict: 服务健康状态
        """
        try:
            from backend.core.shared_services import get_service_manager

            service_manager = get_service_manager()
            service_status = service_manager.get_service_status()

            return {
                "success": True,
                "services": service_status,
            }

        except Exception as e:
            self._log_error("检查服务健康", e)
            return {"success": False, "message": str(e)}

    # ==================== 日志管理 ====================

    def query_logs(
        self,
        level: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """查询日志.

        Args:
            level: 日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
            start_time: 开始时间
            end_time: 结束时间
            limit: 返回数量限制

        Returns:
            Dict: 日志列表
        """
        try:
            # 读取日志文件
            log_dir = Path("logs")
            log_file = log_dir / "terminal_v0.50.log"

            if not log_file.exists():
                return {
                    "success": True,
                    "logs": [],
                    "total": 0,
                    "message": "日志文件不存在",
                }

            # 读取日志
            logs = []
            try:
                with open(log_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()

                # 解析日志行（简单实现）
                for line in lines[-limit:]:  # 只返回最后limit条
                    if level and level.upper() not in line:
                        continue
                    logs.append({"message": line.strip(), "raw": line})

                return {
                    "success": True,
                    "logs": logs,
                    "total": len(logs),
                }

            except Exception as e:
                self.logger.error(f"读取日志文件失败: {e}", exc_info=True)
                return {
                    "success": False,
                    "message": f"读取日志失败: {str(e)}",
                    "logs": [],
                    "total": 0,
                }

        except Exception as e:
            self._log_error("查询日志", e)
            return {"success": False, "message": str(e)}

    # ==================== 系统诊断 ====================

    def run_diagnostics(self) -> Dict[str, Any]:
        """运行系统诊断.

        Returns:
            Dict: 诊断结果
        """
        try:
            diagnostics = {
                "timestamp": datetime.now().isoformat(),
                "performance": self._diagnose_performance(),
                "network": self._diagnose_network(),
                "database": self._diagnose_database(),
            }

            return {
                "success": True,
                "diagnostics": diagnostics,
            }

        except Exception as e:
            self._log_error("运行诊断", e)
            return {"success": False, "message": str(e)}

    def _diagnose_performance(self) -> Dict[str, Any]:
        """性能诊断."""
        try:
            return {
                "cpu_count": psutil.cpu_count(),
                "cpu_freq": psutil.cpu_freq().current if psutil.cpu_freq() else 0,
                "memory_total": psutil.virtual_memory().total,
                "disk_total": psutil.disk_usage("/").total,
            }
        except Exception as e:
            return {"error": str(e)}

    def _diagnose_network(self) -> Dict[str, Any]:
        """网络诊断."""
        try:
            import socket

            # 检查网络连接
            result = {
                "hostname": socket.gethostname(),
                "internet_accessible": False,
            }

            # 尝试连接外部服务器
            try:
                socket.create_connection(("www.baidu.com", 80), timeout=3)
                result["internet_accessible"] = True
            except OSError:
                pass

            return result

        except Exception as e:
            return {"error": str(e)}

    def _diagnose_database(self) -> Dict[str, Any]:
        """数据库诊断."""
        try:
            db_file = Path("data/terminal.db")

            if not db_file.exists():
                return {
                    "exists": False,
                    "message": "数据库文件不存在",
                }

            return {
                "exists": True,
                "size": db_file.stat().st_size,
                "path": str(db_file),
            }

        except Exception as e:
            return {"error": str(e)}
