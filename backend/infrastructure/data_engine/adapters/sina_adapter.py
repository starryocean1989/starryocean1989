# -*- coding: utf-8 -*-

"""
新浪财经数据适配器.

本模块实现了新浪财经数据源的适配器,
用于获取实时和历史的市场数据.
"""

from datetime import datetime
from typing import Dict, List, Optional, Union
from urllib.parse import urlencode

import aiohttp

from .base_adapter import BaseDataAdapter


class SinaDataAdapter(BaseDataAdapter):
    """
    新浪财经数据适配器.

    继承自BaseDataAdapter,提供新浪财经数据的获取功能.
    """

    def __init__(
        self, config: Dict[str, Union[str, int, float, bool]]
    ) -> None:
        """
        初始化新浪财经适配器.

        Args:
            config: 配置字典,包含API密钥,超时设置等
        """
        super().__init__(config)
        self._name = "SINA"
        self._description = "新浪财经数据源适配器"
        self._version = "1.0.0"
        self._base_url = "https://hq.sinajs.cn/"
        self._session: Optional[aiohttp.ClientSession] = None
        self.last_connection_time: Optional[datetime] = None

    @property
    def name(self) -> str:
        """适配器名称."""
        return self._name

    @property
    def description(self) -> str:
        """适配器描述."""
        return self._description

    @property
    def version(self) -> str:
        """适配器版本."""
        return self._version

    async def connect(self) -> bool:
        """
        连接到新浪财经数据源.

        Returns:
            bool: 连接是否成功
        """
        try:
            if self._session is None:
                timeout = aiohttp.ClientTimeout(total=30)
                self._session = aiohttp.ClientSession(timeout=timeout)

            self.is_connected = True
            self.last_connection_time = datetime.utcnow()
            return True

        except (aiohttp.ClientError, OSError):
            self.is_connected = False
            return False

    async def disconnect(self) -> bool:
        """
        断开数据源连接.

        Returns:
            bool: 断开是否成功
        """
        try:
            if self._session:
                await self._session.close()
                self._session = None

            self.is_connected = False
            return True

        except (aiohttp.ClientError, OSError):
            return False

    def _check_connection(self) -> bool:
        """
        检查连接状态.

        Returns:
            bool: 是否已连接
        """
        return self.is_connected and self._session is not None

    def _format_symbol(self, symbol: str) -> str:
        """
        格式化证券代码为新浪格式.

        Args:
            symbol: 证券代码

        Returns:
            str: 新浪格式的代码
        """
        # 新浪财经代码格式转换
        if symbol.startswith("0") or symbol.startswith("3"):
            return f"sz{symbol}"
        elif symbol.startswith("6") or symbol.startswith("9"):
            return f"sh{symbol}"
        else:
            return symbol

    async def get_market_data(
        self, symbol: str, _data_type: str = "kline"  # noqa: U101
    ) -> Optional[Dict[str, Union[str, int, float, bool]]]:
        """
        获取市场数据.

        Args:
            symbol: 证券代码
            data_type: 数据类型 (kline, quote, orderbook等)

        Returns:
            Optional[Dict[str, Union[str, int, float, bool]]]: 市场数据字典
        """
        try:
            if not self._check_connection():
                return None

            formatted_symbol = self._format_symbol(symbol)

            # 构建请求URL
            params = {"list": formatted_symbol}
            url = f"{self._base_url}?{urlencode(params)}"

            # 类型检查时忽略aiohttp的具体类型
            async with self._session.get(url) as response:
                if response.status == 200:
                    text = await response.text()
                    return self._parse_market_data(text, symbol)
                else:
                    return None

        except (aiohttp.ClientError, OSError, ValueError):
            return None

    def _parse_market_data(
        self, raw_data: str, symbol: str
    ) -> Dict[str, Union[str, int, float, bool]]:
        """
        解析新浪财经返回的原始数据.

        Args:
            raw_data: 原始数据字符串
            symbol: 证券代码

        Returns:
            Dict[str, Union[str, int, float, bool]]: 解析后的数据
        """
        try:
            # 新浪财经数据格式: var hq_str_sz000001="平安银行,12.34,12.35,..."
            lines = raw_data.strip().split("\n")
            for line in lines:
                if f"hq_str_{self._format_symbol(symbol)}" in line:
                    # 提取数据部分
                    data_part = line.split("=")[1].strip('";')
                    fields = data_part.split(",")

                    if len(fields) >= 6:
                        return {
                            "symbol": symbol,
                            "name": fields[0],
                            "price": float(fields[3]) if fields[3] else 0.0,
                            "change": float(fields[4]) if fields[4] else 0.0,
                            "change_percent": (
                                float(fields[5]) if fields[5] else 0.0
                            ),
                            "volume": (
                                int(fields[8])
                                if len(fields) > 8 and fields[8]
                                else 0
                            ),
                            "amount": (
                                float(fields[9])
                                if len(fields) > 9 and fields[9]
                                else 0.0
                            ),
                            "timestamp": datetime.utcnow().isoformat(),
                            "source": "sina",
                        }

            return {}

        except (ValueError, IndexError, KeyError):
            return {}

    async def get_historical_data(
        self,
        _symbol: str,  # noqa: U101
        _start_date: datetime,  # noqa: U101
        _end_date: datetime,  # noqa: U101
        _data_type: str = "kline",  # noqa: U101
    ) -> List[Dict[str, Union[str, int, float, bool]]]:
        """
        获取历史数据.

        注意:新浪财经API可能不提供完整的K线历史数据,
        此方法返回空列表,建议使用其他数据源获取历史数据.

        Args:
            symbol: 证券代码
            start_date: 开始日期
            end_date: 结束日期
            data_type: 数据类型

        Returns:
            List[Dict[str, Union[str, int, float, bool]]]: 历史数据列表
        """
        # 新浪财经主要提供实时数据,历史数据功能受限
        # 返回空列表,建议使用其他数据源
        return []

    async def cleanup(self) -> None:
        """清理资源."""
        await self.disconnect()
