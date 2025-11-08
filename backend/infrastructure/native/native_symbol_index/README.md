# -*- coding: utf-8 -*-
# native_symbol_index

提供针对股票品种的高性能索引构建能力：

- `build(records)`：构建 `code -> symbol` 与 `market -> codes` 索引
- `get_symbol(code)`：O(1) 查询品种详情
- `get_codes_by_market(market)`：快速获取指定市场下所有代码
- `all_codes()`：返回所有代码列表

## 构建

```powershell
cd backend/infrastructure/native/native_symbol_index
python setup.py build_ext --inplace
```

构建完成后即可通过 `backend.infrastructure.native.native_symbol_index` 导入。
若扩展不可用，模块会自动回退到纯 Python 实现。

> 推荐使用 `backend/infrastructure/native/compile_all.bat` 一键构建，脚本会按顺序编译全部扩展（含本模块），失败时暂停并输出错误日志。


