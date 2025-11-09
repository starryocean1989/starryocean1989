# -*- coding: utf-8 -*-
"""native_async 测试文件."""

import pytest
from typing import Dict, Any, List

from backend.infrastructure.native.native_async import reduce_task_results, ASYNC_REDUCE_AVAILABLE


class TestNativeAsync:
    """native_async 模块测试."""

    def test_async_available(self):
        """测试 ASYNC_REDUCE_AVAILABLE 状态."""
        assert isinstance(ASYNC_REDUCE_AVAILABLE, bool)

    def test_reduce_task_results_basic(self):
        """测试 reduce_task_results 基本功能."""
        # 成功的结果
        task_results = [
            ("AAPL", 150.0),
            ("GOOGL", 2500.0),
            ("MSFT", 300.0),
        ]

        result = reduce_task_results(task_results, total=3)

        assert isinstance(result, dict)
        assert "summary" in result
        assert "items" in result
        assert "errors" in result
        assert "error_symbols" in result
        assert "milestones" in result

        summary = result["summary"]
        assert summary["total"] == 3
        assert summary["success_count"] == 3
        assert summary["null_count"] == 0
        assert summary["error_count"] == 0

        items = result["items"]
        assert len(items) == 3
        assert items[0] == ("AAPL", 150.0)
        assert items[1] == ("GOOGL", 2500.0)
        assert items[2] == ("MSFT", 300.0)

    def test_reduce_task_results_with_errors(self):
        """测试包含错误的任务结果."""
        task_results = [
            ("AAPL", 150.0),
            ValueError("Network error"),
            ("MSFT", 300.0),
            ("GOOGL", Exception("Timeout")),
        ]

        result = reduce_task_results(task_results, total=4)

        summary = result["summary"]
        assert summary["total"] == 4
        assert summary["success_count"] == 2  # AAPL 和 MSFT
        assert summary["error_count"] == 2   # ValueError 和 Exception
        assert summary["null_count"] == 0

        errors = result["errors"]
        assert len(errors) == 2

        items = result["items"]
        assert len(items) == 4  # 所有任务都有对应项

    def test_reduce_task_results_with_nulls(self):
        """测试包含空值的任务结果."""
        task_results = [
            ("AAPL", 150.0),
            ("GOOGL", None),
            ("MSFT", 300.0),
        ]

        result = reduce_task_results(task_results, total=3)

        summary = result["summary"]
        assert summary["total"] == 3
        assert summary["success_count"] == 2
        assert summary["null_count"] == 1
        assert summary["error_count"] == 0

    def test_reduce_task_results_with_symbols(self):
        """测试使用外部symbols参数."""
        task_results = [
            150.0,  # 值
            2500.0,
            300.0,
        ]

        symbols = ["AAPL", "GOOGL", "MSFT"]
        result = reduce_task_results(task_results, total=3, symbols=symbols)

        items = result["items"]
        assert len(items) == 3
        assert items[0] == ("AAPL", 150.0)
        assert items[1] == ("GOOGL", 2500.0)
        assert items[2] == ("MSFT", 300.0)

    def test_reduce_task_results_progress_callback(self):
        """测试进度回调功能."""
        progress_calls = []

        def progress_callback(completed, total, symbol):
            progress_calls.append((completed, total, symbol))

        task_results = [
            ("AAPL", 150.0),
            ("GOOGL", 2500.0),
        ]

        result = reduce_task_results(
            task_results,
            total=2,
            progress_stride=1,
            progress_callback=progress_callback
        )

        # 验证进度回调被调用
        assert len(progress_calls) == 2
        assert progress_calls[0] == (1, 2, "AAPL")
        assert progress_calls[1] == (2, 2, "GOOGL")

    def test_reduce_task_results_milestones(self):
        """测试里程碑功能."""
        task_results = [
            ("AAPL", 150.0),
            ("GOOGL", 2500.0),
            ("MSFT", 300.0),
            ("TSLA", 800.0),
        ]

        result = reduce_task_results(task_results, total=4, progress_stride=2)

        milestones = result["milestones"]
        assert len(milestones) == 2  # 每2步一个里程碑
        # 第一个里程碑: 完成2个任务，2个成功
        assert milestones[0] == (2, 2, 0, 0)
        # 第二个里程碑: 完成4个任务，4个成功
        assert milestones[1] == (4, 4, 0, 0)

    def test_reduce_task_results_empty(self):
        """测试空任务结果."""
        result = reduce_task_results([], total=0)

        assert result["summary"]["total"] == 0
        assert result["summary"]["success_count"] == 0
        assert result["summary"]["null_count"] == 0
        assert result["summary"]["error_count"] == 0
        assert result["items"] == []
        assert result["errors"] == []
        assert result["milestones"] == []
