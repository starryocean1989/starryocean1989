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
                def load_bar_data(
                    self,
                    symbol: str,
                    exchange: Optional[str] = None,
                    interval: str = "1m",
                    start: Optional[Any] = None,
                    end: Optional[Any] = None,
                ):
                    return []

            class DummyVnpyService:
                def __init__(self):
                    self.is_initialized = True
                    self._chinastock_engine = None
                    self._init_chinastock_engine()

                def _init_chinastock_engine(self):
                    """初始化data_module_vnpy引擎（真实的）"""
                    try:
                        from vnpy.event import EventEngine
                        from vnpy.trader.engine import MainEngine
                        from backend.infrastructure.data_module_vnpy import ChinaStockApp

                        # 创建真实的VnPy引擎和data_module_vnpy
                        event_engine = EventEngine()
                        main_engine = MainEngine(event_engine)
                        self._chinastock_engine = main_engine.add_app(ChinaStockApp)
                        self._main_engine = main_engine
                        self._event_engine = event_engine
                        logger.info("data_module_vnpy引擎已加载到测试环境")
                    except Exception as e:
                        logger.warning("无法加载data_module_vnpy引擎: %s", e)
                        self._chinastock_engine = None

                def get_database_manager(self):
                    return DummyDatabase()

                def get_symbols(self):
                    """从data_module_vnpy获取品种列表"""
                    if self._chinastock_engine:
                        try:
                            stocks_dict = self._chinastock_engine.refresh_stock_list()
                            if stocks_dict and isinstance(stocks_dict, dict):
                                # 转换为统一格式
                                symbols = []
                                for market_type, stock_codes in stocks_dict.items():
                                    if not isinstance(stock_codes, list):
                                        continue
                                    for code in stock_codes:
                                        # 根据代码判断交易所
                                        if code.startswith(("6", "688")):
                                            exchange = "SSE"
                                        elif code.startswith(("0", "1", "2", "3")):
                                            exchange = "SZSE"
                                        else:
                                            exchange = "SSE"

                                        symbols.append(
                                            {
                                                "symbol": code,
                                                "exchange": exchange,
                                                "name": code,
                                                "product": market_type,
                                                "size": 100,
                                                "pricetick": 0.01,
                                            }
                                        )
                                return symbols
                        except Exception as e:
                            logger.warning("从data_module_vnpy获取品种失败: %s", e)
                    return []

                def get_chinastock_engine(self):
                    """获取data_module_vnpy引擎"""
                    return self._chinastock_engine

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

            # 保存vnpy_stub引用供stop使用
            self._vnpy_stub = vnpy_stub

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

            # 关闭data_module_vnpy引擎
            if hasattr(self, "_vnpy_stub") and self._vnpy_stub:
                if hasattr(self._vnpy_stub, "_main_engine") and self._vnpy_stub._main_engine:
                    try:
                        self._vnpy_stub._main_engine.close()
                        logger.info("data_module_vnpy引擎已关闭")
                    except Exception as e:
                        logger.warning("关闭data_module_vnpy引擎失败: %s", e)

                if hasattr(self._vnpy_stub, "_event_engine") and self._vnpy_stub._event_engine:
                    try:
                        self._vnpy_stub._event_engine.stop()
                        logger.info("事件引擎已停止")
                    except Exception as e:
                        logger.warning("停止事件引擎失败: %s", e)

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
