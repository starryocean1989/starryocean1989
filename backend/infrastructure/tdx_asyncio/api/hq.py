# -*- coding: utf-8 -*-
"""
异步标准行情API

概述
- 提供通达信标准行情的纯异步接口，基于 `asyncio` 构建，适用于批量查询与高并发场景。
- 封装了常用的标准行情方法，并提供周期映射与安全调用的高级辅助函数。

快速上手
- 使用 `AsyncTdxHq_API.factory((ip, port))` 建立连接，或结合连接池进行候选与回退。
- 周期与分类映射：`"1d" -> 4`，`"5m" -> 0`，`"1m" -> 8`（详见 `utils.helper.interval_to_category`）。
- 服务器候选推荐：优先使用 `network.constants.BROKER_SERVERS_7709` 中的稳定券商节点。

示例
>>> from backend.infrastructure.tdx_asyncio.api.hq import AsyncTdxHq_API
>>> client = await AsyncTdxHq_API.factory(("119.147.171.206", 7709))
>>> if client:
...     bars = await client.get_security_bars(4, 1, "600000", 0, 800)
...     quotes = await client.get_security_quotes([(1, "600000"), (0, "000001")])
...     await client.disconnect()
"""
import asyncio
from typing import List, Tuple, Optional

from ..core.socket_client import AsyncBaseSocketClient, async_last_ack_time
from ..network.constants import TDXParams
from ..parsers.setup import AsyncSetupCmd1, AsyncSetupCmd2, AsyncSetupCmd3
from ..parsers.std.bars import AsyncGetSecurityBarsCmd
from ..parsers.std.quotes import AsyncGetSecurityQuotesCmd
from ..parsers.std.list import AsyncGetSecurityList
from ..parsers.std.xdxr import AsyncGetXdXrInfo
from ..parsers.std.minute_time import AsyncGetMinuteTimeData
from ..parsers.std.index_bars import AsyncGetIndexBarsCmd
from ..parsers.std.history_minute import AsyncGetHistoryMinuteTimeData
from ..parsers.std.transaction import AsyncGetTransactionData
from ..parsers.std.history_transaction import AsyncGetHistoryTransactionData
from ..parsers.std.finance import AsyncGetFinanceInfo


class AsyncTdxHq_API(AsyncBaseSocketClient):
    """
    异步通达信行情API（标准行情）

    设计特性
    - 纯异步：基于 `asyncio.open_connection` 与异步锁实现并发安全。
    - 自动初始化：`connect` 成功后会自动调用 `setup` 完成三次握手，无需手动触发。
    - 可选重试：通过 `auto_retry` 控制失败后的重试策略；`raise_exception=False` 时返回 `None/False` 表示失败。

    使用建议
    - 单连接：直接使用 `factory((ip, port))` 创建并连接；完成后调用 `disconnect` 释放。
    - 多连接：结合连接池模块进行主备管理与故障转移，提升可用性与吞吐。
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
        self, category: int, market: int, code: str, start: int, count: int
    ) -> Optional[List[dict]]:
        """
        获取K线数据（异步）

        :param category: K线类型 (0=5分钟, 4=日K线, 8=1分钟)
        :param market: 市场 (0=深圳, 1=上海, 2=北交所)
        :param code: 股票代码
        :param start: 起始位置
        :param count: 数量（最大800）
        :return: K线数据列表

        返回字段概览
        - `open/close/high/low`: 开收高低价
        - `vol/amount`: 成交量（股）与成交额（元）
        - `datetime`: 形如 `YYYY-MM-DD HH:MM`（详见 `parsers.std.bars`）
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

        返回字段概览
        - 价格相关：`price/open/high/low/last_close`
        - 交易相关：`vol/cur_vol/amount/s_vol/b_vol`
        - 五档：`bid1..bid5/ask1..ask5/bid_vol1..bid_vol5/ask_vol1..ask_vol5`
        - 其他：`servertime/active1/active2/reversed_bytes*`、`reversed_bytes9`（涨速）
        详见 `parsers.std.quotes.AsyncGetSecurityQuotesCmd.parseResponse`
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

        :param market: 市场 (0=深圳, 1=上海, 2=北交所)
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

        :param market: 市场 (0=深圳, 1=上海, 2=北交所)
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

        :param market: 市场 (0=深圳, 1=上海, 2=北交所)
        :param code: 股票代码
        :return: 分时图数据列表（242个分钟点）
        """
        cmd = AsyncGetMinuteTimeData(self.reader, self.writer, lock=self.lock)
        cmd.setParams(market, code)

        return await cmd.call_api()

    @async_last_ack_time
    async def get_index_bars(
        self, category: int, market: int, code: str, start: int, count: int
    ) -> Optional[List[dict]]:
        """
        获取指数K线数据（异步）

        :param category: K线类型 (0=5分钟, 4=日K线, 8=1分钟)
        :param market: 市场 (0=深圳, 1=上海, 2=北交所)
        :param code: 指数代码
        :param start: 起始位置
        :param count: 数量（最大800）
        :return: 指数K线数据列表（结构与普通K线一致，部分指数包含涨跌家数等附加字段）
        """
        cmd = AsyncGetIndexBarsCmd(self.reader, self.writer, lock=self.lock)
        cmd.setParams(category, market, code, start, count)

        return await cmd.call_api()

    @async_last_ack_time
    async def get_history_minute_time_data(
        self, market: int, code: str, date: int
    ) -> Optional[List[dict]]:
        """
        获取历史分时图数据（异步）

        :param market: 市场 (0=深圳, 1=上海, 2=北交所)
        :param code: 股票代码
        :param date: 日期，格式20161201的整型
        :return: 分时图数据列表（242个分钟点）
        """
        cmd = AsyncGetHistoryMinuteTimeData(self.reader, self.writer, lock=self.lock)
        cmd.setParams(market, code, date)

        return await cmd.call_api()

    @async_last_ack_time
    async def get_transaction_data(
        self, market: int, code: str, start: int, count: int
    ) -> Optional[List[dict]]:
        """
        获取当日逐笔成交数据（异步）

        :param market: 市场 (0=深圳, 1=上海, 2=北交所)
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
        self, market: int, code: str, start: int, count: int, date: int
    ) -> Optional[List[dict]]:
        """
        获取历史逐笔成交数据（异步）

        :param market: 市场 (0=深圳, 1=上海, 2=北交所)
        :param code: 股票代码
        :param start: 起始位置
        :param count: 数量（最大2000）
        :param date: 日期，格式20161201的整型
        :return: 历史逐笔成交数据列表（时间、价格、成交量、买卖方向）

        返回字段概览
        - `time`: 逐笔时间，`HH:MM:SS`（详见 `utils.helper.get_time`）
        - `price/vol`: 成交价格与数量
        - `buyorsell`: 买卖方向（可能返回 `B/S/` 等）
        """
        cmd = AsyncGetHistoryTransactionData(self.reader, self.writer, lock=self.lock)
        cmd.setParams(market, code, start, count, date)

        return await cmd.call_api()

    @async_last_ack_time
    async def get_finance_info(self, market: int, code: str) -> Optional[dict]:
        """
        获取财务信息（异步）

        :param market: 市场 (0=深圳, 1=上海, 2=北交所)
        :param code: 股票代码
        :return: 财务信息字典（包含33个字段：股本、资产、利润等）

        字段说明
        - 详见 `parsers.std.finance.AsyncGetFinanceInfo` 中的逐项定义与单位换算（多数以万元为单位返回，已转换为元或股）。
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
        raise_exception: bool = True,
    ) -> Optional["AsyncTdxHq_API"]:
        """
        工厂方法：创建并连接异步行情客户端

        :param server: 服务器地址 (ip, port)
        :param timeout: 连接超时时间
        :param heartbeat: 是否启动心跳
        :param auto_retry: 是否自动重试
        :param raise_exception: 是否抛出异常
        :return: 已连接的客户端实例；连接失败返回 `None`

        说明
        - 成功建立后自动执行 `setup` 完成握手；失败时根据 `raise_exception` 决定是否抛出异常。
        - 建议结合 `BROKER_SERVERS_7709` 或连接池进行候选与回退，以提升稳定性。
        """
        ip, port = server

        client = AsyncTdxHq_API(
            heartbeat=heartbeat, auto_retry=auto_retry, raise_exception=raise_exception
        )

        result = await client.connect(ip=ip, port=port, time_out=timeout)

        if result is False:
            return None

        return client


# ==============================================================================
# 高级封装函数
# ==============================================================================


async def get_security_list_batch(
    api: AsyncTdxHq_API,
    market: int,
    start: int = 0,
    page_size: int = 1000,
    max_pages: Optional[int] = None,
) -> List[dict]:
    """
    批量获取股票列表（支持自动分页）

    Args:
        api: AsyncTdxHq_API 实例
        market: 市场代码 (0=深圳, 1=上海, 2=北交所)
        start: 起始位置（默认0）
        page_size: 每页大小（默认1000，TDX API限制）
        max_pages: 最大页数（None表示获取所有）

    Returns:
        股票列表数据

    Examples:
        >>> api = AsyncTdxHq_API()
        >>> await api.connect("119.147.171.206", 7709)
        >>> stocks = await get_security_list_batch(api, market=1)
        >>> print(f"获取到 {len(stocks)} 只股票")
    """
    from ..utils.logger import logger

    all_stocks = []
    current_start = start
    page_count = 0

    while True:
        if max_pages is not None and page_count >= max_pages:
            break

        try:
            page_result = await api.get_security_list(market=market, start=current_start)

            if not page_result or len(page_result) == 0:
                break

            all_stocks.extend(page_result)
            page_count += 1

            # 如果返回的数据少于page_size，说明已经是最后一页
            if len(page_result) < page_size:
                break

            # 更新起始位置
            current_start += len(page_result)

        except Exception as e:
            logger.warning(f"获取股票列表失败: market={market}, start={current_start}, 错误: {e}")
            break

    return all_stocks


async def get_security_list_all(
    api: AsyncTdxHq_API,
    market: int,
) -> List[dict]:
    """
    获取所有股票列表（自动处理分页）

    Args:
        api: AsyncTdxHq_API 实例
        market: 市场代码 (0=深圳, 1=上海, 2=北交所)

    Returns:
        所有股票列表数据

    Examples:
        >>> api = AsyncTdxHq_API()
        >>> await api.connect("119.147.171.206", 7709)
        >>> stocks = await get_security_list_all(api, market=1)
        >>> print(f"获取到 {len(stocks)} 只股票")
    """
    return await get_security_list_batch(api, market=market, start=0, max_pages=None)


async def get_security_bars_by_interval(
    api: AsyncTdxHq_API,
    symbol: str,
    interval: str,
    market: Optional[int] = None,
    start: int = 0,
    count: int = 10000,
) -> Optional[List[dict]]:
    """
    按周期获取K线数据（自动处理周期映射）

    Args:
        api: AsyncTdxHq_API 实例
        symbol: 股票代码
        interval: 周期字符串 ("1d", "5m", "1m")
        market: 市场代码 (0=深圳, 1=上海, 2=北交所)，如果为None则自动判断
        start: 起始位置（默认0）
        count: 数量（默认10000，最大800）

    Returns:
        K线数据列表

    Raises:
        ValueError: 当interval不支持时

    Examples:
        >>> api = AsyncTdxHq_API()
        >>> await api.connect("119.147.171.206", 7709)
        >>> bars = await get_security_bars_by_interval(api, "600000", "1d", market=1)
        >>> print(f"获取到 {len(bars)} 条K线")
    """
    from ..utils.helper import interval_to_category, get_market_from_code

    # 自动判断市场
    if market is None:
        market = get_market_from_code(symbol, strict=False)

    # 转换周期到category
    category = interval_to_category(interval)

    # 限制count不超过800（TDX API限制）
    count = min(count, 800)

    return await api.get_security_bars(
        category=category,
        market=market,
        code=symbol,
        start=start,
        count=count,
    )


async def get_security_bars_safe(
    api: AsyncTdxHq_API,
    symbol: str,
    interval: str,
    market: Optional[int] = None,
    start: int = 0,
    count: int = 10000,
    timeout: float = 10.0,
) -> Optional[List[dict]]:
    """
    安全获取K线数据（自动处理市场代码、周期映射、错误处理）

    Args:
        api: AsyncTdxHq_API 实例
        symbol: 股票代码
        interval: 周期字符串 ("1d", "5m", "1m")
        market: 市场代码 (0=深圳, 1=上海, 2=北交所)，如果为None则自动判断
        start: 起始位置（默认0）
        count: 数量（默认10000，最大800）
        timeout: 超时时间（秒，默认10.0）

    Returns:
        K线数据列表，失败返回None

    Examples:
        >>> api = AsyncTdxHq_API()
        >>> await api.connect("119.147.171.206", 7709)
        >>> bars = await get_security_bars_safe(api, "600000", "1d")
        >>> if bars:
        >>>     print(f"获取到 {len(bars)} 条K线")
    """
    from ..utils.logger import logger

    try:
        return await asyncio.wait_for(
            get_security_bars_by_interval(
                api=api,
                symbol=symbol,
                interval=interval,
                market=market,
                start=start,
                count=count,
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.debug(f"获取K线数据超时: symbol={symbol}, interval={interval}")
        return None
    except ValueError as e:
        logger.warning(f"不支持的周期: {interval}, 错误: {e}")
        return None
    except Exception as e:
        logger.warning(f"获取K线数据失败: symbol={symbol}, interval={interval}, 错误: {e}")
        return None
