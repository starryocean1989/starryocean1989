# -*- coding: utf-8 -*-
"""
数据源服务.

提供数据源配置和管理相关的业务逻辑。
"""

import logging
import asyncio
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from datetime import datetime

from backend.services.base_service import BaseService
from backend.core.models import DataSourceConfig

if TYPE_CHECKING:
    from backend.services.vnpy_service import VnpyService
    from backend.services.event_service import EventService

logger = logging.getLogger(__name__)


class DataSourceService(BaseService):
    """数据源服务."""

    def __init__(self, vnpy_service: "VnpyService", event_service: "EventService"):
        """初始化数据源服务."""
        super().__init__("DataSourceService")
        self.vnpy_service = vnpy_service
        self.event_service = event_service
        self._data_sources: Dict[str, DataSourceConfig] = {}
        self._connection_tests: Dict[str, Dict[str, Any]] = {}

    async def initialize(self) -> None:
        """初始化数据源服务."""
        try:
            self.logger.info("正在初始化数据源服务...")

            # 加载默认数据源配置
            await self._load_default_data_sources()

            # 注册事件处理器
            self.event_service.register_handler(
                "data_source_created", self._handle_data_source_created
            )
            self.event_service.register_handler(
                "data_source_updated", self._handle_data_source_updated
            )
            self.event_service.register_handler(
                "data_source_deleted", self._handle_data_source_deleted
            )
            self.event_service.register_handler(
                "data_source_test", self._handle_data_source_test
            )

            self.logger.info("数据源服务初始化完成")
            self.is_initialized = True

        except Exception as e:
            self.logger.error("数据源服务初始化失败: %s", e)
            raise

    async def shutdown(self) -> None:
        """关闭数据源服务."""
        try:
            self.logger.info("正在关闭数据源服务...")

            # 取消注册事件处理器
            self.event_service.unregister_handler(
                "data_source_created", self._handle_data_source_created
            )
            self.event_service.unregister_handler(
                "data_source_updated", self._handle_data_source_updated
            )
            self.event_service.unregister_handler(
                "data_source_deleted", self._handle_data_source_deleted
            )
            self.event_service.unregister_handler(
                "data_source_test", self._handle_data_source_test
            )

            # 清理数据
            self._data_sources.clear()
            self._connection_tests.clear()

            self.logger.info("数据源服务关闭完成")
            self.is_initialized = False

        except Exception as e:
            self.logger.error("数据源服务关闭失败: %s", e)
            raise

    async def health_check(self) -> Dict[str, Any]:
        """检查数据源服务健康状态."""
        try:
            return {
                "service_name": self.service_name,
                "is_initialized": self.is_initialized,
                "total_sources": len(self._data_sources),
                "enabled_sources": len(
                    [s for s in self._data_sources.values() if s.is_enabled]
                ),
                "connected_sources": len(
                    [s for s in self._data_sources.values() if s.is_connected]
                ),
                "source_types": list(
                    set(s.source_type for s in self._data_sources.values())
                ),
                "vnpy_service_available": self.vnpy_service.is_initialized,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("数据源服务健康检查失败: %s", e)
            return {
                "service_name": self.service_name,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def _load_default_data_sources(self) -> None:
        """加载默认数据源配置."""
        try:
            # 创建默认数据源配置
            default_sources = [
                DataSourceConfig(
                    source_id="tushare_default",
                    source_type="tushare",
                    name="Tushare数据源",
                    is_enabled=True,
                    is_connected=False,
                    config={
                        "token": "",
                        "timeout": 30,
                        "retry_count": 3,
                    },
                    last_connected=None,
                    error_count=0,
                ),
                DataSourceConfig(
                    source_id="akshare_default",
                    source_type="akshare",
                    name="AKShare数据源",
                    is_enabled=True,
                    is_connected=False,
                    config={
                        "timeout": 30,
                        "retry_count": 3,
                    },
                    last_connected=None,
                    error_count=0,
                ),
                DataSourceConfig(
                    source_id="yfinance_default",
                    source_type="yfinance",
                    name="Yahoo Finance数据源",
                    is_enabled=True,
                    is_connected=False,
                    config={
                        "timeout": 30,
                        "retry_count": 3,
                    },
                    last_connected=None,
                    error_count=0,
                ),
            ]

            for source in default_sources:
                self._data_sources[source.source_id] = source

            self.logger.info(
                "默认数据源配置加载完成: %d 个数据源", len(default_sources)
            )

        except Exception as e:
            self.logger.error("加载默认数据源配置失败: %s", e)
            raise

    async def get_all_data_sources(self) -> List[DataSourceConfig]:
        """获取所有数据源配置."""
        try:
            sources = list(self._data_sources.values())
            self.logger.info("获取所有数据源配置: %d 个", len(sources))
            return sources

        except Exception as e:
            self.logger.error("获取所有数据源配置失败: %s", e)
            raise

    async def get_data_source_by_id(self, source_id: str) -> Optional[DataSourceConfig]:
        """根据ID获取数据源配置."""
        try:
            source = self._data_sources.get(source_id)
            if source:
                self.logger.info("获取数据源配置: %s", source_id)
            else:
                self.logger.warning("数据源不存在: %s", source_id)

            return source

        except Exception as e:
            self.logger.error("获取数据源配置失败: %s", e)
            raise

    async def create_data_source(
        self, source_config: DataSourceConfig
    ) -> DataSourceConfig:
        """创建数据源配置."""
        try:
            # 检查ID是否已存在
            if source_config.source_id in self._data_sources:
                raise ValueError(f"数据源ID已存在: {source_config.source_id}")

            # 保存配置
            self._data_sources[source_config.source_id] = source_config

            # 发送创建事件
            await self.event_service.emit_event(
                "data_source_created", source_config.dict()
            )

            self.logger.info("数据源配置创建成功: %s", source_config.source_id)
            return source_config

        except Exception as e:
            self.logger.error("创建数据源配置失败: %s", e)
            raise

    async def update_data_source(
        self, source_id: str, source_config: DataSourceConfig
    ) -> DataSourceConfig:
        """更新数据源配置."""
        try:
            # 检查数据源是否存在
            if source_id not in self._data_sources:
                raise ValueError(f"数据源不存在: {source_id}")

            # 保持原有ID
            source_config.source_id = source_id

            # 更新配置
            self._data_sources[source_id] = source_config

            # 发送更新事件
            await self.event_service.emit_event(
                "data_source_updated", source_config.dict()
            )

            self.logger.info("数据源配置更新成功: %s", source_id)
            return source_config

        except Exception as e:
            self.logger.error("更新数据源配置失败: %s", e)
            raise

    async def delete_data_source(self, source_id: str) -> bool:
        """删除数据源配置."""
        try:
            # 检查数据源是否存在
            if source_id not in self._data_sources:
                self.logger.warning("数据源不存在: %s", source_id)
                return False

            # 删除配置
            del self._data_sources[source_id]

            # 清理测试结果
            if source_id in self._connection_tests:
                del self._connection_tests[source_id]

            # 发送删除事件
            await self.event_service.emit_event(
                "data_source_deleted", {"source_id": source_id}
            )

            self.logger.info("数据源配置删除成功: %s", source_id)
            return True

        except Exception as e:
            self.logger.error("删除数据源配置失败: %s", e)
            raise

    async def test_data_source_connection(self, source_id: str) -> Dict[str, Any]:
        """测试数据源连接."""
        try:
            # 检查数据源是否存在
            source = self._data_sources.get(source_id)
            if not source:
                raise ValueError(f"数据源不存在: {source_id}")

            # 发送测试事件
            await self.event_service.emit_event(
                "data_source_test", {"source_id": source_id}
            )

            # 模拟连接测试
            test_result = await self._simulate_connection_test(source)

            # 保存测试结果
            self._connection_tests[source_id] = test_result

            # 更新数据源状态
            if test_result["connection_status"] == "success":
                source.is_connected = True
                source.last_connected = datetime.now()
                source.error_count = 0
            else:
                source.is_connected = False
                source.error_count += 1

            self.logger.info(
                "数据源连接测试完成: %s, 状态=%s",
                source_id,
                test_result["connection_status"],
            )
            return test_result

        except Exception as e:
            self.logger.error("测试数据源连接失败: %s", e)
            raise

    async def _simulate_connection_test(
        self, source: DataSourceConfig
    ) -> Dict[str, Any]:
        """模拟连接测试."""
        try:
            # 模拟测试延迟
            await asyncio.sleep(0.5)

            # 根据数据源类型模拟不同的测试结果
            if source.source_type == "tushare":
                # Tushare需要token
                if source.config.get("token"):
                    test_result = {
                        "source_id": source.source_id,
                        "connection_status": "success",
                        "response_time": 0.5,
                        "test_time": datetime.now().isoformat(),
                        "message": "连接测试成功",
                        "details": {
                            "api_version": "1.2.89",
                            "user_level": "basic",
                        },
                    }
                else:
                    test_result = {
                        "source_id": source.source_id,
                        "connection_status": "failed",
                        "response_time": 0.5,
                        "test_time": datetime.now().isoformat(),
                        "message": "缺少API Token",
                        "error": "Token is required for Tushare",
                    }
            else:
                # 其他数据源模拟成功
                test_result = {
                    "source_id": source.source_id,
                    "connection_status": "success",
                    "response_time": 0.3,
                    "test_time": datetime.now().isoformat(),
                    "message": "连接测试成功",
                    "details": {
                        "source_type": source.source_type,
                        "timeout": source.config.get("timeout", 30),
                    },
                }

            return test_result

        except Exception as e:
            return {
                "source_id": source.source_id,
                "connection_status": "error",
                "response_time": 0.0,
                "test_time": datetime.now().isoformat(),
                "message": "连接测试出错",
                "error": str(e),
            }

    async def enable_data_source(self, source_id: str) -> bool:
        """启用数据源."""
        try:
            source = self._data_sources.get(source_id)
            if not source:
                self.logger.warning("数据源不存在: %s", source_id)
                return False

            source.is_enabled = True
            self.logger.info("数据源已启用: %s", source_id)
            return True

        except Exception as e:
            self.logger.error("启用数据源失败: %s", e)
            raise

    async def disable_data_source(self, source_id: str) -> bool:
        """禁用数据源."""
        try:
            source = self._data_sources.get(source_id)
            if not source:
                self.logger.warning("数据源不存在: %s", source_id)
                return False

            source.is_enabled = False
            source.is_connected = False
            self.logger.info("数据源已禁用: %s", source_id)
            return True

        except Exception as e:
            self.logger.error("禁用数据源失败: %s", e)
            raise

    async def get_enabled_data_sources(self) -> List[DataSourceConfig]:
        """获取启用的数据源列表."""
        try:
            enabled_sources = [s for s in self._data_sources.values() if s.is_enabled]
            self.logger.info("获取启用的数据源: %d 个", len(enabled_sources))
            return enabled_sources

        except Exception as e:
            self.logger.error("获取启用的数据源失败: %s", e)
            raise

    async def get_connected_data_sources(self) -> List[DataSourceConfig]:
        """获取已连接的数据源列表."""
        try:
            connected_sources = [
                s for s in self._data_sources.values() if s.is_connected
            ]
            self.logger.info("获取已连接的数据源: %d 个", len(connected_sources))
            return connected_sources

        except Exception as e:
            self.logger.error("获取已连接的数据源失败: %s", e)
            raise

    def get_connection_test_result(self, source_id: str) -> Optional[Dict[str, Any]]:
        """获取连接测试结果."""
        try:
            result = self._connection_tests.get(source_id)
            if result:
                self.logger.info("获取连接测试结果: %s", source_id)
            else:
                self.logger.warning("连接测试结果不存在: %s", source_id)

            return result

        except Exception as e:
            self.logger.error("获取连接测试结果失败: %s", e)
            raise

    async def _handle_data_source_created(self, event: Dict[str, Any]) -> None:
        """处理数据源创建事件."""
        try:
            data = event.get("data", {})
            source_id = data.get("source_id")

            if source_id:
                self.logger.info("处理数据源创建事件: %s", source_id)

        except Exception as e:
            self.logger.error("处理数据源创建事件失败: %s", e)

    async def _handle_data_source_updated(self, event: Dict[str, Any]) -> None:
        """处理数据源更新事件."""
        try:
            data = event.get("data", {})
            source_id = data.get("source_id")

            if source_id:
                self.logger.info("处理数据源更新事件: %s", source_id)

        except Exception as e:
            self.logger.error("处理数据源更新事件失败: %s", e)

    async def _handle_data_source_deleted(self, event: Dict[str, Any]) -> None:
        """处理数据源删除事件."""
        try:
            data = event.get("data", {})
            source_id = data.get("source_id")

            if source_id:
                self.logger.info("处理数据源删除事件: %s", source_id)

        except Exception as e:
            self.logger.error("处理数据源删除事件失败: %s", e)

    async def _handle_data_source_test(self, event: Dict[str, Any]) -> None:
        """处理数据源测试事件."""
        try:
            data = event.get("data", {})
            source_id = data.get("source_id")

            if source_id:
                # 执行连接测试
                await self.test_data_source_connection(source_id)
                self.logger.info("处理数据源测试事件: %s", source_id)

        except Exception as e:
            self.logger.error("处理数据源测试事件失败: %s", e)

    def get_data_source_statistics(self) -> Dict[str, Any]:
        """获取数据源统计信息."""
        try:
            stats = {
                "total_sources": len(self._data_sources),
                "enabled_sources": len(
                    [s for s in self._data_sources.values() if s.is_enabled]
                ),
                "connected_sources": len(
                    [s for s in self._data_sources.values() if s.is_connected]
                ),
                "source_types": {},
                "connection_tests": len(self._connection_tests),
                "timestamp": datetime.now().isoformat(),
            }

            # 统计各类型数据源数量
            for source in self._data_sources.values():
                source_type = source.source_type
                if source_type not in stats["source_types"]:
                    stats["source_types"][source_type] = 0
                stats["source_types"][source_type] += 1

            return stats

        except Exception as e:
            self.logger.error("获取数据源统计信息失败: %s", e)
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }


# 导出公共接口
__all__ = ["DataSourceService"]
