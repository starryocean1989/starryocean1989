# -*- coding: utf-8 -*-
"""
数据融合服务.

提供多数据源数据融合和清洗功能。
"""

import logging
from typing import Dict, List, Optional, TYPE_CHECKING, Any
from datetime import datetime, timedelta

from backend.services.base_service import BaseService

if TYPE_CHECKING:
    from backend.services.vnpy_service import VnpyService
    from backend.services.event_service import EventService

logger = logging.getLogger(__name__)


class DataFusionService(BaseService):
    """数据融合服务."""

    def __init__(self, vnpy_service: "VnpyService", event_service: "EventService"):
        """初始化数据融合服务."""
        super().__init__("DataFusionService")
        self.vnpy_service = vnpy_service
        self.event_service = event_service
        self._fusion_cache: Dict[str, List[Dict[str, Any]]] = {}

    async def initialize(self) -> None:
        """初始化数据融合服务."""
        try:
            self.logger.info("正在初始化数据融合服务...")

            # 注册事件处理器
            self.event_service.register_handler(
                "market_data_updated", self._handle_market_data_updated
            )

            self.logger.info("数据融合服务初始化完成")
            self.is_initialized = True

        except Exception as e:
            self.logger.error("数据融合服务初始化失败: %s", e)
            raise

    async def shutdown(self) -> None:
        """关闭数据融合服务."""
        try:
            self.logger.info("正在关闭数据融合服务...")

            # 取消注册事件处理器
            self.event_service.unregister_handler(
                "market_data_updated", self._handle_market_data_updated
            )

            # 清理缓存
            self._fusion_cache.clear()

            self.logger.info("数据融合服务关闭完成")
            self.is_initialized = False

        except Exception as e:
            self.logger.error("数据融合服务关闭失败: %s", e)
            raise

    async def health_check(self) -> Dict[str, Any]:
        """检查数据融合服务健康状态."""
        try:
            return {
                "service_name": self.service_name,
                "is_initialized": self.is_initialized,
                "fusion_cache_size": len(self._fusion_cache),
                "vnpy_service_available": self.vnpy_service.is_initialized,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("数据融合服务健康检查失败: %s", e)
            return {
                "service_name": self.service_name,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def fuse_market_data(
        self,
        symbol: str,
        exchange: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        frequency: str = "1m",
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """融合市场数据."""
        try:
            self.logger.info(
                "融合市场数据: symbol=%s, exchange=%s, frequency=%s",
                symbol,
                exchange,
                frequency,
            )

            # 生成缓存键
            cache_key = f"{symbol}.{exchange}.{frequency}"
            
            # 检查缓存
            if cache_key in self._fusion_cache:
                cached_data = self._fusion_cache[cache_key]
                self.logger.info("从缓存获取融合数据: %s, %d 条", cache_key, len(cached_data))
                return cached_data

            # 从多个数据源获取数据
            data_sources = await self._get_available_data_sources(symbol, exchange)
            
            if not data_sources:
                self.logger.warning("无可用数据源: %s.%s", symbol, exchange)
                return []

            # 融合数据
            fused_data = await self._perform_data_fusion(
                data_sources, symbol, exchange, start_date, end_date, frequency, limit
            )

            # 数据清洗
            cleaned_data = await self._clean_data(fused_data)

            # 缓存结果
            self._fusion_cache[cache_key] = cleaned_data

            self.logger.info("数据融合完成: %s.%s, %d 条记录", symbol, exchange, len(cleaned_data))
            return cleaned_data

        except Exception as e:
            self.logger.error("数据融合失败: %s", e)
            raise

    async def _get_available_data_sources(
        self, symbol: str, exchange: str
    ) -> List[str]:
        """获取可用的数据源."""
        try:
            # 这里应该从数据源服务获取可用数据源
            # 暂时返回模拟数据源
            available_sources = ["vnpy_local", "tushare", "akshare"]
            
            self.logger.info(
                "获取可用数据源: %s.%s, %d 个数据源",
                symbol,
                exchange,
                len(available_sources),
            )
            return available_sources

        except Exception as e:
            self.logger.error("获取可用数据源失败: %s", e)
            return []

    async def _perform_data_fusion(
        self,
        data_sources: List[str],
        symbol: str,
        exchange: str,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        frequency: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """执行数据融合."""
        try:
            all_data = []

            for source in data_sources:
                try:
                    # 从不同数据源获取数据
                    source_data = await self._fetch_from_source(
                        source, symbol, exchange, start_date, end_date, frequency, limit
                    )
                    
                    if source_data:
                        # 添加数据源标识
                        for data_point in source_data:
                            data_point["source"] = source
                        
                        all_data.extend(source_data)
                        self.logger.info(
                            "从数据源 %s 获取数据: %d 条", source, len(source_data)
                        )

                except Exception as e:
                    self.logger.warning("从数据源 %s 获取数据失败: %s", source, e)
                    continue

            # 按时间排序
            all_data.sort(key=lambda x: x.get("timestamp", 0))

            # 去重和合并
            fused_data = await self._merge_data_by_timestamp(all_data)

            self.logger.info("数据融合完成: %d 条原始数据 -> %d 条融合数据", len(all_data), len(fused_data))
            return fused_data

        except Exception as e:
            self.logger.error("执行数据融合失败: %s", e)
            raise

    async def _fetch_from_source(
        self,
        source: str,
        symbol: str,
        exchange: str,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        frequency: str,
        limit: int,
    ) -> List[Dict[str, Any]]:
        """从指定数据源获取数据."""
        try:
            if source == "vnpy_local":
                # 从VnPy本地数据库获取数据
                vnpy_data = self.vnpy_service.get_historical_data(
                    symbol=symbol,
                    exchange=exchange,
                    start_date=start_date,
                    end_date=end_date,
                    frequency=frequency,
                    limit=limit,
                )

                data = []
                for bar in vnpy_data:
                    data.append({
                        "timestamp": int(bar.datetime.timestamp() * 1000),
                        "datetime": bar.datetime.isoformat(),
                        "open": float(bar.open_price),
                        "high": float(bar.high_price),
                        "low": float(bar.low_price),
                        "close": float(bar.close_price),
                        "volume": int(bar.volume),
                        "turnover": float(bar.turnover),
                        "open_interest": int(bar.open_interest),
                        "source": source,
                    })

                return data

            else:
                # 其他数据源的处理
                self.logger.warning("暂不支持的数据源: %s", source)
                return []

        except Exception as e:
            self.logger.error("从数据源 %s 获取数据失败: %s", source, e)
            return []

    async def _merge_data_by_timestamp(self, all_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按时间戳合并数据."""
        try:
            if not all_data:
                return []

            # 按时间戳分组
            timestamp_groups = {}
            for data_point in all_data:
                timestamp = data_point.get("timestamp")
                if timestamp:
                    if timestamp not in timestamp_groups:
                        timestamp_groups[timestamp] = []
                    timestamp_groups[timestamp].append(data_point)

            # 合并每个时间戳的数据
            merged_data = []
            for timestamp, group_data in timestamp_groups.items():
                merged_point = await self._merge_data_points(group_data)
                merged_data.append(merged_point)

            # 重新排序
            merged_data.sort(key=lambda x: x.get("timestamp", 0))

            return merged_data

        except Exception as e:
            self.logger.error("按时间戳合并数据失败: %s", e)
            return all_data

    async def _merge_data_points(self, data_points: List[Dict[str, Any]]) -> Dict[str, Any]:
        """合并数据点."""
        try:
            if len(data_points) == 1:
                return data_points[0]

            # 选择最可靠的数据源
            priority_sources = ["vnpy_local", "tushare", "akshare"]
            
            for source in priority_sources:
                for data_point in data_points:
                    if data_point.get("source") == source:
                        # 添加数据源信息
                        data_point["merged_sources"] = [dp.get("source") for dp in data_points]
                        return data_point

            # 如果都不匹配，返回第一个
            result = data_points[0]
            result["merged_sources"] = [dp.get("source") for dp in data_points]
            return result

        except Exception as e:
            self.logger.error("合并数据点失败: %s", e)
            return data_points[0] if data_points else {}

    async def _clean_data(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """清洗数据."""
        try:
            if not data:
                return []

            cleaned_data = []
            
            for data_point in data:
                # 检查数据完整性
                if await self._validate_data_point(data_point):
                    # 数据修复
                    cleaned_point = await self._repair_data_point(data_point)
                    cleaned_data.append(cleaned_point)
                else:
                    self.logger.warning("跳过无效数据点: %s", data_point.get("datetime"))

            self.logger.info("数据清洗完成: %d 条原始数据 -> %d 条清洗后数据", len(data), len(cleaned_data))
            return cleaned_data

        except Exception as e:
            self.logger.error("数据清洗失败: %s", e)
            return data

    async def _validate_data_point(self, data_point: Dict[str, Any]) -> bool:
        """验证数据点."""
        try:
            # 检查必需字段
            required_fields = ["timestamp", "datetime", "open", "high", "low", "close", "volume"]
            for field in required_fields:
                if field not in data_point or data_point[field] is None:
                    return False

            # 检查价格合理性
            open_price = float(data_point["open"])
            high_price = float(data_point["high"])
            low_price = float(data_point["low"])
            close_price = float(data_point["close"])
            volume = int(data_point["volume"])

            if open_price <= 0 or high_price <= 0 or low_price <= 0 or close_price <= 0:
                return False

            if volume < 0:
                return False

            # 检查OHLC关系
            if high_price < max(open_price, close_price) or low_price > min(open_price, close_price):
                return False

            return True

        except (ValueError, TypeError):
            return False

    async def _repair_data_point(self, data_point: Dict[str, Any]) -> Dict[str, Any]:
        """修复数据点."""
        try:
            repaired_point = data_point.copy()

            # 修复价格精度
            for price_field in ["open", "high", "low", "close"]:
                if price_field in repaired_point:
                    repaired_point[price_field] = round(float(repaired_point[price_field]), 2)

            # 修复成交量
            if "volume" in repaired_point:
                repaired_point["volume"] = int(repaired_point["volume"])

            # 修复成交额
            if "turnover" in repaired_point and repaired_point["turnover"]:
                repaired_point["turnover"] = round(float(repaired_point["turnover"]), 2)

            # 修复持仓量
            if "open_interest" in repaired_point and repaired_point["open_interest"]:
                repaired_point["open_interest"] = int(repaired_point["open_interest"])

            return repaired_point

        except Exception as e:
            self.logger.error("修复数据点失败: %s", e)
            return data_point

    async def _handle_market_data_updated(self, event: Dict[str, Any]) -> None:
        """处理市场数据更新事件."""
        try:
            data = event.get("data", {})
            symbol = data.get("symbol")
            exchange = data.get("exchange")
            frequency = data.get("frequency", "1m")

            if symbol and exchange:
                # 清除相关缓存
                cache_key = f"{symbol}.{exchange}.{frequency}"
                if cache_key in self._fusion_cache:
                    del self._fusion_cache[cache_key]
                    self.logger.info("清除融合数据缓存: %s", cache_key)

        except Exception as e:
            self.logger.error("处理市场数据更新事件失败: %s", e)

    def get_cache_statistics(self) -> Dict[str, Any]:
        """获取缓存统计信息."""
        try:
            return {
                "fusion_cache_size": len(self._fusion_cache),
                "cache_keys": list(self._fusion_cache.keys()),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("获取缓存统计信息失败: %s", e)
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }


# 导出公共接口
__all__ = ["DataFusionService"]
