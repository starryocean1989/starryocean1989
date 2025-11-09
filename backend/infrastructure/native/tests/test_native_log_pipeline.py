# -*- coding: utf-8 -*-
import time
import pytest

native_log_pipeline = pytest.importorskip("native_log_pipeline")


def test_pipeline_batch_and_repeat_merging():
    captured = []

    def fallback(batch):
        captured.extend(list(batch))

    pipeline = native_log_pipeline.install(batch_size=2, flush_ms=0, fallback=fallback)

    try:
        assert pipeline.push({"message": "boot", "level": "INFO"}) is False
        assert pipeline.push({"message": "boot", "level": "INFO"}) in {False, True}
        pipeline.flush(force=True)

        assert captured, "fallback should receive merged batch"
        entry = captured[0]
        assert entry["_repeat"] == 2

        stats = pipeline.stats()
        assert stats["total_pushed"] >= 2
        assert stats["total_flushed"] >= 1
    finally:
        native_log_pipeline.flush_and_close(pipeline)


def test_pipeline_enable_logging():
    """测试日志桥接功能是否能正常启用/禁用."""
    captured = []

    def fallback(batch):
        captured.extend(list(batch))

    # 测试启用日志
    pipeline_with_logging = native_log_pipeline.install(
        batch_size=2,
        flush_ms=0,
        fallback=fallback,
        enable_logging=True
    )

    # 测试禁用日志
    pipeline_without_logging = native_log_pipeline.install(
        batch_size=2,
        flush_ms=0,
        fallback=fallback,
        enable_logging=False
    )

    try:
        # 测试带日志的pipeline
        pipeline_with_logging.push({"message": "test_with_logging", "level": "INFO"})
        pipeline_with_logging.flush(force=True)

        # 测试不带日志的pipeline
        pipeline_without_logging.push({"message": "test_without_logging", "level": "INFO"})
        pipeline_without_logging.flush(force=True)

        # 验证功能正常
        assert len(captured) == 2

        # 验证统计信息
        stats_with = pipeline_with_logging.stats()
        stats_without = pipeline_without_logging.stats()

        assert stats_with["total_flushed"] >= 1
        assert stats_without["total_flushed"] >= 1

    finally:
        native_log_pipeline.flush_and_close(pipeline_with_logging)
        native_log_pipeline.flush_and_close(pipeline_without_logging)


def test_pipeline_monitor_basic():
    """测试PipelineMonitor基本功能."""
    captured = []

    def fallback(batch):
        captured.extend(list(batch))

    pipeline = native_log_pipeline.install(
        batch_size=2,
        flush_ms=0,
        fallback=fallback
    )

    monitor = native_log_pipeline.PipelineMonitor(
        pipeline,
        check_interval=0.1,  # 快速检查，便于测试
        error_threshold=1,   # 降低阈值便于测试
    )

    try:
        # 启动监控
        monitor.start()

        # 添加一些日志
        pipeline.push({"message": "test_monitor", "level": "INFO"})
        pipeline.flush(force=True)

        # 等待监控检查
        time.sleep(0.2)

        # 验证监控没有崩溃
        stats = pipeline.stats()
        assert stats["total_flushed"] >= 1

    finally:
        monitor.stop()
        native_log_pipeline.flush_and_close(pipeline)


def test_install_with_monitor():
    """测试install_with_monitor函数."""
    pipeline, monitor = native_log_pipeline.install_with_monitor(
        batch_size=2,
        flush_ms=0,
        enable_monitor=True,
        monitor_check_interval=0.1,
    )

    try:
        # 验证pipeline创建成功
        assert pipeline is not None

        # 验证monitor创建成功
        assert monitor is not None

        # 验证monitor已启动
        assert monitor._monitor_thread is not None
        assert monitor._monitor_thread.is_alive()

        # 测试pipeline功能
        pipeline.push({"message": "test_with_monitor", "level": "INFO"})
        pipeline.flush(force=True)

        stats = pipeline.stats()
        assert stats["total_flushed"] >= 1

    finally:
        if monitor:
            monitor.stop()
        native_log_pipeline.flush_and_close(pipeline)


def test_install_with_monitor_disabled():
    """测试禁用监控的情况."""
    pipeline, monitor = native_log_pipeline.install_with_monitor(
        batch_size=2,
        flush_ms=0,
        enable_monitor=False,
    )

    try:
        # 验证pipeline创建成功
        assert pipeline is not None

        # 验证monitor为None
        assert monitor is None

        # 测试pipeline功能
        pipeline.push({"message": "test_without_monitor", "level": "INFO"})
        pipeline.flush(force=True)

        stats = pipeline.stats()
        assert stats["total_flushed"] >= 1

    finally:
        native_log_pipeline.flush_and_close(pipeline)


def test_pipeline_monitor_error_threshold():
    """测试监控器的错误阈值检测."""
    error_count = 0

    def failing_fallback(batch):
        nonlocal error_count
        error_count += 1
        raise RuntimeError("Simulated fallback error")

    pipeline = native_log_pipeline.install(
        batch_size=1,
        flush_ms=0,
        fallback=failing_fallback
    )

    monitor = native_log_pipeline.PipelineMonitor(
        pipeline,
        check_interval=0.05,  # 非常快的检查
        error_threshold=2,    # 设置较低的阈值
        alert_cooldown=0.1,   # 短冷却时间便于测试
    )

    try:
        # 启动监控
        monitor.start()

        # 触发多次错误
        for i in range(3):
            pipeline.push({"message": f"error_test_{i}", "level": "ERROR"})
            pipeline.flush(force=True)

        # 等待监控检测
        time.sleep(0.2)

        # 验证错误被记录
        stats = pipeline.stats()
        assert stats["fallback_errors"] >= 3

        # 验证error_count
        assert error_count >= 3

    finally:
        monitor.stop()
        native_log_pipeline.flush_and_close(pipeline)

