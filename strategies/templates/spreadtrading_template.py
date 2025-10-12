# -*- coding: utf-8 -*-
# flake8: noqa
# pylint: skip-file
"""
价差交易策略模板

作者: {{author}}
创建时间: {{created_at}}
"""

from vnpy_spreadtrading import SpreadStrategyTemplate, SpreadData
from vnpy.trader.object import TickData, OrderData, TradeData


class {{strategy_name}}(SpreadStrategyTemplate):
    """{{description}}"""

    # 策略作者
    author = "{{author}}"

    # 策略参数
    {{parameters}}

    # 策略变量
    {{variables}}

    def __init__(self, strategy_engine, strategy_name, spread_name, setting):
        """构造函数"""
        super().__init__(strategy_engine, strategy_name, spread_name, setting)

    def on_init(self):
        """策略初始化"""
        self.write_log("策略初始化")

    def on_start(self):
        """策略启动"""
        self.write_log("策略启动")

    def on_stop(self):
        """策略停止"""
        self.write_log("策略停止")

    def on_spread_data(self, spread: SpreadData):
        """价差行情推送"""
        pass

    def on_spread_pos(self):
        """价差持仓更新"""
        pass

    def on_spread_algo(self, algo):
        """价差算法推送"""
        pass

    def on_order(self, order: OrderData):
        """委托回报"""
        pass

    def on_trade(self, trade: TradeData):
        """成交回报"""
        pass

