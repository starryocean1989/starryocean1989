# -*- coding: utf-8 -*-
# native_async

异步任务结果归约模块，负责在 C++ 层完成聚合统计：

- `reduce_task_results(task_results, total, progress_stride=0, progress_callback=None)`

返回值包含：

- `summary`: 统计信息（成功、失败、None 等数量）
- `items`: 标准化后的 `(symbol, value)` 列表
- `errors`: 错误详情（异常、回调失败等）
- `milestones`: 进度快照（达到指定步长时记录）

## 构建

```powershell
cd backend/infrastructure/native/native_async
python setup.py build_ext --inplace
```

构建失败时会自动回退到 Python 实现。

> 依赖 `pybind11`。推荐先在 `backend/infrastructure/native` 目录运行 `compile_all.bat`，脚本会逐一编译全部扩展（含本模块），遇到错误会暂停并打印日志。

