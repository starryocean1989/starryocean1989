# -*- coding: utf-8 -*-
"""
双均线策略示例

这是一个简单的双均线交叉策略示例，用于演示VnPy CTA策略的基本结构。

策略逻辑：
1. 计算快速均线和慢速均线
2. 当快速均线上穿慢速均线时，买入开仓
3. 当快速均线下穿慢速均线时，卖出平仓

作者: VnPy团队
"""

from vnpy_ctastrategy import CtaTemplate
from vnpy.trader.object import BarData, TickData


class DoubleMaStrategy(CtaTemplate):
    """双均线策略"""

    # 策略作者
    author = "VnPy团队"

    # 策略参数
    fast_window = 10  # 快速均线窗口
    slow_window = 20  # 慢速均线窗口

    # 策略变量
    fast_ma = 0.0  # 快速均线值
    slow_ma = 0.0  # 慢速均线值
    ma_trend = 0  # 均线趋势：1表示金叉，-1表示死叉

    # 参数列表
    parameters = ["fast_window", "slow_window"]

    # 变量列表
    variables = ["fast_ma", "slow_ma", "ma_trend"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """构造函数"""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

        # 用于存储K线的列表
        self.bars = []

    def on_init(self):
        """策略初始化"""
        self.write_log("策略初始化")

        # 加载历史数据用于初始化
        self.load_bar(10)

    def on_start(self):
        """策略启动"""
        self.write_log("策略启动")

    def on_stop(self):
        """策略停止"""
        self.write_log("策略停止")

    def on_tick(self, tick: TickData):
        """Tick推送"""
        pass

    def on_bar(self, bar: BarData):
        """K线推送"""
        # 保存K线数据
        self.bars.append(bar)

        # 如果K线数量不足，则等待
        if len(self.bars) < self.slow_window:
            return

        # 只保留需要的K线数量
        if len(self.bars) > self.slow_window * 2:
            self.bars = self.bars[-self.slow_window * 2 :]

        # 计算快速均线
        fast_sum = sum([b.close_price for b in self.bars[-self.fast_window :]])
        self.fast_ma = fast_sum / self.fast_window

        # 计算慢速均线
        slow_sum = sum([b.close_price for b in self.bars[-self.slow_window :]])
        self.slow_ma = slow_sum / self.slow_window

        # 判断均线趋势
        if self.fast_ma > self.slow_ma:
            new_trend = 1
        elif self.fast_ma < self.slow_ma:
            new_trend = -1
        else:
            new_trend = 0

        # 检测均线交叉信号
        if new_trend != self.ma_trend:
            # 金叉：买入开仓
            if new_trend == 1:
                if self.pos == 0:
                    self.buy(bar.close_price + 10, 1)
                    self.write_log(f"金叉信号，买入开仓：价格={bar.close_price}")

            # 死叉：卖出平仓
            elif new_trend == -1:
                if self.pos > 0:
                    self.sell(bar.close_price - 10, 1)
                    self.write_log(f"死叉信号，卖出平仓：价格={bar.close_price}")

            # 更新趋势
            self.ma_trend = new_trend

        # 更新界面
        self.put_event()

    def on_order(self, order):
        """委托回报"""
        self.write_log(f"委托回报：{order.vt_orderid}, 状态={order.status}")

    def on_trade(self, trade):
        """成交回报"""
        self.write_log(
            f"成交回报：{trade.vt_tradeid}, "
            f"方向={trade.direction}, "
            f"价格={trade.price}, "
            f"数量={trade.volume}"
        )

    def on_stop_order(self, stop_order):
        """停止单回报"""
        pass
