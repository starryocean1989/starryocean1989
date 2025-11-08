# -*- coding: utf-8 -*-
# native_indicator 原生技术指标扩展

提供 SMA/EMA/MACD/RSI 等常用技术指标的高性能实现，完全依赖 `native_indicator_core`
扩展计算；若扩展不可用，需要调用方自行降级（例如回退到 `talib`）。

## 功能特性

- `sma(closes, period=5)`：简单移动平均
- `ema(closes, period=5)`：指数移动平均
- `macd(closes, fast=12, slow=26, signal=9)`：MACD 指标，返回 `macd/signal/hist`
- `rsi(closes, period=14)`：相对强弱指标
- `calculate_indicator(name, closes, **kwargs)`：统一入口
- `calculate_indicator_batch(name, datasets, **kwargs)`：批量计算

## 构建

```powershell
cd backend/infrastructure/native/native_indicator
python setup.py build_ext --inplace
```

> 如需强制启用 AVX2，可设置环境变量 `ENABLE_NATIVE_INDATOR_AVX2=1`

也可以使用统一脚本：

```powershell
cd backend/infrastructure/native
.\compile_all.bat
```

## Python API

```python
from backend.infrastructure.native import native_indicator
from backend.infrastructure.native.native_indicator import calculate_indicator

values = [1.0, 2.0, 3.0, 4.0, 5.0]

rsi = calculate_indicator("RSI", values, period=14)
macd = calculate_indicator("MACD", values, fast=12, slow=26, signal=9)
```

## 测试

```powershell
pytest tests/test_native_indicator.py
pytest tests/test_native_indicator_performance.py  # 设置 RUN_NATIVE_INDICATOR_PERF=1 才会执行
```

性能测试输出平均耗时与提升比，可与其他实现进行对比评估。


