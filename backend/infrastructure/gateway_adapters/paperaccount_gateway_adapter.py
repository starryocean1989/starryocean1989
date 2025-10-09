# -*- coding: utf-8 -*-
"""
PaperAccount网关适配器.

将vnpy_paperaccount.PaperAccountEngine适配为标准的vnpy Gateway接口。
"""

from typing import Dict, Optional

from vnpy.trader.constant import Exchange
from vnpy.trader.gateway import BaseGateway
from vnpy.trader.object import (
    AccountData,
    CancelRequest,
    ContractData,
    OrderData,
    OrderRequest,
    PositionData,
    SubscribeRequest,
    TickData,
)


class PaperAccountGateway(BaseGateway):
    """
    PaperAccount网关适配器.

    将PaperAccountEngine封装为标准Gateway接口，使其可以像其他网关一样使用。

    特点：
    - 纯本地模拟交易，无需服务器连接
    - 支持完整的交易功能（下单、撤单、查询等）
    - 提供虚拟资金和持仓管理
    - 实时P&L计算
    """

    default_name = "PAPERACCOUNT"

    default_setting = {
        "initial_capital": 1000000.0,  # 初始资金
        "slippage": 0.0,  # 滑点（点数）
        "commission_rate": 0.0003,  # 手续费率
        "size": 1,  # 合约大小
    }

    exchanges = [
        Exchange.SSE,
        Exchange.SZSE,
        Exchange.CFFEX,
        Exchange.SHFE,
        Exchange.DCE,
        Exchange.CZCE,
        Exchange.INE,
    ]

    def __init__(self, event_engine, gateway_name: str):
        """初始化网关."""
        super().__init__(event_engine, gateway_name)

        # PaperAccount引擎
        self.paper_engine = None

        # 配置参数
        self.initial_capital = 1000000.0
        self.slippage = 0.0
        self.commission_rate = 0.0003
        self.size = 1

        # 连接状态
        self.connected = False

        # 合约字典
        self.contracts: Dict[str, ContractData] = {}

        # 订单字典
        self.orders: Dict[str, OrderData] = {}

        # 持仓字典
        self.positions: Dict[str, PositionData] = {}

        # 账户数据
        self.account: Optional[AccountData] = None

    def connect(self, setting: dict) -> None:
        """连接网关."""
        # 获取配置参数
        self.initial_capital = setting.get("initial_capital", 1000000.0)
        self.slippage = setting.get("slippage", 0.0)
        self.commission_rate = setting.get("commission_rate", 0.0003)
        self.size = setting.get("size", 1)

        # 初始化PaperAccount引擎
        try:
            from vnpy_paperaccount import PaperAccountEngine

            # 创建PaperAccount引擎实例
            self.paper_engine = PaperAccountEngine(self.event_engine)

            # 初始化引擎
            self.paper_engine.init_engine()

            # 设置初始资金
            self.paper_engine.set_capital(self.initial_capital)

            # 设置手续费率和滑点
            self.paper_engine.set_parameters(
                commission_rate=self.commission_rate, slippage=self.slippage, size=self.size
            )

            # 标记为已连接
            self.connected = True

            # 初始化账户数据
            self._init_account_data()

            # 写入日志
            self.write_log("PaperAccount网关连接成功")

        except ImportError as e:
            self.write_log(f"vnpy_paperaccount未安装: {e}")
            return
        except Exception as e:
            self.write_log(f"PaperAccount连接失败: {e}")
            return

    def close(self) -> None:
        """关闭网关."""
        if self.paper_engine:
            try:
                self.paper_engine.close()
            except Exception as e:
                self.write_log(f"关闭PaperAccount引擎失败: {e}")

        self.connected = False
        self.write_log("PaperAccount网关已关闭")

    def subscribe(self, req: SubscribeRequest) -> None:
        """订阅行情."""
        # PaperAccount使用实时行情，需要外部通过事件引擎推送tick数据
        # Gateway本身不处理行情订阅，由外部数据源负责
        self.write_log(f"订阅行情: {req.symbol}.{req.exchange.value}")

    def send_order(self, req: OrderRequest) -> str:
        """发送委托."""
        if not self.connected:
            self.write_log("PaperAccount未连接，无法下单")
            return ""

        if not self.paper_engine:
            self.write_log("PaperAccount引擎不可用")
            return ""

        try:
            # 调用PaperAccount引擎发送订单
            order_id = self.paper_engine.send_order(req)

            # 创建订单数据
            order = OrderData(
                symbol=req.symbol,
                exchange=req.exchange,
                orderid=order_id,
                direction=req.direction,
                offset=req.offset,
                price=req.price,
                volume=req.volume,
                gateway_name=self.gateway_name,
            )

            # 保存订单
            self.orders[order_id] = order

            # 推送订单事件
            self.on_order(order)

            return order_id

        except Exception as e:
            self.write_log(f"发送订单失败: {e}")
            return ""

    def cancel_order(self, req: CancelRequest) -> None:
        """撤销委托."""
        if not self.connected:
            self.write_log("PaperAccount未连接，无法撤单")
            return

        if not self.paper_engine:
            self.write_log("PaperAccount引擎不可用")
            return

        try:
            # 调用PaperAccount引擎撤销订单
            self.paper_engine.cancel_order(req)

            self.write_log(f"订单撤销成功: {req.orderid}")

        except Exception as e:
            self.write_log(f"撤销订单失败: {e}")

    def query_account(self) -> None:
        """查询账户资金."""
        if not self.connected or not self.paper_engine:
            return

        try:
            # 获取账户信息
            capital = self.paper_engine.get_capital()
            available = self.paper_engine.get_available()

            # 创建账户数据
            account = AccountData(
                accountid=self.gateway_name,
                balance=capital,
                frozen=capital - available,
                gateway_name=self.gateway_name,
            )

            self.account = account

            # 推送账户事件
            self.on_account(account)

        except Exception as e:
            self.write_log(f"查询账户失败: {e}")

    def query_position(self) -> None:
        """查询持仓."""
        if not self.connected or not self.paper_engine:
            return

        try:
            # 获取持仓信息
            positions = self.paper_engine.get_all_positions()

            for pos_data in positions:
                # 创建持仓数据
                position = PositionData(
                    symbol=pos_data["symbol"],
                    exchange=pos_data["exchange"],
                    direction=pos_data["direction"],
                    volume=pos_data["volume"],
                    frozen=pos_data.get("frozen", 0),
                    price=pos_data.get("price", 0),
                    pnl=pos_data.get("pnl", 0),
                    gateway_name=self.gateway_name,
                )

                # 保存持仓
                pos_key = f"{position.vt_symbol}_{position.direction.value}"
                self.positions[pos_key] = position

                # 推送持仓事件
                self.on_position(position)

        except Exception as e:
            self.write_log(f"查询持仓失败: {e}")

    def _init_account_data(self) -> None:
        """初始化账户数据."""
        account = AccountData(
            accountid=self.gateway_name,
            balance=self.initial_capital,
            frozen=0.0,
            gateway_name=self.gateway_name,
        )

        self.account = account
        self.on_account(account)

    def process_tick_event(self, event) -> None:
        """处理Tick事件（用于PaperAccount计算盈亏）."""
        tick: TickData = event.data

        if self.paper_engine:
            try:
                # 更新PaperAccount的行情数据
                self.paper_engine.process_tick(tick)

                # 更新账户和持仓
                self.query_account()
                self.query_position()
            except Exception as e:
                self.write_log(f"处理Tick事件失败: {e}")
