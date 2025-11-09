"""native_calendar 扩展的统一导出."""

import logging
from typing import Any, Iterable, Optional

from backend.infrastructure.system_vnpy.logging_system import (
    LogType,
    bind_logger_defaults,
)

_logger = bind_logger_defaults(
    logging.getLogger("backend.native.calendar.wrapper"),
    log_type=LogType.SYSTEM.value,
    scenario="backend.native.calendar",
)

NATIVE_CALENDAR_AVAILABLE = False

try:
    from ._native_calendar import NativeCalendar  # type: ignore

    NATIVE_CALENDAR_AVAILABLE = True
    _logger.debug(
        "native_calendar extension loaded",
        extra={"native_module": "backend.native.calendar.core"},
    )
except ImportError:
    _logger.error(
        "native_calendar extension unavailable, calendar features disabled",
        extra={"native_module": "backend.native.calendar.core"},
    )

    class NativeCalendar:  # type: ignore
        """纯 Python 兜底实现，仅用于在扩展不可用时提供提示."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise RuntimeError(
                "native_calendar 扩展未编译，无法构建原生交易日历。"
                "请先运行 `compile_all.bat` 或安装已编译的 wheel。"
            )

        def is_trading_day(self, *_: Any, **__: Any) -> bool:
            raise RuntimeError("native_calendar 扩展未可用。")

        def get_trading_days(self, *_: Any, **__: Any) -> Iterable[str]:
            raise RuntimeError("native_calendar 扩展未可用。")

        def get_next_trading_day(self, *_: Any, **__: Any) -> Optional[str]:
            raise RuntimeError("native_calendar 扩展未可用。")


__all__ = ["NativeCalendar", "NATIVE_CALENDAR_AVAILABLE"]
