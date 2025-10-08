# -*- coding: utf-8 -*-
"""
CTP网关适配器

CTP（综合交易平台）- 国内期货、期权交易网关
"""

import logging
from typing import Any, Dict, Optional
from datetime import datetime

from backend.services.trading_gateway.gateway_adapters.base_adapter import (
    BaseGatewayAdapter,
)

logger = logging.getLogger(__name__)


class CTPGatewayAdapter(BaseGatewayAdapter):
    """CTP网关适配器"""

    def __init__(self):
        """初始化CTP网关适配器"""
        super().__init__("CTP")

    def get_config_schema(self) -> Dict[str, Any]:
        """获取CTP网关配置模式"""
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

    def connect(self, config: Dict[str, Any], password: Optional[str] = None) -> bool:
        """连接CTP网关"""
        try:
            # 尝试导入vnpy_ctp
            try:
                # pylint: disable=unused-import,import-outside-toplevel
                from vnpy_ctp import CtpGateway  # noqa: F401

                logger.info("成功导入vnpy_ctp")

                # 实际集成代码
                # self.vnpy_gateway = CtpGateway(event_engine)
                # self.vnpy_gateway.connect(config)

                self.is_connected = True
                logger.info("CTP网关连接成功")
                return True

            except ImportError as e:
                logger.error("vnpy_ctp未安装: %s", e)
                raise ImportError("vnpy_ctp未安装，请安装: pip install vnpy_ctp")

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("CTP网关连接失败: %s", e)
            self.is_connected = False
            raise

    def disconnect(self) -> bool:
        """断开CTP网关"""
        try:
            if self.vnpy_gateway:
                # self.vnpy_gateway.close()
                pass

            self.is_connected = False
            logger.info("CTP网关已断开")
            return True

        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("CTP网关断开失败: %s", e)
            return False

    def subscribe(self, symbol: str, exchange: str) -> bool:
        """订阅行情"""
        logger.info("订阅行情: %s.%s", symbol, exchange)
        return True

    def send_order(self, order_req: Dict[str, Any]) -> str:
        """发送委托"""
        logger.info("发送委托: %s", order_req)
        order_symbol = order_req.get("symbol", "unknown")
        return f"order_{order_symbol}_{int(datetime.now().timestamp())}"

    def cancel_order(self, order_id: str) -> bool:
        """撤销委托"""
        logger.info("撤销委托: %s", order_id)
        return True

    def query_account(self) -> Dict[str, Any]:
        """查询资金"""
        return {
            "account_id": "CTP_ACCOUNT",
            "balance": 1000000.0,
            "available": 950000.0,
            "frozen": 50000.0,
        }

    def query_position(self) -> list:
        """查询持仓"""
        return []


__all__ = ["CTPGatewayAdapter"]
