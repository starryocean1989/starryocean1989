# -*- coding: utf-8 -*-
"""
数据转换工具.

提供VnPy对象与统一数据模型之间的转换功能。
"""

import logging
from typing import Any, Dict, List, Optional, Union
from datetime import datetime

from backend.core.models import (
    UnifiedMarketData,
    UnifiedOrder,
    UnifiedTrade,
    UnifiedPosition,
    UnifiedAccount,
    DataMetadata,
    DataCategory,
    DataSource,
)

logger = logging.getLogger(__name__)


class DataConverter:
    """数据转换器."""

    @staticmethod
    def vnpy_tick_to_unified(tick: Any) -> Optional[UnifiedMarketData]:
        """将VnPy TickData转换为统一行情数据."""
        try:
            if not tick or not hasattr(tick, "symbol"):
                return None

            return UnifiedMarketData(
                symbol=tick.symbol,
                exchange=getattr(tick, "exchange", ""),
                data_type="tick",
                datetime=getattr(tick, "datetime", datetime.now()),
                timestamp=int(getattr(tick, "datetime", datetime.now()).timestamp()),
                open_price=getattr(tick, "open_price", 0.0),
                high_price=getattr(tick, "high_price", 0.0),
                low_price=getattr(tick, "low_price", 0.0),
                close_price=getattr(tick, "last_price", 0.0),
                pre_close=getattr(tick, "pre_close", 0.0),
                volume=getattr(tick, "volume", 0),
                turnover=getattr(tick, "turnover", 0.0),
                open_interest=getattr(tick, "open_interest", 0),
                bid_price=getattr(tick, "bid_price_1", 0.0),
                bid_volume=getattr(tick, "bid_volume_1", 0),
                ask_price=getattr(tick, "ask_price_1", 0.0),
                ask_volume=getattr(tick, "ask_volume_1", 0),
                metadata=DataMetadata(
                    DataCategory.MARKET_DATA,
                    DataSource.VNPY,
                    symbol=tick.symbol,
                    exchange=getattr(tick, "exchange", ""),
                    count=1,
                    last_updated=getattr(tick, "datetime", datetime.now()),
                ),
            )

        except Exception as e:
            logger.error("转换VnPy TickData失败: %s", e)
            return None

    @staticmethod
    def vnpy_bar_to_unified(bar: Any) -> Optional[UnifiedMarketData]:
        """将VnPy BarData转换为统一行情数据."""
        try:
            if not bar or not hasattr(bar, "symbol"):
                return None

            return UnifiedMarketData(
                symbol=bar.symbol,
                exchange=getattr(bar, "exchange", ""),
                data_type="bar",
                datetime=getattr(bar, "datetime", datetime.now()),
                timestamp=int(getattr(bar, "datetime", datetime.now()).timestamp()),
                open_price=getattr(bar, "open_price", 0.0),
                high_price=getattr(bar, "high_price", 0.0),
                low_price=getattr(bar, "low_price", 0.0),
                close_price=getattr(bar, "close_price", 0.0),
                pre_close=0.0,  # BarData中没有pre_close
                volume=getattr(bar, "volume", 0),
                turnover=getattr(bar, "turnover", 0.0),
                open_interest=getattr(bar, "open_interest", 0),
                metadata=DataMetadata(
                    DataCategory.MARKET_DATA,
                    DataSource.VNPY,
                    symbol=bar.symbol,
                    exchange=getattr(bar, "exchange", ""),
                    frequency=f"{getattr(bar, 'interval', 1)}m",
                    count=1,
                    last_updated=getattr(bar, "datetime", datetime.now()),
                ),
            )

        except Exception as e:
            logger.error("转换VnPy BarData失败: %s", e)
            return None

    @staticmethod
    def vnpy_order_to_unified(order: Any) -> Optional[UnifiedOrder]:
        """将VnPy OrderData转换为统一订单数据."""
        try:
            if not order or not hasattr(order, "symbol"):
                return None

            return UnifiedOrder(
                order_id=getattr(order, "orderid", ""),
                symbol=order.symbol,
                exchange=getattr(order, "exchange", ""),
                order_type=getattr(order, "type", ""),
                direction=getattr(order, "direction", ""),
                price=getattr(order, "price", 0.0),
                volume=getattr(order, "volume", 0),
                status=getattr(order, "status", ""),
                order_time=DataConverter._parse_time(getattr(order, "time", "")),
                traded_volume=getattr(order, "traded", 0),
                metadata=DataMetadata(
                    DataCategory.TRANSACTION_DATA,
                    DataSource.VNPY,
                    symbol=order.symbol,
                    exchange=getattr(order, "exchange", ""),
                    count=1,
                    last_updated=datetime.now(),
                ),
            )

        except Exception as e:
            logger.error("转换VnPy OrderData失败: %s", e)
            return None

    @staticmethod
    def vnpy_trade_to_unified(trade: Any) -> Optional[UnifiedTrade]:
        """将VnPy TradeData转换为统一成交数据."""
        try:
            if not trade or not hasattr(trade, "symbol"):
                return None

            return UnifiedTrade(
                trade_id=getattr(trade, "tradeid", ""),
                order_id=getattr(trade, "orderid", ""),
                symbol=trade.symbol,
                exchange=getattr(trade, "exchange", ""),
                direction=getattr(trade, "direction", ""),
                price=getattr(trade, "price", 0.0),
                volume=getattr(trade, "volume", 0),
                trade_time=DataConverter._parse_time(getattr(trade, "time", "")),
                metadata=DataMetadata(
                    DataCategory.TRANSACTION_DATA,
                    DataSource.VNPY,
                    symbol=trade.symbol,
                    exchange=getattr(trade, "exchange", ""),
                    count=1,
                    last_updated=datetime.now(),
                ),
            )

        except Exception as e:
            logger.error("转换VnPy TradeData失败: %s", e)
            return None

    @staticmethod
    def vnpy_position_to_unified(position: Any) -> Optional[UnifiedPosition]:
        """将VnPy PositionData转换为统一持仓数据."""
        try:
            if not position or not hasattr(position, "symbol"):
                return None

            volume = getattr(position, "volume", 0)
            frozen = getattr(position, "frozen", 0)
            available = max(0, volume - frozen)

            return UnifiedPosition(
                symbol=position.symbol,
                exchange=getattr(position, "exchange", ""),
                direction=getattr(position, "direction", ""),
                volume=volume,
                frozen_volume=frozen,
                available_volume=available,
                cost_price=getattr(position, "price", 0.0),
                market_price=0.0,  # 需要外部提供
                unrealized_pnl=getattr(position, "pnl", 0.0),
                realized_pnl=0.0,  # 需要外部计算
                metadata=DataMetadata(
                    DataCategory.PORTFOLIO_DATA,
                    DataSource.VNPY,
                    symbol=position.symbol,
                    exchange=getattr(position, "exchange", ""),
                    count=1,
                    last_updated=datetime.now(),
                ),
            )

        except Exception as e:
            logger.error("转换VnPy PositionData失败: %s", e)
            return None

    @staticmethod
    def vnpy_account_to_unified(account: Any) -> Optional[UnifiedAccount]:
        """将VnPy AccountData转换为统一账户数据."""
        try:
            if not account or not hasattr(account, "accountid"):
                return None

            balance = getattr(account, "balance", 0.0)
            available = getattr(account, "available", 0.0)
            frozen = balance - available
            close_profit = getattr(account, "close_profit", 0.0)
            position_profit = getattr(account, "position_profit", 0.0)
            total_profit = close_profit + position_profit

            return UnifiedAccount(
                account_id=account.accountid,
                account_type="future",  # 默认期货账户
                balance=balance,
                available=available,
                frozen=frozen,
                commission=getattr(account, "commission", 0.0),
                margin=getattr(account, "margin", 0.0),
                close_profit=close_profit,
                position_profit=position_profit,
                total_profit=total_profit,
                metadata=DataMetadata(
                    DataCategory.PORTFOLIO_DATA,
                    DataSource.VNPY,
                    count=1,
                    last_updated=datetime.now(),
                ),
            )

        except Exception as e:
            logger.error("转换VnPy AccountData失败: %s", e)
            return None

    @staticmethod
    def unified_to_dict(
        data: Union[
            UnifiedMarketData,
            UnifiedOrder,
            UnifiedTrade,
            UnifiedPosition,
            UnifiedAccount,
        ],
    ) -> Dict[str, Any]:
        """将统一数据模型转换为字典."""
        try:
            if isinstance(data, UnifiedMarketData):
                return data.to_pandas_row()
            elif isinstance(
                data, (UnifiedOrder, UnifiedTrade, UnifiedPosition, UnifiedAccount)
            ):
                return {
                    key: value
                    for key, value in data.__dict__.items()
                    if not key.startswith("_")
                }
            else:
                return {}

        except Exception as e:
            logger.error("转换统一数据模型为字典失败: %s", e)
            return {}

    @staticmethod
    def batch_convert_vnpy_data(
        data_list: List[Any], data_type: str
    ) -> List[Dict[str, Any]]:
        """批量转换VnPy数据."""
        try:
            converted_data = []

            for data in data_list:
                unified_data = None

                if data_type == "tick":
                    unified_data = DataConverter.vnpy_tick_to_unified(data)
                elif data_type == "bar":
                    unified_data = DataConverter.vnpy_bar_to_unified(data)
                elif data_type == "order":
                    unified_data = DataConverter.vnpy_order_to_unified(data)
                elif data_type == "trade":
                    unified_data = DataConverter.vnpy_trade_to_unified(data)
                elif data_type == "position":
                    unified_data = DataConverter.vnpy_position_to_unified(data)
                elif data_type == "account":
                    unified_data = DataConverter.vnpy_account_to_unified(data)

                if unified_data:
                    converted_data.append(DataConverter.unified_to_dict(unified_data))

            return converted_data

        except Exception as e:
            logger.error("批量转换VnPy数据失败: %s", e)
            return []

    @staticmethod
    def _parse_time(time_str: str) -> datetime:
        """解析时间字符串."""
        try:
            if not time_str:
                return datetime.now()

            # 尝试不同的时间格式
            time_formats = [
                "%H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%dT%H:%M:%S",
                "%Y-%m-%dT%H:%M:%S.%f",
            ]

            for fmt in time_formats:
                try:
                    return datetime.strptime(time_str, fmt)
                except ValueError:
                    continue

            # 如果都失败，返回当前时间
            return datetime.now()

        except Exception as e:
            logger.error("解析时间字符串失败: %s - %s", time_str, e)
            return datetime.now()

    @staticmethod
    def validate_data_quality(data: Dict[str, Any], data_type: str) -> Dict[str, Any]:
        """验证数据质量."""
        try:
            quality_score = 1.0
            issues = []

            if data_type == "market_data":
                # 验证行情数据质量
                required_fields = ["symbol", "datetime", "close_price"]
                for field in required_fields:
                    if field not in data or data[field] is None:
                        issues.append(f"缺少必需字段: {field}")
                        quality_score -= 0.2

                # 验证价格合理性
                if "close_price" in data and data["close_price"] <= 0:
                    issues.append("价格数据异常")
                    quality_score -= 0.3

            elif data_type == "order":
                # 验证订单数据质量
                required_fields = ["order_id", "symbol", "price", "volume"]
                for field in required_fields:
                    if field not in data or data[field] is None:
                        issues.append(f"缺少必需字段: {field}")
                        quality_score -= 0.2

            elif data_type == "trade":
                # 验证成交数据质量
                required_fields = ["trade_id", "symbol", "price", "volume"]
                for field in required_fields:
                    if field not in data or data[field] is None:
                        issues.append(f"缺少必需字段: {field}")
                        quality_score -= 0.2

            # 确保质量分数在0-1之间
            quality_score = max(0.0, min(1.0, quality_score))

            return {
                "quality_score": quality_score,
                "issues": issues,
                "is_valid": quality_score >= 0.7,
            }

        except Exception as e:
            logger.error("验证数据质量失败: %s", e)
            return {
                "quality_score": 0.0,
                "issues": [f"验证过程出错: {e}"],
                "is_valid": False,
            }


# 导出公共接口
__all__ = ["DataConverter"]
