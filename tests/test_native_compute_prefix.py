# -*- coding: utf-8 -*-
"""Tests for native_compute.prefix_sum_scale."""

import random

import pytest

from backend.infrastructure.native.native_compute import (
    COMPUTE_AVAILABLE,
    PREFIX_SUM_AVAILABLE,
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
