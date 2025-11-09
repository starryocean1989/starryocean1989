# -*- coding: utf-8 -*-
"""
TDX二进制数据读取器

读取通达信软件本地保存的二进制K线数据文件，支持：
- 日线数据: vipdoc/{market}/lday/{symbol}.day
- 5分钟线: vipdoc/{market}/fzline/{symbol}.lc5
- 1分钟线: vipdoc/{market}/minline/{symbol}.lc1

市场代码：
- sh: 上证
- sz: 深证
- bj: 北证
"""

import asyncio
import logging
import struct
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Union, Any

import pandas as pd

# 导入native_iocp（支持降级）
try:
    from backend.infrastructure.native.native_iocp.compat import aopen as compat_aopen  # type: ignore

    IOCP_AVAILABLE = True
except ImportError:
    try:
        import aiofiles

        async def compat_aopen(filepath: Union[str, Path], mode: str = "r", **kwargs: Any) -> Any:
            """兼容的异步文件打开函数"""
            return await aiofiles.open(filepath, mode, **kwargs)

        IOCP_AVAILABLE = False
    except ImportError:
        compat_aopen = None  # type: ignore
        IOCP_AVAILABLE = False

# 导入native_compute（支持降级）
try:
    from backend.infrastructure.native.native_compute import (
        batch_compute,
        COMPUTE_AVAILABLE,
    )

    _USE_NATIVE_COMPUTE = COMPUTE_AVAILABLE
except ImportError:
    batch_compute = None  # type: ignore
    _USE_NATIVE_COMPUTE = False

# 导入native_conversion（支持降级）
try:
    from backend.infrastructure.native.native_conversion import (
        batch_convert,
        CONVERSION_AVAILABLE,
    )

    _USE_NATIVE_CONVERSION = CONVERSION_AVAILABLE
except ImportError:
    batch_convert = None  # type: ignore
    _USE_NATIVE_CONVERSION = False

from .base import BaseReader
from .bj_decoder import BjStockDecoder


class TdxBinaryReader(BaseReader):
    """通达信二进制数据读取器

    读取通达信软件本地保存的二进制K线数据文件，支持：
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
    DATA_TYPE_PATHS = {
        "day": "lday",
        "5min": "fzline",
        "1min": "minline",
    }

    # 文件扩展名
    FILE_EXTENSIONS = {
        "day": ".day",
        "5min": ".lc5",
        "1min": ".lc1",
    }

    # 日线数据结构：32字节
    DAY_STRUCT = "<IIIIIfII"  # 日期(I), 开(I), 高(I), 低(I), 收(I), 成交额(f), 成交量(I), 保留(I)
    DAY_RECORD_SIZE = 32

    # 分钟线数据结构：32字节
    MIN_STRUCT = (
        "<HHfffffII"  # 日期(H), 时间(H), 开(f), 高(f), 低(f), 收(f), 成交额(f), 成交量(I), 保留(I)
    )
    MIN_RECORD_SIZE = 32

    def __init__(self, tdx_root_path: Optional[Union[str, Path]] = None):
        """初始化TDX二进制读取器

        Args:
            tdx_root_path: 通达信软件根目录，如果为None则使用默认路径
        """
        super().__init__()

        # 获取TDX根目录
        if tdx_root_path:
            self.tdx_root = Path(tdx_root_path)
        else:
            # 默认路径
            self.tdx_root = Path("C:/new_tdx")

        self.logger.info(
            f"TDX根目录: {self.tdx_root}", extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"}
        )

    def _get_file_path(self, symbol: str, data_type: str, market: str) -> Path:
        """获取数据文件路径

        Args:
            symbol: 品种代码
            data_type: 数据类型
            market: 市场

        Returns:
            文件路径
        """
        # vipdoc/{market}/{subdir}/{symbol}{ext}
        subdir = self.DATA_TYPE_PATHS.get(data_type, "lday")
        ext = self.FILE_EXTENSIONS.get(data_type, ".day")

        file_path = self.tdx_root / "vipdoc" / market / subdir / f"{symbol}{ext}"
        return file_path

    def read_single(self, symbol: str, data_type: str, market: str) -> pd.DataFrame:
        """读取单个品种的数据（同步版本，使用native_iocp优化）

        Args:
            symbol: 品种代码
            data_type: 数据类型（day/5min/1min）
            market: 市场（sh/sz/bj）

        Returns:
            DataFrame
        """
        # 🚀 性能优化：同步版本直接调用异步版本，使用native_iocp优化
        # 使用asyncio.run()在同步方法中调用异步方法
        try:
            loop = asyncio.get_running_loop()
            # 如果事件循环已经在运行，在新线程中运行
            import concurrent.futures
            future = concurrent.futures.Future()
            def _run():
                try:
                    result = asyncio.run(self.read_single_async(symbol, data_type, market))
                    future.set_result(result)
                except Exception as e:
                    future.set_exception(e)
            thread = threading.Thread(target=_run)
            thread.start()
            thread.join()
            return future.result()
        except RuntimeError:
            # 如果没有运行中的事件循环，直接使用asyncio.run()
            return asyncio.run(self.read_single_async(symbol, data_type, market))

    async def read_single_async(self, symbol: str, data_type: str, market: str) -> pd.DataFrame:
        """读取单个品种的数据（异步版本，native_iocp集成）

        Args:
            symbol: 品种代码
            data_type: 数据类型
            market: 市场

        Returns:
            DataFrame
        """
        start_time = time.time()

        file_path = self._get_file_path(symbol, data_type, market)

        self.logger.debug(
            f"[TdxBinaryReader] 开始异步读取: symbol={symbol}, data_type={data_type}, market={market}, file_path={file_path}",
            extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
        )

        if not file_path.exists():
            self.logger.debug(
                f"[TdxBinaryReader] 文件不存在: {file_path}",
                extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
            )
            return pd.DataFrame()

        try:
            # 使用native_iocp异步读取（如可用）
            read_start_time = time.time()
            if compat_aopen:
                self.logger.debug(
                    "[TdxBinaryReader] 使用native_iocp异步读取",
                    extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
                )
                async with await compat_aopen(file_path, "rb") as f:
                    raw_data = await f.read()
            else:
                # 降级到同步读取
                self.logger.debug(
                    "[TdxBinaryReader] 降级到同步读取（compat_aopen不可用）",
                    extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
                )
                with open(file_path, "rb") as f:
                    raw_data = f.read()
            read_elapsed = time.time() - read_start_time

            file_size = len(raw_data)
            self.logger.debug(
                f"[TdxBinaryReader] 文件异步读取完成: 文件大小={file_size} bytes, 耗时={read_elapsed:.3f}s",
                extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
            )

            # 解码数据
            decode_start_time = time.time()
            df = self._decode_binary(raw_data, data_type)
            decode_elapsed = time.time() - decode_start_time

            # 如果是北证股票，应用解码器
            if market == "bj" and BjStockDecoder.is_bj_stock(symbol):
                bj_decode_start_time = time.time()
                df = BjStockDecoder.decode_bj_stock(df)
                bj_decode_elapsed = time.time() - bj_decode_start_time
                self.logger.debug(
                    f"[TdxBinaryReader] 北证股票解码完成: 耗时={bj_decode_elapsed:.3f}s",
                    extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
                )

            total_elapsed = time.time() - start_time
            record_count = len(df)
            self.logger.debug(
                f"[TdxBinaryReader] 异步读取成功: {symbol}/{data_type}, 记录数={record_count}, "
                f"解码耗时={decode_elapsed:.3f}s, 总耗时={total_elapsed:.3f}s",
                extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
            )
            return df

        except Exception as e:
            total_elapsed = time.time() - start_time
            self.logger.error(
                f"[TdxBinaryReader] ❌ 异步读取文件失败: {file_path}, 错误: {e}, 耗时={total_elapsed:.3f}s",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": "tdx_data_read"},
            )
            self.logger.debug(
                f"[TdxBinaryReader] 异常类型: {type(e).__name__}, 异常详情: {str(e)}",
                extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
            )
            return pd.DataFrame()

    def _decode_binary(self, raw_data: bytes, data_type: str) -> pd.DataFrame:
        """解码二进制数据

        Args:
            raw_data: 原始二进制数据
            data_type: 数据类型

        Returns:
            DataFrame
        """
        start_time = time.time()
        data_size = len(raw_data)

        self.logger.debug(
            f"[TdxBinaryReader] 开始解码二进制数据: data_type={data_type}, 数据大小={data_size} bytes",
            extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
        )

        if data_type == "day":
            df = self._decode_day_data(raw_data)
        elif data_type in ["5min", "1min"]:
            df = self._decode_min_data(raw_data)
        else:
            self.logger.warning(
                f"[TdxBinaryReader] ⚠️ 不支持的数据类型: {data_type}",
                extra={"log_type": "ALERT", "scenario": "tdx_data_read"},
            )
            return pd.DataFrame()

        elapsed = time.time() - start_time
        record_count = len(df)
        self.logger.debug(
            f"[TdxBinaryReader] 解码完成: data_type={data_type}, 记录数={record_count}, 耗时={elapsed:.3f}s",
            extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
        )
        return df

    def _decode_day_data(self, raw_data: bytes) -> pd.DataFrame:
        """解码日线数据

        Args:
            raw_data: 原始二进制数据

        Returns:
            DataFrame
        """
        records = []
        record_count = len(raw_data) // self.DAY_RECORD_SIZE

        if record_count == 0:
            return pd.DataFrame()

        # 🚀 性能优化：使用native_compute批量处理价格转换
        # 批量收集所有价格值
        date_ints = []
        open_prices = []
        high_prices = []
        low_prices = []
        close_prices = []
        amounts = []
        volumes = []

        # 🚀 性能优化：使用struct.unpack_from避免内存切片拷贝
        # 直接从未切片的内存缓冲区解包，避免每次循环创建新的bytes对象
        for i in range(record_count):
            offset = i * self.DAY_RECORD_SIZE

            # 边界检查：确保有足够的数据
            if offset + self.DAY_RECORD_SIZE > len(raw_data):
                break

            try:
                # 使用unpack_from直接解包，避免切片拷贝
                (
                    date_int,
                    open_price,
                    high_price,
                    low_price,
                    close_price,
                    amount,
                    volume,
                    reserved,
                ) = struct.unpack_from(self.DAY_STRUCT, raw_data, offset)

                # 收集数据
                date_ints.append(date_int)
                open_prices.append(open_price)
                high_prices.append(high_price)
                low_prices.append(low_price)
                close_prices.append(close_price)
                amounts.append(amount)
                volumes.append(volume)
            except Exception as e:
                self.logger.debug(
                    f"解析日线记录失败: {e}",
                    extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
                )
                continue

        # 批量除以1000.0（使用native_compute）
        if len(open_prices) > 0:
            if _USE_NATIVE_COMPUTE and batch_compute is not None:
                compute_func = batch_compute
                try:
                    open_prices = compute_func(open_prices, "divide_by_1000")  # type: ignore[call-arg]
                    high_prices = compute_func(high_prices, "divide_by_1000")  # type: ignore[call-arg]
                    low_prices = compute_func(low_prices, "divide_by_1000")  # type: ignore[call-arg]
                    close_prices = compute_func(close_prices, "divide_by_1000")  # type: ignore[call-arg]
                except Exception as exc:
                    self.logger.debug(
                        "[TdxBinaryReader] native_compute失败，降级到Python实现: %s",
                        exc,
                        extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
                    )
                    open_prices = [p / 1000.0 for p in open_prices]
                    high_prices = [p / 1000.0 for p in high_prices]
                    low_prices = [p / 1000.0 for p in low_prices]
                    close_prices = [p / 1000.0 for p in close_prices]
            else:
                open_prices = [p / 1000.0 for p in open_prices]
                high_prices = [p / 1000.0 for p in high_prices]
                low_prices = [p / 1000.0 for p in low_prices]
                close_prices = [p / 1000.0 for p in close_prices]

        # 🚀 性能优化：使用native_conversion批量转换日期整数到字符串，然后批量解析
        # 批量转换日期整数到字符串
        if _USE_NATIVE_CONVERSION and batch_convert is not None:
            convert_func = batch_convert
            try:
                date_strs = convert_func(date_ints, str)  # type: ignore[call-arg]
            except Exception as exc:
                self.logger.debug(
                    "[TdxBinaryReader] native_conversion批量转换失败，降级到Python实现: %s",
                    exc,
                    extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
                )
                date_strs = [str(d) for d in date_ints]
        else:
            date_strs = [str(d) for d in date_ints]

        # 🚀 性能优化：批量提取年、月、日字符串切片，然后批量转换为整数
        # 批量提取年、月、日字符串
        year_strs = []
        month_strs = []
        day_strs = []
        valid_indices = []  # 记录有效日期的索引

        for i, date_str in enumerate(date_strs):
            if len(date_str) == 8:
                year_strs.append(date_str[0:4])
                month_strs.append(date_str[4:6])
                day_strs.append(date_str[6:8])
                valid_indices.append(i)

        # 🚀 使用native_conversion批量转换字符串到整数
        if len(year_strs) > 0:
            if _USE_NATIVE_CONVERSION and batch_convert is not None:
                convert_func = batch_convert
                try:
                    years = convert_func(year_strs, int)  # type: ignore[call-arg]
                    months = convert_func(month_strs, int)  # type: ignore[call-arg]
                    days = convert_func(day_strs, int)  # type: ignore[call-arg]
                except Exception as e:
                    # 降级到Python实现
                    self.logger.debug(
                        f"[TdxBinaryReader] native_conversion批量转换失败，降级到Python实现: {e}",
                        extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
                    )
                    years = [int(s) for s in year_strs]
                    months = [int(s) for s in month_strs]
                    days = [int(s) for s in day_strs]
            else:
                years = [int(s) for s in year_strs]
                months = [int(s) for s in month_strs]
                days = [int(s) for s in day_strs]

            # 构建记录
            for idx, (year, month, day) in enumerate(zip(years, months, days)):
                i = valid_indices[idx]
                records.append(
                    {
                        "datetime": pd.Timestamp(year, month, day),
                        "open": open_prices[i],
                        "high": high_prices[i],
                        "low": low_prices[i],
                        "close": close_prices[i],
                        "amount": amounts[i],
                        "volume": volumes[i],
                    }
                )

        if records:
            df = pd.DataFrame(records)
            df = df.set_index("datetime")
            return df
        else:
            return pd.DataFrame()

    def _decode_min_data(self, raw_data: bytes) -> pd.DataFrame:
        """解码分钟线数据

        注意：分钟线数据中的价格已经是浮点数，不需要除以1000.0转换

        Args:
            raw_data: 原始二进制数据

        Returns:
            DataFrame
        """
        records = []
        record_count = len(raw_data) // self.MIN_RECORD_SIZE

        if record_count == 0:
            return pd.DataFrame()

        # 🚀 性能优化：使用struct.unpack_from避免内存切片拷贝
        # 直接从未切片的内存缓冲区解包，避免每次循环创建新的bytes对象
        for i in range(record_count):
            offset = i * self.MIN_RECORD_SIZE

            # 边界检查：确保有足够的数据
            if offset + self.MIN_RECORD_SIZE > len(raw_data):
                break

            try:
                # 使用unpack_from直接解包，避免切片拷贝
                (
                    date_code,
                    time_code,
                    open_price,
                    high_price,
                    low_price,
                    close_price,
                    amount,
                    volume,
                    reserved,
                ) = struct.unpack_from(self.MIN_STRUCT, raw_data, offset)

                # 解析日期
                year = date_code // 2048 + 2004
                month = (date_code % 2048) // 100
                day = (date_code % 2048) % 100

                # 解析时间
                hour = time_code // 60
                minute = time_code % 60

                records.append(
                    {
                        "datetime": pd.Timestamp(year, month, day, hour, minute),
                        "open": open_price,  # 已经是浮点数，不需要转换
                        "high": high_price,  # 已经是浮点数，不需要转换
                        "low": low_price,  # 已经是浮点数，不需要转换
                        "close": close_price,  # 已经是浮点数，不需要转换
                        "amount": amount,
                        "volume": volume,
                    }
                )
            except Exception as e:
                self.logger.debug(
                    f"解析分钟线记录失败: {e}",
                    extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
                )
                continue

        if records:
            df = pd.DataFrame(records)
            df = df.set_index("datetime")
            return df
        else:
            return pd.DataFrame()

    def process_batch(
        self,
        symbols: List[str],
        data_type: str,
        market: str,
        progress_callback: Optional[Callable] = None,
    ) -> Dict[str, pd.DataFrame]:
        """批量处理多个品种（同步版本）

        Args:
            symbols: 品种代码列表
            data_type: 数据类型
            market: 市场
            progress_callback: 进度回调函数

        Returns:
            {symbol: DataFrame}
        """
        results = {}
        total = len(symbols)

        for i, symbol in enumerate(symbols):
            df = self.read_single(symbol, data_type, market)
            if not df.empty:
                results[symbol] = df

            if progress_callback:
                try:
                    progress_callback(i + 1, total, f"已处理: {symbol}")
                except Exception as e:
                    self.logger.warning(
                        f"⚠️ [TdxBinaryReader] 进度回调执行失败: {e}",
                        extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
                    )
                    pass

        self.logger.info(
            f"批量读取完成: {len(results)}/{total}",
            extra={"log_type": "SYSTEM", "scenario": "tdx_data_read"},
        )
        return results

    async def process_batch_async(
        self, symbols: List[str], data_type: str, market: str, max_concurrent: int = 50
    ) -> Dict[str, pd.DataFrame]:
        """批量处理多个品种（异步版本，native_iocp集成）

        Args:
            symbols: 品种代码列表
            data_type: 数据类型
            market: 市场
            max_concurrent: 最大并发数

        Returns:
            {symbol: DataFrame}
        """
        results = {}
        semaphore = asyncio.Semaphore(max_concurrent)

        async def read_with_semaphore(symbol):
            async with semaphore:
                df = await self.read_single_async(symbol, data_type, market)
                if not df.empty:
                    return symbol, df
                return symbol, None

        # 创建任务
        tasks = [read_with_semaphore(symbol) for symbol in symbols]

        # 并发执行
        task_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 收集结果
        for result in task_results:
            if isinstance(result, tuple) and result[1] is not None:
                symbol, df = result
                results[symbol] = df

        self.logger.info(f"异步批量读取完成: {len(results)}/{len(symbols)}")
        return results
