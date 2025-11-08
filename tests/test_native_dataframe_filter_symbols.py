# -*- coding: utf-8 -*-
"""Tests for native_dataframe_ops.filter_symbols."""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.infrastructure.native.native_dataframe_ops import (  # noqa: E402
    DATAFRAME_OPS_AVAILABLE,
    filter_symbols,
)


def _python_reference(
    records,
    *,
    deduplicate: bool = True,
    drop_empty_code: bool = True,
    require_name: bool = False,
):
    seen = set()
    result = []
    for symbol in records:
        if not isinstance(symbol, dict):
            continue

        code = symbol.get("code")
        if code is None:
            continue

        code_text = str(code).strip()
        if drop_empty_code and not code_text:
            continue

        if require_name:
            name = symbol.get("name")
            if name is None or str(name).strip() == "":
                continue

        if deduplicate:
            if code_text in seen:
                continue
            seen.add(code_text)

        result.append(symbol)

    return result


@pytest.mark.parametrize(
    "drop_empty_code",
    [True, False],
)
def test_filter_symbols_deduplicate_matches_python(drop_empty_code):
    records = [
        {"code": "000001", "name": "平安银行"},
        {"code": "000001", "name": "重复"},
        {"code": " 000002 ", "name": "万科A"},
        {"code": None, "name": "无代码"},
        {"code": "", "name": "空白"},
    ]

    expected = _python_reference(
        records,
        deduplicate=True,
        drop_empty_code=drop_empty_code,
    )

    actual = filter_symbols(
        records,
        deduplicate=True,
        drop_empty_code=drop_empty_code,
    )

    assert actual == expected


def test_filter_symbols_require_name_and_order():
    records = [
        {"code": "300001", "name": "  第一家公司  "},
        {"code": "300002", "name": ""},
        {"code": "300003", "name": None},
        {"code": "300004", "name": "第四家公司"},
    ]

    actual = filter_symbols(
        records,
        deduplicate=False,
        drop_empty_code=True,
        require_name=True,
    )

    assert actual == [records[0], records[3]]


def test_filter_symbols_handles_non_dict_entries():
    records = [
        {"code": "688001", "name": "华兴源创"},
        ["invalid", "entry"],
        {"code": "688002", "name": "睿创微纳"},
    ]

    expected = _python_reference(records)
    actual = filter_symbols(records)

    assert actual == expected


def test_filter_symbols_available_flag_exposed():
    assert isinstance(DATAFRAME_OPS_AVAILABLE, bool)
