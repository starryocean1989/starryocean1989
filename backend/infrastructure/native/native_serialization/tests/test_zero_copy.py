# -*- coding: utf-8 -*-
"""zero_copy_serialize 单元测试."""

from __future__ import annotations

import platform

import pandas as pd
import pytest

from backend.infrastructure.native.native_serialization import (
    SERIALIZATION_AVAILABLE,
    zero_copy_serialize,
)
from backend.infrastructure.data_module_vnpy.arrow_utils import (
    ARROW_AVAILABLE,
    arrow_bytes_to_dataframe,
)


WINDOWS = platform.system() == "Windows"


@pytest.mark.skipif(
    not (WINDOWS and SERIALIZATION_AVAILABLE and ARROW_AVAILABLE),
    reason="native serialization 或 pyarrow 不可用",
)
def test_zero_copy_dataframe_returns_memoryview_roundtrip():
    df = pd.DataFrame(
        {
            "open": [1.1, 2.2],
            "close": [1.3, 2.4],
            "symbol": ["000001", "000002"],
        },
        index=pd.to_datetime(["2024-01-01", "2024-01-02"], utc=True),
    )
    df.index.name = "datetime"

    payload = zero_copy_serialize(df)

    assert isinstance(payload, memoryview)
    assert payload.readonly is True
    restored = arrow_bytes_to_dataframe(payload.tobytes())
    pd.testing.assert_frame_equal(restored, df)


@pytest.mark.skipif(not (WINDOWS and SERIALIZATION_AVAILABLE), reason="native serialization 不可用")
def test_zero_copy_passthrough_for_bytes():
    data = b"test-bytes"
    serialized = zero_copy_serialize(data)
    assert serialized is data


@pytest.mark.skipif(not (WINDOWS and SERIALIZATION_AVAILABLE), reason="native serialization 不可用")
def test_zero_copy_pickle_fallback_for_dict():
    sample = {"a": 1, "b": 2}
    payload = zero_copy_serialize(sample)
    assert isinstance(payload, (bytes, bytearray, memoryview))


