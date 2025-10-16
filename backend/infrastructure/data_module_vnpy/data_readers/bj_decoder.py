# -*- coding: utf-8 -*-
"""
北证数据二进制解码器

基于pytdx的源码分析实现，支持读取北证市场的通达信二进制数据文件。

二进制格式（通过分析pytdx源码得出）：
- 格式字符串: '<IIIIIfII'
- 字段：日期(I), 开盘(I), 最高(I), 最低(I), 收盘(I), 成交额(f), 成交量(I), 保留(I)
- 每条记录: 32字节

系数转换（参考上证A股）：
- 价格系数: 0.01 (价格需要除以100)
- 成交量系数: 0.01 (成交量需要除以100)
"""

import logging
import struct
from pathlib import Path
from typing import List, Tuple, cast

import pandas as pd


class BjStockDecoder:
    """北证股票数据解码器"""

    # 日线二进制格式
    DAY_FORMAT = "<IIIIIfII"  # 小端序，8个字段
    DAY_SIZE = struct.calcsize(DAY_FORMAT)  # 32字节

    # 分钟线二进制格式（5分钟线和1分钟线）
    MIN_FORMAT = "<HHfffffII"  # 小端序，日期(H), 时间(H), OHLC(4个f), 成交额(f), 成交量(I), 保留(I)
    MIN_SIZE = struct.calcsize(MIN_FORMAT)  # 32字节

    # 北证A股系数（参考上证/深证A股）
    PRICE_COEFFICIENT = 0.01  # 价格 / 100（仅日线需要）
    VOLUME_COEFFICIENT = 0.01  # 成交量 / 100（仅日线需要）

    def __init__(self):
        """初始化解码器"""
        self.logger = logging.getLogger(__name__)

    def read_day_file(self, file_path: Path) -> pd.DataFrame:
        """读取北证日线数据文件.

        Args:
            file_path: 数据文件路径

        Returns:
            DataFrame: 标准化的OHLCV数据
        """
        try:
            if not file_path.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")

            # 读取二进制数据
            with open(file_path, "rb") as f:
                content = f.read()

            # 解析记录（日线格式）
            records = self._unpack_day_records(content)

            if not records:
                self.logger.warning("文件为空或格式错误: %s", file_path)
                return pd.DataFrame()

            # 转换为DataFrame
            df = self._records_to_dataframe(records)

            self.logger.info("成功读取 %d 条记录: %s", len(df), file_path.name)
            return df

        except Exception as e:
            self.logger.error("读取文件失败: %s, 错误: %s", file_path, e)
            raise

    def _unpack_day_records(self, data: bytes) -> List[Tuple]:
        """解析日线二进制数据为记录列表.

        Args:
            data: 二进制数据

        Returns:
            List[Tuple]: 记录列表
        """
        records = []
        record_struct = struct.Struct(self.DAY_FORMAT)

        # 按32字节一条记录解析
        for offset in range(0, len(data), self.DAY_SIZE):
            if offset + self.DAY_SIZE > len(data):
                # 剩余数据不足一条记录，跳过
                break

            try:
                record = record_struct.unpack_from(data, offset)
                records.append(record)
            except struct.error as e:
                self.logger.warning("解析日线记录失败，offset=%d: %s", offset, e)
                continue

        return records

    def _unpack_min_records(self, data: bytes) -> List[Tuple]:
        """解析分钟线二进制数据为记录列表.

        Args:
            data: 二进制数据

        Returns:
            List[Tuple]: 记录列表
        """
        records = []
        record_struct = struct.Struct(self.MIN_FORMAT)

        # 按32字节一条记录解析
        for offset in range(0, len(data), self.MIN_SIZE):
            if offset + self.MIN_SIZE > len(data):
                # 剩余数据不足一条记录，跳过
                break

            try:
                record = record_struct.unpack_from(data, offset)
                records.append(record)
            except struct.error as e:
                self.logger.warning("解析分钟线记录失败，offset=%d: %s", offset, e)
                continue

        return records

    def _records_to_dataframe(self, records: List[Tuple]) -> pd.DataFrame:
        """将记录列表转换为DataFrame.

        Args:
            records: 记录列表，每条记录格式：
                (日期, 开盘, 最高, 最低, 收盘, 成交额, 成交量, 保留)

        Returns:
            DataFrame: 标准化的OHLCV数据
        """
        data = []

        for record in records:
            # 解析字段
            date_int = record[0]  # 例如: 20250101
            open_price = record[1] * self.PRICE_COEFFICIENT
            high_price = record[2] * self.PRICE_COEFFICIENT
            low_price = record[3] * self.PRICE_COEFFICIENT
            close_price = record[4] * self.PRICE_COEFFICIENT
            amount = record[5]  # 成交额（元）
            volume = record[6] * self.VOLUME_COEFFICIENT  # 成交量（手）
            # record[7] 是保留字段，忽略

            # 转换日期格式: 20250101 -> 2025-01-01
            date_str = str(date_int)
            if len(date_str) == 8:
                date_formatted = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            else:
                # 日期格式异常，跳过
                self.logger.warning("日期格式异常: %d", date_int)
                continue

            data.append(
                {
                    "date": date_formatted,
                    "open": open_price,
                    "high": high_price,
                    "low": low_price,
                    "close": close_price,
                    "amount": amount,
                    "volume": volume,
                }
            )

        # 创建DataFrame
        df = pd.DataFrame(data)

        if not df.empty:
            # 转换日期为datetime
            df["datetime"] = pd.to_datetime(df["date"], errors="coerce")
            # 删除无效日期
            df = df[df["datetime"].notna()].copy()
            # 设置索引
            df = df.set_index("datetime")
            # 只返回需要的列
            return cast(pd.DataFrame, df[["open", "high", "low", "close", "amount", "volume"]])

        return df

    def _parse_min_date(self, num: int) -> Tuple[int, int, int]:
        """解析分钟线日期编码.

        编码规则（通过pytdx源码分析）：
        year = num // 2048 + 2004
        month = (num % 2048) // 100
        day = (num % 2048) % 100

        Args:
            num: 日期编码

        Returns:
            (year, month, day)
        """
        year = num // 2048 + 2004
        month = (num % 2048) // 100
        day = (num % 2048) % 100
        return year, month, day

    def _parse_min_time(self, num: int) -> Tuple[int, int]:
        """解析分钟线时间编码.

        编码规则：从0点开始的分钟数
        hour = num // 60
        minute = num % 60

        Args:
            num: 时间编码（分钟数）

        Returns:
            (hour, minute)
        """
        hour = num // 60
        minute = num % 60
        return hour, minute

    def _min_records_to_dataframe(self, records: List[Tuple]) -> pd.DataFrame:
        """将分钟线记录列表转换为DataFrame.

        Args:
            records: 记录列表，每条记录格式：
                (日期编码(H), 时间编码(H), 开盘(f), 最高(f), 最低(f), 收盘(f), 成交额(f), 成交量(I), 保留(I))

        Returns:
            DataFrame: 标准化的OHLCV数据
        """
        data = []

        for record in records:
            # 解析字段
            date_code = record[0]
            time_code = record[1]
            open_price = record[2]  # 分钟线价格已经是正确值，不需要系数
            high_price = record[3]
            low_price = record[4]
            close_price = record[5]
            amount = record[6]  # 成交额
            volume = record[7]  # 成交量（分钟线是股数，不是手数）
            # record[8] 是保留字段，忽略

            # 解析日期和时间
            try:
                year, month, day = self._parse_min_date(date_code)
                hour, minute = self._parse_min_time(time_code)

                # 构建datetime字符串
                datetime_str = f"{year:04d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:00"

                data.append(
                    {
                        "date": datetime_str,
                        "open": open_price,
                        "high": high_price,
                        "low": low_price,
                        "close": close_price,
                        "amount": amount,
                        "volume": volume,
                    }
                )
            except Exception as e:
                self.logger.warning(
                    "解析分钟线记录失败: date=%d, time=%d, %s", date_code, time_code, e
                )
                continue

        # 创建DataFrame
        df = pd.DataFrame(data)

        if not df.empty:
            # 转换日期为datetime
            df["datetime"] = pd.to_datetime(df["date"], errors="coerce")
            # 删除无效日期
            df = df[df["datetime"].notna()].copy()
            # 设置索引
            df = df.set_index("datetime")
            # 只返回需要的列
            return cast(pd.DataFrame, df[["open", "high", "low", "close", "amount", "volume"]])

        return df

    def read_5min_file(self, file_path: Path) -> pd.DataFrame:
        """读取北证5分钟线数据文件.

        Args:
            file_path: 数据文件路径

        Returns:
            DataFrame: 标准化的OHLCV数据
        """
        try:
            if not file_path.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")

            # 读取二进制数据
            with open(file_path, "rb") as f:
                content = f.read()

            # 解析记录（分钟线格式）
            records = self._unpack_min_records(content)

            if not records:
                self.logger.warning("文件为空或格式错误: %s", file_path)
                return pd.DataFrame()

            # 转换为DataFrame
            df = self._min_records_to_dataframe(records)

            self.logger.info("成功读取 %d 条5分钟线记录: %s", len(df), file_path.name)
            return df

        except Exception as e:
            self.logger.error("读取5分钟线文件失败: %s, 错误: %s", file_path, e)
            raise

    def read_1min_file(self, file_path: Path) -> pd.DataFrame:
        """读取北证1分钟线数据文件.

        Args:
            file_path: 数据文件路径

        Returns:
            DataFrame: 标准化的OHLCV数据
        """
        try:
            if not file_path.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")

            # 读取二进制数据
            with open(file_path, "rb") as f:
                content = f.read()

            # 解析记录（分钟线格式）
            records = self._unpack_min_records(content)

            if not records:
                self.logger.warning("文件为空或格式错误: %s", file_path)
                return pd.DataFrame()

            # 转换为DataFrame
            df = self._min_records_to_dataframe(records)

            self.logger.info("成功读取 %d 条1分钟线记录: %s", len(df), file_path.name)
            return df

        except Exception as e:
            self.logger.error("读取1分钟线文件失败: %s, 错误: %s", file_path, e)
            raise
