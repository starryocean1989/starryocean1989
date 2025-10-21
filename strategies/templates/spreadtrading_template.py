# -*- coding: utf-8 -*-
"""
价差交易策略模板

这是一个价差交易策略模板文件，用于创建自定义价差交易策略。
使用时请修改类名、参数和变量定义。

作者: 策略作者名称
创建时间: 创建日期
"""

from vnpy_spreadtrading import SpreadStrategyTemplate, SpreadData
from vnpy.trader.object import OrderData, TradeData


class SpreadTradingTemplate(SpreadStrategyTemplate):
    """价差交易策略模板"""

    # 策略作者
    author = "策略作者名称"

    # 策略参数 - 请根据实际需求修改
    fast_window = 10
    slow_window = 20

    # 策略变量 - 请根据实际需求修改
    fast_ma = 0.0
    slow_ma = 0.0

    # 参数列表
    parameters = ["fast_window", "slow_window"]
    
    # 变量列表
    variables = ["fast_ma", "slow_ma"]

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

