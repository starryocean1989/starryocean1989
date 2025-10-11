# -*- coding: utf-8 -*-
"""
数据读取器基类

定义统一的数据读取接口，所有数据读取器都应继承此基类。

设计模式：
- 采用模板方法模式
- read(): 读取原始数据
- standardize(): 标准化数据格式
- save(): 保存标准化后的数据
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

import pandas as pd


class BaseReader(ABC):
    """数据读取器抽象基类"""

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
