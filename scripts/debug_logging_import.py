import sys
import traceback
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

try:
    import backend.infrastructure.system_vnpy.logging_system  # noqa: F401
    print("logging_system imported successfully")
except Exception as exc:
    print(f"logging_system import failed: {exc}")
    traceback.print_exc()
