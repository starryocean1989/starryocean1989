# -*- coding: utf-8 -*-
"""
异步历史逐笔成交解析器
"""
import struct
from collections import OrderedDict

# 🚀 性能优化：导入native_compute用于批量价格计算
from backend.infrastructure.native.native_compute import batch_compute

from ...utils.helper import get_price, get_time
from ...utils.logger import logger
from ..base import AsyncBaseParser


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
        # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
        (num,) = struct.unpack_from("<H", body_buf, pos)
        logger.debug(f"num => {num}")

        pos += 2

        # skip 4 bytes
        pos += 4

        # 🚀 性能优化：批量收集数据，然后批量处理价格计算
        raw_data = []  # 存储原始数据
        price_raws = []  # 存储价格差值

        # 第一遍：解析所有数据
        for _ in range(num):
            hour, minute, pos = get_time(body_buf, pos)  # noqa

            price_raw, pos = get_price(body_buf, pos)
            vol, pos = get_price(body_buf, pos)

            buy_or_sell, pos = get_price(body_buf, pos)
            _, pos = get_price(body_buf, pos)

            # 收集数据
            price_raws.append(price_raw)
            raw_data.append(
                {
                    "hour": hour,
                    "minute": minute,
                    "vol": vol,
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
            prices = batch_compute(cumulative_prices, "divide")  # type: ignore
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
                    ("buyorsell", data["buy_or_sell"]),
                ]
            )

            logger.debug(f"tick => {tick}")
            ticks.append(tick)

        return ticks
