# -*- coding: utf-8 -*-
"""
native_finance_ops - 组合分析原生算子

提供高性能金融计算功能：
1. 日频盈亏聚合与累计曲线生成
2. 绩效指标计算（收益率、波动率、夏普、回撤等）
3. 周期分组（周/月/年）

使用方式：
```python
from backend.infrastructure.native.native_finance_ops import (
    aggregate_daily_pnl,
    compute_return_metrics,
    bucketize_period,
    FINANCE_OPS_AVAILABLE
)

# 聚合日频数据
dates = [20240101, 20240102, 20240103]
pnl = [100.0, -50.0, 200.0]
result = aggregate_daily_pnl(dates, pnl)
# result = {'dates': [...], 'daily_returns': [...], 'cumulative_equity': [...]}

# 计算绩效指标
metrics = compute_return_metrics(pnl_series, equity_series, trading_days_per_year=252)
# metrics = {'total_return': 0.15, 'sharpe_ratio': 1.5, 'max_drawdown': 0.08, ...}
```
"""

try:
    from .native_finance_ops import (
        aggregate_daily_pnl,
        compute_return_metrics,
        bucketize_period,
        FINANCE_OPS_AVAILABLE,
        VERSION
    )
    
    _AVAILABLE = True
    _ERROR = None
    
except ImportError as e:
    _AVAILABLE = False
    _ERROR = str(e)
    FINANCE_OPS_AVAILABLE = False
    
    # 提供降级函数
    def aggregate_daily_pnl(*args, **kwargs):
        raise ImportError(f"native_finance_ops not available: {_ERROR}")
    
    def compute_return_metrics(*args, **kwargs):
        raise ImportError(f"native_finance_ops not available: {_ERROR}")
    
    def bucketize_period(*args, **kwargs):
        raise ImportError(f"native_finance_ops not available: {_ERROR}")
    
    VERSION = "0.0.0"


__all__ = [
    'aggregate_daily_pnl',
    'compute_return_metrics',
    'bucketize_period',
    'FINANCE_OPS_AVAILABLE',
    'VERSION',
]


def is_available():
    """检查native_finance_ops是否可用"""
    return _AVAILABLE


def get_error():
    """获取导入错误信息"""
    return _ERROR
