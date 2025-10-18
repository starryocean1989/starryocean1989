# -*- coding: utf-8 -*-
"""
异步证券列表解析器
"""
import struct
from collections import OrderedDict

from ...helper import get_volume
from ..async_base import AsyncBaseParser


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
        (num,) = struct.unpack("<H", body_buf[:2])

        pos += 2
        symbols = []

        for _ in range(num):
            one_bytes = body_buf[pos : pos + 29]

            (
                code,
                volunit,
                name_bytes,
                reversed_bytes1,
                decimal_point,
                pre_close_raw,
                reversed_bytes2,
            ) = struct.unpack("<6sH8s4sBI4s", one_bytes)

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

            pre_close = get_volume(pre_close_raw)
            pos += 29

            rows = OrderedDict(
                [
                    ("code", code),
                    ("volunit", volunit),
                    ("decimal_point", decimal_point),
                    ("name", name),
                    ("pre_close", pre_close),
                ]
            )

            symbols.append(rows)

        return symbols
