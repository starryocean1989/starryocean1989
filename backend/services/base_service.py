# -*- coding: utf-8 -*-
"""
基础服务类.

提供所有服务的通用功能和接口定义。
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """服务状态枚举."""

    STOPPED = "stopped"  # 未启动
    STARTING = "starting"  # 启动中
    RUNNING = "running"  # 运行中
    STOPPING = "stopping"  # 停止中
    ERROR = "error"  # 错误状态


class BaseService(ABC):
    """服务基类.

    所有业务服务的抽象基类，提供：
    - 标准的初始化和关闭接口
    - 健康检查机制
    - 状态管理
    - 日志记录
    - 错误处理
    """

    def __init__(self):
        """初始化基础服务."""
        self.service_name = self.__class__.__name__
        self.logger = logging.getLogger(f"{__name__}.{self.service_name}")
        self.status = ServiceStatus.STOPPED
        self.is_initialized = False
        self.start_time: Optional[datetime] = None
        self._errors: List[str] = []

        # VNPY引擎引用（在_do_initialize中设置）
        self.main_engine = None
        self.event_engine = None

        self.logger.info(f"服务 {self.service_name} 创建完成")

    def initialize(self) -> bool:
        """初始化服务.

        Returns:
            bool: 是否成功初始化
        """
        try:
            self.status = ServiceStatus.STARTING
            self.logger.info(f"正在初始化服务: {self.service_name}")

            # 获取全局VNPY引擎
            from backend.core.shared_services import get_main_engine, get_event_engine

            self.main_engine = get_main_engine()
            self.event_engine = get_event_engine()

            # 调用子类的具体初始化逻辑
            result = self._do_initialize()

            if result:
                self.is_initialized = True
                self.start_time = datetime.now()
                self.status = ServiceStatus.RUNNING
                self.logger.info(f"服务 {self.service_name} 初始化成功")
            else:
                self.status = ServiceStatus.ERROR
                self.logger.error(f"服务 {self.service_name} 初始化失败")

            return result

        except Exception as e:
            self.status = ServiceStatus.ERROR
            self._errors.append(f"初始化异常: {str(e)}")
            self.logger.error(f"服务 {self.service_name} 初始化异常: {e}", exc_info=True)
            return False

    def shutdown(self) -> bool:
        """关闭服务.

        Returns:
            bool: 是否成功关闭
        """
        try:
            self.status = ServiceStatus.STOPPING
            self.logger.info(f"正在关闭服务: {self.service_name}")

            # 调用子类的具体关闭逻辑
            result = self._do_shutdown()

            self.is_initialized = False
            self.status = ServiceStatus.STOPPED
            self.logger.info(f"服务 {self.service_name} 关闭完成")

            return result

        except Exception as e:
            self.status = ServiceStatus.ERROR
            self._errors.append(f"关闭异常: {str(e)}")
            self.logger.error(f"服务 {self.service_name} 关闭异常: {e}", exc_info=True)
            return False

    def health_check(self) -> Dict[str, Any]:
        """健康检查.

        Returns:
            Dict: 健康检查结果
        """
        try:
            # 基础健康检查
            is_healthy = (
                self.status == ServiceStatus.RUNNING
                and self.is_initialized
                and len(self._errors) == 0
            )

            # 调用子类的具体健康检查逻辑
            custom_health = self._do_health_check()

            return {
                "service_name": self.service_name,
                "status": self.status.value,
                "is_healthy": is_healthy,
                "is_initialized": self.is_initialized,
                "uptime": self._get_uptime(),
                "errors": self._errors[-5:],  # 最近5个错误
                "custom": custom_health,
            }

        except Exception as e:
            return {
                "service_name": self.service_name,
                "status": "error",
                "is_healthy": False,
                "error": str(e),
            }

    @abstractmethod
    def _do_initialize(self) -> bool:
        """具体的初始化逻辑（由子类实现）.

        Returns:
            bool: 是否成功
        """
        pass

    @abstractmethod
    def _do_shutdown(self) -> bool:
        """具体的关闭逻辑（由子类实现）.

        Returns:
            bool: 是否成功
        """
        pass

    def _do_health_check(self) -> Dict[str, Any]:
        """具体的健康检查逻辑（由子类可选实现）.

        Returns:
            Dict: 自定义健康检查信息
        """
        return {}

    def get_service_info(self) -> Dict[str, Any]:
        """获取服务信息."""
        return {
            "service_name": self.service_name,
            "status": self.status.value,
            "is_initialized": self.is_initialized,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "uptime": self._get_uptime(),
            "error_count": len(self._errors),
            "has_main_engine": self.main_engine is not None,
            "has_event_engine": self.event_engine is not None,
        }

    def _get_uptime(self) -> Optional[float]:
        """获取运行时间（秒）."""
        if self.start_time:
            return (datetime.now() - self.start_time).total_seconds()
        return None

    def _log_operation(self, operation: str, **kwargs) -> None:
        """记录操作日志."""
        details = ", ".join(f"{k}={v}" for k, v in kwargs.items())
        self.logger.info(f"[{self.service_name}] {operation} {details if details else ''}")

    def _log_error(self, operation: str, error: Exception, **kwargs) -> None:
        """记录错误日志."""
        error_msg = f"{operation}: {str(error)}"
        self._errors.append(error_msg)

        # 限制错误列表大小
        if len(self._errors) > 100:
            self._errors = self._errors[-50:]

        details = ", ".join(f"{k}={v}" for k, v in kwargs.items())
        self.logger.error(
            f"[{self.service_name}] {operation} 失败 - {error} {details if details else ''}",
            exc_info=True,
        )

    def clear_errors(self):
        """清空错误记录."""
        self._errors.clear()

    def get_errors(self, limit: int = 10) -> List[str]:
        """获取最近的错误记录.

        Args:
            limit: 返回的错误数量限制

        Returns:
            List[str]: 错误列表
        """
        return self._errors[-limit:] if self._errors else []


# 导出公共接口
__all__ = ["BaseService", "ServiceStatus"]
