# -*- coding: utf-8 -*-
"""
图表服务.

提供图表数据获取和配置管理功能。
"""

import logging
from typing import Dict, List, Optional, Any, TYPE_CHECKING
from datetime import datetime, timedelta

from backend.services.base_service import BaseService
from backend.core.models import ChartConfig

if TYPE_CHECKING:
    from backend.services.vnpy_service import VnpyService
    from backend.services.event_service import EventService

logger = logging.getLogger(__name__)


class ChartService(BaseService):
    """图表服务."""

    def __init__(self, vnpy_service: "VnpyService", event_service: "EventService"):
        """初始化图表服务."""
        super().__init__("ChartService")
        self.vnpy_service = vnpy_service
        self.event_service = event_service
        self._chart_configs: Dict[str, ChartConfig] = {}

    async def initialize(self) -> None:
        """初始化图表服务."""
        try:
            self.logger.info("正在初始化图表服务...")

            # 注册事件处理器
            self.event_service.register_handler(
                "market_data_updated", self._handle_market_data_updated
            )

            self.logger.info("图表服务初始化完成")
            self.is_initialized = True

        except Exception as e:
            self.logger.error("图表服务初始化失败: %s", e)
            raise

    async def shutdown(self) -> None:
        """关闭图表服务."""
        try:
            self.logger.info("正在关闭图表服务...")

            # 取消注册事件处理器
            self.event_service.unregister_handler(
                "market_data_updated", self._handle_market_data_updated
            )

            # 清理配置
            self._chart_configs.clear()

            self.logger.info("图表服务关闭完成")
            self.is_initialized = False

        except Exception as e:
            self.logger.error("图表服务关闭失败: %s", e)
            raise

    async def health_check(self) -> Dict[str, Any]:
        """检查图表服务健康状态."""
        try:
            return {
                "service_name": self.service_name,
                "is_initialized": self.is_initialized,
                "chart_configs": len(self._chart_configs),
                "vnpy_service_available": self.vnpy_service.is_initialized,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("图表服务健康检查失败: %s", e)
            return {
                "service_name": self.service_name,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def get_chart_data(
        self,
        symbol: str,
        exchange: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        frequency: str = "1m",
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """获取图表数据."""
        try:
            self.logger.info(
                "获取图表数据: symbol=%s, exchange=%s, frequency=%s, limit=%d",
                symbol,
                exchange,
                frequency,
                limit,
            )

            # 从VnPy获取历史数据
            vnpy_data = self.vnpy_service.get_historical_data(
                symbol=symbol,
                exchange=exchange,
                start_date=start_date,
                end_date=end_date,
                frequency=frequency,
                limit=limit,
            )

            # 转换为图表格式
            chart_data = []
            for bar in vnpy_data:
                chart_data.append(
                    {
                        "timestamp": int(bar.datetime.timestamp() * 1000),
                        "datetime": bar.datetime.isoformat(),
                        "open": float(bar.open_price),
                        "high": float(bar.high_price),
                        "low": float(bar.low_price),
                        "close": float(bar.close_price),
                        "volume": int(bar.volume),
                        "turnover": float(bar.turnover),
                        "open_interest": int(bar.open_interest),
                    }
                )

            self.logger.info("返回图表数据: %d 条记录", len(chart_data))
            return chart_data

        except Exception as e:
            self.logger.error("获取图表数据失败: %s", e)
            raise

    async def get_chart_config(self, symbol: str, exchange: str) -> ChartConfig:
        """获取图表配置."""
        try:
            config_key = f"{symbol}.{exchange}"

            # 检查缓存
            if config_key in self._chart_configs:
                return self._chart_configs[config_key]

            # 获取品种信息
            symbol_info = self.vnpy_service.get_symbol_info(symbol, exchange)
            if not symbol_info:
                raise ValueError(f"品种不存在: {symbol}.{exchange}")

            # 构建图表配置
            chart_config = ChartConfig(
                chart_id=f"{symbol}.{exchange}",
                symbol=symbol,
                exchange=exchange,
                chart_type="kline",
                period="1m",
                indicators=[],
                overlays=[],
                theme="dark",
                auto_refresh=True,
            )

            # 缓存配置
            self._chart_configs[config_key] = chart_config

            self.logger.info("获取图表配置: %s", config_key)
            return chart_config

        except Exception as e:
            self.logger.error("获取图表配置失败: %s", e)
            raise

    async def update_chart_config(
        self, symbol: str, exchange: str, config_updates: Dict[str, Any]
    ) -> ChartConfig:
        """更新图表配置."""
        try:
            config_key = f"{symbol}.{exchange}"

            # 获取现有配置
            chart_config = await self.get_chart_config(symbol, exchange)

            # 更新配置
            for key, value in config_updates.items():
                if hasattr(chart_config, key):
                    setattr(chart_config, key, value)

            # 保存更新后的配置
            self._chart_configs[config_key] = chart_config

            # 发送配置更新事件
            await self.event_service.emit_event(
                "chart_config_updated",
                {
                    "symbol": symbol,
                    "exchange": exchange,
                    "config": chart_config.dict(),
                },
            )

            self.logger.info("图表配置已更新: %s", config_key)
            return chart_config

        except Exception as e:
            self.logger.error("更新图表配置失败: %s", e)
            raise

    async def get_supported_frequencies(self) -> List[Dict[str, Any]]:
        """获取支持的数据频率."""
        try:
            frequencies = [
                {"value": "1s", "label": "1秒", "description": "1秒K线"},
                {"value": "5s", "label": "5秒", "description": "5秒K线"},
                {"value": "10s", "label": "10秒", "description": "10秒K线"},
                {"value": "30s", "label": "30秒", "description": "30秒K线"},
                {"value": "1m", "label": "1分钟", "description": "1分钟K线"},
                {"value": "5m", "label": "5分钟", "description": "5分钟K线"},
                {"value": "15m", "label": "15分钟", "description": "15分钟K线"},
                {"value": "30m", "label": "30分钟", "description": "30分钟K线"},
                {"value": "1h", "label": "1小时", "description": "1小时K线"},
                {"value": "4h", "label": "4小时", "description": "4小时K线"},
                {"value": "1d", "label": "1日", "description": "日K线"},
            ]

            self.logger.info("返回支持的数据频率: %d 个", len(frequencies))
            return frequencies

        except Exception as e:
            self.logger.error("获取支持的数据频率失败: %s", e)
            raise

    async def validate_chart_request(
        self,
        symbol: str,
        exchange: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        frequency: str = "1m",
        limit: int = 1000,
    ) -> Dict[str, Any]:
        """验证图表请求参数."""
        try:
            validation_result = {
                "valid": True,
                "errors": [],
                "warnings": [],
            }

            # 验证品种
            symbol_info = self.vnpy_service.get_symbol_info(symbol, exchange)
            if not symbol_info:
                validation_result["valid"] = False
                validation_result["errors"].append(f"品种不存在: {symbol}.{exchange}")

            # 验证日期范围
            if start_date and end_date:
                if start_date >= end_date:
                    validation_result["valid"] = False
                    validation_result["errors"].append("开始日期必须早于结束日期")

                # 检查日期范围是否过大
                date_range = end_date - start_date
                if date_range.days > 365:
                    validation_result["warnings"].append("日期范围过大，可能影响性能")

            # 验证频率
            supported_frequencies = await self.get_supported_frequencies()
            frequency_values = [f["value"] for f in supported_frequencies]
            if frequency not in frequency_values:
                validation_result["valid"] = False
                validation_result["errors"].append(f"不支持的数据频率: {frequency}")

            # 验证数据量限制
            if limit > 10000:
                validation_result["warnings"].append("数据量过大，建议减少limit参数")

            self.logger.info(
                "图表请求验证完成: valid=%s, errors=%d, warnings=%d",
                validation_result["valid"],
                len(validation_result["errors"]),
                len(validation_result["warnings"]),
            )
            return validation_result

        except Exception as e:
            self.logger.error("验证图表请求失败: %s", e)
            return {
                "valid": False,
                "errors": [f"验证失败: {str(e)}"],
                "warnings": [],
            }

    async def _handle_market_data_updated(self, event: Dict[str, Any]) -> None:
        """处理市场数据更新事件."""
        try:
            data = event.get("data", {})
            symbol = data.get("symbol")
            exchange = data.get("exchange")

            if symbol and exchange:
                config_key = f"{symbol}.{exchange}"
                # 清除相关配置缓存，强制重新获取最新配置
                if config_key in self._chart_configs:
                    del self._chart_configs[config_key]
                    self.logger.info("清除图表配置缓存: %s", config_key)

        except Exception as e:
            self.logger.error("处理市场数据更新事件失败: %s", e)

    def get_cache_statistics(self) -> Dict[str, Any]:
        """获取缓存统计信息."""
        try:
            return {
                "chart_configs_cached": len(self._chart_configs),
                "cache_keys": list(self._chart_configs.keys()),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("获取缓存统计信息失败: %s", e)
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }


# 导出公共接口
__all__ = ["ChartService"]
