# -*- coding: utf-8 -*-
# flake8: noqa
# pylint: skip-file
# pyright: basic
# type: ignore
"""
组合策略模板

作者: {{author}}
创建时间: {{created_at}}
"""

from vnpy_portfoliostrategy import StrategyTemplate
from vnpy.trader.object import BarData, TickData


class {{strategy_name}}(StrategyTemplate):
    """{{description}}"""

    author = "{{author}}"

    # 策略参数
    {{parameters}}

    # 策略变量
    {{variables}}

    def __init__(self, strategy_engine, strategy_name, vt_symbols, setting):
        """构造函数"""
        super().__init__(strategy_engine, strategy_name, vt_symbols, setting)

    def on_init(self):
        """策略初始化"""
        self.write_log("策略初始化")

    def on_start(self):
        """策略启动"""
        self.write_log("策略启动")

    def on_stop(self):
        """策略停止"""
        self.write_log("策略停止")

    def on_tick(self, tick: TickData):
        """Tick推送"""
        pass

    def on_bars(self, bars: dict):
        """多合约K线推送"""
        pass

