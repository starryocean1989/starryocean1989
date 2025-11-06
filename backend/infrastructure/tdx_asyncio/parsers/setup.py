# -*- coding: utf-8 -*-
"""
异步初始化命令解析器
"""
from .base import AsyncBaseParser


class AsyncBaseSetup(AsyncBaseParser):
    """
    基础初始化命令
    """

    def parseResponse(self, body_buf):
        """
        解析返回结果
        :param body_buf:
        :return:
        """
        return body_buf


class AsyncSetupCmd1(AsyncBaseSetup):
    """
    初始化命令1
    """

    def setup(self):
        self.send_pkg = bytearray.fromhex("0c 02 18 93 00 01 03 00 03 00 0d 00 01")


class AsyncSetupCmd2(AsyncBaseSetup):
    """
    初始化命令2
    """

    def setup(self):
        self.send_pkg = bytearray.fromhex("0c 02 18 94 00 01 03 00 03 00 0d 00 02")


class AsyncSetupCmd3(AsyncBaseSetup):
    """
    初始化命令3
    """

    def setup(self):
        self.send_pkg = bytearray.fromhex(
            "0c 03 18 99 00 01 20 00 20 00 db 0f d5 d0"
            "c9 cc d6 a4 a8 af 00 00 00 8f c2 25 40 13"
            "00 00 d5 00 c9 cc bd f0 d7 ea 00 00 00 02"
        )

