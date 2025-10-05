# -*- coding: utf-8 -*-
"""
VnPy服务注册表
管理所有VnPy服务的注册和发现
"""

import logging
from typing import Dict, Any, Optional
from abc import ABC, abstractmethod

from .core_adapter import vnpy_adapter

logger = logging.getLogger(__name__)


class VnPyService(ABC):
    """VnPy服务基类"""

    def __init__(self, name: str):
        self.name = name
        self._initialized = False

    @abstractmethod
    def initialize(self) -> bool:
        """初始化服务"""
        pass

    @abstractmethod
    def shutdown(self):
        """关闭服务"""
        pass

    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized


class DataService(VnPyService):
    """数据服务"""

    def __init__(self):
        super().__init__("data_service")
        self.datafeeds: Dict[str, Any] = {}

    def initialize(self) -> bool:
        """初始化数据服务"""
        try:
            # 注册数据源
            self._register_datafeeds()
            self._initialized = True
            logger.info("数据服务初始化成功")
            return True
        except Exception as e:
            logger.error(f"数据服务初始化失败: {e}")
            return False

    def _register_datafeeds(self):
        """注册数据源"""
        # 从适配器获取已注册的数据源
        if vnpy_adapter.is_initialized():
            self.datafeeds = vnpy_adapter.datafeeds.copy()

    def get_datafeed(self, name: str) -> Optional[Any]:
        """获取数据源"""
        return self.datafeeds.get(name)

    def shutdown(self):
        """关闭数据服务"""
        self.datafeeds.clear()
        self._initialized = False
        logger.info("数据服务已关闭")


class TradingService(VnPyService):
    """交易服务"""

    def __init__(self):
        super().__init__("trading_service")
        self.gateways: Dict[str, Any] = {}

    def initialize(self) -> bool:
        """初始化交易服务"""
        try:
            # 注册交易网关
            self._register_gateways()
            self._initialized = True
            logger.info("交易服务初始化成功")
            return True
        except Exception as e:
            logger.error(f"交易服务初始化失败: {e}")
            return False

    def _register_gateways(self):
        """注册交易网关"""
        # 从适配器获取已注册的网关
        if vnpy_adapter.is_initialized():
            self.gateways = vnpy_adapter.gateways.copy()

    def get_gateway(self, name: str) -> Optional[Any]:
        """获取交易网关"""
        return self.gateways.get(name)

    def shutdown(self):
        """关闭交易服务"""
        self.gateways.clear()
        self._initialized = False
        logger.info("交易服务已关闭")


class StrategyService(VnPyService):
    """策略服务"""

    def __init__(self):
        super().__init__("strategy_service")
        self.apps: Dict[str, Any] = {}

    def initialize(self) -> bool:
        """初始化策略服务"""
        try:
            # 注册策略应用
            self._register_apps()
            self._initialized = True
            logger.info("策略服务初始化成功")
            return True
        except Exception as e:
            logger.error(f"策略服务初始化失败: {e}")
            return False

    def _register_apps(self):
        """注册策略应用"""
        # 从适配器获取已注册的应用
        if vnpy_adapter.is_initialized():
            self.apps = vnpy_adapter.apps.copy()

    def get_app(self, name: str) -> Optional[Any]:
        """获取策略应用"""
        return self.apps.get(name)

    def shutdown(self):
        """关闭策略服务"""
        self.apps.clear()
        self._initialized = False
        logger.info("策略服务已关闭")


class VnPyServiceRegistry:
    """VnPy服务注册表"""

    def __init__(self):
        self.services: Dict[str, VnPyService] = {}
        self._initialized = False

    def register_service(self, service: VnPyService) -> bool:
        """注册服务"""
        try:
            if service.name in self.services:
                logger.warning(f"服务 {service.name} 已存在,将被覆盖")

            self.services[service.name] = service
            logger.info(f"服务 {service.name} 注册成功")
            return True

        except Exception as e:
            logger.error(f"注册服务 {service.name} 失败: {e}")
            return False

    def unregister_service(self, name: str) -> bool:
        """注销服务"""
        try:
            if name in self.services:
                service = self.services[name]
                if service.is_initialized():
                    service.shutdown()
                del self.services[name]
                logger.info(f"服务 {name} 注销成功")
                return True
            else:
                logger.warning(f"服务 {name} 不存在")
                return False

        except Exception as e:
            logger.error(f"注销服务 {name} 失败: {e}")
            return False

    def get_service(self, name: str) -> Optional[VnPyService]:
        """获取服务"""
        return self.services.get(name)

    def initialize_all(self) -> bool:
        """初始化所有服务"""
        try:
            success_count = 0
            for name, service in self.services.items():
                if service.initialize():
                    success_count += 1
                else:
                    logger.error(f"服务 {name} 初始化失败")

            self._initialized = success_count == len(self.services)

            if self._initialized:
                logger.info("所有VnPy服务初始化成功")
            else:
                logger.warning(f"部分VnPy服务初始化失败: {success_count}/{len(self.services)}")

            return self._initialized

        except Exception as e:
            logger.error(f"初始化VnPy服务失败: {e}")
            return False

    def shutdown_all(self):
        """关闭所有服务"""
        try:
            for name, service in self.services.items():
                try:
                    if service.is_initialized():
                        service.shutdown()
                except Exception as e:
                    logger.error(f"关闭服务 {name} 失败: {e}")

            self._initialized = False
            logger.info("所有VnPy服务已关闭")

        except Exception as e:
            logger.error(f"关闭VnPy服务失败: {e}")

    def get_service_status(self) -> Dict[str, bool]:
        """获取所有服务状态"""
        return {name: service.is_initialized() for name, service in self.services.items()}

    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized


# 创建全局服务注册表并注册默认服务
service_registry = VnPyServiceRegistry()

# 注册默认服务
service_registry.register_service(DataService())
service_registry.register_service(TradingService())
service_registry.register_service(StrategyService())


__all__ = [
    "VnPyService", "DataService", "TradingService", "StrategyService",
    "VnPyServiceRegistry", "service_registry"
]
