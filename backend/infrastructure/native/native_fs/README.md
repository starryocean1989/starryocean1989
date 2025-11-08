# -*- coding: utf-8 -*-
# native_fs 模块

`native_fs` 提供 Windows 平台下基于 `ReadDirectoryChangesW` + Overlapped I/O 的高性能目录监控能力。

## 功能特性

- ✅ **零轮询**：使用操作系统事件通知，文件变更可在毫秒级送达到 Python 层。
- ✅ **递归监控**：支持对目录树的递归监控。
- ✅ **线程安全回调**：事件由后台原生线程捕获，通过 GIL 安全回调至 Python。
- ✅ **可降级**：扩展缺失时 `FS_WATCH_AVAILABLE=False`，调用方可自动回退至 Python 轮询方案。

## API

```python
from backend.infrastructure.native.native_fs import watch_directory

def on_event(event: dict) -> None:
    print(event)

watcher = watch_directory(
    r"C:\data\kline",
    on_event,
    recursive=True,
    buffer_size=128 * 1024,
)
```

事件字典包含：

- `event`: 事件类别（`created`/`deleted`/`modified`/`renamed_old`/`renamed_new`）
- `name`: 相对路径（相对 watch_directory 传入路径）
- `timestamp_ms`: 事件生成时的系统毫秒时间戳

退出时调用 `watcher.stop()` 或使用上下文管理器：

```python
with watch_directory(path, on_event) as watcher:
    ...
```

## 编译

```powershell
cd backend/infrastructure/native/native_fs
python setup.py build_ext --inplace
```

建议通过 `backend/infrastructure/native/compile_all.bat` 一键构建。


