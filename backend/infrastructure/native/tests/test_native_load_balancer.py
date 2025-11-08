# -*- coding: utf-8 -*-
"""native_load_balancer 模块测试."""

import platform

import pytest

from backend.infrastructure.native.native_load_balancer import (
    LOAD_BALANCER_AVAILABLE,
    optimize,
)


WINDOWS = platform.system() == "Windows"


@pytest.mark.skipif(not (WINDOWS and LOAD_BALANCER_AVAILABLE), reason="native_load_balancer 扩展不可用")
def test_optimize_respects_server_and_task_constraints():
    result = optimize(
        bottleneck_value=85.0,
        queue_factor=0.6,
        base_processes=6,
        base_coroutines=800,
        max_processes=12,
        max_coroutines=2000,
        min_coroutines=10,
        total_max_connections=300,
        task_total_count=180,
    )

    processes = result["processes"]
    coroutines = result["coroutines_per_process"]
    total_concurrency = result["total_concurrency"]

    assert processes >= 1
    assert coroutines >= 1
    assert total_concurrency <= 300  # 服务器约束
    assert total_concurrency <= 180  # 任务约束
    assert result["server_constrained"] is True
    assert result["task_constrained"] is True


@pytest.mark.skipif(not (WINDOWS and LOAD_BALANCER_AVAILABLE), reason="native_load_balancer 扩展不可用")
def test_optimize_handles_no_constraints():
    result = optimize(
        bottleneck_value=20.0,
        queue_factor=1.0,
        base_processes=2,
        base_coroutines=50,
        max_processes=8,
        max_coroutines=400,
        min_coroutines=10,
        total_max_connections=10_000,
        task_total_count=0,
    )

    processes = result["processes"]
    coroutines = result["coroutines_per_process"]

    assert processes >= 1
    assert coroutines >= 10
    assert result["server_constrained"] is False
    assert result["task_constrained"] is False

