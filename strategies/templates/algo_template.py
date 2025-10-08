# -*- coding: utf-8 -*-
# flake8: noqa
# pylint: skip-file
"""
算法交易策略模板

作者: {{author}}
创建时间: {{created_at}}
"""

from vnpy_algotrading import AlgoTemplate
from vnpy.trader.object import TickData


class {{strategy_name}}(AlgoTemplate):
    """{{description}}"""

    display_name = "{{strategy_name}}"

    # 策略参数
    {{parameters}}

    # 策略变量
    {{variables}}

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

