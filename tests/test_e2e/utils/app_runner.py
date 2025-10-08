# -*- coding: utf-8 -*-
"""
后端应用启动器.

提供E2E测试所需的后端应用启动和管理功能。
"""

import asyncio
import logging
from typing import Any, Dict, Optional

from backend.config import Settings

logger = logging.getLogger(__name__)


class BackendAppRunner:
    """后端应用运行器."""

    def __init__(self):
        """初始化应用运行器."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self.settings: Optional[Settings] = None
        self._initialized = False

    async def start(self) -> Dict[str, Any]:
        """
        启动后端应用.

        Returns:
            包含服务实例的字典
        """
        try:
            self.logger.info("正在启动后端应用（测试模式）...")

            # 初始化配置
            self.settings = Settings()

            # 简化实现：不需要启动完整的后端服务
            # E2E测试会通过conftest.py中的fixtures获取具体的服务实例

            self._initialized = True
            self.logger.info("后端应用启动成功")

            # 返回基础服务实例供测试使用（注入共享服务与轻量桩）
            class SharedServices:
                def __init__(self, vnpy_service, event_service):
                    self.vnpy_service = vnpy_service
                    self.event_service = event_service

            class DummyDatabase:
                def load_bar_data(self, symbol: str, exchange: Optional[str] = None,
                                  interval: str = "1m", start: Optional[Any] = None,
                                  end: Optional[Any] = None):
                    return []

            class DummyVnpyService:
                def __init__(self):
                    self.is_initialized = True
                def get_database_manager(self):
                    return DummyDatabase()
                def get_symbols(self):
                    return []

            class DummyEventService:
                def __init__(self):
                    self._handlers = {}
                    self.is_initialized = True
                def register_handler(self, event_type: str, handler):
                    self._handlers.setdefault(event_type, []).append(handler)
                def unregister_handler(self, event_type: str, handler):
                    if event_type in self._handlers:
                        try:
                            self._handlers[event_type].remove(handler)
                        except ValueError:
                            pass
                async def emit_event(self, event_type: str, data: Dict[str, Any]):
                    # 轻量桩：不做实际分发
                    return

            vnpy_stub = DummyVnpyService()
            event_stub = DummyEventService()
            shared = SharedServices(vnpy_stub, event_stub)

            return {
                "settings": self.settings,
                "vnpy_service": vnpy_stub,
                "event_service": event_stub,
                "shared_services": shared,
            }

        except Exception as e:
            self.logger.error(f"启动后端应用失败: {e}")
            raise

    async def stop(self) -> None:
        """停止后端应用."""
        try:
            if not self._initialized:
                return

            self.logger.info("正在关闭后端应用...")

            # 简化实现：无需清理

            self._initialized = False
            self.logger.info("后端应用关闭完成")

        except Exception as e:
            self.logger.error(f"关闭后端应用失败: {e}")
            raise

    @property
    def is_initialized(self) -> bool:
        """检查应用是否已初始化."""
        return self._initialized


# 导出公共接口
__all__ = ["BackendAppRunner"]
