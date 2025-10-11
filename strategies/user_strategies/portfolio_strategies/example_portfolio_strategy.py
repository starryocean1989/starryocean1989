# -*- coding: utf-8 -*-
"""
多品种组合轮动策略示例

根据多个品种的相对强度进行轮动，持有强势品种，卖出弱势品种
适用于股票、期货等多品种组合交易

作者: VnPy团队
"""

from vnpy_portfoliostrategy import StrategyTemplate
from vnpy.trader.object import BarData, TickData
from vnpy.trader.constant import Direction, Offset


class PortfolioRotationStrategy(StrategyTemplate):
    """多品种组合轮动策略"""

    # 策略作者
    author = "VnPy团队"

    # 策略参数
    momentum_window = 20  # 动量计算窗口
    rebalance_days = 5  # 调仓间隔（天数）
    hold_count = 2  # 持有品种数量
    position_size = 10000  # 每个品种持仓金额

    # 策略变量
    bar_count = 0  # K线计数
    momentum_dict = {}  # 品种动量字典
    target_positions = {}  # 目标持仓
    current_positions = {}  # 当前持仓

    # 参数列表
    parameters = ["momentum_window", "rebalance_days", "hold_count", "position_size"]

    # 变量列表
    variables = ["bar_count", "momentum_dict", "target_positions"]

    def __init__(self, strategy_engine, strategy_name, vt_symbols, setting):
        """构造函数"""
        super().__init__(strategy_engine, strategy_name, vt_symbols, setting)

        # 存储K线数据
        self.bars_dict = {}
        for vt_symbol in vt_symbols:
            self.bars_dict[vt_symbol] = []

    def on_init(self):
        """策略初始化"""
        self.write_log("多品种组合轮动策略初始化")

        # 加载历史数据
        self.load_bars(self.momentum_window + 10)

    def on_start(self):
        """策略启动"""
        self.write_log("多品种组合轮动策略启动")

    def on_stop(self):
        """策略停止"""
        self.write_log("多品种组合轮动策略停止")

    def on_bars(self, bars: dict):
        """K线推送（多品种同时推送）"""
        self.bar_count += 1

        # 保存K线数据
        for vt_symbol, bar in bars.items():
            if vt_symbol not in self.bars_dict:
                self.bars_dict[vt_symbol] = []
            self.bars_dict[vt_symbol].append(bar)

            # 只保留需要的K线数量
            if len(self.bars_dict[vt_symbol]) > self.momentum_window * 2:
                self.bars_dict[vt_symbol] = self.bars_dict[vt_symbol][-self.momentum_window * 2 :]

        # 检查是否到达调仓时间
        if self.bar_count % self.rebalance_days != 0:
            return

        # 计算各品种动量
        self._calculate_momentum()

        # 选择目标持仓品种
        self._select_targets()

        # 执行调仓
        self._rebalance()

    def _calculate_momentum(self):
        """计算各品种动量"""
        self.momentum_dict.clear()

        for vt_symbol, bars in self.bars_dict.items():
            if len(bars) < self.momentum_window:
                continue

            # 计算动量：当前价格相对N日前的涨幅
            current_price = bars[-1].close_price
            past_price = bars[-self.momentum_window].close_price

            if past_price > 0:
                momentum = (current_price - past_price) / past_price * 100
                self.momentum_dict[vt_symbol] = momentum

        self.write_log(f"动量计算完成: {self.momentum_dict}")

    def _select_targets(self):
        """选择目标持仓品种"""
        # 按动量排序
        sorted_symbols = sorted(self.momentum_dict.items(), key=lambda x: x[1], reverse=True)

        # 选择前N个品种
        self.target_positions.clear()
        for i in range(min(self.hold_count, len(sorted_symbols))):
            vt_symbol = sorted_symbols[i][0]
            self.target_positions[vt_symbol] = self.position_size

        self.write_log(f"目标持仓: {self.target_positions}")

    def _rebalance(self):
        """执行调仓"""
        # 获取当前持仓
        for vt_symbol in self.vt_symbols:
            pos = self.get_pos(vt_symbol)
            self.current_positions[vt_symbol] = pos

        # 平掉不在目标中的持仓
        for vt_symbol, pos in self.current_positions.items():
            if pos > 0 and vt_symbol not in self.target_positions:
                bar = self.bars_dict.get(vt_symbol, [None])[-1]
                if bar:
                    self.sell(vt_symbol, bar.close_price, abs(pos))
                    self.write_log(f"平仓: {vt_symbol}, 数量={abs(pos)}")

        # 建立目标持仓
        for vt_symbol, target_value in self.target_positions.items():
            current_pos = self.current_positions.get(vt_symbol, 0)

            bar = self.bars_dict.get(vt_symbol, [None])[-1]
            if not bar:
                continue

            # 计算目标持仓数量
            target_volume = int(target_value / bar.close_price)

            # 计算需要交易的数量
            diff = target_volume - current_pos

            if diff > 0:
                self.buy(vt_symbol, bar.close_price, abs(diff))
                self.write_log(f"买入: {vt_symbol}, 数量={abs(diff)}")
            elif diff < 0:
                self.sell(vt_symbol, bar.close_price, abs(diff))
                self.write_log(f"卖出: {vt_symbol}, 数量={abs(diff)}")

        # 更新界面
        self.put_event()

    def on_order(self, order):
        """委托回报"""
        self.write_log(f"委托回报: {order.vt_orderid}, 状态={order.status.value}")

    def on_trade(self, trade):
        """成交回报"""
        self.write_log(
            f"成交回报: {trade.vt_tradeid}, "
            f"品种={trade.vt_symbol}, "
            f"方向={trade.direction.value}, "
            f"数量={trade.volume}"
        )
