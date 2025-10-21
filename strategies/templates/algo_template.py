# -*- coding: utf-8 -*-
# flake8: noqa
# pylint: skip-file
"""
算法交易策略模板

作者: [请填写作者名称]
创建时间: [请填写创建时间]
"""

from vnpy_algotrading import AlgoTemplate
from vnpy.trader.object import TickData


class AlgoStrategyTemplate(AlgoTemplate):
    """算法交易策略模板 - 请修改类名和描述"""

    display_name = "AlgoStrategyTemplate"

    # 策略参数 (示例)
    # price_add: int = 5
    # volume: int = 100

    # 策略变量 (示例)
    # traded: int = 0

    def __init__(self, algo_engine, algo_name, vt_symbol, setting):
        """构造函数"""
        super().__init__(algo_engine, algo_name, vt_symbol, setting)

    def on_tick(self, tick: TickData):
        """Tick推送"""
        pass

    def on_order(self, order):
        """委托回报"""
        pass

    def on_trade(self, trade):
        """成交回报"""
        pass

    def on_timer(self):
        """定时器"""
        pass

