# -*- coding: utf-8 -*-
"""
通达信二进制数据读取器

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

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from mootdx.reader import Reader

from .base_reader import BaseReader
from .bj_decoder import BjStockDecoder
from ..config import config_manager
from ..data_quality import StorageManager


class TdxBinaryReader(BaseReader):
    """通达信二进制数据读取器"""

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
        if source_path is None:
            source_path = config_manager.get_tdx_reader_root_dir()
            if source_path is None:
                raise ValueError("通达信根目录未配置")

        super().__init__(source_path)

        self.logger = logging.getLogger(__name__)
        self.storage_manager = StorageManager()
        # Reader.factory() 返回标准读取器，需要传递 tdxdir 参数
        self.reader = Reader.factory(market="std", tdxdir=str(source_path))
        # 北证数据解码器（mootdx不支持北证，使用自定义解码器）
        self.bj_decoder = BjStockDecoder()

    def read(
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

        self.logger.info("读取通达信数据: %s", data_file)

        try:
            # 判断是否为北证市场，使用不同的解码器
            if market == "bj":
                # 使用自定义北证解码器
                if data_type == "day":
                    df = self.bj_decoder.read_day_file(data_file)
                elif data_type == "5min":
                    df = self.bj_decoder.read_5min_file(data_file)
                elif data_type == "1min":
                    df = self.bj_decoder.read_1min_file(data_file)
                else:
                    raise ValueError(f"不支持的数据类型: {data_type}")

                self.logger.info("使用北证解码器读取: %s", data_file.name)
            else:
                # 使用mootdx.reader读取上证/深证数据
                df = self.reader.daily(str(data_file))

            if df is None or df.empty:
                self.logger.warning("读取的数据为空: %s", data_file)
                return pd.DataFrame()

            # 添加元数据
            df.attrs["symbol"] = symbol
            df.attrs["data_type"] = data_type
            df.attrs["market"] = market
            df.attrs["interval"] = type_info["interval"]

            self.logger.info("成功读取 %d 条数据: %s", len(df), data_file)
            return df

        except Exception as e:
            self.logger.error("读取通达信数据失败: %s, 错误: %s", data_file, e)
            raise

    def standardize(self, raw_data: Any) -> pd.DataFrame:
        """
        标准化通达信数据格式

        Args:
            raw_data: 原始数据（mootdx.reader返回的DataFrame）

        Returns:
            标准化后的DataFrame
        """
        if raw_data is None or (isinstance(raw_data, pd.DataFrame) and raw_data.empty):
            return pd.DataFrame()

        df = raw_data.copy()

        # 获取元数据
        symbol = df.attrs.get("symbol", "")
        interval = df.attrs.get("interval", "1d")

        # mootdx.reader 返回的数据：index是日期，列是 open, high, low, close, amount, volume
        # 需要将 index 转换为 datetime 列
        if df.index.name is None or "date" in str(df.index.name).lower():
            df = df.reset_index()
            # 第一列是日期
            if len(df.columns) > 0:
                first_col = str(df.columns[0])  # 确保是字符串类型
                if first_col not in ["datetime", "open", "high"]:
                    df = df.rename(columns={first_col: "datetime"})

        # 标准化列名
        column_mapping = {
            "date": "datetime",
            "time": "datetime",
            "vol": "volume",
            "amount": "turnover",
        }

        df = df.rename(columns=column_mapping)

        # 确保datetime列是datetime类型
        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
            # 删除无效日期
            df = df[df["datetime"].notna()].copy()
        else:
            # 如果没有 datetime 列，尝试从 index 获取
            df["datetime"] = pd.to_datetime(df.index, errors="coerce")
            df = df[df["datetime"].notna()].copy()

        # 确保数值列是float类型
        numeric_columns = ["open", "high", "low", "close", "volume"]
        for col in numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # 添加品种和周期信息
        df["symbol"] = symbol
        df["interval"] = interval

        # 按时间排序
        if "datetime" in df.columns:
            # 确保 df 是 DataFrame 类型，避免类型推断问题
            if isinstance(df, pd.DataFrame):
                df = df.sort_values("datetime")

        # 验证格式
        try:
            # 确保传入的是 DataFrame
            if isinstance(df, pd.DataFrame):
                self.validate_dataframe(df)
        except ValueError as e:
            self.logger.error("数据格式验证失败: %s", e)
            raise

        self.logger.info("数据标准化完成: %d 条记录", len(df))
        # 确保返回的是 DataFrame
        if isinstance(df, pd.DataFrame):
            return df
        else:
            # 如果不是 DataFrame，返回空 DataFrame
            return pd.DataFrame()

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
            return False

        try:
            # 提取品种和周期信息
            symbol = dataframe["symbol"].iloc[0]
            interval = dataframe["interval"].iloc[0]

            # 选择保存模式
            if merge:
                # 增量更新：合并现有数据和新数据，去重
                # 先查询现有数据
                existing_df = self.storage_manager.query_kline(symbol, interval)
                
                if existing_df is not None and not existing_df.empty:
                    # 合并新旧数据
                    merged_df = pd.concat([existing_df, dataframe], ignore_index=True)
                    
                    # 按 datetime 排序并去重
                    if "datetime" in merged_df.columns:
                        merged_df = merged_df.sort_values("datetime")
                        merged_df = merged_df.drop_duplicates(subset=["datetime"], keep="last")
                    
                    # 保存合并后的数据
                    file_path = self.storage_manager.save_kline(symbol, interval, merged_df)
                    if file_path:
                        self.logger.info(
                            "数据增量保存成功: %s %s (合并模式，合并后共 %d 条)", 
                            symbol, interval, len(merged_df)
                        )
                        return True
                    else:
                        self.logger.error("数据增量保存失败: %s %s", symbol, interval)
                        return False
                else:
                    # 如果没有现有数据，直接保存
                    file_path = self.storage_manager.save_kline(symbol, interval, dataframe)
                    if file_path:
                        self.logger.info("数据保存成功: %s %s (首次保存)", symbol, interval)
                        return True
                    else:
                        self.logger.error("数据保存失败: %s %s", symbol, interval)
                        return False
            else:
                # 覆盖模式：直接覆盖原有数据
                file_path = self.storage_manager.save_kline(symbol, interval, dataframe)
                if file_path:
                    self.logger.info(
                        "数据保存成功: %s %s -> %s (覆盖模式)", symbol, interval, file_path
                    )
                    return True
                else:
                    self.logger.error("数据保存失败: %s %s", symbol, interval)
                    return False

        except Exception as e:
            self.logger.error("保存数据时出错: %s", e, exc_info=True)
            return False

    def read_batch(
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
                df = self.read(symbol=symbol, data_type=data_type, market=market)
                if not df.empty:
                    results[symbol] = df
            except Exception as e:
                self.logger.error("读取 %s 失败: %s", symbol, e)

        self.logger.info("批量读取完成: 成功 %d/%d", len(results), len(symbols))
        return results

    def process_batch(
        self,
        symbols: List[str],
        data_type: str = "day",
        market: str = "sh",
        progress_callback=None,
        max_workers: int = 4,
        stop_check=None,
    ) -> Dict[str, bool]:
        """
        批量处理多个品种的数据（读取 -> 标准化 -> 保存）

        Args:
            symbols: 品种代码列表
            data_type: 数据类型
            market: 市场代码
            progress_callback: 进度回调函数 callback(current, total, symbol, success)
            max_workers: 最大线程数
            stop_check: 停止检查函数，返回True时停止处理

        Returns:
            品种代码到处理结果的映射字典
        """
        results = {}
        total = len(symbols)

        # 如果只有少量品种或max_workers=1，使用单线程
        if total <= 5 or max_workers == 1:
            for i, symbol in enumerate(symbols, 1):
                # 检查停止标志
                if stop_check and stop_check():
                    self.logger.info("检测到停止标志，中断处理")
                    break

                try:
                    # 读取数据
                    raw_data = self.read(symbol=symbol, data_type=data_type, market=market)

                    # 标准化
                    df = self.standardize(raw_data)

                    # 保存
                    success = self.save(df)
                    results[symbol] = success

                    # 进度回调
                    if progress_callback:
                        progress_callback(i, total, symbol, success)

                except Exception as e:
                    self.logger.error("处理 %s 失败: %s", symbol, e)
                    results[symbol] = False
                    if progress_callback:
                        progress_callback(i, total, symbol, False)
        else:
            # 多线程处理
            from concurrent.futures import ThreadPoolExecutor, as_completed
            import threading

            results_lock = threading.Lock()
            completed_count = [0]  # 使用列表以便在闭包中修改

            def process_one_symbol(symbol: str) -> tuple:
                """处理单个品种"""
                try:
                    raw_data = self.read(symbol=symbol, data_type=data_type, market=market)
                    df = self.standardize(raw_data)
                    success = self.save(df)
                    return (symbol, success)
                except Exception as e:
                    self.logger.error("处理 %s 失败: %s", symbol, e)
                    return (symbol, False)

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有任务
                future_to_symbol = {
                    executor.submit(process_one_symbol, symbol): symbol for symbol in symbols
                }

                # 处理完成的任务
                for future in as_completed(future_to_symbol):
                    # 检查停止标志
                    if stop_check and stop_check():
                        self.logger.info("检测到停止标志，中断批量处理")
                        # 取消未开始的任务
                        for f in future_to_symbol:
                            if not f.done():
                                f.cancel()
                        break

                    symbol, success = future.result()

                    with results_lock:
                        results[symbol] = success
                        completed_count[0] += 1

                        # 进度回调
                        if progress_callback:
                            progress_callback(completed_count[0], total, symbol, success)

        success_count = sum(1 for v in results.values() if v)
        self.logger.info("批量处理完成: 成功 %d/%d", success_count, len(symbols))

        return results
