# -*- coding: utf-8 -*-
# flake8: noqa
# pylint: skip-file
# pyright: basic
# type: ignore
"""
脚本交易策略模板

作者: {{author}}
创建时间: {{created_at}}

脚本交易策略提供最大的灵活性，适合：
- 快速验证交易想法
- 临时性交易任务
- 策略原型开发
- 数据分析和研究
"""

from vnpy_scripttrader import ScriptEngine
from vnpy.trader.object import TickData, OrderData, TradeData, PositionData
from vnpy.trader.constant import Direction, Offset, OrderType


class {{strategy_name}}(ScriptEngine):
    """{{description}}"""

    def __init__(self, main_engine, event_engine):
        """构造函数"""
        super().__init__(main_engine, event_engine)

        # 在此处添加自定义变量
        {{variables}}

    def on_tick(self, tick: TickData):
        """Tick推送"""
        pass

    def on_order(self, order: OrderData):
        """委托回报"""
        pass

    def on_trade(self, trade: TradeData):
        """成交回报"""
        pass

    # 在此处添加自定义方法
    {{custom_methods}}

