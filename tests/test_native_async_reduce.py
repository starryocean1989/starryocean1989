# -*- coding: utf-8 -*-
from typing import List, Tuple

import pytest

import importlib

reduce_task_results = importlib.import_module(
    "backend.infrastructure.native.native_async"
).reduce_task_results


def test_reduce_task_results_basic():

    callback_calls: List[Tuple[int, int, str]] = []

    def progress_callback(current: int, total: int, message: str) -> None:
        callback_calls.append((current, total, message))

    task_results = [
        ("000001", "20210101"),
        ("000002", None),
        RuntimeError("network error"),
    ]
    symbols = ["000001", "000002", "000003"]

    payload = reduce_task_results(
        task_results,
        total=len(task_results),
        progress_stride=1,
        progress_callback=progress_callback,
        symbols=symbols,
    )

    summary = payload["summary"]
    assert summary["success_count"] == 1
    assert summary["null_count"] == 1
    assert summary["error_count"] == 1

    items = payload["items"]
    assert items == [("000001", "20210101"), ("000002", None)]

    error_symbols = payload["error_symbols"]
    assert error_symbols[-1] == "000003"

    assert callback_calls == [
        (1, 3, "000001"),
        (2, 3, "000002"),
    ]


