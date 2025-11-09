# -*- coding: utf-8 -*-
r"""
单步调试 native_scheduler 的最小脚本。

使用方式：
1. 进入仓库根目录 `C:\Users\USER\Desktop\terminal_v0.50`。
2. 在命令行/VS 调试器中运行：
       python debug_native_scheduler.py
   若需强制原生实现，可取消下方的环境变量设置。
"""

from __future__ import annotations

import os
import time

# 根据需要选择是否强制 Python 回退
# os.environ["NATIVE_SCHEDULER_FORCE_NATIVE"] = "1"
# os.environ["NATIVE_SCHEDULER_FORCE_PY"] = "0"

from backend.infrastructure.native.native_scheduler import NativeScheduler, USING_NATIVE_CORE
from backend.infrastructure.native.native_threadpool import NativeThreadPool


def main() -> None:
    print("Using native core:", USING_NATIVE_CORE)

    scheduler = NativeScheduler(executor_factory=NativeThreadPool)
    scheduler.register_category("demo", queue_capacity=8, max_workers=2)

    results = []

    def task(x: int) -> int:
        print("task received:", x, type(x))
        results.append(x)
        time.sleep(0.01)
        try:
            return x * x
        except TypeError:
            return x

    futures = [scheduler.submit("demo", task, call_args=(i,)) for i in range(3)]
    values = [future.result(timeout=2.0) for future in futures]

    print("Task results:", values)
    print("Observed order:", results)
    print("Stats:", scheduler.stats())
    scheduler.shutdown()


if __name__ == "__main__":
    main()
