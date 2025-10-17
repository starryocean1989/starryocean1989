# -*- coding: utf-8 -*-
"""
异步历史分时图解析器
"""
import struct
from collections import OrderedDict

from ...helper import get_price, get_security_coefficient
from ..async_base import AsyncBaseParser


class AsyncGetHistoryMinuteTimeData(AsyncBaseParser):
    """
    获取历史分时图数据命令（异步）
    """

    def __init__(self, reader, writer, lock=None):
        super().__init__(reader, writer, lock)
        self.coefficient = 0.001

    def setParams(self, market, code, date):
        """
        设置参数
        :param market: 市场 (0=深圳, 1=上海)
        :param code: 股票代码
        :param date: 日期，格式20161201的整型
        """
        self.coefficient = get_security_coefficient(market=market, code=code)

        if (type(date) is str) or (type(date) is bytes):
            date = int(date)

        if type(code) is str:
            code = code.encode("utf-8")

        pkg = bytearray.fromhex("0c 01 30 00 01 01 0d 00 0d 00 b4 0f")
        pkg.extend(struct.pack("<IB6s", date, market, code))

        self.send_pkg = pkg

    def parseResponse(self, body_buf):
        """
        解析历史分时图响应

        :param body_buf: 响应体字节数据
        :return: 分时图数据列表（242个分钟点）
        """
        pos = 0

        (num,) = struct.unpack("<H", body_buf[:2])
        last_price = 0

        # 跳过了4个字节，实在不知道是什么意思
        pos += 6
        prices = []

        for _ in range(num):
            price_raw, pos = get_price(body_buf, pos)
            reversed1, pos = get_price(body_buf, pos)

            vol, pos = get_price(body_buf, pos)
            last_price = last_price + price_raw

            price = OrderedDict([("price", float(last_price) * self.coefficient), ("vol", vol)])
            prices.append(price)

        return prices

