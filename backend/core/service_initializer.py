# -*- coding: utf-8 -*-
# pylint: disable=protected-access
# 注: ServiceInitializer 作为 ServiceManager 的紧密协作类,
# 需要访问 _record_error 方法来记录详细的服务初始化过程
"""
服务初始化器 - 错误追踪和详细报告版本

专注于详细错误报告机制，让用户知道服务初始化的具体问题。
不实现多层级降级机制，而是提供完整的错误信息追踪。
"""

import logging
import threading
from typing import Any, Dict

from .shared_services import ErrorSeverity, ServiceManager
from .vnpy_service_adapter import VnPyServiceAdapter

logger = logging.getLogger(__name__)


class ServiceInitializer:
    """服务初始化器 - 专注于错误追踪和报告"""

    def __init__(self, service_manager: ServiceManager):
        """初始化服务初始化器"""
        self.service_manager = service_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        self._initialization_lock = threading.Lock()

        # VnPy服务适配器
        self.vnpy_adapter = None

    def initialize_all_services(self) -> bool:
        """初始化所有服务，返回成功状态"""
        try:
            with self._initialization_lock:
                self.service_manager._record_error(
                    "ServiceInitializer",
                    "INITIALIZATION_START",
                    "开始初始化所有后端服务",
                    severity=ErrorSeverity.INFO,
                )

                success = True

                # 初始化VnPy服务适配器
                if not self._initialize_vnpy_adapter():
                    success = False

                # 初始化品种服务
                if not self._initialize_symbol_service():
                    success = False

                # 初始化其他核心服务
                if not self._initialize_other_services():
                    success = False

                if success:
                    self.service_manager._record_error(
                        "ServiceInitializer",
                        "INITIALIZATION_SUCCESS",
                        "所有后端服务初始化成功",
                        severity=ErrorSeverity.INFO,
                    )
                else:
                    self.service_manager._record_error(
                        "ServiceInitializer",
                        "INITIALIZATION_PARTIAL_SUCCESS",
                        "部分后端服务初始化成功，部分失败",
                        severity=ErrorSeverity.WARNING,
                    )

                return success

        except Exception as e:
            self.service_manager._record_error(
                "ServiceInitializer",
                "INITIALIZATION_EXCEPTION",
                f"服务初始化过程中发生异常: {str(e)}",
                exception=e,
                severity=ErrorSeverity.CRITICAL,
            )
            return False

    def _initialize_vnpy_adapter(self) -> bool:
        """初始化VnPy服务适配器"""
        try:
            self.service_manager._record_error(
                "ServiceInitializer",
                "VNPY_ADAPTER_INIT_START",
                "开始初始化VnPy服务适配器",
                severity=ErrorSeverity.INFO,
            )

            # 创建VnPy服务适配器
            self.vnpy_adapter = VnPyServiceAdapter(self.service_manager)

            # 注册到服务管理器
            success = self.service_manager.register_service("vnpy_service", self.vnpy_adapter)

            if success:
                self.service_manager._record_error(
                    "ServiceInitializer",
                    "VNPY_ADAPTER_INIT_SUCCESS",
                    "VnPy服务适配器初始化成功",
                    severity=ErrorSeverity.INFO,
                )
                return True
            else:
                self.service_manager._record_error(
                    "ServiceInitializer",
                    "VNPY_ADAPTER_REGISTRATION_FAILED",
                    "VnPy服务适配器注册失败",
                    severity=ErrorSeverity.ERROR,
                )
                return False

        except Exception as e:
            self.service_manager._record_error(
                "ServiceInitializer",
                "VNPY_ADAPTER_INIT_EXCEPTION",
                f"VnPy服务适配器初始化异常: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return False

    def _initialize_symbol_service(self) -> bool:
        """初始化品种服务"""
        try:
            self.service_manager._record_error(
                "ServiceInitializer",
                "SYMBOL_SERVICE_INIT_START",
                "开始初始化品种服务",
                severity=ErrorSeverity.INFO,
            )

            # 检查VnPy服务是否可用
            vnpy_service = self.service_manager.get_service("vnpy_service")
            if vnpy_service is None:
                self.service_manager._record_error(
                    "ServiceInitializer",
                    "SYMBOL_SERVICE_VNPY_DEPENDENCY_MISSING",
                    "无法初始化品种服务：VnPy服务不可用",
                    severity=ErrorSeverity.ERROR,
                )
                return False

            # 创建品种服务（简化版本，直接使用VnPy适配器）
            symbol_service = SymbolServiceWrapper(vnpy_service)

            # 注册服务
            success = self.service_manager.register_service("symbol_service", symbol_service)

            if success:
                self.service_manager._record_error(
                    "ServiceInitializer",
                    "SYMBOL_SERVICE_INIT_SUCCESS",
                    "品种服务初始化成功",
                    severity=ErrorSeverity.INFO,
                )
                return True
            else:
                return False

        except Exception as e:
            self.service_manager._record_error(
                "ServiceInitializer",
                "SYMBOL_SERVICE_INIT_EXCEPTION",
                f"品种服务初始化异常: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return False

    def _initialize_other_services(self) -> bool:
        """初始化其他核心服务"""
        try:
            self.service_manager._record_error(
                "ServiceInitializer",
                "OTHER_SERVICES_INIT_START",
                "开始初始化其他核心服务",
                severity=ErrorSeverity.INFO,
            )

            success_count = 0
            total_services = 0

            # 初始化事件服务
            total_services += 1
            if self._initialize_event_service():
                success_count += 1

            # 初始化本地数据服务
            total_services += 1
            if self._initialize_local_data_service():
                success_count += 1

            # 初始化下载服务
            total_services += 1
            if self._initialize_download_service():
                success_count += 1

            # 初始化数据源服务
            total_services += 1
            if self._initialize_data_source_service():
                success_count += 1

            if success_count == total_services:
                self.service_manager._record_error(
                    "ServiceInitializer",
                    "OTHER_SERVICES_INIT_SUCCESS",
                    f"所有{total_services}个其他服务初始化成功",
                    severity=ErrorSeverity.INFO,
                )
                return True
            else:
                self.service_manager._record_error(
                    "ServiceInitializer",
                    "OTHER_SERVICES_INIT_PARTIAL",
                    f"其他服务初始化部分成功：{success_count}/{total_services}",
                    severity=ErrorSeverity.WARNING,
                )
                return False

        except Exception as e:
            self.service_manager._record_error(
                "ServiceInitializer",
                "OTHER_SERVICES_INIT_EXCEPTION",
                f"其他服务初始化异常: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return False

    def _initialize_event_service(self) -> bool:
        """初始化事件服务"""
        try:
            # 创建简单的事件服务
            event_service = SimpleEventService()
            return self.service_manager.register_service("event_service", event_service)
        except Exception as e:
            self.service_manager._record_error(
                "ServiceInitializer",
                "EVENT_SERVICE_INIT_FAILED",
                f"事件服务初始化失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return False

    def _initialize_local_data_service(self) -> bool:
        """初始化本地数据服务"""
        try:
            # 创建简单的本地数据服务
            local_data_service = SimpleLocalDataService()
            return self.service_manager.register_service("local_data_service", local_data_service)
        except Exception as e:
            self.service_manager._record_error(
                "ServiceInitializer",
                "LOCAL_DATA_SERVICE_INIT_FAILED",
                f"本地数据服务初始化失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return False

    def _initialize_download_service(self) -> bool:
        """初始化下载服务"""
        try:
            # 创建简单的下载服务
            download_service = SimpleDownloadService()
            return self.service_manager.register_service("download_service", download_service)
        except Exception as e:
            self.service_manager._record_error(
                "ServiceInitializer",
                "DOWNLOAD_SERVICE_INIT_FAILED",
                f"下载服务初始化失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return False

    def _initialize_data_source_service(self) -> bool:
        """初始化数据源服务"""
        try:
            # 导入并创建数据源服务
            from backend.services.data_center.data_source_service import DataSourceService

            data_source_service = DataSourceService()
            return self.service_manager.register_service("data_source_service", data_source_service)
        except Exception as e:
            self.service_manager._record_error(
                "ServiceInitializer",
                "DATA_SOURCE_SERVICE_INIT_FAILED",
                f"数据源服务初始化失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return False

    def get_initialization_report(self) -> Dict[str, Any]:
        """获取初始化报告"""
        report = {
            "vnpy_adapter_available": self.vnpy_adapter is not None,
            "vnpy_adapter_status": None,
            "services_registered": len(self.service_manager.services),
            "error_count": len(self.service_manager.errors),
        }

        if self.vnpy_adapter:
            report["vnpy_adapter_status"] = self.vnpy_adapter.get_status()

        return report


class SymbolServiceWrapper:
    """品种服务包装器"""

    def __init__(self, vnpy_adapter):
        """初始化品种服务包装器

        Args:
            vnpy_adapter: VnPy服务适配器实例
        """
        self.vnpy_adapter = vnpy_adapter
        self.logger = logging.getLogger("SymbolServiceWrapper")

    async def get_all_symbols(self):
        """获取所有品种"""
        return self.vnpy_adapter.get_symbols()

    async def refresh_cache(self):
        """刷新缓存"""
        return self.vnpy_adapter.refresh_stock_list()


class SimpleEventService:
    """简单事件服务"""

    def __init__(self):
        """初始化简单事件服务"""
        self.handlers = {}
        self.logger = logging.getLogger("SimpleEventService")

    async def emit_event(self, event_type, data=None):
        """发送事件"""
        if event_type in self.handlers:
            for handler in self.handlers[event_type]:
                try:
                    handler(data)
                except Exception as e:
                    self.logger.error("事件处理器执行失败: %s", e)

    def register_handler(self, event_type, handler):
        """注册事件处理器"""
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)


class SimpleLocalDataService:
    """简单本地数据服务"""

    def __init__(self):
        """初始化简单本地数据服务"""
        self.logger = logging.getLogger("SimpleLocalDataService")

    async def query_data(self):
        """查询数据"""
        return []

    def get_status(self):
        """获取状态"""
        return "运行中"


class SimpleDownloadService:
    """简单下载服务"""

    def __init__(self):
        """初始化简单下载服务"""
        self.logger = logging.getLogger("SimpleDownloadService")
        self.tasks = []

    async def create_download_task(self):
        """创建下载任务"""
        task = {"task_id": f"task_{len(self.tasks)}", "status": "pending"}
        self.tasks.append(task)
        return task

    async def get_download_tasks(self):
        """获取下载任务"""
        return self.tasks
