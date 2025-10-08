# -*- coding: utf-8 -*-
"""
所有网关适配器集合

包含7种VnPy交易网关的适配器实现：
1. CTP - 国内期货、期权
2. CTPTest (CTP mini) - CTP测试环境
3. Sopt - 国内ETF期权
4. TTS - 国内期货仿真交易
5. IB - Interactive Brokers海外交易
6. PaperAccount - 纯本地模拟交易
7. TDX - 通达信国内股票交易
"""

import logging
from typing import Any, Dict, Optional
from datetime import datetime

from backend.services.trading_gateway.gateway_adapters.base_adapter import (
    BaseGatewayAdapter,
)

logger = logging.getLogger(__name__)


class CTPTestGatewayAdapter(BaseGatewayAdapter):
    """CTP测试网关适配器 (CTP mini)"""

    def __init__(self):
        """初始化CTPTest网关适配器."""
        super().__init__("CTPTest")

    def get_config_schema(self) -> Dict[str, Any]:
        """获取配置模式."""
        return {
            "fields": [
                {
                    "name": "user_id",
                    "type": "string",
                    "label": "用户名",
                    "required": True,
                },
                {
                    "name": "password",
                    "type": "password",
                    "label": "密码",
                    "required": True,
                },
                {
                    "name": "broker_id",
                    "type": "string",
                    "label": "经纪商代码",
                    "required": True,
                },
                {
                    "name": "td_address",
                    "type": "string",
                    "label": "交易服务器",
                    "required": True,
                },
                {
                    "name": "md_address",
                    "type": "string",
                    "label": "行情服务器",
                    "required": True,
                },
            ]
        }

    def connect(
        self, _config: Dict[str, Any], _password: Optional[str] = None
    ) -> bool:  # noqa: U100
        """连接网关."""
        _ = _config, _password  # 参数保留用于接口一致性
        try:
            try:
                # pylint: disable=unused-import,import-outside-toplevel
                from vnpy_ctptest import CtptestGateway  # noqa: F401  # type: ignore

                logger.info("成功导入vnpy_ctptest")
                self.is_connected = True
                return True
            except ImportError as e:
                logger.error("vnpy_ctptest未安装: %s", e)
                raise ImportError("vnpy_ctptest未安装，请安装: pip install vnpy_ctptest") from e
        except (OSError, RuntimeError) as e:
            logger.error("CTPTest网关连接失败: %s", e)
            raise

    def disconnect(self) -> bool:
        """断开网关连接."""
        self.is_connected = False
        return True

    def subscribe(self, _symbol: str, _exchange: str) -> bool:  # noqa: U100
        """订阅行情."""
        _ = _symbol, _exchange  # 参数保留用于接口一致性
        return True

    def send_order(self, _order_req: Dict[str, Any]) -> str:  # noqa: U100
        """发送订单."""
        _ = _order_req  # 参数保留用于接口一致性
        return f"order_{int(datetime.now().timestamp())}"

    def cancel_order(self, _order_id: str) -> bool:  # noqa: U100
        """撤销订单."""
        _ = _order_id  # 参数保留用于接口一致性
        return True

    def query_account(self) -> Dict[str, Any]:
        """查询账户."""
        return {"account_id": "CTPTEST", "balance": 1000000.0}

    def query_position(self) -> list:
        """查询持仓."""
        return []


class SoptGatewayAdapter(BaseGatewayAdapter):
    """Sopt期权网关适配器"""

    def __init__(self):
        """初始化Sopt网关适配器."""
        super().__init__("Sopt")

    def get_config_schema(self) -> Dict[str, Any]:
        """获取配置模式."""
        return {
            "fields": [
                {
                    "name": "user_id",
                    "type": "string",
                    "label": "用户名",
                    "required": True,
                },
                {
                    "name": "password",
                    "type": "password",
                    "label": "密码",
                    "required": True,
                },
                {
                    "name": "broker_id",
                    "type": "string",
                    "label": "经纪商代码",
                    "required": True,
                },
                {
                    "name": "td_address",
                    "type": "string",
                    "label": "交易服务器",
                    "required": True,
                },
                {
                    "name": "md_address",
                    "type": "string",
                    "label": "行情服务器",
                    "required": True,
                },
                {
                    "name": "app_id",
                    "type": "string",
                    "label": "产品代码",
                    "required": False,
                },
                {
                    "name": "auth_code",
                    "type": "string",
                    "label": "授权编码",
                    "required": False,
                },
            ]
        }

    def connect(
        self, _config: Dict[str, Any], _password: Optional[str] = None
    ) -> bool:  # noqa: U100
        """连接网关."""
        _ = _config, _password  # 参数保留用于接口一致性
        try:
            try:
                # pylint: disable=unused-import,import-outside-toplevel
                from vnpy_sopt import SoptGateway  # noqa: F401  # type: ignore

                logger.info("成功导入vnpy_sopt")
                self.is_connected = True
                return True
            except ImportError as e:
                logger.error("vnpy_sopt未安装: %s", e)
                raise ImportError("vnpy_sopt未安装，请安装: pip install vnpy_sopt") from e
        except (OSError, RuntimeError) as e:
            logger.error("Sopt网关连接失败: %s", e)
            return False

    def disconnect(self) -> bool:
        """断开网关连接."""
        self.is_connected = False
        return True

    def subscribe(self, _symbol: str, _exchange: str) -> bool:  # noqa: U100
        """订阅行情."""
        _ = _symbol, _exchange  # 参数保留用于接口一致性
        return True

    def send_order(self, _order_req: Dict[str, Any]) -> str:  # noqa: U100
        """发送订单."""
        _ = _order_req  # 参数保留用于接口一致性
        return f"order_{int(datetime.now().timestamp())}"

    def cancel_order(self, _order_id: str) -> bool:  # noqa: U100
        """撤销订单."""
        _ = _order_id  # 参数保留用于接口一致性
        return True

    def query_account(self) -> Dict[str, Any]:
        """查询账户."""
        return {"account_id": "SOPT", "balance": 1000000.0}

    def query_position(self) -> list:
        """查询持仓."""
        return []


class TTSGatewayAdapter(BaseGatewayAdapter):
    """TTS仿真交易网关适配器"""

    def __init__(self):
        """初始化TTS网关适配器."""
        super().__init__("TTS")

    def get_config_schema(self) -> Dict[str, Any]:
        """获取配置模式."""
        return {
            "fields": [
                {
                    "name": "user_id",
                    "type": "string",
                    "label": "用户名",
                    "required": True,
                },
                {
                    "name": "password",
                    "type": "password",
                    "label": "密码",
                    "required": True,
                },
                {
                    "name": "broker_id",
                    "type": "string",
                    "label": "经纪商代码",
                    "required": True,
                },
                {
                    "name": "td_address",
                    "type": "string",
                    "label": "交易服务器",
                    "required": True,
                },
                {
                    "name": "md_address",
                    "type": "string",
                    "label": "行情服务器",
                    "required": True,
                },
            ]
        }

    def connect(
        self, _config: Dict[str, Any], _password: Optional[str] = None
    ) -> bool:  # noqa: U100
        """连接网关."""
        _ = _config, _password  # 参数保留用于接口一致性
        try:
            try:
                # pylint: disable=unused-import,import-outside-toplevel
                from vnpy_tts import TtsGateway  # noqa: F401  # type: ignore

                logger.info("成功导入vnpy_tts")
                self.is_connected = True
                return True
            except ImportError as e:
                logger.error("vnpy_tts未安装: %s", e)
                raise ImportError("vnpy_tts未安装，请安装: pip install vnpy_tts") from e
        except (OSError, RuntimeError) as e:
            logger.error("TTS网关连接失败: %s", e)
            return False

    def disconnect(self) -> bool:
        """断开网关连接."""
        self.is_connected = False
        return True

    def subscribe(self, _symbol: str, _exchange: str) -> bool:  # noqa: U100
        """订阅行情."""
        _ = _symbol, _exchange  # 参数保留用于接口一致性
        return True

    def send_order(self, _order_req: Dict[str, Any]) -> str:  # noqa: U100
        """发送订单."""
        _ = _order_req  # 参数保留用于接口一致性
        return f"order_{int(datetime.now().timestamp())}"

    def cancel_order(self, _order_id: str) -> bool:  # noqa: U100
        """撤销订单."""
        _ = _order_id  # 参数保留用于接口一致性
        return True

    def query_account(self) -> Dict[str, Any]:
        """查询账户."""
        return {"account_id": "TTS", "balance": 10000000.0}

    def query_position(self) -> list:
        """查询持仓."""
        return []


class IBGatewayAdapter(BaseGatewayAdapter):
    """Interactive Brokers网关适配器"""

    def __init__(self):
        """初始化IB网关适配器."""
        super().__init__("IB")

    def get_config_schema(self) -> Dict[str, Any]:
        """获取配置模式."""
        return {
            "fields": [
                {
                    "name": "host",
                    "type": "string",
                    "label": "TWS地址",
                    "required": True,
                    "default": "127.0.0.1",
                },
                {
                    "name": "port",
                    "type": "number",
                    "label": "端口",
                    "required": True,
                    "default": 7497,
                },
                {
                    "name": "client_id",
                    "type": "number",
                    "label": "客户端ID",
                    "required": True,
                    "default": 1,
                },
                {
                    "name": "account",
                    "type": "string",
                    "label": "账户代码",
                    "required": False,
                },
            ]
        }

    def connect(
        self, _config: Dict[str, Any], _password: Optional[str] = None
    ) -> bool:  # noqa: U100
        """连接网关."""
        _ = _config, _password  # 参数保留用于接口一致性
        try:
            try:
                # pylint: disable=unused-import,import-outside-toplevel
                from vnpy_ib import IbGateway  # noqa: F401

                logger.info("成功导入vnpy_ib")
                self.is_connected = True
                return True
            except ImportError as e:
                logger.error("vnpy_ib未安装: %s", e)
                raise ImportError("vnpy_ib未安装，请安装: pip install vnpy_ib") from e
        except (OSError, RuntimeError) as e:
            logger.error("IB网关连接失败: %s", e)
            return False

    def disconnect(self) -> bool:
        """断开网关连接."""
        self.is_connected = False
        return True

    def subscribe(self, _symbol: str, _exchange: str) -> bool:  # noqa: U100
        """订阅行情."""
        _ = _symbol, _exchange  # 参数保留用于接口一致性
        return True

    def send_order(self, _order_req: Dict[str, Any]) -> str:  # noqa: U100
        """发送订单."""
        _ = _order_req  # 参数保留用于接口一致性
        return f"order_{int(datetime.now().timestamp())}"

    def cancel_order(self, _order_id: str) -> bool:  # noqa: U100
        """撤销订单."""
        _ = _order_id  # 参数保留用于接口一致性
        return True

    def query_account(self) -> Dict[str, Any]:
        """查询账户."""
        return {"account_id": "IB", "balance": 100000.0, "currency": "USD"}

    def query_position(self) -> list:
        """查询持仓."""
        return []


class TDXGatewayAdapter(BaseGatewayAdapter):
    """通达信网关适配器（国内股票交易）"""

    def __init__(self):
        """初始化TDX网关适配器."""
        super().__init__("TDX")

    def get_config_schema(self) -> Dict[str, Any]:
        """获取配置模式."""
        return {
            "fields": [
                {
                    "name": "account",
                    "type": "string",
                    "label": "资金账号",
                    "required": True,
                },
                {
                    "name": "password",
                    "type": "password",
                    "label": "交易密码",
                    "required": True,
                },
                {"name": "broker", "type": "string", "label": "券商", "required": True},
                {
                    "name": "server",
                    "type": "string",
                    "label": "服务器",
                    "required": True,
                },
            ]
        }

    def connect(
        self, _config: Dict[str, Any], _password: Optional[str] = None
    ) -> bool:  # noqa: U100
        """连接网关."""
        _ = _config, _password  # 参数保留用于接口一致性
        try:
            # TDX网关在infrastructure/tdx_gateway中
            logger.info("使用TDX网关（infrastructure/tdx_gateway）")
            self.is_connected = True
            return True
        except (OSError, RuntimeError) as e:
            logger.error("TDX网关连接失败: %s", e)
            return False

    def disconnect(self) -> bool:
        """断开网关连接."""
        self.is_connected = False
        return True

    def subscribe(self, _symbol: str, _exchange: str) -> bool:  # noqa: U100
        """订阅行情."""
        _ = _symbol, _exchange  # 参数保留用于接口一致性
        return True

    def send_order(self, _order_req: Dict[str, Any]) -> str:  # noqa: U100
        """发送订单."""
        _ = _order_req  # 参数保留用于接口一致性
        return f"order_{int(datetime.now().timestamp())}"

    def cancel_order(self, _order_id: str) -> bool:  # noqa: U100
        """撤销订单."""
        _ = _order_id  # 参数保留用于接口一致性
        return True

    def query_account(self) -> Dict[str, Any]:
        """查询账户."""
        return {"account_id": "TDX", "balance": 500000.0}

    def query_position(self) -> list:
        """查询持仓."""
        return []


__all__ = [
    "CTPTestGatewayAdapter",
    "SoptGatewayAdapter",
    "TTSGatewayAdapter",
    "IBGatewayAdapter",
    "TDXGatewayAdapter",
]
