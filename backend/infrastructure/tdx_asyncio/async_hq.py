# -*- coding: utf-8 -*-
"""
异步标准行情API
"""
import asyncio
from typing import List, Tuple, Optional

from .async_base_socket_client import AsyncBaseSocketClient, async_last_ack_time
from .constants import TDXParams
from .parser.async_setup_commands import AsyncSetupCmd1, AsyncSetupCmd2, AsyncSetupCmd3
from .parser.std.async_get_security_bars import AsyncGetSecurityBarsCmd
from .parser.std.async_get_security_quotes import AsyncGetSecurityQuotesCmd
from .parser.std.async_get_security_list import AsyncGetSecurityList
from .parser.std.async_get_xdxr_info import AsyncGetXdXrInfo
from .parser.std.async_get_minute_time_data import AsyncGetMinuteTimeData
from .parser.std.async_get_index_bars import AsyncGetIndexBarsCmd
from .parser.std.async_get_history_minute_time_data import AsyncGetHistoryMinuteTimeData
from .parser.std.async_get_transaction_data import AsyncGetTransactionData
from .parser.std.async_get_history_transaction_data import AsyncGetHistoryTransactionData
from .parser.std.async_get_finance_info import AsyncGetFinanceInfo


class AsyncTdxHq_API(AsyncBaseSocketClient):
    """
    异步通达信行情API
    使用asyncio实现纯异步通信
    """

    async def setup(self):
        """
        初始化连接（异步）
        """
        cmd1 = AsyncSetupCmd1(self.reader, self.writer, lock=self.lock)
        await cmd1.call_api()

        cmd2 = AsyncSetupCmd2(self.reader, self.writer, lock=self.lock)
        await cmd2.call_api()

        cmd3 = AsyncSetupCmd3(self.reader, self.writer, lock=self.lock)
        await cmd3.call_api()

    @async_last_ack_time
    async def get_security_bars(
        self,
        category: int,
        market: int,
        code: str,
        start: int,
        count: int
    ) -> Optional[List[dict]]:
        """
        获取K线数据（异步）

        :param category: K线类型 (0=5分钟, 4=日K线, 8=1分钟)
        :param market: 市场 (0=深圳, 1=上海)
        :param code: 股票代码
        :param start: 起始位置
        :param count: 数量（最大800）
        :return: K线数据列表
        """
        cmd = AsyncGetSecurityBarsCmd(self.reader, self.writer, lock=self.lock)
        cmd.setParams(category, market, code, start, count)

        return await cmd.call_api()

    @async_last_ack_time
    async def get_security_quotes(self, all_stock=None, code=None) -> Optional[List[dict]]:
        """
        获取实时行情（异步，支持批量查询）

        支持三种形式的参数：
        - get_security_quotes(market, code)
        - get_security_quotes((market, code))
        - get_security_quotes([(market1, code1), (market2, code2)])

        :param all_stock: (market, code) 的列表或元组
        :param code: 可选，单个股票代码
        :return: 实时行情数据列表
        """
        if code:
            all_stock = [(all_stock, code)]
        elif (
            (isinstance(all_stock, list) or isinstance(all_stock, tuple))
            and len(all_stock) == 2
            and type(all_stock[0]) is int
        ):
            all_stock = [all_stock]

        cmd = AsyncGetSecurityQuotesCmd(self.reader, self.writer, lock=self.lock)
        cmd.setParams(all_stock)

        return await cmd.call_api()

    @async_last_ack_time
    async def get_security_list(self, market: int, start: int) -> Optional[List[dict]]:
        """
        获取证券列表（异步，支持分页）

        :param market: 市场 (0=深圳, 1=上海)
        :param start: 开始位置
        :return: 证券列表数据
        """
        cmd = AsyncGetSecurityList(self.reader, self.writer, lock=self.lock)
        cmd.setParams(market, start)

        return await cmd.call_api()

    @async_last_ack_time
    async def get_xdxr_info(self, market: int, code: str) -> Optional[List[dict]]:
        """
        获取除权除息信息（异步）

        :param market: 市场 (0=深圳, 1=上海)
        :param code: 股票代码
        :return: 除权除息数据列表
        """
        cmd = AsyncGetXdXrInfo(self.reader, self.writer, lock=self.lock)
        cmd.setParams(market, code)

        return await cmd.call_api()

    @async_last_ack_time
    async def get_minute_time_data(self, market: int, code: str) -> Optional[List[dict]]:
        """
        获取当日分时图数据（异步）

        :param market: 市场 (0=深圳, 1=上海)
        :param code: 股票代码
        :return: 分时图数据列表（242个分钟点）
        """
        cmd = AsyncGetMinuteTimeData(self.reader, self.writer, lock=self.lock)
        cmd.setParams(market, code)

        return await cmd.call_api()

    @async_last_ack_time
    async def get_index_bars(
        self,
        category: int,
        market: int,
        code: str,
        start: int,
        count: int
    ) -> Optional[List[dict]]:
        """
        获取指数K线数据（异步）

        :param category: K线类型 (0=5分钟, 4=日K线, 8=1分钟)
        :param market: 市场 (0=深圳, 1=上海)
        :param code: 指数代码
        :param start: 起始位置
        :param count: 数量（最大800）
        :return: 指数K线数据列表（包含up_count和down_count）
        """
        cmd = AsyncGetIndexBarsCmd(self.reader, self.writer, lock=self.lock)
        cmd.setParams(category, market, code, start, count)

        return await cmd.call_api()

    @async_last_ack_time
    async def get_history_minute_time_data(self, market: int, code: str, date: int) -> Optional[List[dict]]:
        """
        获取历史分时图数据（异步）

        :param market: 市场 (0=深圳, 1=上海)
        :param code: 股票代码
        :param date: 日期，格式20161201的整型
        :return: 分时图数据列表（242个分钟点）
        """
        cmd = AsyncGetHistoryMinuteTimeData(self.reader, self.writer, lock=self.lock)
        cmd.setParams(market, code, date)

        return await cmd.call_api()

    @async_last_ack_time
    async def get_transaction_data(self, market: int, code: str, start: int, count: int) -> Optional[List[dict]]:
        """
        获取当日逐笔成交数据（异步）

        :param market: 市场 (0=深圳, 1=上海)
        :param code: 股票代码
        :param start: 起始位置
        :param count: 数量（最大2000）
        :return: 逐笔成交数据列表（时间、价格、成交量、买卖方向）
        """
        cmd = AsyncGetTransactionData(self.reader, self.writer, lock=self.lock)
        cmd.setParams(market, code, start, count)

        return await cmd.call_api()

    @async_last_ack_time
    async def get_history_transaction_data(
        self,
        market: int,
        code: str,
        start: int,
        count: int,
        date: int
    ) -> Optional[List[dict]]:
        """
        获取历史逐笔成交数据（异步）

        :param market: 市场 (0=深圳, 1=上海)
        :param code: 股票代码
        :param start: 起始位置
        :param count: 数量（最大2000）
        :param date: 日期，格式20161201的整型
        :return: 历史逐笔成交数据列表（时间、价格、成交量、买卖方向）
        """
        cmd = AsyncGetHistoryTransactionData(self.reader, self.writer, lock=self.lock)
        cmd.setParams(market, code, start, count, date)

        return await cmd.call_api()

    @async_last_ack_time
    async def get_finance_info(self, market: int, code: str) -> Optional[dict]:
        """
        获取财务信息（异步）

        :param market: 市场 (0=深圳, 1=上海)
        :param code: 股票代码
        :return: 财务信息字典（包含33个字段：股本、资产、利润等）
        """
        cmd = AsyncGetFinanceInfo(self.reader, self.writer, lock=self.lock)
        cmd.setParams(market, code)

        return await cmd.call_api()

    @staticmethod
    async def factory(
        server: Tuple[str, int],
        timeout: float = 5.0,
        heartbeat: bool = False,
        auto_retry: bool = False,
        raise_exception: bool = True
    ) -> Optional['AsyncTdxHq_API']:
        """
        工厂方法：创建并连接异步行情客户端

        :param server: 服务器地址 (ip, port)
        :param timeout: 连接超时时间
        :param heartbeat: 是否启动心跳
        :param auto_retry: 是否自动重试
        :param raise_exception: 是否抛出异常
        :return: 已连接的客户端实例
        """
        ip, port = server

        client = AsyncTdxHq_API(
            heartbeat=heartbeat,
            auto_retry=auto_retry,
            raise_exception=raise_exception
        )

        result = await client.connect(ip=ip, port=port, time_out=timeout)

        if result is False:
            return None

        return client

