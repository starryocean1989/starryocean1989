# -*- coding: utf-8 -*-
"""
脚本交易辅助策略示例

提供手动交易的辅助功能，如止损、止盈、追踪止损等
适用于需要人工判断但希望自动执行风控的场景

作者: VnPy团队
"""

from typing import Optional

from vnpy_scripttrader import ScriptEngine
from vnpy.trader.object import TickData, OrderData, TradeData, PositionData
from vnpy.trader.constant import Direction, Offset, OrderType


class ScriptTraderAssistant(ScriptEngine):
    """脚本交易辅助"""

    def __init__(self, main_engine, event_engine):
        """构造函数"""
        super().__init__(main_engine, event_engine)

        # 监控的合约
        self.vt_symbol = ""

        # 止损止盈参数
        self.stop_loss_price = 0.0  # 止损价
        self.take_profit_price = 0.0  # 止盈价
        self.trailing_stop_pct = 0.0  # 追踪止损百分比
        self.highest_price = 0.0  # 最高价（用于追踪止损）

        # 当前持仓和价格
        self.current_pos = 0
        self.current_price = 0.0

    def start_monitor(
        self, vt_symbol: str, stop_loss: float = 0, take_profit: float = 0, trailing_pct: float = 0
    ):
        """开始监控

        Args:
            vt_symbol: 合约代码
            stop_loss: 止损价（0表示不设置）
            take_profit: 止盈价（0表示不设置）
            trailing_pct: 追踪止损百分比（0表示不设置）
        """
        self.vt_symbol = vt_symbol
        self.stop_loss_price = stop_loss
        self.take_profit_price = take_profit
        self.trailing_stop_pct = trailing_pct
        self.highest_price = 0.0

        # 订阅行情
        self.subscribe(vt_symbol)

        self.write_log(f"开始监控 {vt_symbol}")
        self.write_log(f"止损价: {stop_loss}, 止盈价: {take_profit}, 追踪止损: {trailing_pct}%")

    def stop_monitor(self):
        """停止监控"""
        self.write_log(f"停止监控 {self.vt_symbol}")
        self.vt_symbol = ""

    def on_tick(self, tick: TickData):
        """行情推送"""
        if tick.vt_symbol != self.vt_symbol:
            return

        # 更新当前价格
        self.current_price = tick.last_price

        # 更新持仓
        position = self.get_position(tick.vt_symbol)
        if position:
            self.current_pos = position.volume
        else:
            self.current_pos = 0

        # 如果没有持仓，不需要检查止损止盈
        if self.current_pos == 0:
            return

        # 检查止损
        if self.stop_loss_price > 0:
            if self.current_pos > 0 and tick.last_price <= self.stop_loss_price:
                self._close_position("触发止损")
                return
            elif self.current_pos < 0 and tick.last_price >= self.stop_loss_price:
                self._close_position("触发止损")
                return

        # 检查止盈
        if self.take_profit_price > 0:
            if self.current_pos > 0 and tick.last_price >= self.take_profit_price:
                self._close_position("触发止盈")
                return
            elif self.current_pos < 0 and tick.last_price <= self.take_profit_price:
                self._close_position("触发止盈")
                return

        # 检查追踪止损
        if self.trailing_stop_pct > 0 and self.current_pos > 0:
            # 更新最高价
            if tick.last_price > self.highest_price:
                self.highest_price = tick.last_price
                self.write_log(f"更新最高价: {self.highest_price}")

            # 计算追踪止损价
            trailing_stop = self.highest_price * (1 - self.trailing_stop_pct / 100)

            # 检查是否触发追踪止损
            if tick.last_price <= trailing_stop:
                self._close_position(f"触发追踪止损（最高价: {self.highest_price}）")
                return

    def _close_position(self, reason: str):
        """平仓"""
        if self.current_pos == 0:
            return

        tick = self.get_tick(self.vt_symbol)
        if not tick:
            self.write_log("无法获取行情")
            return

        # 根据持仓方向平仓
        if self.current_pos > 0:
            # 平多仓
            price = tick.bid_price_1
            self.sell(self.vt_symbol, price, abs(self.current_pos))
            self.write_log(f"{reason}，平多仓: {abs(self.current_pos)} 手")
        else:
            # 平空仓
            price = tick.ask_price_1
            self.buy(self.vt_symbol, price, abs(self.current_pos))
            self.write_log(f"{reason}，平空仓: {abs(self.current_pos)} 手")

    def manual_buy(self, vt_symbol: str, price: float, volume: int):
        """手动买入"""
        self.buy(vt_symbol, price, volume)
        self.write_log(f"手动买入: {vt_symbol}, 价格={price}, 数量={volume}")

    def manual_sell(self, vt_symbol: str, price: float, volume: int):
        """手动卖出"""
        self.sell(vt_symbol, price, volume)
        self.write_log(f"手动卖出: {vt_symbol}, 价格={price}, 数量={volume}")

    def manual_short(self, vt_symbol: str, price: float, volume: int):
        """手动卖空"""
        self.short(vt_symbol, price, volume)
        self.write_log(f"手动卖空: {vt_symbol}, 价格={price}, 数量={volume}")

    def manual_cover(self, vt_symbol: str, price: float, volume: int):
        """手动平空"""
        self.cover(vt_symbol, price, volume)
        self.write_log(f"手动平空: {vt_symbol}, 价格={price}, 数量={volume}")

    def get_position(self, vt_symbol: str) -> Optional[PositionData]:
        """获取持仓"""
        positions = self.main_engine.get_all_positions()
        for pos in positions:
            if pos.vt_symbol == vt_symbol:
                return pos
        return None


# 使用示例
if __name__ == "__main__":
    # 这是一个使用示例，展示如何使用脚本交易助手
    # 实际使用时需要在ScriptTrader的控制台中运行

    # 创建助手实例（在实际环境中，main_engine和event_engine会自动传入）
    # assistant = ScriptTraderAssistant(main_engine, event_engine)

    # 示例1: 设置止损止盈监控
    # assistant.start_monitor("rb2310.SHFE", stop_loss=3800, take_profit=4000)

    # 示例2: 设置追踪止损（当价格上涨后回落2%时平仓）
    # assistant.start_monitor("rb2310.SHFE", trailing_pct=2.0)

    # 示例3: 手动下单
    # assistant.manual_buy("rb2310.SHFE", 3900, 1)

    pass
