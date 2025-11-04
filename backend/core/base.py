# -*- coding: utf-8 -*-
"""
核心基础模块 - 合并版本.

整合了以下模块：
- imports: 集中导入管理
- shared_services: 共享服务管理器
- service_initializer: 服务初始化器

提供统一的核心基础设施，包括导入、服务管理和初始化流程。
"""

# =============================================================================
# Part 1: 基础导入和VnPy集成
# =============================================================================

import datetime
import json
import logging
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from enum import Enum

# 从vnpy_imports导入所有VnPy相关功能
from backend.services.vnpy_imports import (
    # 数据处理库
    pd,
    np,
    PANDAS_AVAILABLE,
    NUMPY_AVAILABLE,
    # 系统监控
    psutil,
    PSUTIL_AVAILABLE,
    # VnPy核心
    VNPY_AVAILABLE,
    MainEngine,
    EventEngine,
    Event,
    TickData,
    BarData,
    OrderData,
    TradeData,
    PositionData,
    AccountData,
    EVENT_TICK,
    EVENT_ORDER,
    EVENT_TRADE,
    EVENT_POSITION,
    EVENT_ACCOUNT,
    EVENT_LOG,
    # VnPy策略引擎
    CTA_ENGINE,
    ALGO_ENGINE,
    PORTFOLIO_ENGINE,
    CTA_ENGINE_AVAILABLE,
    ALGO_ENGINE_AVAILABLE,
    PORTFOLIO_ENGINE_AVAILABLE,
    # VnPy网关
    CTP_GATEWAY,
    IB_GATEWAY,
    PAPER_ACCOUNT_GATEWAY,
    CTP_GATEWAY_AVAILABLE,
    IB_GATEWAY_AVAILABLE,
    PAPERACCOUNT_GATEWAY_AVAILABLE,
    # VnPy数据源
    TUSHARE_DATAFEED,
    RQDATA_DATAFEED,
    TUSHARE_DATAFEED_AVAILABLE,
    RQDATA_DATAFEED_AVAILABLE,
    # Infrastructure
    SystemMonitor,
    ProcessManager,
    SYSTEM_MODULE_AVAILABLE,
    # 工具函数
    setup_logging,
    vnpy_to_pandas,
    # 别名定义
    CtpGateway,
    IbGateway,
    PaperAccountGateway,
    PortfolioEngine,
    RqdataDatafeed,
    TushareDatafeed,
)

# 导入监控版EventEngine（用于队列深度和延迟监控）
from backend.infrastructure.system_vnpy import MonitoredEventEngine


# =============================================================================
# Part 2: 共享服务管理器 (来自 shared_services.py)
# =============================================================================


class ErrorSeverity(Enum):
    """错误严重程度."""

    DEBUG = "debug"  # 🆕 架构修复：添加DEBUG级别（用于非关键路径的信息记录）
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
        self.timestamp = datetime.datetime.now()
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

        return "%s [%s] %s: %s" % (prefix, time_str, self.service_name, self.message)


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
        """设置错误追踪日志记录器.

        简化版：依赖LoggingHub的托管模式，不手动创建handler
        """
        import logging

        # 使用标准logger命名，handler由LoggingHub统一管理
        return logging.getLogger("backend.core.service_manager")

    def register_service(self, name: str, service: Any) -> bool:
        """注册服务并记录任何错误"""
        try:
            if name in self.services:
                # 🎯 架构修复：重复注册降级为DEBUG
                # 在快速启动模式下，调用方已经检查服务是否存在
                # 如果到达这里说明是防御性检查，不应该输出WARNING
                self.record_error(
                    name,
                    "DUPLICATE_REGISTRATION",
                    "服务 '%s' 已经注册过了" % name,
                    severity=ErrorSeverity.DEBUG,  # 降级为DEBUG
                )
                return False

            # 验证服务是否可用
            if service is None:
                self.record_error(
                    name, "NULL_SERVICE", "尝试注册空服务 '%s'" % name, severity=ErrorSeverity.ERROR
                )
                return False

            self.services[name] = service
            self.logger.debug("服务 '%s' 注册成功", name)
            return True

        except Exception as e:
            self.record_error(
                name,
                "REGISTRATION_EXCEPTION",
                "注册服务 '%s' 时发生异常: %s" % (name, str(e)),
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return False

    def get_service(self, name: str, silent: bool = False) -> Any:
        """获取服务.

        Args:
            name: 服务名称
            silent: 是否静默模式（服务不存在时不记录错误，适用于可选服务查询）

        Returns:
            服务实例，如果不存在则返回None
        """
        try:
            if name not in self.services:
                if not silent:
                    # 🎯 架构修复：在快速启动模式下，查询可选服务是正常行为
                    # 只有在非静默模式下才记录错误（用于核心服务的严格检查）
                    self.record_error(
                        name,
                        "SERVICE_NOT_FOUND",
                        "请求的服务 '%s' 未找到。可用服务: %s" % (name, list(self.services.keys())),
                        severity=ErrorSeverity.DEBUG,  # 降级为DEBUG，避免误导
                    )
                return None

            service = self.services[name]
            if service is None:
                if not silent:
                    self.record_error(
                        name,
                        "NULL_SERVICE_RETRIEVED",
                        "服务 '%s' 存在但为空" % name,
                        severity=ErrorSeverity.ERROR,
                    )
                return None

            return service

        except Exception as e:
            if not silent:
                self.record_error(
                    name,
                    "SERVICE_ACCESS_EXCEPTION",
                    "访问服务 '%s' 时发生异常: %s" % (name, str(e)),
                    exception=e,
                    severity=ErrorSeverity.ERROR,
                )
            return None

    def has_service(self, name: str) -> bool:
        """检查服务是否已注册.

        Args:
            name: 服务名称

        Returns:
            bool: 服务是否存在
        """
        return name in self.services

    def list_services(self) -> List[str]:
        """获取所有已注册的服务名称列表

        Returns:
            List[str]: 服务名称列表
        """
        with self._lock:
            return list(self.services.keys())

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
        # 🎯 架构修复：添加DEBUG级别的日志映射
        log_level = {
            ErrorSeverity.DEBUG: self.logger.debug,  # DEBUG级别使用debug日志
            ErrorSeverity.INFO: self.logger.info,
            ErrorSeverity.WARNING: self.logger.warning,
            ErrorSeverity.ERROR: self.logger.error,
            ErrorSeverity.CRITICAL: self.logger.critical,
        }.get(severity, self.logger.error)

        log_level("[%s] %s: %s", service_name, error_type, message, extra={"log_type": "SYSTEM"})

        # 🎯 架构修复：DEBUG级别的异常详情也用debug输出，避免误导
        if exception and hasattr(exception, "__traceback__"):
            if severity == ErrorSeverity.DEBUG:
                self.logger.debug("异常详情：%s", str(exception))
            else:
                self.logger.error("异常详情：%s", str(exception), extra={"log_type": "SYSTEM"})

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
            "summary": "共记录 %d 个错误/警告" % len(self.errors),
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
        report_lines.append("📊 错误统计: %s" % summary["summary"])

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
            report_lines.append(
                "\n%s %s (%d 项):" % (icon, severity.value.upper(), len(severity_errors))
            )
            report_lines.append("-" * 30)

            for error in severity_errors:
                time_str = error.timestamp.strftime("%H:%M:%S")
                report_lines.append("  [%s] %s" % (time_str, error.service_name))
                report_lines.append("    错误类型: %s" % error.error_type)
                report_lines.append("    详细信息: %s" % error.message)

                if error.exception:
                    report_lines.append("    异常: %s" % str(error.exception))

                report_lines.append("")

        # 问题解决建议
        report_lines.append("\n💡 建议解决方案:")
        report_lines.append("-" * 30)

        critical_errors = [e for e in self.errors if e.severity == ErrorSeverity.CRITICAL]
        major_errors = [e for e in self.errors if e.severity == ErrorSeverity.ERROR]

        if critical_errors:
            report_lines.append("🔴 严重错误需要立即修复:")
            for error in critical_errors[:3]:  # 只显示前3个
                report_lines.append("  - %s: %s" % (error.service_name, error.message))

        if major_errors:
            report_lines.append("❌ 主要错误需要优先处理:")
            for error in major_errors[:3]:  # 只显示前3个
                report_lines.append("  - %s: %s" % (error.service_name, error.message))

        # 服务状态概览
        report_lines.append("\n🔍 服务状态概览:")
        report_lines.append("-" * 30)
        report_lines.append("已注册服务数量: %d" % len(self.services))
        if self.services:
            report_lines.append("可用服务: %s" % ", ".join(self.services.keys()))
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
                        status[name] = "📊 %s" % service_status
                    else:
                        status[name] = "✅ 已注册"
                except Exception as e:
                    status[name] = "❌ 检查失败: %s" % str(e)

        return status

    def get_detailed_error_log(self) -> List[Dict[str, Any]]:
        """获取详细的错误日志"""
        with self._lock:
            return [error.to_dict() for error in self.errors]

    def export_error_report(self, file_path: str) -> bool:
        """导出错误报告到文件"""
        try:
            report_data = {
                "timestamp": datetime.datetime.now().isoformat(),
                "summary": self.get_error_summary(),
                "user_friendly_report": self.get_user_friendly_error_report(),
                "service_status": self.get_service_status(),
                "detailed_errors": self.get_detailed_error_log(),
            }

            Path(file_path).parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2, ensure_ascii=False)

            self.logger.info("错误报告已导出到：%s", file_path)
            return True

        except Exception as e:
            self.record_error(
                "ServiceManager",
                "EXPORT_ERROR",
                "导出错误报告失败: %s" % str(e),
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return False


# 全局服务管理器实例
_service_manager: Optional[ServiceManager] = None
_init_lock = threading.Lock()

# 全局VNPY引擎实例
_main_engine: Optional[Any] = None
_event_engine: Optional[Any] = None
_china_stock_engine: Optional[Any] = None


def get_service_manager() -> ServiceManager:
    """获取全局服务管理器实例."""
    global _service_manager

    if _service_manager is None:
        with _init_lock:
            if _service_manager is None:
                _service_manager = ServiceManager()
                logging.getLogger(__name__).info("全局服务管理器已创建")

    return _service_manager


def get_main_engine() -> Optional[Any]:
    """获取全局VNPY主引擎实例."""
    return _main_engine


def get_event_engine() -> Optional[Any]:
    """获取全局VNPY事件引擎实例."""
    return _event_engine


def get_china_stock_engine() -> Optional[Any]:
    """获取全局ChinaStock数据引擎实例."""
    return _china_stock_engine


def set_main_engine(engine: Any) -> None:
    """设置全局VNPY主引擎实例."""
    global _main_engine
    _main_engine = engine
    logging.getLogger(__name__).info("全局主引擎已设置")


def set_event_engine(engine: Any) -> None:
    """设置全局VNPY事件引擎实例."""
    global _event_engine
    _event_engine = engine
    logging.getLogger(__name__).info("全局事件引擎已设置")


def set_china_stock_engine(engine: Any) -> None:
    """设置全局ChinaStock数据引擎实例."""
    global _china_stock_engine
    _china_stock_engine = engine
    logging.getLogger(__name__).info("全局ChinaStock引擎已设置")


def get_error_report() -> str:
    """获取当前的错误报告"""
    service_manager = get_service_manager()
    return service_manager.get_user_friendly_error_report()


def clear_error_log() -> None:
    """清空错误日志"""
    service_manager = get_service_manager()
    service_manager.clear_errors()


# =============================================================================
# Part 3: 服务初始化器 (已迁移至 backend.startup.initializers)
# =============================================================================

# =============================================================================
# 向后兼容导入 - 从新位置导入
# =============================================================================

# 从 backend.startup.initializers 导入服务初始化相关类和函数
from backend.startup.initializers.service_initializer import (
    InitializationPhase,
    ServiceInitializer,
    initialize_services,
    initialize_real_services,
    shutdown_services,
    shutdown_real_services,
)

__all__ = [
    # 标准库
    "json",
    "time",
    "datetime",
    "traceback",
    "threading",
    "logging",
    "Path",
    # 类型
    "Dict",
    "List",
    "Optional",
    "Any",
    # 数据处理
    "pd",
    "np",
    "PANDAS_AVAILABLE",
    "NUMPY_AVAILABLE",
    # 系统
    "psutil",
    "PSUTIL_AVAILABLE",
    # VnPy核心
    "VNPY_AVAILABLE",
    "MainEngine",
    "EventEngine",
    "Event",
    "TickData",
    "BarData",
    "OrderData",
    "TradeData",
    "PositionData",
    "AccountData",
    "EVENT_TICK",
    "EVENT_ORDER",
    "EVENT_TRADE",
    "EVENT_POSITION",
    "EVENT_ACCOUNT",
    "EVENT_LOG",
    # VnPy策略引擎
    "CTA_ENGINE",
    "ALGO_ENGINE",
    "PORTFOLIO_ENGINE",
    "CTA_ENGINE_AVAILABLE",
    "ALGO_ENGINE_AVAILABLE",
    "PORTFOLIO_ENGINE_AVAILABLE",
    # VnPy网关
    "CTP_GATEWAY",
    "IB_GATEWAY",
    "PAPER_ACCOUNT_GATEWAY",
    "CTP_GATEWAY_AVAILABLE",
    "IB_GATEWAY_AVAILABLE",
    "PAPERACCOUNT_GATEWAY_AVAILABLE",
    # VnPy数据源
    "TUSHARE_DATAFEED",
    "RQDATA_DATAFEED",
    "TUSHARE_DATAFEED_AVAILABLE",
    "RQDATA_DATAFEED_AVAILABLE",
    # Infrastructure
    "SystemMonitor",
    "ProcessManager",
    "SYSTEM_MODULE_AVAILABLE",
    # 工具函数
    "setup_logging",
    "vnpy_to_pandas",
    # 别名定义
    "CtpGateway",
    "IbGateway",
    "PaperAccountGateway",
    "PortfolioEngine",
    "RqdataDatafeed",
    "TushareDatafeed",
    # 服务管理
    "ErrorSeverity",
    "ServiceError",
    "ServiceManager",
    "get_service_manager",
    "get_main_engine",
    "get_event_engine",
    "get_china_stock_engine",
    "set_main_engine",
    "set_event_engine",
    "set_china_stock_engine",
    "get_error_report",
    "clear_error_log",
    # 服务初始化 (向后兼容)
    "InitializationPhase",
    "ServiceInitializer",
    "initialize_services",
    "initialize_real_services",
    "shutdown_services",
    "shutdown_real_services",
]
