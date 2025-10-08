# -*- coding: utf-8 -*-
"""数据中心工具模块 - 常量定义."""

# 交易所选项
EXCHANGES = [
    "全部",
    "上交所",
    "深交所",
    "北交所",
    "中金所",
    "大商所",
    "郑商所",
    "上期所",
    "广期所",
]

# 品种类型选项
SYMBOL_TYPES = [
    "全部",
    "股票",
    "基金",
    "债券",
    "可转债",
    "期货",
    "期权",
    "指数",
]

# 筛选预设配置
FILTER_PRESETS = {
    "沪深A股": {"exchange": "上交所", "type": "股票"},
    "北证股票": {"exchange": "北交所", "type": "股票"},
    "可转债": {"exchange": "全部", "type": "可转债"},
    "T+0基金": {"exchange": "全部", "type": "基金"},
}

# 表格列标题
SYMBOLS_TABLE_HEADERS = ["品种代码", "品种名称", "交易所", "类型", "状态", "操作"]
LOCAL_DATA_TABLE_HEADERS = ["日期", "开盘价", "最高价", "最低价", "收盘价", "成交量", "成交额"]
DOWNLOAD_PROGRESS_TABLE_HEADERS = ["品种", "周期", "进度", "状态"]
SOURCES_TABLE_HEADERS = ["数据源", "类型", "状态", "连接数", "操作"]

# 默认分页大小选项
PAGE_SIZE_OPTIONS = ["20", "50", "100", "200"]
