# -*- coding: utf-8 -*-
"""
Parquet格式存储管理模块

负责K线数据的存储和查询，使用Parquet列式压缩格式：
- 数据保存：将K线数据保存为Parquet文件
- 数据查询：根据品种、周期、时间范围查询数据
- 数据管理：列出所有品种、删除数据等
- 分区策略：按品种和周期分区存储
"""

import logging
import shutil
from datetime import date, datetime
from pathlib import Path  # noqa: TC003
from typing import Dict, List, Optional, Union

import pandas as pd

from .config import config_manager


class StorageManager:
    """存储管理器"""

    def __init__(self):
        """初始化存储管理器"""
        self.data_dir = config_manager.get_data_dir()
        self.logger = logging.getLogger(__name__)

        # 确保数据目录存在
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def save_kline(self, symbol: str, interval: str, dataframe: pd.DataFrame) -> Path:
        """
        保存K线数据到Parquet文件

        Args:
            symbol: 品种代码
            interval: K线周期
            dataframe: K线数据DataFrame

        Returns:
            保存的文件路径
        """
        try:
            # 创建品种目录
            symbol_dir = self.data_dir / symbol
            symbol_dir.mkdir(parents=True, exist_ok=True)

            # 创建周期目录
            interval_dir = symbol_dir / interval
            interval_dir.mkdir(parents=True, exist_ok=True)

            # 文件路径
            file_path = interval_dir / "data.parquet"

            # 标准化数据格式
            df = self._standardize_dataframe(dataframe, symbol, interval)

            # 保存为Parquet文件
            df.to_parquet(file_path, index=False, engine="pyarrow")

            self.logger.info("成功保存 %s %s 数据到: %s", symbol, interval, file_path)
            return file_path

        except Exception as e:
            self.logger.error("保存 %s %s 数据失败: %s", symbol, interval, e)
            raise

    def query_kline(
        self,
        symbol: str,
        interval: str,
        start_date: Optional[Union[str, date]] = None,
        end_date: Optional[Union[str, date]] = None,
    ) -> Optional[pd.DataFrame]:
        """
        查询K线数据

        Args:
            symbol: 品种代码
            interval: K线周期
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            K线数据DataFrame，如果不存在则返回None
        """
        try:
            # 构建文件路径
            file_path = self.data_dir / symbol / interval / "data.parquet"

            if not file_path.exists():
                self.logger.warning("数据文件不存在: %s", file_path)
                return None

            # 读取Parquet文件
            df = pd.read_parquet(file_path)

            # 日期过滤
            if start_date or end_date:
                df = self._filter_by_date_range(df, start_date, end_date)

            self.logger.info(
                "成功查询 %s %s 数据: %d 条记录", symbol, interval, len(df)
            )
            return df

        except (OSError, pd.errors.ParserError) as e:
            self.logger.error("查询 %s %s 数据失败: %s", symbol, interval, e)
            return None

    def list_symbols(self) -> List[str]:
        """
        列出所有品种

        Returns:
            品种代码列表
        """
        try:
            symbols = []
            for item in self.data_dir.iterdir():
                if item.is_dir():
                    symbols.append(item.name)

            self.logger.info("发现 %d 个品种", len(symbols))
            return sorted(symbols)

        except OSError as e:
            self.logger.error("列出品种失败: %s", e)
            return []

    def list_intervals(self, symbol: str) -> List[str]:
        """
        列出指定品种的所有周期

        Args:
            symbol: 品种代码

        Returns:
            周期列表
        """
        try:
            symbol_dir = self.data_dir / symbol
            if not symbol_dir.exists():
                return []

            intervals = []
            for item in symbol_dir.iterdir():
                if item.is_dir():
                    intervals.append(item.name)

            return sorted(intervals)

        except OSError as e:
            self.logger.error("列出 %s 周期失败: %s", symbol, e)
            return []

    def get_data_info(self, symbol: str, interval: str) -> Optional[Dict]:
        """
        获取数据文件信息

        Args:
            symbol: 品种代码
            interval: K线周期

        Returns:
            数据信息字典
        """
        try:
            file_path = self.data_dir / symbol / interval / "data.parquet"

            if not file_path.exists():
                return None

            # 读取文件信息
            df = pd.read_parquet(file_path)

            info = {
                "symbol": symbol,
                "interval": interval,
                "file_path": str(file_path),
                "file_size": file_path.stat().st_size,
                "record_count": len(df),
                "columns": list(df.columns),
                "start_date": (
                    df["datetime"].min() if "datetime" in df.columns else None
                ),
                "end_date": (
                    df["datetime"].max() if "datetime" in df.columns else None
                ),
                "last_modified": datetime.fromtimestamp(file_path.stat().st_mtime),
            }

            return info

        except (OSError, pd.errors.ParserError) as e:
            self.logger.error("获取 %s %s 数据信息失败: %s", symbol, interval, e)
            return None

    def delete_data(self, symbol: str, interval: Optional[str] = None) -> bool:
        """
        删除数据

        Args:
            symbol: 品种代码
            interval: K线周期，如果为None则删除整个品种

        Returns:
            是否删除成功
        """
        try:
            if interval:
                # 删除指定周期数据
                interval_dir = self.data_dir / symbol / interval
                if interval_dir.exists():
                    shutil.rmtree(interval_dir)
                    self.logger.info("删除 %s %s 数据成功", symbol, interval)
            else:
                # 删除整个品种数据
                symbol_dir = self.data_dir / symbol
                if symbol_dir.exists():
                    shutil.rmtree(symbol_dir)
                    self.logger.info("删除 %s 所有数据成功", symbol)

            return True

        except OSError as e:
            self.logger.error("删除 %s %s 数据失败: %s", symbol, interval, e)
            return False

    def backup_data(self, symbol: str, interval: str, backup_dir: Path) -> bool:
        """
        备份数据

        Args:
            symbol: 品种代码
            interval: K线周期
            backup_dir: 备份目录

        Returns:
            是否备份成功
        """
        try:
            source_path = self.data_dir / symbol / interval / "data.parquet"

            if not source_path.exists():
                self.logger.warning("源文件不存在: %s", source_path)
                return False

            # 创建备份目录
            backup_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{symbol}_{interval}_backup_{timestamp}.parquet"
            backup_path = backup_dir / filename

            # 复制文件
            shutil.copy2(source_path, backup_path)

            self.logger.info("备份 %s %s 数据到: %s", symbol, interval, backup_path)
            return True

        except OSError as e:
            self.logger.error("备份 %s %s 数据失败: %s", symbol, interval, e)
            return False

    def merge_data(self, symbol: str, interval: str, new_data: pd.DataFrame) -> bool:
        """
        合并新数据到现有数据

        Args:
            symbol: 品种代码
            interval: K线周期
            new_data: 新数据DataFrame

        Returns:
            是否合并成功
        """
        try:
            # 标准化新数据
            new_data = self._standardize_dataframe(new_data, symbol, interval)

            # 读取现有数据
            existing_data = self.query_kline(symbol, interval)

            if existing_data is None or existing_data.empty:
                # 如果没有现有数据，直接保存新数据
                self.save_kline(symbol, interval, new_data)
            else:
                # 合并数据
                merged_data = pd.concat([existing_data, new_data], ignore_index=True)

                # 去重（基于datetime列）
                if "datetime" in merged_data.columns:
                    merged_data = merged_data.drop_duplicates(
                        subset=["datetime"], keep="last"
                    )
                    merged_data = merged_data.sort_values("datetime")

                # 保存合并后的数据
                self.save_kline(symbol, interval, merged_data)

            self.logger.info("成功合并 %s %s 数据", symbol, interval)
            return True

        except (OSError, pd.errors.ParserError, ValueError) as e:
            self.logger.error("合并 %s %s 数据失败: %s", symbol, interval, e)
            return False

    def get_storage_stats(self) -> Dict:
        """
        获取存储统计信息

        Returns:
            存储统计字典
        """
        try:
            stats = {
                "total_symbols": 0,
                "total_files": 0,
                "total_size": 0,
                "symbols": [],
            }

            for symbol_dir in self.data_dir.iterdir():
                if symbol_dir.is_dir():
                    symbol_stats = {
                        "symbol": symbol_dir.name,
                        "intervals": [],
                        "total_size": 0,
                    }

                    for interval_dir in symbol_dir.iterdir():
                        if interval_dir.is_dir():
                            file_path = interval_dir / "data.parquet"
                            if file_path.exists():
                                file_size = file_path.stat().st_size
                                symbol_stats["intervals"].append(
                                    {"interval": interval_dir.name, "size": file_size}
                                )
                                symbol_stats["total_size"] += file_size
                                stats["total_size"] += file_size
                                stats["total_files"] += 1

                    stats["symbols"].append(symbol_stats)
                    stats["total_symbols"] += 1

            return stats

        except OSError as e:
            self.logger.error("获取存储统计失败: %s", e)
            return {}

    def _standardize_dataframe(
        self, df: pd.DataFrame, symbol: str, interval: str
    ) -> pd.DataFrame:
        """
        标准化DataFrame格式

        Args:
            df: 原始DataFrame
            symbol: 品种代码
            interval: K线周期

        Returns:
            标准化后的DataFrame
        """
        # 添加品种和周期信息
        df = df.copy()
        df["symbol"] = symbol
        df["interval"] = interval

        # 确保datetime列是datetime类型
        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"])

        # 确保数值列是float类型
        numeric_columns = ["open", "high", "low", "close", "volume"]
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # 按时间排序
        if "datetime" in df.columns:
            df = df.sort_values("datetime")

        return df

    def _filter_by_date_range(
        self,
        df: pd.DataFrame,
        start_date: Optional[Union[str, date]],
        end_date: Optional[Union[str, date]],
    ) -> pd.DataFrame:
        """
        按日期范围过滤数据

        Args:
            df: 原始DataFrame
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            过滤后的DataFrame
        """
        if "datetime" not in df.columns:
            return df

        # 转换日期格式
        if start_date:
            if isinstance(start_date, str):
                start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            mask = df["datetime"].dt.date >= start_date
            df = df.loc[mask]

        if end_date:
            if isinstance(end_date, str):
                end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
            mask = df["datetime"].dt.date <= end_date
            df = df.loc[mask]

        return df
