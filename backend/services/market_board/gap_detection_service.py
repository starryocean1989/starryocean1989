# -*- coding: utf-8 -*-
"""
断点检测服务.

提供数据断点检测和分析功能。
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List
from datetime import datetime

from backend.services.base_service import BaseService
from backend.core.models import GapInfo

if TYPE_CHECKING:
    from backend.services.vnpy_service import VnpyService
    from backend.services.event_service import EventService

logger = logging.getLogger(__name__)


class GapDetectionService(BaseService):
    """断点检测服务."""

    def __init__(self, vnpy_service: "VnpyService", event_service: "EventService"):
        """初始化断点检测服务."""
        super().__init__("GapDetectionService")
        self.vnpy_service = vnpy_service
        self.event_service = event_service
        self._gap_cache: Dict[str, List[GapInfo]] = {}

    async def initialize(self) -> None:
        """初始化断点检测服务."""
        try:
            self.logger.info("正在初始化断点检测服务...")

            # 注册事件处理器
            self.event_service.register_handler(
                "market_data_updated", self._handle_market_data_updated
            )

            self.logger.info("断点检测服务初始化完成")
            self.is_initialized = True

        except Exception as e:
            self.logger.error("断点检测服务初始化失败: %s", e)
            raise

    async def shutdown(self) -> None:
        """关闭断点检测服务."""
        try:
            self.logger.info("正在关闭断点检测服务...")

            # 取消注册事件处理器
            self.event_service.unregister_handler(
                "market_data_updated", self._handle_market_data_updated
            )

            # 清理缓存
            self._gap_cache.clear()

            self.logger.info("断点检测服务关闭完成")
            self.is_initialized = False

        except Exception as e:
            self.logger.error("断点检测服务关闭失败: %s", e)
            raise

    async def health_check(self) -> Dict[str, Any]:
        """检查断点检测服务健康状态."""
        try:
            return {
                "service_name": self.service_name,
                "is_initialized": self.is_initialized,
                "gap_cache_size": len(self._gap_cache),
                "vnpy_service_available": self.vnpy_service.is_initialized,
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("断点检测服务健康检查失败: %s", e)
            return {
                "service_name": self.service_name,
                "status": "error",
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }

    async def detect_gaps(
        self,
        symbol: str,
        exchange: str,
        start_date: datetime,
        end_date: datetime,
        frequency: str = "1m",
    ) -> List[GapInfo]:
        """检测数据断点."""
        try:
            self.logger.info(
                "检测数据断点: symbol=%s, exchange=%s, frequency=%s, start_date=%s, end_date=%s",
                symbol,
                exchange,
                frequency,
                start_date,
                end_date,
            )

            # 生成缓存键
            cache_key = f"{symbol}.{exchange}.{frequency}.{start_date.date()}.{end_date.date()}"

            # 检查缓存
            if cache_key in self._gap_cache:
                cached_gaps = self._gap_cache[cache_key]
                self.logger.info(
                    "从缓存获取断点检测结果: %s, %d 个断点", cache_key, len(cached_gaps)
                )
                return cached_gaps

            # 获取历史数据
            vnpy_data = self.vnpy_service.get_historical_data(
                symbol=symbol,
                exchange=exchange,
                start_date=start_date,
                end_date=end_date,
                frequency=frequency,
            )

            if not vnpy_data:
                self.logger.warning("无历史数据，无法检测断点: %s.%s", symbol, exchange)
                return []

            # 检测断点
            gaps = await self._analyze_data_gaps(vnpy_data, symbol, exchange, frequency)

            # 缓存结果
            self._gap_cache[cache_key] = gaps

            # 发送断点检测完成事件
            await self.event_service.emit_event(
                "gaps_detected",
                {
                    "symbol": symbol,
                    "exchange": exchange,
                    "frequency": frequency,
                    "gap_count": len(gaps),
                    "timestamp": datetime.now().isoformat(),
                },
            )

            self.logger.info("断点检测完成: %s.%s, %d 个断点", symbol, exchange, len(gaps))
            return gaps

        except Exception as e:
            self.logger.error("检测数据断点失败: %s", e)
            raise

    async def _analyze_data_gaps(
        self, vnpy_data: List, symbol: str, exchange: str, frequency: str
    ) -> List[GapInfo]:
        """分析数据断点."""
        try:
            gaps = []
            expected_interval = self._get_frequency_seconds(frequency)

            for i in range(1, len(vnpy_data)):
                prev_time = vnpy_data[i - 1].datetime
                curr_time = vnpy_data[i].datetime
                time_diff = (curr_time - prev_time).total_seconds()

                # 检查是否超出预期间隔
                if time_diff > expected_interval * 1.5:  # 允许50%的误差
                    gap_info = GapInfo(
                        symbol=symbol,
                        exchange=exchange,
                        gap_start=prev_time,
                        gap_end=curr_time,
                        gap_type=self._classify_gap_type(time_diff, expected_interval),
                        severity=self._assess_gap_severity(time_diff, expected_interval),
                        suggested_action=self._get_suggested_action(time_diff, expected_interval),
                    )
                    gaps.append(gap_info)

            return gaps

        except Exception as e:
            self.logger.error("分析数据断点失败: %s", e)
            return []

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

    def _classify_gap_type(self, time_diff: float, expected_interval: int) -> str:
        """分类断点类型."""
        try:
            ratio = time_diff / expected_interval

            if ratio <= 2:
                return "minor_gap"
            elif ratio <= 10:
                return "missing_data"
            elif ratio <= 100:
                return "major_gap"
            else:
                return "data_loss"

        except Exception:
            return "unknown"

    def _assess_gap_severity(self, time_diff: float, expected_interval: int) -> str:
        """评估断点严重程度."""
        try:
            ratio = time_diff / expected_interval

            if ratio <= 2:
                return "low"
            elif ratio <= 10:
                return "medium"
            elif ratio <= 100:
                return "high"
            else:
                return "critical"

        except Exception:
            return "unknown"

    def _get_suggested_action(self, time_diff: float, expected_interval: int) -> str:
        """获取建议操作."""
        try:
            ratio = time_diff / expected_interval

            if ratio <= 2:
                return "忽略小断点"
            elif ratio <= 10:
                return "检查数据源连接"
            elif ratio <= 100:
                return "重新下载缺失数据"
            else:
                return "联系技术支持"

        except Exception:
            return "未知操作"

    async def get_gap_statistics(
        self,
        symbol: str,
        exchange: str,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """获取断点统计信息."""
        try:
            # 检测所有频率的断点
            frequencies = ["1m", "5m", "15m", "30m", "1h", "1d"]
            all_gaps = []

            for frequency in frequencies:
                gaps = await self.detect_gaps(symbol, exchange, start_date, end_date, frequency)
                all_gaps.extend(gaps)

            # 统计信息
            total_gaps = len(all_gaps)
            gap_types = {}
            gap_severities = {}
            total_missing_time = 0

            for gap in all_gaps:
                # 统计类型
                gap_type = gap.gap_type
                gap_types[gap_type] = gap_types.get(gap_type, 0) + 1

                # 统计严重程度
                severity = gap.severity
                gap_severities[severity] = gap_severities.get(severity, 0) + 1

                # 累计缺失时间
                total_missing_time += (gap.gap_end - gap.gap_start).total_seconds()

            stats = {
                "symbol": symbol,
                "exchange": exchange,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "total_gaps": total_gaps,
                "gap_types": gap_types,
                "gap_severities": gap_severities,
                "total_missing_time_seconds": total_missing_time,
                "total_missing_time_hours": total_missing_time / 3600,
                "data_completeness": await self._calculate_completeness(
                    start_date, end_date, all_gaps
                ),
                "timestamp": datetime.now().isoformat(),
            }

            self.logger.info("获取断点统计信息: %s.%s, %d 个断点", symbol, exchange, total_gaps)
            return stats

        except Exception as e:
            self.logger.error("获取断点统计信息失败: %s", e)
            raise

    async def _calculate_completeness(
        self,
        start_date: datetime,
        end_date: datetime,
        gaps: List[GapInfo],
    ) -> float:
        """计算数据完整性."""
        try:
            # 计算总时间跨度
            total_span = (end_date - start_date).total_seconds()

            # 计算缺失时间
            missing_time = sum((gap.gap_end - gap.gap_start).total_seconds() for gap in gaps)

            # 计算完整性百分比
            completeness = max(0, (total_span - missing_time) / total_span * 100)

            return round(completeness, 2)

        except Exception as e:
            self.logger.error("计算数据完整性失败: %s", e)
            return 0.0

    async def auto_fix_gaps(
        self,
        symbol: str,
        exchange: str,
        start_date: datetime,
        end_date: datetime,
        frequency: str = "1m",
        severity_threshold: str = "medium",
    ) -> Dict[str, Any]:
        """自动修复断点."""
        try:
            self.logger.info(
                "自动修复断点: symbol=%s, exchange=%s, frequency=%s, severity=%s",
                symbol,
                exchange,
                frequency,
                severity_threshold,
            )

            # 检测断点
            gaps = await self.detect_gaps(symbol, exchange, start_date, end_date, frequency)

            # 筛选需要修复的断点
            severity_levels = {"low": 1, "medium": 2, "high": 3, "critical": 4}
            threshold_level = severity_levels.get(severity_threshold, 2)

            fixable_gaps = [
                gap for gap in gaps if severity_levels.get(gap.severity, 0) >= threshold_level
            ]

            # 执行修复
            fixed_count = 0
            failed_count = 0

            for gap in fixable_gaps:
                try:
                    # 发送下载任务
                    await self.event_service.emit_event(
                        "auto_download_gap_data",
                        {
                            "symbol": symbol,
                            "exchange": exchange,
                            "start_date": gap.gap_start,
                            "end_date": gap.gap_end,
                            "frequency": frequency,
                            "gap_id": f"{gap.gap_start}_{gap.gap_end}",
                        },
                    )
                    fixed_count += 1

                except Exception as e:
                    self.logger.error("修复断点失败: %s, %s", gap.gap_start, e)
                    failed_count += 1

            result = {
                "symbol": symbol,
                "exchange": exchange,
                "frequency": frequency,
                "total_gaps": len(gaps),
                "fixable_gaps": len(fixable_gaps),
                "fixed_count": fixed_count,
                "failed_count": failed_count,
                "timestamp": datetime.now().isoformat(),
            }

            self.logger.info("自动修复断点完成: %s.%s, 修复 %d 个", symbol, exchange, fixed_count)
            return result

        except Exception as e:
            self.logger.error("自动修复断点失败: %s", e)
            raise

    async def _handle_market_data_updated(self, event: Dict[str, Any]) -> None:
        """处理市场数据更新事件."""
        try:
            data = event.get("data", {})
            symbol = data.get("symbol")
            exchange = data.get("exchange")
            frequency = data.get("frequency", "1m")

            if symbol and exchange:
                # 清除相关缓存
                keys_to_remove = [
                    key
                    for key in self._gap_cache.keys()
                    if key.startswith(f"{symbol}.{exchange}.{frequency}")
                ]
                for key in keys_to_remove:
                    del self._gap_cache[key]

                if keys_to_remove:
                    self.logger.info("清除断点检测缓存: %d 个", len(keys_to_remove))

        except Exception as e:
            self.logger.error("处理市场数据更新事件失败: %s", e)

    def get_cache_statistics(self) -> Dict[str, Any]:
        """获取缓存统计信息."""
        try:
            return {
                "gap_cache_size": len(self._gap_cache),
                "cache_keys": list(self._gap_cache.keys()),
                "timestamp": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("获取缓存统计信息失败: %s", e)
            return {
                "error": str(e),
                "timestamp": datetime.now().isoformat(),
            }


# 导出公共接口
__all__ = ["GapDetectionService"]
