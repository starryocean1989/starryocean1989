import asyncio
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.infrastructure.data_module_vnpy.data_readers.data_readers import (
    AdjustableAsyncSemaphore,
    TdxDynamicExecutor,
)
from backend.infrastructure.data_module_vnpy.load_balancer.load_balancer import (
    LoadBalancer,
    TaskType,
)


@pytest.mark.asyncio
async def test_adjustable_semaphore_dynamic_limit():
    semaphore = AdjustableAsyncSemaphore(1)
    started = []
    finished = []
    release_guard = asyncio.Event()

    async def worker(idx: int):
        async with semaphore:
            started.append(idx)
            await release_guard.wait()
            finished.append(idx)

    tasks = [asyncio.create_task(worker(i)) for i in range(3)]

    await asyncio.sleep(0.05)
    assert started == [0]

    await semaphore.set_limit(2)
    await asyncio.sleep(0.05)
    assert set(started) == {0, 1}

    release_guard.set()
    await asyncio.gather(*tasks)
    assert set(finished) == {0, 1, 2}


@pytest.mark.asyncio
async def test_load_balancer_disk_queue_depth_mapping():
    LoadBalancer._instance = None  # type: ignore[attr-defined]
    lb = LoadBalancer(event_engine=None)

    metrics = {
        "system": {
            "cpu_percent": 40.0,
            "memory_percent": 35.0,
            "storage_subsystem": {
                "disks": {
                    "disk0": {"queue_depth": 1.5},
                    "disk1": {"queue_depth": 3.0},
                }
            },
        }
    }

    lb.metrics_monitor = SimpleNamespace(get_metrics=lambda force_realtime: metrics)
    lb.evaluator = SimpleNamespace(
        evaluate=lambda _: {
            "action": "hold",
            "adjustment": 0,
            "pressure_score": 42,
            "bottleneck": "balanced",
            "scale_factor": 1.0,
            "cpu_score": 0,
            "memory_score": 0,
            "disk_score": 0,
            "network_score": 0,
            "swap_active": False,
            "emergency": False,
            "reason": "test",
        }
    )
    lb.config_calculator = SimpleNamespace(
        calculate_for_task=lambda task, eval_result: {"max_workers": 1, "batch_size": 100}
    )

    class DummyTask:
        name = "dummy"

        def __init__(self):
            self.metrics = SimpleNamespace(task_type=TaskType.LOCAL_PROCESSING)

    try:
        config = lb.get_optimal_config_with_adjustment(DummyTask(), current_concurrency=4, processes=2)
    finally:
        LoadBalancer._instance = None  # type: ignore[attr-defined]

    assert config["disk_queue_depth"] == 3.0
    assert config["action"] == "hold"


@pytest.mark.asyncio
async def test_tdx_dynamic_executor_with_real_data():
    tdx_root = os.environ.get("TDX_DATA_ROOT")
    if not tdx_root:
        pytest.skip("TDX_DATA_ROOT is not configured")

    data_root = Path(tdx_root)
    day_dir = data_root / "vipdoc" / "sh" / "lday"
    if not day_dir.exists():
        pytest.skip("TDX day-line directory not found")

    symbols = [p.stem[2:] for p in sorted(day_dir.glob("sh*.day"))[:2]]
    if not symbols:
        pytest.skip("No TDX day-line files available")

    executor = TdxDynamicExecutor(data_root)
    results = await executor.execute_batch(
        symbols,
        data_type="day",
        market="sh",
        initial_processes=1,
        initial_coroutines=1,
    )

    assert len(results) == len(symbols)
    assert executor.adjustment_history
