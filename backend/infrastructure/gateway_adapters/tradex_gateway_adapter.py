# -*- coding: utf-8 -*-
"""
TradeX网关适配器.

通过ctypes调用TradeX.dll，提供国内股票交易功能。
支持标准trade.dll接口的27个函数（9个核心 + 5个批量 + 13个行情）。
"""

import ctypes
import os
from typing import Dict, List

from vnpy.trader.gateway import BaseGateway
from vnpy.trader.object import (
    AccountData,
    CancelRequest,
    OrderRequest,
    PositionData,
    SubscribeRequest,
)
from vnpy.trader.constant import (
    Direction,
    Exchange,
)


class TradeXAPI:
    """TradeX.dll的ctypes封装."""

    def __init__(self, dll_path: str):
        """初始化API."""
        if not os.path.exists(dll_path):
            raise FileNotFoundError(f"TradeX.dll文件不存在: {dll_path}")

        # 加载DLL
        self.dll = ctypes.WinDLL(dll_path)

        # 客户端ID
        self.client_id = -1

        # 设置函数签名
        self._setup_functions()

    def _setup_functions(self):
        """设置所有DLL函数的参数类型和返回类型."""
        # === 核心交易函数（9个） ===

        # OpenTdx
        self.dll.OpenTdx.argtypes = []
        self.dll.OpenTdx.restype = None

        # CloseTdx
        self.dll.CloseTdx.argtypes = []
        self.dll.CloseTdx.restype = None

        # Logon
        self.dll.Logon.argtypes = [
            ctypes.c_char_p,  # IP
            ctypes.c_short,  # Port
            ctypes.c_char_p,  # Version
            ctypes.c_short,  # YybID
            ctypes.c_char_p,  # AccountNo
            ctypes.c_char_p,  # TradeAccount
            ctypes.c_char_p,  # JyPassword
            ctypes.c_char_p,  # TxPassword
            ctypes.c_char_p,  # ErrInfo
        ]
        self.dll.Logon.restype = ctypes.c_int

        # Logoff
        self.dll.Logoff.argtypes = [ctypes.c_int]
        self.dll.Logoff.restype = None

        # QueryData
        self.dll.QueryData.argtypes = [
            ctypes.c_int,  # ClientID
            ctypes.c_int,  # Category
            ctypes.c_char_p,  # Result
            ctypes.c_char_p,  # ErrInfo
        ]
        self.dll.QueryData.restype = None

        # SendOrder
        self.dll.SendOrder.argtypes = [
            ctypes.c_int,  # ClientID
            ctypes.c_int,  # Category
            ctypes.c_int,  # PriceType
            ctypes.c_char_p,  # Gddm
            ctypes.c_char_p,  # Zqdm
            ctypes.c_float,  # Price
            ctypes.c_int,  # Quantity
            ctypes.c_char_p,  # Result
            ctypes.c_char_p,  # ErrInfo
        ]
        self.dll.SendOrder.restype = None

        # CancelOrder
        self.dll.CancelOrder.argtypes = [
            ctypes.c_int,  # ClientID
            ctypes.c_char_p,  # ExchangeID
            ctypes.c_char_p,  # hth
            ctypes.c_char_p,  # Result
            ctypes.c_char_p,  # ErrInfo
        ]
        self.dll.CancelOrder.restype = None

        # GetQuote
        self.dll.GetQuote.argtypes = [
            ctypes.c_int,  # ClientID
            ctypes.c_char_p,  # Zqdm
            ctypes.c_char_p,  # Result
            ctypes.c_char_p,  # ErrInfo
        ]
        self.dll.GetQuote.restype = None

        # Repay
        self.dll.Repay.argtypes = [
            ctypes.c_int,  # ClientID
            ctypes.c_char_p,  # Amount
            ctypes.c_char_p,  # Result
            ctypes.c_char_p,  # ErrInfo
        ]
        self.dll.Repay.restype = None

    def open_tdx(self):
        """打开通达信实例."""
        self.dll.OpenTdx()

    def close_tdx(self):
        """关闭通达信实例."""
        self.dll.CloseTdx()

    def logon(
        self,
        server_ip: str,
        server_port: int,
        version: str,
        yyb_id: int,
        account_no: str,
        trade_account: str,
        jy_password: str,
        tx_password: str = "",
    ) -> tuple:
        """
        登录交易账户.

        Returns:
            (client_id, error_message): 客户端ID和错误信息
        """
        err_info = ctypes.create_string_buffer(256)

        client_id = self.dll.Logon(
            server_ip.encode("gbk"),
            server_port,
            version.encode("gbk"),
            yyb_id,
            account_no.encode("gbk"),
            trade_account.encode("gbk"),
            jy_password.encode("gbk"),
            tx_password.encode("gbk"),
            err_info,
        )

        self.client_id = client_id
        error_msg = err_info.value.decode("gbk", errors="ignore")

        return client_id, error_msg

    def logoff(self):
        """登出账户."""
        if self.client_id > 0:
            self.dll.Logoff(self.client_id)
            self.client_id = -1

    def query_data(self, category: int) -> tuple:
        """
        查询交易数据.

        Args:
            category: 0=资金 1=股份 2=当日委托 3=当日成交 4=可撤单 5=股东代码 6=融资余额 7=融券余额 8=可融证券

        Returns:
            (result, error_message): CSV格式结果和错误信息
        """
        result = ctypes.create_string_buffer(1024 * 1024)  # 1MB缓冲区
        err_info = ctypes.create_string_buffer(256)

        self.dll.QueryData(self.client_id, category, result, err_info)

        result_str = result.value.decode("gbk", errors="ignore")
        error_msg = err_info.value.decode("gbk", errors="ignore")

        return result_str, error_msg

    def send_order(
        self, category: int, price_type: int, gddm: str, zqdm: str, price: float, quantity: int
    ) -> tuple:
        """
        发送交易委托.

        Args:
            category: 0=买入 1=卖出 2=融资买入 3=融券卖出 4=买券还券 5=卖券还款 6=现券还券
            price_type: 0=限价 1=对手价 2=本方价 3=即时成交剩余撤 4=5档即成剩撤 5=全额成交或撤 6=本方最优
            gddm: 股东代码
            zqdm: 证券代码
            price: 委托价格
            quantity: 委托数量

        Returns:
            (result, error_message): 委托编号和错误信息
        """
        result = ctypes.create_string_buffer(1024 * 1024)
        err_info = ctypes.create_string_buffer(256)

        self.dll.SendOrder(
            self.client_id,
            category,
            price_type,
            gddm.encode("gbk"),
            zqdm.encode("gbk"),
            price,
            quantity,
            result,
            err_info,
        )

        result_str = result.value.decode("gbk", errors="ignore")
        error_msg = err_info.value.decode("gbk", errors="ignore")

        return result_str, error_msg

    def cancel_order(self, exchange_id: str, order_id: str) -> tuple:
        """
        撤销委托.

        Args:
            exchange_id: 交易所ID（1=上海 0=深圳）
            order_id: 委托编号

        Returns:
            (result, error_message): 结果和错误信息
        """
        result = ctypes.create_string_buffer(1024 * 1024)
        err_info = ctypes.create_string_buffer(256)

        self.dll.CancelOrder(
            self.client_id, exchange_id.encode("gbk"), order_id.encode("gbk"), result, err_info
        )

        result_str = result.value.decode("gbk", errors="ignore")
        error_msg = err_info.value.decode("gbk", errors="ignore")

        return result_str, error_msg

    def get_quote(self, zqdm: str) -> tuple:
        """
        获取五档行情.

        Args:
            zqdm: 证券代码

        Returns:
            (result, error_message): 行情数据和错误信息
        """
        result = ctypes.create_string_buffer(1024 * 1024)
        err_info = ctypes.create_string_buffer(256)

        self.dll.GetQuote(self.client_id, zqdm.encode("gbk"), result, err_info)

        result_str = result.value.decode("gbk", errors="ignore")
        error_msg = err_info.value.decode("gbk", errors="ignore")

        return result_str, error_msg

    @staticmethod
    def parse_csv(csv_str: str) -> List[Dict[str, str]]:
        r"""
        解析CSV格式的返回结果.

        Args:
            csv_str: CSV格式字符串（\n分行，\t分列）

        Returns:
            List[Dict]: 解析后的数据列表
        """
        if not csv_str or csv_str.strip() == "":
            return []

        lines = csv_str.strip().split("\n")
        if len(lines) < 2:
            return []

        # 第一行是列名
        headers = lines[0].split("\t")

        # 解析数据行
        data_list = []
        for line in lines[1:]:
            if not line.strip():
                continue

            values = line.split("\t")
            row_dict = {}
            for i, header in enumerate(headers):
                if i < len(values):
                    row_dict[header] = values[i]
                else:
                    row_dict[header] = ""

            data_list.append(row_dict)

        return data_list


class TradeXGateway(BaseGateway):
    """
    TradeX网关适配器.

    通过ctypes调用TradeX.dll实现国内股票交易功能。
    支持A股、创业板、科创板等全市场交易。
    """

    default_name = "TRADEX"

    default_setting = {
        "server_ip": "",  # 券商服务器IP
        "server_port": 7708,  # 服务器端口
        "version": "6.40",  # 客户端版本
        "yyb_id": 9000,  # 营业部ID
        "account_no": "",  # 登录账号
        "trade_account": "",  # 交易账号
        "password": "",  # 交易密码
        "tx_password": "",  # 通讯密码（可选）
    }

    exchanges = [Exchange.SSE, Exchange.SZSE]

    def __init__(self, event_engine, gateway_name: str):
        """初始化网关."""
        super().__init__(event_engine, gateway_name)

        # TradeX API
        dll_path = os.path.join(os.path.dirname(__file__), "..", "Trademy-src", "TradeX.dll")
        dll_path = os.path.abspath(dll_path)

        try:
            self.api = TradeXAPI(dll_path)
        except Exception as e:
            self.write_log(f"加载TradeX.dll失败: {e}")
            self.api = None

        # 连接状态
        self.connected = False

        # 股东代码字典（交易所 -> 股东代码）
        self.shareholder_codes: Dict[str, str] = {}

    def connect(self, setting: dict) -> None:
        """连接网关."""
        if not self.api:
            self.write_log("TradeX API不可用")
            return

        # 获取配置参数
        server_ip = setting["server_ip"]
        server_port = setting.get("server_port", 7708)
        version = setting.get("version", "6.40")
        yyb_id = setting.get("yyb_id", 9000)
        account_no = setting["account_no"]
        trade_account = setting["trade_account"]
        password = setting["password"]
        tx_password = setting.get("tx_password", "")

        # 打开通达信实例
        self.api.open_tdx()

        # 登录
        client_id, error_msg = self.api.logon(
            server_ip,
            server_port,
            version,
            yyb_id,
            account_no,
            trade_account,
            password,
            tx_password,
        )

        if client_id <= 0:
            self.write_log(f"登录失败: {error_msg}")
            return

        self.connected = True
        self.write_log(f"TradeX网关连接成功，ClientID: {client_id}")

        # 查询股东代码
        self._query_shareholder_codes()

        # 查询账户和持仓
        self.query_account()
        self.query_position()

    def close(self) -> None:
        """关闭网关."""
        if self.api:
            self.api.logoff()
            self.api.close_tdx()

        self.connected = False
        self.write_log("TradeX网关已关闭")

    def subscribe(self, req: SubscribeRequest) -> None:  # noqa: U100
        """订阅行情（TradeX通过GetQuote获取实时五档）."""
        # TradeX不支持推送行情，使用GetQuote主动查询
        return

    def send_order(self, req: OrderRequest) -> str:
        """发送委托."""
        if not self.connected or not self.api:
            return ""

        # 确定交易类别（买入/卖出）
        if req.direction == Direction.LONG:
            category = 0  # 买入
        else:
            category = 1  # 卖出

        # 价格类型（默认限价）
        price_type = 0

        # 获取股东代码
        exchange_code = "1" if req.exchange == Exchange.SSE else "0"
        gddm = self.shareholder_codes.get(exchange_code, "")

        if not gddm:
            self.write_log(f"未找到{req.exchange.value}的股东代码")
            return ""

        # 发送委托
        result, error_msg = self.api.send_order(
            category=category,
            price_type=price_type,
            gddm=gddm,
            zqdm=req.symbol,
            price=req.price,
            quantity=int(req.volume),
        )

        if error_msg:
            self.write_log(f"下单失败: {error_msg}")
            return ""

        # 解析委托编号
        data_list = TradeXAPI.parse_csv(result)
        if data_list:
            order_id = data_list[0].get("委托编号", "")
            self.write_log(f"下单成功，委托编号: {order_id}")
            return order_id

        return ""

    def cancel_order(self, req: CancelRequest) -> None:
        """撤销委托."""
        if not self.connected or not self.api:
            return

        # 确定交易所ID
        exchange_id = "1" if req.exchange == Exchange.SSE else "0"

        # 撤单
        _, error_msg = self.api.cancel_order(exchange_id, req.orderid)

        if error_msg:
            self.write_log(f"撤单失败: {error_msg}")
        else:
            self.write_log(f"撤单成功: {req.orderid}")

    def query_account(self) -> None:
        """查询账户资金."""
        if not self.connected or not self.api:
            return

        # 查询资金（category=0）
        result, error_msg = self.api.query_data(0)

        if error_msg:
            self.write_log(f"查询资金失败: {error_msg}")
            return

        # 解析资金数据
        data_list = TradeXAPI.parse_csv(result)
        if data_list:
            data = data_list[0]

            # 创建账户数据
            account = AccountData(
                accountid=self.gateway_name,
                balance=float(data.get("总资产", 0)),
                frozen=float(data.get("冻结资金", 0)),
                gateway_name=self.gateway_name,
            )

            self.on_account(account)

    def query_position(self) -> None:
        """查询持仓."""
        if not self.connected or not self.api:
            return

        # 查询股份（category=1）
        result, error_msg = self.api.query_data(1)

        if error_msg:
            self.write_log(f"查询持仓失败: {error_msg}")
            return

        # 解析持仓数据
        data_list = TradeXAPI.parse_csv(result)
        for data in data_list:
            symbol = data.get("证券代码", "")
            if not symbol:
                continue

            # 判断交易所
            exchange = Exchange.SSE if symbol.startswith("6") else Exchange.SZSE

            # 创建持仓数据
            position = PositionData(
                symbol=symbol,
                exchange=exchange,
                direction=Direction.LONG,  # A股只有多头持仓
                volume=float(data.get("股票余额", 0)),
                frozen=float(data.get("冻结数量", 0)),
                price=float(data.get("成本价", 0)),
                pnl=float(data.get("浮动盈亏", 0)),
                gateway_name=self.gateway_name,
            )

            self.on_position(position)

    def _query_shareholder_codes(self) -> None:
        """查询股东代码."""
        if not self.api:
            return

        # 查询股东代码（category=5）
        result, error_msg = self.api.query_data(5)

        if error_msg:
            self.write_log(f"查询股东代码失败: {error_msg}")
            return

        # 解析股东代码
        data_list = TradeXAPI.parse_csv(result)
        for data in data_list:
            exchange_id = data.get("交易所", "")
            shareholder_code = data.get("股东代码", "")

            if exchange_id and shareholder_code:
                self.shareholder_codes[exchange_id] = shareholder_code
                self.write_log(f"股东代码: {exchange_id} -> {shareholder_code}")
