# -*- coding: utf-8 -*-
"""pytest配置 - native扩展测试."""

from __future__ import annotations

import enum
import logging
import sys
import types
from pathlib import Path
from typing import Any, cast

# 将项目根目录添加到sys.path以便导入backend模块
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# 将native目录添加到sys.path以便直接导入native模块
_NATIVE_DIR = Path(__file__).resolve().parent.parent
if str(_NATIVE_DIR) not in sys.path:
    sys.path.insert(0, str(_NATIVE_DIR))

try:
    import backend.infrastructure.system_vnpy.logging_system  # noqa: F401
except ModuleNotFoundError as exc:
    if exc.name != "vnpy":
        raise

    fallback_module = types.ModuleType(
        "backend.infrastructure.system_vnpy.logging_system"
    )

    class LogType(enum.Enum):
        SYSTEM = "system"

    def bind_logger_defaults(
        logger: logging.Logger,
        *,
        log_type: str = "SYSTEM",
        scenario: str | None = None,
    ) -> logging.Logger:
        def _prepare_extra(extra: dict | None) -> dict:
            base = dict(extra) if isinstance(extra, dict) else {}
            base.setdefault("log_type", log_type)
            if scenario and "scenario" not in base:
                base["scenario"] = scenario
            return base

        def _wrap(method_name: str, expects_level: bool = False):
            original = getattr(logger, method_name, None)
            if original is None:
                return None

            if expects_level:
                def wrapper_with_level(level, msg, *args, **kwargs):
                    kwargs["extra"] = _prepare_extra(kwargs.get("extra"))
                    return original(level, msg, *args, **kwargs)
                return wrapper_with_level
            else:
                def wrapper_without_level(msg, *args, **kwargs):
                    kwargs["extra"] = _prepare_extra(kwargs.get("extra"))
                    return original(msg, *args, **kwargs)
                return wrapper_without_level

        for name in ("debug", "info", "warning", "error", "critical", "exception"):
            wrapped = _wrap(name)
            if wrapped is not None:
                setattr(logger, name, wrapped)

        wrapped_log = _wrap("log", expects_level=True)
        if wrapped_log is not None:
            setattr(logger, "log", wrapped_log)

        return logger

    fallback_module = cast(Any, fallback_module)
    fallback_module.LogType = LogType
    fallback_module.bind_logger_defaults = bind_logger_defaults
    fallback_module.__all__ = ["LogType", "bind_logger_defaults"]
    sys.modules["backend.infrastructure.system_vnpy.logging_system"] = fallback_module

