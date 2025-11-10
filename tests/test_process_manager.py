# -*- coding: utf-8 -*-
"""ProcessManager 单元测试."""

import asyncio
import pytest
from unittest.mock import MagicMock

from backend.startup.processes.manager import ProcessManager
from backend.startup.processes.spec import ProcessSpec, RestartPolicy
from backend.startup.processes.state import ProcessState


@pytest.fixture
async def manager():
    """创建 ProcessManager 实例."""
    return ProcessManager()


@pytest.fixture
def sample_spec():
    """创建示例进程规格."""
    async def dummy_start(runtime):
        runtime.handle.pid = 12345
        runtime.handle.process = MagicMock()
    
    async def dummy_stop(runtime):
        pass
    
    async def dummy_readiness(runtime):
        return True
    
    return ProcessSpec(
        name="test_process",
        start=dummy_start,
        stop=dummy_stop,
        readiness=dummy_readiness,
        restart_policy=RestartPolicy(max_retries=2, backoff_seconds=0.1),
    )


@pytest.mark.asyncio
async def test_register_process(manager, sample_spec):
    """测试进程注册."""
    await manager.register(sample_spec)
    
    assert "test_process" in manager._specs
    assert "test_process" in manager._handles
    assert manager.get_state("test_process") == ProcessState.CREATED


@pytest.mark.asyncio
async def test_register_duplicate_process(manager, sample_spec):
    """测试重复注册进程."""
    await manager.register(sample_spec)
    
    with pytest.raises(ValueError, match="already registered"):
        await manager.register(sample_spec)


@pytest.mark.asyncio
async def test_start_process(manager, sample_spec):
    """测试启动进程."""
    await manager.register(sample_spec)
    
    dummy_context = MagicMock()
    await manager.start("test_process", dummy_context)
    
    assert manager.get_state("test_process") == ProcessState.READY
    handle = manager.get_handle("test_process")
    assert handle.pid == 12345


@pytest.mark.asyncio
async def test_start_nonexistent_process(manager):
    """测试启动不存在的进程."""
    dummy_context = MagicMock()
    
    with pytest.raises(ValueError, match="not registered"):
        await manager.start("nonexistent", dummy_context)


@pytest.mark.asyncio
async def test_start_already_started_process(manager, sample_spec):
    """测试启动已启动的进程."""
    await manager.register(sample_spec)
    
    dummy_context = MagicMock()
    await manager.start("test_process", dummy_context)
    
    with pytest.raises(RuntimeError, match="already started"):
        await manager.start("test_process", dummy_context)


@pytest.mark.asyncio
async def test_stop_process(manager, sample_spec):
    """测试停止进程."""
    await manager.register(sample_spec)
    
    dummy_context = MagicMock()
    await manager.start("test_process", dummy_context)
    await manager.stop("test_process", dummy_context)
    
    assert manager.get_state("test_process") == ProcessState.STOPPED


@pytest.mark.asyncio
async def test_restart_process(manager, sample_spec):
    """测试重启进程."""
    await manager.register(sample_spec)
    
    dummy_context = MagicMock()
    await manager.start("test_process", dummy_context)
    await manager.restart("test_process", dummy_context)
    
    # 重启后应该回到 READY 状态
    assert manager.get_state("test_process") == ProcessState.READY


@pytest.mark.asyncio
async def test_mark_degraded_and_recovered(manager, sample_spec):
    """测试标记降级和恢复."""
    await manager.register(sample_spec)
    
    dummy_context = MagicMock()
    await manager.start("test_process", dummy_context)
    
    # 标记为降级
    await manager.mark_degraded("test_process", dummy_context)
    assert manager.get_state("test_process") == ProcessState.DEGRADED
    
    # 标记为恢复
    await manager.mark_recovered("test_process", dummy_context)
    assert manager.get_state("test_process") == ProcessState.READY


@pytest.mark.asyncio
async def test_start_all_with_dependencies(manager):
    """测试按依赖顺序启动所有进程."""
    # 创建两个有依赖关系的进程规格
    async def start_dep1(runtime):
        runtime.handle.pid = 1001
    
    async def start_dep2(runtime):
        runtime.handle.pid = 1002
    
    spec1 = ProcessSpec(
        name="dependency1",
        start=start_dep1,
    )
    
    spec2 = ProcessSpec(
        name="dependency2",
        start=start_dep2,
        dependencies=["dependency1"],
    )
    
    await manager.register(spec1)
    await manager.register(spec2)
    
    dummy_context = MagicMock()
    await manager.start_all(dummy_context)
    
    assert manager.get_state("dependency1") == ProcessState.READY
    assert manager.get_state("dependency2") == ProcessState.READY


@pytest.mark.asyncio
async def test_circular_dependency_detection(manager):
    """测试循环依赖检测."""
    async def dummy_start(runtime):
        pass
    
    spec1 = ProcessSpec(
        name="process1",
        start=dummy_start,
        dependencies=["process2"],
    )
    
    spec2 = ProcessSpec(
        name="process2",
        start=dummy_start,
        dependencies=["process1"],
    )
    
    await manager.register(spec1)
    await manager.register(spec2)
    
    dummy_context = MagicMock()
    
    with pytest.raises(ValueError, match="Circular dependency"):
        await manager.start_all(dummy_context)


@pytest.mark.asyncio
async def test_max_retries_exceeded(manager):
    """测试超过最大重试次数."""
    call_count = 0
    
    async def failing_start(runtime):
        nonlocal call_count
        call_count += 1
        raise RuntimeError("Start failed")
    
    spec = ProcessSpec(
        name="failing_process",
        start=failing_start,
        restart_policy=RestartPolicy(max_retries=2, backoff_seconds=0.01),
    )
    
    await manager.register(spec)
    
    dummy_context = MagicMock()
    await manager.start("failing_process", dummy_context)
    
    # 应该进入 FAILED 状态
    assert manager.get_state("failing_process") == ProcessState.FAILED
    assert call_count == 3  # 初始尝试 + 2 次重试


@pytest.mark.asyncio
async def test_state_change_callback(manager, sample_spec):
    """测试状态变更回调."""
    callback_calls = []
    
    async def state_callback(old_state, new_state):
        callback_calls.append((old_state, new_state))
    
    sample_spec.on_state_change = state_callback
    await manager.register(sample_spec)
    
    dummy_context = MagicMock()
    await manager.start("test_process", dummy_context)
    
    # 验证回调被调用
    assert len(callback_calls) >= 1
    assert callback_calls[0] == (ProcessState.CREATED, ProcessState.STARTING)


@pytest.mark.asyncio
async def test_readiness_probe_failure(manager):
    """测试就绪探针失败."""
    readiness_calls = []
    
    async def failing_readiness(runtime):
        nonlocal readiness_calls
        readiness_calls.append(True)
        return False  # 模拟就绪检查失败
    
    async def dummy_start(runtime):
        runtime.handle.pid = 12345
    
    spec = ProcessSpec(
        name="readiness_fail_process",
        start=dummy_start,
        readiness=failing_readiness,
    )
    
    await manager.register(spec)
    
    dummy_context = MagicMock()
    await manager.start("readiness_fail_process", dummy_context)
    
    # 等待就绪探针检查
    await asyncio.sleep(0.1)
    
    # 应该进入 DEGRADED 状态
    assert manager.get_state("readiness_fail_process") == ProcessState.DEGRADED
    assert len(readiness_calls) >= 1


@pytest.mark.asyncio
async def test_stop_all(manager):
    """测试停止所有进程."""
    async def dummy_start(runtime):
        runtime.handle.pid = 12345
    
    spec1 = ProcessSpec(name="process1", start=dummy_start)
    spec2 = ProcessSpec(name="process2", start=dummy_start)
    
    await manager.register(spec1)
    await manager.register(spec2)
    
    dummy_context = MagicMock()
    await manager.start_all(dummy_context)
    
    # 验证所有进程都已启动
    assert manager.get_state("process1") == ProcessState.READY
    assert manager.get_state("process2") == ProcessState.READY
    
    # 停止所有进程
    await manager.stop_all(dummy_context)
    
    # 验证所有进程都已停止
    assert manager.get_state("process1") == ProcessState.STOPPED
    assert manager.get_state("process2") == ProcessState.STOPPED
