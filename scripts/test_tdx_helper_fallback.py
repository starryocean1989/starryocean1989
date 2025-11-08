import os
import sys
import logging
import importlib.util

# 确保项目根目录加入sys.path（脚本位于 scripts/ 子目录）
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _import_logging_system_from_file(project_root: str):
    path = os.path.join(project_root, "backend", "infrastructure", "system_vnpy", "logging_system.py")
    spec = importlib.util.spec_from_file_location("u_logging_system_fallback_test", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(mod)  # type: ignore
    return mod


def main():
    logging_system = _import_logging_system_from_file(PROJECT_ROOT)

    # 初始化统一日志系统：关闭有序队列，启用多进程以确保环境一致
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

    # 在root_logger上预置一个哨兵Handler，用于检测是否被清空
    root_logger = logging.getLogger()
    sentinel = logging.StreamHandler(sys.stdout)
    sentinel.setLevel(logging.DEBUG)
    sentinel.setFormatter(logging.Formatter("[SENTINEL] %(message)s"))
    root_logger.addHandler(sentinel)

    handlers_before = list(root_logger.handlers)

    # 确保环境变量中没有有效的队列token，从而触发tdx_asyncio回退逻辑
    os.environ.pop(logging_system.LOGGING_QUEUE_TOKEN_ENV, None)

    # 调用 tdx_asyncio 的回退配置函数
    from backend.infrastructure.tdx_asyncio.utils.helper import configure_subprocess_logging

    logger = configure_subprocess_logging(worker_id=1, task_type="helper_fallback_test", scenario="unit_test")
    logger.info("验证日志：tdx_asyncio回退逻辑不清空root handlers", extra={"log_type": "STAGE_NODE"})

    # 检查root handlers是否保留哨兵，以及数量不减少
    handlers_after = list(root_logger.handlers)
    sentinel_present = any(h is sentinel for h in handlers_after)

    print(f"handlers_before={len(handlers_before)}, handlers_after={len(handlers_after)}, sentinel_present={sentinel_present}")

    # 优雅停止多进程日志收集器，避免后台线程报错
    try:
        collector = logging_system.get_multi_process_collector()
        if collector:
            collector.stop()
    except Exception:
        pass

    if sentinel_present and len(handlers_after) >= len(handlers_before):
        print("[TEST] ✅ tdx_helper_fallback: root handlers 保持不变且未被清空")
        return 0
    else:
        print("[TEST] ❌ tdx_helper_fallback: root handlers 发生丢失或被清空")
        return 1


if __name__ == "__main__":
    sys.exit(main())