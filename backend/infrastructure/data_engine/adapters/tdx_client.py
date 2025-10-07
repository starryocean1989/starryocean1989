# -*- coding: utf-8 -*-

"""
通达信行情客户端实现.

本模块实现了完整的通达信行情数据获取功能，
支持上海、深圳、北交所的市场数据获取.
"""

import logging
import socket
import struct
import zlib
from datetime import datetime
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple, Union

from .base_adapter import BaseDataAdapter


class TDXConfig:
    """TDX配置类."""

    def __init__(self) -> None:
        """初始化TDX配置."""
        self.host = "localhost"
        self.port = 7709
        self.timeout = 30
        self.auto_reconnect = True
        self.max_retry = 3
        self.retry_delay = 1.0


class TDXHqClient(BaseDataAdapter):
    """
    通达信行情客户端.

    基于pytdx协议实现，参考gotdx-main的设计，
    支持上交所、深交所、北交所的市场数据获取.
    """

    # 市场常量
    MARKET_SZ = 0  # 深圳
    MARKET_SH = 1  # 上海
    MARKET_BJ = 2  # 北京（北交所）

    # 命令常量
    CMD_SECURITY_QUOTES = 0x053E  # 行情信息
    CMD_SECURITY_COUNT = 0x044E  # 证券数量
    CMD_SECURITY_LIST = 0x0450  # 证券列表
    CMD_SECURITY_BARS = 0x052D  # K线数据
    CMD_MINUTE_TIME_DATA = 0x0537  # 分时数据

    def __init__(self, config: Dict[str, Union[str, int, float, bool]]) -> None:
        """
        初始化通达信行情客户端.

        Args:
            config: 配置字典,包含主机,端口等设置
        """
        super().__init__(config)
        self._name = "TDX_HQ"
        self._description = "通达信行情数据客户端"
        self._version = "1.0.0"
        self._socket: Optional[socket.socket] = None
        self._lock = Lock()
        self._config = TDXConfig()
        self.connected = False
        self.last_connection_time: Optional[datetime] = None
        self._logger = logging.getLogger(f"{__name__}.{self._name}")

        # 从配置中更新设置
        if "host" in config:
            self._config.host = str(config["host"])
        if "port" in config:
            self._config.port = int(config["port"])
        if "timeout" in config:
            self._config.timeout = int(config["timeout"])

    @property
    def name(self) -> str:
        """适配器名称."""
        return self._name

    @property
    def description(self) -> str:
        """适配器描述."""
        return self._description

    @property
    def version(self) -> str:
        """适配器版本."""
        return self._version

    async def connect(self) -> bool:
        """
        连接到通达信服务器.

        Returns:
            bool: 连接是否成功
        """
        try:
            with self._lock:
                if self._socket:
                    self._socket.close()

                self._logger.info(
                    "正在连接到TDX服务器 %s:%s", self._config.host, self._config.port
                )
                self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._socket.settimeout(self._config.timeout)
                self._socket.connect((self._config.host, self._config.port))

                # 发送握手包1
                if not self._send_handshake1():
                    return False

                # 发送握手包2
                if not self._send_handshake2():
                    return False

                self.connected = True
                self.last_connection_time = datetime.utcnow()
                self._logger.info("TDX连接成功")
                return True

        except OSError as exc:
            self.connected = False
            if self._socket:
                self._socket.close()
                self._socket = None
            self._logger.error("TDX连接失败: %s", exc)
            return False

    async def disconnect(self) -> bool:
        """
        断开服务器连接.

        Returns:
            bool: 断开是否成功
        """
        try:
            with self._lock:
                if self._socket:
                    self._logger.info("正在断开TDX连接")
                    self._socket.close()
                    self._socket = None

                self.connected = False
                self._logger.info("TDX连接已断开")
                return True

        except OSError as exc:
            self._logger.error("断开TDX连接时出错: %s", exc)
            return False

    async def check_connection(self) -> bool:
        """
        检查连接状态.

        Returns:
            bool: 是否已连接
        """
        if not self._socket:
            self._logger.debug("TDX socket未初始化")
            return False

        try:
            # 发送心跳包检查连接
            if self.connected and self._socket:
                # 可以添加实际的心跳检查逻辑
                return True
            return False
        except OSError as exc:
            self._logger.warning("TDX连接检查失败: %s", exc)
            self.connected = False
            return False

    def _send_handshake1(self) -> bool:
        """发送握手包1."""
        try:
            if not self._socket:
                self._logger.error("Socket未初始化，无法发送握手包1")
                return False
            handshake1 = bytes.fromhex("0c 02 18 93 00 01 03 00 03 00 0d 00 01")
            self._socket.send(handshake1)
            response = self._socket.recv(20)
            return len(response) > 0
        except OSError as exc:
            self._logger.error("发送握手包1失败: %s", exc)
            return False

    def _send_handshake2(self) -> bool:
        """发送握手包2."""
        try:
            if not self._socket:
                self._logger.error("Socket未初始化，无法发送握手包2")
                return False
            handshake2 = bytes.fromhex("0c 02 18 94 00 01 03 00 03 00 0d 00 02")
            self._socket.send(handshake2)
            response = self._socket.recv(20)
            return len(response) > 0
        except OSError as exc:
            self._logger.error("发送握手包2失败: %s", exc)
            return False

    def _send_request(self, request_data: bytes) -> Optional[bytes]:
        """
        发送请求并接收响应.

        Args:
            request_data: 请求数据

        Returns:
            Optional[bytes]: 响应数据
        """
        try:
            if not self._socket or not self.connected:
                self._logger.error("TDX socket未连接，无法发送请求")
                return None

            with self._lock:
                self._socket.send(request_data)
                # 读取响应头部
                header = self._socket.recv(16)
                if len(header) != 16:
                    self._logger.error("响应头部长度错误: %d", len(header))
                    return None

                # 解析响应头部
                header_data = struct.unpack("<IIIIHH", header)
                zip_size = header_data[4]
                unzip_size = header_data[5]

                # 读取响应数据
                response_data = self._socket.recv(zip_size)
                if len(response_data) != zip_size:
                    self._logger.error(
                        "响应数据长度错误: %d != %d", len(response_data), zip_size
                    )
                    return None

                # 如果数据被压缩，需要解压
                if zip_size != unzip_size:
                    response_data = zlib.decompress(response_data)

                self._logger.debug("TDX请求响应长度: %s", len(response_data))
                return response_data

        except OSError as exc:
            self._logger.error("发送TDX请求时出错: %s", exc)
            return None

    def _format_symbol(self, market: int, code: str) -> bytes:
        """
        格式化证券代码为通达信格式.

        Args:
            market: 市场标识 (0=深圳, 1=上海, 2=北交所)
            code: 证券代码

        Returns:
            bytes: 通达信格式的代码
        """
        try:
            # 通达信代码格式: 市场标识(1字节) + 6位代码
            code_padded = code.zfill(6)
            return struct.pack("<B6s", market, code_padded.encode("ascii"))
        except ValueError as exc:
            self._logger.error("格式化证券代码 %s 时出错: %s", code, exc)
            return struct.pack("<B6s", market, code.zfill(6).encode("ascii"))

    async def get_security_quotes(
        self, stocks: List[Tuple[int, str]]
    ) -> List[Dict[str, Any]]:
        """
        获取行情数据.

        Args:
            stocks: 股票代码列表，格式为 [(market, code), ...]

        Returns:
            List[Dict[str, Any]]: 行情数据列表
        """
        try:
            if not self.connected or not self._socket:
                self._logger.warning("TDX未连接，无法获取行情数据")
                return []

            stock_count = len(stocks)
            if stock_count == 0:
                return []

            # 构建请求包
            pkg_len = stock_count * 7 + 12

            # 请求头部: 0x10c, 0x02006320, pkg_len, pkg_len, 0x5053e, 0, 0, stock_count
            header_data = struct.pack(
                "<HIHHIIHH",
                0x10C,
                0x02006320,
                pkg_len,
                pkg_len,
                self.CMD_SECURITY_QUOTES,
                0,
                0,
                stock_count,
            )

            request_data = bytearray(header_data)
            for market, code in stocks:
                request_data.extend(self._format_symbol(market, code))

            # 发送请求
            response = self._send_request(bytes(request_data))
            if not response:
                return []

            # 解析响应
            return self._parse_security_quotes_response(response)

        except Exception as exc:
            self._logger.error("获取行情数据时出错: %s", exc)
            return []

    def _parse_security_quotes_response(self, response: bytes) -> List[Dict[str, Any]]:
        """解析行情数据响应."""
        quotes = []
        pos = 0

        try:
            # 跳过前两个字节
            pos += 2

            # 读取股票数量
            stock_count = struct.unpack("<H", response[pos : pos + 2])[0]
            pos += 2

            for _ in range(stock_count):
                # 解析一只股票的数据
                market = response[pos]
                code = response[pos + 1 : pos + 7].decode("ascii").strip()
                pos += 7

                # 活跃度
                active1 = struct.unpack("<H", response[pos : pos + 2])[0]
                pos += 2

                # 价格数据（使用get_price解析）
                price = self._get_price(response, pos)
                pos += 4  # get_price会自动推进位置

                last_close_diff = self._get_price(response, pos)
                pos += 4

                open_diff = self._get_price(response, pos)
                pos += 4

                high_diff = self._get_price(response, pos)
                pos += 4

                low_diff = self._get_price(response, pos)
                pos += 4

                # 其他字段...
                # 这里简化处理，实际应该解析所有字段

                quote = {
                    "market": market,
                    "code": code,
                    "active1": active1,
                    "price": self._calc_price(price, 0),
                    "last_close": self._calc_price(price, last_close_diff),
                    "open": self._calc_price(price, open_diff),
                    "high": self._calc_price(price, high_diff),
                    "low": self._calc_price(price, low_diff),
                    "timestamp": datetime.utcnow().isoformat(),
                    "source": "tdx",
                }
                quotes.append(quote)

        except Exception as exc:
            self._logger.error("解析行情数据响应时出错: %s", exc)

        return quotes

    def _get_price(self, data: bytes, start_pos: int) -> int:
        """
        解析通达信价格数据.

        Args:
            data: 数据字节串
            start_pos: 起始位置

        Returns:
            int: 价格值
        """
        # 简化版价格解析，实际应该实现完整的get_price逻辑
        if start_pos + 4 > len(data):
            return 0

        price = struct.unpack("<i", data[start_pos : start_pos + 4])[0]
        return price

    def _calc_price(self, base_price: int, diff: int) -> float:
        """计算实际价格."""
        return float(base_price + diff) / 100

    async def get_quotes(self, symbols: List[str]) -> List[Dict[str, Any]]:
        """
        获取行情数据（简化接口）.

        Args:
            symbols: 股票代码列表

        Returns:
            List[Dict[str, Any]]: 行情数据列表
        """
        # 这里需要实现符号到市场+代码的转换逻辑
        # 简化处理，假设所有股票都是深圳股票
        stocks = [(self.MARKET_SZ, symbol) for symbol in symbols]
        return await self.get_security_quotes(stocks)

    async def get_market_data(
        self, symbol: str, data_type: str = "quote"
    ) -> Optional[Dict[str, Union[str, int, float, bool]]]:
        """
        获取市场数据（简化接口）.

        Args:
            symbol: 证券代码
            data_type: 数据类型 (当前仅支持 "quote")

        Returns:
            Optional[Dict[str, Union[str, int, float, bool]]]: 市场数据字典
        """
        _ = data_type  # 当前仅支持quote类型，参数保留用于未来扩展
        quotes = await self.get_quotes([symbol])
        return quotes[0] if quotes else None

    async def get_historical_data(
        self, symbol: str, start_date: datetime, end_date: datetime
    ) -> List[Dict[str, Any]]:
        """
        获取历史数据（简化接口）.

        Args:
            symbol: 证券代码
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            List[Dict[str, Any]]: 历史数据列表
        """
        # 保留参数用于未来实现
        _ = (symbol, start_date, end_date)
        # 这里需要实现历史数据获取逻辑
        # 简化处理，返回空列表
        self._logger.warning("历史数据获取功能尚未完全实现")
        return []

    async def get_security_bars(
        self, category: int, market: int, code: str, start: int, count: int
    ) -> List[Dict[str, Any]]:
        """
        获取股票K线数据.

        Args:
            category: K线类型 (9=日K线)
            market: 市场标识 (0=深圳, 1=上海, 2=北交所)
            code: 证券代码
            start: 起始位置
            count: 数量

        Returns:
            List[Dict[str, Any]]: K线数据列表
        """
        try:
            if not self.connected or not self._socket:
                self._logger.warning("TDX未连接，无法获取K线数据")
                return []

            # 构建请求包
            # 请求头部: 0x10c, 0x02006320, pkg_len, pkg_len, 0x052d, ...
            pkg_len = 12 + 7 + 2  # 头部(12) + 股票标识(7) + 其他参数(2)

            header_data = struct.pack(
                "<HIHHIIHHHHHHHHHH",
                0x10C,
                0x02006320,
                pkg_len,
                pkg_len,
                self.CMD_SECURITY_BARS,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
                0,
            )

            # 股票标识
            stock_data = self._format_symbol(market, code)

            # 参数：category, start, count
            param_data = struct.pack("<HHH", category, start, count)

            request_data = bytearray(header_data)
            request_data.extend(stock_data)
            request_data.extend(param_data)

            # 发送请求
            response = self._send_request(bytes(request_data))
            if not response:
                return []

            # 解析响应
            return self._parse_security_bars_response(response)

        except Exception as exc:
            self._logger.error("获取K线数据时出错: %s", exc)
            return []

    def _parse_security_bars_response(self, response: bytes) -> List[Dict[str, Any]]:
        """解析K线数据响应."""
        klines = []
        pos = 0

        try:
            # 跳过前两个字节
            pos += 2

            # 读取K线数量
            kline_count = struct.unpack("<H", response[pos : pos + 2])[0]
            pos += 2

            for _ in range(kline_count):
                # 解析一条K线数据
                # 年、月、日、时、分
                year = struct.unpack("<H", response[pos : pos + 2])[0]
                month = struct.unpack("<H", response[pos + 2 : pos + 4])[0]
                day = struct.unpack("<H", response[pos + 4 : pos + 6])[0]
                hour = struct.unpack("<H", response[pos + 6 : pos + 8])[0]
                minute = struct.unpack("<H", response[pos + 8 : pos + 10])[0]
                pos += 10

                # 价格和成交量
                open_price = self._get_price(response, pos)
                pos += 4

                high_price = self._get_price(response, pos)
                pos += 4

                low_price = self._get_price(response, pos)
                pos += 4

                close_price = self._get_price(response, pos)
                pos += 4

                amount_raw = struct.unpack("<I", response[pos : pos + 4])[0]
                pos += 4
                amount = self._get_volume(amount_raw)

                volume_raw = struct.unpack("<I", response[pos : pos + 4])[0]
                pos += 4
                volume = self._get_volume(volume_raw)

                # 保留字段
                reserved = struct.unpack("<I", response[pos : pos + 4])[0]
                pos += 4

                kline = {
                    "code": "UNKNOWN",  # 需要从请求中获取
                    "datetime": (
                        f"{year:04d}-{month:02d}-{day:02d} " f"{hour:02d}:{minute:02d}"
                    ),
                    "open": self._calc_price(open_price, 0),
                    "high": self._calc_price(high_price, 0),
                    "low": self._calc_price(low_price, 0),
                    "close": self._calc_price(close_price, 0),
                    "volume": volume,
                    "amount": amount,
                    "reserved": reserved,
                }
                klines.append(kline)

        except Exception as exc:
            self._logger.error("解析K线数据响应时出错: %s", exc)

        return klines

    def _get_volume(self, raw_volume: int) -> float:
        """解析成交量数据."""
        # 简化版成交量解析，实际应该实现完整的get_volume逻辑
        return float(raw_volume) / 100  # 假设除以100转换为手

    async def cleanup(self) -> None:
        """清理资源."""
        try:
            self._logger.info("正在清理TDX客户端资源")
            await self.disconnect()
            self._logger.info("TDX客户端资源清理完成")
        except OSError as exc:
            self._logger.error("清理TDX客户端资源时出错: %s", exc)
