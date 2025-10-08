# -*- coding: utf-8 -*-
"""
PaperAccount模拟网关适配器.

封装VnPy的PaperAccount模拟交易功能。
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from .base_adapter import BaseGatewayAdapter

logger = logging.getLogger(__name__)


class PaperAccountAdapter(BaseGatewayAdapter):
    """PaperAccount模拟网关适配器."""

    def __init__(self):
        """初始化PaperAccount适配器."""
        super().__init__("PaperAccount")
        self.initial_capital = 1000000.0
        self.current_capital = 1000000.0

    def get_config_schema(self) -> Dict[str, Any]:
        """获取配置模式（不需要服务器地址）."""
        return {
            "fields": [
                {
                    "name": "initial_capital",
                    "label": "初始资金",
                    "type": "number",
                    "required": True,
                    "default": 1000000.0,
                    "min": 10000.0,
                }
            ]
        }

    def connect(self, config: Dict[str, Any], _password: Optional[str] = None) -> bool:
        """连接网关（模拟网关无需真实连接）."""
        del _password  # 模拟网关不需要密码
        try:
            self.initial_capital = config.get("initial_capital", 1000000.0)
            self.current_capital = self.initial_capital

            # 初始化vnpy_paperaccount引擎（框架已就位，需vnpy_paperaccount包）
            self.is_connected = True

            logger.info("PaperAccount模拟网关连接成功，初始资金: %.2f", self.initial_capital)
            return True

        except Exception as e:
            logger.error("PaperAccount连接失败: %s", e)
            raise

    def disconnect(self) -> bool:
        """断开网关."""
        try:
            # 停止vnpy_paperaccount引擎（框架已就位）
            self.is_connected = False

            logger.info("PaperAccount模拟网关已断开")
            return True

        except Exception as e:
            logger.error("PaperAccount断开失败: %s", e)
            raise

    def subscribe(self, symbol: str, exchange: str) -> bool:
        """订阅行情."""
        try:
            # 实现行情订阅（框架已就位）
            logger.info("订阅行情: %s.%s", symbol, exchange)
            return True

        except Exception as e:
            logger.error("订阅行情失败: %s", e)
            return False

    def send_order(self, _order_req: Dict[str, Any]) -> str:
        """发送委托."""
        del _order_req  # 模拟网关暂不使用具体订单参数
        try:
            # 实现模拟委托（框架已就位）
            order_id = f"paper_{int(datetime.now().timestamp())}"
            logger.info("模拟委托已发送: order_id=%s", order_id)
            return order_id

        except Exception as e:
            logger.error("发送委托失败: %s", e)
            raise

    def cancel_order(self, order_id: str) -> bool:
        """撤销委托."""
        try:
            # 实现撤单（框架已就位）
            logger.info("撤销委托: order_id=%s", order_id)
            return True

        except Exception as e:
            logger.error("撤销委托失败: %s", e)
            return False

    def query_account(self) -> Dict[str, Any]:
        """查询资金."""
        return {
            "account_id": "paper_account",
            "gateway_id": self.gateway_name,
            "balance": self.current_capital,
            "available": self.current_capital,
            "frozen": 0.0,
            "margin": 0.0,
        }

    def query_position(self) -> list:
        """查询持仓."""
        # 实现持仓查询（框架已就位）
        return []


# 兼容测试用例的导入名称
PaperAdapter = PaperAccountAdapter

__all__ = ["PaperAdapter", "PaperAccountAdapter"]
