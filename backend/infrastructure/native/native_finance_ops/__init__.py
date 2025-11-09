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

from backend.infrastructure.native.logging_bridge import (
    NativeLogLevel,
    log_from_native,
    native_call_guard,
)

_COMPONENT_WRAPPER = "backend.native.finance_ops.wrapper"
_COMPONENT_FALLBACK = "backend.native.finance_ops.fallback"

try:
    from . import native_finance_ops as _native_finance_ops

    apply_price_adjustments_native = _native_finance_ops.apply_price_adjustments
    aggregate_daily_pnl_native = _native_finance_ops.aggregate_daily_pnl
    compute_return_metrics_native = _native_finance_ops.compute_return_metrics
    bucketize_period_native = _native_finance_ops.bucketize_period
    compute_period_statistics_native = _native_finance_ops.compute_period_statistics
    compute_risk_profile_native = _native_finance_ops.compute_risk_profile
    FINANCE_OPS_AVAILABLE = _native_finance_ops.FINANCE_OPS_AVAILABLE
    VERSION = _native_finance_ops.VERSION

    _AVAILABLE = True
    _ERROR = None

    @native_call_guard(component=_COMPONENT_WRAPPER)
    def apply_price_adjustments(*args, **kwargs):
        return apply_price_adjustments_native(*args, **kwargs)

    @native_call_guard(component=_COMPONENT_WRAPPER)
    def aggregate_daily_pnl(*args, **kwargs):
        return aggregate_daily_pnl_native(*args, **kwargs)

    @native_call_guard(component=_COMPONENT_WRAPPER)
    def compute_return_metrics(*args, **kwargs):
        return compute_return_metrics_native(*args, **kwargs)

    @native_call_guard(component=_COMPONENT_WRAPPER)
    def bucketize_period(*args, **kwargs):
        return bucketize_period_native(*args, **kwargs)

    @native_call_guard(component=_COMPONENT_WRAPPER)
    def compute_period_statistics(*args, **kwargs):
        return compute_period_statistics_native(*args, **kwargs)

    @native_call_guard(component=_COMPONENT_WRAPPER)
    def compute_risk_profile(*args, **kwargs):
        return compute_risk_profile_native(*args, **kwargs)

except ImportError as e:
    _AVAILABLE = False
    _ERROR = str(e)
    FINANCE_OPS_AVAILABLE = False
    VERSION = "0.0.0"

    log_from_native(
        NativeLogLevel.ERROR,
        _COMPONENT_FALLBACK,
        "import_native_finance_ops",
        0,
        "native_finance_ops extension not available; raising ImportError for callers",
        details=str(e),
    )

    # 提供降级函数
    def aggregate_daily_pnl(*args, **kwargs):
        raise ImportError(f"native_finance_ops not available: {_ERROR}")

    def compute_return_metrics(*args, **kwargs):
        raise ImportError(f"native_finance_ops not available: {_ERROR}")

    def bucketize_period(*args, **kwargs):
        raise ImportError(f"native_finance_ops not available: {_ERROR}")

    def compute_period_statistics(*args, **kwargs):
        raise ImportError(f"native_finance_ops not available: {_ERROR}")

    def compute_risk_profile(*args, **kwargs):
        raise ImportError(f"native_finance_ops not available: {_ERROR}")

    def apply_price_adjustments(*args, **kwargs):
        raise ImportError(f"native_finance_ops not available: {_ERROR}")


__all__ = [
    'apply_price_adjustments',
    'aggregate_daily_pnl',
    'compute_return_metrics',
    'bucketize_period',
    'compute_period_statistics',
    'compute_risk_profile',
    'FINANCE_OPS_AVAILABLE',
    'VERSION',
]


def is_available():
    """检查native_finance_ops是否可用"""
    return _AVAILABLE


def get_error():
    """获取导入错误信息"""
    return _ERROR
