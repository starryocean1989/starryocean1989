# -*- coding: utf-8 -*-
"""
VnPy服务适配器 - 错误追踪和详细报告版本

专注于详细错误报告机制，让用户知道VnPy集成的具体问题。
不实现多层级降级机制，而是提供完整的错误信息追踪。
"""

# pylint: disable=protected-access
# 说明：VnPyServiceAdapter需要访问ServiceManager的_record_error方法进行错误追踪

import logging
import threading
import traceback
from datetime import datetime
from typing import Any, Dict, List
from enum import Enum

from .shared_services import ErrorSeverity, ServiceManager

logger = logging.getLogger(__name__)


class VnPyServiceStatus(Enum):
    """VnPy服务状态."""

    NOT_INITIALIZED = "not_initialized"
    INITIALIZING = "initializing"
    INITIALIZATION_FAILED = "initialization_failed"
    READY = "ready"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"


class VnPyServiceAdapter:
    """VnPy服务适配器 - 专注于错误追踪和报告"""

    def __init__(self, service_manager: ServiceManager):
        """初始化VnPy服务适配器."""
        self.service_manager = service_manager
        self.logger = logging.getLogger("VnPyServiceAdapter")
        self.status = VnPyServiceStatus.NOT_INITIALIZED
        self._lock = threading.RLock()

        # VnPy组件状态
        self.vnpy_available = False
        self.terminal_engine = None
        self.main_engine = None
        self.event_engine = None

        # 数据中心需要的ChinaStock引擎
        self.chinastock_engine = None

        # 错误追踪
        self.initialization_errors = []
        self.operation_errors = []

        self._attempt_vnpy_initialization()

    def _attempt_vnpy_initialization(self):
        """尝试初始化VnPy组件"""
        self.status = VnPyServiceStatus.INITIALIZING

        try:
            # 尝试导入VnPy核心模块
            self._import_vnpy_modules()

            # 初始化VnPy引擎
            self._initialize_vnpy_engines()

            # 初始化数据中心需要的ChinaStock引擎
            self._initialize_chinastock_engine()

            self.status = VnPyServiceStatus.READY
            self.service_manager._record_error(
                "VnPyServiceAdapter",
                "INITIALIZATION_SUCCESS",
                "VnPy服务适配器初始化成功",
                severity=ErrorSeverity.INFO,
            )

        except Exception as e:
            self.status = VnPyServiceStatus.INITIALIZATION_FAILED
            error_msg = f"VnPy服务适配器初始化失败: {str(e)}"
            self.service_manager._record_error(
                "VnPyServiceAdapter",
                "INITIALIZATION_FAILED",
                error_msg,
                exception=e,
                severity=ErrorSeverity.CRITICAL,
            )
            self.initialization_errors.append(
                {"timestamp": datetime.now(), "error": str(e), "traceback": traceback.format_exc()}
            )

    def _import_vnpy_modules(self):
        """导入VnPy模块"""
        try:
            # 尝试导入VnPy核心 - 这些导入用于验证VnPy包是否正确安装
            from vnpy.trader.engine import MainEngine  # noqa: F401
            from vnpy.event import EventEngine, Event  # noqa: F401
            from vnpy.trader.object import (  # noqa: F401
                BaseData,
                TickData,
                BarData,
                OrderData,
                TradeData,
                PositionData,
                AccountData,
            )

            self.vnpy_available = True
            self.service_manager._record_error(
                "VnPyServiceAdapter",
                "VNPY_IMPORT_SUCCESS",
                "VnPy核心模块导入成功",
                severity=ErrorSeverity.INFO,
            )

        except ImportError as e:
            self.vnpy_available = False
            error_msg = f"VnPy核心模块导入失败: {str(e)}. 请确保已正确安装VnPy包"
            self.service_manager._record_error(
                "VnPyServiceAdapter",
                "VNPY_IMPORT_FAILED",
                error_msg,
                exception=e,
                severity=ErrorSeverity.CRITICAL,
            )
            raise RuntimeError(error_msg) from e

        # 尝试导入data_module_vnpy包
        try:
            from backend.infrastructure.data_module_vnpy import ChinaStockEngine  # noqa: F401

            self.service_manager._record_error(
                "VnPyServiceAdapter",
                "DATA_MODULE_IMPORT_SUCCESS",
                "data_module_vnpy包导入成功",
                severity=ErrorSeverity.INFO,
            )

        except ImportError as e:
            error_msg = f"data_module_vnpy包导入失败: {str(e)}. 这将影响品种列表功能"
            self.service_manager._record_error(
                "VnPyServiceAdapter",
                "DATA_MODULE_IMPORT_FAILED",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            raise RuntimeError(error_msg) from e

    def _initialize_vnpy_engines(self):
        """初始化VnPy引擎"""
        try:
            from vnpy.event import EventEngine
            from vnpy.trader.engine import MainEngine

            # 初始化事件引擎
            self.event_engine = EventEngine()
            self.service_manager._record_error(
                "VnPyServiceAdapter",
                "EVENT_ENGINE_INIT_SUCCESS",
                "VnPy事件引擎初始化成功",
                severity=ErrorSeverity.INFO,
            )

            # 初始化主引擎
            self.main_engine = MainEngine(self.event_engine)
            self.service_manager._record_error(
                "VnPyServiceAdapter",
                "MAIN_ENGINE_INIT_SUCCESS",
                "VnPy主引擎初始化成功",
                severity=ErrorSeverity.INFO,
            )

        except Exception as e:
            error_msg = f"VnPy引擎初始化失败: {str(e)}"
            self.service_manager._record_error(
                "VnPyServiceAdapter",
                "ENGINE_INIT_FAILED",
                error_msg,
                exception=e,
                severity=ErrorSeverity.CRITICAL,
            )
            raise RuntimeError(error_msg) from e

    def _initialize_chinastock_engine(self):
        """初始化ChinaStock引擎（数据中心品种列表功能需要）"""
        try:
            from backend.infrastructure.data_module_vnpy import ChinaStockEngine

            # 创建ChinaStock引擎实例
            self.chinastock_engine = ChinaStockEngine(self.main_engine, self.event_engine)

            self.service_manager._record_error(
                "VnPyServiceAdapter",
                "CHINASTOCK_ENGINE_INIT_SUCCESS",
                "ChinaStock引擎初始化成功，品种列表功能可用",
                severity=ErrorSeverity.INFO,
            )

        except Exception as e:
            error_msg = f"ChinaStock引擎初始化失败: {str(e)}. 品种列表功能将不可用"
            self.service_manager._record_error(
                "VnPyServiceAdapter",
                "CHINASTOCK_ENGINE_INIT_FAILED",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            # 不抛出异常，因为这不是致命错误
            self.chinastock_engine = None

    def get_status(self) -> Dict[str, Any]:
        """获取VnPy服务状态"""
        return {
            "status": self.status.value,
            "vnpy_available": self.vnpy_available,
            "main_engine_available": self.main_engine is not None,
            "event_engine_available": self.event_engine is not None,
            "chinastock_engine_available": self.chinastock_engine is not None,
            "initialization_errors_count": len(self.initialization_errors),
            "operation_errors_count": len(self.operation_errors),
        }

    def get_chinastock_engine(self):
        """获取ChinaStock引擎（数据中心品种列表功能）"""
        if self.chinastock_engine is None:
            error_msg = (
                "ChinaStock引擎不可用。可能的原因：1) data_module_vnpy包未安装 2) 初始化失败"
            )
            self.service_manager._record_error(
                "VnPyServiceAdapter",
                "CHINASTOCK_ENGINE_NOT_AVAILABLE",
                error_msg,
                severity=ErrorSeverity.ERROR,
            )
            return None

        return self.chinastock_engine

    def refresh_stock_list(self) -> Dict[str, List[str]]:
        """刷新股票列表（品种列表功能）"""
        try:
            if self.chinastock_engine is None:
                error_msg = "无法刷新股票列表：ChinaStock引擎不可用"
                self.service_manager._record_error(
                    "VnPyServiceAdapter",
                    "REFRESH_STOCK_LIST_ENGINE_UNAVAILABLE",
                    error_msg,
                    severity=ErrorSeverity.ERROR,
                )
                return {}

            # 调用ChinaStock引擎的刷新方法
            result = self.chinastock_engine.refresh_stock_list()

            if result:
                self.service_manager._record_error(
                    "VnPyServiceAdapter",
                    "REFRESH_STOCK_LIST_SUCCESS",
                    f"股票列表刷新成功，获得{len(result)}类品种",
                    severity=ErrorSeverity.INFO,
                )
                return result
            else:
                error_msg = "股票列表刷新返回空结果"
                self.service_manager._record_error(
                    "VnPyServiceAdapter",
                    "REFRESH_STOCK_LIST_EMPTY_RESULT",
                    error_msg,
                    severity=ErrorSeverity.WARNING,
                )
                return {}

        except Exception as e:
            error_msg = f"刷新股票列表时发生异常: {str(e)}"
            self.service_manager._record_error(
                "VnPyServiceAdapter",
                "REFRESH_STOCK_LIST_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            self.operation_errors.append(
                {
                    "timestamp": datetime.now(),
                    "operation": "refresh_stock_list",
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )
            return {}

    def reload_stock_list(self) -> bool:
        """重新加载股票列表（品种列表重新加载功能）"""
        try:
            if self.chinastock_engine is None:
                error_msg = "无法重新加载股票列表：ChinaStock引擎不可用"
                self.service_manager._record_error(
                    "VnPyServiceAdapter",
                    "RELOAD_STOCK_LIST_ENGINE_UNAVAILABLE",
                    error_msg,
                    severity=ErrorSeverity.ERROR,
                )
                return False

            # 调用ChinaStock引擎的重新加载方法
            success = self.chinastock_engine.reload_stock_list()

            if success:
                self.service_manager._record_error(
                    "VnPyServiceAdapter",
                    "RELOAD_STOCK_LIST_SUCCESS",
                    "股票列表重新加载成功",
                    severity=ErrorSeverity.INFO,
                )
                return True
            else:
                error_msg = "股票列表重新加载失败：引擎返回False"
                self.service_manager._record_error(
                    "VnPyServiceAdapter",
                    "RELOAD_STOCK_LIST_FAILED",
                    error_msg,
                    severity=ErrorSeverity.ERROR,
                )
                return False

        except Exception as e:
            error_msg = f"重新加载股票列表时发生异常: {str(e)}"
            self.service_manager._record_error(
                "VnPyServiceAdapter",
                "RELOAD_STOCK_LIST_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            self.operation_errors.append(
                {
                    "timestamp": datetime.now(),
                    "operation": "reload_stock_list",
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                }
            )
            return False

    def get_symbols(self) -> List[Dict[str, Any]]:
        """获取品种符号列表"""
        try:
            stock_list = self.refresh_stock_list()

            if not stock_list:
                self.service_manager._record_error(
                    "VnPyServiceAdapter",
                    "GET_SYMBOLS_EMPTY_LIST",
                    "获取品种符号列表为空",
                    severity=ErrorSeverity.WARNING,
                )
                return []

            # 转换为标准格式
            symbols = []
            for category, symbol_list in stock_list.items():
                for symbol in symbol_list:
                    symbols.append(
                        {
                            "symbol": symbol,
                            "name": f"{category}_{symbol}",
                            "category": category,
                            "exchange": self._get_exchange_from_symbol(symbol),
                        }
                    )

            self.service_manager._record_error(
                "VnPyServiceAdapter",
                "GET_SYMBOLS_SUCCESS",
                f"获取品种符号列表成功，共{len(symbols)}个品种",
                severity=ErrorSeverity.INFO,
            )

            return symbols

        except Exception as e:
            error_msg = f"获取品种符号列表时发生异常: {str(e)}"
            self.service_manager._record_error(
                "VnPyServiceAdapter",
                "GET_SYMBOLS_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return []

    def _get_exchange_from_symbol(self, symbol: str) -> str:
        """根据品种代码推断交易所"""
        if symbol.startswith("60") or symbol.startswith("51") or symbol.startswith("50"):
            return "SSE"  # 上交所
        elif symbol.startswith("00") or symbol.startswith("30") or symbol.startswith("15"):
            return "SZSE"  # 深交所
        elif symbol.startswith("8") or symbol.startswith("4"):
            return "BSE"  # 北交所
        else:
            return "UNKNOWN"

    def test_connection(self) -> Dict[str, Any]:
        """测试VnPy连接状态"""
        test_result = {
            "vnpy_core_available": False,
            "data_module_available": False,
            "chinastock_engine_available": False,
            "basic_functionality": False,
            "details": [],
        }

        try:
            # 测试VnPy核心
            if self.vnpy_available and self.main_engine and self.event_engine:
                test_result["vnpy_core_available"] = True
                test_result["details"].append("✅ VnPy核心模块可用")
            else:
                test_result["details"].append("❌ VnPy核心模块不可用")

            # 测试data_module_vnpy
            if self.chinastock_engine is not None:
                test_result["data_module_available"] = True
                test_result["chinastock_engine_available"] = True
                test_result["details"].append("✅ data_module_vnpy包可用")
                test_result["details"].append("✅ ChinaStock引擎可用")
            else:
                test_result["details"].append("❌ data_module_vnpy包或ChinaStock引擎不可用")

            # 测试基本功能
            symbols = self.get_symbols()
            if symbols:
                test_result["basic_functionality"] = True
                test_result["details"].append(f"✅ 基本功能正常，获得{len(symbols)}个品种")
            else:
                test_result["details"].append("❌ 基本功能异常，无法获取品种列表")

            overall_status = (
                test_result["vnpy_core_available"]
                and test_result["data_module_available"]
                and test_result["basic_functionality"]
            )

            if overall_status:
                self.service_manager._record_error(
                    "VnPyServiceAdapter",
                    "CONNECTION_TEST_SUCCESS",
                    "VnPy连接测试成功",
                    severity=ErrorSeverity.INFO,
                )
            else:
                self.service_manager._record_error(
                    "VnPyServiceAdapter",
                    "CONNECTION_TEST_PARTIAL_FAILURE",
                    "VnPy连接测试部分失败",
                    severity=ErrorSeverity.WARNING,
                )

            test_result["overall_status"] = overall_status
            return test_result

        except Exception as e:
            error_msg = f"VnPy连接测试时发生异常: {str(e)}"
            self.service_manager._record_error(
                "VnPyServiceAdapter",
                "CONNECTION_TEST_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            test_result["details"].append(f"❌ 测试异常: {str(e)}")
            test_result["overall_status"] = False
            return test_result

    def get_detailed_status_report(self) -> str:
        """获取详细状态报告"""
        report_lines = []
        report_lines.append("🔍 VnPy服务适配器状态报告")
        report_lines.append("=" * 50)

        # 基本状态
        status_icon = {
            VnPyServiceStatus.NOT_INITIALIZED: "⚪",
            VnPyServiceStatus.INITIALIZING: "🟡",
            VnPyServiceStatus.INITIALIZATION_FAILED: "🔴",
            VnPyServiceStatus.READY: "🟢",
            VnPyServiceStatus.ERROR: "🔴",
        }

        icon = status_icon.get(self.status, "❓")
        report_lines.append(f"📊 当前状态: {icon} {self.status.value}")

        # 组件可用性
        report_lines.append("\n🧩 组件可用性:")
        report_lines.append(f"  VnPy核心: {'✅' if self.vnpy_available else '❌'}")
        report_lines.append(f"  主引擎: {'✅' if self.main_engine else '❌'}")
        report_lines.append(f"  事件引擎: {'✅' if self.event_engine else '❌'}")
        report_lines.append(f"  ChinaStock引擎: {'✅' if self.chinastock_engine else '❌'}")

        # 错误统计
        if self.initialization_errors or self.operation_errors:
            report_lines.append("\n🚨 错误统计:")
            report_lines.append(f"  初始化错误: {len(self.initialization_errors)}")
            report_lines.append(f"  操作错误: {len(self.operation_errors)}")

            # 显示最近的错误
            if self.initialization_errors:
                report_lines.append("\n❌ 最近的初始化错误:")
                for error in self.initialization_errors[-3:]:
                    time_str = error["timestamp"].strftime("%H:%M:%S")
                    report_lines.append(f"  [{time_str}] {error['error']}")

            if self.operation_errors:
                report_lines.append("\n⚠️ 最近的操作错误:")
                for error in self.operation_errors[-3:]:
                    time_str = error["timestamp"].strftime("%H:%M:%S")
                    report_lines.append(f"  [{time_str}] {error['operation']}: {error['error']}")
        else:
            report_lines.append("\n✅ 无错误记录")

        # 功能可用性
        report_lines.append("\n🎯 功能可用性:")
        if self.chinastock_engine:
            report_lines.append("  ✅ 品种列表刷新")
            report_lines.append("  ✅ 品种列表重新加载")
            report_lines.append("  ✅ 品种符号获取")
        else:
            report_lines.append("  ❌ 品种列表功能不可用")

        return "\n".join(report_lines)

    def get_error_history(self) -> Dict[str, List[Dict]]:
        """获取错误历史"""
        return {
            "initialization_errors": self.initialization_errors,
            "operation_errors": self.operation_errors,
        }

    def clear_error_history(self):
        """清空错误历史"""
        self.initialization_errors.clear()
        self.operation_errors.clear()
        self.service_manager._record_error(
            "VnPyServiceAdapter",
            "ERROR_HISTORY_CLEARED",
            "VnPy适配器错误历史已清空",
            severity=ErrorSeverity.INFO,
        )


def create_vnpy_service_adapter(service_manager: ServiceManager) -> VnPyServiceAdapter:
    """创建VnPy服务适配器"""
    return VnPyServiceAdapter(service_manager)
