# -*- coding: utf-8 -*-
"""
数据库验证工具.

提供VnPy数据库和终端数据库的验证功能。
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.database import BaseDatabase

logger = logging.getLogger(__name__)


class VnPyDBHelper:
    """VnPy数据库验证工具."""

    def __init__(self, database: BaseDatabase):
        """初始化数据库助手."""
        self.database = database
        self.logger = logging.getLogger(self.__class__.__name__)

    def count_bars(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> int:
        """
        统计Bar数据条数.

        Args:
            symbol: 品种代码
            exchange: 交易所
            interval: 时间周期
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            数据条数
        """
        try:
            bars = self.database.load_bar_data(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start=start_date,
                end=end_date,
            )

            count = len(bars)
            self.logger.info(
                f"统计Bar数据: {symbol}.{exchange.value}, " f"周期={interval.value}, 数量={count}"
            )
            return count

        except Exception as e:
            self.logger.error(f"统计Bar数据失败: {e}")
            return 0

    def verify_data_format(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        limit: int = 10,
    ) -> Dict[str, Any]:
        """
        验证数据格式完整性.

        Args:
            symbol: 品种代码
            exchange: 交易所
            interval: 时间周期
            limit: 验证数据条数

        Returns:
            验证结果字典
        """
        try:
            bars = self.database.load_bar_data(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start=None,
                end=None,
            )

            if not bars:
                return {
                    "valid": False,
                    "error": "没有数据",
                    "count": 0,
                }

            # 验证前limit条数据
            check_bars = bars[:limit] if len(bars) > limit else bars

            # 检查必需字段
            required_fields = [
                "datetime",
                "open_price",
                "high_price",
                "low_price",
                "close_price",
                "volume",
            ]
            missing_fields = []

            for bar in check_bars:
                for field in required_fields:
                    if not hasattr(bar, field):
                        missing_fields.append(field)
                        break

            # 检查数据有效性
            invalid_count = 0
            for bar in check_bars:
                # 检查价格是否为正数
                if bar.open_price <= 0 or bar.close_price <= 0:
                    invalid_count += 1
                # 检查high >= low
                if bar.high_price < bar.low_price:
                    invalid_count += 1

            result = {
                "valid": len(missing_fields) == 0 and invalid_count == 0,
                "total_count": len(bars),
                "checked_count": len(check_bars),
                "missing_fields": missing_fields,
                "invalid_count": invalid_count,
                "sample_data": {
                    "datetime": str(check_bars[0].datetime) if check_bars else None,
                    "open": check_bars[0].open_price if check_bars else None,
                    "high": check_bars[0].high_price if check_bars else None,
                    "low": check_bars[0].low_price if check_bars else None,
                    "close": check_bars[0].close_price if check_bars else None,
                    "volume": check_bars[0].volume if check_bars else None,
                },
            }

            self.logger.info(f"数据格式验证: {symbol}.{exchange.value}, 结果={result['valid']}")
            return result

        except Exception as e:
            self.logger.error(f"验证数据格式失败: {e}")
            return {
                "valid": False,
                "error": str(e),
                "count": 0,
            }

    def get_data_date_range(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
    ) -> Dict[str, Optional[datetime]]:
        """
        获取数据的日期范围.

        Args:
            symbol: 品种代码
            exchange: 交易所
            interval: 时间周期

        Returns:
            包含start_date和end_date的字典
        """
        try:
            bars = self.database.load_bar_data(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start=None,
                end=None,
            )

            if not bars:
                return {"start_date": None, "end_date": None}

            start_date = bars[0].datetime
            end_date = bars[-1].datetime

            self.logger.info(
                f"数据日期范围: {symbol}.{exchange.value}, " f"{start_date} ~ {end_date}"
            )

            return {
                "start_date": start_date,
                "end_date": end_date,
            }

        except Exception as e:
            self.logger.error(f"获取数据日期范围失败: {e}")
            return {"start_date": None, "end_date": None}

    def clear_test_data(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
    ) -> bool:
        """
        清理测试数据.

        Args:
            symbol: 品种代码
            exchange: 交易所
            interval: 时间周期

        Returns:
            是否成功
        """
        try:
            # VnPy的BaseDatabase没有提供删除接口
            # 这里仅记录日志，实际清理需要在测试前后手动处理
            self.logger.warning(
                f"清理测试数据: {symbol}.{exchange.value}, " f"周期={interval.value} (需要手动清理)"
            )
            return True

        except Exception as e:
            self.logger.error(f"清理测试数据失败: {e}")
            return False

    def detect_data_quality(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
    ) -> Dict[str, Any]:
        """
        检测数据质量.

        Args:
            symbol: 品种代码
            exchange: 交易所
            interval: 时间周期

        Returns:
            数据质量报告字典
        """
        try:
            bars = self.database.load_bar_data(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start=None,
                end=None,
            )

            if not bars:
                return {
                    "quality_score": 0.0,
                    "total_count": 0,
                    "issues": ["没有数据"],
                }

            # 检测问题
            issues = []
            duplicate_count = 0
            gap_count = 0
            invalid_price_count = 0
            zero_volume_count = 0

            # 检查重复数据
            datetime_set = set()
            for bar in bars:
                if bar.datetime in datetime_set:
                    duplicate_count += 1
                datetime_set.add(bar.datetime)

            if duplicate_count > 0:
                issues.append(f"重复数据: {duplicate_count}条")

            # 检查数据断点
            for i in range(1, len(bars)):
                time_diff = (bars[i].datetime - bars[i - 1].datetime).total_seconds()
                expected_diff = self._get_expected_interval_seconds(interval)
                if time_diff > expected_diff * 2:  # 允许2倍偏差
                    gap_count += 1

            if gap_count > 0:
                issues.append(f"数据断点: {gap_count}个")

            # 检查价格有效性
            for bar in bars:
                if bar.open_price <= 0 or bar.close_price <= 0:
                    invalid_price_count += 1
                if bar.high_price < bar.low_price:
                    invalid_price_count += 1

            if invalid_price_count > 0:
                issues.append(f"无效价格: {invalid_price_count}条")

            # 检查成交量
            for bar in bars:
                if bar.volume == 0:
                    zero_volume_count += 1

            if zero_volume_count > len(bars) * 0.5:  # 超过50%
                issues.append(f"零成交量: {zero_volume_count}条")

            # 计算质量分数
            total_issues = duplicate_count + gap_count + invalid_price_count
            quality_score = max(0.0, 1.0 - (total_issues / len(bars)))

            result = {
                "quality_score": quality_score,
                "total_count": len(bars),
                "duplicate_count": duplicate_count,
                "gap_count": gap_count,
                "invalid_price_count": invalid_price_count,
                "zero_volume_count": zero_volume_count,
                "issues": issues if issues else ["无"],
            }

            self.logger.info(
                f"数据质量检测: {symbol}.{exchange.value}, " f"质量分数={quality_score:.2%}"
            )
            return result

        except Exception as e:
            self.logger.error(f"数据质量检测失败: {e}")
            return {
                "quality_score": 0.0,
                "total_count": 0,
                "error": str(e),
            }

    def identify_missing_data(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        expected_start: datetime,
        expected_end: datetime,
    ) -> Dict[str, Any]:
        """
        识别缺失的数据.

        Args:
            symbol: 品种代码
            exchange: 交易所
            interval: 时间周期
            expected_start: 期望开始时间
            expected_end: 期望结束时间

        Returns:
            缺失数据报告字典
        """
        try:
            bars = self.database.load_bar_data(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start=expected_start,
                end=expected_end,
            )

            if not bars:
                return {
                    "has_missing": True,
                    "missing_ranges": [(expected_start, expected_end)],
                    "completeness": 0.0,
                }

            # 计算期望的数据点数量
            expected_count = self._calculate_expected_bars(expected_start, expected_end, interval)
            actual_count = len(bars)
            completeness = min(1.0, actual_count / expected_count) if expected_count > 0 else 0.0

            # 检测缺失范围
            missing_ranges = []
            interval_seconds = self._get_expected_interval_seconds(interval)

            for i in range(1, len(bars)):
                time_diff = (bars[i].datetime - bars[i - 1].datetime).total_seconds()
                if time_diff > interval_seconds * 2:  # 检测断点
                    missing_ranges.append((bars[i - 1].datetime, bars[i].datetime))

            result = {
                "has_missing": len(missing_ranges) > 0 or completeness < 0.95,
                "expected_count": expected_count,
                "actual_count": actual_count,
                "completeness": completeness,
                "missing_ranges": missing_ranges[:10],  # 最多返回10个
                "missing_range_count": len(missing_ranges),
            }

            self.logger.info(
                f"缺失数据识别: {symbol}.{exchange.value}, " f"完整度={completeness:.2%}"
            )
            return result

        except Exception as e:
            self.logger.error(f"缺失数据识别失败: {e}")
            return {
                "has_missing": True,
                "error": str(e),
            }

    def _get_expected_interval_seconds(self, interval: Interval) -> int:
        """获取时间周期对应的秒数."""
        interval_map = {
            Interval.MINUTE: 60,
            Interval.MINUTE_5: 300,
            Interval.MINUTE_15: 900,
            Interval.MINUTE_30: 1800,
            Interval.HOUR: 3600,
            Interval.DAILY: 86400,
        }
        return interval_map.get(interval, 60)

    def _calculate_expected_bars(
        self,
        start: datetime,
        end: datetime,
        interval: Interval,
    ) -> int:
        """计算期望的Bar数量（简化版）."""
        total_seconds = (end - start).total_seconds()
        interval_seconds = self._get_expected_interval_seconds(interval)
        # 简化计算，不考虑交易时间
        expected = int(total_seconds / interval_seconds)
        return max(1, expected)

    # ========== 数据质量检查扩展方法 ==========

    def check_data_completeness(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        start_date: datetime,
        end_date: datetime,
    ) -> Dict[str, Any]:
        """检查数据完整性."""
        try:
            bars = self.database.load_bar_data(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start=start_date,
                end=end_date,
            )

            expected_count = self._calculate_expected_bars(start_date, end_date, interval)
            actual_count = len(bars)
            missing_count = max(0, expected_count - actual_count)
            completeness_score = actual_count / expected_count if expected_count > 0 else 0.0

            return {
                "expected_count": expected_count,
                "actual_count": actual_count,
                "missing_count": missing_count,
                "completeness_score": completeness_score,
            }
        except Exception as e:
            self.logger.error(f"检查数据完整性失败: {e}")
            return {
                "expected_count": 0,
                "actual_count": 0,
                "missing_count": 0,
                "completeness_score": 0.0,
                "error": str(e),
            }

    def check_field_completeness(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
    ) -> Dict[str, float]:
        """检查OHLCV字段完整性."""
        try:
            bars = self.database.load_bar_data(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start=None,
                end=None,
            )

            if not bars:
                return {
                    "open": 0.0,
                    "high": 0.0,
                    "low": 0.0,
                    "close": 0.0,
                    "volume": 0.0,
                }

            total_count = len(bars)
            field_valid_counts = {
                "open": 0,
                "high": 0,
                "low": 0,
                "close": 0,
                "volume": 0,
            }

            for bar in bars:
                if bar.open_price > 0:
                    field_valid_counts["open"] += 1
                if bar.high_price > 0:
                    field_valid_counts["high"] += 1
                if bar.low_price > 0:
                    field_valid_counts["low"] += 1
                if bar.close_price > 0:
                    field_valid_counts["close"] += 1
                if bar.volume >= 0:
                    field_valid_counts["volume"] += 1

            return {field: count / total_count for field, count in field_valid_counts.items()}

        except Exception as e:
            self.logger.error(f"检查字段完整性失败: {e}")
            return {
                "open": 0.0,
                "high": 0.0,
                "low": 0.0,
                "close": 0.0,
                "volume": 0.0,
                "error": str(e),
            }

    def check_data_accuracy(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
    ) -> Dict[str, Any]:
        """检查数据准确性."""
        try:
            bars = self.database.load_bar_data(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start=None,
                end=None,
            )

            if not bars:
                return {
                    "price_anomalies": 0,
                    "ohlc_errors": 0,
                    "volume_anomalies": 0,
                    "timestamp_errors": 0,
                    "accuracy_score": 0.0,
                }

            price_anomalies = 0
            ohlc_errors = 0
            volume_anomalies = 0
            timestamp_errors = 0
            anomaly_details = []

            for bar in bars:
                # 检查价格范围
                if bar.open_price <= 0 or bar.close_price <= 0:
                    price_anomalies += 1
                    anomaly_details.append(f"负价格: {bar.datetime}")

                # 检查OHLC关系
                if bar.high_price < bar.open_price or bar.high_price < bar.close_price:
                    ohlc_errors += 1
                    anomaly_details.append(f"OHLC关系错误: {bar.datetime}")
                if bar.low_price > bar.open_price or bar.low_price > bar.close_price:
                    ohlc_errors += 1

                # 检查成交量
                if bar.volume < 0:
                    volume_anomalies += 1

                # 检查时间戳
                if bar.datetime is None:
                    timestamp_errors += 1

            total_issues = price_anomalies + ohlc_errors + volume_anomalies + timestamp_errors
            accuracy_score = max(0.0, 1.0 - (total_issues / len(bars)))

            return {
                "price_anomalies": price_anomalies,
                "ohlc_errors": ohlc_errors,
                "volume_anomalies": volume_anomalies,
                "timestamp_errors": timestamp_errors,
                "accuracy_score": accuracy_score,
                "anomaly_details": anomaly_details[:10],
            }

        except Exception as e:
            self.logger.error(f"检查数据准确性失败: {e}")
            return {
                "price_anomalies": 0,
                "ohlc_errors": 0,
                "volume_anomalies": 0,
                "timestamp_errors": 0,
                "accuracy_score": 0.0,
                "error": str(e),
            }

    def check_data_consistency(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
    ) -> Dict[str, Any]:
        """检查数据一致性."""
        try:
            bars = self.database.load_bar_data(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start=None,
                end=None,
            )

            if not bars:
                return {
                    "time_order_errors": 0,
                    "duplicate_count": 0,
                    "trading_hour_errors": 0,
                    "consistency_score": 0.0,
                }

            time_order_errors = 0
            duplicate_count = 0
            trading_hour_errors = 0
            datetime_set = set()
            duplicate_details = []

            for i, bar in enumerate(bars):
                # 检查时间序列单调性
                if i > 0 and bar.datetime <= bars[i - 1].datetime:
                    time_order_errors += 1

                # 检查重复数据
                if bar.datetime in datetime_set:
                    duplicate_count += 1
                    duplicate_details.append(str(bar.datetime))
                datetime_set.add(bar.datetime)

                # 检查交易时段（简化：只检查小时）
                hour = bar.datetime.hour
                if hour < 9 or hour > 15:  # A股交易时间大致范围
                    trading_hour_errors += 1

            total_issues = time_order_errors + duplicate_count
            consistency_score = max(0.0, 1.0 - (total_issues / len(bars)))

            return {
                "time_order_errors": time_order_errors,
                "duplicate_count": duplicate_count,
                "duplicate_details": duplicate_details[:10],
                "trading_hour_errors": trading_hour_errors,
                "consistency_score": consistency_score,
            }

        except Exception as e:
            self.logger.error(f"检查数据一致性失败: {e}")
            return {
                "time_order_errors": 0,
                "duplicate_count": 0,
                "trading_hour_errors": 0,
                "consistency_score": 0.0,
                "error": str(e),
            }

    def generate_quality_report(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        include_details: bool = False,
    ) -> Dict[str, Any]:
        """生成数据质量报告."""
        try:
            bars = self.database.load_bar_data(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start=None,
                end=None,
            )

            if not bars:
                return {
                    "overall_quality_score": 0.0,
                    "dimension_scores": {
                        "completeness": 0.0,
                        "accuracy": 0.0,
                        "consistency": 0.0,
                        "timeliness": 0.0,
                    },
                    "issues": ["没有数据"],
                    "recommendations": ["需要下载数据"],
                }

            # 获取各维度评分
            completeness_check = self.detect_data_quality(symbol, exchange, interval)
            accuracy_check = self.check_data_accuracy(symbol, exchange, interval)
            consistency_check = self.check_data_consistency(symbol, exchange, interval)

            completeness_score = completeness_check.get("quality_score", 0.0)
            accuracy_score = accuracy_check.get("accuracy_score", 0.0)
            consistency_score = consistency_check.get("consistency_score", 0.0)
            timeliness_score = 1.0  # 简化：假设时效性良好

            # 计算综合质量分数
            overall_score = (
                completeness_score * 0.3
                + accuracy_score * 0.3
                + consistency_score * 0.3
                + timeliness_score * 0.1
            )

            # 收集问题
            issues = []
            issues.extend(completeness_check.get("issues", []))
            if accuracy_check.get("price_anomalies", 0) > 0:
                issues.append(f"价格异常: {accuracy_check['price_anomalies']}条")
            if consistency_check.get("duplicate_count", 0) > 0:
                issues.append(f"重复数据: {consistency_check['duplicate_count']}条")

            # 生成修复建议
            recommendations = []
            if completeness_score < 0.95:
                recommendations.append("建议执行增量数据下载以补全缺失数据")
            if accuracy_score < 0.95:
                recommendations.append("建议执行数据清洗以修复异常数据")
            if consistency_score < 0.95:
                recommendations.append("建议检查并清除重复数据")

            date_range = self.get_data_date_range(symbol, exchange, interval)

            return {
                "overall_quality_score": overall_score,
                "dimension_scores": {
                    "completeness": completeness_score,
                    "accuracy": accuracy_score,
                    "consistency": consistency_score,
                    "timeliness": timeliness_score,
                },
                "issues": issues if issues else ["无"],
                "recommendations": recommendations if recommendations else ["数据质量良好"],
                "generated_at": datetime.now().isoformat(),
                "data_time_range": f"{date_range['start_date']} ~ {date_range['end_date']}",
                "sample_size": len(bars),
            }

        except Exception as e:
            self.logger.error(f"生成质量报告失败: {e}")
            return {
                "overall_quality_score": 0.0,
                "error": str(e),
            }

    def generate_repair_plan(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
        issues: List[str],
    ) -> Dict[str, Any]:
        """生成修复计划."""
        try:
            # 分析问题类型
            has_gaps = any("断点" in issue or "缺失" in issue for issue in issues)
            has_duplicates = any("重复" in issue for issue in issues)
            has_anomalies = any("异常" in issue or "无效" in issue for issue in issues)

            # 确定修复策略
            if has_gaps:
                strategy = "incremental_download"
            elif has_duplicates:
                strategy = "deduplication"
            elif has_anomalies:
                strategy = "data_cleaning"
            else:
                strategy = "full_download"

            # 确定修复时间范围
            from datetime import timedelta

            date_range = self.get_data_date_range(symbol, exchange, interval)
            if date_range["start_date"]:
                time_range = {
                    "start": date_range["start_date"],
                    "end": datetime.now(),
                }
            else:
                time_range = {
                    "start": datetime.now() - timedelta(days=7),
                    "end": datetime.now(),
                }

            return {
                "strategy": strategy,
                "time_range": time_range,
                "estimated_duration": "30-60秒",
                "priority": "high" if len(issues) > 3 else "medium",
            }

        except Exception as e:
            self.logger.error(f"生成修复计划失败: {e}")
            return {
                "strategy": "manual_check",
                "error": str(e),
            }

    def create_data_snapshot(
        self,
        symbol: str,
        exchange: Exchange,
        interval: Interval,
    ) -> Dict[str, Any]:
        """创建数据快照."""
        try:
            bars = self.database.load_bar_data(
                symbol=symbol,
                exchange=exchange,
                interval=interval,
                start=None,
                end=None,
            )

            quality_result = self.detect_data_quality(symbol, exchange, interval)

            return {
                "timestamp": datetime.now().isoformat(),
                "total_records": len(bars),
                "quality_score": quality_result.get("quality_score", 0.0),
                "missing_count": 0,  # 简化
                "anomaly_count": quality_result.get("invalid_price_count", 0),
            }

        except Exception as e:
            self.logger.error(f"创建数据快照失败: {e}")
            return {
                "timestamp": datetime.now().isoformat(),
                "total_records": 0,
                "error": str(e),
            }


# 导出公共接口
__all__ = ["VnPyDBHelper"]
