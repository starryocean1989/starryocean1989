# -*- coding: utf-8 -*-
# native_finance_ops 扩展

金融指标批处理扩展，覆盖波动率、夏普比率、收益回撤等常用量化指标；在扩展缺失时自动回退 Python 版本。

## 功能概述

- `calc_sharpe(returns, risk_free=0.0)`：日度收益到夏普比率的高性能计算。
- `calc_max_drawdown(nav_series)`：原生循环求取最大回撤，减少 Python 迭代开销。
- `batch_volatility(returns, window)`：批量滑窗波动率统计。
- `finance_metrics.summarize(portfolio)`：一次性返回收益、波动、回撤等聚合信息。
- `compute_period_statistics(dates, pnl, initial_equity=1_000_000)`：原生聚合日/周/月维度统计并输出权益曲线与关键指标。
- `compute_risk_profile(returns, scale, confidence_levels=(0.95, 0.99))`：原生计算 VaR/CVaR、夏普、索提诺、最大回撤等风险画像。

## 编译

```bash
cd backend/infrastructure/native/native_finance_ops
python setup.py build_ext --inplace
```

> 建议在 `backend/infrastructure/native` 目录运行 `compile_all.bat`，脚本会顺序构建全部扩展（含本模块），失败时暂停并输出详细日志。

## 测试

```bash
pytest backend/infrastructure/native/native_finance_ops/test_finance_ops.py -v
```

## 依赖

- Windows 平台、Python 3.8+。
- Visual Studio Build Tools、Windows SDK。
- numpy（作为输入向量容器）。


