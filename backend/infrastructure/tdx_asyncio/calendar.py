# -*- coding: utf-8 -*-
"""
异步交易日历系统模块

提供中国股票市场交易日历功能，完全异步化实现。
现使用 pandas_market_calendars 作为底层实现（专业、可靠的市场日历库）

核心功能：
- 基于 pandas_market_calendars 的中国A股交易日历
- 异步接口（保持原有API兼容性）
- 缓存机制（24小时刷新）
- 便捷的交易日判断函数

作者：[项目名称]
版本：3.0 - 使用 pandas_market_calendars 重构
"""

import asyncio
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Optional

import pandas as pd
import pandas_market_calendars as mcal

from .logger import logger


class TradingCalendar:
    """
    异步交易日历管理器

    使用 pandas_market_calendars 作为底层实现，提供中国A股交易日历
    """

    def __init__(self, cache_dir: str = "cache"):
        """
        初始化交易日历

        :param cache_dir: 缓存目录（保持接口兼容，实际使用mcal内置缓存）
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # 初始化中国A股市场日历
        # XSHG = 上海证券交易所 (Shanghai Stock Exchange)
        try:
            self.calendar = mcal.get_calendar("XSHG")
            logger.info("✓ 成功加载中国A股交易日历 (XSHG)")
        except Exception as e:
            logger.error(f"加载交易日历失败: {e}")
            # 降级：尝试使用深圳交易所
            try:
                self.calendar = mcal.get_calendar("XSHE")
                logger.warning("使用深圳交易所日历 (XSHE) 作为备选")
            except Exception as e2:
                logger.error(f"降级方案也失败: {e2}")
                raise RuntimeError("无法加载任何中国A股交易日历") from e2

        # 缓存交易日历数据（内存缓存）
        self._calendar_cache: Optional[pd.DataFrame] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = 86400  # 24小时缓存

    async def get_trading_calendar(self, start_year: Optional[int] = None) -> pd.DataFrame:
        """
        异步获取交易日历数据

        :param start_year: 开始年份，None为最近几年
        :return: DataFrame包含交易日，列名：['date', 'year']
        """
        try:
            # 检查缓存
            if self._calendar_cache is not None and self._cache_timestamp is not None:
                if (datetime.now() - self._cache_timestamp).total_seconds() < self._cache_ttl:
                    logger.debug("使用缓存的交易日历数据")
                    return self._calendar_cache

            # 确定日期范围
            if start_year is None:
                start_year = datetime.now().year - 5  # 默认最近5年

            start_date = f"{start_year}-01-01"
            end_date = f"{datetime.now().year + 1}-12-31"  # 包含未来一年

            # 在异步环境中执行同步操作
            schedule = await asyncio.to_thread(
                self.calendar.schedule, start_date=start_date, end_date=end_date
            )

            # 转换为所需格式
            trading_days = schedule.index.date
            calendar_df = pd.DataFrame(
                {"date": trading_days, "year": [d.year for d in trading_days]}
            )

            # 更新缓存
            self._calendar_cache = calendar_df
            self._cache_timestamp = datetime.now()

            logger.info(
                f"✓ 成功获取交易日历：{len(calendar_df)}个交易日 ({start_year}-{datetime.now().year+1})"
            )
            return calendar_df

        except Exception as e:
            logger.error(f"获取交易日历失败: {e}", exc_info=True)
            # 返回空DataFrame保持兼容性
            return pd.DataFrame(columns=["date", "year"])

    async def is_trading_day(self, date_str: Optional[str] = None) -> bool:
        """
        判断指定日期是否为交易日

        :param date_str: 日期字符串（YYYY-MM-DD格式），None为今天
        :return: True=交易日，False=非交易日
        """
        if date_str is None:
            target_date = date.today()
        else:
            try:
                target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                logger.error(f"日期格式错误: {date_str}")
                return False

        # 获取交易日历
        calendar_df = await self.get_trading_calendar()

        if calendar_df.empty:
            logger.warning("无法获取交易日历，返回False")
            return False

        # 检查目标日期是否在交易日历中
        is_trading = target_date in calendar_df["date"].values

        logger.debug(f"日期 {target_date} {'是' if is_trading else '不是'}交易日")
        return is_trading

    async def get_next_trading_day(self, date_str: Optional[str] = None) -> Optional[str]:
        """
        获取下一个交易日

        :param date_str: 起始日期，None为今天
        :return: 下一个交易日的日期字符串（YYYY-MM-DD）
        """
        if date_str is None:
            start_date = date.today()
        else:
            try:
                start_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                logger.error(f"日期格式错误: {date_str}")
                return None

        # 获取交易日历
        calendar_df = await self.get_trading_calendar()

        if calendar_df.empty:
            return None

        # 查找下一个交易日
        future_dates = calendar_df[calendar_df["date"] > start_date]

        if future_dates.empty:
            return None

        next_trading = future_dates.iloc[0]["date"]
        return next_trading.strftime("%Y-%m-%d")

    async def get_previous_trading_day(self, date_str: Optional[str] = None) -> Optional[str]:
        """
        获取上一个交易日

        :param date_str: 起始日期，None为今天
        :return: 上一个交易日的日期字符串（YYYY-MM-DD）
        """
        if date_str is None:
            start_date = date.today()
        else:
            try:
                start_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                logger.error(f"日期格式错误: {date_str}")
                return None

        # 获取交易日历
        calendar_df = await self.get_trading_calendar()

        if calendar_df.empty:
            return None

        # 查找上一个交易日
        past_dates = calendar_df[calendar_df["date"] < start_date]

        if past_dates.empty:
            return None

        prev_trading = past_dates.iloc[-1]["date"]
        return prev_trading.strftime("%Y-%m-%d")

    async def get_trading_days_in_range(self, start_date: str, end_date: str) -> List[str]:
        """
        获取指定范围内的所有交易日

        :param start_date: 开始日期（YYYY-MM-DD）
        :param end_date: 结束日期（YYYY-MM-DD）
        :return: 交易日列表
        """
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError as e:
            logger.error(f"日期格式错误: {e}")
            return []

        # 获取交易日历
        calendar_df = await self.get_trading_calendar()

        if calendar_df.empty:
            return []

        # 筛选指定范围内的交易日
        mask = (calendar_df["date"] >= start) & (calendar_df["date"] <= end)
        trading_days = calendar_df[mask]["date"].tolist()

        return [d.strftime("%Y-%m-%d") for d in trading_days]

    async def get_non_trading_days_in_range(self, start_date: str, end_date: str) -> List[str]:
        """
        获取指定范围内的所有非交易日

        :param start_date: 开始日期（YYYY-MM-DD）
        :param end_date: 结束日期（YYYY-MM-DD）
        :return: 非交易日列表
        """
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError as e:
            logger.error(f"日期格式错误: {e}")
            return []

        # 生成所有日期
        all_dates = []
        current = start
        while current <= end:
            all_dates.append(current)
            current += timedelta(days=1)

        # 获取交易日
        trading_days = await self.get_trading_days_in_range(start_date, end_date)
        trading_dates = set(datetime.strptime(d, "%Y-%m-%d").date() for d in trading_days)

        # 返回非交易日
        non_trading_days = [d.strftime("%Y-%m-%d") for d in all_dates if d not in trading_dates]

        return non_trading_days


# ==================== 全局实例和便捷函数 ====================

# 全局交易日历实例
trading_calendar = TradingCalendar()


# 便捷函数（直接使用全局实例）
async def get_trading_calendar_global() -> pd.DataFrame:
    """便捷函数：获取交易日历"""
    return await trading_calendar.get_trading_calendar()


async def is_trading_day_global(date_str: Optional[str] = None) -> bool:
    """便捷函数：判断交易日"""
    return await trading_calendar.is_trading_day(date_str)


async def get_next_trading_day_global(date_str: Optional[str] = None) -> Optional[str]:
    """便捷函数：获取下一个交易日"""
    return await trading_calendar.get_next_trading_day(date_str)


async def get_previous_trading_day_global(date_str: Optional[str] = None) -> Optional[str]:
    """便捷函数：获取上一个交易日"""
    return await trading_calendar.get_previous_trading_day(date_str)


async def get_trading_days_in_range_global(start: str, end: str) -> List[str]:
    """便捷函数：获取交易日范围"""
    return await trading_calendar.get_trading_days_in_range(start, end)


# ==================== 使用示例 ====================


async def example_usage():
    """使用示例"""

    print("=== 交易日历系统演示 (pandas_market_calendars版本) ===")

    # 1. 获取交易日历
    calendar = await get_trading_calendar_global()
    print(f"获取到 {len(calendar)} 个交易日")

    # 2. 判断今天是否交易日
    is_today_trading = await is_trading_day_global()
    print(f"今天是交易日: {is_today_trading}")

    # 3. 获取下一个交易日
    next_day = await get_next_trading_day_global()
    print(f"下一个交易日: {next_day}")

    # 4. 获取上一个交易日
    prev_day = await get_previous_trading_day_global()
    print(f"上一个交易日: {prev_day}")

    # 5. 获取指定范围的交易日
    trading_days = await get_trading_days_in_range_global("2024-01-01", "2024-01-10")
    print(f"2024-01-01到2024-01-10的交易日: {trading_days}")


if __name__ == "__main__":
    asyncio.run(example_usage())
