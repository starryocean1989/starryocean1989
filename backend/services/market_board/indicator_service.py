# -*- coding: utf-8 -*-
"""
指标服务.

提供技术指标计算和分析功能。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from datetime import datetime

from backend.services.base_service import BaseService
from backend.core.models import IndicatorConfig  # noqa: TC001

if TYPE_CHECKING:
    from backend.services.vnpy_service import VnpyService
    from backend.services.event_service import EventService

logger = logging.getLogger(__name__)


class IndicatorService(BaseService):
    """指标服务."""

    def __init__(self, vnpy_service: "VnpyService", event_service: "EventService"):
        """初始化指标服务."""
        super().__init__("IndicatorService")
        self.vnpy_service = vnpy_service
        self.event_service = event_service
        self._indicator_cache: Dict[str, List[Dict[str, Any]]] = {}

    async def initialize(self) -> None:
        """初始化指标服务."""
        try:
            self.logger.info("正在初始化指标服务...")

            # 注册事件处理器
            self.event_service.register_handler(
                "market_data_updated", self._handle_market_data_updated
            )

            self.logger.info("指标服务初始化完成")
            self.is_initialized = True

        except Exception as e:
            self.logger.error("指标服务初始化失败: %s", e)
            raise

    async def shutdown(self) -> None:
        """关闭指标服务."""
        try:
            self.logger.info("正在关闭指标服务...")

            # 取消注册事件处理器
            self.event_service.unregister_handler(
                "market_data_updated", self._handle_market_data_updated
            )

            # 清理缓存
            self._indicator_cache.clear()

            self.logger.info("指标服务关闭完成")
            self.is_initialized = False

        except Exception as e:
            self.logger.error("指标服务关闭失败: %s", e)
            raise

    async def health_check(self) -> Dict[str, Any]:
        """检查指标服务健康状态."""
        try:
            return {
                "service_name": self.service_name,
                "is_initialized": self.is_initialized,
                "indicator_cache_size": len(self._indicator_cache),
                "vnpy_service_available": self.vnpy_service.is_initialized,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("指标服务健康检查失败: %s", e)
            return {
                "service_name": self.service_name,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def calculate_indicators(
        self,
        symbol: str,
        exchange: str,
        indicator_configs: List[IndicatorConfig],
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        frequency: str = "1m",
        limit: int = 1000,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """计算技术指标."""
        try:
            self.logger.info(
                "计算技术指标: symbol=%s, exchange=%s, indicators=%d",
                symbol,
                exchange,
                len(indicator_configs),
            )

            # 获取历史数据
            vnpy_data = self.vnpy_service.get_historical_data(
                symbol=symbol,
                exchange=exchange,
                start_date=start_date,
                end_date=end_date,
                frequency=frequency,
                limit=limit,
            )

            if not vnpy_data:
                raise ValueError("无历史数据")

            # 计算各个指标
            results = {}
            for indicator_config in indicator_configs:
                indicator_name = indicator_config.name
                cache_key = f"{symbol}.{exchange}.{indicator_name}.{frequency}"

                # 检查缓存
                if cache_key in self._indicator_cache:
                    results[indicator_name] = self._indicator_cache[cache_key]
                    continue

                # 计算指标
                indicator_values = await self._calculate_single_indicator(
                    vnpy_data, indicator_config
                )

                # 缓存结果
                self._indicator_cache[cache_key] = indicator_values
                results[indicator_name] = indicator_values

            # 发送指标计算完成事件
            await self.event_service.emit_event(
                "indicators_calculated",
                {
                    "symbol": symbol,
                    "exchange": exchange,
                    "indicators": [config.name for config in indicator_configs],
                },
            )

            self.logger.info("技术指标计算完成: %d 个指标", len(results))
            return results

        except Exception as e:
            self.logger.error("计算技术指标失败: %s", e)
            raise

    async def _calculate_single_indicator(
        self, vnpy_data: List, indicator_config: IndicatorConfig
    ) -> List[Dict[str, Any]]:
        """计算单个指标."""
        try:
            indicator_name = indicator_config.name
            parameters = indicator_config.parameters

            if indicator_name == "MA":
                return await self._calculate_ma(vnpy_data, parameters)
            elif indicator_name == "EMA":
                return await self._calculate_ema(vnpy_data, parameters)
            elif indicator_name == "MACD":
                return await self._calculate_macd(vnpy_data, parameters)
            elif indicator_name == "RSI":
                return await self._calculate_rsi(vnpy_data, parameters)
            elif indicator_name == "KDJ":
                return await self._calculate_kdj(vnpy_data, parameters)
            else:
                raise ValueError(f"不支持的指标: {indicator_name}")

        except Exception as e:
            self.logger.error("计算指标失败: %s, %s", indicator_name, e)
            raise

    async def _calculate_ma(
        self, vnpy_data: List, parameters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """计算移动平均线."""
        period = parameters.get("period", 20)
        ma_values = []

        for i in range(len(vnpy_data)):
            if i < period - 1:
                ma_values.append(
                    {
                        "timestamp": int(vnpy_data[i].datetime.timestamp() * 1000),
                        "datetime": vnpy_data[i].datetime.isoformat(),
                        "value": None,
                        "indicator_name": "MA",
                        "parameters": parameters,
                    }
                )
            else:
                ma_value = (
                    sum(vnpy_data[j].close_price for j in range(i - period + 1, i + 1)) / period
                )
                ma_values.append(
                    {
                        "timestamp": int(vnpy_data[i].datetime.timestamp() * 1000),
                        "datetime": vnpy_data[i].datetime.isoformat(),
                        "value": float(ma_value),
                        "indicator_name": "MA",
                        "parameters": parameters,
                    }
                )

        return ma_values

    async def _calculate_ema(
        self, vnpy_data: List, parameters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """计算指数移动平均线."""
        period = parameters.get("period", 12)
        alpha = 2 / (period + 1)
        ema_values = []

        for i in range(len(vnpy_data)):
            if i == 0:
                ema_value = vnpy_data[i].close_price
            else:
                ema_value = (
                    alpha * vnpy_data[i].close_price + (1 - alpha) * ema_values[i - 1]["value"]
                )

            ema_values.append(
                {
                    "timestamp": int(vnpy_data[i].datetime.timestamp() * 1000),
                    "datetime": vnpy_data[i].datetime.isoformat(),
                    "value": float(ema_value),
                    "indicator_name": "EMA",
                    "parameters": parameters,
                }
            )

        return ema_values

    async def _calculate_macd(
        self, vnpy_data: List, parameters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """计算MACD指标."""
        fast_period = parameters.get("fast_period", 12)
        slow_period = parameters.get("slow_period", 26)
        signal_period = parameters.get("signal_period", 9)

        # 计算快速和慢速EMA
        fast_alpha = 2 / (fast_period + 1)
        slow_alpha = 2 / (slow_period + 1)

        fast_ema = []
        slow_ema = []
        macd_line = []
        signal_line = []
        histogram = []

        for i in range(len(vnpy_data)):
            # 计算快速EMA
            if i == 0:
                fast_ema.append(vnpy_data[i].close_price)
            else:
                fast_ema.append(
                    fast_alpha * vnpy_data[i].close_price + (1 - fast_alpha) * fast_ema[i - 1]
                )

            # 计算慢速EMA
            if i == 0:
                slow_ema.append(vnpy_data[i].close_price)
            else:
                slow_ema.append(
                    slow_alpha * vnpy_data[i].close_price + (1 - slow_alpha) * slow_ema[i - 1]
                )

            # 计算MACD线
            macd_line.append(fast_ema[i] - slow_ema[i])

        # 计算信号线
        signal_alpha = 2 / (signal_period + 1)
        for i in range(len(macd_line)):
            if i == 0:
                signal_line.append(macd_line[i])
            else:
                signal_line.append(
                    signal_alpha * macd_line[i] + (1 - signal_alpha) * signal_line[i - 1]
                )

        # 计算柱状图
        for i in range(len(macd_line)):
            histogram.append(macd_line[i] - signal_line[i])

        # 构建结果
        macd_values = []
        for i in range(len(vnpy_data)):
            macd_values.append(
                {
                    "timestamp": int(vnpy_data[i].datetime.timestamp() * 1000),
                    "datetime": vnpy_data[i].datetime.isoformat(),
                    "macd": float(macd_line[i]),
                    "signal": float(signal_line[i]),
                    "histogram": float(histogram[i]),
                    "indicator_name": "MACD",
                    "parameters": parameters,
                }
            )

        return macd_values

    async def _calculate_rsi(
        self, vnpy_data: List, parameters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """计算RSI指标."""
        period = parameters.get("period", 14)
        rsi_values = []

        # 计算价格变化
        price_changes = []
        for i in range(1, len(vnpy_data)):
            price_changes.append(vnpy_data[i].close_price - vnpy_data[i - 1].close_price)

        for i in range(len(vnpy_data)):
            if i < period:
                rsi_values.append(
                    {
                        "timestamp": int(vnpy_data[i].datetime.timestamp() * 1000),
                        "datetime": vnpy_data[i].datetime.isoformat(),
                        "value": None,
                        "indicator_name": "RSI",
                        "parameters": parameters,
                    }
                )
            else:
                # 计算指定期间内的平均涨幅和跌幅
                gains = [change for change in price_changes[i - period : i] if change > 0]
                losses = [-change for change in price_changes[i - period : i] if change < 0]

                avg_gain = sum(gains) / period if gains else 0
                avg_loss = sum(losses) / period if losses else 0

                if avg_loss == 0:
                    rsi = 100
                else:
                    rs = avg_gain / avg_loss
                    rsi = 100 - (100 / (1 + rs))

                rsi_values.append(
                    {
                        "timestamp": int(vnpy_data[i].datetime.timestamp() * 1000),
                        "datetime": vnpy_data[i].datetime.isoformat(),
                        "value": float(rsi),
                        "indicator_name": "RSI",
                        "parameters": parameters,
                    }
                )

        return rsi_values

    async def _calculate_kdj(
        self, vnpy_data: List, parameters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """计算KDJ指标."""
        k_period = parameters.get("k_period", 9)
        d_period = parameters.get("d_period", 3)

        k_values = []
        d_values = []
        j_values = []

        for i in range(len(vnpy_data)):
            if i < k_period - 1:
                k_values.append(None)
                d_values.append(None)
                j_values.append(None)
            else:
                # 计算指定期间内的最高价和最低价
                period_high = max(vnpy_data[j].high_price for j in range(i - k_period + 1, i + 1))
                period_low = min(vnpy_data[j].low_price for j in range(i - k_period + 1, i + 1))

                if period_high == period_low:
                    k_value = 50
                else:
                    k_value = (
                        (vnpy_data[i].close_price - period_low) / (period_high - period_low) * 100
                    )

                k_values.append(k_value)

                # 计算D值（K值的移动平均）
                if len(k_values) < d_period:
                    d_values.append(None)
                else:
                    valid_k_values = [k for k in k_values[-d_period:] if k is not None]
                    if valid_k_values:
                        d_value = sum(valid_k_values) / len(valid_k_values)
                    else:
                        d_value = None
                    d_values.append(d_value)

                # 计算J值
                if k_value is not None and d_values[-1] is not None:
                    j_value = 3 * k_value - 2 * d_values[-1]
                else:
                    j_value = None
                j_values.append(j_value)

        # 构建结果
        kdj_values = []
        for i in range(len(vnpy_data)):
            kdj_values.append(
                {
                    "timestamp": int(vnpy_data[i].datetime.timestamp() * 1000),
                    "datetime": vnpy_data[i].datetime.isoformat(),
                    "k": float(k_values[i]) if k_values[i] is not None else None,
                    "d": float(d_values[i]) if d_values[i] is not None else None,
                    "j": float(j_values[i]) if j_values[i] is not None else None,
                    "indicator_name": "KDJ",
                    "parameters": parameters,
                }
            )

        return kdj_values

    async def get_supported_indicators(self) -> List[Dict[str, Any]]:
        """获取支持的指标列表."""
        try:
            indicators = [
                {
                    "name": "MA",
                    "display_name": "移动平均线",
                    "description": "简单移动平均线",
                    "parameters": [
                        {
                            "name": "period",
                            "type": "int",
                            "default": 20,
                            "min": 1,
                            "max": 200,
                            "description": "计算周期",
                        }
                    ],
                    "outputs": ["value"],
                },
                {
                    "name": "EMA",
                    "display_name": "指数移动平均线",
                    "description": "指数移动平均线",
                    "parameters": [
                        {
                            "name": "period",
                            "type": "int",
                            "default": 12,
                            "min": 1,
                            "max": 200,
                            "description": "计算周期",
                        }
                    ],
                    "outputs": ["value"],
                },
                {
                    "name": "MACD",
                    "display_name": "MACD指标",
                    "description": "移动平均收敛散度",
                    "parameters": [
                        {
                            "name": "fast_period",
                            "type": "int",
                            "default": 12,
                            "min": 1,
                            "max": 100,
                            "description": "快速EMA周期",
                        },
                        {
                            "name": "slow_period",
                            "type": "int",
                            "default": 26,
                            "min": 1,
                            "max": 100,
                            "description": "慢速EMA周期",
                        },
                        {
                            "name": "signal_period",
                            "type": "int",
                            "default": 9,
                            "min": 1,
                            "max": 50,
                            "description": "信号线周期",
                        },
                    ],
                    "outputs": ["macd", "signal", "histogram"],
                },
                {
                    "name": "RSI",
                    "display_name": "RSI指标",
                    "description": "相对强弱指数",
                    "parameters": [
                        {
                            "name": "period",
                            "type": "int",
                            "default": 14,
                            "min": 1,
                            "max": 100,
                            "description": "计算周期",
                        }
                    ],
                    "outputs": ["value"],
                },
                {
                    "name": "KDJ",
                    "display_name": "KDJ指标",
                    "description": "随机指标",
                    "parameters": [
                        {
                            "name": "k_period",
                            "type": "int",
                            "default": 9,
                            "min": 1,
                            "max": 50,
                            "description": "K值周期",
                        },
                        {
                            "name": "d_period",
                            "type": "int",
                            "default": 3,
                            "min": 1,
                            "max": 20,
                            "description": "D值周期",
                        },
                        {
                            "name": "j_period",
                            "type": "int",
                            "default": 3,
                            "min": 1,
                            "max": 20,
                            "description": "J值周期",
                        },
                    ],
                    "outputs": ["k", "d", "j"],
                },
            ]

            self.logger.info("返回支持的指标列表: %d 个指标", len(indicators))
            return indicators

        except Exception as e:
            self.logger.error("获取支持的指标列表失败: %s", e)
            raise

    async def _handle_market_data_updated(self, event: Dict[str, Any]) -> None:
        """处理市场数据更新事件."""
        try:
            data = event.get("data", {})
            symbol = data.get("symbol")
            exchange = data.get("exchange")

            if symbol and exchange:
                # 清除相关指标缓存
                keys_to_remove = [
                    key
                    for key in self._indicator_cache.keys()
                    if key.startswith(f"{symbol}.{exchange}")
                ]
                for key in keys_to_remove:
                    del self._indicator_cache[key]

                if keys_to_remove:
                    self.logger.info("清除指标缓存: %d 个", len(keys_to_remove))

        except Exception as e:
            self.logger.error("处理市场数据更新事件失败: %s", e)

    def get_cache_statistics(self) -> Dict[str, Any]:
        """获取缓存统计信息."""
        try:
            return {
                "indicator_cache_size": len(self._indicator_cache),
                "cache_keys": list(self._indicator_cache.keys()),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("获取缓存统计信息失败: %s", e)
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }


# 导出公共接口
__all__ = ["IndicatorService"]
