# -*- coding: utf-8 -*-
"""
异步除权除息解析器
"""
import struct
from collections import OrderedDict

# 🚀 性能优化：导入native_compute用于批量成交量计算
from backend.infrastructure.native.native_compute import batch_compute

from ...utils.helper import get_datetime
from ..base import AsyncBaseParser

XDXR_CATEGORY_MAPPING = {
    1: "除权除息",
    2: "送配股上市",
    3: "非流通股上市",
    4: "未知股本变动",
    5: "股本变化",
    6: "增发新股",
    7: "股份回购",
    8: "增发新股上市",
    9: "转配股上市",
    10: "可转债上市",
    11: "扩缩股",
    12: "非流通股缩股",
    13: "送认购权证",
    14: "送认沽权证",
}


class AsyncGetXdXrInfo(AsyncBaseParser):
    """
    获取除权除息信息命令（异步）
    """

    def setParams(self, market, code):
        """
        设置参数
        :param market: 市场 (0=深圳, 1=上海)
        :param code: 股票代码
        """
        if type(code) is str:
            code = code.encode("utf-8")

        pkg = bytearray.fromhex("0c 1f 18 76 00 01 0b 00 0b 00 0f 00 01 00")
        pkg.extend(struct.pack("<B6s", market, code))

        self.send_pkg = pkg

    def parseResponse(self, body_buf):
        """
        解析除权除息响应

        :param body_buf: 响应体字节数据
        :return: 除权除息数据列表
        """
        pos = 0

        if len(body_buf) < 11:
            return []

        pos += 9  # skip 9
        # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
        (num,) = struct.unpack_from("<H", body_buf, pos)

        pos += 2

        # 🚀 性能优化：批量收集数据，然后批量处理成交量计算
        raw_data = []  # 存储原始数据
        volume_raws = []  # 存储成交量原始值
        volume_mapping = []  # 记录每个记录的成交量索引映射 [(record_idx, field_name, volume_idx), ...]

        for _ in range(num):
            pos += 7
            pos += 1

            year, month, day, hour, minute, pos = get_datetime(9, body_buf, pos)
            # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
            (category,) = struct.unpack_from("<B", body_buf, pos)
            pos += 1

            suogu = None
            panqianliutong, panhouliutong, qianzongguben, houzongguben = None, None, None, None
            songzhuangu, fenhong, peigu, peigujia = None, None, None, None
            fenshu, xingquanjia = None, None

            if category == 1:
                # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
                fenhong, peigujia, songzhuangu, peigu = struct.unpack_from("<ffff", body_buf, pos)
            elif category in [11, 12]:
                # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
                _, _, suogu, _ = struct.unpack_from("<IIfI", body_buf, pos)
            elif category in [13, 14]:
                # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
                xingquanjia, _, fenshu, _ = struct.unpack_from("<fIfI", body_buf, pos)
            else:
                # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
                panqianliutong_raw, qianzongguben_raw, panhouliutong_raw, houzongguben_raw = (
                    struct.unpack_from("<IIII", body_buf, pos)
                )
                # 收集成交量原始值（跳过0值，0值直接返回0）
                record_idx = len(raw_data)
                if panqianliutong_raw != 0:
                    volume_raws.append(panqianliutong_raw)
                    volume_mapping.append((record_idx, "panqianliutong", len(volume_raws) - 1))
                else:
                    volume_mapping.append((record_idx, "panqianliutong", -1))

                if panhouliutong_raw != 0:
                    volume_raws.append(panhouliutong_raw)
                    volume_mapping.append((record_idx, "panhouliutong", len(volume_raws) - 1))
                else:
                    volume_mapping.append((record_idx, "panhouliutong", -1))

                if qianzongguben_raw != 0:
                    volume_raws.append(qianzongguben_raw)
                    volume_mapping.append((record_idx, "qianzongguben", len(volume_raws) - 1))
                else:
                    volume_mapping.append((record_idx, "qianzongguben", -1))

                if houzongguben_raw != 0:
                    volume_raws.append(houzongguben_raw)
                    volume_mapping.append((record_idx, "houzongguben", len(volume_raws) - 1))
                else:
                    volume_mapping.append((record_idx, "houzongguben", -1))

            pos += 16

            # 保存原始数据
            raw_data.append(
                {
                    "year": year,
                    "month": month,
                    "day": day,
                    "category": category,
                    "fenhong": fenhong,
                    "peigujia": peigujia,
                    "songzhuangu": songzhuangu,
                    "peigu": peigu,
                    "suogu": suogu,
                    "fenshu": fenshu,
                    "xingquanjia": xingquanjia,
                }
            )

        # 🚀 性能优化：批量处理成交量（使用native_compute）
        if len(volume_raws) > 0:
            volumes = batch_compute(volume_raws, "get_volume")  # type: ignore[call-arg]
        else:
            volumes = []

        # 第二遍：构建结果，使用批量处理后的成交量值
        rows = []
        for i, data in enumerate(raw_data):
            # 从volume_mapping中获取对应的成交量值
            panqianliutong = None
            panhouliutong = None
            qianzongguben = None
            houzongguben = None

            for record_idx, field_name, vol_idx in volume_mapping:
                if record_idx == i:
                    if vol_idx == -1:
                        vol_value = 0
                    else:
                        vol_value = volumes[vol_idx]

                    if field_name == "panqianliutong":
                        panqianliutong = vol_value
                    elif field_name == "panhouliutong":
                        panhouliutong = vol_value
                    elif field_name == "qianzongguben":
                        qianzongguben = vol_value
                    elif field_name == "houzongguben":
                        houzongguben = vol_value

            row = OrderedDict(
                [
                    ("year", data["year"]),
                    ("month", data["month"]),
                    ("day", data["day"]),
                    ("category", data["category"]),
                    ("name", self.get_category_name(data["category"])),
                    ("fenhong", data["fenhong"]),
                    ("peigujia", data["peigujia"]),
                    ("songzhuangu", data["songzhuangu"]),
                    ("peigu", data["peigu"]),
                    ("suogu", data["suogu"]),
                    ("panqianliutong", panqianliutong),
                    ("panhouliutong", panhouliutong),
                    ("qianzongguben", qianzongguben),
                    ("houzongguben", houzongguben),
                    ("fenshu", data["fenshu"]),
                    ("xingquanjia", data["xingquanjia"]),
                ]
            )
            rows.append(row)

        return rows

    @staticmethod
    def get_category_name(category_id):
        """
        获取分类名称
        如果配置内没有，则返回 category_id
        :param category_id: 分类ID
        :return: 分类名称
        """
        return XDXR_CATEGORY_MAPPING.get(category_id, str(category_id))
