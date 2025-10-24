# -*- coding: utf-8 -*-
"""
期权Delta对冲策略示例

通过持有期权头寸并用标的资产进行Delta对冲，实现方向中性策略
适用于波动率交易和时间价值收割

作者: VnPy团队
"""

from vnpy_optionmaster import OptionTemplate
from vnpy.trader.object import TickData, OrderData, TradeData
from vnpy.trader.constant import Direction, Offset


class OptionDeltaHedgeStrategy(OptionTemplate):
    """期权Delta对冲策略"""

    # 策略作者
    author = "VnPy团队"

    # 策略参数
    hedge_threshold = 0.1  # 对冲阈值（Delta绝对值）
    hedge_ratio = 1.0  # 对冲比例
    max_position = 10  # 最大持仓

    # 策略变量
    portfolio_delta = 0.0  # 组合Delta
    portfolio_gamma = 0.0  # 组合Gamma
    portfolio_vega = 0.0  # 组合Vega
    portfolio_theta = 0.0  # 组合Theta
    underlying_price = 0.0  # 标的价格

    # 参数列表
    parameters = ["hedge_threshold", "hedge_ratio", "max_position"]

    # 变量列表
    variables = [
        "portfolio_delta",
        "portfolio_gamma",
        "portfolio_vega",
        "portfolio_theta",
        "underlying_price",
    ]

    def __init__(self, option_engine, strategy_name, vt_symbols, setting):
        """构造函数"""
        super().__init__(option_engine, strategy_name, vt_symbols, setting)

    def on_init(self):
        """策略初始化"""
        self.write_log("期权Delta对冲策略初始化")

    def on_start(self):
        """策略启动"""
        self.write_log("期权Delta对冲策略启动")

    def on_stop(self):
        """策略停止"""
        self.write_log("期权Delta对冲策略停止")

    def on_tick(self, tick: TickData):
        """行情推送"""
        # 更新标的价格
        if tick.vt_symbol == self.get_underlying_symbol():
            self.underlying_price = tick.last_price

        # 计算组合希腊字母
        self._calculate_greeks()

        # 检查是否需要对冲
        if abs(self.portfolio_delta) > self.hedge_threshold:
            self._hedge_delta()

    def _calculate_greeks(self):
        """计算组合希腊字母"""
        # 从持仓计算希腊字母
        positions = self.get_all_positions()

        total_delta = 0.0
        total_gamma = 0.0
        total_vega = 0.0
        total_theta = 0.0

        for pos in positions:
            # 获取期权信息
            option_data = self.get_option_data(pos.vt_symbol)
            if option_data:
                total_delta += option_data.delta * pos.volume
                total_gamma += option_data.gamma * pos.volume
                total_vega += option_data.vega * pos.volume
                total_theta += option_data.theta * pos.volume

        self.portfolio_delta = total_delta
        self.portfolio_gamma = total_gamma
        self.portfolio_vega = total_vega
        self.portfolio_theta = total_theta

        # 更新界面
        self.put_event()

    def _hedge_delta(self):
        """Delta对冲"""
        # 计算需要对冲的数量
        hedge_volume = int(abs(self.portfolio_delta) * self.hedge_ratio)

        if hedge_volume == 0:
            return

        # 获取标的行情
        underlying_tick = self.get_tick(self.get_underlying_symbol())
        if not underlying_tick:
            self.write_log("无法获取标的行情")
            return

        # 根据Delta符号决定对冲方向
        if self.portfolio_delta > 0:
            # Delta为正，需要卖出标的
            price = underlying_tick.bid_price_1
            self.short(self.get_underlying_symbol(), price, hedge_volume)
            self.write_log(f"Delta对冲: 卖出标的 {hedge_volume} 手")
        else:
            # Delta为负，需要买入标的
            price = underlying_tick.ask_price_1
            self.buy(self.get_underlying_symbol(), price, hedge_volume)
            self.write_log(f"Delta对冲: 买入标的 {hedge_volume} 手")

    def on_order(self, order: OrderData):
        """委托回报"""
        status_value = order.status.value if order.status else "未知"
        self.write_log(f"委托回报: {order.vt_orderid}, 状态={status_value}")

    def on_trade(self, trade: TradeData):
        """成交回报"""
        direction_value = trade.direction.value if trade.direction else "未知"
        self.write_log(
            f"成交回报: {trade.vt_tradeid}, "
            f"方向={direction_value}, "
            f"数量={trade.volume}"
        )

    def get_underlying_symbol(self) -> str:
        """获取标的合约代码"""
        # 这里需要根据实际情况返回标的合约
        # 示例：如果是50ETF期权，返回 "510050.SSE"
        return "510050.SSE"

    def get_option_data(self, vt_symbol: str):
        """获取期权数据（需要从期权引擎获取）"""
        # 这里是示例，实际需要从option_engine获取
        return None

    def get_all_positions(self):
        """获取所有持仓"""
        # 这里是示例，实际需要从引擎获取
        return []
