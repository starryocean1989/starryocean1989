# -*- coding: utf-8 -*-
"""
依赖注入模块.

提供FastAPI依赖注入功能，包括服务获取、数据库连接等。
"""

import logging
from typing import Optional

from fastapi import HTTPException, status

from backend.services.data_center import (
    DataSourceService,
    DownloadService,
    LocalDataService,
    SymbolService,
)
from backend.services.event_service import EventService
from backend.services.market_board import (
    ChartService,
    DataFusionService,
    GapDetectionService,
    IndicatorService,
    RealtimeService,
)
from backend.services.vnpy_service import VnpyService

# 新模块服务将在后续实现
# from backend.services.strategy_center import ...
# from backend.services.trading_gateway import ...
# from backend.services.portfolio import ...
# from backend.services.system_manager import ...

logger = logging.getLogger(__name__)


class DependencyContainer:
    """依赖注入容器."""

    def __init__(self):
        """初始化依赖容器."""
        self._vnpy_service: Optional[VnpyService] = None
        self._event_service: Optional[EventService] = None
        self._symbol_service: Optional[SymbolService] = None
        self._download_service: Optional[DownloadService] = None
        self._local_data_service: Optional[LocalDataService] = None
        self._data_source_service: Optional[DataSourceService] = None
        self._chart_service: Optional[ChartService] = None
        self._indicator_service: Optional[IndicatorService] = None
        self._realtime_service: Optional[RealtimeService] = None
        self._data_fusion_service: Optional[DataFusionService] = None
        self._gap_detection_service: Optional[GapDetectionService] = None
        self._initialized = False

    async def initialize(self):
        """初始化所有服务."""
        if self._initialized:
            return

        try:
            # 初始化VnPy服务
            self._vnpy_service = VnpyService()
            await self._vnpy_service.initialize()

            # 初始化事件服务
            self._event_service = EventService(self._vnpy_service)

            # 初始化数据中心服务
            self._symbol_service = SymbolService(self._vnpy_service)
            self._download_service = DownloadService(
                self._vnpy_service, self._event_service
            )
            self._local_data_service = LocalDataService(
                self._vnpy_service, self._event_service
            )
            self._data_source_service = DataSourceService(
                self._vnpy_service, self._event_service
            )

            # 初始化数据中心服务
            await self._symbol_service.initialize()
            await self._download_service.initialize()
            await self._local_data_service.initialize()
            await self._data_source_service.initialize()

            # 初始化行情看板服务
            self._chart_service = ChartService(self._vnpy_service, self._event_service)
            self._indicator_service = IndicatorService(
                self._vnpy_service, self._event_service
            )
            self._realtime_service = RealtimeService(
                self._vnpy_service, self._event_service
            )
            self._data_fusion_service = DataFusionService(
                self._vnpy_service, self._event_service
            )
            self._gap_detection_service = GapDetectionService(
                self._vnpy_service, self._event_service
            )

            await self._chart_service.initialize()
            await self._indicator_service.initialize()
            await self._realtime_service.initialize()
            await self._data_fusion_service.initialize()
            await self._gap_detection_service.initialize()

            self._initialized = True
            logger.info("依赖注入容器初始化完成")

        except Exception as e:
            logger.error("依赖注入容器初始化失败: %s", e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="服务初始化失败",
            ) from e

    def get_vnpy_service(self) -> VnpyService:
        """获取VnPy服务实例."""
        if not self._initialized:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="服务未初始化"
            )
        if self._vnpy_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="VnPy服务不可用"
            )
        return self._vnpy_service

    def get_event_service(self) -> EventService:
        """获取事件服务实例."""
        if not self._initialized:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="服务未初始化"
            )
        if self._event_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="事件服务不可用"
            )
        return self._event_service

    def get_symbol_service(self) -> SymbolService:
        """获取品种服务实例."""
        if not self._initialized:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="服务未初始化"
            )
        if self._symbol_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="品种服务不可用"
            )
        return self._symbol_service

    def get_download_service(self) -> DownloadService:
        """获取下载服务实例."""
        if not self._initialized:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="服务未初始化"
            )
        if self._download_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="下载服务不可用"
            )
        return self._download_service

    def get_local_data_service(self) -> LocalDataService:
        """获取本地数据服务实例."""
        if not self._initialized:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="服务未初始化"
            )
        if self._local_data_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="本地数据服务不可用",
            )
        return self._local_data_service

    def get_data_source_service(self) -> DataSourceService:
        """获取数据源服务实例."""
        if not self._initialized:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="服务未初始化"
            )
        if self._data_source_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="数据源服务不可用",
            )
        return self._data_source_service

    def get_chart_service(self) -> ChartService:
        """获取图表服务实例."""
        if not self._initialized:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="服务未初始化"
            )
        if self._chart_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="图表服务不可用",
            )
        return self._chart_service

    def get_indicator_service(self) -> IndicatorService:
        """获取指标服务实例."""
        if not self._initialized:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="服务未初始化"
            )
        if self._indicator_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="指标服务不可用",
            )
        return self._indicator_service

    def get_realtime_service(self) -> RealtimeService:
        """获取实时服务实例."""
        if not self._initialized:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="服务未初始化"
            )
        if self._realtime_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="实时服务不可用",
            )
        return self._realtime_service

    def get_data_fusion_service(self) -> DataFusionService:
        """获取数据融合服务实例."""
        if not self._initialized:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="服务未初始化"
            )
        if self._data_fusion_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="数据融合服务不可用",
            )
        return self._data_fusion_service

    def get_gap_detection_service(self) -> GapDetectionService:
        """获取断点检测服务实例."""
        if not self._initialized:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="服务未初始化"
            )
        if self._gap_detection_service is None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="断点检测服务不可用",
            )
        return self._gap_detection_service

    async def shutdown(self):
        """关闭所有服务."""
        # 关闭行情看板服务
        if self._gap_detection_service:
            await self._gap_detection_service.shutdown()
        if self._data_fusion_service:
            await self._data_fusion_service.shutdown()
        if self._realtime_service:
            await self._realtime_service.shutdown()
        if self._indicator_service:
            await self._indicator_service.shutdown()
        if self._chart_service:
            await self._chart_service.shutdown()
        # 关闭数据中心服务
        if self._symbol_service:
            await self._symbol_service.shutdown()
        if self._download_service:
            await self._download_service.shutdown()
        if self._local_data_service:
            await self._local_data_service.shutdown()
        if self._data_source_service:
            await self._data_source_service.shutdown()
        # 关闭基础服务
        if self._event_service:
            await self._event_service.shutdown()
        if self._vnpy_service:
            await self._vnpy_service.shutdown()
        self._initialized = False
        logger.info("依赖注入容器已关闭")


# 全局依赖容器实例
_dependency_container = DependencyContainer()


def get_vnpy_service() -> VnpyService:
    """获取VnPy服务的依赖注入函数."""
    return _dependency_container.get_vnpy_service()


def get_event_service() -> EventService:
    """获取事件服务的依赖注入函数."""
    return _dependency_container.get_event_service()


def get_symbol_service() -> SymbolService:
    """获取品种服务的依赖注入函数."""
    return _dependency_container.get_symbol_service()


def get_download_service() -> DownloadService:
    """获取下载服务的依赖注入函数."""
    return _dependency_container.get_download_service()


def get_local_data_service() -> LocalDataService:
    """获取本地数据服务的依赖注入函数."""
    return _dependency_container.get_local_data_service()


def get_data_source_service() -> DataSourceService:
    """获取数据源服务的依赖注入函数."""
    return _dependency_container.get_data_source_service()


def get_chart_service() -> ChartService:
    """获取图表服务的依赖注入函数."""
    return _dependency_container.get_chart_service()


def get_indicator_service() -> IndicatorService:
    """获取指标服务的依赖注入函数."""
    return _dependency_container.get_indicator_service()


def get_realtime_service() -> RealtimeService:
    """获取实时服务的依赖注入函数."""
    return _dependency_container.get_realtime_service()


def get_data_fusion_service() -> DataFusionService:
    """获取数据融合服务的依赖注入函数."""
    return _dependency_container.get_data_fusion_service()


def get_gap_detection_service() -> GapDetectionService:
    """获取断点检测服务的依赖注入函数."""
    return _dependency_container.get_gap_detection_service()


async def initialize_dependencies():
    """初始化依赖注入容器."""
    await _dependency_container.initialize()


async def shutdown_dependencies():
    """关闭依赖注入容器."""
    await _dependency_container.shutdown()


# 导出公共接口
__all__ = [
    "DependencyContainer",
    "get_vnpy_service",
    "get_event_service",
    "get_symbol_service",
    "get_download_service",
    "get_local_data_service",
    "get_data_source_service",
    "get_chart_service",
    "get_indicator_service",
    "get_realtime_service",
    "get_data_fusion_service",
    "get_gap_detection_service",
    "initialize_dependencies",
    "shutdown_dependencies",
]
