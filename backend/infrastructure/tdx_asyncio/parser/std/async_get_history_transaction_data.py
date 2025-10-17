# -*- coding: utf-8 -*-
"""
异步历史逐笔成交解析器
"""
import struct
from collections import OrderedDict

from ...helper import get_price, get_time
from ...logger import logger
from ..async_base import AsyncBaseParser


class AsyncGetHistoryTransactionData(AsyncBaseParser):
    """
    获取历史逐笔成交数据命令（异步）
    """

    def setParams(self, market, code, start, count, date):
        """
        设置请求参数
        :param market: 市场 (0=深圳, 1=上海)
        :param code: 股票代码
        :param start: 起始位置
        :param count: 数量（最大2000）
        :param date: 日期，格式20161201的整型
        """
        if type(code) is str:
            code = code.encode("utf-8")

        if type(date) is (type(date) is str) or (type(date) is bytes):
            date = int(date)

        pkg = bytearray.fromhex("0c 01 30 01 00 01 12 00 12 00 b5 0f")
        pkg.extend(struct.pack("<IH6sHH", date, market, code, start, count))

        self.send_pkg = pkg

    def parseResponse(self, body_buf):
        """
        解析返回结果
        :param body_buf: 响应体字节数据
        :return: 历史逐笔成交数据列表
        """
        pos = 0
        (num,) = struct.unpack("<H", body_buf[:2])
        logger.debug(f'num => {num}')

        pos += 2
        ticks = []

        # skip 4 bytes
        pos += 4
        last_price = 0

        for _ in range(num):
            hour, minute, pos = get_time(body_buf, pos)  # noqa

            price_raw, pos = get_price(body_buf, pos)
            vol, pos = get_price(body_buf, pos)

            buy_or_sell, pos = get_price(body_buf, pos)
            _, pos = get_price(body_buf, pos)

            last_price = last_price + price_raw

            tick = OrderedDict(
                [
                    ("time", "%02d:%02d" % (hour, minute)),
                    ("price", float(last_price) / 100),
                    ("vol", vol),
                    ("buyorsell", buy_or_sell),
                ]
            )

            logger.debug(f'tick => {tick}')
            ticks.append(tick)

        return ticks

