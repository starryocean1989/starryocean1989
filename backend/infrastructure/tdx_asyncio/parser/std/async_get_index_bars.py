# -*- coding: utf-8 -*-
"""
异步指数K线解析器
"""
import struct
from collections import OrderedDict

from ...helper import get_datetime, get_price, get_volume
from ..async_base import AsyncBaseParser


class AsyncGetIndexBarsCmd(AsyncBaseParser):
    """
    获取指数K线数据命令（异步）
    """

    def setParams(self, category, market, code, start, count):
        """
        设置参数

        :param category: K线类型 (0=5分钟, 4=日K线, 8=1分钟)
        :param market: 市场 (0=深圳, 1=上海)
        :param code: 指数代码
        :param start: 起始位置
        :param count: 数量
        """
        if type(code) is str:
            code = code.encode("utf-8")

        self.category = category

        val = (
            0x10C,
            0x01016408,
            0x1C,
            0x1C,
            0x052D,
            market,
            code,
            category,
            1,
            start,
            count,
            0,
            0,
            0,
        )
        pkg = struct.pack("<HIHHHH6sHHHHIIH", *val)

        self.send_pkg = pkg

    def parseResponse(self, body_buf):
        """
        解析指数K线响应

        :param body_buf: 响应体字节数据
        :return: 指数K线数据列表
        """
        (ret_count,) = struct.unpack("<H", body_buf[0:2])

        pos = 2

        klines = []
        pre_diff_base = 0

        for _ in range(ret_count):
            year, month, day, hour, minute, pos = get_datetime(self.category, body_buf, pos)

            price_open_diff, pos = get_price(body_buf, pos)
            price_close_diff, pos = get_price(body_buf, pos)

            price_high_diff, pos = get_price(body_buf, pos)
            price_low_diff, pos = get_price(body_buf, pos)

            (vol_raw,) = struct.unpack("<I", body_buf[pos : pos + 4])
            vol = get_volume(vol_raw)

            pos += 4

            (db_vol_raw,) = struct.unpack("<I", body_buf[pos : pos + 4])
            db_vol = get_volume(db_vol_raw)

            pos += 4

            (up_count, down_count) = struct.unpack("<HH", body_buf[pos : pos + 4])

            pos += 4

            open_ = self._cal_price1000(price_open_diff, pre_diff_base)
            price_open_diff = price_open_diff + pre_diff_base

            close = self._cal_price1000(price_open_diff, price_close_diff)
            high = self._cal_price1000(price_open_diff, price_high_diff)
            low = self._cal_price1000(price_open_diff, price_low_diff)

            pre_diff_base = price_open_diff + price_close_diff

            kline = OrderedDict(
                [
                    ("open", open_),
                    ("close", close),
                    ("high", high),
                    ("low", low),
                    ("vol", vol),
                    ("amount", db_vol),
                    ("year", year),
                    ("month", month),
                    ("day", day),
                    ("hour", hour),
                    ("minute", minute),
                    ("datetime", f"{year:d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"),
                    ("up_count", up_count),
                    ("down_count", down_count),
                ]
            )

            klines.append(kline)

        return klines

