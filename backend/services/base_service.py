# -*- coding: utf-8 -*-
"""
基础服务类.

提供所有服务的通用功能和接口定义。
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class BaseService(ABC):
    """服务基类."""

    def __init__(self, service_name: str):
        """初始化基础服务."""
        self.service_name = service_name
        self.logger = logging.getLogger(f"{__name__}.{service_name}")
        self.is_initialized = False
        self.start_time: Optional[datetime] = None

    @abstractmethod
    async def initialize(self) -> None:
        """初始化服务."""
        pass

    @abstractmethod
    async def shutdown(self) -> None:
        """关闭服务."""
        pass

    @abstractmethod
    async def health_check(self) -> Dict[str, Any]:
        """健康检查."""
        pass

    def get_service_info(self) -> Dict[str, Any]:
        """获取服务信息."""
        return {
            "service_name": self.service_name,
            "is_initialized": self.is_initialized,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "uptime": self._get_uptime(),
        }

    def _get_uptime(self) -> Optional[float]:
        """获取运行时间."""
        if self.start_time:
            return (datetime.now() - self.start_time).total_seconds()
        return None

    def _log_operation(self, operation: str, **kwargs) -> None:
        """记录操作日志."""
        self.logger.info(
            "服务操作: %s - %s",
            operation,
            ", ".join(f"{k}={v}" for k, v in kwargs.items()),
        )

    def _log_error(self, operation: str, error: Exception, **kwargs) -> None:
        """记录错误日志."""
        self.logger.error(
            "服务错误: %s - %s - %s",
            operation,
            str(error),
            ", ".join(f"{k}={v}" for k, v in kwargs.items()),
        )


class ServiceManager:
    """服务管理器."""

    def __init__(self):
        """初始化服务管理器."""
        self.logger = logging.getLogger(__name__)
        self._services: Dict[str, BaseService] = {}
        self._initialized = False

    def register_service(self, service: BaseService) -> None:
        """注册服务."""
        service_name = service.service_name
        if service_name in self._services:
            self.logger.warning("服务已存在，将被覆盖: %s", service_name)

        self._services[service_name] = service
        self.logger.info("服务已注册: %s", service_name)

    async def initialize_all(self) -> None:
        """初始化所有服务."""
        if self._initialized:
            self.logger.warning("服务管理器已初始化")
            return

        self.logger.info("开始初始化所有服务...")

        for service_name, service in self._services.items():
            try:
                self.logger.info("初始化服务: %s", service_name)
                await service.initialize()
                service.start_time = datetime.now()
                service.is_initialized = True
                self.logger.info("服务初始化完成: %s", service_name)
            except Exception as e:
                self.logger.error("服务初始化失败: %s - %s", service_name, e)
                raise

        self._initialized = True
        self.logger.info("所有服务初始化完成")

    async def shutdown_all(self) -> None:
        """关闭所有服务."""
        if not self._initialized:
            self.logger.warning("服务管理器未初始化")
            return

        self.logger.info("开始关闭所有服务...")

        # 逆序关闭服务
        for service_name, service in reversed(list(self._services.items())):
            try:
                self.logger.info("关闭服务: %s", service_name)
                await service.shutdown()
                service.is_initialized = False
                self.logger.info("服务关闭完成: %s", service_name)
            except Exception as e:
                self.logger.error("服务关闭失败: %s - %s", service_name, e)

        self._initialized = False
        self.logger.info("所有服务关闭完成")

    async def health_check_all(self) -> Dict[str, Any]:
        """检查所有服务健康状态."""
        results = {
            "overall_status": "healthy",
            "services": {},
            "total_services": len(self._services),
            "healthy_services": 0,
            "unhealthy_services": 0,
        }

        for service_name, service in self._services.items():
            try:
                health_info = await service.health_check()
                results["services"][service_name] = {
                    "status": "healthy",
                    "info": health_info,
                }
                results["healthy_services"] += 1
            except Exception as e:
                results["services"][service_name] = {
                    "status": "unhealthy",
                    "error": str(e),
                }
                results["unhealthy_services"] += 1
                results["overall_status"] = "unhealthy"

        return results

    def get_service(self, service_name: str) -> Optional[BaseService]:
        """获取服务实例."""
        return self._services.get(service_name)

    def get_all_services(self) -> Dict[str, BaseService]:
        """获取所有服务."""
        return self._services.copy()

    def get_service_info(self) -> Dict[str, Any]:
        """获取服务管理器信息."""
        return {
            "total_services": len(self._services),
            "initialized": self._initialized,
            "services": {
                name: service.get_service_info()
                for name, service in self._services.items()
            },
        }


# 导出公共接口
__all__ = ["BaseService", "ServiceManager"]
