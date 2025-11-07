import os
import sys
import time
import logging
import subprocess
import importlib.util

# 确保项目根目录加入sys.path（脚本位于 scripts/ 子目录）
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 统一测试日志
log = logging.getLogger(__name__)


def _import_logging_system_from_file(project_root: str):
    path = os.path.join(project_root, "backend", "infrastructure", "system_vnpy", "logging_system.py")
    spec = importlib.util.spec_from_file_location("u_logging_system_main", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def main():
    # 初始化统一日志系统：启用多进程收集器，关闭有序队列以便直接控制台输出
    logging_system = _import_logging_system_from_file(PROJECT_ROOT)

    hub = logging_system.setup_logging_system(
        event_engine=None,
        db_manager=None,
        enable_ordered_queue=False,
        enable_multi_process=True,
    )

    # 为LoggingHub设置控制台输出Handler，便于在测试中看到输出
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
    hub.set_console_handler(console_handler)

    collector = logging_system.get_multi_process_collector()
    if collector is None:
        log.error("[TEST] ❌ 未能获取MultiProcessLogCollector实例", extra={"log_type": "STAGE_NODE"})
        sys.exit(1)

    token = collector.get_bridge_token()
    if not token:
        log.error("[TEST] ❌ 未能生成日志队列token", extra={"log_type": "STAGE_NODE"})
        sys.exit(1)

    env = os.environ.copy()
    env[logging_system.LOGGING_QUEUE_TOKEN_ENV] = token

    child_script = os.path.join(os.path.dirname(__file__), "child_log.py")
    if not os.path.exists(child_script):
        log.error(f"[TEST] ❌ 子进程脚本不存在: {child_script}", extra={"log_type": "STAGE_NODE"})
        sys.exit(1)

    log.info("[TEST] ▶️ 启动子进程，进行日志桥接测试...", extra={"log_type": "STAGE_NODE"})
    proc = subprocess.Popen([sys.executable, child_script], env=env)
    try:
        ret = proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        log.error("[TEST] ❌ 子进程超时，已终止", extra={"log_type": "STAGE_NODE"})
        sys.exit(1)

    if ret != 0:
        log.error(f"[TEST] ❌ 子进程返回码异常: {ret}", extra={"log_type": "STAGE_NODE"})
        sys.exit(ret)

    # 给日志处理留少许时间
    time.sleep(0.5)
    log.info("[TEST] ✅ 日志桥接测试结束（请确认上述控制台已输出子进程 STAGE_NODE 日志）", extra={"log_type": "STAGE_NODE"})

    # 优雅停止多进程日志收集器，避免后台线程报错
    try:
        collector.stop()
    except Exception:
        pass


if __name__ == "__main__":
    main()