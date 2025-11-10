import importlib
import os
import traceback
import sys

module_name = "backend.infrastructure.system_vnpy.monitor_toolkit"
print(f"Importing {module_name}...")


def _trace_exit(code: int | None = None):
    print(f"sys.exit intercepted with code={code!r}")
    traceback.print_stack()
    raise SystemExit(code)


def _trace_os_exit(code: int = 0):
    print(f"os._exit intercepted with code={code!r}")
    traceback.print_stack()
    raise SystemExit(code)


sys.exit = _trace_exit  # type: ignore[assignment]
os._exit = _trace_os_exit  # type: ignore[assignment]
try:
    mod = importlib.import_module(module_name)
except BaseException as exc:  # noqa: BLE001
    print(f"Import failed with {type(exc).__name__}: {exc}")
    traceback.print_exc()
    if isinstance(exc, SystemExit):
        sys.exit(getattr(exc, "code", 1) or 1)
    sys.exit(1)
else:
    print("Import succeeded", mod)
    sys.exit(0)
