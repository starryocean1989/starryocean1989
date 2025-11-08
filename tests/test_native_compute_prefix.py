# -*- coding: utf-8 -*-
"""Tests for native_compute.prefix_sum_scale."""

import random
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.infrastructure.native.native_compute import (  # noqa: E402
    COMPUTE_AVAILABLE,
    PREFIX_SUM_AVAILABLE,
    batch_compute,
    batch_hash,
    batch_validate_iso_dates,
    batch_compare_dates,
    prefix_sum_scale,
)


@pytest.mark.skipif(
    not (COMPUTE_AVAILABLE and PREFIX_SUM_AVAILABLE),
    reason="prefix_sum_scale not available",
)
def test_prefix_sum_scale_matches_python_divide():
    random.seed(42)
    diffs = [random.randint(-500, 500) for _ in range(1024)]

    result = prefix_sum_scale(diffs, "divide")

    cumulative = []
    total = 0
    for value in diffs:
        total += value
        cumulative.append(total / 100.0)

    assert result == pytest.approx(cumulative)


@pytest.mark.skipif(
    not (COMPUTE_AVAILABLE and PREFIX_SUM_AVAILABLE),
    reason="prefix_sum_scale not available",
)
def test_prefix_sum_scale_supports_alternate_scales():
    diffs = [1000, 2000, -500, 750]

    by_1000 = prefix_sum_scale(diffs, "divide_by_1000")
    expected_1000 = []
    running = 0
    for diff in diffs:
        running += diff
        expected_1000.append(running / 1000.0)
    assert by_1000 == pytest.approx(expected_1000)

    custom = prefix_sum_scale(diffs, "scale", 256.0)
    expected_custom = []
    running = 0
    for diff in diffs:
        running += diff
        expected_custom.append(running / 256.0)
    assert custom == pytest.approx(expected_custom)


@pytest.mark.skipif(
    not (COMPUTE_AVAILABLE and PREFIX_SUM_AVAILABLE),
    reason="prefix_sum_scale not available",
)
def test_prefix_sum_scale_empty_input():
    assert prefix_sum_scale([], "divide") == []


@pytest.mark.skipif(not COMPUTE_AVAILABLE, reason="native_compute 不可用")
def test_batch_compute_supported_operations():
    values = [100, 200, 300]
    assert batch_compute(values, "divide_by_100") == pytest.approx([1.0, 2.0, 3.0])
    assert batch_compute(values, "divide_by_1000") == pytest.approx([0.1, 0.2, 0.3])
    assert batch_compute([1, 2, 3], "square") == [1.0, 4.0, 9.0]


@pytest.mark.skipif(not COMPUTE_AVAILABLE, reason="native_compute 不可用")
def test_batch_hash_returns_hex_strings():
    payload = [b"alpha", b"beta"]
    hashes = batch_hash(payload, "md5")
    assert all(isinstance(item, str) for item in hashes)
    assert len(hashes[0]) == 32


@pytest.mark.skipif(not COMPUTE_AVAILABLE, reason="native_compute 不可用")
def test_batch_validate_and_compare_dates():
    dates = ["2024-01-01", "invalid", None]
    validity = batch_validate_iso_dates(dates)
    assert validity == [True, False, False]

    comparisons = batch_compare_dates(["2024-01-01", "2024-01-10", "2023-12-31"], "2024-01-05")
    assert comparisons == [-1, 1, -1]
