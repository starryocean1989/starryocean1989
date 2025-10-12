# -*- coding: utf-8 -*-
"""
通达信日期时间解码器

处理通达信API返回的编码日期格式：
1. 分钟线：YYYY-MM-DDD 格式，DDD是从年初开始的天数
2. 日线：DDDD-MM-DD 格式，DDDD是从1990-01-01开始的总天数

注意：
- 编码日期主要存在于更早期的历史数据中
- 由于mootdx API的offset限制（最大800），通常获取不到编码日期
- 本解码器作为保险措施，确保即使遇到编码日期也能正确处理
- 对于正常日期，使用快速路径（批量解析），不影响性能
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


class TdxDateTimeDecoder:
    """通达信日期时间解码器"""

    # 日线基准日期：1990-01-01
    DAILY_BASE_DATE = datetime(1990, 1, 1)

    @staticmethod
    def decode_minute_datetime(date_str: str, time_str: str = "00:00") -> Optional[datetime]:
        """
        解码分钟线日期时间

        格式: YYYY-MM-DDD HH:MM
        编码: DDD是从年初开始的天数（1-366）

        Args:
            date_str: 日期字符串，如 "2004-02-77"
            time_str: 时间字符串，如 "05:09"

        Returns:
            解码后的datetime对象，解码失败返回None

        Examples:
            >>> decode_minute_datetime("2004-02-77", "05:09")
            datetime(2004, 3, 17, 5, 9)

            >>> decode_minute_datetime("2004-00-00", "00:00")
            datetime(2003, 12, 31, 0, 0)
        """
        try:
            parts = date_str.split("-")
            if len(parts) != 3:
                return None

            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])

            # 检查是否需要解码（day > 31或month > 12或day=0或month=0）
            if 1 <= day <= 31 and 1 <= month <= 12:
                # 正常日期，无需解码
                time_parts = time_str.split(":")
                hour = int(time_parts[0]) if len(time_parts) > 0 else 0
                minute = int(time_parts[1]) if len(time_parts) > 1 else 0
                return datetime(year, month, day, hour, minute)

            # 需要解码：day是从年初开始的天数
            year_start = datetime(year, 1, 1)

            # day为0表示上一年最后一天
            if day == 0:
                decoded_date = datetime(year - 1, 12, 31)
            else:
                # day-1是因为1月1日是第1天（不是第0天）
                decoded_date = year_start + timedelta(days=day - 1)

            # 添加时间部分
            time_parts = time_str.split(":")
            hour = int(time_parts[0]) if len(time_parts) > 0 else 0
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0

            decoded_datetime = decoded_date.replace(hour=hour, minute=minute)

            logger.debug("分钟线日期解码: %s %s → %s", date_str, time_str, decoded_datetime)
            return decoded_datetime

        except Exception as e:
            logger.error("分钟线日期解码失败: %s %s, 错误: %s", date_str, time_str, e)
            return None

    @staticmethod
    def decode_daily_datetime(date_str: str, time_str: str = "15:00") -> Optional[datetime]:
        """
        解码日线日期时间

        格式: DDDD-MM-DD HH:MM
        编码: DDDD是从1990-01-01开始的总天数

        Args:
            date_str: 日期字符串，如 "3903-78-38"
            time_str: 时间字符串，如 "15:00"

        Returns:
            解码后的datetime对象，解码失败返回None

        Examples:
            >>> decode_daily_datetime("3903-78-38", "15:00")
            datetime(2000, 9, 8, 15, 0)

            >>> decode_daily_datetime("4382-19-85", "15:00")
            datetime(2001, 12, 31, 15, 0)
        """
        try:
            parts = date_str.split("-")
            if len(parts) != 3:
                return None

            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])

            # 检查是否需要解码（year > 2200或month > 12或day > 31或day=0或month=0）
            if year <= 2200 and 1 <= day <= 31 and 1 <= month <= 12:
                # 正常日期，无需解码
                time_parts = time_str.split(":")
                hour = int(time_parts[0]) if len(time_parts) > 0 else 15
                minute = int(time_parts[1]) if len(time_parts) > 1 else 0
                return datetime(year, month, day, hour, minute)

            # 需要解码：year是从1990-01-01开始的天数
            decoded_date = TdxDateTimeDecoder.DAILY_BASE_DATE + timedelta(days=year)

            # 添加时间部分（日线默认15:00）
            time_parts = time_str.split(":")
            hour = int(time_parts[0]) if len(time_parts) > 0 else 15
            minute = int(time_parts[1]) if len(time_parts) > 1 else 0

            decoded_datetime = decoded_date.replace(hour=hour, minute=minute)

            logger.debug("日线日期解码: %s %s → %s", date_str, time_str, decoded_datetime)
            return decoded_datetime

        except Exception as e:
            logger.error("日线日期解码失败: %s %s, 错误: %s", date_str, time_str, e)
            return None

    @staticmethod
    def decode_dataframe(df: pd.DataFrame, interval: str) -> pd.DataFrame:
        """
        批量解码DataFrame中的日期时间（智能判断是否需要解码）

        Args:
            df: 包含datetime列的DataFrame（原始数据）
            interval: 周期类型（用于判断解码方式）

        Returns:
            解码后的DataFrame
        """
        try:
            if df is None or df.empty:
                return df

            if "datetime" not in df.columns:
                logger.warning("DataFrame中没有datetime列")
                return df

            # 创建副本避免修改原数据
            df = df.copy()

            # 判断是分钟线还是日线
            is_minute = interval in ["1m", "5m", "15m", "30m", "60m"]

            # 📊 先检查datetime列的数据类型
            datetime_col = df["datetime"]

            # 如果已经是datetime类型，说明是正常数据，直接返回
            if pd.api.types.is_datetime64_any_dtype(datetime_col):
                logger.debug("datetime列已是datetime类型，无需解码")
                return df

            # 🔧 优化：先尝试批量解析（快速路径，用于正常日期）
            try:
                # 🔧 添加format参数避免警告，指定常见的日期格式
                # 通达信的datetime格式通常是 "YYYY-MM-DD HH:MM"
                import warnings

                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    df["datetime"] = pd.to_datetime(
                        df["datetime"], format="%Y-%m-%d %H:%M", errors="raise"
                    )
                logger.debug("✓ 批量解析成功，无需逐行解码，返回 %d 行", len(df))
                return df
            except (ValueError, pd.errors.ParserError) as e:
                # format不匹配或有编码日期，尝试不指定format
                try:
                    import warnings

                    with warnings.catch_warnings():
                        warnings.simplefilter("ignore")
                        df["datetime"] = pd.to_datetime(df["datetime"], errors="raise")
                    logger.debug("✓ 自动格式解析成功，返回 %d 行", len(df))
                    return df
                except (ValueError, pd.errors.ParserError) as e2:
                    # 批量解析失败，说明有编码日期，需要逐行解码
                    logger.info("检测到编码日期，启动逐行解码... 错误: %s", str(e2)[:100])

            # 🔧 逐行解码（慢速路径，仅用于编码日期）
            decoded_dates = []
            success_count = 0
            fail_count = 0

            for idx, row in df.iterrows():
                # 获取原始datetime字符串
                datetime_value = row["datetime"]

                # 如果是字符串，解码
                if isinstance(datetime_value, str):
                    date_str = datetime_value
                else:
                    # 转换为字符串
                    date_str = str(datetime_value)

                try:
                    # 分离日期和时间部分
                    if " " in date_str:
                        date_part, time_part = date_str.split(" ", 1)
                    else:
                        date_part = date_str
                        time_part = "15:00" if not is_minute else "00:00"

                    # 根据周期类型选择解码方法
                    if is_minute:
                        decoded = TdxDateTimeDecoder.decode_minute_datetime(date_part, time_part)
                    else:
                        decoded = TdxDateTimeDecoder.decode_daily_datetime(date_part, time_part)

                    if decoded:
                        decoded_dates.append(decoded)
                        success_count += 1
                    else:
                        # 解码失败，尝试直接解析
                        try:
                            decoded_dates.append(pd.to_datetime(date_str))
                            success_count += 1
                        except:
                            decoded_dates.append(pd.NaT)
                            fail_count += 1

                except Exception as e:
                    logger.debug("解码失败: %s, 错误: %s", date_str, str(e)[:50])
                    decoded_dates.append(pd.NaT)
                    fail_count += 1

            # 更新datetime列
            df["datetime"] = decoded_dates

            # 删除NaT行
            original_len = len(df)
            df = df.dropna(subset=["datetime"])
            removed = original_len - len(df)

            if removed > 0:
                logger.info(
                    "✓ 解码完成：成功 %d 行，失败 %d 行，删除 %d 行",
                    success_count,
                    fail_count,
                    removed,
                )
            else:
                logger.debug("✓ 解码完成：成功 %d 行", success_count)

            return df

        except Exception as e:
            logger.error("批量解码失败: %s", e, exc_info=True)
            return df


# 便捷函数
def decode_tdx_datetime(date_str: str, time_str: str, interval: str) -> Optional[datetime]:
    """
    根据周期自动选择解码方法

    Args:
        date_str: 日期字符串
        time_str: 时间字符串
        interval: 周期类型

    Returns:
        解码后的datetime对象
    """
    if interval in ["1m", "5m", "15m", "30m", "60m"]:
        return TdxDateTimeDecoder.decode_minute_datetime(date_str, time_str)
    else:
        return TdxDateTimeDecoder.decode_daily_datetime(date_str, time_str)
