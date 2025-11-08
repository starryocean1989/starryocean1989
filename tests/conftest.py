# -*- coding: utf-8 -*-
"""pytest公共夹具配置。

为性能测试补充缺失的数据夹具，避免因参数未提供而导致收集失败。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
if str(_TESTS_DIR) not in sys.path:
    sys.path.append(str(_TESTS_DIR))




@pytest.fixture(scope="session", name="data")
def fixture_orjson_test_data():
    """提供orjson性能测试所需的示例数据。"""

    return generate_complex_request()


