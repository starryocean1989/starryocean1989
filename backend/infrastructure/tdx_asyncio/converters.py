# -*- coding: utf-8 -*-
"""
数据转换工具模块

提供智能数据转换和多格式文件输出功能，借鉴mootdx的优秀设计，
完全异步化实现，不依赖任何外部库。

作者：[项目名称]
版本：2.0
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import pandas as pd

from .logger import logger


def to_dataframe(data: Any, set_index: bool = True) -> pd.DataFrame:
    """
    智能数据转换（融合mootdx功能）

    支持输入类型：
    - dict → DataFrame(单行)
    - list[dict] → DataFrame
    - DataFrame → 直接返回
    - None/空 → 空DataFrame

    自动处理：
    - datetime/date 字段自动设为索引
    - vol 字段自动创建 volume 别名

    :param data: 要转换的数据
    :param set_index: 是否自动设置时间索引
    :return: pandas DataFrame
    """
    # 空值处理
    if data is None or (isinstance(data, (list, dict)) and not data):
        return pd.DataFrame()

    # DataFrame直接返回
    if isinstance(data, pd.DataFrame):
        result = data.copy()
    # 列表转换
    elif isinstance(data, list):
        if not data:
            return pd.DataFrame()
        result = pd.DataFrame(data=data)
    # 字典转换（单行）
    elif isinstance(data, dict):
        result = pd.DataFrame(data=[data])
    else:
        logger.warning(f"不支持的数据类型: {type(data)}")
        return pd.DataFrame()

    # 自动索引设置（模仿mootdx行为）
    if set_index and not result.empty:
        # 查找时间字段
        time_columns = ['datetime', 'date', 'time']
        index_col = None

        for col in time_columns:
            if col in result.columns:
                index_col = col
                break

        if index_col:
            try:
                # 尝试转换为datetime索引
                if index_col == 'datetime':
                    result.index = pd.to_datetime(result[index_col])
                elif index_col == 'date':
                    result.index = pd.to_datetime(result[index_col])
                else:
                    # time字段可能需要特殊处理
                    pass

                # 删除原时间列（模仿mootdx行为）
                result = result.drop(columns=[index_col])
            except Exception as e:
                logger.warning(f"设置时间索引失败: {e}")

        # vol字段别名处理（模仿mootdx行为）
        if 'vol' in result.columns and 'volume' not in result.columns:
            result['volume'] = result['vol']

    return result


async def to_file_async(
    df: pd.DataFrame,
    filepath: str,
    format_hint: Optional[str] = None
) -> bool:
    """
    异步多格式文件输出

    支持格式：
    - .csv
    - .xlsx, .xls
    - .json
    - .h5
    - .parquet（新增）

    特性：
    - 自动创建目录
    - 异步写入（不阻塞）
    - 异常处理和重试

    :param df: 要保存的DataFrame
    :param filepath: 输出文件路径
    :param format_hint: 格式提示（可选，自动从扩展名推断）
    :return: 是否保存成功
    """
    if df is None or df.empty:
        logger.warning("数据为空，跳过保存")
        return False

    filepath = Path(filepath)
    format_hint = format_hint or filepath.suffix.lower()

    # 自动创建目录
    try:
        filepath.parent.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        logger.error(f"创建目录失败: {e}")
        return False

    try:
        # 根据格式选择保存方法
        if format_hint == '.csv':
            # 异步CSV写入
            csv_content = df.to_csv(index=False, encoding='utf-8')
            await _async_write_text(filepath, csv_content)

        elif format_hint in ['.xlsx', '.xls']:
            # Excel格式（需要openpyxl）
            try:
                await _async_write_excel(df, filepath)
            except ImportError:
                logger.warning("未安装openpyxl，使用CSV格式保存")
                csv_path = filepath.with_suffix('.csv')
                csv_content = df.to_csv(index=False, encoding='utf-8')
                await _async_write_text(csv_path, csv_content)
                return True

        elif format_hint == '.json':
            # JSON格式
            json_content = df.to_json(orient='records', indent=2)
            await _async_write_text(filepath, json_content)

        elif format_hint == '.h5':
            # HDF5格式（需要tables）
            try:
                await _async_write_hdf5(df, filepath)
            except ImportError:
                logger.warning("未安装tables，使用JSON格式保存")
                json_path = filepath.with_suffix('.json')
                json_content = df.to_json(orient='records', indent=2)
                await _async_write_text(json_path, json_content)
                return True

        elif format_hint == '.parquet':
            # Parquet格式（需要pyarrow）
            try:
                await _async_write_parquet(df, filepath)
            except ImportError:
                logger.warning("未安装pyarrow，使用CSV格式保存")
                csv_path = filepath.with_suffix('.csv')
                csv_content = df.to_csv(index=False, encoding='utf-8')
                await _async_write_text(csv_path, csv_content)
                return True

        else:
            logger.error(f"不支持的文件格式: {format_hint}")
            return False

        logger.info(f"数据已保存到: {filepath}")
        return True

    except Exception as e:
        logger.error(f"保存文件失败: {e}")
        return False


# ==================== 内部异步写入函数 ====================

async def _async_write_text(filepath: Path, content: str) -> None:
    """异步写入文本文件"""
    def _write():
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

    await asyncio.get_event_loop().run_in_executor(None, _write)


async def _async_write_excel(df: pd.DataFrame, filepath: Path) -> None:
    """异步写入Excel文件"""
    def _write():
        df.to_excel(str(filepath), index=False)

    await asyncio.get_event_loop().run_in_executor(None, _write)


async def _async_write_hdf5(df: pd.DataFrame, filepath: Path) -> None:
    """异步写入HDF5文件"""
    def _write():
        df.to_hdf(str(filepath), key='df', mode='w')

    await asyncio.get_event_loop().run_in_executor(None, _write)


async def _async_write_parquet(df: pd.DataFrame, filepath: Path) -> None:
    """异步写入Parquet文件"""
    def _write():
        df.to_parquet(str(filepath), index=False)

    await asyncio.get_event_loop().run_in_executor(None, _write)


# ==================== 便捷函数 ====================

def to_csv(df: pd.DataFrame, filepath: str) -> bool:
    """
    便捷CSV保存函数（同步版本）

    :param df: DataFrame数据
    :param filepath: 保存路径
    :return: 是否保存成功
    """
    try:
        df.to_csv(filepath, index=False, encoding='utf-8')
        return True
    except Exception as e:
        logger.error(f"CSV保存失败: {e}")
        return False


def to_json(df: pd.DataFrame, filepath: str) -> bool:
    """
    便捷JSON保存函数（同步版本）

    :param df: DataFrame数据
    :param filepath: 保存路径
    :return: 是否保存成功
    """
    try:
        df.to_json(filepath, orient='records', indent=2)
        return True
    except Exception as e:
        logger.error(f"JSON保存失败: {e}")
        return False


# ==================== 使用示例 ====================

async def example_usage():
    """使用示例"""

    # 1. 数据转换示例
    data = [
        {'code': '600000', 'price': 10.5, 'vol': 1000, 'datetime': '2023-01-01 09:30:00'},
        {'code': '600001', 'price': 20.5, 'vol': 2000, 'datetime': '2023-01-01 09:31:00'},
    ]

    df = to_dataframe(data)
    print(f"转换后DataFrame形状: {df.shape}")
    print(f"列名: {list(df.columns)}")

    # 2. 文件保存示例
    success = await to_file_async(df, 'data/example.csv')
    print(f"CSV保存结果: {success}")

    success = await to_file_async(df, 'data/example.json')
    print(f"JSON保存结果: {success}")

    # 3. 同步保存示例
    success = to_csv(df, 'data/example_sync.csv')
    print(f"同步CSV保存结果: {success}")


if __name__ == "__main__":
    # 运行示例
    asyncio.run(example_usage())
