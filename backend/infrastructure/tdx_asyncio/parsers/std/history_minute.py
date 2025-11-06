# -*- coding: utf-8 -*-
"""
异步历史分时图解析器
"""
import struct
from collections import OrderedDict

# 🚀 性能优化：导入native_compute用于批量价格计算
from backend.infrastructure.native.native_compute import batch_compute

from ...utils.helper import get_price, get_security_coefficient
from ..base import AsyncBaseParser


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

        # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
        (num,) = struct.unpack_from("<H", body_buf, pos)

        # 跳过了4个字节，实在不知道是什么意思
        pos += 6

        # 🚀 性能优化：批量收集数据，然后批量处理价格计算
        raw_data = []  # 存储原始数据
        price_raws = []  # 存储价格差值

        # 第一遍：解析所有数据
        for _ in range(num):
            price_raw, pos = get_price(body_buf, pos)
            reversed1, pos = get_price(body_buf, pos)

            vol, pos = get_price(body_buf, pos)

            # 收集数据
            price_raws.append(price_raw)
            raw_data.append({"vol": vol})

        # 🚀 性能优化：计算累积价格（顺序依赖，在Python中计算）
        last_price = 0
        cumulative_prices = []
        for price_raw in price_raws:
            last_price = last_price + price_raw
            cumulative_prices.append(float(last_price))

        # 🚀 性能优化：批量乘以系数（使用native_compute）
        if len(cumulative_prices) > 0:
            coefficients = [self.coefficient] * len(cumulative_prices)
            final_prices = batch_compute(cumulative_prices, "multiply", coefficients)
        else:
            final_prices = []

        # 第二遍：构建结果
        prices = []
        for i, data in enumerate(raw_data):
            prices.append(OrderedDict([("price", final_prices[i]), ("vol", data["vol"])]))

        return prices
