# -*- coding: utf-8 -*-
"""代码片段管理器.

提供常用代码片段的快速插入：
- 预设片段库
- 自定义片段
- 片段变量替换
"""

from typing import Dict, List, Optional
from pathlib import Path
import json

from backend.core.utils import LoggerMixin


class SnippetManager(LoggerMixin):
    """代码片段管理器."""

    # 预设片段库
    DEFAULT_SNIPPETS = {
        # CTA策略模板
        "cta_strategy": {
            "prefix": "cta",
            "body": '''# -*- coding: utf-8 -*-
"""${1:策略名称}."""

from vnpy_ctastrategy import CtaTemplate
from vnpy.trader.object import BarData, TickData


class ${2:MyStrategy}(CtaTemplate):
    """${1:策略名称}."""
    
    author = "${3:作者名}"
    
    # 策略参数
    ${4:fast_window} = ${5:10}
    ${6:slow_window} = ${7:20}
    
    # 策略变量
    ${8:fast_ma} = 0.0
    ${9:slow_ma} = 0.0
    
    parameters = ["${4}", "${6}"]
    variables = ["${8}", "${9}"]
    
    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """初始化策略."""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)
    
    def on_init(self):
        """策略初始化回调."""
        self.write_log("策略初始化")
        self.load_bar(10)
    
    def on_start(self):
        """策略启动回调."""
        self.write_log("策略启动")
    
    def on_stop(self):
        """策略停止回调."""
        self.write_log("策略停止")
    
    def on_tick(self, tick: TickData):
        """Tick数据推送."""
        pass
    
    def on_bar(self, bar: BarData):
        """K线数据推送."""
        pass
''',
            "description": "CTA策略模板",
            "category": "策略模板",
        },
        # 算法交易策略模板
        "algo_strategy": {
            "prefix": "algo",
            "body": '''# -*- coding: utf-8 -*-
"""${1:算法策略名称}."""

from vnpy_algotrading import AlgoTemplate


class ${2:MyAlgoStrategy}(AlgoTemplate):
    """${1:算法策略名称}."""
    
    display_name = "${1}"
    
    default_setting = {}
    
    variables = []
    
    def __init__(self, algo_engine, algo_name, setting):
        """初始化算法."""
        super().__init__(algo_engine, algo_name, setting)
    
    def on_tick(self, tick):
        """Tick数据推送."""
        pass
    
    def on_order(self, order):
        """委托更新推送."""
        pass
    
    def on_trade(self, trade):
        """成交数据推送."""
        pass
    
    def on_timer(self):
        """定时器推送."""
        pass
    
    def on_stop(self):
        """算法停止."""
        pass
''',
            "description": "算法交易策略模板",
            "category": "策略模板",
        },
        # MACD指标计算
        "macd_indicator": {
            "prefix": "macd",
            "body": """# MACD指标计算
import talib

# 计算MACD
macd, signal, hist = talib.MACD(
    ${1:close_array},
    fastperiod=${2:12},
    slowperiod=${3:26},
    signalperiod=${4:9}
)

# 判断信号
if macd[-1] > signal[-1] and macd[-2] <= signal[-2]:
    # 金叉信号
    ${5:pass}
elif macd[-1] < signal[-1] and macd[-2] >= signal[-2]:
    # 死叉信号
    ${6:pass}
""",
            "description": "MACD指标计算",
            "category": "技术指标",
        },
        # 移动平均线
        "ma_indicator": {
            "prefix": "ma",
            "body": """# 移动平均线计算
import numpy as np

# 快速均线
fast_ma = np.mean(${1:close_array}[-${2:5}:])

# 慢速均线
slow_ma = np.mean(${1}[-${3:20}:])

# 均线交叉判断
if fast_ma > slow_ma:
    # 多头趋势
    ${4:pass}
elif fast_ma < slow_ma:
    # 空头趋势
    ${5:pass}
""",
            "description": "移动平均线计算",
            "category": "技术指标",
        },
        # ATR指标
        "atr_indicator": {
            "prefix": "atr",
            "body": """# ATR指标计算（平均真实波幅）
import talib

atr = talib.ATR(
    ${1:high_array},
    ${2:low_array},
    ${3:close_array},
    timeperiod=${4:14}
)

# ATR值
current_atr = atr[-1]

# 基于ATR设置止损
stop_loss = ${5:entry_price} - ${6:2} * current_atr
""",
            "description": "ATR指标计算",
            "category": "技术指标",
        },
        # 数据加载
        "load_data": {
            "prefix": "loaddata",
            "body": """# 加载历史数据
from datetime import datetime

start_date = datetime(${1:2024}, ${2:1}, ${3:1})
end_date = datetime(${4:2024}, ${5:12}, ${6:31})

# 加载K线数据
bars = self.load_bar(
    ${7:10},  # 加载天数
    ${8:Interval.MINUTE},  # 周期
    callback=${9:self.on_bar}  # 回调函数
)
""",
            "description": "加载历史数据",
            "category": "数据操作",
        },
        # 下单操作
        "place_order": {
            "prefix": "order",
            "body": """# 下单操作
# 买入开仓
vt_orderids = self.buy(
    price=${1:bar.close_price + 10},
    volume=${2:1},
    stop=${3:False},
    lock=${4:False}
)

# 卖出平仓
# vt_orderids = self.sell(
#     price=${5:bar.close_price - 10},
#     volume=${6:1},
#     stop=${7:False},
#     lock=${8:False}
# )

# 卖出开仓
# vt_orderids = self.short(
#     price=${9:bar.close_price - 10},
#     volume=${10:1},
#     stop=${11:False},
#     lock=${12:False}
# )

# 买入平仓
# vt_orderids = self.cover(
#     price=${13:bar.close_price + 10},
#     volume=${14:1},
#     stop=${15:False},
#     lock=${16:False}
# )
""",
            "description": "下单操作",
            "category": "交易操作",
        },
        # 仓位管理
        "position_management": {
            "prefix": "position",
            "body": """# 仓位管理
current_pos = self.pos

if current_pos == 0:
    # 空仓状态
    ${1:pass}
elif current_pos > 0:
    # 多头仓位
    ${2:pass}
elif current_pos < 0:
    # 空头仓位
    ${3:pass}

# 获取目标仓位
target_pos = ${4:1}

# 计算需要交易的数量
trade_volume = target_pos - current_pos

if trade_volume > 0:
    # 需要买入
    self.buy(${5:price}, abs(trade_volume))
elif trade_volume < 0:
    # 需要卖出
    self.sell(${6:price}, abs(trade_volume))
""",
            "description": "仓位管理",
            "category": "交易操作",
        },
        # 日志记录
        "log": {
            "prefix": "log",
            "body": 'self.write_log("${1:日志消息}")',
            "description": "记录日志",
            "category": "工具函数",
        },
        # 异常处理
        "try_except": {
            "prefix": "try",
            "body": """try:
    ${1:pass}
except ${2:Exception} as e:
    self.write_log(f"错误: {str(e)}")
    ${3:pass}
""",
            "description": "异常处理",
            "category": "工具函数",
        },
    }

    def __init__(self):
        """初始化片段管理器."""
        # 片段库
        self.snippets: Dict[str, Dict] = {}

        # 配置文件路径
        self.config_file = Path("config/snippets.json")

        # 加载片段
        self._load_snippets()

        self.logger.info(f"代码片段管理器初始化完成，共 {len(self.snippets)} 个片段")

    def _load_snippets(self):
        """加载片段."""
        # 先加载默认片段
        self.snippets = self.DEFAULT_SNIPPETS.copy()

        # 如果存在自定义片段，加载并合并
        if self.config_file.exists():
            try:
                with open(self.config_file, "r", encoding="utf-8") as f:
                    custom_snippets = json.load(f)

                # 合并自定义片段
                self.snippets.update(custom_snippets)

                self.logger.info(f"自定义片段已加载: {len(custom_snippets)} 个")

            except Exception as e:
                self.logger.error(f"加载自定义片段失败: {e}")

    def get_snippet(self, snippet_id: str) -> Optional[str]:
        """获取片段内容.

        Args:
            snippet_id: 片段ID

        Returns:
            Optional[str]: 片段内容
        """
        snippet = self.snippets.get(snippet_id)
        if snippet:
            return snippet["body"]
        return None

    def get_snippet_by_prefix(self, prefix: str) -> Optional[str]:
        """根据前缀获取片段.

        Args:
            prefix: 前缀

        Returns:
            Optional[str]: 片段内容
        """
        for snippet_id, snippet in self.snippets.items():
            if snippet.get("prefix") == prefix:
                return snippet["body"]
        return None

    def get_all_snippets(self) -> Dict[str, Dict]:
        """获取所有片段.

        Returns:
            Dict: 所有片段
        """
        return self.snippets.copy()

    def get_snippets_by_category(self, category: str) -> Dict[str, Dict]:
        """根据分类获取片段.

        Args:
            category: 分类名称

        Returns:
            Dict: 该分类的所有片段
        """
        return {
            snippet_id: snippet
            for snippet_id, snippet in self.snippets.items()
            if snippet.get("category") == category
        }

    def get_categories(self) -> List[str]:
        """获取所有分类.

        Returns:
            List[str]: 分类列表
        """
        categories = set()
        for snippet in self.snippets.values():
            if "category" in snippet:
                categories.add(snippet["category"])
        return sorted(list(categories))

    def add_snippet(
        self,
        snippet_id: str,
        prefix: str,
        body: str,
        description: str = "",
        category: str = "自定义",
    ):
        """添加自定义片段.

        Args:
            snippet_id: 片段ID
            prefix: 前缀（触发词）
            body: 片段内容
            description: 描述
            category: 分类
        """
        self.snippets[snippet_id] = {
            "prefix": prefix,
            "body": body,
            "description": description,
            "category": category,
        }

        # 保存到配置
        self._save_custom_snippets()

        self.logger.info(f"添加片段: {snippet_id}")

    def remove_snippet(self, snippet_id: str):
        """移除片段.

        Args:
            snippet_id: 片段ID
        """
        if snippet_id in self.snippets:
            # 不能删除默认片段
            if snippet_id in self.DEFAULT_SNIPPETS:
                self.logger.warning(f"不能删除默认片段: {snippet_id}")
                return

            del self.snippets[snippet_id]

            # 保存配置
            self._save_custom_snippets()

            self.logger.info(f"移除片段: {snippet_id}")

    def replace_variables(self, snippet_body: str, variables: Dict[str, str]) -> str:
        """替换片段中的变量.

        Args:
            snippet_body: 片段内容
            variables: 变量映射 {占位符: 值}

        Returns:
            str: 替换后的内容
        """
        result = snippet_body

        # 替换所有变量
        for placeholder, value in variables.items():
            result = result.replace(placeholder, value)

        return result

    def _save_custom_snippets(self):
        """保存自定义片段."""
        try:
            # 确保配置目录存在
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

            # 只保存自定义片段（不在默认片段中的）
            custom_snippets = {
                snippet_id: snippet
                for snippet_id, snippet in self.snippets.items()
                if snippet_id not in self.DEFAULT_SNIPPETS
            }

            # 保存到文件
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(custom_snippets, f, indent=2, ensure_ascii=False)

            self.logger.info(f"自定义片段已保存: {len(custom_snippets)} 个")

        except Exception as e:
            self.logger.error(f"保存自定义片段失败: {e}")
