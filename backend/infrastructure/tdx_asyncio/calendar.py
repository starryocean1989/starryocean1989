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
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Optional, cast

import pandas as pd
import pandas_market_calendars as mcal

from .logger import logger


class TradingCalendar:
    """
    异步交易日历管理器

    使用 pandas_market_calendars 作为底层实现，提供中国A股交易日历（1990年至今）
    """

    def __init__(self, cache_dir: Optional[str] = None):
        """
        初始化交易日历

        :param cache_dir: 缓存目录（如果为None，使用ConfigManager获取缓存目录）
        """
        # 🔧 修复：使用 ConfigManager 获取缓存目录，确保使用 data/cache 目录
        if cache_dir is None:
            try:
                import sys
                from pathlib import Path

                # 添加项目根目录到sys.path
                project_root = Path(__file__).parent.parent.parent.parent
                if str(project_root) not in sys.path:
                    sys.path.insert(0, str(project_root))

                from backend.infrastructure.data_module_vnpy.core_engine import ConfigManager
                config_manager = ConfigManager.get_instance()
                self.cache_dir = config_manager.get_cache_dir()
            except Exception:
                # 降级：使用默认相对路径
                self.cache_dir = Path("cache")  # Path已在文件顶部导入
                self.cache_dir.mkdir(parents=True, exist_ok=True)
        else:
            self.cache_dir = Path(cache_dir)  # Path已在文件顶部导入
            self.cache_dir.mkdir(parents=True, exist_ok=True)

        # pandas_market_calendars无需初始化，直接调用API即可
        logger.debug("✓ 交易日历管理器初始化完成 (pandas_market_calendars数据源)")

        # 缓存交易日历数据（内存缓存）
        self._calendar_cache: Optional[pd.DataFrame] = None
        self._cache_timestamp: Optional[datetime] = None
        self._cache_ttl = 86400  # 24小时缓存

        # 🔧 修复：文件缓存路径使用缓存目录下的绝对路径
        self._cache_file = self.cache_dir / "trading_calendar.json"

    def _load_from_file_cache(self) -> Optional[pd.DataFrame]:
        """从文件缓存加载交易日历（使用DailyCacheManager）

        Returns:
            DataFrame 或 None（如果缓存无效或不存在）
        """
        try:
            # 🔧 延迟导入避免循环依赖
            import sys
            from pathlib import Path

            # 添加项目根目录到sys.path
            project_root = Path(__file__).parent.parent.parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))

            from backend.infrastructure.data_module_vnpy.core_engine import DailyCacheManager

            # 🔧 确保使用Path对象
            cache_file_path = Path(self._cache_file) if not isinstance(self._cache_file, Path) else self._cache_file

            cache_data, cache_date, is_valid = DailyCacheManager.load_with_validation(
                cache_file_path
            )

            if not cache_data or not is_valid:
                return None

            # 将缓存数据转换回DataFrame
            if isinstance(cache_data, list):
                # 格式：[{"date": "YYYY-MM-DD", "year": YYYY}, ...]
                df = pd.DataFrame(cache_data)
                # 将date列从字符串转换为date对象
                df["date"] = pd.to_datetime(df["date"]).dt.date
                return df

            return None

        except Exception as e:
            logger.debug(f"加载交易日历文件缓存失败: {e}")
            return None

    def _save_to_file_cache(self, calendar_df: pd.DataFrame) -> bool:
        """保存交易日历到文件缓存（使用DailyCacheManager）

        Args:
            calendar_df: 交易日历DataFrame

        Returns:
            是否保存成功
        """
        try:
            # 🔧 延迟导入避免循环依赖
            import sys
            from pathlib import Path

            # 添加项目根目录到sys.path
            project_root = Path(__file__).parent.parent.parent.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))

            from backend.infrastructure.data_module_vnpy import DailyCacheManager

            # 转换DataFrame为可序列化格式
            cache_data = calendar_df.to_dict("records")

            # 将date对象转换为字符串
            for record in cache_data:
                if "date" in record and hasattr(record["date"], "strftime"):
                    record["date"] = record["date"].strftime("%Y-%m-%d")

            # 🔧 确保使用Path对象
            cache_file_path = Path(self._cache_file) if not isinstance(self._cache_file, Path) else self._cache_file

            # 使用DailyCacheManager保存（带日期）
            success = DailyCacheManager.save_with_date(cache_data, cache_file_path)

            if success:
                logger.debug(f"交易日历已保存到文件缓存: {self._cache_file}")
            else:
                logger.warning(f"保存交易日历文件缓存失败")

            return success

        except Exception as e:
            logger.error(f"保存交易日历文件缓存异常: {e}", exc_info=True)
            return False

    async def get_trading_calendar(self, start_year: Optional[int] = None) -> pd.DataFrame:
        """
        异步获取交易日历数据

        :param start_year: 开始年份，None为从1990年开始（pandas_market_calendars支持1990年至今）
        :return: DataFrame包含交易日，列名：['date', 'year']
        """
        try:
            # 🆕 先尝试从文件缓存加载
            cached_df = self._load_from_file_cache()
            if cached_df is not None:
                logger.debug("使用文件缓存的交易日历数据")
                self._calendar_cache = cached_df
                self._cache_timestamp = datetime.now()

                # 如果指定了start_year，筛选数据
                if start_year is not None:
                    cached_df = cast(
                        pd.DataFrame, cached_df[cached_df["year"] >= start_year].copy()
                    )

                return cached_df

            # 🔧 修复：缓存不存在或无效时，自动从API请求数据生成
            # 继续执行下面的逻辑，从API获取数据

            # 检查内存缓存
            if self._calendar_cache is not None and self._cache_timestamp is not None:
                if (datetime.now() - self._cache_timestamp).total_seconds() < self._cache_ttl:
                    logger.debug("使用内存缓存的交易日历数据")

                    # 如果指定了start_year，筛选数据
                    if start_year is not None:
                        return cast(
                            pd.DataFrame,
                            self._calendar_cache[self._calendar_cache["year"] >= start_year].copy(),
                        )

                    return self._calendar_cache

            # 在异步环境中执行同步操作（调用 pandas_market_calendars API）
            sse = await asyncio.to_thread(mcal.get_calendar, "SSE")  # 上海证券交易所
            schedule = await asyncio.to_thread(
                sse.schedule,
                start_date="1990-01-01",
                end_date=(datetime.now() + timedelta(days=365)).strftime("%Y-%m-%d"),
            )
            # 将 DatetimeIndex 转换为日期列表
            trade_dates_dt = schedule.index
            trade_dates = [d.date() for d in trade_dates_dt]

            # 转换为所需格式
            calendar_df = pd.DataFrame({"date": trade_dates, "year": [d.year for d in trade_dates]})

            # 排序（确保一致性）
            calendar_df = calendar_df.sort_values("date").reset_index(drop=True)

            # 更新缓存（缓存完整数据）
            self._calendar_cache = calendar_df
            self._cache_timestamp = datetime.now()

            # 🆕 保存到文件缓存
            self._save_to_file_cache(calendar_df)

            # 获取日期范围用于日志
            min_year = calendar_df["year"].min()
            max_year = calendar_df["year"].max()

            logger.info(f"✓ 成功获取交易日历：{len(calendar_df)}个交易日 ({min_year}-{max_year})")

            # 如果指定了start_year，筛选数据
            if start_year is not None:
                calendar_df = cast(
                    pd.DataFrame, calendar_df[calendar_df["year"] >= start_year].copy()
                )
                logger.debug(f"筛选{start_year}年及以后的数据：{len(calendar_df)}个交易日")

            return calendar_df

        except Exception as e:
            logger.error(f"获取交易日历失败: {e}", exc_info=True)
            # 返回空DataFrame保持兼容性
            empty_df = pd.DataFrame({"date": [], "year": []})
            return cast(pd.DataFrame, empty_df)

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

    print("=== 交易日历系统演示 (pandas_market_calendars版本 - 支持1990年至今) ===")

    # 1. 获取交易日历（完整历史数据）
    calendar = await get_trading_calendar_global()
    print(f"获取到 {len(calendar)} 个交易日")
    print(f"最早日期: {calendar['date'].min()}")
    print(f"最晚日期: {calendar['date'].max()}")

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
