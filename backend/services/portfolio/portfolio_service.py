# -*- coding: utf-8 -*-
"""
组合管理服务.

提供组合创建、管理、虚拟网关生成等功能。
"""

import logging
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class PortfolioService:
    """组合管理服务."""

    def __init__(self):
        """初始化组合服务."""
        self.portfolios: Dict[str, Dict[str, Any]] = {}
        self.virtual_gateways: Dict[str, Dict[str, Any]] = {}
        logger.info("组合管理服务初始化完成")

    def create_portfolio(
        self,
        portfolio_name: str,
        description: str = "",
        config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """创建组合."""
        try:
            portfolio_id = f"pf_{int(datetime.now().timestamp())}"

            portfolio = {
                "portfolio_id": portfolio_id,
                "portfolio_name": portfolio_name,
                "portfolio_type": "custom",
                "description": description,
                "config": config or {},
                "is_active": True,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }

            self.portfolios[portfolio_id] = portfolio

            logger.info("组合创建成功: portfolio_id=%s", portfolio_id)
            return portfolio

        except Exception as e:
            logger.error("创建组合失败: %s", e)
            raise

    def create_virtual_gateway(
        self, virtual_name: str, member_gateways: List[str], description: str = ""
    ) -> Dict[str, Any]:
        """创建虚拟网关."""
        try:
            # 使用hashlib生成唯一ID
            virtual_id = hashlib.md5(
                f"{sorted(member_gateways)}_{datetime.now().timestamp()}".encode()
            ).hexdigest()[:16]

            virtual_gateway = {
                "virtual_id": virtual_id,
                "virtual_name": virtual_name,
                "member_gateways": member_gateways,
                "description": description,
                "created_at": datetime.now().isoformat(),
                "updated_at": datetime.now().isoformat(),
            }

            self.virtual_gateways[virtual_id] = virtual_gateway

            logger.info(
                "虚拟网关创建成功: virtual_id=%s, members=%s",
                virtual_id,
                member_gateways,
            )
            return virtual_gateway

        except Exception as e:
            logger.error("创建虚拟网关失败: %s", e)
            raise

    def list_portfolios(self) -> List[Dict[str, Any]]:
        """列出所有组合."""
        return list(self.portfolios.values())

    def get_portfolio(self, portfolio_id: str) -> Optional[Dict[str, Any]]:
        """获取组合详情."""
        return self.portfolios.get(portfolio_id)

    def delete_portfolio(self, portfolio_id: str) -> bool:
        """删除组合."""
        try:
            if portfolio_id not in self.portfolios:
                raise ValueError(f"组合不存在: {portfolio_id}")

            del self.portfolios[portfolio_id]

            logger.info("组合删除成功: portfolio_id=%s", portfolio_id)
            return True

        except Exception as e:
            logger.error("删除组合失败: %s", e)
            raise

    def delete_virtual_gateway(self, virtual_id: str) -> bool:
        """删除虚拟网关."""
        try:
            if virtual_id not in self.virtual_gateways:
                raise ValueError(f"虚拟网关不存在: {virtual_id}")

            del self.virtual_gateways[virtual_id]

            logger.info("虚拟网关删除成功: virtual_id=%s", virtual_id)
            return True

        except Exception as e:
            logger.error("删除虚拟网关失败: %s", e)
            raise

    def list_virtual_gateways(self) -> List[Dict[str, Any]]:
        """列出所有虚拟网关."""
        return list(self.virtual_gateways.values())


__all__ = ["PortfolioService"]
