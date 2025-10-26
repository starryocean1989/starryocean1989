
import logging
from pathlib import Path

# 确保logs目录存在
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)

# 创建专门的DEBUG日志记录器
debug_logger = logging.getLogger("SystemManager.DEBUG")
debug_logger.setLevel(logging.DEBUG)

# 清除旧的handler
for handler in debug_logger.handlers[:]:
    debug_logger.removeHandler(handler)

# 文件handler（DEBUG级别）
file_handler = logging.FileHandler("logs/systemmanager_debug.log", mode="w", encoding="utf-8")
file_handler.setLevel(logging.DEBUG)

# 格式化器
formatter = logging.Formatter(
    "%(asctime)s.%(msecs)03d - %(name)s - %(levelname)s - %(message)s",
    datefmt="%H:%M:%S"
)
file_handler.setFormatter(formatter)
debug_logger.addHandler(file_handler)

# 注入到SystemManager
import sys
sys.modules["__debug_logger__"] = debug_logger
print("[DEBUG] ✅ 调试日志已配置: logs/systemmanager_debug.log")
