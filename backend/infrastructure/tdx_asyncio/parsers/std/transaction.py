# -*- coding: utf-8 -*-
"""
异步当日逐笔成交解析器
"""
import struct
from collections import OrderedDict

# 🚀 性能优化：导入安全批量计算封装
from ...utils.helper import get_price, get_time, safe_batch_compute
from ..base import AsyncBaseParser


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

        # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
        (num,) = struct.unpack_from("<H", body_buf, pos)

        pos += 2

        # 🚀 性能优化：批量收集数据，然后批量处理价格计算
        raw_data = []  # 存储原始数据
        price_raws = []  # 存储价格差值

        # 第一遍：解析所有数据
        for _ in range(num):
            hour, minute, pos = get_time(body_buf, pos)
            price_raw, pos = get_price(body_buf, pos)

            vol, pos = get_price(body_buf, pos)
            num_val, pos = get_price(body_buf, pos)

            buy_or_sell, pos = get_price(body_buf, pos)
            _, pos = get_price(body_buf, pos)

            # 收集数据
            price_raws.append(price_raw)
            raw_data.append(
                {
                    "hour": hour,
                    "minute": minute,
                    "vol": vol,
                    "num": num_val,
                    "buy_or_sell": buy_or_sell,
                }
            )

        # 🚀 性能优化：计算累积价格（顺序依赖，在Python中计算）
        last_price = 0
        cumulative_prices = []
        for price_raw in price_raws:
            last_price = last_price + price_raw
            cumulative_prices.append(last_price)

        # 🚀 性能优化：批量除以100（使用native_compute）
        if len(cumulative_prices) > 0:
            prices = safe_batch_compute(cumulative_prices, "divide")
        else:
            prices = []

        # 第二遍：构建结果
        ticks = []
        for i, data in enumerate(raw_data):
            tick = OrderedDict(
                [
                    ("time", "%02d:%02d" % (data["hour"], data["minute"])),
                    ("price", prices[i]),
                    ("vol", data["vol"]),
                    ("num", data["num"]),
                    ("buyorsell", data["buy_or_sell"]),  # noqa
                ]
            )

            ticks.append(tick)

        return ticks
