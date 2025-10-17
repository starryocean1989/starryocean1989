# -*- coding: utf-8 -*-
"""
异步分时图解析器（当日）
"""
import struct
from collections import OrderedDict

from ...helper import get_price, get_security_coefficient
from ..async_base import AsyncBaseParser


class AsyncGetMinuteTimeData(AsyncBaseParser):
    """
    获取当日分时图数据命令（异步）
    """

    def __init__(self, reader, writer, lock=None):
        super().__init__(reader, writer, lock)
        self.coefficient = 0.01

    def setParams(self, market, code):
        """
        设置参数
        :param market: 市场 (0=深圳, 1=上海)
        :param code: 股票代码
        """
        if type(code) is str:
            code = code.encode("utf-8")

        pkg = bytearray.fromhex("0c 1b 08 00 01 01 0e 00 0e 00 1d 05")
        pkg.extend(struct.pack("<H6sI", market, code, 0))

        self.send_pkg = pkg
        self.coefficient = get_security_coefficient(market=market, code=code)

    def parseResponse(self, body_buf):
        """
        解析分时图响应

        :param body_buf: 响应体字节数据
        :return: 分时图数据列表（242个分钟点）
        """
        pos = 0

        (num,) = struct.unpack("<H", body_buf[:2])

        last_price = 0

        pos += 4
        prices = []

        for _ in range(num):
            price_raw, pos = get_price(body_buf, pos)
            reversed1, pos = get_price(body_buf, pos)

            vol, pos = get_price(body_buf, pos)
            last_price = float(last_price + price_raw)

            prices.append(OrderedDict([("price", last_price * self.coefficient), ("vol", vol)]))

        return prices

