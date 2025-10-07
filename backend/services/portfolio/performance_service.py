# -*- coding: utf-8 -*-
"""
业绩分析服务.

提供业绩指标计算功能，使用pandas和numpy。
"""

import logging
from typing import Dict, Any, List
import numpy as np
from datetime import datetime

logger = logging.getLogger(__name__)


class PerformanceService:
    """业绩分析服务."""

    def __init__(self):
        """初始化业绩服务."""
        logger.info("业绩分析服务初始化完成")

    def calculate_performance(
        self, portfolio_id: str, returns: List[float], net_values: List[float]
    ) -> Dict[str, Any]:
        """计算业绩指标."""
        try:
            if not returns or not net_values:
                return self._empty_performance(portfolio_id)

            returns_array = np.array(returns)
            net_values_array = np.array(net_values)

            # 总收益率
            total_return = float((net_values_array[-1] / net_values_array[0]) - 1)

            # 年化收益率
            days = len(returns_array)
            annual_return = float(
                (1 + total_return) ** (252 / days) - 1 if days > 0 else 0
            )

            # 夏普比率 (假设无风险利率为3%)
            risk_free_rate = 0.03 / 252
            excess_returns = returns_array - risk_free_rate
            sharpe_ratio = float(
                np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)
                if np.std(excess_returns) > 0
                else 0
            )

            # 索提诺比率 (只考虑下行波动)
            downside_returns = returns_array[returns_array < 0]
            downside_std = float(
                np.std(downside_returns) if len(downside_returns) > 0 else 0
            )
            sortino_ratio = float(
                np.mean(excess_returns) / downside_std * np.sqrt(252)
                if downside_std > 0
                else 0
            )

            # 最大回撤
            cumulative = np.cumprod(1 + returns_array)
            running_max = np.maximum.accumulate(cumulative)
            drawdown = (cumulative - running_max) / running_max
            max_drawdown = float(np.min(drawdown))

            # 胜率
            win_count = int(np.sum(returns_array > 0))
            total_count = len(returns_array)
            win_rate = float(win_count / total_count if total_count > 0 else 0)

            performance = {
                "portfolio_id": portfolio_id,
                "date": datetime.now().isoformat(),
                "net_value": float(net_values_array[-1]),
                "total_return": total_return,
                "daily_return": (
                    float(returns_array[-1]) if len(returns_array) > 0 else 0.0
                ),
                "annual_return": annual_return,
                "sharpe_ratio": sharpe_ratio,
                "sortino_ratio": sortino_ratio,
                "max_drawdown": max_drawdown,
                "win_rate": win_rate,
            }

            logger.info(
                "业绩指标计算完成: portfolio_id=%s, total_return=%.2f%%",
                portfolio_id,
                total_return * 100,
            )
            return performance

        except Exception as e:
            logger.error("计算业绩指标失败: %s", e)
            raise

    def _empty_performance(self, portfolio_id: str) -> Dict[str, Any]:
        """空业绩指标."""
        return {
            "portfolio_id": portfolio_id,
            "date": datetime.now().isoformat(),
            "net_value": 1.0,
            "total_return": 0.0,
            "daily_return": 0.0,
            "annual_return": 0.0,
            "sharpe_ratio": 0.0,
            "sortino_ratio": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
        }


__all__ = ["PerformanceService"]
