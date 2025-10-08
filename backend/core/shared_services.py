# -*- coding: utf-8 -*-
"""
共享服务管理器 - 错误追踪和详细报告版本

专注于详细错误报告机制，让用户知道哪里出错了。
不实现多层级降级机制，而是提供完整的错误信息追踪。
"""

import logging
import threading
import traceback
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum
from pathlib import Path

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """错误严重程度."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ServiceError:
    """服务错误信息."""

    def __init__(
        self,
        service_name: str,
        error_type: str,
        message: str,
        exception: Optional[Exception] = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
    ):
        """初始化服务错误对象."""
        self.service_name = service_name
        self.error_type = error_type
        self.message = message
        self.exception = exception
        self.severity = severity
        self.timestamp = datetime.now()
        self.traceback = traceback.format_exc() if exception else None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式."""
        return {
            "service_name": self.service_name,
            "error_type": self.error_type,
            "message": self.message,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
            "traceback": self.traceback,
            "exception_type": type(self.exception).__name__ if self.exception else None,
        }

    def get_user_friendly_message(self) -> str:
        """获取用户友好的错误消息."""
        severity_prefix = {
            ErrorSeverity.INFO: "ℹ️",
            ErrorSeverity.WARNING: "⚠️",
            ErrorSeverity.ERROR: "❌",
            ErrorSeverity.CRITICAL: "🚨",
        }

        prefix = severity_prefix.get(self.severity, "❌")
        time_str = self.timestamp.strftime("%H:%M:%S")

        return f"{prefix} [{time_str}] {self.service_name}: {self.message}"


class ServiceManager:
    """服务管理器 - 专注于错误追踪和详细报告"""

    def __init__(self):
        """初始化服务管理器."""
        self.services = {}
        self.errors = []  # 存储所有错误信息
        self.logger = self._setup_logger()
        self.initialization_attempted = False
        self.initialization_completed = False
        self._lock = threading.RLock()
        self._max_errors_per_service = 50  # 每个服务最多保留50个错误

    def _setup_logger(self):
        """设置错误追踪日志记录器"""
        import logging

        logger = logging.getLogger("ServiceManager")
        logger.setLevel(logging.DEBUG)

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
            handler.setFormatter(formatter)
            logger.addHandler(handler)

        return logger

    def register_service(self, name: str, service: Any) -> bool:
        """注册服务并记录任何错误"""
        try:
            if name in self.services:
                self.record_error(
                    name,
                    "DUPLICATE_REGISTRATION",
                    f"服务 '{name}' 已经注册过了",
                    severity=ErrorSeverity.WARNING,
                )
                return False

            # 验证服务是否可用
            if service is None:
                self.record_error(
                    name, "NULL_SERVICE", f"尝试注册空服务 '{name}'", severity=ErrorSeverity.ERROR
                )
                return False

            self.services[name] = service
            self.logger.info("服务 '%s' 注册成功", name)
            return True

        except Exception as e:
            self.record_error(
                name,
                "REGISTRATION_EXCEPTION",
                f"注册服务 '{name}' 时发生异常: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return False

    def get_service(self, name: str) -> Any:
        """获取服务，记录访问错误"""
        try:
            if name not in self.services:
                self.record_error(
                    name,
                    "SERVICE_NOT_FOUND",
                    f"请求的服务 '{name}' 未找到。可用服务: {list(self.services.keys())}",
                    severity=ErrorSeverity.ERROR,
                )
                return None

            service = self.services[name]
            if service is None:
                self.record_error(
                    name,
                    "NULL_SERVICE_RETRIEVED",
                    f"服务 '{name}' 存在但为空",
                    severity=ErrorSeverity.ERROR,
                )
                return None

            return service

        except Exception as e:
            self.record_error(
                name,
                "SERVICE_ACCESS_EXCEPTION",
                f"访问服务 '{name}' 时发生异常: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return None

    def record_error(
        self,
        service_name: str,
        error_type: str,
        message: str,
        exception: Optional[Exception] = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
    ):
        """记录详细错误信息"""
        error = ServiceError(service_name, error_type, message, exception, severity)

        with self._lock:
            self.errors.append(error)

            # 限制错误数量，防止内存泄漏
            if len(self.errors) > self._max_errors_per_service * 10:
                self.errors = self.errors[-self._max_errors_per_service * 5 :]

        # 同时记录到日志
        log_level = {
            ErrorSeverity.INFO: self.logger.info,
            ErrorSeverity.WARNING: self.logger.warning,
            ErrorSeverity.ERROR: self.logger.error,
            ErrorSeverity.CRITICAL: self.logger.critical,
        }.get(severity, self.logger.error)

        log_level("[%s] %s: %s", service_name, error_type, message)
        if exception and hasattr(exception, "__traceback__"):
            self.logger.error("异常详情: %s", str(exception))

    def get_error_summary(self) -> Dict[str, Any]:
        """获取错误统计摘要"""
        if not self.errors:
            return {
                "total_errors": 0,
                "by_severity": {},
                "by_service": {},
                "by_error_type": {},
                "summary": "无错误记录",
            }

        # 按严重程度统计
        by_severity = {}
        for error in self.errors:
            severity = error.severity.value
            by_severity[severity] = by_severity.get(severity, 0) + 1

        # 按服务统计
        by_service = {}
        for error in self.errors:
            service = error.service_name
            by_service[service] = by_service.get(service, 0) + 1

        # 按错误类型统计
        by_error_type = {}
        for error in self.errors:
            error_type = error.error_type
            by_error_type[error_type] = by_error_type.get(error_type, 0) + 1

        return {
            "total_errors": len(self.errors),
            "by_severity": by_severity,
            "by_service": by_service,
            "by_error_type": by_error_type,
            "summary": f"共记录 {len(self.errors)} 个错误/警告",
        }

    def get_user_friendly_error_report(self) -> str:
        """获取用户友好的错误报告"""
        if not self.errors:
            return "✅ 所有服务运行正常，无错误记录。"

        report_lines = []
        report_lines.append("📋 系统错误报告")
        report_lines.append("=" * 50)

        # 错误统计概览
        summary = self.get_error_summary()
        report_lines.append(f"📊 错误统计: {summary['summary']}")

        # 按严重程度分组显示
        severity_order = [
            ErrorSeverity.CRITICAL,
            ErrorSeverity.ERROR,
            ErrorSeverity.WARNING,
            ErrorSeverity.INFO,
        ]

        for severity in severity_order:
            severity_errors = [e for e in self.errors if e.severity == severity]
            if not severity_errors:
                continue

            severity_icons = {
                ErrorSeverity.CRITICAL: "🔴",
                ErrorSeverity.ERROR: "❌",
                ErrorSeverity.WARNING: "⚠️",
                ErrorSeverity.INFO: "ℹ️",
            }

            icon = severity_icons.get(severity, "❓")
            report_lines.append(f"\n{icon} {severity.value.upper()} ({len(severity_errors)} 项):")
            report_lines.append("-" * 30)

            for error in severity_errors:
                time_str = error.timestamp.strftime("%H:%M:%S")
                report_lines.append(f"  [{time_str}] {error.service_name}")
                report_lines.append(f"    错误类型: {error.error_type}")
                report_lines.append(f"    详细信息: {error.message}")

                if error.exception:
                    report_lines.append(f"    异常: {str(error.exception)}")

                report_lines.append("")

        # 问题解决建议
        report_lines.append("\n💡 建议解决方案:")
        report_lines.append("-" * 30)

        critical_errors = [e for e in self.errors if e.severity == ErrorSeverity.CRITICAL]
        major_errors = [e for e in self.errors if e.severity == ErrorSeverity.ERROR]

        if critical_errors:
            report_lines.append("🔴 严重错误需要立即修复:")
            for error in critical_errors[:3]:  # 只显示前3个
                report_lines.append(f"  - {error.service_name}: {error.message}")

        if major_errors:
            report_lines.append("❌ 主要错误需要优先处理:")
            for error in major_errors[:3]:  # 只显示前3个
                report_lines.append(f"  - {error.service_name}: {error.message}")

        # 服务状态概览
        report_lines.append("\n🔍 服务状态概览:")
        report_lines.append("-" * 30)
        report_lines.append(f"已注册服务数量: {len(self.services)}")
        if self.services:
            report_lines.append(f"可用服务: {', '.join(self.services.keys())}")
        else:
            report_lines.append("⚠️ 当前没有任何已注册的服务")

        return "\n".join(report_lines)

    def clear_errors(self):
        """清空错误记录"""
        with self._lock:
            self.errors.clear()
        self.logger.info("错误记录已清空")

    def get_service_status(self) -> Dict[str, str]:
        """获取所有服务的状态"""
        status = {}
        for name, service in self.services.items():
            if service is None:
                status[name] = "❌ 空服务"
            else:
                # 尝试基本的服务健康检查
                try:
                    if hasattr(service, "is_connected") and callable(service.is_connected):
                        is_connected = service.is_connected()
                        status[name] = "✅ 已连接" if is_connected else "⚠️ 未连接"
                    elif hasattr(service, "status") and callable(service.status):
                        service_status = service.status()
                        status[name] = f"📊 {service_status}"
                    else:
                        status[name] = "✅ 已注册"
                except Exception as e:
                    status[name] = f"❌ 检查失败: {str(e)}"

        return status

    def get_detailed_error_log(self) -> List[Dict[str, Any]]:
        """获取详细的错误日志"""
        with self._lock:
            return [error.to_dict() for error in self.errors]

    def export_error_report(self, file_path: str) -> bool:
        """导出错误报告到文件"""
        try:
            report_data = {
                "timestamp": datetime.now().isoformat(),
                "summary": self.get_error_summary(),
                "user_friendly_report": self.get_user_friendly_error_report(),
                "service_status": self.get_service_status(),
                "detailed_errors": self.get_detailed_error_log(),
            }

            Path(file_path).parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False)

            self.logger.info("错误报告已导出到: %s", file_path)
            return True

        except Exception as e:
            self.record_error(
                "ServiceManager",
                "EXPORT_ERROR",
                f"导出错误报告失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return False


# 全局服务管理器实例
_service_manager: Optional[ServiceManager] = None
_init_lock = threading.Lock()


def get_service_manager() -> ServiceManager:
    """获取全局服务管理器实例."""
    global _service_manager

    if _service_manager is None:
        with _init_lock:
            if _service_manager is None:
                _service_manager = ServiceManager()
                logger.info("全局服务管理器已创建")

    return _service_manager


def initialize_services() -> Dict[str, Any]:
    """初始化所有服务，返回详细的初始化报告"""
    try:
        from .service_initializer import ServiceInitializer

        service_manager = get_service_manager()
        initializer = ServiceInitializer(service_manager)

        # 记录初始化开始
        service_manager.record_error(
            "ServiceManager",
            "INITIALIZATION_START",
            "开始初始化所有服务",
            severity=ErrorSeverity.INFO,
        )

        # 执行初始化
        success = initializer.initialize_all_services()
        service_manager.initialization_attempted = True
        service_manager.initialization_completed = success

        # 生成初始化报告
        if success:
            service_manager.record_error(
                "ServiceManager",
                "INITIALIZATION_SUCCESS",
                "所有服务初始化成功",
                severity=ErrorSeverity.INFO,
            )
            logger.info("服务初始化完成")
        else:
            service_manager.record_error(
                "ServiceManager",
                "INITIALIZATION_PARTIAL_FAILURE",
                "部分服务初始化失败，请查看详细错误信息",
                severity=ErrorSeverity.WARNING,
            )
            logger.warning("服务初始化部分失败")

        # 返回详细报告
        return {
            "success": success,
            "initialization_completed": success,
            "error_summary": service_manager.get_error_summary(),
            "service_status": service_manager.get_service_status(),
            "user_friendly_report": service_manager.get_user_friendly_error_report(),
        }

    except Exception as e:
        service_manager = get_service_manager()
        service_manager.record_error(
            "ServiceManager",
            "INITIALIZATION_EXCEPTION",
            f"服务初始化过程中发生严重异常: {str(e)}",
            exception=e,
            severity=ErrorSeverity.CRITICAL,
        )
        logger.error("服务初始化失败: %s", e, exc_info=True)

        return {
            "success": False,
            "initialization_completed": False,
            "error_summary": service_manager.get_error_summary(),
            "service_status": service_manager.get_service_status(),
            "user_friendly_report": service_manager.get_user_friendly_error_report(),
        }


def shutdown_services() -> None:
    """关闭所有服务."""
    global _service_manager

    if _service_manager:
        _service_manager.record_error(
            "ServiceManager", "SHUTDOWN_START", "开始关闭所有服务", severity=ErrorSeverity.INFO
        )

        # 这里可以添加具体的服务关闭逻辑
        _service_manager = None
        logger.info("全局服务管理器已清理")


def get_error_report() -> str:
    """获取当前的错误报告"""
    service_manager = get_service_manager()
    return service_manager.get_user_friendly_error_report()


def clear_error_log() -> None:
    """清空错误日志"""
    service_manager = get_service_manager()
    service_manager.clear_errors()
