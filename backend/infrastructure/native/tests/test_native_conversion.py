# -*- coding: utf-8 -*-
from __future__ import annotations

import pytest

conversion = pytest.importorskip("backend.infrastructure.native.native_conversion")


@pytest.mark.skipif(
    not conversion.CONVERSION_AVAILABLE,
    reason="native_conversion 扩展不可用",
)
def test_batch_convert_basic_types():
    numbers = ["1", "2", "3", "4"]
    converted = conversion.batch_convert(numbers, "int")
    assert converted == [1, 2, 3, 4]

    floats = conversion.batch_convert(numbers, "float")
    assert floats == pytest.approx([1.0, 2.0, 3.0, 4.0])

    strings = conversion.batch_convert([1, 2, 3], "str")
    assert strings == ["1", "2", "3"]


@pytest.mark.skipif(
    not conversion.CONVERSION_AVAILABLE,
    reason="native_conversion 扩展不可用",
)
def test_batch_encode_decode_symmetry():
    payload = ["中文", "test", "😀"]
    encoded = conversion.batch_encode(payload, encoding="utf-8")
    assert all(isinstance(item, (bytes, bytearray)) for item in encoded)

    decoded = conversion.batch_decode(encoded, encoding="utf-8")
    assert decoded == payload

