# -*- coding: utf-8 -*-
"""
异步原始协议解析器
"""
import struct

from .base import AsyncBaseParser


class AsyncRawParser(AsyncBaseParser):
    """
    原始数据解析器，直接返回响应数据
    """

    def setParams(self, pkg):
        """
        设置发送数据包
        :param pkg: send pkg
        """
        self.send_pkg = pkg

    def parseResponse(self, body_buf):
        """
        解析结果（直接返回）
        :param body_buf: buff
        :return:
        """
        return body_buf

    @staticmethod
    def parse_pkg_header(header: bytes) -> int:
        """
        解析响应头，获取响应体长度

        :param header: 响应头字节数据（16字节）
        :return: 响应体长度
        """
        if len(header) != 16:
            return 0

        _, _, _, zip_size, unzip_size = struct.unpack("<IIIHH", header)
        return zip_size

    @staticmethod
    def parse_pkg_header_full(header: bytes) -> tuple[int, int]:
        """
        解析响应头，获取压缩大小和解压大小

        :param header: 响应头字节数据（16字节）
        :return: (zip_size, unzip_size)
        """
        if len(header) != 16:
            return (0, 0)

        _, _, _, zip_size, unzip_size = struct.unpack("<IIIHH", header)
        return (zip_size, unzip_size)

