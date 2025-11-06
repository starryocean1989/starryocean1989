# -*- coding: utf-8 -*-
"""
异步财务信息解析器
"""
import struct
from collections import OrderedDict

# 🚀 性能优化：导入native_compute用于批量乘法运算
from backend.infrastructure.native.native_compute import batch_compute

from ..base import AsyncBaseParser


class AsyncGetFinanceInfo(AsyncBaseParser):
    """
    获取财务信息命令（异步）

    返回字段说明：
    - liutongguben: 流通股本（万股）
    - zongguben: 总股本（万股）
    - zongzichan: 总资产（万元）
    - jingzichan: 净资产（万元）
    - zhuyingshouru: 主营收入（万元）
    - jinglirun: 净利润（万元）
    - meigujingzichan: 每股净资产（元）
    - industry: 行业代码
    - province: 省份代码
    - updated_date: 更新日期
    - ipo_date: 上市日期
    """

    def setParams(self, market, code):
        """
        设置请求参数
        :param market: 市场 (0=深圳, 1=上海, 2=北交所)
        :param code: 股票代码
        """
        if type(code) is str:
            code = code.encode("utf-8")

        pkg = bytearray.fromhex("0c 1f 18 76 00 01 0b 00 0b 00 10 00 01 00")
        pkg.extend(struct.pack("<B6s", market, code))

        self.send_pkg = pkg

    def parseResponse(self, body_buf):
        """
        解析财务信息响应
        :param body_buf: 响应体字节数据
        :return: 财务信息字典（33个字段）
        """
        pos = 0
        pos += 2  # skip num ,we only query 1 in this case

        # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
        market, code = struct.unpack_from("<B6s", body_buf, pos)

        pos += 7

        # 🚀 性能优化：使用 struct.unpack_from 避免内存切片拷贝
        (
            liutongguben,
            province,
            industry,
            updated_date,
            ipo_date,
            zongguben,
            guojiagu,
            faqirenfarengu,
            farengu,
            bgu,
            hgu,
            zhigonggu,
            zongzichan,
            liudongzichan,
            gudingzichan,
            wuxingzichan,
            gudongrenshu,
            liudongfuzhai,
            changqifuzhai,
            zibengongjijin,
            jingzichan,
            zhuyingshouru,
            zhuyinglirun,
            yingshouzhangkuan,
            yingyelirun,
            touzishouyu,
            jingyingxianjinliu,
            zongxianjinliu,
            cunhuo,
            lirunzonghe,
            shuihoulirun,
            jinglirun,
            weifenlirun,
            baoliu1,
            baoliu2,
        ) = struct.unpack_from("<fHHIIffffffffffffffffffffffffffffff", body_buf, pos)

        # 🚀 性能优化：批量收集需要乘以10000的值，然后批量处理
        # 需要乘以10000的字段（按顺序）
        values_to_multiply = [
            liutongguben,
            zongguben,
            guojiagu,
            faqirenfarengu,
            farengu,
            bgu,
            hgu,
            zhigonggu,
            zongzichan,
            liudongzichan,
            gudingzichan,
            wuxingzichan,
            liudongfuzhai,
            changqifuzhai,
            zibengongjijin,
            jingzichan,
            zhuyingshouru,
            zhuyinglirun,
            yingshouzhangkuan,
            yingyelirun,
            touzishouyu,
            jingyingxianjinliu,
            zongxianjinliu,
            cunhuo,
            lirunzonghe,
            shuihoulirun,
            jinglirun,
            weifenlirun,
        ]

        # 批量乘以10000（使用native_compute）
        if len(values_to_multiply) > 0:
            multipliers = [10000.0] * len(values_to_multiply)
            multiplied_values = batch_compute(values_to_multiply, "multiply", multipliers)  # type: ignore[call-arg]
        else:
            multiplied_values = []

        # 构建结果字典
        result = OrderedDict(
            [
                ("market", market),
                ("code", code.decode("utf-8")),
                ("liutongguben", multiplied_values[0]),
                ("province", province),
                ("industry", industry),
                ("updated_date", updated_date),
                ("ipo_date", ipo_date),
                ("zongguben", multiplied_values[1]),
                ("guojiagu", multiplied_values[2]),
                ("faqirenfarengu", multiplied_values[3]),
                ("farengu", multiplied_values[4]),
                ("bgu", multiplied_values[5]),
                ("hgu", multiplied_values[6]),
                ("zhigonggu", multiplied_values[7]),
                ("zongzichan", multiplied_values[8]),
                ("liudongzichan", multiplied_values[9]),
                ("gudingzichan", multiplied_values[10]),
                ("wuxingzichan", multiplied_values[11]),
                ("gudongrenshu", gudongrenshu),
                ("liudongfuzhai", multiplied_values[12]),
                ("changqifuzhai", multiplied_values[13]),
                ("zibengongjijin", multiplied_values[14]),
                ("jingzichan", multiplied_values[15]),
                ("zhuyingshouru", multiplied_values[16]),
                ("zhuyinglirun", multiplied_values[17]),
                ("yingshouzhangkuan", multiplied_values[18]),
                ("yingyelirun", multiplied_values[19]),
                ("touzishouyu", multiplied_values[20]),
                ("jingyingxianjinliu", multiplied_values[21]),
                ("zongxianjinliu", multiplied_values[22]),
                ("cunhuo", multiplied_values[23]),
                ("lirunzonghe", multiplied_values[24]),
                ("shuihoulirun", multiplied_values[25]),
                ("jinglirun", multiplied_values[26]),
                ("weifenpeilirun", multiplied_values[27]),
                ("meigujingzichan", baoliu1),
                ("baoliu2", baoliu2),
            ]
        )

        return result
