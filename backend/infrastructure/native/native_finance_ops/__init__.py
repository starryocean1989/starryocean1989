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

from typing import TYPE_CHECKING

from backend.infrastructure.native.logging_bridge import (
    NativeLogLevel,
    log_from_native,
    native_call_guard,
)

if TYPE_CHECKING:
    try:
        from . import native_finance_ops as _native  # type: ignore
    except ImportError:
        pass

_COMPONENT_WRAPPER = "backend.native.finance_ops.wrapper"
_COMPONENT_FALLBACK = "backend.native.finance_ops.fallback"

# 尝试导入原生模块
try:
    from . import native_finance_ops as _native  # type: ignore
except ImportError as e:
    FINANCE_OPS_AVAILABLE = False
    VERSION = "0.0.0"
    __all__ = ["FINANCE_OPS_AVAILABLE", "VERSION"]

    log_from_native(
        NativeLogLevel.ERROR,
        _COMPONENT_FALLBACK,
        "import_native_finance_ops",
        0,
        "native_finance_ops extension not available; raising ImportError for callers",
        details=str(e),
    )

    def _raise_error():
        raise ImportError(f"native_finance_ops not available: {str(e)}")

    # 导出降级函数
    apply_price_adjustments = _raise_error  # type: ignore
    aggregate_daily_pnl = _raise_error  # type: ignore
    compute_return_metrics = _raise_error  # type: ignore
    bucketize_period = _raise_error  # type: ignore
    compute_period_statistics = _raise_error  # type: ignore
    compute_risk_profile = _raise_error  # type: ignore
else:
    # 原生模块可用，获取函数引用
    apply_price_adjustments = getattr(_native, "apply_price_adjustments", None)  # type: ignore
    aggregate_daily_pnl = getattr(_native, "aggregate_daily_pnl", None)  # type: ignore
    compute_return_metrics = getattr(_native, "compute_return_metrics", None)  # type: ignore
    bucketize_period = getattr(_native, "bucketize_period", None)  # type: ignore
    compute_period_statistics = getattr(_native, "compute_period_statistics", None)  # type: ignore
    compute_risk_profile = getattr(_native, "compute_risk_profile", None)  # type: ignore

    FINANCE_OPS_AVAILABLE = getattr(_native, "FINANCE_OPS_AVAILABLE", False)  # type: ignore
    VERSION = getattr(_native, "VERSION", "0.0.0")  # type: ignore

    # 验证核心函数是否可用
    essential_funcs = [
        apply_price_adjustments,
        aggregate_daily_pnl,
        compute_return_metrics,
        bucketize_period,
        compute_period_statistics,
        compute_risk_profile
    ]

    if not all(callable(func) for func in essential_funcs):
        log_from_native(
            NativeLogLevel.ERROR,
            _COMPONENT_FALLBACK,
            "validate_native_functions",
            0,
            "native_finance_ops extension missing core entrypoints",
            details="Some required functions are not available in the native module",
        )

        def _raise_error():
            raise ImportError("native_finance_ops extension missing core entrypoints")

        apply_price_adjustments = _raise_error  # type: ignore
        aggregate_daily_pnl = _raise_error  # type: ignore
        compute_return_metrics = _raise_error  # type: ignore
        bucketize_period = _raise_error  # type: ignore
        compute_period_statistics = _raise_error  # type: ignore
        compute_risk_profile = _raise_error  # type: ignore

        FINANCE_OPS_AVAILABLE = False

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
    return FINANCE_OPS_AVAILABLE


def get_error():
    """获取导入错误信息"""
    return "Check logs for import error details"
