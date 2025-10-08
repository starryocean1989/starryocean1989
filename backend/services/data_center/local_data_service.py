# -*- coding: utf-8 -*-
"""
本地数据服务.

提供本地数据查询和管理相关的业务逻辑。
"""

import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from datetime import datetime, timedelta

from backend.services.base_service import BaseService
from backend.core.models import UnifiedMarketData

if TYPE_CHECKING:
    from backend.services.vnpy_service import VnpyService
    from backend.services.event_service import EventService

logger = logging.getLogger(__name__)


class LocalDataService(BaseService):
    """本地数据服务."""

    def __init__(self, vnpy_service: "VnpyService", event_service: "EventService"):
        """初始化本地数据服务."""
        super().__init__("LocalDataService")
        self.vnpy_service = vnpy_service
        self.event_service = event_service
        self._data_cache: Dict[str, List[UnifiedMarketData]] = {}
        self._cache_ttl = 300  # 缓存5分钟

    async def initialize(self) -> None:
        """初始化本地数据服务."""
        try:
            self.logger.info("正在初始化本地数据服务...")

            # 注册事件处理器
            self.event_service.register_handler(
                "market_data_updated", self._handle_market_data_updated
            )

            self.logger.info("本地数据服务初始化完成")
            self.is_initialized = True

        except Exception as e:
            self.logger.error("本地数据服务初始化失败: %s", e)
            raise

    async def shutdown(self) -> None:
        """关闭本地数据服务."""
        try:
            self.logger.info("正在关闭本地数据服务...")

            # 取消注册事件处理器
            self.event_service.unregister_handler(
                "market_data_updated", self._handle_market_data_updated
            )

            # 清理缓存
            self._data_cache.clear()

            self.logger.info("本地数据服务关闭完成")
            self.is_initialized = False

        except Exception as e:
            self.logger.error("本地数据服务关闭失败: %s", e)
            raise

    async def health_check(self) -> Dict[str, Any]:
        """检查本地数据服务健康状态."""
        try:
            return {
                "service_name": self.service_name,
                "is_initialized": self.is_initialized,
                "cache_size": len(self._data_cache),
                "cache_keys": list(self._data_cache.keys()),
                "vnpy_service_available": self.vnpy_service.is_initialized,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("本地数据服务健康检查失败: %s", e)
            return {
                "service_name": self.service_name,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def get_market_data(
        self,
        symbol: str,
        exchange: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        data_type: str = "bar",
        frequency: str = "1m",
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """获取市场数据."""
        try:
            # 生成缓存键
            cache_key = f"{symbol}.{exchange}.{data_type}.{frequency}"

            # 检查缓存
            if cache_key in self._data_cache:
                cached_data = self._data_cache[cache_key]
                self.logger.info("从缓存获取市场数据: %s, %d 条", cache_key, len(cached_data))
                return [data.to_pandas_row() for data in cached_data]

            # 从VnPy获取数据
            market_data = await self._fetch_from_vnpy(
                symbol, exchange, start_date, end_date, data_type, frequency, limit
            )

            # 缓存数据
            self._data_cache[cache_key] = market_data

            # 转换为字典格式
            data_dicts = [data.to_pandas_row() for data in market_data]

            self.logger.info("获取市场数据: %s.%s, %d 条", symbol, exchange, len(data_dicts))
            return data_dicts

        except Exception as e:
            self.logger.error("获取市场数据失败: %s", e)
            raise

    async def get_tick_data(
        self,
        symbol: str,
        exchange: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """获取Tick数据."""
        try:
            return await self.get_market_data(
                symbol, exchange, start_date, end_date, "tick", "1s", limit
            )

        except Exception as e:
            self.logger.error("获取Tick数据失败: %s", e)
            raise

    async def get_bar_data(
        self,
        symbol: str,
        exchange: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        frequency: str = "1m",
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """获取K线数据."""
        try:
            return await self.get_market_data(
                symbol, exchange, start_date, end_date, "bar", frequency, limit
            )

        except Exception as e:
            self.logger.error("获取K线数据失败: %s", e)
            raise

    async def get_latest_data(
        self,
        symbol: str,
        exchange: str,
        data_type: str = "tick",
    ) -> Optional[Dict[str, Any]]:
        """获取最新数据."""
        try:
            # 从缓存获取最新数据
            cache_key = f"{symbol}.{exchange}.{data_type}"
            if cache_key in self._data_cache:
                cached_data = self._data_cache[cache_key]
                if cached_data:
                    latest = cached_data[-1]
                    self.logger.info("获取最新数据: %s.%s", symbol, exchange)
                    return latest.to_pandas_row()

            # 从VnPy获取最新数据
            latest_data = await self._fetch_latest_from_vnpy(symbol, exchange, data_type)

            if latest_data:
                self.logger.info("获取最新数据: %s.%s", symbol, exchange)
                return latest_data.to_pandas_row()

            return None

        except Exception as e:
            self.logger.error("获取最新数据失败: %s", e)
            raise

    async def search_data_gaps(
        self,
        symbol: str,
        exchange: str,
        start_date: datetime,
        end_date: datetime,
        frequency: str = "1m",
    ) -> List[Dict[str, Any]]:
        """搜索数据断点."""
        try:
            # 获取数据
            data = await self.get_bar_data(symbol, exchange, start_date, end_date, frequency)

            if not data:
                return []

            # 分析数据断点
            gaps = []
            expected_interval = self._get_frequency_seconds(frequency)

            for i in range(1, len(data)):
                prev_time = datetime.fromisoformat(data[i - 1]["datetime"].replace("Z", "+00:00"))
                curr_time = datetime.fromisoformat(data[i]["datetime"].replace("Z", "+00:00"))

                time_diff = (curr_time - prev_time).total_seconds()

                if time_diff > expected_interval * 1.5:  # 允许50%的误差
                    gap_info = {
                        "symbol": symbol,
                        "exchange": exchange,
                        "gap_start": prev_time.isoformat(),
                        "gap_end": curr_time.isoformat(),
                        "gap_type": "missing_data",
                        "severity": "medium",
                        "suggested_action": "下载缺失数据",
                        "duration_seconds": time_diff,
                        "expected_interval": expected_interval,
                    }
                    gaps.append(gap_info)

            self.logger.info("搜索数据断点: %s.%s, %d 个断点", symbol, exchange, len(gaps))
            return gaps

        except Exception as e:
            self.logger.error("搜索数据断点失败: %s", e)
            raise

    async def get_data_statistics(
        self,
        symbol: str,
        exchange: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """获取数据统计信息."""
        try:
            # 获取数据
            data = await self.get_bar_data(symbol, exchange, start_date, end_date)

            if not data:
                return {
                    "symbol": symbol,
                    "exchange": exchange,
                    "total_records": 0,
                    "start_date": None,
                    "end_date": None,
                    "price_range": {"min": 0, "max": 0},
                    "volume_total": 0,
                    "turnover_total": 0,
                }

            # 计算统计信息
            prices = [record["close_price"] for record in data if record["close_price"] > 0]
            volumes = [record["volume"] for record in data if record["volume"] > 0]
            turnovers = [record["turnover"] for record in data if record["turnover"] > 0]

            stats = {
                "symbol": symbol,
                "exchange": exchange,
                "total_records": len(data),
                "start_date": data[0]["datetime"] if data else None,
                "end_date": data[-1]["datetime"] if data else None,
                "price_range": {
                    "min": min(prices) if prices else 0,
                    "max": max(prices) if prices else 0,
                    "avg": sum(prices) / len(prices) if prices else 0,
                },
                "volume_total": sum(volumes),
                "volume_avg": sum(volumes) / len(volumes) if volumes else 0,
                "turnover_total": sum(turnovers),
                "turnover_avg": sum(turnovers) / len(turnovers) if turnovers else 0,
            }

            self.logger.info("获取数据统计信息: %s.%s", symbol, exchange)
            return stats

        except Exception as e:
            self.logger.error("获取数据统计信息失败: %s", e)
            raise

    async def _fetch_from_vnpy(
        self,
        symbol: str,
        exchange: str,
        start_date: Optional[datetime],
        end_date: Optional[datetime],
        data_type: str,
        frequency: str,
        limit: int,
    ) -> List[UnifiedMarketData]:
        """从VnPy获取数据."""
        try:
            if not self.vnpy_service or not self.vnpy_service.is_initialized:
                raise RuntimeError("VnPy服务未初始化")

            # 获取VnPy数据库管理器
            database_manager = self.vnpy_service.get_database_manager()
            if not database_manager:
                raise ConnectionError("无法获取VnPy数据库管理器")

            if not start_date:
                start_date = datetime.now() - timedelta(days=1)
            if not end_date:
                end_date = datetime.now()

            # 映射频率到VnPy的Interval
            interval_map = {
                "1s": "1s",
                "1m": "1m",
                "5m": "5m",
                "15m": "15m",
                "30m": "30m",
                "1h": "1h",
                "1d": "d",
            }
            vnpy_interval = interval_map.get(frequency, "1m")

            # 从VnPy数据库获取bar数据
            bars = database_manager.load_bar_data(
                symbol=symbol,
                exchange=exchange,
                interval=vnpy_interval,
                start=start_date,
                end=end_date,
            )

            if not bars:
                raise ValueError(f"未找到品种 {symbol}.{exchange} 的{data_type}数据")

            # 转换为UnifiedMarketData格式
            result = []
            for bar in bars[:limit]:
                market_data = UnifiedMarketData(
                    symbol=symbol,
                    exchange=exchange,
                    data_type=data_type,
                    datetime=bar.datetime,
                    timestamp=int(bar.datetime.timestamp()),
                    open_price=bar.open_price,
                    high_price=bar.high_price,
                    low_price=bar.low_price,
                    close_price=bar.close_price,
                    pre_close=getattr(bar, "pre_close", 0),
                    volume=bar.volume,
                    turnover=getattr(bar, "turnover", 0),
                    open_interest=getattr(bar, "open_interest", 0),
                )
                result.append(market_data)

            self.logger.info("从VnPy获取数据: %s.%s, %d 条", symbol, exchange, len(result))
            return result

        except Exception as e:
            self.logger.error("从VnPy获取数据失败: %s", e)
            raise

    async def _fetch_latest_from_vnpy(
        self,
        symbol: str,
        exchange: str,
        data_type: str,
    ) -> Optional[UnifiedMarketData]:
        """从VnPy获取最新数据."""
        try:
            if not self.vnpy_service or not self.vnpy_service.is_initialized:
                raise RuntimeError("VnPy服务未初始化")

            # 获取VnPy数据库管理器
            database_manager = self.vnpy_service.get_database_manager()
            if not database_manager:
                raise ConnectionError("无法获取VnPy数据库管理器")

            # 获取最新的一条bar数据
            end_date = datetime.now()
            start_date = end_date - timedelta(days=1)  # 查询最近1天的数据

            bars = database_manager.load_bar_data(
                symbol=symbol, exchange=exchange, interval="1m", start=start_date, end=end_date
            )

            if not bars:
                raise ValueError(f"未找到品种 {symbol}.{exchange} 的最新数据")

            # 取最后一条数据
            latest_bar = bars[-1]

            latest_data = UnifiedMarketData(
                symbol=symbol,
                exchange=exchange,
                data_type=data_type,
                datetime=latest_bar.datetime,
                timestamp=int(latest_bar.datetime.timestamp()),
                open_price=latest_bar.open_price,
                high_price=latest_bar.high_price,
                low_price=latest_bar.low_price,
                close_price=latest_bar.close_price,
                pre_close=getattr(latest_bar, "pre_close", 0),
                volume=latest_bar.volume,
                turnover=getattr(latest_bar, "turnover", 0),
                open_interest=getattr(latest_bar, "open_interest", 0),
            )

            self.logger.info("从VnPy获取最新数据: %s.%s", symbol, exchange)
            return latest_data

        except Exception as e:
            self.logger.error("从VnPy获取最新数据失败: %s", e)
            raise

    def _get_frequency_seconds(self, frequency: str) -> int:
        """获取频率对应的秒数."""
        frequency_map = {
            "1s": 1,
            "5s": 5,
            "10s": 10,
            "30s": 30,
            "1m": 60,
            "5m": 300,
            "15m": 900,
            "30m": 1800,
            "1h": 3600,
            "4h": 14400,
            "1d": 86400,
        }
        return frequency_map.get(frequency, 60)

    async def _handle_market_data_updated(self, event: Dict[str, Any]) -> None:
        """处理市场数据更新事件."""
        try:
            data = event.get("data", {})
            symbol = data.get("symbol")
            exchange = data.get("exchange")
            data_type = data.get("data_type")

            if symbol and exchange and data_type:
                # 清除相关缓存
                cache_key = f"{symbol}.{exchange}.{data_type}"
                if cache_key in self._data_cache:
                    del self._data_cache[cache_key]
                    self.logger.info("清除数据缓存: %s", cache_key)

        except Exception as e:
            self.logger.error("处理市场数据更新事件失败: %s", e)

    def clear_cache(self, symbol: Optional[str] = None, exchange: Optional[str] = None) -> int:
        """清理缓存."""
        try:
            if symbol and exchange:
                # 清理指定品种的缓存
                keys_to_remove = [
                    key for key in self._data_cache if key.startswith(f"{symbol}.{exchange}")
                ]
                for key in keys_to_remove:
                    del self._data_cache[key]

                self.logger.info(
                    "清理指定品种缓存: %s.%s, %d 个",
                    symbol,
                    exchange,
                    len(keys_to_remove),
                )
                return len(keys_to_remove)
            else:
                # 清理所有缓存
                cache_size = len(self._data_cache)
                self._data_cache.clear()
                self.logger.info("清理所有数据缓存: %d 个", cache_size)
                return cache_size

        except Exception as e:
            self.logger.error("清理缓存失败: %s", e)
            return 0

    def get_cache_statistics(self) -> Dict[str, Any]:
        """获取缓存统计信息."""
        try:
            return {
                "cache_size": len(self._data_cache),
                "cache_keys": list(self._data_cache.keys()),
                "cache_ttl": self._cache_ttl,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("获取缓存统计信息失败: %s", e)
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }


# 导出公共接口
__all__ = ["LocalDataService"]
