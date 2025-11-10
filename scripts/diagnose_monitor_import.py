import importlib
import traceback

MODULE = "backend.infrastructure.system_vnpy.monitor_toolkit"
print(f"[diagnose] importing {MODULE}...")
try:
    importlib.import_module(MODULE)
except SystemExit as exc:
    print(f"[diagnose] SystemExit intercepted: code={exc.code!r}")
    traceback.print_exc()
except BaseException as exc:  # noqa: BLE001
    print(f"[diagnose] exception: {type(exc).__name__}: {exc}")
    traceback.print_exc()
else:
    print("[diagnose] import succeeded")
