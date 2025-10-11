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
# Part 1: 集中导入 (来自 imports.py)
# =============================================================================

import asyncio
import datetime
import json
import logging
import os
import sqlite3
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
from enum import Enum

# 网络请求
import requests

# 数据处理库
try:
    import numpy as np
    import pandas as pd

    PANDAS_AVAILABLE = True
    NUMPY_AVAILABLE = True
except ImportError:
    pd = None  # type: ignore
    np = None  # type: ignore
    PANDAS_AVAILABLE = False
    NUMPY_AVAILABLE = False

# 系统监控
try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None  # type: ignore
    PSUTIL_AVAILABLE = False

# VnPy核心模块 - 直接从vnpy包导入
try:
    from vnpy.event import Event, EventEngine
    from vnpy.trader.engine import MainEngine
    from vnpy.trader.object import (
        AccountData,
        BarData,
        OrderData,
        PositionData,
        TickData,
        TradeData,
    )
    from vnpy.trader.event import (
        EVENT_ACCOUNT,
        EVENT_LOG,
        EVENT_ORDER,
        EVENT_POSITION,
        EVENT_TICK,
        EVENT_TRADE,
    )

    VNPY_AVAILABLE = True
except ImportError:
    # 如果导入失败，提供存根
    VNPY_AVAILABLE = False
    MainEngine = None
    EventEngine = None
    Event = None
    TickData = None
    BarData = None
    OrderData = None
    TradeData = None
    PositionData = None
    AccountData = None
    EVENT_TICK = "eTick"
    EVENT_ORDER = "eOrder"
    EVENT_TRADE = "eTrade"
    EVENT_POSITION = "ePosition"
    EVENT_ACCOUNT = "eAccount"
    EVENT_LOG = "eLog"

# VnPy策略引擎
try:
    if VNPY_AVAILABLE:
        from vnpy_ctastrategy import CtaEngine as CTA_ENGINE

        CTA_ENGINE_AVAILABLE = True
    else:
        CTA_ENGINE_AVAILABLE = False
        CTA_ENGINE = None  # type: ignore
except ImportError:
    CTA_ENGINE_AVAILABLE = False
    CTA_ENGINE = None  # type: ignore

try:
    if VNPY_AVAILABLE:
        from vnpy_algotrading import AlgoEngine as ALGO_ENGINE

        ALGO_ENGINE_AVAILABLE = True
    else:
        ALGO_ENGINE_AVAILABLE = False
        ALGO_ENGINE = None  # type: ignore
except ImportError:
    ALGO_ENGINE_AVAILABLE = False
    ALGO_ENGINE = None  # type: ignore

try:
    if VNPY_AVAILABLE:
        from vnpy_portfoliostrategy import StrategyEngine as PORTFOLIO_ENGINE

        PORTFOLIO_ENGINE_AVAILABLE = True
    else:
        PORTFOLIO_ENGINE_AVAILABLE = False
        PORTFOLIO_ENGINE = None  # type: ignore
except ImportError:
    PORTFOLIO_ENGINE_AVAILABLE = False
    PORTFOLIO_ENGINE = None  # type: ignore

# VnPy网关
try:
    if VNPY_AVAILABLE:
        try:
            from vnpy_ctp import CtpGateway as CTP_GATEWAY  # type: ignore

            CTP_GATEWAY_AVAILABLE = True
        except ImportError:
            CTP_GATEWAY_AVAILABLE = False
            CTP_GATEWAY = None  # type: ignore
    else:
        CTP_GATEWAY_AVAILABLE = False
        CTP_GATEWAY = None  # type: ignore
except ImportError:
    CTP_GATEWAY_AVAILABLE = False
    CTP_GATEWAY = None  # type: ignore

try:
    if VNPY_AVAILABLE:
        try:
            from vnpy_ib import IbGateway as IB_GATEWAY  # type: ignore

            IB_GATEWAY_AVAILABLE = True
        except ImportError:
            IB_GATEWAY_AVAILABLE = False
            IB_GATEWAY = None  # type: ignore
    else:
        IB_GATEWAY_AVAILABLE = False
        IB_GATEWAY = None  # type: ignore
except ImportError:
    IB_GATEWAY_AVAILABLE = False
    IB_GATEWAY = None  # type: ignore

try:
    if VNPY_AVAILABLE:
        try:
            from vnpy_paperaccount import PaperAccountGateway as PAPER_ACCOUNT_GATEWAY  # type: ignore

            PAPERACCOUNT_GATEWAY_AVAILABLE = True
        except ImportError:
            PAPERACCOUNT_GATEWAY_AVAILABLE = False
            PAPER_ACCOUNT_GATEWAY = None  # type: ignore
    else:
        PAPERACCOUNT_GATEWAY_AVAILABLE = False
        PAPER_ACCOUNT_GATEWAY = None  # type: ignore
except ImportError:
    PAPERACCOUNT_GATEWAY_AVAILABLE = False
    PAPER_ACCOUNT_GATEWAY = None  # type: ignore

# VnPy数据源
try:
    if VNPY_AVAILABLE:
        try:
            from vnpy_tushare import TushareDatafeed as TUSHARE_DATAFEED  # type: ignore

            TUSHARE_DATAFEED_AVAILABLE = True
        except ImportError:
            TUSHARE_DATAFEED_AVAILABLE = False
            TUSHARE_DATAFEED = None  # type: ignore
    else:
        TUSHARE_DATAFEED_AVAILABLE = False
        TUSHARE_DATAFEED = None  # type: ignore
except ImportError:
    TUSHARE_DATAFEED_AVAILABLE = False
    TUSHARE_DATAFEED = None  # type: ignore

try:
    if VNPY_AVAILABLE:
        try:
            from vnpy_rqdata import RqdataDatafeed as RQDATA_DATAFEED  # type: ignore

            RQDATA_DATAFEED_AVAILABLE = True
        except ImportError:
            RQDATA_DATAFEED_AVAILABLE = False
            RQDATA_DATAFEED = None  # type: ignore
    else:
        RQDATA_DATAFEED_AVAILABLE = False
        RQDATA_DATAFEED = None  # type: ignore
except ImportError:
    RQDATA_DATAFEED_AVAILABLE = False
    RQDATA_DATAFEED = None  # type: ignore

# Infrastructure模块
try:
    from ..infrastructure.system_vnpy.system_monitor import SystemMonitor  # type: ignore
    from ..infrastructure.system_vnpy.process_manager import ProcessManager  # type: ignore

    SYSTEM_MODULE_AVAILABLE = True
except ImportError:
    SystemMonitor = None  # type: ignore
    ProcessManager = None  # type: ignore
    SYSTEM_MODULE_AVAILABLE = False


def setup_logging(
    name: str = "terminal", level: str = "INFO", log_file: Optional[str] = None
) -> logging.Logger:
    """
    配置日志系统.

    Args:
        name: 日志名称
        level: 日志级别
        log_file: 日志文件路径（可选）

    Returns:
        配置好的Logger对象
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    if logger.handlers:
        return logger

    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 文件处理器
    if log_file:
        try:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setLevel(logging.DEBUG)
            file_formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s"
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)
        except OSError as e:
            logger.warning("无法创建日志文件: %s", e)

    return logger


def vnpy_to_pandas(vnpy_data_list: List[Any], data_type: str = "bar") -> Optional[Any]:
    """
    将VnPy数据对象转换为pandas DataFrame.

    Args:
        vnpy_data_list: VnPy数据对象列表
        data_type: 数据类型 ("bar" 或 "tick")

    Returns:
        pandas DataFrame或None
    """
    if not PANDAS_AVAILABLE or not vnpy_data_list:
        return None

    try:
        if not PANDAS_AVAILABLE or pd is None:
            return None

        if data_type == "bar":
            df = pd.DataFrame(
                [
                    {
                        "datetime": data.datetime,
                        "symbol": data.symbol,
                        "open": data.open_price,
                        "high": data.high_price,
                        "low": data.low_price,
                        "close": data.close_price,
                        "volume": data.volume,
                    }
                    for data in vnpy_data_list
                ]
            )
        elif data_type == "tick":
            df = pd.DataFrame(
                [
                    {
                        "datetime": data.datetime,
                        "symbol": data.symbol,
                        "last_price": data.last_price,
                        "volume": data.volume,
                        "bid_price": data.bid_price_1,
                        "ask_price": data.ask_price_1,
                    }
                    for data in vnpy_data_list
                ]
            )
        else:
            return None

        if not df.empty:
            df["datetime"] = pd.to_datetime(df["datetime"])
            df.set_index("datetime", inplace=True)

        return df
    except Exception as e:
        logging.error("VnPy数据转换失败: %s", e)
        return None


# 别名定义
CtpGateway = CTP_GATEWAY if CTP_GATEWAY_AVAILABLE else None
IbGateway = IB_GATEWAY if IB_GATEWAY_AVAILABLE else None
PaperAccountGateway = (
    PAPER_ACCOUNT_GATEWAY
    if "PAPER_ACCOUNT_GATEWAY" in locals() and PAPER_ACCOUNT_GATEWAY is not None
    else None
)
PortfolioEngine = PORTFOLIO_ENGINE if PORTFOLIO_ENGINE_AVAILABLE else None
RqdataDatafeed = RQDATA_DATAFEED if RQDATA_DATAFEED_AVAILABLE else None
TushareDatafeed = TUSHARE_DATAFEED if TUSHARE_DATAFEED_AVAILABLE else None


# =============================================================================
# Part 2: 共享服务管理器 (来自 shared_services.py)
# =============================================================================


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
                "timestamp": datetime.datetime.now().isoformat(),
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


def get_message_publisher():
    """获取全局消息发布器实例."""
    # 消息发布器需要事件引擎和WebSocket服务器来初始化
    # 这里暂时返回None，实际使用时需要确保这些依赖可用
    return None


# =============================================================================
# Part 3: 服务初始化器 (来自 service_initializer.py)
# =============================================================================


class InitializationPhase(Enum):
    """初始化阶段."""

    VNPY_CORE = "vnpy_core"  # VNPY核心框架
    DATA_ENGINES = "data_engines"  # 数据引擎（ChinaStockEngine等）
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

    def __init__(self, service_manager):
        """初始化服务初始化器.

        Args:
            service_manager: 服务管理器实例
        """
        self.service_manager = service_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        self.initialized_services: Dict[str, Any] = {}
        self.failed_services: List[str] = []

        # VNPY引擎实例
        self.main_engine = None
        self.event_engine = None
        self.china_stock_engine = None

    def initialize_all_services(self) -> bool:
        """初始化所有服务.

        Returns:
            bool: 是否成功初始化（允许部分失败）
        """
        try:
            self.logger.info("=" * 60)
            self.logger.info("开始初始化服务...")
            self.logger.info("=" * 60)

            # 🔧 修复点1：显式初始化配置（从环境变量指定的路径）
            from backend.config import init_settings, get_settings
            import os

            config_file = os.getenv("CONFIG_FILE")
            if config_file:
                self.logger.info("从环境变量加载配置文件: %s", config_file)
                init_settings(config_file)
            else:
                self.logger.info("使用默认配置文件")
                init_settings()

            # 验证配置已加载
            settings = get_settings()
            self.logger.info("配置文件路径: %s", settings.config_file)
            if settings.ai.api_key:
                masked_key = (
                    f"{settings.ai.api_key[:4]}...{settings.ai.api_key[-4:]}"
                    if len(settings.ai.api_key) > 8
                    else "***"
                )
                self.logger.info("AI API Key: %s", masked_key)
            else:
                self.logger.info("AI API Key: 未设置")

            # 阶段1: 初始化VNPY核心框架
            phase1_success = self._initialize_vnpy_core()

            # 阶段2: 初始化数据引擎
            phase2_success = self._initialize_data_engines()

            # 阶段3: 初始化数据服务
            phase3_success = self._initialize_data_services()

            # 阶段4: 初始化交易服务
            self._initialize_trading_services()

            # 阶段5: 初始化策略服务
            self._initialize_strategy_services()

            # 阶段6: 初始化辅助服务
            self._initialize_auxiliary_services()

            # 生成初始化报告
            self._generate_initialization_report()

            # 如果核心服务初始化成功，即使部分服务失败也返回True
            core_services_ok = phase1_success or phase2_success or phase3_success

            if core_services_ok:
                self.logger.info("✅ 核心服务初始化成功，系统可以启动")
                return True
            else:
                self.logger.error("❌ 核心服务初始化失败，系统无法正常启动")
                return False

        except Exception as e:
            self.logger.error("服务初始化过程发生严重异常: %s", e, exc_info=True)
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

        self.logger.info("开始添加策略应用...")

        # 1. CTA策略应用
        try:
            from vnpy_ctastrategy import CtaStrategyApp

            self.main_engine.add_app(CtaStrategyApp)
            self.logger.info("✅ CtaStrategyApp 已添加")
        except ImportError:
            self.logger.warning("⚠️ vnpy_ctastrategy 未安装")
        except Exception as e:
            self.logger.error("❌ 添加 CtaStrategyApp 失败: %s", e)

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
            from vnpy_scripttrader import ScriptTraderApp

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

    def _initialize_vnpy_core(self) -> bool:
        """阶段1: 初始化VNPY核心框架.

        Returns:
            bool: 是否成功
        """
        self.logger.info("\n" + "=" * 60)
        self.logger.info("阶段1: 初始化VNPY核心框架")
        self.logger.info("=" * 60)

        try:
            # 导入VNPY核心类
            try:
                from vnpy.event import EventEngine
                from vnpy.trader.engine import MainEngine

                self.logger.info("✅ VNPY核心模块导入成功")
            except ImportError as e:
                self.logger.error("❌ VNPY核心模块导入失败: %s", e)
                self.failed_services.append("vnpy_core")
                return False

            # 创建事件引擎
            try:
                self.event_engine = EventEngine()
                self.logger.info("✅ EventEngine 创建成功")
            except Exception as e:
                self.logger.error("❌ EventEngine 创建失败: %s", e, exc_info=True)
                self.failed_services.append("event_engine")
                return False

            # 创建主引擎
            try:
                self.main_engine = MainEngine(self.event_engine)
                self.logger.info("✅ MainEngine 创建成功")
            except Exception as e:
                self.logger.error("❌ MainEngine 创建失败: %s", e, exc_info=True)
                self.failed_services.append("main_engine")
                return False

            # 配置数据服务（使用本地data_module_vnpy作为datafeed）
            self._configure_datafeed()

            # 注册到全局
            set_main_engine(self.main_engine)
            set_event_engine(self.event_engine)

            # 延迟加载策略应用（避免启动时内存错误）
            # 策略应用将在首次使用时按需加载
            # self._add_strategy_apps()

            self.logger.info("✅ VNPY核心框架初始化完成")
            return True

        except Exception as e:
            self.logger.error("❌ VNPY核心框架初始化失败: %s", e, exc_info=True)
            self.failed_services.append("vnpy_core")
            return False

    def _initialize_data_engines(self) -> bool:
        """阶段2: 初始化数据引擎.

        Returns:
            bool: 是否成功
        """
        self.logger.info("\n" + "=" * 60)
        self.logger.info("阶段2: 初始化数据引擎")
        self.logger.info("=" * 60)

        if not self.main_engine or not self.event_engine:
            self.logger.warning("⚠️ VNPY引擎未初始化，跳过数据引擎初始化")
            return False

        try:
            # 初始化ChinaStockEngine
            try:
                from backend.infrastructure.data_module_vnpy.engine import ChinaStockEngine

                self.china_stock_engine = ChinaStockEngine(self.main_engine, self.event_engine)
                self.logger.info("✅ ChinaStockEngine 创建成功")

                # 注册到全局
                set_china_stock_engine(self.china_stock_engine)

            except ImportError as e:
                self.logger.warning("⚠️ ChinaStockEngine 不可用: %s", e)
                self.failed_services.append("china_stock_engine")
            except Exception as e:
                self.logger.error("❌ ChinaStockEngine 初始化失败: %s", e, exc_info=True)
                self.failed_services.append("china_stock_engine")

            # 集成data_engine作为vnpy datafeed
            try:
                from backend.infrastructure.data_engine.vnpy_datafeed import DataEngineGateway

                # 添加DataEngine网关到MainEngine
                self.main_engine.add_gateway(DataEngineGateway)
                self.logger.info("✅ DataEngine网关已注册")

            except ImportError as e:
                self.logger.warning("⚠️ DataEngine网关不可用: %s", e)
            except Exception as e:
                self.logger.error("❌ DataEngine网关注册失败: %s", e, exc_info=True)

            self.logger.info("✅ 数据引擎初始化完成")
            return True

        except Exception as e:
            self.logger.error("❌ 数据引擎初始化失败: %s", e, exc_info=True)
            return False

    def _initialize_data_services(self) -> bool:
        """阶段3: 初始化数据服务.

        Returns:
            bool: 是否成功
        """
        self.logger.info("\n" + "=" * 60)
        self.logger.info("阶段3: 初始化数据服务")
        self.logger.info("=" * 60)

        success_count = 0

        # 初始化DataCenterService
        try:
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

        return success_count > 0

    def _initialize_trading_services(self) -> bool:
        """阶段4: 初始化交易服务.

        Returns:
            bool: 是否成功
        """
        self.logger.info("\n" + "=" * 60)
        self.logger.info("阶段4: 初始化交易服务")
        self.logger.info("=" * 60)

        success_count = 0

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
                success_count += 1
            else:
                self.logger.warning("⚠️ TradingGatewayService 初始化失败")
                self.failed_services.append("trading_gateway_service")

        except Exception as e:
            self.logger.error("❌ TradingGatewayService 初始化异常: %s", e, exc_info=True)
            self.failed_services.append("trading_gateway_service")

        return success_count > 0

    def _initialize_strategy_services(self) -> bool:
        """阶段5: 初始化策略服务.

        Returns:
            bool: 是否成功
        """
        self.logger.info("\n" + "=" * 60)
        self.logger.info("阶段5: 初始化策略服务")
        self.logger.info("=" * 60)

        success_count = 0

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
                success_count += 1
            else:
                self.logger.warning("⚠️ StrategyCenterService 初始化失败")
                self.failed_services.append("strategy_center_service")

        except Exception as e:
            self.logger.error("❌ StrategyCenterService 初始化异常: %s", e, exc_info=True)
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
                success_count += 1
            else:
                # AI是可选功能，降低日志级别避免干扰
                self.logger.debug("⚠️ AIAssistantService 初始化失败（可能未配置API密钥）")
                self.failed_services.append("ai_assistant_service")

        except Exception as e:
            # AI是可选功能，降低日志级别避免干扰
            self.logger.debug("❌ AIAssistantService 初始化异常: %s", e)
            self.failed_services.append("ai_assistant_service")

        return success_count > 0

    def _initialize_auxiliary_services(self) -> bool:
        """阶段6: 初始化辅助服务.

        Returns:
            bool: 是否成功
        """
        self.logger.info("\n" + "=" * 60)
        self.logger.info("阶段6: 初始化辅助服务")
        self.logger.info("=" * 60)

        success_count = 0

        # 初始化PortfolioService
        try:
            from backend.services.portfolio_service import PortfolioService

            portfolio_service = PortfolioService()
            init_success = portfolio_service.initialize()

            if init_success:
                self.service_manager.register_service("portfolio_service", portfolio_service)
                self.initialized_services["portfolio_service"] = portfolio_service
                self.logger.info("✅ PortfolioService 初始化成功")
                success_count += 1
            else:
                self.logger.warning("⚠️ PortfolioService 初始化失败")
                self.failed_services.append("portfolio_service")

        except Exception as e:
            self.logger.error("❌ PortfolioService 初始化异常: %s", e, exc_info=True)
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
                success_count += 1
            else:
                self.logger.warning("⚠️ MarketBoardService 初始化失败")
                self.failed_services.append("market_board_service")

        except Exception as e:
            self.logger.error("❌ MarketBoardService 初始化异常: %s", e, exc_info=True)
            self.failed_services.append("market_board_service")

        # 初始化SystemManagerService
        # 🔧 修复点3：SystemManagerService 专门处理（即使初始化失败也注册服务）
        try:
            from backend.services.system_manager_service import SystemManagerService

            system_manager_service = SystemManagerService()
            init_success = system_manager_service.initialize()

            if init_success:
                self.service_manager.register_service(
                    "system_manager_service", system_manager_service
                )
                self.initialized_services["system_manager_service"] = system_manager_service
                self.logger.info("✅ SystemManagerService 初始化成功")
                success_count += 1
            else:
                self.logger.warning("⚠️ SystemManagerService 初始化失败（但已注册服务）")
                # 即使初始化失败，也注册服务（让UI能够访问）
                self.service_manager.register_service(
                    "system_manager_service", system_manager_service
                )
                self.failed_services.append("system_manager_service")

        except Exception as e:
            self.logger.error("❌ SystemManagerService 创建失败: %s", e, exc_info=True)
            self.service_manager.record_error(
                "SystemManagerService",
                "SERVICE_CREATION_FAILED",
                f"创建服务失败: {str(e)}",
                exception=e,
            )
            self.failed_services.append("system_manager_service")

        return success_count > 0

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


def initialize_services() -> Dict[str, Any]:
    """初始化所有服务，返回详细的初始化报告"""
    try:
        service_manager = get_service_manager()

        # 记录初始化开始
        service_manager.record_error(
            "ServiceManager",
            "INITIALIZATION_START",
            "开始初始化所有服务",
            severity=ErrorSeverity.INFO,
        )

        # 执行初始化
        success = initialize_real_services()
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
            logging.getLogger(__name__).info("服务初始化完成")
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


def initialize_real_services() -> bool:
    """初始化所有服务的入口函数.

    Returns:
        bool: 是否初始化成功
    """
    service_manager = get_service_manager()
    initializer = ServiceInitializer(service_manager)
    return initializer.initialize_all_services()


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

    logging.getLogger(__name__).info("所有服务已关闭")


# =============================================================================
# 导出的公共接口
# =============================================================================

__all__ = [
    # 标准库
    "os",
    "sys",
    "json",
    "time",
    "datetime",
    "traceback",
    "asyncio",
    "threading",
    "sqlite3",
    "logging",
    "Path",
    "ThreadPoolExecutor",
    # 类型
    "Dict",
    "List",
    "Optional",
    "Any",
    "Union",
    "Tuple",
    # 网络
    "requests",
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
    "get_message_publisher",
    # 服务初始化
    "InitializationPhase",
    "ServiceInitializer",
    "initialize_services",
    "initialize_real_services",
    "shutdown_services",
    "shutdown_real_services",
]
