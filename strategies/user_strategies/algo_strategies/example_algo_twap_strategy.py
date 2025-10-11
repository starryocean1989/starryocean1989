# -*- coding: utf-8 -*-
"""
TWAP算法交易策略示例

TWAP (Time Weighted Average Price) 时间加权平均价格算法
将大单拆分成多个小单，在指定时间段内均匀执行，降低市场冲击

作者: VnPy团队
"""

from vnpy_algotrading import AlgoTemplate
from vnpy.trader.object import TickData, OrderData, TradeData
from vnpy.trader.constant import Direction, Offset


class TwapAlgoStrategy(AlgoTemplate):
    """TWAP算法交易策略"""

    # 策略作者
    author = "VnPy团队"

    # 策略参数
    target_volume = 100  # 目标成交数量
    time_interval = 60  # 时间间隔（秒）
    order_volume = 10  # 每次下单数量

    # 策略变量
    traded_volume = 0  # 已成交数量
    order_count = 0  # 下单次数
    timer_count = 0  # 定时器计数

    # 参数列表
    parameters = ["target_volume", "time_interval", "order_volume"]

    # 变量列表
    variables = ["traded_volume", "order_count", "timer_count"]

    def __init__(self, algo_engine, algo_name, vt_symbol, setting):
        """构造函数"""
        super().__init__(algo_engine, algo_name, vt_symbol, setting)

    def on_init(self):
        """算法初始化"""
        self.write_log("TWAP算法初始化")

    def on_start(self):
        """算法启动"""
        self.write_log("TWAP算法启动")
        # 启动定时器
        self.start_timer(self.time_interval)

    def on_stop(self):
        """算法停止"""
        self.write_log("TWAP算法停止")
        # 停止定时器
        self.stop_timer()
        # 撤销所有委托
        self.cancel_all()

    def on_tick(self, tick: TickData):
        """行情推送"""
        pass

    def on_timer(self):
        """定时器触发"""
        self.timer_count += 1

        # 检查是否完成
        if self.traded_volume >= self.target_volume:
            self.write_log(f"TWAP算法完成，总成交: {self.traded_volume}")
            self.stop()
            return

        # 计算本次下单数量
        remaining = self.target_volume - self.traded_volume
        volume = min(self.order_volume, remaining)

        # 获取最新行情
        tick = self.get_tick()
        if not tick:
            self.write_log("获取行情失败")
            return

        # 以对手价下单
        price = tick.ask_price_1  # 使用卖一价买入
        orderids = self.buy(price, volume)

        self.order_count += 1
        self.write_log(f"第{self.order_count}次下单: 价格={price}, 数量={volume}")

    def on_order(self, order: OrderData):
        """委托回报"""
        self.write_log(f"委托回报: {order.vt_orderid}, 状态={order.status.value}")

    def on_trade(self, trade: TradeData):
        """成交回报"""
        self.traded_volume += trade.volume
        self.write_log(
            f"成交回报: {trade.vt_tradeid}, "
            f"数量={trade.volume}, "
            f"累计={self.traded_volume}/{self.target_volume}"
        )

        # 更新界面
        self.put_event()
