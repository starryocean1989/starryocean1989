# -*- coding: utf-8 -*-
"""
异步K线数据解析器（核心）
"""
import struct
from collections import OrderedDict

# 🚀 性能优化：导入安全的批量计算封装
from ...utils.helper import get_datetime, get_price, safe_batch_compute
from ..base import AsyncBaseParser


class AsyncGetSecurityBarsCmd(AsyncBaseParser):
    """
    获取K线数据命令（异步）
    """

    def setParams(self, category, market, code, start, count):
        """
        设置参数

        :param category: K线类型 (0=5分钟, 4=日K线, 8=1分钟)
        :param market: 市场 (0=深圳, 1=上海)
        :param code: 股票代码
        :param start: 起始位置
        :param count: 数量
        """
        if type(code) is str:
            code = code.encode("utf-8")

        self.category = category

        values = (
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

        self.send_pkg = struct.pack("<HIHHHH6sHHHHIIH", *values)

    def parseResponse(self, body_buf):
        """
        解析K线数据响应

        :param body_buf: 响应体字节数据
        :return: K线数据列表
        """
        pos = 0

        # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
        (ret_count,) = struct.unpack_from("<H", body_buf, pos)
        pos += 2

        klines = []

        pre_diff_base = 0

        # 🚀 性能优化：批量收集需要除以1000的价格值，然后批量处理
        # 收集所有需要除以1000的原始价格值（整数形式）
        prices_to_divide = []  # 存储 (base_p + diff) 的原始值
        # 🚀 性能优化：批量收集成交量原始值，然后批量处理
        volumes_raw = []  # 存储成交量原始值（按顺序：vol, db_vol）

        # 第一遍：解析所有数据，收集价格值和成交量值
        raw_data = []
        for _ in range(ret_count):
            year, month, day, hour, minute, pos = get_datetime(self.category, body_buf, pos)

            price_open_diff, pos = get_price(body_buf, pos)
            price_close_diff, pos = get_price(body_buf, pos)

            price_high_diff, pos = get_price(body_buf, pos)
            price_low_diff, pos = get_price(body_buf, pos)

            # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
            (vol_raw,) = struct.unpack_from("<I", body_buf, pos)
            volumes_raw.append(vol_raw)  # 收集vol_raw

            pos += 4

            # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
            (db_vol_raw,) = struct.unpack_from("<I", body_buf, pos)
            volumes_raw.append(db_vol_raw)  # 收集db_vol_raw

            pos += 4

            # 计算价格（先不除以1000，收集原始值）
            open_base = price_open_diff + pre_diff_base
            price_open_diff = open_base
            close_base = price_open_diff + price_close_diff
            high_base = price_open_diff + price_high_diff
            low_base = price_open_diff + price_low_diff

            pre_diff_base = price_open_diff + price_close_diff

            # 收集需要除以1000的价格值（按顺序：open, close, high, low）
            prices_to_divide.extend([open_base, close_base, high_base, low_base])

            # 保存原始数据（先不计算成交量）
            raw_data.append(
                {
                    "year": year,
                    "month": month,
                    "day": day,
                    "hour": hour,
                    "minute": minute,
                }
            )

        # 🚀 性能优化：批量除以1000（使用native_compute）
        if len(prices_to_divide) > 0:
            prices_divided = safe_batch_compute(prices_to_divide, "divide_by_1000")
        else:
            prices_divided = []

        # 🚀 性能优化：批量处理成交量（使用native_compute）
        if len(volumes_raw) > 0:
            volumes = safe_batch_compute(volumes_raw, "get_volume")
        else:
            volumes = []

        # 第二遍：构建结果，使用批量处理后的价格值和成交量值
        price_idx = 0
        vol_idx = 0
        for data in raw_data:
            # 从批量处理结果中获取价格（每个记录4个价格：open, close, high, low）
            open_ = prices_divided[price_idx]
            close = prices_divided[price_idx + 1]
            high = prices_divided[price_idx + 2]
            low = prices_divided[price_idx + 3]
            price_idx += 4

            # 从批量处理结果中获取成交量（每个记录2个成交量：vol, db_vol）
            vol = volumes[vol_idx]
            db_vol = volumes[vol_idx + 1]
            vol_idx += 2

            # 🚀 性能优化：批量格式化日期时间字符串（使用f-string，比%格式化更快）
            datetime_str = f"{data['year']}-{data['month']:02d}-{data['day']:02d} {data['hour']:02d}:{data['minute']:02d}"

            kline = OrderedDict(
                [
                    ("open", open_),
                    ("close", close),
                    ("high", high),
                    ("low", low),
                    ("vol", vol),
                    ("amount", db_vol),
                    ("year", data["year"]),
                    ("month", data["month"]),
                    ("day", data["day"]),
                    ("hour", data["hour"]),
                    ("minute", data["minute"]),
                    ("datetime", datetime_str),
                ]
            )

            klines.append(kline)

        return klines
