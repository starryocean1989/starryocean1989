# -*- coding: utf-8 -*-
# native_dataframe_ops 扩展

提供针对表格数据的批量算子，加速 DataFrame / ndarray 的聚合与转换。

## 功能概述

- `fast_fillna(frame, value)`：在 C 扩展层填充缺失值，避免 Python 循环。
- `normalize_numeric(frame, columns=None)`：对选定列进行向量化归一化。
- `rolling_apply(frame, window, func)`：高性能滑窗计算（回退版本调用 pandas）。
- 所有 API 均在扩展不可用时自动回退到 Python 实现，保证功能可用。

## 编译

```bash
cd backend/infrastructure/native/native_dataframe_ops
python setup.py build_ext --inplace
```

> 推荐在 `backend/infrastructure/native` 目录执行 `compile_all.bat`，脚本会顺序编译全部扩展（含本模块），遇到错误自动暂停便于排查。

## 测试

目前尚未纳入统一 `pytest` 套件，可根据业务需求编写自定义用例验证结果正确性。

## 依赖

- Windows 平台（Vista 及以上）。
- Python 3.8+，配套 Visual Studio Build Tools 与 Windows SDK。
- pandas / numpy（作为高层数据结构提供者）。


