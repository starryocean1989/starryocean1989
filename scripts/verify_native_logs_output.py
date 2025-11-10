#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
验证 backend/infrastructure/native 内埋点的日志是否正确输出到 logs 目录。

步骤：
1) 动态注入轻量级 vnpy 兼容桩，避免依赖真实 vnpy。
2) 初始化统一日志系统（LoggingHub + EventLogFileHandler）。
3) 安装 native 日志桥接（logging_bridge）。
4) 直接调用 log_from_native 输出多条示例日志。
5) 结束事件流程并读取日志文件内容，打印关键信息。

该脚本不依赖 C 扩展实际编译，可在本地环境快速验证日志落盘。
"""

from __future__ import annotations

import sys
import os
import types
import logging
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _install_vnpy_stub() -> None:
    """为 logging_system 注入最小化的 vnpy 兼容桩。"""
    if 'vnpy' in sys.modules and 'vnpy.event' in sys.modules:
        return

    vnpy = types.ModuleType('vnpy')
    vnpy_event = types.ModuleType('vnpy.event')

    class Event:  # 最小事件类型，占位即可
        def __init__(self, type_: str, data: Any | None = None) -> None:
            self.type = type_
            self.data = data

    class EventEngine:  # 最小事件引擎，占位即可
        def __init__(self) -> None:
            self._started = False

        def start(self) -> None:
            self._started = True

        def stop(self) -> None:
            self._started = False

        def put(self, event: Event) -> None:  # noqa: D401
            # 轻量化：不做任何事，仅兼容接口
            pass

    vnpy_event.Event = Event  # type: ignore
    vnpy_event.EventEngine = EventEngine  # type: ignore

    vnpy.event = vnpy_event  # type: ignore

    sys.modules['vnpy'] = vnpy
    sys.modules['vnpy.event'] = vnpy_event


def ensure_logs_dir() -> Path:
    logs_dir = PROJECT_ROOT / 'logs'
    logs_dir.mkdir(parents=True, exist_ok=True)
    return logs_dir


def main() -> int:
    # 1) 安装 vnpy 兼容桩
    _install_vnpy_stub()

    # 2) 初始化统一日志系统
    from backend.infrastructure.system_vnpy.logging_system import (
        setup_logging_system,
        start_event_process,
        end_event_process,
    )

    from vnpy.event import EventEngine

    # 确保 logs 目录存在
    ensure_logs_dir()

    # 初始化 LoggingHub（关闭有序队列与多进程以简化本地验证）
    hub = setup_logging_system(
        event_engine=EventEngine(),
        db_manager=None,
        enable_ordered_queue=False,
        enable_multi_process=False,
    )
    hub.setLevel(logging.DEBUG)

    # 3) 开启事件日志流程（application_startup）
    event_file = start_event_process('application_startup', metadata={
        'verifier': 'verify_native_logs_output.py',
        'purpose': 'native logging bridge verification',
    })

    # 4) 安装并触发原生日志桥接
    from backend.infrastructure.native.logging_bridge import (
        install_native_logging_bridge,
        log_from_native,
        NativeLogLevel,
    )

    install_native_logging_bridge()

    # 触发多条示例日志（不同等级）
    samples = [
        (NativeLogLevel.DEBUG,   'native.threadpool',    'init_pool',     12,  '线程池初始化'),
        (NativeLogLevel.INFO,    'native.conversion',    'convert_batch', 88,  '批量转换完成'),
        (NativeLogLevel.WARNING, 'native.ipc',           'open_pipe',     33,  '命名管道连接重试'),
        (NativeLogLevel.ERROR,   'native.iocp',          'async_read',    47,  '异步读取失败'),
        (NativeLogLevel.CRITICAL,'native.log_pipeline',  'flush',         21,  '日志批量刷新致命错误'),
    ]

    for lvl, comp, func, line, msg in samples:
        log_from_native(level=lvl, component=comp, function=func, line=line, message=msg, details='verification')

    # 5) 结束事件并读取日志文件，打印摘要
    end_event_process(success=True, summary='native bridge verification complete')

    # 打印输出位置与示例内容
    print(f"\n✅ 日志文件已生成: {event_file}")
    if Path(event_file).exists():
        try:
            # 读取最后若干行，便于查看
            content = Path(event_file).read_text(encoding='utf-8', errors='ignore')
            lines = content.splitlines()
            tail = lines[-20:] if len(lines) > 20 else lines
            print("\n—— 日志文件尾部示例（最多20行）——")
            for line in tail:
                print(line)
        except Exception as exc:
            print(f"⚠️  读取日志文件失败: {exc}")
    else:
        print("❌ 未找到事件日志文件，请检查EventLogFileHandler注入")

    # 额外：打印当前目录下所有日志文件
    logs_dir = PROJECT_ROOT / 'logs'
    print("\n—— 当前logs目录文件 ——")
    for p in sorted(logs_dir.glob('*.log')):
        print(f"- {p.name}")

    return 0


if __name__ == '__main__':
    raise SystemExit(main())

