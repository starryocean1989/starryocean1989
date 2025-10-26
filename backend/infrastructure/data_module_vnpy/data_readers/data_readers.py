# -*- coding: utf-8 -*-
"""
数据标准化读取工具 - 极限合并版

本模块已完成极限合并：将原4个独立文件合并为1个统一文件data_readers.py

合并前文件清单：
1. base_reader.py (123行) - 数据读取器基类
2. bj_decoder.py (280行) - 北证数据二进制解码器
3. tdx_reader.py (316行) - 通达信二进制数据读取器
4. tdx_dynamic_executor.py (360行) - TDX动态执行器

合并后：data_readers.py (~1,079行)

API兼容性：100%向后兼容，所有导入路径保持有效

合并日期：2025-10-26
"""

import asyncio
import concurrent.futures
import logging
import os
import struct
import time
from abc import ABC, abstractmethod
from collections import Counter, deque
from dataclasses import dataclass
import multiprocessing
from multiprocessing import Process, Event
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, cast
import queue

import pandas as pd

from backend.infrastructure.tdx_asyncio import (
    read_day_data,
    read_minute_data,
    read_lc5_data,
)
from backend.infrastructure.data_module_vnpy.load_balancer.load_balancer import (
    LocalProcessingTask,
)


# ==============================================================================
# 第1部分：基类定义（原base_reader.py）
# ==============================================================================


class BaseReader(ABC):
    """数据读取器抽象基类

    定义统一的数据读取接口，所有数据读取器都应继承此基类。

    设计模式：
    - 采用模板方法模式
    - read(): 读取原始数据
    - standardize(): 标准化数据格式
    - save(): 保存标准化后的数据
    """

    def __init__(self, source_path: Path):
        """
        初始化数据读取器

        Args:
            source_path: 数据源路径（文件或目录）
        """
        self.source_path = source_path

        if not self.source_path.exists():
            raise FileNotFoundError(f"数据源路径不存在: {source_path}")

    @abstractmethod
    def read(self, **kwargs) -> Any:
        """
        读取原始数据

        Args:
            **kwargs: 读取参数

        Returns:
            原始数据（具体类型由子类决定）

        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError("子类必须实现read()方法")

    @abstractmethod
    def standardize(self, raw_data: Any) -> pd.DataFrame:
        """
        标准化数据格式

        将原始数据转换为标准的DataFrame格式，必须包含以下列：
        - datetime: 时间（datetime类型）
        - open: 开盘价（float）
        - high: 最高价（float）
        - low: 最低价（float）
        - close: 收盘价（float）
        - volume: 成交量（float）
        - symbol: 品种代码（str）
        - interval: K线周期（str，如'1d', '5m', '1m'）

        Args:
            raw_data: 原始数据

        Returns:
            标准化后的DataFrame

        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError("子类必须实现standardize()方法")

    @abstractmethod
    def save(self, dataframe: pd.DataFrame, target_path: Optional[Path] = None) -> bool:
        """
        保存标准化后的数据

        Args:
            dataframe: 标准化后的DataFrame
            target_path: 目标保存路径（可选，如不指定则使用默认路径）

        Returns:
            是否保存成功

        Raises:
            NotImplementedError: 子类必须实现此方法
        """
        raise NotImplementedError("子类必须实现save()方法")

    def process(self, **kwargs) -> bool:
        """
        完整的处理流程：读取 -> 标准化 -> 保存

        这是一个模板方法，定义了完整的处理流程。
        子类通常不需要重写此方法，只需实现read()、standardize()、save()即可。

        Args:
            **kwargs: 处理参数

        Returns:
            是否处理成功
        """
        try:
            # 1. 读取原始数据
            raw_data = self.read(**kwargs)

            # 2. 标准化数据格式
            dataframe = self.standardize(raw_data)

            # 3. 保存数据
            success = self.save(dataframe)

            return success

        except Exception as e:
            raise RuntimeError(f"数据处理失败: {e}") from e

    def validate_dataframe(self, df: pd.DataFrame) -> bool:
        """
        验证DataFrame是否符合标准格式

        Args:
            df: 待验证的DataFrame

        Returns:
            是否符合标准格式

        Raises:
            ValueError: 如果格式不符合要求
        """
        required_columns = [
            "datetime",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "symbol",
            "interval",
        ]

        # 检查必需列是否存在
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(f"DataFrame缺少必需列: {missing_columns}")

        # 检查数据类型
        if not pd.api.types.is_datetime64_any_dtype(df["datetime"]):
            raise ValueError("datetime列必须是datetime类型")

        numeric_columns = ["open", "high", "low", "close", "volume"]
        for col in numeric_columns:
            if not pd.api.types.is_numeric_dtype(df[col]):
                raise ValueError(f"{col}列必须是数值类型")

        return True


# ==============================================================================
# 第2部分：北证数据解码器（原bj_decoder.py）
# ==============================================================================


class BjStockDecoder:
    """北证股票数据解码器

    基于pytdx的源码分析实现，支持读取北证市场的通达信二进制数据文件。

    二进制格式（通过分析pytdx源码得出）：
    - 格式字符串: '<IIIIIfII'
    - 字段：日期(I), 开盘(I), 最高(I), 最低(I), 收盘(I), 成交额(f), 成交量(I), 保留(I)
    - 每条记录: 32字节

    系数转换（参考上证A股）：
    - 价格系数: 0.01 (价格需要除以100)
    - 成交量系数: 0.01 (成交量需要除以100)
    """

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


# ==============================================================================
# 第3部分：通达信二进制数据读取器（原tdx_reader.py）
# ==============================================================================


class TdxBinaryReader(BaseReader):
    """通达信二进制数据读取器

    读取通达信软件本地保存的二进制K线数据文件，并标准化保存为Parquet格式。

    支持的数据类型：
    - 日线数据: vipdoc/{market}/lday/{symbol}.day
    - 5分钟线: vipdoc/{market}/fzline/{symbol}.lc5
    - 1分钟线: vipdoc/{market}/minline/{symbol}.lc1

    市场代码：
    - sh: 上证
    - sz: 深证
    - bj: 北证
    """

    # 市场代码映射
    MARKET_CODES = {
        "sh": "上证",
        "sz": "深证",
        "bj": "北证",
    }

    # 数据类型映射
    DATA_TYPE_MAPPING = {
        "day": {"interval": "1d", "subdir": "lday", "ext": ".day"},
        "5min": {"interval": "5m", "subdir": "fzline", "ext": ".lc5"},
        "1min": {"interval": "1m", "subdir": "minline", "ext": ".lc1"},
    }

    def __init__(self, source_path: Optional[Path] = None):
        """
        初始化通达信数据读取器

        Args:
            source_path: 通达信软件根目录（如不指定则从配置读取）
        """
        # 延迟导入避免循环依赖
        from ..config import config_manager
        from ..local_data.data_quality import StorageManager

        if source_path is None:
            source_path = config_manager.get_tdx_reader_root_dir()
            if source_path is None:
                raise ValueError("通达信根目录未配置")

        super().__init__(source_path)

        self.logger = logging.getLogger(__name__)
        self.storage_manager = StorageManager()
        # 不再使用 mootdx Reader，改用 tdx_asyncio 的异步读取器
        # 北证数据解码器（tdx_asyncio不支持北证，使用自定义解码器）
        self.bj_decoder = BjStockDecoder()
        self._last_save_metrics: Dict[str, Any] = {}
        self._last_standardize_rows: int = 0

    async def read(
        self,
        symbol: str,
        data_type: str = "day",
        market: str = "sh",
    ) -> Any:
        """
        读取通达信二进制数据

        Args:
            symbol: 品种代码（6位）
            data_type: 数据类型（'day', '5min', '1min'）
            market: 市场代码（'sh', 'sz', 'bj'）

        Returns:
            读取的原始数据

        Raises:
            ValueError: 参数不合法
            FileNotFoundError: 数据文件不存在
        """
        # 验证参数
        if data_type not in self.DATA_TYPE_MAPPING:
            raise ValueError(
                f"不支持的数据类型: {data_type}, "
                f"支持的类型: {list(self.DATA_TYPE_MAPPING.keys())}"
            )

        if market not in self.MARKET_CODES:
            raise ValueError(
                f"不支持的市场代码: {market}, " f"支持的市场: {list(self.MARKET_CODES.keys())}"
            )

        # 构建文件路径
        type_info = self.DATA_TYPE_MAPPING[data_type]
        subdir = type_info["subdir"]
        ext = type_info["ext"]

        # 路径格式: {tdx_root}/vipdoc/{market}/{subdir}/{market}{symbol}{ext}
        # 注意：通达信的文件名格式是 {market}{symbol}{ext}，例如 sh600000.day
        data_file = self.source_path / "vipdoc" / market / subdir / f"{market}{symbol}{ext}"

        if not data_file.exists():
            raise FileNotFoundError(f"数据文件不存在: {data_file}")

        try:
            # 判断是否为北证市场，使用不同的解码器
            if market == "bj":
                # 使用自定义北证解码器（放在线程池避免阻塞事件循环）
                if data_type == "day":
                    df = await asyncio.to_thread(self.bj_decoder.read_day_file, data_file)
                elif data_type == "5min":
                    df = await asyncio.to_thread(self.bj_decoder.read_5min_file, data_file)
                elif data_type == "1min":
                    df = await asyncio.to_thread(self.bj_decoder.read_1min_file, data_file)
                else:
                    raise ValueError(f"不支持的数据类型: {data_type}")

                self.logger.info("使用北证解码器读取: %s", data_file.name)
            else:
                # 使用 tdx_asyncio 异步读取器读取上证/深证数据
                if data_type == "day":
                    df = await read_day_data(data_file)
                elif data_type == "1min":
                    df = await read_minute_data(data_file)
                elif data_type == "5min":
                    df = await read_lc5_data(data_file)
                else:
                    raise ValueError(f"不支持的数据类型: {data_type}")

            if df is None or df.empty:
                return pd.DataFrame()

            # 添加元数据
            df.attrs["symbol"] = symbol
            df.attrs["data_type"] = data_type
            df.attrs["market"] = market
            df.attrs["interval"] = type_info["interval"]

            return df

        except Exception as e:
            self.logger.error("读取通达信数据失败: %s, 错误: %s", data_file, e)
            raise

    def standardize(self, raw_data: Any) -> pd.DataFrame:
        """同步标准化入口，兼容旧调用"""
        return self._standardize_impl(raw_data)

    async def standardize_async(self, raw_data: Any) -> pd.DataFrame:
        """异步标准化，避免阻塞事件循环"""
        return await asyncio.to_thread(self._standardize_impl, raw_data)

    def _standardize_impl(self, raw_data: Any) -> pd.DataFrame:
        if raw_data is None or (isinstance(raw_data, pd.DataFrame) and raw_data.empty):
            return pd.DataFrame()

        df = raw_data.copy()

        symbol = df.attrs.get("symbol", "")
        interval = df.attrs.get("interval", "1d")

        column_mapping = {
            "date": "datetime",
            "time": "datetime",
            "vol": "volume",
            "amount": "turnover",
        }

        rename_map: Dict[str, str] = {}
        for old_name, new_name in column_mapping.items():
            if old_name in df.columns:
                rename_map[old_name] = new_name

        if rename_map:
            df = df.rename(columns=rename_map)

        if "datetime" not in df.columns:
            if df.index.name is None or "date" in str(df.index.name).lower():
                df = df.reset_index()
                if len(df.columns) > 0:
                    first_col = str(df.columns[0])
                    if first_col not in ["datetime", "open", "high"]:
                        df = df.rename(columns={first_col: "datetime"})

        if df.columns.duplicated().any():
            self.logger.warning(
                "检测到重复列名: %s, 正在去重", df.columns[df.columns.duplicated()].tolist()
            )
            df = df.loc[:, ~df.columns.duplicated()]

        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
            df = df[df["datetime"].notna()].copy()
        else:
            df["datetime"] = pd.to_datetime(df.index, errors="coerce")
            df = df[df["datetime"].notna()].copy()

        numeric_columns = ["open", "high", "low", "close", "volume"]
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        df["symbol"] = symbol
        df["interval"] = interval

        if "datetime" in df.columns and isinstance(df, pd.DataFrame):
            df = df.sort_values("datetime")
            df = df.drop_duplicates(subset=["datetime"], keep="last")
            df = df.reset_index(drop=True)

        try:
            if isinstance(df, pd.DataFrame):
                self.validate_dataframe(df)
        except ValueError as e:
            self.logger.error("数据格式验证失败: %s", e)
            raise

        if isinstance(df, pd.DataFrame):
            self._last_standardize_rows = len(df)
            return df

        self._last_standardize_rows = 0
        return pd.DataFrame()

    def get_last_standardize_rows(self) -> int:
        return self._last_standardize_rows

    def get_last_save_metrics(self) -> Dict[str, Any]:
        return self._last_save_metrics

    def save(
        self, dataframe: pd.DataFrame, target_path: Optional[Path] = None, merge: bool = True
    ) -> bool:
        """
        保存标准化后的数据到Parquet格式

        Args:
            dataframe: 标准化后的DataFrame
            target_path: 目标保存路径（不使用，由StorageManager管理路径）
            merge: 是否使用增量更新模式（True=合并去重，False=覆盖）

        Returns:
            是否保存成功
        """
        if dataframe.empty:
            self.logger.warning("数据为空，跳过保存")
            self._last_save_metrics = {"mode": "skip_empty", "new_rows": 0}
            return False

        success = False
        file_path: Optional[Path] = None
        save_metrics: Dict[str, Any] = {
            "mode": "merge" if merge else "overwrite",
            "new_rows": int(len(dataframe)),
        }

        try:
            # 提取品种和周期信息
            symbol = dataframe["symbol"].iloc[0]
            interval = dataframe["interval"].iloc[0]
            save_metrics.update({"symbol": symbol, "interval": interval})

            if merge:
                query_start = time.perf_counter()
                existing_df = self.storage_manager.query_kline(symbol, interval)
                save_metrics["query_ms"] = (time.perf_counter() - query_start) * 1000
                existing_rows = int(len(existing_df)) if existing_df is not None else 0
                save_metrics["existing_rows"] = existing_rows

                if existing_df is not None and not existing_df.empty:
                    existing_df = existing_df.reset_index(drop=True)
                    dataframe = dataframe.reset_index(drop=True)

                    merge_start = time.perf_counter()
                    merged_df = pd.concat([existing_df, dataframe], ignore_index=True)
                    if "datetime" in merged_df.columns:
                        merged_df = merged_df.sort_values("datetime")
                        merged_df = merged_df.drop_duplicates(subset=["datetime"], keep="last")
                        merged_df = merged_df.reset_index(drop=True)
                    save_metrics["merge_ms"] = (time.perf_counter() - merge_start) * 1000

                    write_start = time.perf_counter()
                    file_path = self.storage_manager.save_kline(symbol, interval, merged_df)
                    save_metrics["write_ms"] = (time.perf_counter() - write_start) * 1000
                    save_metrics["result_rows"] = int(len(merged_df))

                    if file_path:
                        self.logger.info(
                            "数据增量保存成功: %s %s (合并模式，合并后共 %d 条)",
                            symbol,
                            interval,
                            len(merged_df),
                        )
                        success = True
                    else:
                        self.logger.error("数据增量保存失败: %s %s", symbol, interval)
                        success = False
                else:
                    write_start = time.perf_counter()
                    file_path = self.storage_manager.save_kline(symbol, interval, dataframe)
                    save_metrics["write_ms"] = (time.perf_counter() - write_start) * 1000
                    save_metrics["result_rows"] = int(len(dataframe))

                    if file_path:
                        self.logger.info("数据保存成功: %s %s (首次保存)", symbol, interval)
                        success = True
                    else:
                        self.logger.error("数据保存失败: %s %s", symbol, interval)
                        success = False
            else:
                write_start = time.perf_counter()
                file_path = self.storage_manager.save_kline(symbol, interval, dataframe)
                save_metrics["write_ms"] = (time.perf_counter() - write_start) * 1000
                save_metrics["existing_rows"] = 0
                save_metrics["result_rows"] = int(len(dataframe))

                if file_path:
                    self.logger.info(
                        "数据保存成功: %s %s -> %s (覆盖模式)", symbol, interval, file_path
                    )
                    success = True
                else:
                    self.logger.error("数据保存失败: %s %s", symbol, interval)
                    success = False

        except Exception as e:
            import traceback

            error_detail = traceback.format_exc()
            self.logger.error("❌ 保存数据时出错: %s", e, exc_info=True)
            print(f"❌ 保存失败: {e}")
            print(error_detail)
            save_metrics["error"] = str(e)
            success = False

        self._last_save_metrics = save_metrics
        return success

    async def save_async(
        self, dataframe: pd.DataFrame, target_path: Optional[Path] = None, merge: bool = True
    ) -> bool:
        """异步保存包装，避免阻塞事件循环"""
        return await asyncio.to_thread(self.save, dataframe, target_path, merge)

    async def read_batch(
        self,
        symbols: List[str],
        data_type: str = "day",
        market: str = "sh",
    ) -> Dict[str, pd.DataFrame]:
        """
        批量读取多个品种的数据

        Args:
            symbols: 品种代码列表
            data_type: 数据类型
            market: 市场代码

        Returns:
            品种代码到DataFrame的映射字典
        """
        results = {}

        for symbol in symbols:
            try:
                df = await self.read(symbol=symbol, data_type=data_type, market=market)
                if not df.empty:
                    results[symbol] = df
            except Exception as e:
                self.logger.error("读取 %s 失败: %s", symbol, e)

        self.logger.info("批量读取完成: 成功 %d/%d", len(results), len(symbols))
        return results


# ==============================================================================
# 第4部分：TDX动态执行器（原tdx_dynamic_executor.py）
# ==============================================================================


# ==================== 模块级worker函数（可pickle） ====================


class AdjustableAsyncSemaphore:
    """Semaphore with runtime-adjustable (and optional) limit."""

    def __init__(
        self, initial_limit: Optional[int], logger: Optional[logging.Logger] = None
    ) -> None:
        if initial_limit is not None and initial_limit <= 0:
            raise ValueError("initial_limit must be positive when provided")
        self._limit: Optional[int] = initial_limit
        self._in_use = 0
        self._cond = asyncio.Condition()
        self._logger = logger

    async def __aenter__(self):
        await self.acquire()
        return None

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()

    async def acquire(self) -> None:
        if self._limit is None:
            self._in_use += 1
            return
        async with self._cond:
            while self._in_use >= self._limit:
                await self._cond.wait()
            self._in_use += 1

    async def release(self) -> None:
        if self._limit is None:
            if self._in_use > 0:
                self._in_use -= 1
            return
        async with self._cond:
            if self._in_use > 0:
                self._in_use -= 1
            self._cond.notify_all()

    async def set_limit(self, new_limit: Optional[int]) -> Tuple[Optional[int], Optional[int], int]:
        if new_limit is not None and new_limit <= 0:
            new_limit = 1
        async with self._cond:
            old = self._limit
            self._limit = new_limit
            in_use = self._in_use
            self._cond.notify_all()
        if self._logger:
            self._logger.debug(
                "AdjustableAsyncSemaphore limit change: %s -> %s (in_use=%d)",
                old,
                new_limit,
                in_use,
            )
        return old, new_limit, in_use

    def snapshot(self) -> Dict[str, Optional[int]]:
        return {"limit": self._limit, "in_use": self._in_use}


def _tdx_worker_process(
    worker_id: int,
    symbols: List[str],
    data_type: str,
    market: str,
    tdx_dir_str: str,
    result_queue,
    stop_event,
    config_queue=None,
    initial_coroutines: Optional[int] = None,
):
    """Worker进程入口点（模块级函数，可以被pickle）"""
    import sys
    from pathlib import Path
    import asyncio

    sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

    # 在worker进程中创建reader实例
    worker_reader = TdxBinaryReader(Path(tdx_dir_str))

    # 运行worker的异步逻辑
    asyncio.run(
        _tdx_worker_async(
            worker_id,
            worker_reader,
            symbols,
            data_type,
            market,
            result_queue,
            stop_event,
            config_queue=config_queue,
            initial_coroutines=initial_coroutines,
        )
    )


async def _tdx_worker_async(
    worker_id: int,
    reader,
    symbols: List[str],
    data_type: str,
    market: str,
    result_queue,
    stop_event,
    config_queue=None,
    initial_coroutines: Optional[int] = None,
):
    """Worker的异步处理逻辑（模块级函数）"""
    import logging

    logger = logging.getLogger(__name__)

    logger.info("[Worker-%d] 启动，处理%d个品种", worker_id, len(symbols))

    throttling_enabled = config_queue is not None and initial_coroutines is not None
    semaphore: Optional[AdjustableAsyncSemaphore]
    if throttling_enabled:
        semaphore = AdjustableAsyncSemaphore(initial_coroutines, logger=logger)
        current_coroutines: Optional[int] = initial_coroutines
    else:
        semaphore = None
        current_coroutines = None
        logger.info("[Worker-%d] 协程限流已禁用，按符号全并发处理", worker_id)

    loop = asyncio.get_running_loop()
    cpu_count = os.cpu_count() or 4
    if throttling_enabled:
        base_limit = max(initial_coroutines or cpu_count, cpu_count)
    else:
        base_limit = max(len(symbols), cpu_count)
    executor_capacity = min(max(base_limit, cpu_count), 2048)
    thread_executors: List[concurrent.futures.ThreadPoolExecutor] = []
    thread_executor = concurrent.futures.ThreadPoolExecutor(max_workers=executor_capacity)
    thread_executors.append(thread_executor)
    loop.set_default_executor(thread_executor)
    logger.info(
        "[Worker-%d] 配置线程池: max_workers=%d (throttling=%s)",
        worker_id,
        executor_capacity,
        throttling_enabled,
    )

    async def _execute_symbol(symbol: str):
        if stop_event.is_set():
            return

        start_time = time.perf_counter()
        stage_metrics: Dict[str, Any] = {"symbol": symbol}
        try:
            # 1. 读取TDX数据
            read_start = time.perf_counter()
            raw_df = await reader.read(symbol=symbol, data_type=data_type, market=market)
            stage_metrics["read_ms"] = (time.perf_counter() - read_start) * 1000
            stage_metrics["raw_rows"] = int(len(raw_df)) if hasattr(raw_df, "__len__") else 0

            if raw_df.empty:
                stage_metrics["reason"] = "empty_raw"
                result_queue.put((symbol, False, stage_metrics, time.perf_counter() - start_time))
                return

            # 2. 标准化数据（添加symbol和interval列）
            standardize_start = time.perf_counter()
            standardized_df = await reader.standardize_async(raw_df)
            stage_metrics["standardize_ms"] = (time.perf_counter() - standardize_start) * 1000
            stage_metrics["standardized_rows"] = reader.get_last_standardize_rows()

            if standardized_df.empty:
                stage_metrics["reason"] = "standardize_empty"
                result_queue.put((symbol, False, stage_metrics, time.perf_counter() - start_time))
                return

            # 3. 保存标准化数据（异步包装避免阻塞事件循环）
            save_start = time.perf_counter()
            save_result = await reader.save_async(
                standardized_df,
                None,  # target_path
                True,  # merge=True (增量更新模式)
            )
            stage_metrics["save_ms"] = (time.perf_counter() - save_start) * 1000
            stage_metrics["save_details"] = reader.get_last_save_metrics()

            if save_result:
                result_queue.put((symbol, True, stage_metrics, time.perf_counter() - start_time))
            else:
                stage_metrics["reason"] = "save_failed"
                result_queue.put((symbol, False, stage_metrics, time.perf_counter() - start_time))

        except Exception as e:
            stage_metrics["reason"] = "exception"
            stage_metrics["error"] = str(e)
            result_queue.put((symbol, False, stage_metrics, time.perf_counter() - start_time))

    async def process_symbol(symbol: str):
        if semaphore is not None:
            async with semaphore:
                await _execute_symbol(symbol)
        else:
            await _execute_symbol(symbol)

    # 创建所有任务
    tasks = [asyncio.create_task(process_symbol(symbol)) for symbol in symbols]

    # 定期检查配置队列，动态调整
    monitor_task: Optional[asyncio.Task]

    if throttling_enabled:
        async def config_monitor():
            nonlocal current_coroutines, executor_capacity, thread_executor
            while not stop_event.is_set():
                try:
                    new_coroutines = config_queue.get_nowait()
                    if semaphore is None:
                        current_coroutines = new_coroutines
                        continue
                    if new_coroutines != current_coroutines:
                        old = current_coroutines
                        _, effective_limit, in_use = await semaphore.set_limit(new_coroutines)
                        current_coroutines = effective_limit
                        backlog = (
                            max(0, in_use - effective_limit)
                            if effective_limit is not None
                            else 0
                        )
                        logger.info(
                            "[Worker-%d] 📊 协程调整: %s → %s (in_use=%d, backlog=%d)",
                            worker_id,
                            old,
                            effective_limit,
                            in_use,
                            backlog,
                        )
                    if (
                        semaphore is not None
                        and effective_limit is not None
                        and effective_limit > executor_capacity
                    ):
                        new_capacity = min(max(effective_limit, cpu_count), 2048)
                        if new_capacity > executor_capacity:
                            logger.info(
                                "[Worker-%d] 扩容线程池: %d → %d",
                                worker_id,
                                executor_capacity,
                                new_capacity,
                            )
                            new_executor = concurrent.futures.ThreadPoolExecutor(
                                max_workers=new_capacity
                            )
                            thread_executors.append(new_executor)
                            loop.set_default_executor(new_executor)
                            executor_capacity = new_capacity
                except queue.Empty:
                    pass
                await asyncio.sleep(0.5)

        monitor_task = asyncio.create_task(config_monitor())
    else:
        monitor_task = None

    # 等待所有任务完成
    await asyncio.gather(*tasks, return_exceptions=True)
    if monitor_task is not None:
        monitor_task.cancel()

    logger.info("[Worker-%d] 完成", worker_id)
    for executor in thread_executors:
        executor.shutdown(wait=True)


# ==================== 数据类 ====================


@dataclass
class ExecutionResult:
    """执行结果"""

    success: bool
    symbol: str
    message: Optional[str] = None
    duration: float = 0.0
    details: Optional[Dict[str, Any]] = None


class TdxLocalReadTask(LocalProcessingTask):
    """TDX本地读取任务（带资源指标）"""

    def __init__(self, name: str, total_count: int):
        self.total_count = total_count
        super().__init__(name)

    def _define_metrics(self):
        metrics = super()._define_metrics()
        # 依据批量规模估算处理指标
        metrics.estimated_duration = max(0.5, self.total_count / 2000.0)
        metrics.estimated_workers = max(1, min(8, self.total_count // 500 or 1))
        return metrics

    def execute(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """占位执行，用于兼容LoadBalancer接口。"""
        return {
            "task": self.name,
            "total_count": self.total_count,
            "config": config,
        }


class TdxDynamicExecutor:
    """TDX动态执行器 - 支持动态并发调整

    支持：
    1. 每秒监控资源压力
    2. 动态调整协程数（进程数固定）
    3. 详细的调整历史记录
    """

    def __init__(
        self,
        tdx_dir: Path,  # TDX数据目录
        logger: Optional[logging.Logger] = None,
    ):
        self.tdx_dir = tdx_dir
        self.logger = logger or logging.getLogger(__name__)

        # 动态调整配置
        self.adjustment_interval = 0.3  # 0.3秒检查一次（实际调整由LoadBalancer控制）

        # 执行状态
        self.current_processes = 0
        self.current_coroutines_per_process = 0
        self.total_coroutines = 0
        self.adjustment_history = deque(maxlen=1800)
        self.last_run_summary: Optional[Dict[str, Any]] = None

        # LoadBalancer在主进程创建（用于调整监控）
        from ..load_balancer import get_load_balancer

        self.load_balancer = get_load_balancer()

    async def execute_batch(
        self,
        symbols: List[str],
        data_type: str = "day",
        market: str = "sh",
        initial_processes: int = 2,
        initial_coroutines: int = 20,
        enable_throttling: bool = True,
    ) -> Dict[str, ExecutionResult]:
        """
        执行批量读取（支持动态调整）

        Args:
            symbols: 品种列表
            data_type: 数据类型
            market: 市场代码
            initial_processes: 初始进程数（固定不变）
            initial_coroutines: 初始协程数（动态调整）

        Returns:
            {symbol: ExecutionResult}
        """
        total_count = len(symbols)
        overall_start = time.time()
        self.logger.info("=" * 80)
        self.logger.info("🚀 TdxDynamicExecutor 开始执行")
        self.logger.info("  - 品种数: %d", total_count)
        throttle_label = (
            str(initial_coroutines) if enable_throttling else "∞"
        )
        self.logger.info("  - 初始配置: %d进程 × %s协程", initial_processes, throttle_label)
        if enable_throttling:
            self.logger.info("  - 动态调整: 每%.1f秒", self.adjustment_interval)
        else:
            self.logger.info("  - 动态调整: 已禁用 (全并发读取)")
        self.logger.info("=" * 80)

        # 初始化配置
        self.current_processes = initial_processes
        if enable_throttling:
            self.current_coroutines_per_process = initial_coroutines
            self.total_coroutines = initial_processes * initial_coroutines
        else:
            self.current_coroutines_per_process = 0
            self.total_coroutines = total_count

        # 创建任务
        task = TdxLocalReadTask("tdx_batch_read", total_count)

        # 使用multiprocessing共享数据结构
        ctx = multiprocessing.get_context("spawn")
        result_queue = ctx.Queue()
        stop_event = ctx.Event()
        config_queue = ctx.Queue() if enable_throttling else None  # 用于传递动态配置

        # 平均分配symbols到各进程
        symbols_per_process = (total_count + self.current_processes - 1) // self.current_processes
        symbol_batches = [
            symbols[i : i + symbols_per_process] for i in range(0, total_count, symbols_per_process)
        ]

        self.logger.info(
            "📦 任务分配: %d个进程，每进程约%d个品种", len(symbol_batches), symbols_per_process
        )

        # 启动worker进程（使用模块级函数）
        processes = []
        for i, batch in enumerate(symbol_batches):
            per_process_limit = initial_coroutines if enable_throttling else None
            p = Process(
                target=_tdx_worker_process,  # 模块级函数，可以被pickle
                args=(
                    i,
                    batch,
                    data_type,
                    market,
                    str(self.tdx_dir),
                    result_queue,
                    stop_event,
                    config_queue,
                    per_process_limit,
                ),
            )
            p.start()
            processes.append(p)

        # 启动动态调整监控（如启用限流）
        adjustment_task: Optional[asyncio.Task]
        if enable_throttling:
            adjustment_task = asyncio.create_task(
                self._adjustment_monitor(task, config_queue, stop_event)
            )
        else:
            adjustment_task = None

        # 异步等待所有进程完成（不阻塞事件循环）
        while any(p.is_alive() for p in processes):
            await asyncio.sleep(0.5)  # 每0.5秒检查一次

        # 停止监控
        stop_event.set()
        if adjustment_task is not None:
            try:
                await asyncio.wait_for(adjustment_task, timeout=2.0)
            except asyncio.TimeoutError:
                self.logger.warning("调整监控停止超时")

        # 收集结果
        results = {}
        while not result_queue.empty():
            try:
                symbol, success, payload, duration = result_queue.get_nowait()
                message: Optional[str]
                details: Optional[Dict[str, Any]]
                if isinstance(payload, dict):
                    details = payload
                    message = payload.get("reason") if not success else None
                else:
                    details = None
                    message = str(payload) if payload is not None else None

                results[symbol] = ExecutionResult(
                    success=success,
                    symbol=symbol,
                    message=message,
                    duration=duration,
                    details=details,
                )
            except queue.Empty:
                break

        success_count = sum(1 for r in results.values() if r.success)
        self.logger.info("=" * 80)
        self.logger.info("✅ 执行完成: 成功%d/%d", success_count, total_count)
        self.logger.info("=" * 80)

        duration = time.time() - overall_start
        avg_speed = success_count / duration if duration > 0 else 0.0
        actions = Counter(entry.get("action") for entry in self.adjustment_history)
        per_process_coroutines = (
            self.current_coroutines_per_process if enable_throttling else 0
        )
        self.last_run_summary = {
            "total_symbols": total_count,
            "success": success_count,
            "duration": duration,
            "avg_symbols_per_sec": avg_speed,
            "final_total_coroutines": self.total_coroutines if enable_throttling else None,
            "final_coroutines_per_process": per_process_coroutines if enable_throttling else None,
            "processes": self.current_processes,
            "adjustment_counts": dict(actions),
            "throttling_enabled": enable_throttling,
        }
        total_label = (
            str(self.total_coroutines)
            if enable_throttling
            else f"无上限(≈{total_count})"
        )
        per_process_label = (
            str(per_process_coroutines) if enable_throttling else "无上限"
        )
        self.logger.info(
            "📈 运行摘要: 用时%.2fs, 平均%.2f个/秒, 最终并发=%s (每进程=%s), 调整统计=%s",
            duration,
            avg_speed,
            total_label,
            per_process_label,
            dict(actions),
        )

        return results

    async def _adjustment_monitor(
        self, task: TdxLocalReadTask, config_queue, stop_event: Event  # MPQueue
    ):
        """动态调整监控循环"""
        adjustment_count = 0
        call_count = 0  # 总调用次数（包括hold）
        start_time = time.time()

        self.logger.info("=" * 80)
        self.logger.info(
            "🚀 动态调整监控启动 (间隔%.3f秒 = %.0fms)",
            self.adjustment_interval,
            self.adjustment_interval * 1000,
        )
        self.logger.info("=" * 80)

        while not stop_event.is_set():
            sleep_start = time.time()
            self.logger.info(
                "⏰ 准备睡眠%.0fms (interval=%.3f)",
                self.adjustment_interval * 1000,
                self.adjustment_interval,
            )
            await asyncio.sleep(self.adjustment_interval)
            sleep_elapsed = (time.time() - sleep_start) * 1000
            self.logger.info("⏰ 实际睡眠%.0fms", sleep_elapsed)

            if stop_event.is_set():
                break

            call_count += 1
            call_timestamp = time.time()
            elapsed_since_start = call_timestamp - start_time

            # 调用LoadBalancer动态调整（传递进程数）
            # LoadBalancer内部会检查时间间隔，无需在此重复检查
            try:
                lb_start = time.time()
                config = self.load_balancer.get_optimal_config_with_adjustment(
                    task,
                    self.total_coroutines,
                    force_realtime=True,
                    processes=self.current_processes,
                )
                lb_elapsed = (time.time() - lb_start) * 1000

                action = config.get("action", "hold")
                new_coroutines_total = config.get("new_concurrency", self.total_coroutines)
                new_coroutines_per_process = new_coroutines_total // self.current_processes
                reason = config.get("reason", "")

                # 从config中获取资源指标（LoadBalancer已经读取过了）
                cpu = config.get("cpu_percent", 0)
                mem = config.get("memory_percent", 0)
                queue_depth = config.get("disk_queue_depth", 0)

                if new_coroutines_total != self.total_coroutines:
                    old_total = self.total_coroutines
                    self.current_coroutines_per_process = new_coroutines_per_process
                    self.total_coroutines = new_coroutines_total

                    # 广播新配置到所有worker
                    for _ in range(self.current_processes):
                        config_queue.put(new_coroutines_per_process)

                    adjustment_count += 1

                    self.logger.info(
                        "📊 [调用%d/调整%d] %.1fs ⏱️睡眠%.0fms+LB%.0fms 决策=%-8s 协程: %d → %d | CPU:%.1f%% 内存:%.1f%% 队列:%.1f",
                        call_count,
                        adjustment_count,
                        elapsed_since_start,
                        sleep_elapsed,
                        lb_elapsed,
                        action.upper(),
                        old_total,
                        new_coroutines_total,
                        cpu,
                        mem,
                        queue_depth,
                    )
                else:
                    # hold状态也输出，便于观察
                    self.logger.info(
                        "📊 [调用%d] %.1fs ⏱️睡眠%.0fms+LB%.0fms 决策=%-8s 协程: %d (不变) | CPU:%.1f%% 内存:%.1f%% 队列:%.1f",
                        call_count,
                        elapsed_since_start,
                        sleep_elapsed,
                        lb_elapsed,
                        action.upper(),
                        self.total_coroutines,
                        cpu,
                        mem,
                        queue_depth,
                    )

                self.adjustment_history.append(
                    {
                        "timestamp": call_timestamp,
                        "action": action,
                        "requested_concurrency": new_coroutines_total,
                        "applied_concurrency": self.total_coroutines,
                        "cpu_percent": cpu,
                        "memory_percent": mem,
                        "disk_queue_depth": queue_depth,
                        "disk_util_percent": config.get("disk_util_percent"),
                        "pressure_score": config.get("pressure_score"),
                        "reason": reason,
                        "lb_latency_ms": lb_elapsed,
                        "sleep_elapsed_ms": sleep_elapsed,
                    }
                )

            except Exception as e:
                self.logger.error("动态调整失败: %s", e, exc_info=True)

        elapsed = time.time() - start_time
        self.logger.info("=" * 80)
        self.logger.info(
            "📊 动态调整监控结束: 运行%.1f秒，总调用%d次，成功调整%d次",
            elapsed,
            call_count,
            adjustment_count,
        )
        self.logger.info("   平均调用间隔: %.3f秒", elapsed / call_count if call_count > 0 else 0)
        self.logger.info(
            "   调整成功率: %.1f%%", 100 * adjustment_count / call_count if call_count > 0 else 0
        )
        self.logger.info("=" * 80)


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = [
    # 基类
    "BaseReader",
    # 解码器
    "BjStockDecoder",
    # 读取器
    "TdxBinaryReader",
    # 执行器
    "TdxDynamicExecutor",
    "ExecutionResult",
]
