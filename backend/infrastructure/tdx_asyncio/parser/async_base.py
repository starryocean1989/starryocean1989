# -*- coding: utf-8 -*-
"""
异步基础解析器
"""
import abc
import asyncio
import struct
import zlib
from typing import Optional

from ..logger import logger


class SocketClientNotReady(Exception):
    pass


class SendPkgNotReady(Exception):
    pass


class SendRequestPkgFails(Exception):
    pass


class ResponseHeaderRecvFails(Exception):
    pass


class ResponseRecvFails(Exception):
    pass


RSP_HEADER_LEN = 0x10


class AsyncBaseParser:
    """
    异步基础解析器
    使用asyncio StreamReader/StreamWriter进行异步通信
    """

    def __init__(
        self,
        reader: Optional[asyncio.StreamReader],
        writer: Optional[asyncio.StreamWriter],
        lock: Optional[asyncio.Lock] = None
    ):
        """
        构造函数

        :param reader: asyncio StreamReader
        :param writer: asyncio StreamWriter
        :param lock: 异步锁（可选）
        """
        self.send_pkg = None
        self.data = None

        self.rsp_header_len = RSP_HEADER_LEN
        self.rsp_header = None
        self.rsp_body = None

        self.reader = reader
        self.writer = writer
        self.lock = lock

        self.category = None

    def setParams(self, *args, **xargs):
        """
        构建请求
        需要子类实现
        """
        pass

    @abc.abstractmethod
    def parseResponse(self, body_buf):
        """
        解析结果
        需要子类实现
        :param body_buf:
        """
        pass

    @staticmethod
    def _parse_date(num):
        """
        解析日期
        :param num:
        :return:
        """
        month = (num % 2048) // 100
        year = num // 2048 + 2004
        day = (num % 2048) % 100

        return year, month, day

    @staticmethod
    def _parse_time(num):
        """
        解析时间
        :param num:
        :return:
        """
        return (num // 60), (num % 60)

    @staticmethod
    def _cal_price1000(base_p, diff):
        return float(base_p + diff) / 1000

    def setup(self):
        """
        初始化
        可选实现
        """
        pass

    async def call_api(self):
        """
        调用API（异步）

        :return: 解析后的数据
        """
        if self.lock:
            async with self.lock:
                logger.debug("async api call with lock")
                result = await self._call_api()
        else:
            result = await self._call_api()

        return result

    async def _call_api(self):
        """
        内部API调用实现（异步）

        :return: 解析后的数据
        """
        self.setup()

        if not self.reader or not self.writer:
            raise SocketClientNotReady("socket client not ready")

        if not self.send_pkg:
            raise SendPkgNotReady("send pkg not ready")

        # 发送数据包
        self.writer.write(self.send_pkg)
        await self.writer.drain()

        logger.debug(f"sent {len(self.send_pkg)} bytes")

        # 接收响应头
        head_buf = await self.reader.readexactly(self.rsp_header_len)

        if len(head_buf) == self.rsp_header_len:
            # 解包
            _, _, _, zip_size, unzip_size = struct.unpack("<IIIHH", head_buf)

            logger.debug(f"zip size is: {zip_size}")
            logger.debug(f"unzip size is: {unzip_size}")

            # 接收响应体
            body_buf = bytearray()

            while len(body_buf) < zip_size:
                remaining = zip_size - len(body_buf)
                buf = await self.reader.read(remaining)

                if not buf:
                    logger.debug("接收数据体失败服务器断开连接")
                    raise ResponseRecvFails("接收数据体失败服务器断开连接")

                body_buf.extend(buf)

            # 解压缩（如果需要）
            if zip_size != unzip_size:
                logger.debug("需要解压, 解压数据")
                body_buf = zlib.decompress(body_buf)

            return self.parseResponse(body_buf)

        else:
            # 长度不符合抛出异常
            logger.debug("head_buf is not 0x10")
            raise ResponseHeaderRecvFails(f"head_buf is not 0x10 : {head_buf}")

