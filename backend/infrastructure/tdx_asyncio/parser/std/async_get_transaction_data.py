# -*- coding: utf-8 -*-
"""
异步当日逐笔成交解析器
"""
import struct
from collections import OrderedDict

from ...helper import get_price, get_time
from ..async_base import AsyncBaseParser


class AsyncGetTransactionData(AsyncBaseParser):
    """
    获取当日逐笔成交数据命令（异步）
    """

    def setParams(self, market, code, start, count):
        """
        设置请求参数
        :param market: 市场 (0=深圳, 1=上海)
        :param code: 股票代码
        :param start: 起始位置
        :param count: 数量（最大2000）
        """
        if type(code) is str:
            code = code.encode("utf-8")

        pkg = bytearray.fromhex("0c 17 08 01 01 01 0e 00 0e 00 c5 0f")
        pkg.extend(struct.pack("<H6sHH", market, code, start, count))

        self.send_pkg = pkg

    def parseResponse(self, body_buf):
        """
        解析返回结果
        :param body_buf: 响应体字节数据
        :return: 逐笔成交数据列表
        """
        pos = 0

        (num,) = struct.unpack("<H", body_buf[:2])

        pos += 2

        ticks = []
        last_price = 0

        for _ in range(num):
            hour, minute, pos = get_time(body_buf, pos)
            price_raw, pos = get_price(body_buf, pos)

            vol, pos = get_price(body_buf, pos)
            num, pos = get_price(body_buf, pos)

            buy_or_sell, pos = get_price(body_buf, pos)
            _, pos = get_price(body_buf, pos)

            last_price = last_price + price_raw

            tick = OrderedDict(
                [
                    ("time", "%02d:%02d" % (hour, minute)),
                    ("price", float(last_price) / 100),
                    ("vol", vol),
                    ("num", num),
                    ("buyorsell", buy_or_sell),  # noqa
                ]
            )

            ticks.append(tick)

        return ticks

