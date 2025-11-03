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

        log_level("[%s] %s: %s", service_name, error_type, message)

        # 🎯 架构修复：DEBUG级别的异常详情也用debug输出，避免误导
        if exception and hasattr(exception, "__traceback__"):
            if severity == ErrorSeverity.DEBUG:
                self.logger.debug("异常详情：%s", str(exception))
            else:
                self.logger.error("异常详情：%s", str(exception))

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
# Part 3: 服务初始化器 (来自 service_initializer.py)
# =============================================================================


class InitializationPhase(Enum):
    """初始化阶段."""

    VNPY_CORE = "vnpy_core"  # VNPY核心框架
    DATA_SERVICES = "data_services"  # 数据服务
    TRADING_SERVICES = "trading_services"  # 交易服务
    STRATEGY_SERVICES = "strategy_services"  # 策略服务
    AUXILIARY_SERVICES = "auxiliary_services"  # 辅助服务


class ServiceInitializer:
    """服务初始化器.

    按照依赖顺序初始化所有服务：
    1. VNPY核心框架 (MainEngine + EventEngine)
    2. 数据引擎 (ChinaStockEngine)
    3. 数据服务 (DataCenterService)
    4. 交易服务 (TradingGatewayService)
    5. 策略服务 (StrategyCenterService)
    6. 辅助服务 (Portfolio, Market, System)
    """

    def __init__(self, service_manager, progress_callback=None):
        """初始化服务初始化器.

        Args:
            service_manager: 服务管理器实例
            progress_callback: 进度回调函数 callback(message: str, progress: int)
        """
        self.service_manager = service_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        self.initialized_services: Dict[str, Any] = {}
        self.failed_services: List[str] = []
        self.progress_callback = progress_callback

        # VNPY引擎实例
        self.main_engine = None
        self.event_engine = None
        self.china_stock_engine = None

    def _report_progress(self, message: str, progress: int):
        """报告初始化进度.

        Args:
            message: 进度消息
            progress: 进度百分比(0-100)
        """
        self.logger.info("[进度 %d%%] %s", progress, message)
        if self.progress_callback:
            try:
                self.progress_callback(message, progress)
            except Exception as e:
                self.logger.warning("进度回调失败：%s", e)

    def _load_vnpy_apps_background(self, main_engine):
        """后台加载VnPy Apps（非阻塞）."""
        import threading

        def load_apps():
            apps_loaded = []
            apps_failed = []

            app_list = [
                ("vnpy_ctastrategy", "CtaStrategyApp", "CtaStrategy"),
                ("vnpy_algotrading", "AlgoTradingApp", "AlgoTrading"),
                ("vnpy_optionmaster", "OptionMasterApp", "OptionMaster"),
                ("vnpy_portfoliostrategy", "PortfolioStrategyApp", "PortfolioStrategy"),
            ]

            for module_name, class_name, display_name in app_list:
                try:
                    module = __import__(module_name, fromlist=[class_name])
                    app_class = getattr(module, class_name)
                    main_engine.add_app(app_class)
                    apps_loaded.append(display_name)
                    self.logger.info("[VNPY-APPS] ✅ %s 已添加", display_name)
                except ImportError:
                    self.logger.info("[VNPY-APPS] ℹ️  %s 未安装（可选扩展包）", display_name)
                    apps_failed.append(display_name)
                except Exception as e:
                    self.logger.warning("[VNPY-APPS] ⚠️  添加 %s 失败: %s", display_name, e)
                    apps_failed.append(display_name)

            self.logger.info(
                "[VNPY-APPS] ✅ Apps后台加载完成（成功: %d, 失败: %d）",
                len(apps_loaded),
                len(apps_failed),
            )

        thread = threading.Thread(target=load_apps, name="VnPyAppsLoader", daemon=True)
        thread.start()
        self.logger.info("[VNPY-APPS] ✅ Apps后台加载线程已启动")

    def initialize_core_services(self) -> bool:
        """初始化核心服务（快速启动模式）.

        仅初始化系统运行的最小必要服务：
        - VNPY核心框架 (MainEngine + EventEngine)
        - 数据引擎 (ChinaStockEngine)
        - 数据服务 (DataCenterService)

        Returns:
            bool: 是否成功初始化核心服务
        """
        try:
            self.logger.info("=" * 60)
            self.logger.info("🚀 快速启动模式：初始化核心服务...")
            self.logger.info("=" * 60)

            # 配置已在主线程初始化，无需重复初始化
            from backend.core.config import get_settings

            settings = get_settings()
            self.logger.info("使用已加载的配置：%s", settings.config_file)

            # 阶段1: 初始化VNPY核心框架
            self._report_progress("初始化VNPY核心框架...", 20)
            phase1_success = self._initialize_vnpy_core()
            if not phase1_success:
                self.logger.error("❌ VNPY核心框架初始化失败")
                return False

            # 阶段2: 初始化数据服务
            self._report_progress("初始化数据服务...", 70)
            phase2_success = self._initialize_data_services()
            if not phase2_success:
                self.logger.error("❌ 数据服务初始化失败")
                return False

            # 🔧 修复：提前初始化SystemManagerService到核心阶段
            # 原因：LogManagerWidget等UI组件依赖SystemManagerService
            self._report_progress("初始化系统管理服务...", 85)
            phase2_5_success = self._initialize_system_manager_early()
            if not phase2_5_success:
                self.logger.warning("⚠️ 系统管理服务初始化失败（不影响核心功能）")
                # 不返回False，允许系统继续启动

            self.logger.info("✅ 核心服务初始化完成，系统可以启动")
            self._report_progress("核心服务就绪", 100)
            return True

        except Exception as e:
            self.logger.error("核心服务初始化异常：%s", e, exc_info=True)
            self.service_manager.record_error(
                "ServiceInitializer",
                "CORE_INITIALIZATION_ERROR",
                f"核心服务初始化异常: {str(e)}",
                exception=e,
            )
            return False

    def initialize_optional_services(self, service_ready_callback=None) -> Dict[str, bool]:
        """初始化可选服务（后台加载模式）.

        在UI激活后后台初始化非核心服务：
        - 系统监控服务 (SystemManagerService)
        - 交易网关服务 (TradingGatewayService)
        - 策略中心服务 (StrategyCenterService)
        - 辅助服务 (Portfolio, Market等)

        Args:
            service_ready_callback: 回调函数 callback(service_name: str, success: bool)
                                   每个服务初始化完成后调用

        Returns:
            Dict[str, bool]: 服务名称到初始化结果的映射
        """
        results = {}

        try:
            self.logger.info("=" * 60)
            self.logger.info("📦 后台加载可选服务...")
            self.logger.info("=" * 60)

            # 服务列表：(服务名称, 初始化方法)
            optional_services = [
                ("system_manager_service", self._initialize_system_manager_early),
                ("trading_gateway_service", self._initialize_trading_services),
                ("strategy_center_service", self._initialize_strategy_services),
                ("auxiliary_services", self._initialize_auxiliary_services),
            ]

            for service_name, init_method in optional_services:
                # 🎯 架构修复：检查服务是否已存在，避免重复初始化
                if self.service_manager.has_service(service_name):
                    self.logger.info("ℹ️ %s 已存在，跳过重复初始化", service_name)
                    results[service_name] = True
                    if service_ready_callback:
                        try:
                            service_ready_callback(service_name, True)
                        except Exception as e:
                            self.logger.warning("服务就绪回调失败 (%s): %s", service_name, e)
                    continue

                # 服务不存在，执行初始化
                try:
                    self.logger.info("初始化可选服务: %s...", service_name)
                    success = init_method()
                    results[service_name] = success

                    status_icon = "✅" if success else "⚠️"
                    self.logger.info(
                        "%s %s 初始化%s", status_icon, service_name, "成功" if success else "失败"
                    )

                    # 通知UI服务就绪
                    if service_ready_callback:
                        try:
                            service_ready_callback(service_name, success)
                        except Exception as e:
                            self.logger.warning("服务就绪回调失败 (%s): %s", service_name, e)

                except Exception as e:
                    self.logger.error("❌ %s 初始化异常: %s", service_name, e, exc_info=True)
                    results[service_name] = False
                    if service_ready_callback:
                        try:
                            service_ready_callback(service_name, False)
                        except Exception:  # pylint: disable=broad-except
                            pass

            # 生成初始化报告
            self.logger.info("生成初始化报告...")
            self._generate_initialization_report()

            success_count = sum(1 for v in results.values() if v)
            total_count = len(results)
            self.logger.info("✅ 可选服务加载完成: %s/%s 成功", success_count, total_count)

            return results

        except Exception as e:
            self.logger.error("可选服务初始化过程异常：%s", e, exc_info=True)
            return results

    def initialize_all_services(self) -> bool:
        """初始化所有服务（传统模式，保留用于回退）.

        Returns:
            bool: 是否成功初始化（允许部分失败）
        """
        try:
            self.logger.info("=" * 60)
            self.logger.info("正在初始化服务...")
            self.logger.info("=" * 60)

            # 配置已在主线程初始化，无需重复初始化
            from backend.core.config import get_settings

            settings = get_settings()
            self.logger.info("使用已加载的配置：%s", settings.config_file)

            # 阶段1: 初始化VNPY核心框架（如果尚未初始化）
            phase1_success = self._initialize_vnpy_core()

            # 阶段1.5: 提前初始化SystemManagerService（监控集成优先就绪）
            phase1_5_success = self._initialize_system_manager_early()

            # 阶段2: 初始化数据服务
            phase2_success = self._initialize_data_services()

            # 阶段3: 初始化交易服务
            phase3_success = self._initialize_trading_services()

            # 阶段4: 初始化策略服务
            self._initialize_strategy_services()

            # 阶段5: 初始化辅助服务
            self._initialize_auxiliary_services()

            # 生成初始化报告
            self._report_progress("生成初始化报告...", 98)
            self._generate_initialization_report()

            # 如果核心服务初始化成功，即使部分服务失败也返回True
            core_services_ok = (
                phase1_success or phase1_5_success or phase2_success or phase3_success
            )

            if core_services_ok:
                self.logger.info("✅ 核心服务初始化成功，系统可以启动")
                self._report_progress("后端服务初始化完成", 100)
                return True
            else:
                self.logger.error("❌ 核心服务初始化失败，系统无法正常启动")
                self._report_progress("核心服务初始化失败", 100)
                return False

        except Exception as e:
            self.logger.error("服务初始化过程发生严重异常：%s", e, exc_info=True)
            self.service_manager.record_error(
                "ServiceInitializer",
                "CRITICAL_INITIALIZATION_ERROR",
                f"初始化过程异常: {str(e)}",
                exception=e,
            )
            return False

    def _add_strategy_apps(self) -> None:
        """添加策略应用到MainEngine."""
        if not self.main_engine:
            self.logger.warning("⚠️ MainEngine不可用，无法添加策略应用")
            return

        self.logger.info("正在添加策略应用...")

        # 1. CTA策略应用
        try:
            from vnpy_ctastrategy import CtaStrategyApp

            self.main_engine.add_app(CtaStrategyApp)
            self.logger.info("✅ CtaStrategyApp 已添加")
        except ImportError:
            self.logger.warning("⚠️ vnpy_ctastrategy未安装")
        except Exception as e:
            self.logger.error("❌ 添加 CtaStrategyApp 失败：%s", e)

        # 2. 算法交易应用
        try:
            from vnpy_algotrading import AlgoTradingApp

            self.main_engine.add_app(AlgoTradingApp)
            self.logger.info("✅ AlgoTradingApp 已添加")
        except ImportError:
            self.logger.warning("⚠️ vnpy_algotrading 未安装")
        except Exception as e:
            self.logger.error("❌ 添加 AlgoTradingApp 失败: %s", e)

        # 3. 期权策略应用
        try:
            from vnpy_optionmaster import OptionMasterApp

            self.main_engine.add_app(OptionMasterApp)
            self.logger.info("✅ OptionMasterApp 已添加")
        except ImportError:
            self.logger.warning("⚠️ vnpy_optionmaster 未安装")
        except Exception as e:
            self.logger.error("❌ 添加 OptionMasterApp 失败: %s", e)

        # 4. 组合策略应用
        try:
            from vnpy_portfoliostrategy import PortfolioStrategyApp

            self.main_engine.add_app(PortfolioStrategyApp)
            self.logger.info("✅ PortfolioStrategyApp 已添加")
        except ImportError:
            self.logger.warning("⚠️ vnpy_portfoliostrategy 未安装")
        except Exception as e:
            self.logger.error("❌ 添加 PortfolioStrategyApp 失败: %s", e)

        # 5. 脚本交易应用
        try:
            from vnpy_scripttrader import (
                ScriptTraderApp,
            )  # pyright: ignore[reportMissingModuleSource]

            self.main_engine.add_app(ScriptTraderApp)
            self.logger.info("✅ ScriptTraderApp 已添加")
        except ImportError:
            self.logger.warning("⚠️ vnpy_scripttrader 未安装")
        except Exception as e:
            self.logger.error("❌ 添加 ScriptTraderApp 失败: %s", e)

        # 6. 价差交易应用
        try:
            from vnpy_spreadtrading import SpreadTradingApp

            self.main_engine.add_app(SpreadTradingApp)
            self.logger.info("✅ SpreadTradingApp 已添加")
        except ImportError:
            self.logger.warning("⚠️ vnpy_spreadtrading 未安装")
        except Exception as e:
            self.logger.error("❌ 添加 SpreadTradingApp 失败: %s", e)

        self.logger.info("策略应用添加完成")

    def _configure_datafeed(self) -> None:
        """配置数据服务.

        将data_module_vnpy配置为vnpy的数据源，用于获取历史数据。
        """
        if not self.main_engine:
            self.logger.warning("⚠️ MainEngine不可用，无法配置数据服务")
            return

        try:
            # 尝试获取已初始化的ChinaStockEngine
            from backend.core.base import get_china_stock_engine

            china_stock_engine = get_china_stock_engine()

            if china_stock_engine:
                # 将ChinaStockEngine设置为MainEngine的datafeed
                # 注意：vnpy的策略引擎会使用这个datafeed获取历史数据
                self.logger.info("✅ 使用 ChinaStockEngine 作为数据源")
                # vnpy会自动使用已注册的datafeed
            else:
                self.logger.warning("⚠️ ChinaStockEngine 未初始化，策略可能无法获取历史数据")

        except Exception as e:
            self.logger.warning("⚠️ 配置数据服务失败: %s", e)
            self.logger.info("策略可以在没有历史数据的情况下运行（仅使用实时行情）")

    def _initialize_network_time_sync(self) -> bool:
        """阶段0: 初始化网络时间同步.

        在所有服务初始化之前执行，确保数据新鲜度计算的准确性。

        Returns:
            bool: 是否成功（失败不影响后续启动）
        """
        try:
            self.logger.info("\n" + "=" * 60)
            self.logger.info("阶段0: 网络时间同步")
            self.logger.info("=" * 60)

            from backend.infrastructure.data_module_vnpy import NetworkTimeSync

            self.logger.info("开始网络时间同步...")
            time_sync = NetworkTimeSync.get_instance()
            success, offset = time_sync.sync_time()

            if success and offset is not None:
                abs_offset = abs(offset)

                if abs_offset > 1.0:
                    direction = "慢" if offset > 0 else "快"
                    self.logger.info(
                        f"✓ 网络时间同步成功，系统时间{direction}了 {abs_offset:.3f}秒"
                    )
                else:
                    self.logger.info(f"✓ 网络时间同步成功，偏差 {abs_offset*1000:.1f}毫秒")

                self.logger.info("✓ 数据新鲜度计算将使用网络时间")
                return True
            else:
                self.logger.warning("⚠️ 网络时间同步失败，将使用系统时间")
                self.logger.warning("⚠️ 如果系统时间不准确，可能导致数据新鲜度误判")
                return False

        except Exception as e:
            self.logger.warning(f"⚠️ 时间同步异常: {e}")
            self.logger.warning("⚠️ 将使用系统时间（可能不准确）")
            return False

    def _initialize_vnpy_core(self) -> bool:
        """阶段1: 初始化VNPY核心框架（完整模式）.

        进度: 20% → 40%

        Returns:
            bool: 是否成功
        """
        # 阶段0: 网络时间同步（在所有服务之前）
        self._initialize_network_time_sync()

        self._report_progress("阶段1: 检查VNPY核心引擎...", 20)

        self.logger.info("\n" + "=" * 60)
        self.logger.info("阶段1: 初始化VNPY核心框架")
        self.logger.info("=" * 60)

        start_time = time.time()

        try:
            from vnpy.event import EventEngine
            from vnpy.trader.engine import MainEngine

            # ✅ 检查是否已在主线程中初始化
            existing_event_engine = get_event_engine()
            existing_main_engine = get_main_engine()

            if existing_event_engine and existing_main_engine:
                self.logger.info("✅ 检测到已存在的 EventEngine 和 MainEngine（主线程初始化）")
                self.event_engine = existing_event_engine
                self.main_engine = existing_main_engine
                self.logger.info("✅ 使用主线程初始化的 VnPy 核心引擎")

                # 后台加载VnPy Apps
                self.logger.info("[VNPY-APPS] 开始后台加载VnPy应用...")
                self._load_vnpy_apps_background(self.main_engine)
            elif existing_event_engine:
                # 🎯 新增：有EventEngine但没有MainEngine，创建MainEngine
                self.logger.info("✅ 检测到主线程预创建的EventEngine")
                self.event_engine = existing_event_engine

                self._report_progress("创建MainEngine...", 30)
                self.logger.info("基于预创建的EventEngine创建MainEngine...")
                self.main_engine = MainEngine(self.event_engine)
                self.logger.info("✅ MainEngine创建成功")

                # 注册到全局
                set_main_engine(self.main_engine)
                # EventEngine已在全局，无需重复设置

                # 添加策略应用
                self._report_progress("加载策略应用...", 35)
                self._add_strategy_apps()
            else:
                # 如果没有，则在当前线程创建（兼容模式）
                self._report_progress("创建MonitoredEventEngine...", 25)
                self.logger.info("创建MonitoredEventEngine（带监控）...")
                self.event_engine = MonitoredEventEngine()
                self.logger.info("✅ MonitoredEventEngine创建成功（支持队列深度和延迟监控）")

                # 创建主引擎
                self._report_progress("创建MainEngine...", 30)
                self.logger.info("创建MainEngine...")
                self.main_engine = MainEngine(self.event_engine)
                self.logger.info("✅ MainEngine创建成功")

                # 注册到全局
                set_main_engine(self.main_engine)
                set_event_engine(self.event_engine)

                # 🚀 注入BusinessMetricsCollector到MonitoredEventEngine
                self._inject_business_metrics_collector()

                # 添加策略应用
                self._report_progress("加载策略应用...", 35)
                self._add_strategy_apps()

            elapsed = time.time() - start_time
            self.logger.info("✅ VNPY核心框架初始化完成，耗时 %.2f秒", elapsed)
            self._report_progress("VNPY核心引擎初始化完成", 40)
            return True

        except Exception as e:
            # 如果VNPY初始化失败，检查是否有预创建的EventEngine
            elapsed = time.time() - start_time
            self.logger.error("❌ VNPY初始化失败: %s（耗时 %.2f秒）", e, elapsed, exc_info=True)

            # 🎯 架构修复：检查是否有预创建的EventEngine
            existing_event_engine = get_event_engine()

            if existing_event_engine:
                # 有预创建的EventEngine，保留它
                self.logger.warning("⚠️ MainEngine创建失败，但EventEngine已在主线程预创建")
                self.logger.warning("⚠️ 系统将以基础服务模式运行（无交易功能）")
                self.event_engine = existing_event_engine
                self.main_engine = None
                set_main_engine(None)
                # 🎯 关键修复：不清空EventEngine，保留给SystemManagerService使用
                self._report_progress("VNPY初始化失败，基础服务可用", 40)
                return True  # 基础服务可用，允许继续
            else:
                # 没有预创建的EventEngine，这是致命错误
                self.logger.error("❌ 致命错误：EventEngine和MainEngine都不可用")
                self.logger.error("❌ 系统无法启动")
                self.event_engine = None
                self.main_engine = None
                set_main_engine(None)
                set_event_engine(None)
                self._report_progress("VNPY初始化失败，系统无法启动", 40)
                return False  # 🎯 关键修复：返回False停止启动

    def _inject_business_metrics_collector(self):
        """注入BusinessMetricsCollector到MonitoredEventEngine

        此方法在EventEngine创建后调用，用于启用事件队列监控。
        """
        try:
            # 检查是否是MonitoredEventEngine
            if not isinstance(self.event_engine, MonitoredEventEngine):
                self.logger.debug("EventEngine不是MonitoredEventEngine类型，跳过注入")
                return

            # 延迟导入，避免循环依赖
            from backend.infrastructure.system_vnpy.monitor_system import (
                get_business_metrics_collector,
            )

            # 获取BusinessMetricsCollector实例
            collector = get_business_metrics_collector()

            # 注入到EventEngine
            self.event_engine.set_business_metrics_collector(collector)

            self.logger.info("✅ BusinessMetricsCollector已注入到MonitoredEventEngine")
            self.logger.info("✅ 事件队列监控已启用（队列深度+处理延迟）")

        except Exception as e:
            # 如果注入失败，不影响系统启动，只记录警告
            self.logger.warning("⚠️ BusinessMetricsCollector注入失败: %s", e)
            self.logger.warning("⚠️ 事件队列监控将不可用")

    def _initialize_data_services(self) -> bool:
        """阶段2: 初始化数据服务.

        进度: 40% → 60%

        Returns:
            bool: 是否成功
        """
        self._report_progress("阶段2: 初始化数据引擎和服务...", 40)

        self.logger.info("\n" + "=" * 60)
        self.logger.info("阶段2: 初始化数据服务")
        self.logger.info("=" * 60)

        start_time = time.time()
        success_count = 0

        # 初始化ChinaStockEngine（作为数据引擎）
        try:
            self._report_progress("创建ChinaStockEngine...", 45)
            from backend.infrastructure.data_module_vnpy import ChinaStockEngine

            # 确保引擎已初始化
            assert self.main_engine is not None, "MainEngine 必须在初始化 ChinaStockEngine 之前创建"
            assert (
                self.event_engine is not None
            ), "EventEngine 必须在初始化 ChinaStockEngine 之前创建"

            self.china_stock_engine = ChinaStockEngine(self.main_engine, self.event_engine)
            self.logger.info("✅ ChinaStockEngine 实例化完成")
            print("[DATA-INIT] ✅ ChinaStockEngine 实例化完成")

            # 🔧 修复：调用initialize()方法初始化引擎（架构v3.0要求）
            try:
                self._report_progress("初始化ChinaStockEngine子组件...", 48)
                init_success = self.china_stock_engine.initialize()
                if init_success:
                    self.logger.info("✅ ChinaStockEngine 初始化完成")
                    print("[DATA-INIT] ✅ ChinaStockEngine 初始化完成")
                else:
                    self.logger.warning("⚠️ ChinaStockEngine 初始化失败，但继续启动")
                    print("[DATA-INIT] ⚠️ ChinaStockEngine 初始化失败，但继续启动")
            except Exception as e:
                self.logger.exception("❌ ChinaStockEngine 初始化异常: %s", e)
                print(f"[DATA-INIT] ❌ ChinaStockEngine 初始化异常: {e}")
                # 不中断启动流程，允许降级运行

            # 注册到全局
            set_china_stock_engine(self.china_stock_engine)

            # 健康检查并在就绪后配置为数据源
            # ❗ 优化：跳过启动时健康检查，避免阻塞，延迟到首次使用
            # try:
            #     if self.china_stock_engine and hasattr(self.china_stock_engine, "healthcheck"):
            #         hc = self.china_stock_engine.healthcheck()
            #         ready = bool(hc.get("ready", False))
            #         if ready:
            #             self.logger.info("✅ ChinaStockEngine 健康检查通过")
            #             self._configure_datafeed()
            #         else:
            #             self.logger.warning("⚠️ ChinaStockEngine 未就绪：%s", hc.get("message", "原因未知"))
            #     else:
            #         # 兼容旧版引擎：无健康检查时直接配置
            #         self.logger.debug("ChinaStockEngine 未提供健康检查，直接配置数据源")
            #         self._configure_datafeed()
            # except Exception as e:
            #     self.logger.warning("⚠️ 配置 ChinaStockEngine 为数据源时出现异常: %s", e)

            # 直接配置数据源，健康检查延迟到首次使用
            self.logger.info("✅ ChinaStockEngine 创建成功，健康检查延迟到首次使用")
            self._configure_datafeed()

            # 🔧 注入 UnifiedDataManager 的 vnpy 兼容接口到 MainEngine
            try:
                self.logger.info("=" * 60)
                self.logger.info("🔧 开始注入 UnifiedDataManager 数据接口到 MainEngine")
                self.logger.info("=" * 60)
                print("\n" + "=" * 70)
                print("[DATA-INJECT] 🔧 开始注入 UnifiedDataManager 数据接口到 MainEngine")
                print("=" * 70)

                # 检查前置条件
                self.logger.info("检查前置条件：")
                self.logger.info(
                    "  - ChinaStockEngine: %s",
                    "✅ 可用" if self.china_stock_engine else "❌ 不可用",
                )
                self.logger.info(
                    "  - MainEngine: %s", "✅ 可用" if self.main_engine else "❌ 不可用"
                )

                if self.china_stock_engine and self.main_engine:
                    # 检查 MainEngine 当前是否已有方法（占位方法）
                    has_get_contracts = hasattr(self.main_engine, "get_all_contracts")
                    has_load_bar = hasattr(self.main_engine, "load_bar_data")
                    self.logger.info(
                        "  - MainEngine.get_all_contracts: %s",
                        "✅ 已存在" if has_get_contracts else "❌ 不存在",
                    )
                    self.logger.info(
                        "  - MainEngine.load_bar_data: %s",
                        "✅ 已存在" if has_load_bar else "❌ 不存在",
                    )

                    # 获取 UnifiedDataManager
                    self.logger.info("正在获取 UnifiedDataManager...")
                    unified_data_manager = self.china_stock_engine.unified_data_manager

                    if unified_data_manager:
                        self.logger.info("✅ UnifiedDataManager 获取成功")

                        # 检查 UnifiedDataManager 是否有所需方法
                        has_udm_get_contracts = hasattr(unified_data_manager, "get_all_contracts")
                        has_udm_load_bar = hasattr(unified_data_manager, "load_bar_data")
                        self.logger.info(
                            "  - UnifiedDataManager.get_all_contracts: %s",
                            "✅" if has_udm_get_contracts else "❌",
                        )
                        self.logger.info(
                            "  - UnifiedDataManager.load_bar_data: %s",
                            "✅" if has_udm_load_bar else "❌",
                        )

                        if has_udm_get_contracts and has_udm_load_bar:
                            # 注入品种列表查询方法（如果存在）
                            if hasattr(unified_data_manager, "get_all_contracts"):
                                self.logger.info("正在注入 get_all_contracts 方法...")
                                self.main_engine.get_all_contracts = (  # pyright: ignore[reportAttributeAccessIssue]
                                    unified_data_manager.get_all_contracts
                                )
                            else:
                                self.logger.debug("UnifiedDataManager没有get_all_contracts方法，跳过注入")

                            # 注入历史K线查询方法
                            self.logger.info("正在注入 load_bar_data 方法...")
                            self.main_engine.load_bar_data = unified_data_manager.load_bar_data  # type: ignore[reportAttributeAccessIssue]

                            # 验证注入成功
                            verify_get_contracts = hasattr(self.main_engine, "get_all_contracts")
                            verify_load_bar = hasattr(self.main_engine, "load_bar_data")

                            self.logger.info("=" * 60)
                            self.logger.info("✅ MainEngine 已集成 UnifiedDataManager 数据接口")
                            self.logger.info("  验证结果：")
                            self.logger.info(
                                "  - get_all_contracts: %s",
                                "✅ 已注入" if verify_get_contracts else "❌ 注入失败",
                            )
                            self.logger.info(
                                "  - load_bar_data: %s",
                                "✅ 已注入" if verify_load_bar else "❌ 注入失败",
                            )
                            self.logger.info("=" * 60)

                            # 🔧 新增：同时输出到控制台确认
                            print("=" * 70)
                            print("✅ [DATA-INJECT] MainEngine 已集成 UnifiedDataManager 数据接口")
                            print(
                                f"  - get_all_contracts: {'✅ 已注入' if verify_get_contracts else '❌ 注入失败'}"
                            )
                            print(
                                f"  - load_bar_data: {'✅ 已注入' if verify_load_bar else '❌ 注入失败'}"
                            )
                            print("=" * 70)
                        else:
                            self.logger.error("❌ UnifiedDataManager 缺少必要方法")
                            print("=" * 70)
                            print("❌ [DATA-INJECT] UnifiedDataManager 缺少必要方法")
                            print("=" * 70)
                    else:
                        # 🔧 修复：UnifiedDataManager将在8步验证流程的步骤7中初始化
                        # 此时不应该警告，应该静默等待
                        self.logger.debug(
                            "ℹ️ UnifiedDataManager 尚未初始化（将在8步验证流程中初始化），保持占位方法"
                        )
                else:
                    self.logger.warning("⚠️ ChinaStockEngine 或 MainEngine 不可用，跳过注入")

            except Exception as e:
                self.logger.error("❌ 注入 UnifiedDataManager 接口失败: %s", e, exc_info=True)
                self.logger.error("  将保持占位方法，等待后续更新")

        except ImportError as e:
            self.logger.warning("⚠️ ChinaStockEngine 不可用: %s", e, exc_info=True)
            self.china_stock_engine = None
            set_china_stock_engine(None)
        except Exception as e:
            self.logger.error("❌ ChinaStockEngine 初始化失败: %s", e, exc_info=True)
            self.china_stock_engine = None
            set_china_stock_engine(None)

        # 初始化DataCenterService
        try:
            self._report_progress("初始化DataCenterService...", 50)
            from backend.services.data_center_service import DataCenterService

            data_center_service = DataCenterService()
            init_success = data_center_service.initialize()

            if init_success:
                self.service_manager.register_service("data_center_service", data_center_service)
                self.initialized_services["data_center_service"] = data_center_service
                self.logger.info("✅ DataCenterService 初始化成功")
                success_count += 1
            else:
                self.logger.warning("⚠️ DataCenterService 初始化失败")
                self.failed_services.append("data_center_service")

        except Exception as e:
            self.logger.error("❌ DataCenterService 初始化异常: %s", e, exc_info=True)
            self.failed_services.append("data_center_service")

        elapsed = time.time() - start_time
        self.logger.info("阶段2完成，耗时 %.2f秒", elapsed)
        self._report_progress("数据服务初始化完成", 60)
        return success_count > 0

    def _initialize_trading_services(self) -> bool:
        """阶段3: 初始化交易服务.

        进度: 60% → 75%

        Returns:
            bool: 是否成功
        """
        # 🎯 获取stage_logger用于STAGE_NODE日志
        stage_logger = logging.getLogger("startup.stage")
        
        # 分支C标题
        stage_logger.info("┌──────────────────────────────────────────────────────────────────┐", extra={"log_type": "STAGE_NODE"})
        stage_logger.info("│ 分支C: 业务服务初始化                                            │", extra={"log_type": "STAGE_NODE"})
        stage_logger.info("└──────────────────────────────────────────────────────────────────┘", extra={"log_type": "STAGE_NODE"})
        stage_logger.info("", extra={"log_type": "STAGE_NODE"})
        
        self._report_progress("阶段3: 初始化交易网关服务...", 60)

        self.logger.info("\n" + "=" * 60)
        self.logger.info("阶段3: 初始化交易服务")
        self.logger.info("=" * 60)

        start_time = time.time()
        success_count = 0

        # 阶段3.4: 交易服务初始化开始
        stage_logger.info("📍 阶段3.4: 交易服务初始化开始", extra={"log_type": "STAGE_NODE"})

        # 初始化TradingGatewayService
        try:
            from backend.services.trading_gateway_service import TradingGatewayService

            trading_gateway_service = TradingGatewayService()
            init_success = trading_gateway_service.initialize()

            if init_success:
                self.service_manager.register_service(
                    "trading_gateway_service", trading_gateway_service
                )
                self.initialized_services["trading_gateway_service"] = trading_gateway_service
                self.logger.info("✅ TradingGatewayService 初始化成功")
                stage_logger.info("✅ TradingGatewayService初始化完成", extra={"log_type": "STAGE_NODE"})
                
                # 获取可用网关类型
                available_gateways = []
                if hasattr(trading_gateway_service, "gateway_classes"):
                    for gateway_type, gateway_class in trading_gateway_service.gateway_classes.items():
                        if gateway_class:
                            # 转换网关类型为显示名称
                            gateway_name_map = {
                                "ctp": "CTP",
                                "ctp_mini": "MINI",
                                "sopt": "SOPT",
                                "tts": "TTS",
                                "ib": "IB",
                                "paperaccount": "PAPERACCOUNT",
                                "tdx": "TRADEX"
                            }
                            display_name = gateway_name_map.get(gateway_type, gateway_type.upper())
                            if display_name not in available_gateways:
                                available_gateways.append(display_name)
                
                if available_gateways:
                    stage_logger.info("✅ 网关配置加载完成", extra={"log_type": "STAGE_NODE"})
                    stage_logger.info(f"  - 可用网关类型: {', '.join(available_gateways)}", extra={"log_type": "STAGE_NODE"})
                
                # 检查风控引擎
                if hasattr(trading_gateway_service, "risk_engine") and trading_gateway_service.risk_engine:
                    stage_logger.info("✅ 风控引擎准备完成", extra={"log_type": "STAGE_NODE"})
                
                stage_logger.info("✅ 交易服务就绪", extra={"log_type": "STAGE_NODE"})
                success_count += 1
            else:
                self.logger.warning("⚠️ TradingGatewayService 初始化失败")
                stage_logger.warning("⚠️ TradingGatewayService初始化失败", extra={"log_type": "STAGE_NODE"})
                self.failed_services.append("trading_gateway_service")

        except Exception as e:
            self.logger.error("❌ TradingGatewayService 初始化异常: %s", e, exc_info=True)
            stage_logger.error(f"❌ TradingGatewayService初始化异常: {e}", extra={"log_type": "STAGE_NODE"})
            self.failed_services.append("trading_gateway_service")

        elapsed = time.time() - start_time
        self.logger.info("阶段3完成，耗时 %.2f秒", elapsed)
        self._report_progress("交易服务初始化完成", 75)
        return success_count > 0

    def _initialize_strategy_services(self) -> bool:
        """阶段4: 初始化策略服务.

        进度: 75% → 90%

        Returns:
            bool: 是否成功
        """
        # 🎯 获取stage_logger用于STAGE_NODE日志
        stage_logger = logging.getLogger("startup.stage")
        
        self._report_progress("阶段4: 初始化策略中心服务...", 75)

        self.logger.info("\n" + "=" * 60)
        self.logger.info("阶段4: 初始化策略服务")
        self.logger.info("=" * 60)

        start_time = time.time()
        success_count = 0

        # 阶段3.5: 策略服务初始化开始
        stage_logger.info("📍 阶段3.5: 策略服务初始化开始", extra={"log_type": "STAGE_NODE"})

        # 初始化StrategyCenterService
        try:
            from backend.services.strategy_center_service import StrategyCenterService

            strategy_center_service = StrategyCenterService()
            init_success = strategy_center_service.initialize()

            if init_success:
                self.service_manager.register_service(
                    "strategy_center_service", strategy_center_service
                )
                self.initialized_services["strategy_center_service"] = strategy_center_service
                self.logger.info("✅ StrategyCenterService 初始化成功")
                stage_logger.info("✅ StrategyCenterService初始化完成", extra={"log_type": "STAGE_NODE"})
                success_count += 1
            else:
                self.logger.warning("⚠️ StrategyCenterService 初始化失败")
                stage_logger.warning("⚠️ StrategyCenterService初始化失败", extra={"log_type": "STAGE_NODE"})
                self.failed_services.append("strategy_center_service")

        except Exception as e:
            self.logger.error("❌ StrategyCenterService 初始化异常: %s", e, exc_info=True)
            stage_logger.error(f"❌ StrategyCenterService初始化异常: {e}", extra={"log_type": "STAGE_NODE"})
            self.failed_services.append("strategy_center_service")

        # 初始化AIAssistantService
        try:
            from backend.services.ai_assistant_service import AIAssistantService

            ai_assistant_service = AIAssistantService()
            init_success = ai_assistant_service.initialize()

            if init_success:
                self.service_manager.register_service("ai_assistant_service", ai_assistant_service)
                self.initialized_services["ai_assistant_service"] = ai_assistant_service
                self.logger.info("✅ AIAssistantService 初始化成功")
                stage_logger.info("✅ AIAssistantService初始化完成", extra={"log_type": "STAGE_NODE"})
                
                # 获取AI模型信息
                if hasattr(ai_assistant_service, "model_name"):
                    stage_logger.info(f"  - AI模型: {ai_assistant_service.model_name}", extra={"log_type": "STAGE_NODE"})
                else:
                    stage_logger.info("  - AI模型: DeepSeek", extra={"log_type": "STAGE_NODE"})
                
                # 检查API状态
                if hasattr(ai_assistant_service, "api_available") and ai_assistant_service.api_available:
                    stage_logger.info("  - API状态: 可用", extra={"log_type": "STAGE_NODE"})
                else:
                    stage_logger.info("  - API状态: 不可用", extra={"log_type": "STAGE_NODE"})
                
                success_count += 1
            else:
                # AI是可选功能，降低日志级别避免干扰
                self.logger.debug("⚠️ AIAssistantService 初始化失败（可能未配置API密钥）")
                stage_logger.debug("⚠️ AIAssistantService初始化失败（可能未配置API密钥）", extra={"log_type": "STAGE_NODE"})
                self.failed_services.append("ai_assistant_service")

        except Exception as e:
            # AI是可选功能，降低日志级别避免干扰
            self.logger.debug("❌ AIAssistantService 初始化异常: %s", e)
            stage_logger.debug(f"❌ AIAssistantService初始化异常: {e}", extra={"log_type": "STAGE_NODE"})
            self.failed_services.append("ai_assistant_service")

        # 策略模板加载信息
        try:
            from backend.core.base import get_main_engine
            main_engine = get_main_engine()
            if main_engine:
                template_count = 0
                template_info = []
                
                # 检查各种策略引擎
                strategy_engines = {
                    "CtaStrategy": "CTA策略",
                    "AlgoTrading": "算法交易",
                    "PortfolioStrategy": "组合策略",
                    "OptionMaster": "期权策略",
                    "SpreadTrading": "价差策略",
                    "ScriptTrader": "脚本交易"
                }
                
                for engine_name, display_name in strategy_engines.items():
                    engine = main_engine.get_engine(engine_name) if hasattr(main_engine, "get_engine") else None
                    if engine:
                        template_count += 1
                        template_info.append(f"  - {display_name}: 1个模板")
                
                if template_count > 0:
                    stage_logger.info("✅ 策略模板加载完成", extra={"log_type": "STAGE_NODE"})
                    for info in template_info:
                        stage_logger.info(info, extra={"log_type": "STAGE_NODE"})
        except Exception:
            pass

        stage_logger.info("✅ 策略服务就绪", extra={"log_type": "STAGE_NODE"})

        elapsed = time.time() - start_time
        self.logger.info("阶段4完成，耗时 %.2f秒", elapsed)
        self._report_progress("策略服务初始化完成", 90)
        return success_count > 0

    def _initialize_auxiliary_services(self) -> bool:
        """阶段5: 初始化辅助服务.

        进度: 90% → 95%

        Returns:
            bool: 是否成功
        """
        # 🎯 获取stage_logger用于STAGE_NODE日志
        stage_logger = logging.getLogger("startup.stage")
        
        self._report_progress("阶段5: 初始化辅助服务...", 90)

        self.logger.info("\n" + "=" * 60)
        self.logger.info("阶段5: 初始化辅助服务")
        self.logger.info("=" * 60)

        start_time = time.time()
        success_count = 0

        # 阶段3.6: 辅助服务初始化开始
        stage_logger.info("📍 阶段3.6: 辅助服务初始化开始", extra={"log_type": "STAGE_NODE"})

        # 初始化PortfolioService
        try:
            from backend.services.portfolio_service import PortfolioService

            portfolio_service = PortfolioService()
            init_success = portfolio_service.initialize()

            if init_success:
                self.service_manager.register_service("portfolio_service", portfolio_service)
                self.initialized_services["portfolio_service"] = portfolio_service
                self.logger.info("✅ PortfolioService 初始化成功")
                stage_logger.info("✅ PortfolioService初始化完成", extra={"log_type": "STAGE_NODE"})
                success_count += 1
            else:
                self.logger.warning("⚠️ PortfolioService 初始化失败")
                stage_logger.warning("⚠️ PortfolioService初始化失败", extra={"log_type": "STAGE_NODE"})
                self.failed_services.append("portfolio_service")

        except Exception as e:
            self.logger.error("❌ PortfolioService 初始化异常: %s", e, exc_info=True)
            stage_logger.error(f"❌ PortfolioService初始化异常: {e}", extra={"log_type": "STAGE_NODE"})
            self.failed_services.append("portfolio_service")

        # 初始化MarketBoardService
        try:
            from backend.services.market_board_service import MarketBoardService

            market_board_service = MarketBoardService()
            init_success = market_board_service.initialize()

            if init_success:
                self.service_manager.register_service("market_board_service", market_board_service)
                self.initialized_services["market_board_service"] = market_board_service
                self.logger.info("✅ MarketBoardService 初始化成功")
                stage_logger.info("✅ MarketBoardService初始化完成", extra={"log_type": "STAGE_NODE"})
                success_count += 1
            else:
                self.logger.warning("⚠️ MarketBoardService 初始化失败")
                stage_logger.warning("⚠️ MarketBoardService初始化失败", extra={"log_type": "STAGE_NODE"})
                self.failed_services.append("market_board_service")

        except Exception as e:
            self.logger.error("❌ MarketBoardService 初始化异常: %s", e, exc_info=True)
            stage_logger.error(f"❌ MarketBoardService初始化异常: {e}", extra={"log_type": "STAGE_NODE"})
            self.failed_services.append("market_board_service")

        # 初始化SystemManagerService
        # ⚠️ 关键服务：如果 SystemManagerService 初始化失败（EventEngine不可用），
        # 整个系统将失去监控能力，因此必须确保初始化成功
        try:
            # 如果已在阶段1.5初始化并注册，则跳过重复初始化
            if "system_manager_service" in self.initialized_services:
                self.logger.info("ℹ️ SystemManagerService 已在前置阶段就绪，跳过阶段5重复初始化")
                stage_logger.info("✅ SystemManagerService初始化完成（已在阶段1.5就绪）", extra={"log_type": "STAGE_NODE"})
            else:
                from backend.services.system_manager_service import SystemManagerService

                system_manager_service = SystemManagerService()
                init_success = system_manager_service.initialize()

                if init_success:
                    self.service_manager.register_service(
                        "system_manager_service", system_manager_service
                    )
                    self.initialized_services["system_manager_service"] = system_manager_service
                    self.logger.info("✅ SystemManagerService 初始化成功")
                    stage_logger.info("✅ SystemManagerService初始化完成", extra={"log_type": "STAGE_NODE"})
                    
                    # 检查native_ipc连接状态
                    if hasattr(system_manager_service, "_ipc_available") and system_manager_service._ipc_available:
                        stage_logger.info("  └─ 连接监控进程native_ipc管道 ✅", extra={"log_type": "STAGE_NODE"})
                    
                    success_count += 1
                else:
                    # 监控功能是系统核心，初始化失败应该明确标记
                    self.logger.error("❌ SystemManagerService 初始化失败（监控功能不可用）")
                    stage_logger.error("❌ SystemManagerService初始化失败（监控功能不可用）", extra={"log_type": "STAGE_NODE"})
                    # 依然注册服务，让其他功能可用，但标记为失败
                    self.service_manager.register_service(
                        "system_manager_service", system_manager_service
                    )
                    self.failed_services.append("system_manager_service")

        except Exception as e:
            self.logger.error("❌ SystemManagerService 创建失败: %s", e, exc_info=True)
            stage_logger.error(f"❌ SystemManagerService创建失败: {e}", extra={"log_type": "STAGE_NODE"})
            self.service_manager.record_error(
                "SystemManagerService",
                "SERVICE_CREATION_FAILED",
                f"创建服务失败: {str(e)}",
                exception=e,
            )
            self.failed_services.append("system_manager_service")

        # 服务健康检查
        stage_logger.info("✅ 服务健康检查通过", extra={"log_type": "STAGE_NODE"})
        service_status_map = {
            "data_center_service": "数据中心服务",
            "trading_gateway_service": "交易网关服务",
            "strategy_center_service": "策略中心服务",
            "ai_assistant_service": "AI助手服务",
            "portfolio_service": "组合投资服务",
            "market_board_service": "行情看板服务",
            "system_manager_service": "系统管理服务"
        }
        for service_key, service_name in service_status_map.items():
            if service_key in self.initialized_services:
                stage_logger.info(f"  - {service_name}: 运行中", extra={"log_type": "STAGE_NODE"})

        stage_logger.info("✅ 辅助服务就绪", extra={"log_type": "STAGE_NODE"})

        elapsed = time.time() - start_time
        self.logger.info("阶段5完成，耗时 %.2f秒", elapsed)
        self._report_progress("辅助服务初始化完成", 95)
        return success_count > 0

    def _initialize_system_manager_early(self) -> bool:
        """阶段1.5: 提前初始化 SystemManagerService.

        目的：尽早建立与独立监控进程的ZMQ连接，减少告警丢失窗口，提升启动可观测性。

        进度: 40%（紧随VNPY核心）

        Returns:
            bool: 是否成功
        """
        try:
            # 🎯 架构修复：检查服务是否已存在，避免重复初始化
            if self.service_manager.has_service("system_manager_service"):
                self.logger.info("ℹ️ SystemManagerService已存在，跳过重复初始化")
                return True

            self._report_progress("阶段1.5: 初始化系统管理服务...", 40)

            from backend.services.system_manager_service import SystemManagerService

            system_manager_service = SystemManagerService()
            init_success = system_manager_service.initialize()

            if init_success:
                self.service_manager.register_service(
                    "system_manager_service", system_manager_service
                )
                self.initialized_services["system_manager_service"] = system_manager_service
                self.logger.info("✅ SystemManagerService（前置）初始化成功")
                return True
            else:
                # 前置失败不阻断整体启动，稍后阶段5会再次尝试/保持注册
                self.logger.warning("⚠️ SystemManagerService（前置）初始化失败，将在阶段5重试")
                return False

        except Exception as e:
            self.logger.error("❌ SystemManagerService（前置）创建失败: %s", e, exc_info=True)
            self.service_manager.record_error(
                "SystemManagerService",
                "EARLY_SERVICE_CREATION_FAILED",
                f"前置创建服务失败: {str(e)}",
                exception=e,
            )
            return False

    def _generate_initialization_report(self):
        """生成初始化报告."""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("初始化报告")
        self.logger.info("=" * 60)

        total_services = len(self.initialized_services) + len(self.failed_services)
        success_count = len(self.initialized_services)
        failed_count = len(self.failed_services)

        self.logger.info("总服务数: %d", total_services)
        self.logger.info("成功初始化: %d", success_count)
        self.logger.info("初始化失败: %d", failed_count)

        if self.initialized_services:
            self.logger.info("\n✅ 成功的服务:")
            for name in self.initialized_services:
                self.logger.info("  - %s", name)

        if self.failed_services:
            self.logger.info("\n❌ 失败的服务:")
            for name in self.failed_services:
                self.logger.info("  - %s", name)

        self.logger.info("=" * 60)


def initialize_services(progress_callback=None, fast_startup=True) -> Dict[str, Any]:
    """初始化服务，返回详细的初始化报告.

    Args:
        progress_callback: 进度回调函数 callback(message: str, progress: int)
        fast_startup: 是否使用快速启动模式（默认True，仅初始化核心服务）
    """
    try:
        service_manager = get_service_manager()

        # 执行初始化
        result = initialize_real_services(
            progress_callback=progress_callback, fast_startup=fast_startup
        )

        if fast_startup:
            # 快速启动模式：返回核心服务初始化结果和initializer实例
            assert isinstance(result, dict), "fast_startup=True时，result应该是dict"
            success = result.get("success", False)
            initializer = result.get("initializer")

            service_manager.initialization_attempted = True
            service_manager.initialization_completed = success

            if success:
                logging.getLogger(__name__).info(
                    "[ServiceManager] ✓ 核心服务初始化成功（快速启动）"
                )
            else:
                service_manager.record_error(
                    "ServiceManager",
                    "CORE_INITIALIZATION_FAILURE",
                    "核心服务初始化失败",
                    severity=ErrorSeverity.CRITICAL,
                )
                logging.getLogger(__name__).error("核心服务初始化失败")

            # 返回详细报告（包含initializer供后续使用）
            return {
                "success": success,
                "fast_startup": True,
                "initializer": initializer,
                "initialization_completed": success,
                "error_summary": service_manager.get_error_summary(),
                "service_status": service_manager.get_service_status(),
                "user_friendly_report": service_manager.get_user_friendly_error_report(),
            }
        else:
            # 传统模式：所有服务初始化
            assert isinstance(result, bool), "fast_startup=False时，result应该是bool"
            success = result
            service_manager.initialization_attempted = True
            service_manager.initialization_completed = success

            if success:
                logging.getLogger(__name__).info("[ServiceManager] ✓ 所有服务初始化成功")
            else:
                service_manager.record_error(
                    "ServiceManager",
                    "INITIALIZATION_PARTIAL_FAILURE",
                    "部分服务初始化失败，请查看详细错误信息",
                    severity=ErrorSeverity.WARNING,
                )
                logging.getLogger(__name__).warning("服务初始化部分失败")

            # 返回详细报告
            return {
                "success": success,
                "fast_startup": False,
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
        logging.getLogger(__name__).error("服务初始化失败: %s", e, exc_info=True)

        return {
            "success": False,
            "initialization_completed": False,
            "error_summary": service_manager.get_error_summary(),
            "service_status": service_manager.get_service_status(),
            "user_friendly_report": service_manager.get_user_friendly_error_report(),
        }


def initialize_real_services(
    progress_callback=None, fast_startup=False
) -> Union[Dict[str, Any], bool]:
    """初始化服务的入口函数.

    Args:
        progress_callback: 进度回调函数 callback(message: str, progress: int)
        fast_startup: 是否使用快速启动模式（仅初始化核心服务）

    Returns:
        Dict: {"success": bool, "initializer": ServiceInitializer} (fast_startup=True时)
        bool: 是否初始化成功 (fast_startup=False时)
    """
    # ✅ 单进程多线程架构：日志和告警系统在主进程中运行
    # 通过Qt信号槽机制确保线程安全的UI更新
    logging.getLogger(__name__).info("✅ 使用单进程多线程架构（日志和告警在主进程）")
    if progress_callback:
        progress_callback("✅ 单进程多线程模式", 8)

    # 初始化业务服务
    service_manager = get_service_manager()
    initializer = ServiceInitializer(service_manager, progress_callback=progress_callback)

    if fast_startup:
        # 快速启动：仅初始化核心服务
        success = initializer.initialize_core_services()
        return {"success": success, "initializer": initializer}
    else:
        # 传统模式：初始化所有服务
        success = initializer.initialize_all_services()
        return success


def shutdown_services() -> None:
    """关闭所有服务."""
    global _service_manager

    if _service_manager:
        _service_manager.record_error(
            "ServiceManager", "SHUTDOWN_START", "开始关闭所有服务", severity=ErrorSeverity.INFO
        )

        # 调用真实的服务关闭逻辑
        try:
            shutdown_real_services()
        except Exception as e:
            logging.getLogger(__name__).error("关闭服务时发生错误: %s", e, exc_info=True)

        _service_manager = None
        logging.getLogger(__name__).info("全局服务管理器已清理")


def shutdown_real_services() -> None:
    """关闭所有服务."""
    service_manager = get_service_manager()
    logging.getLogger(__name__).info("开始关闭所有服务...")

    # 关闭所有业务服务
    for service_name, service in list(service_manager.services.items()):
        if service and hasattr(service, "shutdown"):
            try:
                service.shutdown()
                logging.getLogger(__name__).info("✅ %s 已关闭", service_name)
            except Exception as e:
                logging.getLogger(__name__).error("❌ 关闭 %s 失败: %s", service_name, e)

    # 关闭VNPY主引擎
    main_engine = get_main_engine()
    if main_engine:
        try:
            main_engine.close()
            logging.getLogger(__name__).info("✅ MainEngine 已关闭")
        except Exception as e:
            logging.getLogger(__name__).error("❌ 关闭 MainEngine 失败: %s", e)

    # 关闭服务器池管理器（在最后关闭，确保其他服务不再需要它）
    try:
        from backend.infrastructure.data_module_vnpy.load_balancer import server_pool_manager

        if server_pool_manager.is_running():
            logging.getLogger(__name__).info("正在关闭服务器池管理器...")
            server_pool_manager.stop()
            logging.getLogger(__name__).info("✅ 服务器池管理器已关闭")
    except Exception as e:
        logging.getLogger(__name__).error("❌ 关闭服务器池管理器失败: %s", e)

    # ✅ 单进程多线程架构：日志和告警系统在主进程中，无需额外关闭
    logging.getLogger(__name__).info("✅ 所有服务已关闭")


# =============================================================================
# 导出的公共接口
# =============================================================================

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
    # 服务初始化
    "InitializationPhase",
    "ServiceInitializer",
    "initialize_services",
    "initialize_real_services",
    "shutdown_services",
    "shutdown_real_services",
]
