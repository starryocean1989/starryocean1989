# -*- coding: utf-8 -*-
"""
网关适配器基类.

定义所有网关适配器的统一接口。
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BaseGatewayAdapter(ABC):
    """网关适配器基类."""

    def __init__(self, gateway_name: str):
        """初始化网关适配器."""
        self.gateway_name = gateway_name
        self.vnpy_gateway = None
        self.is_connected = False
        logger.info("网关适配器初始化: %s", gateway_name)

    @abstractmethod
    def get_config_schema(self) -> Dict[str, Any]:
        """获取配置模式（动态表单）."""
        raise NotImplementedError()

    @abstractmethod
    def connect(
        self, config: Dict[str, Any], password: Optional[str] = None  # noqa: U100
    ) -> bool:
        """连接网关."""
        raise NotImplementedError()

    @abstractmethod
    def disconnect(self) -> bool:
        """断开网关."""
        raise NotImplementedError()

    @abstractmethod
    def subscribe(self, symbol: str, exchange: str) -> bool:  # noqa: U100
        """订阅行情."""
        raise NotImplementedError()

    @abstractmethod
    def send_order(self, order_req: Dict[str, Any]) -> str:  # noqa: U100
        """发送委托."""
        raise NotImplementedError()

    @abstractmethod
    def cancel_order(self, order_id: str) -> bool:  # noqa: U100
        """撤销委托."""
        raise NotImplementedError()

    @abstractmethod
    def query_account(self) -> Dict[str, Any]:
        """查询资金."""
        raise NotImplementedError()

    @abstractmethod
    def query_position(self) -> list:
        """查询持仓."""
        raise NotImplementedError()

    def get_status(self) -> Dict[str, Any]:
        """获取网关状态."""
        return {
            "gateway_name": self.gateway_name,
            "is_connected": self.is_connected,
        }


__all__ = ["BaseGatewayAdapter"]
