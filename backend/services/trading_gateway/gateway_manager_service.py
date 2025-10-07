# -*- coding: utf-8 -*-
"""
网关管理服务.

提供7种交易网关的统一管理接口。
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class GatewayManagerService:
    """网关管理服务."""

    def __init__(self):
        """初始化网关管理服务."""
        self.gateways: Dict[str, Dict[str, Any]] = {}
        self.gateway_types = {
            "CTP": "期货网关",
            "CTI_mini": "CTP迷你网关",
            "Spot": "ETF期权网关",
            "TTS": "期货仿真网关",
            "IB": "盈透证券网关",
            "PaperAccount": "模拟交易网关",
            "TDX": "通达信股票网关",
        }
        logger.info("网关管理服务初始化完成，支持%d种网关类型", len(self.gateway_types))

    def get_config_schema(self, gateway_type: str) -> Dict[str, Any]:
        """获取网关配置模式（动态表单）."""
        try:
            # PaperAccount不需要服务器地址
            if gateway_type == "PaperAccount":
                return {
                    "fields": [
                        {
                            "name": "initial_capital",
                            "label": "初始资金",
                            "type": "number",
                            "required": True,
                            "default": 1000000.0,
                        }
                    ]
                }

            # 其他网关需要服务器配置
            base_fields = [
                {
                    "name": "server",
                    "label": "服务器地址",
                    "type": "string",
                    "required": True,
                },
                {
                    "name": "username",
                    "label": "用户名",
                    "type": "string",
                    "required": True,
                },
                {
                    "name": "password",
                    "label": "密码",
                    "type": "password",
                    "required": True,
                },
            ]

            # 特定网关的额外字段
            if gateway_type == "CTP":
                base_fields.extend(
                    [
                        {"name": "broker_id", "label": "经纪商代码", "type": "string"},
                        {"name": "product_info", "label": "产品名称", "type": "string"},
                        {"name": "auth_code", "label": "授权编码", "type": "string"},
                    ]
                )
            elif gateway_type == "IB":
                base_fields.extend(
                    [
                        {"name": "client_id", "label": "客户号", "type": "number"},
                        {"name": "account_id", "label": "账户ID", "type": "string"},
                    ]
                )

            return {"fields": base_fields}

        except Exception as e:
            logger.error("获取配置模式失败: %s", e)
            raise

    def create_gateway(
        self, gateway_type: str, instance_name: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """创建网关实例."""
        try:
            if gateway_type not in self.gateway_types:
                raise ValueError(f"不支持的网关类型: {gateway_type}")

            instance_id = f"gw_{int(datetime.now().timestamp())}"

            gateway = {
                "instance_id": instance_id,
                "gateway_type": gateway_type,
                "instance_name": instance_name,
                "config": config,
                "status": "disconnected",
                "connected_at": None,
                "error_count": 0,
                "last_error": None,
                "created_at": datetime.now().isoformat(),
            }

            self.gateways[instance_id] = gateway

            logger.info(
                "网关实例创建成功: instance_id=%s, type=%s", instance_id, gateway_type
            )
            return gateway

        except Exception as e:
            logger.error("创建网关实例失败: %s", e)
            raise

    def connect_gateway(self, instance_id: str, password: Optional[str] = None) -> bool:
        """连接网关.

        Args:
            instance_id: 网关实例ID
            password: 密码（用于重新认证，可选）
        """
        try:
            if instance_id not in self.gateways:
                raise ValueError(f"网关实例不存在: {instance_id}")

            gateway = self.gateways[instance_id]

            # TODO: 实际调用VnPy网关的connect方法
            # 将使用password参数进行认证
            if password:
                logger.debug("使用提供的密码进行连接认证")

            # 这里模拟连接
            gateway["status"] = "connected"
            gateway["connected_at"] = datetime.now().isoformat()

            logger.info("网关连接成功: instance_id=%s", instance_id)
            return True

        except Exception as e:
            logger.error("连接网关失败: instance_id=%s, error=%s", instance_id, e)
            if instance_id in self.gateways:
                self.gateways[instance_id]["status"] = "error"
                self.gateways[instance_id]["last_error"] = str(e)
                self.gateways[instance_id]["error_count"] += 1
            raise

    def disconnect_gateway(self, instance_id: str) -> bool:
        """断开网关."""
        try:
            if instance_id not in self.gateways:
                raise ValueError(f"网关实例不存在: {instance_id}")

            gateway = self.gateways[instance_id]

            # TODO: 实际调用VnPy网关的close方法
            gateway["status"] = "disconnected"
            gateway["disconnected_at"] = datetime.now().isoformat()

            logger.info("网关断开成功: instance_id=%s", instance_id)
            return True

        except Exception as e:
            logger.error("断开网关失败: %s", e)
            raise

    def delete_gateway(self, instance_id: str) -> bool:
        """删除网关实例."""
        try:
            if instance_id not in self.gateways:
                raise ValueError(f"网关实例不存在: {instance_id}")

            # 先断开连接
            if self.gateways[instance_id]["status"] == "connected":
                self.disconnect_gateway(instance_id)

            # 删除实例
            del self.gateways[instance_id]

            logger.info("网关实例删除成功: instance_id=%s", instance_id)
            return True

        except Exception as e:
            logger.error("删除网关实例失败: %s", e)
            raise

    def list_gateways(self) -> List[Dict[str, Any]]:
        """列出所有网关实例."""
        return list(self.gateways.values())

    def get_gateway(self, instance_id: str) -> Optional[Dict[str, Any]]:
        """获取网关实例."""
        return self.gateways.get(instance_id)


__all__ = ["GatewayManagerService"]
