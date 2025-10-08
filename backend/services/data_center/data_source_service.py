# -*- coding: utf-8 -*-
"""
数据源服务 - 错误追踪和详细报告版本

专注于详细错误报告机制，让用户知道数据源服务的具体问题。
不实现多层级降级机制，而是提供完整的错误信息追踪。
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

from backend.core.shared_services import ErrorSeverity, get_service_manager

logger = logging.getLogger(__name__)


class DataSource:
    """数据源"""

    def __init__(self, source_id: str, name: str, source_type: str, config: Dict[str, Any]):
        """
        初始化数据源

        Args:
            source_id: 数据源ID
            name: 数据源名称
            source_type: 数据源类型
            config: 配置参数
        """
        self.source_id = source_id
        self.name = name
        self.source_type = source_type
        self.config = config
        self.status = "disconnected"
        self.last_update: Optional[datetime] = None
        self.error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "source_id": self.source_id,
            "name": self.name,
            "source_type": self.source_type,
            "config": self.config,
            "status": self.status,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "error_message": self.error_message,
        }


class DataSourceService:
    """数据源服务 - 专注于错误追踪和详细报告"""

    def __init__(self):
        """初始化数据源服务"""
        self.service_manager = get_service_manager()
        self.logger = logging.getLogger(self.__class__.__name__)

        self._data_sources: Dict[str, DataSource] = {}
        self._initialization_successful = False

        # 尝试初始化
        self._attempt_initialization()

    def _attempt_initialization(self):
        """尝试初始化数据源服务"""
        try:
            self.service_manager.record_error(
                "DataSourceService",
                "INITIALIZATION_START",
                "开始初始化数据源服务",
                severity=ErrorSeverity.INFO,
            )

            # 初始化一些默认数据源
            self._initialize_default_sources()

            self._initialization_successful = True
            self.service_manager.record_error(
                "DataSourceService",
                "INITIALIZATION_SUCCESS",
                f"数据源服务初始化成功，配置{len(self._data_sources)}个数据源",
                severity=ErrorSeverity.INFO,
            )

        except Exception as e:
            error_msg = f"数据源服务初始化失败: {str(e)}"
            self.service_manager.record_error(
                "DataSourceService",
                "INITIALIZATION_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.CRITICAL,
            )

    def _initialize_default_sources(self):
        """初始化默认数据源"""
        try:
            # 添加一些示例数据源
            default_sources = [
                {
                    "source_id": "vnpy_source",
                    "name": "VnPy数据源",
                    "source_type": "vnpy",
                    "config": {"description": "通过VnPy获取市场数据", "enabled": True},
                },
                {
                    "source_id": "local_cache",
                    "name": "本地缓存",
                    "source_type": "local",
                    "config": {"description": "本地数据缓存", "enabled": True},
                },
                {
                    "source_id": "external_api",
                    "name": "外部API",
                    "source_type": "api",
                    "config": {
                        "description": "外部数据API接口",
                        "enabled": False,
                        "url": "https://api.example.com",
                    },
                },
            ]

            for source_config in default_sources:
                data_source = DataSource(
                    source_id=source_config["source_id"],
                    name=source_config["name"],
                    source_type=source_config["source_type"],
                    config=source_config["config"],
                )
                self._data_sources[data_source.source_id] = data_source

            self.service_manager.record_error(
                "DataSourceService",
                "DEFAULT_SOURCES_INITIALIZED",
                f"默认数据源初始化完成: {len(default_sources)}个",
                severity=ErrorSeverity.INFO,
            )

        except Exception as e:
            self.service_manager.record_error(
                "DataSourceService",
                "DEFAULT_SOURCES_INIT_EXCEPTION",
                f"初始化默认数据源失败: {str(e)}",
                exception=e,
                severity=ErrorSeverity.ERROR,
            )

    async def get_all_data_sources(self) -> List[Dict[str, Any]]:
        """获取所有数据源"""
        try:
            self.service_manager.record_error(
                "DataSourceService",
                "GET_ALL_SOURCES_START",
                "开始获取所有数据源",
                severity=ErrorSeverity.INFO,
            )

            sources = [source.to_dict() for source in self._data_sources.values()]

            self.service_manager.record_error(
                "DataSourceService",
                "GET_ALL_SOURCES_SUCCESS",
                f"获取所有数据源成功，返回{len(sources)}个数据源",
                severity=ErrorSeverity.INFO,
            )

            return sources

        except Exception as e:
            error_msg = f"获取所有数据源失败: {str(e)}"
            self.service_manager.record_error(
                "DataSourceService",
                "GET_ALL_SOURCES_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return []

    async def get_data_source(self, source_id: str) -> Optional[Dict[str, Any]]:
        """获取指定数据源"""
        try:
            source = self._data_sources.get(source_id)

            if source:
                self.service_manager.record_error(
                    "DataSourceService",
                    "GET_SOURCE_SUCCESS",
                    f"获取数据源成功: {source_id}",
                    severity=ErrorSeverity.INFO,
                )
                return source.to_dict()
            else:
                self.service_manager.record_error(
                    "DataSourceService",
                    "SOURCE_NOT_FOUND",
                    f"数据源不存在: {source_id}",
                    severity=ErrorSeverity.WARNING,
                )
                return None

        except Exception as e:
            error_msg = f"获取数据源失败: {str(e)}"
            self.service_manager.record_error(
                "DataSourceService",
                "GET_SOURCE_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return None

    async def test_connection(self, source_id: str) -> bool:
        """测试数据源连接"""
        try:
            self.service_manager.record_error(
                "DataSourceService",
                "TEST_CONNECTION_START",
                f"开始测试数据源连接: {source_id}",
                severity=ErrorSeverity.INFO,
            )

            source = self._data_sources.get(source_id)
            if not source:
                self.service_manager.record_error(
                    "DataSourceService",
                    "TEST_CONNECTION_SOURCE_NOT_FOUND",
                    f"测试连接失败，数据源不存在: {source_id}",
                    severity=ErrorSeverity.ERROR,
                )
                return False

            # 模拟连接测试
            if source.source_type == "vnpy":
                # 检查VnPy服务是否可用
                vnpy_service = self.service_manager.get_service("vnpy_service")
                if vnpy_service:
                    success = True
                    source.status = "connected"
                    source.last_update = datetime.now()
                    source.error_message = None
                else:
                    success = False
                    source.status = "error"
                    source.error_message = "VnPy服务不可用"
            elif source.source_type == "local":
                # 本地缓存总是可用
                success = True
                source.status = "connected"
                source.last_update = datetime.now()
                source.error_message = None
            else:
                # 其他类型模拟失败
                success = False
                source.status = "error"
                source.error_message = "连接测试失败"

            if success:
                self.service_manager.record_error(
                    "DataSourceService",
                    "TEST_CONNECTION_SUCCESS",
                    f"数据源连接测试成功: {source_id}",
                    severity=ErrorSeverity.INFO,
                )
            else:
                self.service_manager.record_error(
                    "DataSourceService",
                    "TEST_CONNECTION_FAILED",
                    f"数据源连接测试失败: {source_id}, 错误: {source.error_message}",
                    severity=ErrorSeverity.WARNING,
                )

            return success

        except Exception as e:
            error_msg = f"测试数据源连接异常: {str(e)}"
            self.service_manager.record_error(
                "DataSourceService",
                "TEST_CONNECTION_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return False

    async def add_data_source(
        self, source_id: str, name: str, source_type: str, config: Dict[str, Any]
    ) -> bool:
        """添加数据源"""
        try:
            if source_id in self._data_sources:
                self.service_manager.record_error(
                    "DataSourceService",
                    "ADD_SOURCE_DUPLICATE",
                    f"数据源已存在: {source_id}",
                    severity=ErrorSeverity.WARNING,
                )
                return False

            data_source = DataSource(source_id, name, source_type, config)
            self._data_sources[source_id] = data_source

            self.service_manager.record_error(
                "DataSourceService",
                "ADD_SOURCE_SUCCESS",
                f"添加数据源成功: {source_id}",
                severity=ErrorSeverity.INFO,
            )
            return True

        except Exception as e:
            error_msg = f"添加数据源失败: {str(e)}"
            self.service_manager.record_error(
                "DataSourceService",
                "ADD_SOURCE_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return False

    async def remove_data_source(self, source_id: str) -> bool:
        """移除数据源"""
        try:
            if source_id not in self._data_sources:
                self.service_manager.record_error(
                    "DataSourceService",
                    "REMOVE_SOURCE_NOT_FOUND",
                    f"要移除的数据源不存在: {source_id}",
                    severity=ErrorSeverity.WARNING,
                )
                return False

            del self._data_sources[source_id]

            self.service_manager.record_error(
                "DataSourceService",
                "REMOVE_SOURCE_SUCCESS",
                f"移除数据源成功: {source_id}",
                severity=ErrorSeverity.INFO,
            )
            return True

        except Exception as e:
            error_msg = f"移除数据源失败: {str(e)}"
            self.service_manager.record_error(
                "DataSourceService",
                "REMOVE_SOURCE_EXCEPTION",
                error_msg,
                exception=e,
                severity=ErrorSeverity.ERROR,
            )
            return False

    def get_service_status(self) -> Dict[str, Any]:
        """获取服务状态"""
        status_counts = {}
        for source in self._data_sources.values():
            status = source.status
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "initialization_successful": self._initialization_successful,
            "total_sources": len(self._data_sources),
            "status_counts": status_counts,
        }

    def get_detailed_status_report(self) -> str:
        """获取详细状态报告"""
        report_lines = []
        report_lines.append("🔍 数据源服务状态报告")
        report_lines.append("=" * 50)

        # 基本状态
        status_icon = "✅" if self._initialization_successful else "❌"
        report_lines.append(
            f"📊 初始化状态: {status_icon} {'成功' if self._initialization_successful else '失败'}"
        )

        # 数据源统计
        report_lines.append(f"📋 总数据源数: {len(self._data_sources)}")

        if self._data_sources:
            status_counts = {}
            for source in self._data_sources.values():
                status = source.status
                status_counts[status] = status_counts.get(status, 0) + 1

            report_lines.append("📊 数据源状态统计:")
            for status, count in status_counts.items():
                status_icons = {"connected": "✅", "disconnected": "⚠️", "error": "❌"}
                icon = status_icons.get(status, "❓")
                report_lines.append(f"  {icon} {status}: {count}")

            report_lines.append("\n📋 数据源详情:")
            for source in self._data_sources.values():
                status_icon = {"connected": "✅", "disconnected": "⚠️", "error": "❌"}.get(
                    source.status, "❓"
                )
                report_lines.append(f"  {status_icon} {source.name} ({source.source_type})")
                if source.error_message:
                    report_lines.append(f"    错误: {source.error_message}")
        else:
            report_lines.append("📋 暂无数据源")

        return "\n".join(report_lines)


# 导出公共接口
__all__ = ["DataSourceService", "DataSource"]
