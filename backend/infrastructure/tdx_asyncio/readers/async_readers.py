# -*- coding: utf-8 -*-
"""
异步本地数据读取器模块

基于pytdx.reader完全重写，提供通达信本地数据文件的异步读取功能。

支持的文件格式：
- .day - 日K线数据
- .lc1 - 1分钟线数据
- .lc5 - 5分钟线数据
- .min - 分钟线数据
- block文件 - 板块数据

核心特点：
- 完全异步化实现
- 自动解析二进制格式
- 返回标准DataFrame格式
- 支持批量读取

作者：[项目名称]
版本：2.0
"""

import asyncio
import struct
import time
from pathlib import Path
from typing import List, Union, Any

import pandas as pd

# 🚀 原生IOCP异步文件I/O：优先使用Windows IOCP，自动降级到aiofiles
try:
    from backend.infrastructure.native.native_iocp import (
        compat_aopen,
        is_iocp_available,
        get_backend,
    )

    _USE_IOCP = True
except ImportError:
    # 兼容：如果没有native_iocp，使用aiofiles
    import aiofiles

    compat_aopen = None

    def is_iocp_available():
        return False

    def get_backend():
        return "aiofiles"

    _USE_IOCP = False

# 🚀 原生批量数值运算：用于优化价格转换性能
try:
    from backend.infrastructure.native.native_compute import (
        batch_compute,
        COMPUTE_AVAILABLE,
    )

    _USE_NATIVE_COMPUTE = COMPUTE_AVAILABLE
except ImportError:
    batch_compute = None
    _USE_NATIVE_COMPUTE = False

# 🚀 原生批量类型转换：用于优化日期整数到字符串转换性能
try:
    from backend.infrastructure.native.native_conversion import (
        batch_convert,
        CONVERSION_AVAILABLE,
    )

    _USE_NATIVE_CONVERSION = CONVERSION_AVAILABLE
except ImportError:
    batch_convert = None
    _USE_NATIVE_CONVERSION = False

from ..utils.logger import logger


# 🚀 统一的异步文件打开函数（自动选择最佳后端）
async def _open_file_async(filepath: Union[str, Path], mode: str = "rb") -> Any:
    """
    异步打开文件，优先使用native_iocp（Windows真异步），失败时降级到aiofiles

    Args:
        filepath: 文件路径
        mode: 打开模式（'rb', 'r', 'wb', etc.）

    Returns:
        文件对象（支持async with上下文管理器）
    """
    if _USE_IOCP and compat_aopen is not None:
        try:
            # 🚀 使用native_iocp（Windows IOCP或aiofiles fallback）
            # compat_aopen返回已打开的文件对象，支持async with
            file_obj = await compat_aopen(filepath, mode)
            return file_obj
        except Exception as e:
            logger.warning(
                f"native_iocp打开文件失败，降级到aiofiles: {e}", extra={"log_type": "SYSTEM"}
            )
            # Fallback到aiofiles
            import aiofiles

            return await aiofiles.open(filepath, mode)
    else:
        # 直接使用aiofiles
        import aiofiles

        return await aiofiles.open(filepath, mode)


class AsyncTdxDayReader:
    """
    异步读取通达信.day日K线文件

    文件格式：
    - 每条记录32字节
    - 包含：日期、开高低收、成交量、成交额等
    """

    RECORD_SIZE = 32  # 每条记录32字节

    def __init__(self, filepath: Union[str, Path]):
        """
        初始化日线读取器

        :param filepath: .day文件路径
        """
        self.filepath = Path(filepath)

    async def read(self) -> pd.DataFrame:
        """
        异步读取日线数据

        :return: DataFrame，列：date, open, high, low, close, amount, volume, ...
        """
        scenario = "tdx_data_read"
        try:
            if not self.filepath.exists():
                logger.error(
                    "文件不存在: %s",
                    self.filepath,
                    extra={"log_type": "ALERT", "scenario": scenario},
                )
                logger.debug(
                    "[TDX-READER] 文件不存在检查: filepath=%s",
                    self.filepath,
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                return pd.DataFrame()

            logger.info(
                "[TDX-READER] ℹ️ 开始读取日线文件: %s",
                self.filepath.name,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 文件路径: %s",
                self.filepath,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 文件大小检查: exists=%s",
                self.filepath.exists(),
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 🚀 使用native_iocp异步读取二进制文件（真异步，无线程池开销）
            read_start_time = time.time()
            f = await _open_file_async(self.filepath, "rb")
            async with f:
                data = await f.read()
            read_elapsed = time.time() - read_start_time

            file_size = len(data)
            logger.debug(
                "[TDX-READER] 文件读取完成: 文件=%s, 大小=%d bytes, 耗时=%.3f s",
                self.filepath.name,
                file_size,
                read_elapsed,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 🔧 优化：直接在协程中解析，避免线程池排队
            # 数据解析很快（通常<1ms），不需要放到线程池
            # 如果数据量很大可以分块处理并定期 await asyncio.sleep(0)
            logger.debug(
                "[TDX-READER] 开始解析日线数据: 文件=%s, 数据大小=%d bytes",
                self.filepath.name,
                len(data),
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.info(
                "[TDX-READER] ℹ️ 开始解析日线数据: 文件=%s",
                self.filepath.name,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            parse_start_time = time.time()
            records = self._parse_day_data(data)
            parse_elapsed = time.time() - parse_start_time

            logger.debug(
                "[TDX-READER] 解析完成: 文件=%s, 记录数=%d, 耗时=%.3f s",
                self.filepath.name,
                len(records),
                parse_elapsed,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            if not records:
                logger.debug(
                    "[TDX-READER] 解析后无记录: 文件=%s",
                    self.filepath.name,
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                logger.warning(
                    "[TDX-READER] ⚠️ 解析后无记录: 文件=%s, 可能文件为空或格式错误",
                    self.filepath.name,
                    extra={"log_type": "ALERT", "scenario": scenario},
                )
                return pd.DataFrame()

            # 转换为DataFrame
            df = pd.DataFrame(records)
            total_elapsed = time.time() - read_start_time

            logger.info(
                "[TDX-READER] 文件读取完成: 文件=%s, 记录数=%d, 总耗时=%.3f s",
                self.filepath.name,
                len(df),
                total_elapsed,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 读取详情: 文件=%s, 记录数=%d, 读取耗时=%.3f s, 解析耗时=%.3f s, 总耗时=%.3f s",
                self.filepath.name,
                len(df),
                read_elapsed,
                parse_elapsed,
                total_elapsed,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            return df

        except Exception as e:
            logger.error(
                "[TDX-READER] ❌ 读取日线数据失败: 文件=%s, 错误=%s",
                self.filepath.name,
                e,
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 异常详情: 文件=%s, 异常类型=%s, 异常消息=%s",
                self.filepath.name,
                type(e).__name__,
                str(e),
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            return pd.DataFrame()

    def _parse_day_data(self, data: bytes) -> List[dict]:
        """
        解析日线数据

        格式（32字节/条）：
        - 日期: 4字节 int (YYYYMMDD)
        - 开盘: 4字节 int (价格*100)
        - 最高: 4字节 int
        - 最低: 4字节 int
        - 收盘: 4字节 int
        - 成交额: 4字节 float
        - 成交量: 4字节 int (手)
        - 保留: 4字节
        """
        scenario = "tdx_data_read"
        records = []

        try:
            logger.debug(
                "[TDX-READER] 开始解析日线数据: 数据大小=%d bytes, 记录大小=%d bytes",
                len(data),
                self.RECORD_SIZE,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            record_count = len(data) // self.RECORD_SIZE
            logger.debug(
                "[TDX-READER] 预计记录数: %d",
                record_count,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 🚀 性能优化：批量收集价格值，使用native_compute批量除以100.0
            if _USE_NATIVE_COMPUTE and record_count > 0:
                # 批量收集所有价格值
                open_prices = []
                high_prices = []
                low_prices = []
                close_prices = []
                date_ints = []
                amounts = []
                volumes = []

                # 🚀 性能优化：使用struct.unpack_from避免内存切片拷贝
                # 直接从未切片的内存缓冲区解包，避免每次循环创建新的bytes对象
                for i in range(record_count):
                    offset = i * self.RECORD_SIZE

                    # 边界检查：确保有足够的数据
                    if offset + self.RECORD_SIZE > len(data):
                        break

                    try:
                        # 使用unpack_from直接解包，避免切片拷贝
                        unpacked = struct.unpack_from("<IiiiiIfI", data, offset)
                        date_ints.append(unpacked[0])
                        open_prices.append(unpacked[1])
                        high_prices.append(unpacked[2])
                        low_prices.append(unpacked[3])
                        close_prices.append(unpacked[4])
                        amounts.append(unpacked[5])
                        volumes.append(unpacked[6])
                    except Exception as e:
                        logger.debug(
                            f"解析日线记录失败: {e}",
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )
                        continue

                # 批量除以100.0（使用native_compute）
                try:
                    if batch_compute is not None:
                        # 🚀 使用正确的操作类型：divide_by_100（根据native_compute API）
                        open_prices = batch_compute(open_prices, "divide_by_100")  # type: ignore
                        high_prices = batch_compute(high_prices, "divide_by_100")  # type: ignore
                        low_prices = batch_compute(low_prices, "divide_by_100")  # type: ignore
                        close_prices = batch_compute(close_prices, "divide_by_100")  # type: ignore
                    else:
                        raise ImportError("batch_compute not available")
                except Exception as e:
                    # 降级到Python实现
                    logger.debug(
                        "[TDX-READER] native_compute失败，降级到Python实现: %s",
                        str(e),
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                    open_prices = [p / 100.0 for p in open_prices]
                    high_prices = [p / 100.0 for p in high_prices]
                    low_prices = [p / 100.0 for p in low_prices]
                    close_prices = [p / 100.0 for p in close_prices]

                # 🚀 性能优化：批量转换日期整数到字符串（使用native_conversion）
                date_strs = []
                try:
                    if _USE_NATIVE_CONVERSION and batch_convert is not None:
                        # 批量转换日期整数到字符串
                        date_strs = batch_convert(date_ints, str)  # type: ignore
                    else:
                        raise ImportError("batch_convert not available")
                except Exception as e:
                    # 降级到Python实现
                    logger.debug(
                        "[TDX-READER] native_conversion失败，降级到Python实现: %s",
                        str(e),
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                    date_strs = [str(d) for d in date_ints]

                # 构建记录
                for i in range(len(date_ints)):
                    date_str = date_strs[i]
                    if len(date_str) == 8:
                        date_obj = pd.to_datetime(date_str, format="%Y%m%d")
                        records.append(
                            {
                                "date": date_obj,
                                "open": open_prices[i],
                                "high": high_prices[i],
                                "low": low_prices[i],
                                "close": close_prices[i],
                                "volume": volumes[i],
                                "amount": amounts[i],
                            }
                        )
            else:
                # 降级到原有实现（native_compute不可用或记录数较少）
                # 🚀 性能优化：使用struct.unpack_from避免内存切片拷贝
                for i in range(record_count):
                    offset = i * self.RECORD_SIZE

                    # 边界检查：确保有足够的数据
                    if offset + self.RECORD_SIZE > len(data):
                        break

                    try:
                        # 使用unpack_from直接解包，避免切片拷贝
                        unpacked = struct.unpack_from("<IiiiiIfI", data, offset)

                        date_int = unpacked[0]
                        open_price = unpacked[1] / 100.0
                        high_price = unpacked[2] / 100.0
                        low_price = unpacked[3] / 100.0
                        close_price = unpacked[4] / 100.0
                        amount = unpacked[5]
                        volume = unpacked[6]

                        # 转换日期格式
                        date_str = str(date_int)
                        if len(date_str) == 8:
                            date_obj = pd.to_datetime(date_str, format="%Y%m%d")

                            records.append(
                                {
                                    "date": date_obj,
                                    "open": open_price,
                                    "high": high_price,
                                    "low": low_price,
                                    "close": close_price,
                                    "volume": volume,
                                    "amount": amount,
                                }
                            )
                    except Exception as e:
                        logger.debug(
                            f"解析日线记录失败: {e}",
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )
                        continue

        except Exception as e:
            logger.debug(
                "[TDX-READER] 解析异常详情: 异常类型=%s, 异常消息=%s, 已解析记录数=%d",
                type(e).__name__,
                str(e),
                len(records),
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.error(
                "[TDX-READER] ❌ 解析日线数据失败: 文件=%s, 错误=%s",
                self.filepath.name if hasattr(self, "filepath") else "unknown",
                e,
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            logger.warning(
                "[TDX-READER] ⚠️ 解析日线数据失败，已解析记录数=%d: %s",
                len(records),
                str(e),
                extra={"log_type": "ALERT", "scenario": scenario},
            )
        else:
            logger.debug(
                "[TDX-READER] 日线数据解析完成: 记录数=%d",
                len(records),
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

        return records


class AsyncTdxMinuteReader:
    """
    异步读取通达信.lc1分钟线文件

    文件格式：
    - 每条记录32字节
    - 包含：时间、开高低收、成交量、成交额等
    """

    RECORD_SIZE = 32  # 每条记录32字节

    def __init__(self, filepath: Union[str, Path]):
        """
        初始化分钟线读取器

        :param filepath: .lc1文件路径
        """
        self.filepath = Path(filepath)

    async def read(self) -> pd.DataFrame:
        """
        异步读取分钟线数据

        :return: DataFrame，列：datetime, open, high, low, close, amount, volume, ...
        """
        scenario = "tdx_data_read"
        try:
            if not self.filepath.exists():
                logger.error(
                    "文件不存在: %s",
                    self.filepath,
                    extra={"log_type": "ALERT", "scenario": scenario},
                )
                logger.debug(
                    "[TDX-READER] 文件不存在检查: filepath=%s",
                    self.filepath,
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                return pd.DataFrame()

            logger.info(
                "[TDX-READER] ℹ️ 开始读取分钟线文件: %s",
                self.filepath.name,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 文件路径: %s",
                self.filepath,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 文件大小检查: exists=%s",
                self.filepath.exists(),
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 🚀 使用native_iocp异步读取二进制文件（真异步，无线程池开销）
            read_start_time = time.time()
            f = await _open_file_async(self.filepath, "rb")
            async with f:
                data = await f.read()
            read_elapsed = time.time() - read_start_time

            file_size = len(data)
            logger.debug(
                "[TDX-READER] 文件读取完成: 文件=%s, 大小=%d bytes, 耗时=%.3f s",
                self.filepath.name,
                file_size,
                read_elapsed,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 🔧 优化：直接在协程中解析，避免线程池排队
            parse_start_time = time.time()
            records = self._parse_minute_data(data)
            parse_elapsed = time.time() - parse_start_time

            if not records:
                logger.debug(
                    "[TDX-READER] 解析后无记录: 文件=%s",
                    self.filepath.name,
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                return pd.DataFrame()

            # 转换为DataFrame
            df = pd.DataFrame(records)
            total_elapsed = time.time() - read_start_time

            logger.info(
                "[TDX-READER] 文件读取完成: 文件=%s, 记录数=%d, 总耗时=%.3f s",
                self.filepath.name,
                len(df),
                total_elapsed,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 读取详情: 文件=%s, 记录数=%d, 读取耗时=%.3f s, 解析耗时=%.3f s, 总耗时=%.3f s",
                self.filepath.name,
                len(df),
                read_elapsed,
                parse_elapsed,
                total_elapsed,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            return df

        except Exception as e:
            scenario = "tdx_data_read"
            logger.error(
                "[TDX-READER] ❌ 读取分钟线数据失败: 文件=%s, 错误=%s",
                self.filepath.name,
                e,
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 异常详情: 文件=%s, 异常类型=%s, 异常消息=%s",
                self.filepath.name,
                type(e).__name__,
                str(e),
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            return pd.DataFrame()

    def _parse_minute_data(self, data: bytes) -> List[dict]:
        """
        解析分钟线数据

        格式（32字节/条）：
        - 日期: 2字节 short (天数，从1900-01-01起)
        - 时间: 2字节 short (分钟数，从0:00起)
        - 开盘: 4字节 int (价格*100)
        - 最高: 4字节 int
        - 最低: 4字节 int
        - 收盘: 4字节 int
        - 成交额: 4字节 float
        - 成交量: 4字节 int (手)
        - 保留: 8字节
        """
        records = []

        try:
            record_count = len(data) // self.RECORD_SIZE

            # 🚀 性能优化：批量收集价格值，使用native_compute批量除以100.0
            if _USE_NATIVE_COMPUTE and record_count > 0:
                # 批量收集所有数据
                days_list = []
                minutes_list = []
                open_prices = []
                high_prices = []
                low_prices = []
                close_prices = []
                volumes = []
                amounts = []

                # 🚀 性能优化：使用struct.unpack_from避免内存切片拷贝
                # 直接从未切片的内存缓冲区解包，避免每次循环创建新的bytes对象
                for i in range(record_count):
                    offset = i * self.RECORD_SIZE

                    # 边界检查：确保有足够的数据（至少28字节用于解析）
                    if offset + 28 > len(data):
                        break

                    try:
                        # 使用unpack_from直接解包，避免切片拷贝
                        unpacked = struct.unpack_from("<HHiiiiIi", data, offset)
                        days_list.append(unpacked[0])
                        minutes_list.append(unpacked[1])
                        open_prices.append(unpacked[2])
                        high_prices.append(unpacked[3])
                        low_prices.append(unpacked[4])
                        close_prices.append(unpacked[5])
                        volumes.append(unpacked[6])
                        amounts.append(unpacked[7])
                    except Exception as e:
                        scenario = "tdx_data_read"
                        logger.debug(
                            f"解析分钟线记录失败: {e}",
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )
                        continue

                # 批量除以100.0（使用native_compute）
                try:
                    if batch_compute is not None:
                        # 🚀 使用正确的操作类型：divide_by_100（根据native_compute API）
                        open_prices = batch_compute(open_prices, "divide_by_100")  # type: ignore
                        high_prices = batch_compute(high_prices, "divide_by_100")  # type: ignore
                        low_prices = batch_compute(low_prices, "divide_by_100")  # type: ignore
                        close_prices = batch_compute(close_prices, "divide_by_100")  # type: ignore
                        amounts = batch_compute(amounts, "divide_by_100")  # type: ignore
                    else:
                        raise ImportError("batch_compute not available")
                except Exception as e:
                    # 降级到Python实现
                    scenario = "tdx_data_read"
                    logger.debug(
                        "[TDX-READER] native_compute失败，降级到Python实现: %s",
                        str(e),
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                    open_prices = [p / 100.0 for p in open_prices]
                    high_prices = [p / 100.0 for p in high_prices]
                    low_prices = [p / 100.0 for p in low_prices]
                    close_prices = [p / 100.0 for p in close_prices]
                    amounts = [a / 100.0 for a in amounts]

                # 构建记录
                base_date = pd.Timestamp("1900-01-01")
                for i in range(len(days_list)):
                    date_obj = base_date + pd.Timedelta(days=days_list[i], minutes=minutes_list[i])
                    records.append(
                        {
                            "datetime": date_obj,
                            "open": open_prices[i],
                            "high": high_prices[i],
                            "low": low_prices[i],
                            "close": close_prices[i],
                            "volume": volumes[i],
                            "amount": amounts[i],
                        }
                    )
            else:
                # 降级到原有实现（native_compute不可用或记录数较少）
                # 🚀 性能优化：使用struct.unpack_from避免内存切片拷贝
                for i in range(record_count):
                    offset = i * self.RECORD_SIZE

                    # 边界检查：确保有足够的数据（至少28字节用于解析）
                    if offset + 28 > len(data):
                        break

                    try:
                        # 使用unpack_from直接解包，避免切片拷贝
                        unpacked = struct.unpack_from("<HHiiiiIi", data, offset)

                        days = unpacked[0]
                        minutes = unpacked[1]
                        open_price = unpacked[2] / 100.0
                        high_price = unpacked[3] / 100.0
                        low_price = unpacked[4] / 100.0
                        close_price = unpacked[5] / 100.0
                        volume = unpacked[6]
                        amount = unpacked[7] / 100.0

                        # 计算日期时间
                        base_date = pd.Timestamp("1900-01-01")
                        date_obj = base_date + pd.Timedelta(days=days, minutes=minutes)

                        records.append(
                            {
                                "datetime": date_obj,
                                "open": open_price,
                                "high": high_price,
                                "low": low_price,
                                "close": close_price,
                                "volume": volume,
                                "amount": amount,
                            }
                        )
                    except Exception as e:
                        scenario = "tdx_data_read"
                        logger.debug(
                            f"解析分钟线记录失败: {e}",
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )
                        continue

        except Exception as e:
            scenario = "tdx_data_read"
            logger.error(
                "[TDX-READER] ❌ 解析分钟线数据失败: 文件=%s, 错误=%s",
                self.filepath.name if hasattr(self, "filepath") else "unknown",
                e,
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 解析异常详情: 异常类型=%s, 异常消息=%s, 已解析记录数=%d",
                type(e).__name__,
                str(e),
                len(records),
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

        return records


class AsyncTdxLc5Reader:
    """
    异步读取通达信.lc5五分钟线文件

    文件格式与分钟线类似，但周期为5分钟
    """

    RECORD_SIZE = 32

    def __init__(self, filepath: Union[str, Path]):
        """
        初始化5分钟线读取器

        :param filepath: .lc5文件路径
        """
        self.filepath = Path(filepath)

    async def read(self) -> pd.DataFrame:
        """
        异步读取5分钟线数据

        :return: DataFrame，列：datetime, open, high, low, close, amount, volume, ...
        """
        scenario = "tdx_data_read"
        try:
            if not self.filepath.exists():
                logger.error(
                    "文件不存在: %s",
                    self.filepath,
                    extra={"log_type": "ALERT", "scenario": scenario},
                )
                logger.debug(
                    "[TDX-READER] 文件不存在检查: filepath=%s",
                    self.filepath,
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                return pd.DataFrame()

            logger.info(
                "[TDX-READER] ℹ️ 开始读取5分钟线文件: %s",
                self.filepath.name,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 文件路径: %s",
                self.filepath,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 文件大小检查: exists=%s",
                self.filepath.exists(),
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 🚀 使用native_iocp异步读取二进制文件（真异步，无线程池开销）
            read_start_time = time.time()
            f = await _open_file_async(self.filepath, "rb")
            async with f:
                data = await f.read()
            read_elapsed = time.time() - read_start_time

            file_size = len(data)
            logger.debug(
                "[TDX-READER] 文件读取完成: 文件=%s, 大小=%d bytes, 耗时=%.3f s",
                self.filepath.name,
                file_size,
                read_elapsed,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 🔧 优化：直接在协程中解析，避免线程池排队
            parse_start_time = time.time()
            records = self._parse_lc5_data(data)
            parse_elapsed = time.time() - parse_start_time

            if not records:
                logger.debug(
                    "[TDX-READER] 解析后无记录: 文件=%s",
                    self.filepath.name,
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                return pd.DataFrame()

            # 转换为DataFrame
            df = pd.DataFrame(records)
            total_elapsed = time.time() - read_start_time

            logger.info(
                "[TDX-READER] 文件读取完成: 文件=%s, 记录数=%d, 总耗时=%.3f s",
                self.filepath.name,
                len(df),
                total_elapsed,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 读取详情: 文件=%s, 记录数=%d, 读取耗时=%.3f s, 解析耗时=%.3f s, 总耗时=%.3f s",
                self.filepath.name,
                len(df),
                read_elapsed,
                parse_elapsed,
                total_elapsed,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            return df

        except Exception as e:
            logger.error(
                "[TDX-READER] ❌ 读取5分钟线数据失败: 文件=%s, 错误=%s",
                self.filepath.name,
                e,
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 异常详情: 文件=%s, 异常类型=%s, 异常消息=%s",
                self.filepath.name,
                type(e).__name__,
                str(e),
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            return pd.DataFrame()

    def _parse_lc5_data(self, data: bytes) -> List[dict]:
        """解析5分钟线数据（格式与分钟线相同）"""
        records = []
        scenario = "tdx_data_read"

        try:
            logger.debug(
                "[TDX-READER] 开始解析5分钟线数据: 数据大小=%d bytes, 记录大小=%d bytes",
                len(data),
                self.RECORD_SIZE,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            record_count = len(data) // self.RECORD_SIZE
            logger.debug(
                "[TDX-READER] 预计记录数: %d",
                record_count,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 🚀 性能优化：批量收集价格值，使用native_compute批量除以100.0
            if _USE_NATIVE_COMPUTE and record_count > 0:
                # 批量收集所有数据
                days_list = []
                minutes_list = []
                open_prices = []
                high_prices = []
                low_prices = []
                close_prices = []
                volumes = []
                amounts = []

                # 🚀 性能优化：使用struct.unpack_from避免内存切片拷贝
                # 直接从未切片的内存缓冲区解包，避免每次循环创建新的bytes对象
                for i in range(record_count):
                    offset = i * self.RECORD_SIZE

                    # 边界检查：确保有足够的数据（至少28字节用于解析）
                    if offset + 28 > len(data):
                        break

                    try:
                        # 使用unpack_from直接解包，避免切片拷贝
                        unpacked = struct.unpack_from("<HHiiiiIi", data, offset)
                        days_list.append(unpacked[0])
                        minutes_list.append(unpacked[1])
                        open_prices.append(unpacked[2])
                        high_prices.append(unpacked[3])
                        low_prices.append(unpacked[4])
                        close_prices.append(unpacked[5])
                        volumes.append(unpacked[6])
                        amounts.append(unpacked[7])
                    except Exception as e:
                        logger.debug(
                            f"解析5分钟线记录失败: {e}",
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )
                        continue

                # 批量除以100.0（使用native_compute）
                try:
                    if batch_compute is not None:
                        # 🚀 使用正确的操作类型：divide_by_100（根据native_compute API）
                        open_prices = batch_compute(open_prices, "divide_by_100")  # type: ignore
                        high_prices = batch_compute(high_prices, "divide_by_100")  # type: ignore
                        low_prices = batch_compute(low_prices, "divide_by_100")  # type: ignore
                        close_prices = batch_compute(close_prices, "divide_by_100")  # type: ignore
                        amounts = batch_compute(amounts, "divide_by_100")  # type: ignore
                    else:
                        raise ImportError("batch_compute not available")
                except Exception as e:
                    # 降级到Python实现
                    logger.debug(
                        "[TDX-READER] native_compute失败，降级到Python实现: %s",
                        str(e),
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                    open_prices = [p / 100.0 for p in open_prices]
                    high_prices = [p / 100.0 for p in high_prices]
                    low_prices = [p / 100.0 for p in low_prices]
                    close_prices = [p / 100.0 for p in close_prices]
                    amounts = [a / 100.0 for a in amounts]

                # 构建记录
                base_date = pd.Timestamp("1900-01-01")
                for i in range(len(days_list)):
                    date_obj = base_date + pd.Timedelta(days=days_list[i], minutes=minutes_list[i])
                    records.append(
                        {
                            "datetime": date_obj,
                            "open": open_prices[i],
                            "high": high_prices[i],
                            "low": low_prices[i],
                            "close": close_prices[i],
                            "volume": volumes[i],
                            "amount": amounts[i],
                        }
                    )
            else:
                # 降级到原有实现（native_compute不可用或记录数较少）
                # 🚀 性能优化：使用struct.unpack_from避免内存切片拷贝
                for i in range(record_count):
                    offset = i * self.RECORD_SIZE

                    # 边界检查：确保有足够的数据（至少28字节用于解析）
                    if offset + 28 > len(data):
                        break

                    try:
                        # 使用unpack_from直接解包，避免切片拷贝
                        unpacked = struct.unpack_from("<HHiiiiIi", data, offset)

                        days = unpacked[0]
                        minutes = unpacked[1]
                        open_price = unpacked[2] / 100.0
                        high_price = unpacked[3] / 100.0
                        low_price = unpacked[4] / 100.0
                        close_price = unpacked[5] / 100.0
                        volume = unpacked[6]
                        amount = unpacked[7] / 100.0

                        base_date = pd.Timestamp("1900-01-01")
                        date_obj = base_date + pd.Timedelta(days=days, minutes=minutes)

                        records.append(
                            {
                                "datetime": date_obj,
                                "open": open_price,
                                "high": high_price,
                                "low": low_price,
                                "close": close_price,
                                "volume": volume,
                                "amount": amount,
                            }
                        )
                    except Exception as e:
                        logger.debug(
                            f"解析5分钟线记录失败: {e}",
                            extra={"log_type": "SYSTEM", "scenario": scenario},
                        )
                        continue

        except Exception as e:
            scenario = "tdx_data_read"
            logger.error(
                "[TDX-READER] ❌ 解析5分钟线数据失败: 文件=%s, 错误=%s",
                self.filepath.name if hasattr(self, "filepath") else "unknown",
                e,
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 解析异常详情: 异常类型=%s, 异常消息=%s, 已解析记录数=%d",
                type(e).__name__,
                str(e),
                len(records),
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
        else:
            logger.debug(
                "[TDX-READER] 5分钟线数据解析完成: 记录数=%d",
                len(records),
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

        return records


class AsyncTdxBlockReader:
    """
    异步读取通达信板块文件

    支持的文件：
    - block_gn.dat - 概念板块
    - block_fg.dat - 风格板块
    - incon.dat - 行业板块
    """

    def __init__(self, filepath: Union[str, Path]):
        """
        初始化板块读取器

        :param filepath: 板块文件路径
        """
        self.filepath = Path(filepath)

    async def read(self) -> pd.DataFrame:
        """
        异步读取板块数据

        :return: DataFrame，列：block_name, code_list
        """
        scenario = "tdx_data_read"
        try:
            if not self.filepath.exists():
                logger.error(
                    "[TDX-READER] ❌ 文件不存在: %s",
                    self.filepath,
                    extra={"log_type": "ALERT", "scenario": scenario},
                )
                logger.debug(
                    "[TDX-READER] 文件不存在检查: filepath=%s",
                    self.filepath,
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                return pd.DataFrame()

            logger.info(
                "[TDX-READER] 开始读取板块文件: %s",
                self.filepath.name,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 文件路径: %s",
                self.filepath,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 🚀 使用native_iocp异步读取文本文件（GBK编码），真异步，无线程池开销
            read_start_time = time.time()
            # 使用二进制模式读取，然后手动解码为GBK，确保兼容性
            f = await _open_file_async(self.filepath, "rb")
            async with f:
                raw_data = await f.read()
                # 解码为GBK文本
                content = raw_data.decode("gbk", errors="ignore")
            read_elapsed = time.time() - read_start_time

            file_size = len(content.encode("gbk"))
            logger.debug(
                "[TDX-READER] 文件读取完成: 文件=%s, 大小=%d bytes, 耗时=%.3f s",
                self.filepath.name,
                file_size,
                read_elapsed,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 解析数据
            parse_start_time = time.time()
            records = self._parse_block_data(content)
            parse_elapsed = time.time() - parse_start_time

            if not records:
                logger.debug(
                    "[TDX-READER] 解析后无记录: 文件=%s",
                    self.filepath.name,
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                return pd.DataFrame()

            # 转换为DataFrame
            df = pd.DataFrame(records)
            total_elapsed = time.time() - read_start_time

            logger.info(
                "[TDX-READER] 文件读取完成: 文件=%s, 板块数=%d, 总耗时=%.3f s",
                self.filepath.name,
                len(df),
                total_elapsed,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 读取详情: 文件=%s, 板块数=%d, 读取耗时=%.3f s, 解析耗时=%.3f s, 总耗时=%.3f s",
                self.filepath.name,
                len(df),
                read_elapsed,
                parse_elapsed,
                total_elapsed,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            return df

        except Exception as e:
            scenario = "tdx_data_read"
            logger.error(
                "[TDX-READER] ❌ 读取板块数据失败: 文件=%s, 错误=%s",
                self.filepath.name,
                e,
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 异常详情: 文件=%s, 异常类型=%s, 异常消息=%s",
                self.filepath.name,
                type(e).__name__,
                str(e),
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            return pd.DataFrame()

    def _parse_block_data(self, content: str) -> List[dict]:
        """
        解析板块数据

        格式：
        #板块名称
        股票代码1
        股票代码2
        ...
        """
        records = []
        scenario = "tdx_data_read"

        try:
            lines = content.strip().split("\n")

            current_block = None
            current_codes = []

            for line in lines:
                line = line.strip()

                if not line:
                    continue

                # 板块名称以#开头
                if line.startswith("#"):
                    # 保存上一个板块
                    if current_block and current_codes:
                        records.append(
                            {
                                "block_name": current_block,
                                "code_list": current_codes.copy(),
                                "count": len(current_codes),
                            }
                        )

                    # 开始新板块
                    current_block = line[1:]  # 去掉#
                    current_codes = []

                else:
                    # 股票代码
                    if current_block:
                        current_codes.append(line)

            # 保存最后一个板块
            if current_block and current_codes:
                records.append(
                    {
                        "block_name": current_block,
                        "code_list": current_codes.copy(),
                        "count": len(current_codes),
                    }
                )

            logger.debug(
                "[TDX-READER] 板块解析完成: 板块数=%d",
                len(records),
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

        except Exception as e:
            scenario = "tdx_data_read"
            logger.error(
                "[TDX-READER] ❌ 解析板块数据失败: 文件=%s, 错误=%s",
                self.filepath.name if hasattr(self, "filepath") else "unknown",
                e,
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 解析异常详情: 异常类型=%s, 异常消息=%s, 已解析板块数=%d",
                type(e).__name__,
                str(e),
                len(records),
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

        return records


# ==================== 便捷函数 ====================


async def read_day_data(filepath: Union[str, Path]) -> pd.DataFrame:
    """
    便捷函数：读取日线数据

    :param filepath: .day文件路径
    :return: DataFrame
    """
    reader = AsyncTdxDayReader(filepath)
    return await reader.read()


async def read_minute_data(filepath: Union[str, Path]) -> pd.DataFrame:
    """
    便捷函数：读取分钟线数据

    :param filepath: .lc1文件路径
    :return: DataFrame
    """
    reader = AsyncTdxMinuteReader(filepath)
    return await reader.read()


async def read_lc5_data(filepath: Union[str, Path]) -> pd.DataFrame:
    """
    便捷函数：读取5分钟线数据

    :param filepath: .lc5文件路径
    :return: DataFrame
    """
    reader = AsyncTdxLc5Reader(filepath)
    return await reader.read()


async def read_block_data(filepath: Union[str, Path]) -> pd.DataFrame:
    """
    便捷函数：读取板块数据

    :param filepath: 板块文件路径
    :return: DataFrame
    """
    reader = AsyncTdxBlockReader(filepath)
    return await reader.read()


class AsyncHistoryFinancialReader:
    """
    异步读取通达信历史财务数据文件

    支持格式：
    - gpcw20171231.zip - 压缩格式
    - gpcw20171231.dat - 解压后格式

    数据字段含义参考：
    https://github.com/rainx/pytdx/issues/133
    """

    def __init__(self, filepath: Union[str, Path]):
        """
        初始化历史财务数据读取器

        :param filepath: 财务数据文件路径（.zip或.dat）
        """
        self.filepath = Path(filepath)

    async def read(self) -> pd.DataFrame:
        """
        异步读取历史财务数据

        :return: DataFrame，列：财务指标数据
        """
        try:
            if not self.filepath.exists():
                logger.error(f"文件不存在: {self.filepath}", extra={"log_type": "SYSTEM"})
                return pd.DataFrame()

            # 检查文件类型
            if self.filepath.suffix == ".zip":
                # ZIP文件需要先解压
                import zipfile

                with zipfile.ZipFile(self.filepath, "r") as zip_ref:
                    # 获取第一个.dat文件
                    dat_files = [f for f in zip_ref.namelist() if f.endswith(".dat")]
                    if not dat_files:
                        logger.error(
                            "ZIP文件中没有.dat文件: %s", self.filepath, extra={"log_type": "SYSTEM"}
                        )
                        return pd.DataFrame()

                    # 读取第一个dat文件
                    with zip_ref.open(dat_files[0]) as f:
                        data = f.read()
            else:
                # 🚀 直接读取.dat文件（使用native_iocp）
                f = await _open_file_async(self.filepath, "rb")
                async with f:
                    data = await f.read()

            # 解析财务数据（简化版）
            records = self._parse_financial_data(data)

            if not records:
                return pd.DataFrame()

            # 转换为DataFrame
            df = pd.DataFrame(records)

            logger.debug("成功读取财务数据: %d条, 文件=%s", len(df), self.filepath.name)
            return df

        except Exception as e:
            logger.error("读取财务数据失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})
            return pd.DataFrame()

    def _parse_financial_data(self, data: bytes) -> List[dict]:
        """
        解析财务数据（简化实现）

        注意：完整的财务数据格式非常复杂，这里提供基础框架
        实际使用时需要根据具体格式进行扩展
        """
        records = []

        try:
            # 财务数据格式非常复杂，包含多种报表类型
            # 这里提供一个基础框架，实际需要完整的解析逻辑

            logger.warning(
                "财务数据解析功能需要完整实现，当前为框架版本", extra={"log_type": "SYSTEM"}
            )

            # 示例：假设数据是固定长度记录
            # 实际格式需要参考通达信财务数据格式文档

            return records

        except Exception as e:
            logger.error("解析财务数据失败: %s", e, exc_info=True, extra={"log_type": "SYSTEM"})

        return records


class AsyncTdxExHqDayReader:
    """
    异步读取扩展行情（期货/期权）日K线文件

    文件格式与股票日K线类似，但存储在扩展市场目录
    """

    RECORD_SIZE = 32  # 每条记录32字节

    def __init__(self, filepath: Union[str, Path]):
        """
        初始化扩展行情日线读取器

        :param filepath: 扩展行情.day文件路径
        """
        self.filepath = Path(filepath)

    async def read(self) -> pd.DataFrame:
        """
        异步读取扩展行情日线数据

        :return: DataFrame，列：date, open, high, low, close, amount, volume, ...
        """
        scenario = "tdx_data_read"
        try:
            if not self.filepath.exists():
                logger.error(
                    "[TDX-READER] ❌ 文件不存在: %s",
                    self.filepath,
                    extra={"log_type": "ALERT", "scenario": scenario},
                )
                logger.debug(
                    "[TDX-READER] 文件不存在检查: filepath=%s",
                    self.filepath,
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                return pd.DataFrame()

            logger.info(
                "[TDX-READER] 开始读取扩展行情日线文件: %s",
                self.filepath.name,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 文件路径: %s",
                self.filepath,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 🚀 使用native_iocp异步读取二进制文件（真异步，无线程池开销）
            read_start_time = time.time()
            f = await _open_file_async(self.filepath, "rb")
            async with f:
                data = await f.read()
            read_elapsed = time.time() - read_start_time

            file_size = len(data)
            logger.debug(
                "[TDX-READER] 文件读取完成: 文件=%s, 大小=%d bytes, 耗时=%.3f s",
                self.filepath.name,
                file_size,
                read_elapsed,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 解析数据（与股票日线格式相同）
            parse_start_time = time.time()
            records = self._parse_exhq_day_data(data)
            parse_elapsed = time.time() - parse_start_time

            if not records:
                logger.debug(
                    "[TDX-READER] 解析后无记录: 文件=%s",
                    self.filepath.name,
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                return pd.DataFrame()

            # 转换为DataFrame
            df = pd.DataFrame(records)
            total_elapsed = time.time() - read_start_time

            logger.info(
                "[TDX-READER] 文件读取完成: 文件=%s, 记录数=%d, 总耗时=%.3f s",
                self.filepath.name,
                len(df),
                total_elapsed,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 读取详情: 文件=%s, 记录数=%d, 读取耗时=%.3f s, 解析耗时=%.3f s, 总耗时=%.3f s",
                self.filepath.name,
                len(df),
                read_elapsed,
                parse_elapsed,
                total_elapsed,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            return df

        except Exception as e:
            scenario = "tdx_data_read"
            logger.error(
                "[TDX-READER] ❌ 读取扩展行情日线数据失败: 文件=%s, 错误=%s",
                self.filepath.name,
                e,
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 异常详情: 文件=%s, 异常类型=%s, 异常消息=%s",
                self.filepath.name,
                type(e).__name__,
                str(e),
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            return pd.DataFrame()

    def _parse_exhq_day_data(self, data: bytes) -> List[dict]:
        """
        解析扩展行情日线数据

        格式与股票日线相同（32字节/条）
        """
        records = []
        scenario = "tdx_data_read"

        try:
            record_count = len(data) // self.RECORD_SIZE

            # 🚀 性能优化：使用struct.unpack_from避免内存切片拷贝
            for i in range(record_count):
                offset = i * self.RECORD_SIZE

                # 边界检查：确保有足够的数据
                if offset + self.RECORD_SIZE > len(data):
                    break

                try:
                    # 使用unpack_from直接解包，避免切片拷贝
                    unpacked = struct.unpack_from("<IiiiiIfI", data, offset)

                    date_int = unpacked[0]
                    open_price = unpacked[1] / 100.0
                    high_price = unpacked[2] / 100.0
                    low_price = unpacked[3] / 100.0
                    close_price = unpacked[4] / 100.0
                    amount = unpacked[5]
                    volume = unpacked[6]

                    # 转换日期格式
                    date_str = str(date_int)
                    if len(date_str) == 8:
                        date_obj = pd.to_datetime(date_str, format="%Y%m%d")

                        records.append(
                            {
                                "date": date_obj,
                                "open": open_price,
                                "high": high_price,
                                "low": low_price,
                                "close": close_price,
                                "volume": volume,
                                "amount": amount,
                            }
                        )
                except Exception as e:
                    logger.debug(
                        f"解析扩展行情日线记录失败: {e}",
                        extra={"log_type": "SYSTEM", "scenario": scenario},
                    )
                    continue

        except Exception as e:
            scenario = "tdx_data_read"
            logger.error(
                "[TDX-READER] ❌ 解析扩展行情日线数据失败: 文件=%s, 错误=%s",
                self.filepath.name if hasattr(self, "filepath") else "unknown",
                e,
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 解析异常详情: 异常类型=%s, 异常消息=%s, 已解析记录数=%d",
                type(e).__name__,
                str(e),
                len(records),
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

        return records


class AsyncCustomerBlockReader:
    """
    异步读取用户自定义板块文件

    支持用户自定义的板块分类文件
    格式与标准板块文件相同
    """

    def __init__(self, filepath: Union[str, Path]):
        """
        初始化自定义板块读取器

        :param filepath: 自定义板块文件路径
        """
        self.filepath = Path(filepath)

    async def read(self) -> pd.DataFrame:
        """
        异步读取自定义板块数据

        :return: DataFrame，列：block_name, code_list, count
        """
        scenario = "tdx_data_read"
        try:
            if not self.filepath.exists():
                logger.error(
                    "[TDX-READER] ❌ 文件不存在: %s",
                    self.filepath,
                    extra={"log_type": "ALERT", "scenario": scenario},
                )
                logger.debug(
                    "[TDX-READER] 文件不存在检查: filepath=%s",
                    self.filepath,
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                return pd.DataFrame()

            logger.info(
                "[TDX-READER] 开始读取自定义板块文件: %s",
                self.filepath.name,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 文件路径: %s",
                self.filepath,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 🚀 使用native_iocp异步读取文本文件（GBK编码），真异步，无线程池开销
            read_start_time = time.time()
            # 使用二进制模式读取，然后手动解码为GBK，确保兼容性
            f = await _open_file_async(self.filepath, "rb")
            async with f:
                raw_data = await f.read()
                # 解码为GBK文本
                content = raw_data.decode("gbk", errors="ignore")
            read_elapsed = time.time() - read_start_time

            file_size = len(content.encode("gbk"))
            logger.debug(
                "[TDX-READER] 文件读取完成: 文件=%s, 大小=%d bytes, 耗时=%.3f s",
                self.filepath.name,
                file_size,
                read_elapsed,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )

            # 解析数据（与标准板块文件相同）
            parse_start_time = time.time()
            records = self._parse_customer_block_data(content)
            parse_elapsed = time.time() - parse_start_time

            if not records:
                logger.debug(
                    "[TDX-READER] 解析后无记录: 文件=%s",
                    self.filepath.name,
                    extra={"log_type": "SYSTEM", "scenario": scenario},
                )
                return pd.DataFrame()

            # 转换为DataFrame
            df = pd.DataFrame(records)
            total_elapsed = time.time() - read_start_time

            logger.info(
                "[TDX-READER] 文件读取完成: 文件=%s, 板块数=%d, 总耗时=%.3f s",
                self.filepath.name,
                len(df),
                total_elapsed,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 读取详情: 文件=%s, 板块数=%d, 读取耗时=%.3f s, 解析耗时=%.3f s, 总耗时=%.3f s",
                self.filepath.name,
                len(df),
                read_elapsed,
                parse_elapsed,
                total_elapsed,
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            return df

        except Exception as e:
            scenario = "tdx_data_read"
            logger.error(
                "[TDX-READER] ❌ 读取自定义板块数据失败: 文件=%s, 错误=%s",
                self.filepath.name,
                e,
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario},
            )
            logger.debug(
                "[TDX-READER] 异常详情: 文件=%s, 异常类型=%s, 异常消息=%s",
                self.filepath.name,
                type(e).__name__,
                str(e),
                extra={"log_type": "SYSTEM", "scenario": scenario},
            )
            return pd.DataFrame()

    def _parse_customer_block_data(self, content: str) -> List[dict]:
        """
        解析自定义板块数据

        格式与标准板块文件相同：
        #板块名称
        股票代码1
        股票代码2
        ...
        """
        records = []

        try:
            lines = content.strip().split("\n")

            current_block = None
            current_codes = []

            for line in lines:
                line = line.strip()

                if not line:
                    continue

                # 板块名称以#开头
                if line.startswith("#"):
                    # 保存上一个板块
                    if current_block and current_codes:
                        records.append(
                            {
                                "block_name": current_block,
                                "code_list": current_codes.copy(),
                                "count": len(current_codes),
                                "custom": True,  # 标记为自定义板块
                            }
                        )

                    # 开始新板块
                    current_block = line[1:]  # 去掉#
                    current_codes = []

                else:
                    # 股票代码
                    if current_block:
                        current_codes.append(line)

            # 保存最后一个板块
            if current_block and current_codes:
                records.append(
                    {
                        "block_name": current_block,
                        "code_list": current_codes.copy(),
                        "count": len(current_codes),
                        "custom": True,
                    }
                )

        except Exception as e:
            logger.error(
                f"解析自定义板块数据失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"}
            )

        return records


# ==================== 扩展便捷函数 ====================


async def read_history_financial_data(filepath: Union[str, Path]) -> pd.DataFrame:
    """
    便捷函数：读取历史财务数据

    :param filepath: 财务数据文件路径（.zip或.dat）
    :return: DataFrame
    """
    reader = AsyncHistoryFinancialReader(filepath)
    return await reader.read()


async def read_exhq_day_data(filepath: Union[str, Path]) -> pd.DataFrame:
    """
    便捷函数：读取扩展行情日线数据

    :param filepath: 扩展行情.day文件路径
    :return: DataFrame
    """
    reader = AsyncTdxExHqDayReader(filepath)
    return await reader.read()


async def read_customer_block_data(filepath: Union[str, Path]) -> pd.DataFrame:
    """
    便捷函数：读取自定义板块数据

    :param filepath: 自定义板块文件路径
    :return: DataFrame
    """
    reader = AsyncCustomerBlockReader(filepath)
    return await reader.read()


# ==================== 使用示例 ====================


async def example_usage():
    """使用示例"""

    print("=== 本地数据读取器演示 ===")

    # 示例文件路径（需要根据实际通达信安装路径调整）
    tdx_dir = Path("C:/new_tdx/vipdoc")

    # 1. 读取日线数据
    day_file = tdx_dir / "sh" / "lday" / "sh600000.day"
    if day_file.exists():
        print(f"\n读取日线数据: {day_file}")
        df_day = await read_day_data(day_file)
        print(f"共 {len(df_day)} 条记录")
        print(df_day.head())

    # 2. 读取分钟线数据
    min_file = tdx_dir / "sh" / "minline" / "sh600000.lc1"
    if min_file.exists():
        print(f"\n读取分钟线数据: {min_file}")
        df_min = await read_minute_data(min_file)
        print(f"共 {len(df_min)} 条记录")
        print(df_min.head())

    # 3. 读取板块数据
    block_file = tdx_dir / "T0002" / "hq_cache" / "block_gn.dat"
    if block_file.exists():
        print(f"\n读取板块数据: {block_file}")
        df_block = await read_block_data(block_file)
        print(f"共 {len(df_block)} 个板块")
        print(df_block.head())


if __name__ == "__main__":
    asyncio.run(example_usage())
