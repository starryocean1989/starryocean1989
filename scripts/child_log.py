import logging
import sys
import time
import os
import importlib.util


def _import_logging_system_from_file(project_root: str):
    path = os.path.join(project_root, "backend", "infrastructure", "system_vnpy", "logging_system.py")
    spec = importlib.util.spec_from_file_location("u_logging_system_child", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def main():
    # 直接从文件加载 logging_system，避免包的 __init__ 副作用
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    logging_system = _import_logging_system_from_file(project_root)

    # 从环境变量恢复队列并配置QueueHandler（跨进程回传）
    queue_proxy = logging_system.load_queue_from_env()
    if queue_proxy:
        logging_system.setup_subprocess_logging(queue_proxy)

    # 发送一个 STAGE_NODE 日志，确保在控制台可见（根据路由规则）
    logger = logging.getLogger("subprocess.test_bridge.worker1")
    logger.info(
        "📍 子进程日志桥接测试：已发送 STAGE_NODE",
        extra={"log_type": "STAGE_NODE", "scenario": "bridge_test"},
    )

    # 发送一个 SYSTEM 日志（不一定显示在控制台，但应被Hub处理）
    logger.info(
        "子进程日志桥接测试：SYSTEM 日志",
        extra={"log_type": "SYSTEM", "scenario": "bridge_test"},
    )

    time.sleep(0.2)
    return 0


if __name__ == "__main__":
    sys.exit(main())