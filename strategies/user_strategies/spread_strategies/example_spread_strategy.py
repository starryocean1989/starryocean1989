# -*- coding: utf-8 -*-
"""
跨期价差套利策略示例

通过监控远近月合约的价差，当价差偏离合理区间时进行套利交易
适用于期货跨期套利、期现套利等

作者: VnPy团队
"""

from vnpy_spreadtrading import SpreadStrategyTemplate, SpreadData
from vnpy.trader.object import TickData, OrderData, TradeData


class SpreadArbitrageStrategy(SpreadStrategyTemplate):
    """跨期价差套利策略"""

    # 策略作者
    author = "VnPy团队"

    # 策略参数
    spread_up = 50.0  # 价差上轨
    spread_down = -50.0  # 价差下轨
    max_pos = 5  # 最大持仓
    payup = 10  # 超价幅度

    # 策略变量
    spread_pos = 0  # 价差持仓
    spread_price = 0.0  # 当前价差
    leg1_price = 0.0  # 腿1价格
    leg2_price = 0.0  # 腿2价格

    # 参数列表
    parameters = ["spread_up", "spread_down", "max_pos", "payup"]

    # 变量列表
    variables = ["spread_pos", "spread_price", "leg1_price", "leg2_price"]

    def __init__(self, strategy_engine, strategy_name, spread_name, setting):
        """构造函数"""
        super().__init__(strategy_engine, strategy_name, spread_name, setting)

    def on_init(self):
        """策略初始化"""
        self.write_log("跨期价差套利策略初始化")

    def on_start(self):
        """策略启动"""
        self.write_log("跨期价差套利策略启动")

    def on_stop(self):
        """策略停止"""
        self.write_log("跨期价差套利策略停止")

    def on_spread_data(self, spread: SpreadData):
        """价差行情推送"""
        # 更新价差价格
        self.spread_price = spread.bid_price

        # 更新腿价格
        self.leg1_price = spread.leg1_bid_price
        self.leg2_price = spread.leg2_ask_price

        # 更新持仓
        self.spread_pos = self.get_spread_pos()

        # 判断交易信号
        # 价差过高，做空价差（卖出腿1，买入腿2）
        if self.spread_price >= self.spread_up:
            if self.spread_pos > -self.max_pos:
                # 计算可以开仓的数量
                volume = min(1, self.max_pos + self.spread_pos)
                if volume > 0:
                    self.short(spread.bid_price - self.payup, volume)
                    self.write_log(f"价差过高 {self.spread_price:.2f}，做空价差 {volume} 手")

        # 价差过低，做多价差（买入腿1，卖出腿2）
        elif self.spread_price <= self.spread_down:
            if self.spread_pos < self.max_pos:
                # 计算可以开仓的数量
                volume = min(1, self.max_pos - self.spread_pos)
                if volume > 0:
                    self.buy(spread.ask_price + self.payup, volume)
                    self.write_log(f"价差过低 {self.spread_price:.2f}，做多价差 {volume} 手")

        # 价差回归，平仓
        elif self.spread_down < self.spread_price < self.spread_up:
            if self.spread_pos > 0:
                # 平多仓
                self.short(spread.bid_price - self.payup, abs(self.spread_pos))
                self.write_log(f"价差回归，平多仓 {abs(self.spread_pos)} 手")

            elif self.spread_pos < 0:
                # 平空仓
                self.buy(spread.ask_price + self.payup, abs(self.spread_pos))
                self.write_log(f"价差回归，平空仓 {abs(self.spread_pos)} 手")

        # 更新界面
        self.put_event()

    def on_spread_pos(self):
        """价差持仓更新"""
        self.spread_pos = self.get_spread_pos()
        self.put_event()

    def on_spread_algo(self, algo):
        """价差算法推送"""
        pass

    def on_order(self, order: OrderData):
        """委托回报"""
        status_value = order.status.value if order.status else "Unknown"
        self.write_log(f"委托回报: {order.vt_orderid}, 状态={status_value}")

    def on_trade(self, trade: TradeData):
        """成交回报"""
        direction_value = trade.direction.value if trade.direction else "Unknown"
        self.write_log(
            f"成交回报: {trade.vt_tradeid}, "
            f"方向={direction_value}, "
            f"数量={trade.volume}"
        )
