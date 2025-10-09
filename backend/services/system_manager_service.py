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

from typing import Any, Dict, List, Optional
from datetime import datetime
from pathlib import Path

from backend.services.base_and_utils import BaseService
from backend.infrastructure.system_vnpy.system_monitor import SystemMonitor
from backend.infrastructure.system_vnpy.network_utils import NetworkTester, PortScanner
from backend.core.utils import (
    performance_tracker,
    AlertRule,
    AlertSeverity,
    AlertStatus,
    NotificationType,
    alert_engine,
    create_rule_from_template,
)


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

        # system_vnpy工具
        self.system_monitor = SystemMonitor()
        self.network_tester = NetworkTester()
        self.port_scanner = PortScanner()

        # 性能跟踪器
        self.performance_tracker = performance_tracker

        # 告警引擎
        self.alert_engine = alert_engine

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
        # 使用新的告警引擎
        try:
            # CPU使用率过高规则
            cpu_rule = create_rule_from_template("cpu_high", "rule_cpu_high", 90, priority=1)
            self.alert_engine.add_rule(cpu_rule)

            # 内存使用率过高规则
            memory_rule = create_rule_from_template(
                "memory_high", "rule_memory_high", 90, priority=1
            )
            self.alert_engine.add_rule(memory_rule)

            # 磁盘使用率过高规则
            disk_rule = create_rule_from_template("disk_high", "rule_disk_high", 85, priority=2)
            self.alert_engine.add_rule(disk_rule)

            self.logger.info("默认告警规则已加载")
        except Exception as e:
            self.logger.error("加载默认告警规则失败: %s", str(e))

    # ==================== 性能指标展示（三维度：数据处理、策略执行、交易执行） ====================

    def get_performance_indicators(self) -> Dict[str, Any]:
        """获取三维度性能指标.

        返回数据处理、策略执行、交易执行三个维度的性能指标，
        对应需求文档链条1.2.1。

        Returns:
            Dict: 包含三维度性能指标的字典

        Example:
            >>> result = service.get_performance_indicators()
            >>> print(result["data_processing"]["avg_query_time_ms"])
        """
        try:
            all_metrics = self.performance_tracker.get_all_metrics()

            # 数据处理性能
            data_processing = self._calculate_data_processing_metrics(
                all_metrics.get("data_processing", {})
            )

            # 策略执行性能
            strategy_execution = self._calculate_strategy_execution_metrics(
                all_metrics.get("strategy_execution", {})
            )

            # 交易执行性能
            trading_execution = self._calculate_trading_execution_metrics(
                all_metrics.get("trading_execution", {})
            )

            return {
                "success": True,
                "performance_indicators": {
                    "data_processing": data_processing,
                    "strategy_execution": strategy_execution,
                    "trading_execution": trading_execution,
                },
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self._log_error("获取性能指标", e)
            return {"success": False, "message": str(e)}

    def _calculate_data_processing_metrics(
        self, metrics: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """计算数据处理性能指标.

        Args:
            metrics: 数据处理类别的原始指标

        Returns:
            Dict: 聚合后的数据处理性能指标
        """
        # 聚合查询时间
        query_times = []
        download_speeds = []
        cache_hits = 0
        cache_misses = 0

        for metric_name, metric_data in metrics.items():
            if "query" in metric_name.lower():
                query_times.append(metric_data.get("avg_time_ms", 0))
            elif "download" in metric_name.lower():
                # 下载速度估算（基于数据量/时间）
                avg_time = metric_data.get("avg_time_ms", 0)
                if avg_time > 0:
                    # 假设平均每次下载1MB数据
                    download_speeds.append(1000 / avg_time)  # MB/s
            elif "cache" in metric_name.lower():
                total_calls = metric_data.get("total_calls", 0)
                success_rate = metric_data.get("success_rate", 100)
                cache_hits += int(total_calls * success_rate / 100)
                cache_misses += int(total_calls * (100 - success_rate) / 100)

        avg_query_time = sum(query_times) / len(query_times) if query_times else 0.0
        avg_download_speed = sum(download_speeds) / len(download_speeds) if download_speeds else 0.0
        cache_hit_rate = (
            cache_hits / (cache_hits + cache_misses) * 100
            if (cache_hits + cache_misses) > 0
            else 0.0
        )

        return {
            "avg_query_time_ms": round(avg_query_time, 2),
            "avg_download_speed_mbps": round(avg_download_speed, 2),
            "cache_hit_rate": round(cache_hit_rate, 2),
            "total_queries": sum(m.get("total_calls", 0) for m in metrics.values()),
            "metrics_detail": metrics,
        }

    def _calculate_strategy_execution_metrics(
        self, metrics: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """计算策略执行性能指标.

        Args:
            metrics: 策略执行类别的原始指标

        Returns:
            Dict: 聚合后的策略执行性能指标
        """
        signal_latencies = []
        bar_processing_times = []

        for metric_name, metric_data in metrics.items():
            avg_time = metric_data.get("avg_time_ms", 0)

            if "signal" in metric_name.lower() or "order" in metric_name.lower():
                signal_latencies.append(avg_time)
            elif "on_bar" in metric_name.lower() or "process" in metric_name.lower():
                bar_processing_times.append(avg_time)

        avg_signal_latency = (
            sum(signal_latencies) / len(signal_latencies) if signal_latencies else 0.0
        )
        avg_bar_processing = (
            sum(bar_processing_times) / len(bar_processing_times) if bar_processing_times else 0.0
        )

        # 从系统监控获取CPU使用率作为策略CPU占用的近似值
        try:
            resource_usage = self.system_monitor.get_resource_usage()
            strategy_cpu_usage = resource_usage.cpu_percent
        except Exception:
            strategy_cpu_usage = 0.0

        return {
            "avg_signal_latency_ms": round(avg_signal_latency, 2),
            "strategy_cpu_usage_percent": round(strategy_cpu_usage, 2),
            "on_bar_processing_time_ms": round(avg_bar_processing, 2),
            "total_strategy_calls": sum(m.get("total_calls", 0) for m in metrics.values()),
            "metrics_detail": metrics,
        }

    def _calculate_trading_execution_metrics(
        self, metrics: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """计算交易执行性能指标.

        Args:
            metrics: 交易执行类别的原始指标

        Returns:
            Dict: 聚合后的交易执行性能指标
        """
        order_latencies = []
        order_success_rates = []
        position_update_delays = []

        for metric_name, metric_data in metrics.items():
            avg_time = metric_data.get("avg_time_ms", 0)
            success_rate = metric_data.get("success_rate", 100)

            if "order" in metric_name.lower() or "send" in metric_name.lower():
                order_latencies.append(avg_time)
                order_success_rates.append(success_rate)
            elif "position" in metric_name.lower() or "update" in metric_name.lower():
                position_update_delays.append(avg_time)

        avg_order_latency = sum(order_latencies) / len(order_latencies) if order_latencies else 0.0
        avg_order_success_rate = (
            sum(order_success_rates) / len(order_success_rates) if order_success_rates else 100.0
        )
        avg_position_update_delay = (
            sum(position_update_delays) / len(position_update_delays)
            if position_update_delays
            else 0.0
        )

        return {
            "avg_order_latency_ms": round(avg_order_latency, 2),
            "order_success_rate": round(avg_order_success_rate, 2),
            "position_update_delay_ms": round(avg_position_update_delay, 2),
            "total_orders": sum(m.get("total_calls", 0) for m in metrics.values()),
            "metrics_detail": metrics,
        }

    def reset_performance_metrics(self, category: Optional[str] = None) -> Dict[str, Any]:
        """重置性能指标.

        Args:
            category: 指标分类（data_processing/strategy_execution/trading_execution）
                     如不指定则重置所有分类

        Returns:
            Dict: 重置结果
        """
        try:
            if category:
                self.performance_tracker.reset_category(category)
                message = f"性能指标已重置: {category}"
            else:
                self.performance_tracker.reset()
                message = "所有性能指标已重置"

            self.logger.info(message)

            return {
                "success": True,
                "message": message,
            }

        except Exception as e:
            self._log_error("重置性能指标", e)
            return {"success": False, "message": str(e)}

    # ==================== 系统状态监控 ====================

    def update_system_metrics(self) -> Dict[str, Any]:
        """更新系统指标.

        Returns:
            Dict: 系统指标
        """
        try:
            # 使用system_vnpy的SystemMonitor获取系统资源使用情况
            resource_usage = self.system_monitor.get_resource_usage()

            metrics = {
                "cpu_percent": resource_usage.cpu_percent,
                "memory_percent": resource_usage.memory_percent,
                "memory_available": None,  # 可从system_info获取
                "disk_percent": resource_usage.disk_percent,
                "network_sent": resource_usage.network_sent,
                "network_recv": resource_usage.network_recv,
                "process_count": resource_usage.process_count,
                "load_average": resource_usage.load_average,
                "timestamp": resource_usage.timestamp.isoformat(),
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

    def get_system_info(self) -> Dict[str, Any]:
        """获取系统基本信息.

        Returns:
            Dict: 系统基本信息
        """
        try:
            # 使用system_vnpy的SystemMonitor获取系统信息
            system_info = self.system_monitor.get_system_info()

            info = {
                "platform": system_info.platform,
                "platform_version": system_info.platform_version,
                "architecture": system_info.architecture,
                "hostname": system_info.hostname,
                "cpu_count": system_info.cpu_count,
                "cpu_count_logical": system_info.cpu_count_logical,
                "memory_total": system_info.memory_total,
                "disk_total": system_info.disk_total,
                "network_interfaces": system_info.network_interfaces,
                "boot_time": system_info.boot_time.isoformat(),
            }

            return {
                "success": True,
                "info": info,
            }

        except Exception as e:
            self._log_error("获取系统信息", e)
            return {"success": False, "message": str(e)}

    def _check_alerts(self, metrics: Dict[str, Any]):
        """检查告警条件（使用告警引擎）.

        Args:
            metrics: 系统指标
        """
        # 使用告警引擎评估规则
        self.alert_engine.evaluate_rules(metrics)

    # ==================== 告警管理（链条1.3.1） ====================

    def add_alert_rule(self, rule_data: Dict[str, Any]) -> Dict[str, Any]:
        """添加告警规则.

        Args:
            rule_data: 规则数据

        Returns:
            Dict: 添加结果
        """
        try:
            rule = AlertRule(
                rule_id=rule_data["rule_id"],
                name=rule_data["name"],
                condition=rule_data["condition"],
                severity=AlertSeverity(rule_data["severity"]),
                enabled=rule_data.get("enabled", True),
                priority=rule_data.get("priority", 0),
                group=rule_data.get("group", "default"),
                description=rule_data.get("description", ""),
            )

            success = self.alert_engine.add_rule(rule)

            return {
                "success": success,
                "message": "规则已添加" if success else "规则添加失败",
            }

        except Exception as e:
            self._log_error("添加告警规则", e)
            return {"success": False, "message": str(e)}

    def update_alert_rule(self, rule_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
        """更新告警规则.

        Args:
            rule_id: 规则ID
            updates: 更新内容

        Returns:
            Dict: 更新结果
        """
        try:
            success = self.alert_engine.update_rule(rule_id, **updates)

            return {
                "success": success,
                "message": "规则已更新" if success else "规则更新失败",
            }

        except Exception as e:
            self._log_error("更新告警规则", e)
            return {"success": False, "message": str(e)}

    def delete_alert_rule(self, rule_id: str) -> Dict[str, Any]:
        """删除告警规则.

        Args:
            rule_id: 规则ID

        Returns:
            Dict: 删除结果
        """
        try:
            success = self.alert_engine.delete_rule(rule_id)

            return {
                "success": success,
                "message": "规则已删除" if success else "规则删除失败",
            }

        except Exception as e:
            self._log_error("删除告警规则", e)
            return {"success": False, "message": str(e)}

    def get_alert_rules(self, group: Optional[str] = None) -> Dict[str, Any]:
        """获取告警规则列表.

        Args:
            group: 规则分组（可选）

        Returns:
            Dict: 规则列表
        """
        try:
            rules = self.alert_engine.get_all_rules(group)
            rule_list = [rule.to_dict() for rule in rules]

            return {
                "success": True,
                "rules": rule_list,
                "count": len(rule_list),
            }

        except Exception as e:
            self._log_error("获取告警规则", e)
            return {"success": False, "rules": [], "message": str(e)}

    def get_alert_history(
        self,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """查询告警历史.

        Args:
            start_time: 开始时间
            end_time: 结束时间
            severity: 严重程度
            status: 状态
            limit: 返回数量限制

        Returns:
            Dict: 告警历史列表
        """
        try:
            start_dt = datetime.fromisoformat(start_time) if start_time else None
            end_dt = datetime.fromisoformat(end_time) if end_time else None
            severity_enum = AlertSeverity(severity) if severity else None
            status_enum = AlertStatus(status) if status else None

            alerts = self.alert_engine.get_alert_history(
                start_dt, end_dt, severity_enum, status_enum, limit
            )

            alert_list = [alert.to_dict() for alert in alerts]

            return {
                "success": True,
                "alerts": alert_list,
                "count": len(alert_list),
            }

        except Exception as e:
            self._log_error("查询告警历史", e)
            return {"success": False, "alerts": [], "message": str(e)}

    def acknowledge_alert(self, alert_id: str, note: str = "") -> Dict[str, Any]:
        """确认告警.

        Args:
            alert_id: 告警ID
            note: 备注

        Returns:
            Dict: 确认结果
        """
        try:
            success = self.alert_engine.acknowledge_alert(alert_id, note)

            return {
                "success": success,
                "message": "告警已确认" if success else "告警确认失败",
            }

        except Exception as e:
            self._log_error("确认告警", e)
            return {"success": False, "message": str(e)}

    def resolve_alert(self, alert_id: str, note: str = "") -> Dict[str, Any]:
        """解决告警.

        Args:
            alert_id: 告警ID
            note: 备注

        Returns:
            Dict: 解决结果
        """
        try:
            success = self.alert_engine.resolve_alert(alert_id, note)

            return {
                "success": success,
                "message": "告警已解决" if success else "告警解决失败",
            }

        except Exception as e:
            self._log_error("解决告警", e)
            return {"success": False, "message": str(e)}

    def configure_alert_notifications(
        self, notification_type: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """配置告警通知.

        Args:
            notification_type: 通知类型 (email/webhook/desktop)
            config: 配置参数

        Returns:
            Dict: 配置结果
        """
        try:
            notif_type = NotificationType(notification_type)
            self.alert_engine.configure_notifications(notif_type, config)

            return {
                "success": True,
                "message": f"{notification_type}通知已配置",
            }

        except Exception as e:
            self._log_error("配置告警通知", e)
            return {"success": False, "message": str(e)}

    # ==================== 服务健康检查 ====================

    def check_all_services(self) -> Dict[str, Any]:
        """检查所有服务健康状态.

        Returns:
            Dict: 服务健康状态
        """
        try:
            from backend.core.base import get_service_manager

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
        limit: int = 100,
    ) -> Dict[str, Any]:
        """查询日志.

        Args:
            level: 日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
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
            # 使用system_vnpy的SystemMonitor获取系统信息
            system_info = self.system_monitor.get_system_info()

            return {
                "cpu_count": system_info.cpu_count,
                "cpu_count_logical": system_info.cpu_count_logical,
                "memory_total": system_info.memory_total,
                "disk_total": system_info.disk_total,
                "architecture": system_info.architecture,
            }
        except Exception as e:
            return {"error": str(e)}

    def _diagnose_network(self) -> Dict[str, Any]:
        """网络诊断."""
        try:
            # 使用system_vnpy的NetworkTester进行网络诊断
            system_info = self.system_monitor.get_system_info()

            result = {
                "hostname": system_info.hostname,
                "network_interfaces": system_info.network_interfaces,
                "internet_accessible": False,
                "connectivity_tests": {},
            }

            # 测试多个外部服务器连通性
            test_hosts = [
                ("www.baidu.com", 80),
                ("www.google.com", 80),
                ("www.bing.com", 80),
            ]

            accessible_count = 0
            for host, port in test_hosts:
                is_accessible = self.network_tester.test_host(host, port)
                result["connectivity_tests"][host] = is_accessible
                if is_accessible:
                    accessible_count += 1

            # 如果至少有一个服务器可访问，认为网络可用
            result["internet_accessible"] = accessible_count > 0

            return result

        except Exception as e:
            return {"error": str(e)}

    def scan_ports(self, host: str, ports: Optional[List[int]] = None) -> Dict[str, Any]:
        """扫描指定主机的端口.

        Args:
            host: 主机地址
            ports: 端口列表（如不提供则扫描常用端口）

        Returns:
            Dict: 端口扫描结果
        """
        try:
            if ports is None:
                # 默认扫描常用端口
                ports = [21, 22, 23, 25, 80, 443, 3306, 3389, 5432, 6379, 8000, 8080, 9000]

            # 使用system_vnpy的PortScanner
            scan_results = self.port_scanner.scan(host, ports)

            return {
                "success": True,
                "host": host,
                "scan_results": scan_results,
            }

        except Exception as e:
            self._log_error("端口扫描", e)
            return {"success": False, "message": str(e)}

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

    # ==================== 配置管理 ====================

    def get_all_configs(self) -> Dict[str, Any]:
        """获取所有模块的配置项（集中展示）.

        聚合以下模块配置：
        1. 数据中心配置 (data_module_vnpy)
        2. VnPy配置
        3. AI助手配置
        4. 数据库配置
        5. 网络配置

        Returns:
            Dict: 所有配置项
        """
        try:
            configs = {}

            # 1. 数据中心配置（来自data_module_vnpy）
            try:
                from backend.infrastructure.data_module_vnpy.config import config_manager

                configs["data_center"] = {
                    "cache_dir": config_manager.get("chinastock.cache_dir"),
                    "data_dir": config_manager.get("chinastock.data_dir"),
                    "tdx_dir": config_manager.get("chinastock.tdx_dir"),
                    "base_date": config_manager.get("chinastock.base_date"),
                    "max_workers": config_manager.get("chinastock.max_workers"),
                    "timeout": config_manager.get("chinastock.timeout"),
                    "retry_times": config_manager.get("chinastock.retry_times"),
                    "enable_watcher": config_manager.get("chinastock.enable_watcher"),
                    "watcher_interval": config_manager.get("chinastock.watcher_interval"),
                }
            except Exception as e:
                self.logger.warning(f"获取数据中心配置失败: {e}")
                configs["data_center"] = {}

            # 2. VnPy配置
            try:
                from backend.config import get_settings

                settings = get_settings()
                configs["vnpy"] = {
                    "event_engine_timer_interval": settings.vnpy.event_engine_timer_interval,
                    "data_storage_path": settings.vnpy.data_storage_path,
                    "log_level": settings.vnpy.log_level,
                    "log_file": settings.vnpy.log_file,
                }
            except Exception as e:
                self.logger.warning(f"获取VnPy配置失败: {e}")
                configs["vnpy"] = {}

            # 3. AI助手配置
            try:
                from backend.config import get_settings

                settings = get_settings()
                configs["ai"] = {
                    "provider": settings.ai.provider,
                    "api_key": settings.ai.api_key if settings.ai.api_key else "",
                    "api_url": settings.ai.api_url,
                    "model": settings.ai.model,
                    "max_tokens": settings.ai.max_tokens,
                    "temperature": settings.ai.temperature,
                    "timeout": settings.ai.timeout,
                    "max_history": settings.ai.max_history,
                    "system_prompt": settings.ai.system_prompt,
                }
            except Exception as e:
                self.logger.warning(f"获取AI配置失败: {e}")
                configs["ai"] = {}

            # 4. 数据库配置
            try:
                from backend.config import get_settings

                settings = get_settings()
                configs["database"] = {
                    "sqlite_path": settings.database.sqlite_path,
                    "sqlite_timeout": settings.database.sqlite_timeout,
                }
            except Exception as e:
                self.logger.warning(f"获取数据库配置失败: {e}")
                configs["database"] = {}

            # 5. 网络配置（WebSocket + API）
            try:
                from backend.config import get_settings

                settings = get_settings()
                configs["network"] = {
                    "ws_max_connections": settings.websocket.max_connections,
                    "ws_connection_timeout": settings.websocket.connection_timeout,
                    "ws_ping_interval": settings.websocket.ping_interval,
                    "api_host": settings.api.host,
                    "api_port": settings.api.port,
                    "api_debug": settings.api.debug,
                }
            except Exception as e:
                self.logger.warning(f"获取网络配置失败: {e}")
                configs["network"] = {}

            return {
                "success": True,
                "configs": configs,
            }

        except Exception as e:
            self._log_error("获取所有配置", e)
            return {"success": False, "message": str(e)}

    def update_config(self, module: str, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """更新指定模块的配置.

        Args:
            module: 模块名称 (data_center/vnpy/ai/database/network)
            config_data: 配置数据字典

        Returns:
            Dict: 更新结果
        """
        try:
            if module == "data_center":
                # 更新data_module_vnpy配置
                from backend.infrastructure.data_module_vnpy.config import config_manager

                # 转换为chinastock.前缀
                chinastock_config = {}
                for key, value in config_data.items():
                    chinastock_config[f"chinastock.{key}"] = value

                config_manager.update_config(chinastock_config)

            elif module in ["vnpy", "ai", "database", "network"]:
                # 更新backend配置
                from backend.config import get_settings

                settings = get_settings()

                if module == "vnpy":
                    for key, value in config_data.items():
                        if hasattr(settings.vnpy, key):
                            setattr(settings.vnpy, key, value)

                elif module == "ai":
                    for key, value in config_data.items():
                        if hasattr(settings.ai, key):
                            setattr(settings.ai, key, value)

                elif module == "database":
                    for key, value in config_data.items():
                        if hasattr(settings.database, key):
                            setattr(settings.database, key, value)

                elif module == "network":
                    # 网络配置需要分别更新websocket和api
                    for key, value in config_data.items():
                        if key.startswith("ws_"):
                            ws_key = key[3:]  # 移除ws_前缀
                            if hasattr(settings.websocket, ws_key):
                                setattr(settings.websocket, ws_key, value)
                        elif key.startswith("api_"):
                            api_key = key[4:]  # 移除api_前缀
                            if hasattr(settings.api, api_key):
                                setattr(settings.api, api_key, value)

                # 保存到文件
                config_file = Path("config/terminal_config.json")
                settings.save_to_file(str(config_file))

            else:
                return {
                    "success": False,
                    "message": f"未知模块: {module}",
                }

            self.logger.info(f"配置已更新: {module} - {list(config_data.keys())}")

            return {
                "success": True,
                "message": f"{module}配置已更新",
            }

        except Exception as e:
            self._log_error(f"更新配置[{module}]", e)
            return {"success": False, "message": str(e)}

    def save_config(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """保存系统配置.

        Args:
            config_data: 配置数据字典

        Returns:
            Dict: 保存结果
        """
        try:
            import json

            # 配置文件路径
            config_file = Path("config/terminal_config.json")
            config_file.parent.mkdir(parents=True, exist_ok=True)

            # 加载现有配置（如果存在）
            if config_file.exists():
                with open(config_file, "r", encoding="utf-8") as f:
                    existing_config = json.load(f)
            else:
                existing_config = {}

            # 合并配置
            existing_config.update(config_data)

            # 保存配置
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(existing_config, f, indent=4, ensure_ascii=False)

            self.logger.info(f"配置已保存: {list(config_data.keys())}")

            return {
                "success": True,
                "message": f"配置已保存 ({len(config_data)}项)",
                "config_file": str(config_file),
            }

        except Exception as e:
            self._log_error("保存配置", e)
            return {
                "success": False,
                "message": f"保存配置失败: {str(e)}",
            }

    def load_config(self) -> Dict[str, Any]:
        """加载系统配置.

        Returns:
            Dict: 配置数据
        """
        try:
            import json

            config_file = Path("config/terminal_config.json")

            if not config_file.exists():
                return {
                    "success": True,
                    "config": {},
                    "message": "配置文件不存在，返回空配置",
                }

            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            self.logger.info(f"配置已加载: {len(config)}项")

            return {
                "success": True,
                "config": config,
                "message": f"配置已加载 ({len(config)}项)",
            }

        except Exception as e:
            self._log_error("加载配置", e)
            return {
                "success": False,
                "config": {},
                "message": f"加载配置失败: {str(e)}",
            }

    # ==================== 工具注册系统 ====================

    def register_tool(self, tool_info: Dict[str, Any]) -> Dict[str, Any]:
        """注册工具.

        Args:
            tool_info: 工具信息，包含name, description, command等

        Returns:
            Dict: 注册结果
        """
        try:
            tool_name = tool_info.get("name")
            if not tool_name:
                return {
                    "success": False,
                    "message": "工具名称不能为空",
                }

            if tool_name in self.registered_tools:
                return {
                    "success": False,
                    "message": f"工具 '{tool_name}' 已经注册",
                }

            # 注册工具
            self.registered_tools[tool_name] = {
                "name": tool_name,
                "description": tool_info.get("description", ""),
                "command": tool_info.get("command", ""),
                "parameters": tool_info.get("parameters", {}),
                "registered_at": datetime.now().isoformat(),
            }

            self.logger.info(f"工具已注册: {tool_name}")

            return {
                "success": True,
                "message": f"工具 '{tool_name}' 注册成功",
            }

        except Exception as e:
            self._log_error("注册工具", e)
            return {
                "success": False,
                "message": f"注册工具失败: {str(e)}",
            }

    def get_tools(self) -> Dict[str, Any]:
        """获取所有注册的工具.

        Returns:
            Dict: 工具列表
        """
        try:
            return {
                "success": True,
                "tools": list(self.registered_tools.values()),
                "count": len(self.registered_tools),
            }

        except Exception as e:
            self._log_error("获取工具列表", e)
            return {
                "success": False,
                "tools": [],
                "message": f"获取工具列表失败: {str(e)}",
            }

    def remove_tool(self, tool_name: str) -> Dict[str, Any]:
        """移除已注册的工具.

        Args:
            tool_name: 工具名称

        Returns:
            Dict: 移除结果
        """
        try:
            if tool_name not in self.registered_tools:
                return {
                    "success": False,
                    "message": f"工具 '{tool_name}' 未注册",
                }

            del self.registered_tools[tool_name]

            self.logger.info(f"工具已移除: {tool_name}")

            return {
                "success": True,
                "message": f"工具 '{tool_name}' 已移除",
            }

        except Exception as e:
            self._log_error("移除工具", e)
            return {
                "success": False,
                "message": f"移除工具失败: {str(e)}",
            }
