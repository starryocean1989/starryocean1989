# -*- coding: utf-8 -*-
"""
异步实时行情解析器
"""
import struct
from collections import OrderedDict

# 🚀 性能优化：导入批量get_price与安全批量计算封装
from ...utils.helper import (
    get_price,
    batch_get_price,
    get_security_coefficient,
    get_volume,
    safe_batch_compute,
)
from ..base import AsyncBaseParser


class AsyncGetSecurityQuotesCmd(AsyncBaseParser):
    """
    获取实时行情命令（异步）
    支持批量查询多只股票
    """

    def setParams(self, all_stock):
        """
        设置参数
        :param all_stock: 一个包含 (market, code) 元组的列表， 如 [ (0, '000001'), (1, '600001') ]
        :return:
        """
        stock_len = len(all_stock)

        if stock_len <= 0:
            return False

        pkgdatalen = stock_len * 7 + 12

        val = (0x10C, 0x02006320, pkgdatalen, pkgdatalen, 0x5053E, 0, 0, stock_len)
        pkg = bytearray(struct.pack("<HIHHIIHH", *val))

        for stock in all_stock:
            market, code = stock

            if type(code) is str:
                code = code.encode("utf-8")

            one_stock_pkg = struct.pack("<B6s", market, code)
            pkg.extend(one_stock_pkg)

        self.send_pkg = pkg

    def parseResponse(self, body_buf):
        """
        解析实时行情响应

        :param body_buf: 响应体字节数据
        :return: 实时行情数据列表
        """
        pos = 0
        pos += 2  # skip b1 cb

        # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
        (num_stock,) = struct.unpack_from("<H", body_buf, pos)

        pos += 2
        stocks = []

        # 🚀 性能优化：批量收集价格数据，然后批量计算
        raw_stock_data = []  # 存储每只股票的原始数据

        for _ in range(num_stock):
            # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
            market, code, active1 = struct.unpack_from("<B6sH", body_buf, pos)
            pos += 9

            # 🚀 性能优化：批量解析前8个get_price调用
            price_values, pos = batch_get_price(body_buf, pos, 8)
            price = price_values[0]
            last_close_diff = price_values[1]
            open_diff = price_values[2]
            high_diff = price_values[3]
            low_diff = price_values[4]
            reversed_bytes0 = price_values[5]
            reversed_bytes1 = price_values[6]
            vol = price_values[7]

            # 单独解析cur_vol（因为后面有amount_raw）
            cur_vol, pos = get_price(body_buf, pos)

            # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
            (amount_raw,) = struct.unpack_from("<I", body_buf, pos)
            amount = get_volume(amount_raw)
            pos += 4

            # 🚀 性能优化：批量解析接下来的16个get_price调用（五档买卖盘）
            price_values2, pos = batch_get_price(body_buf, pos, 16)
            s_vol = price_values2[0]
            b_vol = price_values2[1]
            reversed_bytes2 = price_values2[2]
            reversed_bytes3 = price_values2[3]
            bid1 = price_values2[4]
            ask1 = price_values2[5]
            bid_vol1 = price_values2[6]
            ask_vol1 = price_values2[7]
            bid2 = price_values2[8]
            ask2 = price_values2[9]
            bid_vol2 = price_values2[10]
            ask_vol2 = price_values2[11]
            bid3 = price_values2[12]
            ask3 = price_values2[13]
            bid_vol3 = price_values2[14]
            ask_vol3 = price_values2[15]

            # 🚀 性能优化：批量解析接下来的4个get_price调用（bid4/ask4/bid5/ask5）
            price_values3, pos = batch_get_price(body_buf, pos, 4)
            bid4 = price_values3[0]
            ask4 = price_values3[1]
            bid_vol4 = price_values3[2]
            ask_vol4 = price_values3[3]

            # 单独解析bid5/ask5/bid_vol5/ask_vol5（因为后面有reversed_bytes4）
            bid5, pos = get_price(body_buf, pos)
            ask5, pos = get_price(body_buf, pos)
            bid_vol5, pos = get_price(body_buf, pos)
            ask_vol5, pos = get_price(body_buf, pos)

            # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
            (reversed_bytes4,) = struct.unpack_from("<H", body_buf, pos)
            pos += 2

            # 🚀 性能优化：批量解析最后4个get_price调用
            price_values4, pos = batch_get_price(body_buf, pos, 4)
            reversed_bytes5 = price_values4[0]
            reversed_bytes6 = price_values4[1]
            reversed_bytes7 = price_values4[2]
            reversed_bytes8 = price_values4[3]

            # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
            reversed_bytes9, active2 = struct.unpack_from("<hH", body_buf, pos)
            pos += 4

            code = code.decode("utf-8")
            coefficient = get_security_coefficient(market, code)

            # 收集原始数据，用于后续批量价格计算
            raw_stock_data.append(
                {
                    "market": market,
                    "code": code,
                    "active1": active1,
                    "base_price": price,
                    "price_diffs": [
                        0,
                        last_close_diff,
                        open_diff,
                        high_diff,
                        low_diff,
                        bid1,
                        ask1,
                        bid2,
                        ask2,
                        bid3,
                        ask3,
                        bid4,
                        ask4,
                        bid5,
                        ask5,
                    ],
                    "coefficient": coefficient,
                    "reversed_bytes0": reversed_bytes0,
                    "reversed_bytes1": reversed_bytes1,
                    "vol": vol,
                    "cur_vol": cur_vol,
                    "amount": amount,
                    "s_vol": s_vol,
                    "b_vol": b_vol,
                    "reversed_bytes2": reversed_bytes2,
                    "reversed_bytes3": reversed_bytes3,
                    "bid_vol1": bid_vol1,
                    "ask_vol1": ask_vol1,
                    "bid_vol2": bid_vol2,
                    "ask_vol2": ask_vol2,
                    "bid_vol3": bid_vol3,
                    "ask_vol3": ask_vol3,
                    "bid_vol4": bid_vol4,
                    "ask_vol4": ask_vol4,
                    "bid_vol5": bid_vol5,
                    "ask_vol5": ask_vol5,
                    "reversed_bytes4": reversed_bytes4,
                    "reversed_bytes5": reversed_bytes5,
                    "reversed_bytes6": reversed_bytes6,
                    "reversed_bytes7": reversed_bytes7,
                    "reversed_bytes8": reversed_bytes8,
                    "reversed_bytes9": reversed_bytes9,
                    "active2": active2,
                }
            )

        # 🚀 性能优化：批量计算所有价格
        # 收集所有需要计算的价格数据
        all_price_calculations = []
        for stock_data in raw_stock_data:
            base_price = stock_data["base_price"]
            coefficient = stock_data["coefficient"]
            for diff in stock_data["price_diffs"]:
                all_price_calculations.append((base_price, diff, coefficient))

        # 批量计算所有价格
        calculated_prices = self._batch_calculate_prices(all_price_calculations)

        # 将计算结果分配给每只股票
        price_idx = 0
        for stock_data in raw_stock_data:
            price_count = len(stock_data["price_diffs"])
            stock_data["calculated_prices"] = calculated_prices[price_idx : price_idx + price_count]
            price_idx += price_count

        # 构建最终的股票数据
        for stock_data in raw_stock_data:
            # 使用批量计算的价格
            prices = stock_data["calculated_prices"]
            (
                price,
                last_close,
                open_p,
                high,
                low,
                bid1,
                ask1,
                bid2,
                ask2,
                bid3,
                ask3,
                bid4,
                ask4,
                bid5,
                ask5,
            ) = prices

            one_stock = OrderedDict(
                [
                    ("market", stock_data["market"]),
                    ("code", stock_data["code"]),
                    ("active1", stock_data["active1"]),
                    ("price", price),
                    ("last_close", last_close),
                    ("open", open_p),
                    ("high", high),
                    ("low", low),
                    ("servertime", self._format_time("%s" % stock_data["reversed_bytes0"])),
                    ("reversed_bytes0", stock_data["reversed_bytes0"]),
                    ("reversed_bytes1", stock_data["reversed_bytes1"]),
                    ("vol", stock_data["vol"]),
                    ("cur_vol", stock_data["cur_vol"]),
                    ("amount", stock_data["amount"]),
                    ("s_vol", stock_data["s_vol"]),
                    ("b_vol", stock_data["b_vol"]),
                    ("reversed_bytes2", stock_data["reversed_bytes2"]),
                    ("reversed_bytes3", stock_data["reversed_bytes3"]),
                    ("bid1", bid1),
                    ("ask1", ask1),
                    ("bid_vol1", stock_data["bid_vol1"]),
                    ("ask_vol1", stock_data["ask_vol1"]),
                    ("bid2", bid2),
                    ("ask2", ask2),
                    ("bid_vol2", stock_data["bid_vol2"]),
                    ("ask_vol2", stock_data["ask_vol2"]),
                    ("bid3", bid3),
                    ("ask3", ask3),
                    ("bid_vol3", stock_data["bid_vol3"]),
                    ("ask_vol3", stock_data["ask_vol3"]),
                    ("bid4", bid4),
                    ("ask4", ask4),
                    ("bid_vol4", stock_data["bid_vol4"]),
                    ("ask_vol4", stock_data["ask_vol4"]),
                    ("bid5", bid5),
                    ("ask5", ask5),
                    ("bid_vol5", stock_data["bid_vol5"]),
                    ("ask_vol5", stock_data["ask_vol5"]),
                    ("reversed_bytes4", stock_data["reversed_bytes4"]),
                    ("reversed_bytes5", stock_data["reversed_bytes5"]),
                    ("reversed_bytes6", stock_data["reversed_bytes6"]),
                    ("reversed_bytes7", stock_data["reversed_bytes7"]),
                    ("reversed_bytes8", stock_data["reversed_bytes8"]),
                    ("reversed_bytes9", stock_data["reversed_bytes9"] / 100.0),  # 涨速
                    ("active2", stock_data["active2"]),
                ]
            )

            stocks.append(one_stock)

        return stocks

    @staticmethod
    def _batch_calculate_prices(price_calculations):
        """
        批量计算价格（使用native_compute优化）

        :param price_calculations: [(base_price, diff, coefficient), ...]
        :return: 计算后的价格列表
        """
        if not price_calculations:
            return []

        # 批量计算价格：float(base_price + diff) * coefficient
        base_prices = [calc[0] for calc in price_calculations]
        diffs = [calc[1] for calc in price_calculations]
        coefficients = [calc[2] for calc in price_calculations]

        # 先批量计算 base_price + diff
        sums = safe_batch_compute(base_prices, "add", diffs)

        # 再批量计算 sums * coefficient
        results = safe_batch_compute(sums, "multiply", coefficients)

        return results

    @staticmethod
    def _format_time(time_stamp):
        """
        格式化时间戳
        :param time_stamp: 时间戳字符串
        :return:
        """
        if not int(time_stamp):
            return time_stamp

        time = time_stamp[:8][:-6] + ":"

        if int(time_stamp[-6:-4]) < 60:
            time += "%s:" % time_stamp[-6:-4]
            time += "%06.3f" % (int(time_stamp[-4:]) * 60 / 10000.0)
        else:
            time += "%02d:" % (int(time_stamp[-6:]) * 60 / 1000000)
            time += "%06.3f" % ((int(time_stamp[-6:]) * 60 % 1000000) * 60 / 1000000.0)

        return time
