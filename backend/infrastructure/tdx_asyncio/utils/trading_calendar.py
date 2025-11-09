# -*- coding: utf-8 -*-
"""
异步交易日历系统模块

提供中国股票市场交易日历功能，完全异步化实现。
现使用 pandas_market_calendars 作为底层实现（支持1990年至今的完整历史数据）

核心功能：
- 基于 pandas_market_calendars 的中国A股交易日历（1990年至今）
- 异步接口（保持原有API兼容性）
- 缓存机制（24小时刷新）
- 便捷的交易日判断函数

作者：[项目名称]
版本：5.0 - 使用 pandas_market_calendars 重构，支持完整历史数据
"""

import asyncio
import atexit
from contextlib import contextmanager, redirect_stdout
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Optional, cast
import os
import sys
from io import StringIO

import calendar
import importlib.resources

try:
    from native_calendar import NativeCalendar  # type: ignore[import]
except ImportError:  # pragma: no cover - 回退路径
    NativeCalendar = None  # type: ignore[assignment]

import pandas as pd
import pandas_market_calendars as mcal

from .logger import logger


def _suppress_native_calendar_stdout() -> None:
    """过滤native_calendar扩展的标准输出."""

    original_write = getattr(sys.stdout, "write", None)
    if original_write is None:
        return
    if getattr(original_write, "__native_calendar_filter__", False):  # type: ignore[attr-defined]
        return

    def filtered_write(data: str) -> int:
        stripped = data.strip()
        if stripped in {"NativeCalendar constructed", "NativeCalendar destructed"}:
            return len(data)
        return original_write(data)  # type: ignore[misc]

    setattr(filtered_write, "__native_calendar_filter__", True)  # type: ignore[attr-defined]
    sys.stdout.write = filtered_write  # type: ignore[assignment]


@contextmanager
def _suppress_native_calendar_fd():
    """临时将底层stdout重定向到空设备，屏蔽C++扩展的stdout."""

    try:
        fd = sys.stdout.fileno()
    except (AttributeError, ValueError, OSError):
        yield
        return

    sys.stdout.flush()
    saved_fd = os.dup(fd)
    try:
        with open(os.devnull, "w") as devnull:
            os.dup2(devnull.fileno(), fd)
        yield
    finally:
        try:
            os.dup2(saved_fd, fd)
        finally:
            os.close(saved_fd)


class TradingCalendar:
    """
    交易日历管理器

    使用 native_calendar C++ 扩展作为底层实现，提供高性能的中国A股交易日历查询。
    """

    def __init__(self, cache_dir: Optional[str] = None):
        """
        初始化交易日历

        :param cache_dir: 缓存目录（此版本中未使用，但为保持兼容性而保留）
        """
        self._native_calendar = None
        self._fallback_enabled = False

        if NativeCalendar is not None:
            try:
                _suppress_native_calendar_stdout()
                with importlib.resources.path('native_calendar', 'sse_calendar.bin') as bitmap_path:
                    self._bitmap_path = str(bitmap_path)

                if not os.path.exists(self._bitmap_path):
                    raise FileNotFoundError(f"交易日历位图文件未找到: {self._bitmap_path}")

                with _suppress_native_calendar_fd():
                    with redirect_stdout(StringIO()):
                        self._native_calendar = NativeCalendar(1990, self._bitmap_path)

                def _cleanup_native_calendar() -> None:
                    if self._native_calendar is not None:
                        with _suppress_native_calendar_fd():
                            self._native_calendar = None

                atexit.register(_cleanup_native_calendar)
                logger.debug(
                    "✓ 交易日历初始化完成 (native_calendar C++ 扩展, 数据源: %s)",
                    self._bitmap_path,
                )
            except Exception as exc:  # pragma: no cover - 回退路径
                logger.warning(
                    "native_calendar 加载失败，将启用纯 Python 交易日历: %s",
                    exc,
                    exc_info=True,
                )
                self._native_calendar = None
                self._fallback_enabled = True
        else:
            logger.warning("native_calendar 扩展未安装，启用纯 Python 交易日历")
            self._fallback_enabled = True

        if self._fallback_enabled:
            # 使用 pandas_market_calendars 生成基础日历，缺少依赖时退回工作日判断
            try:
                self._pandas_calendar = mcal.get_calendar("XSHG")
                logger.debug("✓ pandas_market_calendars XSHG 日历已加载作为回退")
            except Exception:  # pragma: no cover - 再次回退
                self._pandas_calendar = None
                logger.warning(
                    "pandas_market_calendars 获取 XSHG 日历失败，将使用工作日规则回退",
                    exc_info=True,
                )


    def get_trading_calendar(self, start_year: Optional[int] = None) -> pd.DataFrame:
        """
        获取交易日历数据 (已废弃)

        此方法在新版中已废弃，因为日历数据直接由C++扩展管理。
        为保持API兼容性，返回一个空的DataFrame。

        :param start_year: 已忽略
        :return: 空的 DataFrame
        """
        logger.warning("get_trading_calendar 方法已废弃，交易日历现在由C++扩展在内部管理。")
        empty_df = pd.DataFrame({"date": [], "year": []})
        return cast(pd.DataFrame, empty_df)

    def is_trading_day(self, target_date: date) -> bool:
        """
        判断指定日期是否为交易日

        :param target_date: 日期对象
        :return: True=交易日，False=非交易日
        """
        if self._native_calendar is not None:
            is_trading = self._native_calendar.is_trading_day(target_date.year, target_date.month, target_date.day)
            logger.debug("日期 %s %s交易日 (native)", target_date, "是" if is_trading else "不是")
            return is_trading

        if self._pandas_calendar is not None:
            schedule = self._pandas_calendar.valid_days(target_date, target_date)
            return not schedule.empty

        # 最后回退：仅根据工作日判断
        return target_date.weekday() < 5

    def get_next_trading_day(self, start_date: date, include_self: bool = False) -> Optional[date]:
        """
        获取下一个交易日

        :param start_date: 起始日期
        :param include_self: 是否包含起始日期当天
        :return: 下一个交易日的日期对象
        """
        if self._native_calendar is not None:
            next_day_tuple = self._native_calendar.get_next_trading_day(start_date.year, start_date.month, start_date.day, include_self)
            if next_day_tuple:
                return date(next_day_tuple[0], next_day_tuple[1], next_day_tuple[2])
            return None

        current = start_date
        if not include_self:
            current += timedelta(days=1)
        while True:
            if self.is_trading_day(current):
                return current
            current += timedelta(days=1)

    def get_previous_trading_day(self, start_date: date, include_self: bool = False) -> Optional[date]:
        """
        获取上一个交易日

        :param start_date: 起始日期
        :param include_self: 是否包含起始日期当天
        :return: 上一个交易日的日期对象
        """
        if self._native_calendar is not None:
            prev_day_tuple = self._native_calendar.get_previous_trading_day(start_date.year, start_date.month, start_date.day, include_self)
            if prev_day_tuple:
                return date(prev_day_tuple[0], prev_day_tuple[1], prev_day_tuple[2])
            return None

        current = start_date
        if not include_self:
            current -= timedelta(days=1)
        while True:
            if self.is_trading_day(current):
                return current
            current -= timedelta(days=1)

    def get_trading_days_in_range(self, start_date: date, end_date: date) -> List[date]:
        """
        获取指定范围内的所有交易日

        :param start_date: 开始日期
        :param end_date: 结束日期
        :return: 交易日列表
        """
        if self._native_calendar is not None:
            trading_days_tuples = self._native_calendar.get_trading_days_in_range(start_date.year, start_date.month, start_date.day, end_date.year, end_date.month, end_date.day)
            return [date(d[0], d[1], d[2]) for d in trading_days_tuples]

        days: List[date] = []
        current = start_date
        while current <= end_date:
            if self.is_trading_day(current):
                days.append(current)
            current += timedelta(days=1)
        return days

    def get_non_trading_days_in_range(self, start_date: date, end_date: date) -> List[date]:
        """
        获取指定范围内的所有非交易日

        :param start_date: 开始日期
        :param end_date: 结束日期
        :return: 非交易日列表
        """
        # 生成所有日期
        all_dates = []
        current = start_date
        while current <= end_date:
            all_dates.append(current)
            current += timedelta(days=1)

        # 获取交易日
        trading_dates_set = set(self.get_trading_days_in_range(start_date, end_date))

        # 返回非交易日
        non_trading_days = [d for d in all_dates if d not in trading_dates_set]

        return non_trading_days


# ==================== 全局实例和便捷函数 ====================

# 全局交易日历实例
trading_calendar = TradingCalendar()


# 便捷函数（直接使用全局实例）
def get_trading_calendar_global() -> pd.DataFrame:
    """便捷函数：获取交易日历 (已废弃)"""
    return trading_calendar.get_trading_calendar()


def is_trading_day_global(target_date: date) -> bool:
    """便捷函数：判断交易日"""
    return trading_calendar.is_trading_day(target_date)


def get_next_trading_day_global(start_date: date, include_self: bool = False) -> Optional[date]:
    """便捷函数：获取下一个交易日"""
    return trading_calendar.get_next_trading_day(start_date, include_self)


def get_previous_trading_day_global(start_date: date, include_self: bool = False) -> Optional[date]:
    """便捷函数：获取上一个交易日"""
    return trading_calendar.get_previous_trading_day(start_date, include_self)


def get_trading_days_in_range_global(start: date, end: date) -> List[date]:
    """便捷函数：获取交易日范围"""
    return trading_calendar.get_trading_days_in_range(start, end)
