# -*- coding: utf-8 -*-
"""
异步证券列表解析器
"""
import struct
from collections import OrderedDict

# 🚀 性能优化：导入安全的批量计算封装
from ...utils.helper import safe_batch_compute
from ..base import AsyncBaseParser


class AsyncGetSecurityList(AsyncBaseParser):
    """
    获取证券列表命令（异步）
    支持分页查询
    """

    def setParams(self, market, start):
        """
        设置参数
        :param market: 市场 (0=深圳, 1=上海)
        :param start: 开始位置
        """
        pkg = bytearray.fromhex("0c 01 18 64 01 01 06 00 06 00 50 04")
        pkg.extend(struct.pack("<HH", market, start))

        self.send_pkg = pkg

    def parseResponse(self, body_buf):
        """
        解析证券列表响应

        :param body_buf: 响应体字节数据
        :return: 证券列表数据
        """
        pos = 0
        # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
        (num,) = struct.unpack_from("<H", body_buf, pos)

        pos += 2

        # 🚀 性能优化：批量收集数据，然后批量处理成交量计算
        raw_data = []  # 存储原始数据
        pre_close_raws = []  # 存储成交量原始值

        # 第一遍：解析所有数据，收集成交量值
        # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
        for _ in range(num):
            (
                code,
                volunit,
                name_bytes,
                reversed_bytes1,
                decimal_point,
                pre_close_raw,
                reversed_bytes2,
            ) = struct.unpack_from("<6sH8s4sBI4s", body_buf, pos)

            code = code.decode("utf-8", errors="ignore")
            # 改进的字符解码逻辑，支持多种编码方式
            try:
                name = name_bytes.decode("gbk")
            except UnicodeDecodeError:
                try:
                    name = name_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    # 如果都失败，使用replace模式保留数据
                    name = name_bytes.decode("gbk", errors="replace")

            # 收集数据
            pre_close_raws.append(pre_close_raw)
            raw_data.append(
                {
                    "code": code,
                    "volunit": volunit,
                    "decimal_point": decimal_point,
                    "name": name,
                }
            )

            pos += 29

        # 🚀 性能优化：批量处理成交量（使用native_compute）
        if len(pre_close_raws) > 0:
            pre_closes = safe_batch_compute(pre_close_raws, "get_volume")
        else:
            pre_closes = []

        # 第二遍：构建结果，使用批量处理后的成交量值
        symbols = []
        for i, data in enumerate(raw_data):
            rows = OrderedDict(
                [
                    ("code", data["code"]),
                    ("volunit", data["volunit"]),
                    ("decimal_point", data["decimal_point"]),
                    ("name", data["name"]),
                    ("pre_close", pre_closes[i]),
                ]
            )

            symbols.append(rows)

        return symbols
