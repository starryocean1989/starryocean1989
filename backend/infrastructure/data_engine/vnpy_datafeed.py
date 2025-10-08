# -*- coding: utf-8 -*-
"""VnPy数据馈送模块 - 将data_engine集成到vnpy."""

import logging
from typing import Any, Dict

from vnpy.trader.gateway import BaseGateway
from vnpy.trader.object import SubscribeRequest, OrderRequest, CancelRequest

logger = logging.getLogger(__name__)


class DataEngineGateway(BaseGateway):
    """数据引擎网关 - 将data_engine作为vnpy的datafeed."""

    default_name = "DATA_ENGINE"

    def __init__(self, event_engine, gateway_name: str = "DATA_ENGINE"):
        """初始化数据引擎网关."""
        super().__init__(event_engine, gateway_name)
        self.logger = logging.getLogger(__name__)

    def connect(self, setting: Dict[str, Any]) -> None:
        """连接网关."""
        self.logger.info("连接数据引擎网关")
        self.write_log("数据引擎网关连接成功")

    def subscribe(self, req: SubscribeRequest) -> None:
        """订阅行情."""
        self.logger.info(f"订阅行情: {req.symbol}")

    def send_order(self, req: OrderRequest) -> str:
        """发送委托."""
        self.logger.warning("数据引擎网关不支持发送委托")
        return ""

    def cancel_order(self, req: CancelRequest) -> None:
        """撤销委托."""
        self.logger.warning("数据引擎网关不支持撤销委托")

    def query_account(self) -> None:
        """查询账户."""
        pass

    def query_position(self) -> None:
        """查询持仓."""
        pass

    def close(self) -> None:
        """关闭连接."""
        self.logger.info("关闭数据引擎网关连接")
        self.write_log("数据引擎网关已关闭")
