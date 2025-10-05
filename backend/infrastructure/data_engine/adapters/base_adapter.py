# -*- coding: utf-8 -*-
"""
数据适配器基类

提供所有数据适配器的统一接口和基础功能.
所有具体的数据适配器都应该继承自此类.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Union, Any
from datetime import datetime


class BaseDataAdapter(ABC):
    """
    数据适配器基类

    定义了所有数据适配器必须实现的接口方法.
    提供统一的数据获取,配置管理和错误处理机制.
    """

    def __init__(self, config: Dict[str, Union[str, int, float, bool]]) -> None:
        """
        初始化数据适配器

        Args:
            config: 适配器配置参数
        """
        self.config = config
        self.is_connected = False
        self.last_update = None

    @abstractmethod
    async def connect(self) -> bool:
        """
        连接到数据源

        Returns:
            bool: 连接是否成功
        """
        raise NotImplementedError

    @abstractmethod
    async def disconnect(self) -> bool:
        """
        断开与数据源的连接

        Returns:
            bool: 断开是否成功
        """
        raise NotImplementedError

    @abstractmethod
    async def get_quotes(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        获取行情数据

        Args:
            symbols: 股票代码列表

        Returns:
            List[Dict[str, Any]]: 行情数据列表
        """
        raise NotImplementedError

    @abstractmethod
    async def get_historical_data(
        self,
        symbol: str,
        start_date: datetime,
        end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        获取历史数据

        Args:
            symbol: 股票代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            List[Dict[str, Any]]: 历史数据列表
        """
        raise NotImplementedError

    def get_config(self, key: str, default: Any = None) -> Any:
        """
        获取配置参数

        Args:
            key: 配置键
            default: 默认值

        Returns:
            Any: 配置值
        """
        return self.config.get(key, default)

    def update_config(self, key: str, value: Any) -> None:
        """
        更新配置参数

        Args:
            key: 配置键
            value: 配置值
        """
        self.config[key] = value
        self.last_update = datetime.now()


__all__ = ["BaseDataAdapter"]
