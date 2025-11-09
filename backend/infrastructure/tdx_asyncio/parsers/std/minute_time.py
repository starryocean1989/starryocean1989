# -*- coding: utf-8 -*-
"""
异步分时图解析器（当日）
"""
import struct
from collections import OrderedDict

# 🚀 性能优化：使用安全批量计算与转换封装
from ...utils.helper import get_price, get_security_coefficient, safe_batch_compute, safe_batch_convert
from ..base import AsyncBaseParser


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

        # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
        (num,) = struct.unpack_from("<H", body_buf, pos)

        pos += 4

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
        cumulative_prices_int = []  # 先存储整数，然后批量转换为浮点数
        for price_raw in price_raws:
            last_price = last_price + price_raw
            cumulative_prices_int.append(last_price)

        # 🚀 性能优化：批量转换为浮点数（使用native_conversion）
        if len(cumulative_prices_int) > 0:
            cumulative_prices = safe_batch_convert(cumulative_prices_int, float)
        else:
            cumulative_prices = []

        # 🚀 性能优化：批量乘以系数（使用native_compute）
        if len(cumulative_prices) > 0:
            coefficients = [self.coefficient] * len(cumulative_prices)
            final_prices = safe_batch_compute(cumulative_prices, "multiply", coefficients)
        else:
            final_prices = []

        # 第二遍：构建结果
        prices = []
        for i, data in enumerate(raw_data):
            prices.append(OrderedDict([("price", final_prices[i]), ("vol", data["vol"])]))

        return prices
