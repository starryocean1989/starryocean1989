# -*- coding: utf-8 -*-
"""
交易网关适配器模块

提供7种VnPy交易网关的统一适配器接口。
"""

from backend.services.trading_gateway.gateway_adapters.base_adapter import (
    BaseGatewayAdapter,
)
from backend.services.trading_gateway.gateway_adapters.paper_adapter import (
    PaperAccountAdapter,
)
from backend.services.trading_gateway.gateway_adapters.ctp_adapter import (
    CTPGatewayAdapter,
)
from backend.services.trading_gateway.gateway_adapters.all_adapters import (
    CTPTestGatewayAdapter,
    SoptGatewayAdapter,
    TTSGatewayAdapter,
    IBGatewayAdapter,
    TDXGatewayAdapter,
)


class GatewayAdapterFactory:
    """网关适配器工厂类"""

    _adapters = {
        "CTP": CTPGatewayAdapter,
        "CTPTest": CTPTestGatewayAdapter,
        "Sopt": SoptGatewayAdapter,
        "TTS": TTSGatewayAdapter,
        "IB": IBGatewayAdapter,
        "PaperAccount": PaperAccountAdapter,
        "TDX": TDXGatewayAdapter,
    }

    @classmethod
    def create_adapter(cls, gateway_type: str) -> BaseGatewayAdapter:
        """创建网关适配器实例"""
        adapter_class = cls._adapters.get(gateway_type)
        if adapter_class:
            return adapter_class()
        else:
            raise ValueError(f"不支持的网关类型: {gateway_type}")

    @classmethod
    def get_supported_types(cls) -> list:
        """获取支持的网关类型列表"""
        return list(cls._adapters.keys())

    @classmethod
    def get_config_schema(cls, gateway_type: str) -> dict:
        """获取指定网关的配置模式"""
        adapter = cls.create_adapter(gateway_type)
        return adapter.get_config_schema()


__all__ = [
    "BaseGatewayAdapter",
    "CTPGatewayAdapter",
    "CTPTestGatewayAdapter",
    "SoptGatewayAdapter",
    "TTSGatewayAdapter",
    "IBGatewayAdapter",
    "PaperAccountAdapter",
    "TDXGatewayAdapter",
    "GatewayAdapterFactory",
]
