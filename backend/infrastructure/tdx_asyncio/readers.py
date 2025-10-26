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
from pathlib import Path
from typing import List, Optional, Union

import aiofiles
import pandas as pd

from .logger import logger


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
        try:
            if not self.filepath.exists():
                logger.error(f"文件不存在: {self.filepath}")
                return pd.DataFrame()

            # 异步读取二进制文件
            async with aiofiles.open(self.filepath, 'rb') as f:
                data = await f.read()

            # 解析数据
            records = await asyncio.to_thread(self._parse_day_data, data)

            if not records:
                return pd.DataFrame()

            # 转换为DataFrame
            df = pd.DataFrame(records)

            logger.debug(f"成功读取日线数据: {len(df)}条, 文件={self.filepath.name}")
            return df

        except Exception as e:
            logger.error(f"读取日线数据失败: {e}")
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
        records = []

        try:
            record_count = len(data) // self.RECORD_SIZE

            for i in range(record_count):
                offset = i * self.RECORD_SIZE

                # 解包32字节数据
                record_bytes = data[offset:offset + self.RECORD_SIZE]

                if len(record_bytes) < self.RECORD_SIZE:
                    break

                # 解析（小端序）
                unpacked = struct.unpack('<IiiiiIfI', record_bytes)

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
                    date_obj = pd.to_datetime(date_str, format='%Y%m%d')

                    records.append({
                        'date': date_obj,
                        'open': open_price,
                        'high': high_price,
                        'low': low_price,
                        'close': close_price,
                        'volume': volume,
                        'amount': amount,
                    })

        except Exception as e:
            logger.error(f"解析日线数据失败: {e}")

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
        try:
            if not self.filepath.exists():
                logger.error(f"文件不存在: {self.filepath}")
                return pd.DataFrame()

            # 异步读取二进制文件
            async with aiofiles.open(self.filepath, 'rb') as f:
                data = await f.read()

            # 解析数据
            records = await asyncio.to_thread(self._parse_minute_data, data)

            if not records:
                return pd.DataFrame()

            # 转换为DataFrame
            df = pd.DataFrame(records)

            logger.debug(f"成功读取分钟线数据: {len(df)}条, 文件={self.filepath.name}")
            return df

        except Exception as e:
            logger.error(f"读取分钟线数据失败: {e}")
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

            for i in range(record_count):
                offset = i * self.RECORD_SIZE

                record_bytes = data[offset:offset + self.RECORD_SIZE]

                if len(record_bytes) < self.RECORD_SIZE:
                    break

                # 解析（小端序）
                unpacked = struct.unpack('<HHiiiiIi', record_bytes[:28])

                days = unpacked[0]
                minutes = unpacked[1]
                open_price = unpacked[2] / 100.0
                high_price = unpacked[3] / 100.0
                low_price = unpacked[4] / 100.0
                close_price = unpacked[5] / 100.0
                volume = unpacked[6]
                amount = unpacked[7] / 100.0

                # 计算日期时间
                base_date = pd.Timestamp('1900-01-01')
                date_obj = base_date + pd.Timedelta(days=days, minutes=minutes)

                records.append({
                    'datetime': date_obj,
                    'open': open_price,
                    'high': high_price,
                    'low': low_price,
                    'close': close_price,
                    'volume': volume,
                    'amount': amount,
                })

        except Exception as e:
            logger.error(f"解析分钟线数据失败: {e}")

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
        try:
            if not self.filepath.exists():
                logger.error(f"文件不存在: {self.filepath}")
                return pd.DataFrame()

            # 异步读取二进制文件
            async with aiofiles.open(self.filepath, 'rb') as f:
                data = await f.read()

            # 解析数据（与分钟线相同）
            records = await asyncio.to_thread(self._parse_lc5_data, data)

            if not records:
                return pd.DataFrame()

            # 转换为DataFrame
            df = pd.DataFrame(records)

            logger.debug(f"成功读取5分钟线数据: {len(df)}条, 文件={self.filepath.name}")
            return df

        except Exception as e:
            logger.error(f"读取5分钟线数据失败: {e}")
            return pd.DataFrame()

    def _parse_lc5_data(self, data: bytes) -> List[dict]:
        """解析5分钟线数据（格式与分钟线相同）"""
        records = []

        try:
            record_count = len(data) // self.RECORD_SIZE

            for i in range(record_count):
                offset = i * self.RECORD_SIZE
                record_bytes = data[offset:offset + self.RECORD_SIZE]

                if len(record_bytes) < self.RECORD_SIZE:
                    break

                unpacked = struct.unpack('<HHiiiiIi', record_bytes[:28])

                days = unpacked[0]
                minutes = unpacked[1]
                open_price = unpacked[2] / 100.0
                high_price = unpacked[3] / 100.0
                low_price = unpacked[4] / 100.0
                close_price = unpacked[5] / 100.0
                volume = unpacked[6]
                amount = unpacked[7] / 100.0

                base_date = pd.Timestamp('1900-01-01')
                date_obj = base_date + pd.Timedelta(days=days, minutes=minutes)

                records.append({
                    'datetime': date_obj,
                    'open': open_price,
                    'high': high_price,
                    'low': low_price,
                    'close': close_price,
                    'volume': volume,
                    'amount': amount,
                })

        except Exception as e:
            logger.error(f"解析5分钟线数据失败: {e}")

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
        try:
            if not self.filepath.exists():
                logger.error(f"文件不存在: {self.filepath}")
                return pd.DataFrame()

            # 异步读取文本文件（板块文件是文本格式）
            async with aiofiles.open(self.filepath, 'r', encoding='gbk') as f:
                content = await f.read()

            # 解析数据
            records = self._parse_block_data(content)

            if not records:
                return pd.DataFrame()

            # 转换为DataFrame
            df = pd.DataFrame(records)

            logger.debug(f"成功读取板块数据: {len(df)}个板块, 文件={self.filepath.name}")
            return df

        except Exception as e:
            logger.error(f"读取板块数据失败: {e}")
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

        try:
            lines = content.strip().split('\n')

            current_block = None
            current_codes = []

            for line in lines:
                line = line.strip()

                if not line:
                    continue

                # 板块名称以#开头
                if line.startswith('#'):
                    # 保存上一个板块
                    if current_block and current_codes:
                        records.append({
                            'block_name': current_block,
                            'code_list': current_codes.copy(),
                            'count': len(current_codes)
                        })

                    # 开始新板块
                    current_block = line[1:]  # 去掉#
                    current_codes = []

                else:
                    # 股票代码
                    if current_block:
                        current_codes.append(line)

            # 保存最后一个板块
            if current_block and current_codes:
                records.append({
                    'block_name': current_block,
                    'code_list': current_codes.copy(),
                    'count': len(current_codes)
                })

        except Exception as e:
            logger.error(f"解析板块数据失败: {e}")

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
                logger.error(f"文件不存在: {self.filepath}")
                return pd.DataFrame()

            # 检查文件类型
            if self.filepath.suffix == '.zip':
                # ZIP文件需要先解压
                import zipfile
                with zipfile.ZipFile(self.filepath, 'r') as zip_ref:
                    # 获取第一个.dat文件
                    dat_files = [f for f in zip_ref.namelist() if f.endswith('.dat')]
                    if not dat_files:
                        logger.error(f"ZIP文件中没有.dat文件: {self.filepath}")
                        return pd.DataFrame()

                    # 读取第一个dat文件
                    with zip_ref.open(dat_files[0]) as f:
                        data = f.read()
            else:
                # 直接读取.dat文件
                async with aiofiles.open(self.filepath, 'rb') as f:
                    data = await f.read()

            # 解析财务数据（简化版）
            records = self._parse_financial_data(data)

            if not records:
                return pd.DataFrame()

            # 转换为DataFrame
            df = pd.DataFrame(records)

            logger.debug(f"成功读取财务数据: {len(df)}条, 文件={self.filepath.name}")
            return df

        except Exception as e:
            logger.error(f"读取财务数据失败: {e}")
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

            logger.warning("财务数据解析功能需要完整实现，当前为框架版本")

            # 示例：假设数据是固定长度记录
            # 实际格式需要参考通达信财务数据格式文档

            return records

        except Exception as e:
            logger.error(f"解析财务数据失败: {e}")

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
        try:
            if not self.filepath.exists():
                logger.error(f"文件不存在: {self.filepath}")
                return pd.DataFrame()

            # 异步读取二进制文件
            async with aiofiles.open(self.filepath, 'rb') as f:
                data = await f.read()

            # 解析数据（与股票日线格式相同）
            records = self._parse_exhq_day_data(data)

            if not records:
                return pd.DataFrame()

            # 转换为DataFrame
            df = pd.DataFrame(records)

            logger.debug(f"成功读取扩展行情日线数据: {len(df)}条, 文件={self.filepath.name}")
            return df

        except Exception as e:
            logger.error(f"读取扩展行情日线数据失败: {e}")
            return pd.DataFrame()

    def _parse_exhq_day_data(self, data: bytes) -> List[dict]:
        """
        解析扩展行情日线数据

        格式与股票日线相同（32字节/条）
        """
        records = []

        try:
            record_count = len(data) // self.RECORD_SIZE

            for i in range(record_count):
                offset = i * self.RECORD_SIZE

                record_bytes = data[offset:offset + self.RECORD_SIZE]

                if len(record_bytes) < self.RECORD_SIZE:
                    break

                # 解析（小端序）
                unpacked = struct.unpack('<IiiiiIfI', record_bytes)

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
                    date_obj = pd.to_datetime(date_str, format='%Y%m%d')

                    records.append({
                        'date': date_obj,
                        'open': open_price,
                        'high': high_price,
                        'low': low_price,
                        'close': close_price,
                        'volume': volume,
                        'amount': amount,
                    })

        except Exception as e:
            logger.error(f"解析扩展行情日线数据失败: {e}")

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
        try:
            if not self.filepath.exists():
                logger.error(f"文件不存在: {self.filepath}")
                return pd.DataFrame()

            # 异步读取文本文件
            async with aiofiles.open(self.filepath, 'r', encoding='gbk') as f:
                content = await f.read()

            # 解析数据（与标准板块文件相同）
            records = self._parse_customer_block_data(content)

            if not records:
                return pd.DataFrame()

            # 转换为DataFrame
            df = pd.DataFrame(records)

            logger.debug(f"成功读取自定义板块数据: {len(df)}个板块, 文件={self.filepath.name}")
            return df

        except Exception as e:
            logger.error(f"读取自定义板块数据失败: {e}")
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
            lines = content.strip().split('\n')

            current_block = None
            current_codes = []

            for line in lines:
                line = line.strip()

                if not line:
                    continue

                # 板块名称以#开头
                if line.startswith('#'):
                    # 保存上一个板块
                    if current_block and current_codes:
                        records.append({
                            'block_name': current_block,
                            'code_list': current_codes.copy(),
                            'count': len(current_codes),
                            'custom': True  # 标记为自定义板块
                        })

                    # 开始新板块
                    current_block = line[1:]  # 去掉#
                    current_codes = []

                else:
                    # 股票代码
                    if current_block:
                        current_codes.append(line)

            # 保存最后一个板块
            if current_block and current_codes:
                records.append({
                    'block_name': current_block,
                    'code_list': current_codes.copy(),
                    'count': len(current_codes),
                    'custom': True
                })

        except Exception as e:
            logger.error(f"解析自定义板块数据失败: {e}")

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

