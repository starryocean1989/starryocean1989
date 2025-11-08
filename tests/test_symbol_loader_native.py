# -*- coding: utf-8 -*-
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, List

import pytest

from backend.infrastructure.data_module_vnpy.data_acquisition import SymbolLoader
from backend.infrastructure.native.native_symbol_index import (
    LOCKFREE_INDEX_AVAILABLE,
    SYMBOL_INDEX_AVAILABLE,
    LockFreeSymbolIndex,
    create_symbol_index,
)

RECORDS = [
    {"code": "000001", "name": "平安银行", "market": "深证A股"},
    {"code": "600000", "name": "浦发银行", "market": "上证A股"},
    {"code": "000002", "name": "万科A", "market": "深证A股"},
]

CLASSIFIED = {
    "深证A股": [
        {"code": "000001", "name": "平安银行"},
        {"code": "000002", "name": "万科A"},
    ],
    "上证A股": [
        {"code": "600000", "name": "浦发银行"},
    ],
}


def _available_impls() -> Iterable[str]:
    yield "python"
    if LOCKFREE_INDEX_AVAILABLE:
        yield "lockfree"
    if SYMBOL_INDEX_AVAILABLE:
        yield "cpp"


@pytest.mark.parametrize("impl", list(_available_impls()))
def test_symbol_index_build_and_query(impl: str):
    if impl == "cpp" and not SYMBOL_INDEX_AVAILABLE:
        pytest.skip("native_symbol_index C++ 扩展未编译，跳过 cpp 引擎")
    if impl == "lockfree" and not LOCKFREE_INDEX_AVAILABLE:
        pytest.skip("LockFreeHashMap 未编译，跳过 lockfree 引擎")

    index = create_symbol_index(use_native=impl != "python", impl=impl)
    index.build(RECORDS)

    symbol = index.get_symbol("000001")
    assert symbol is not None
    assert symbol["name"] == "平安银行"

    sz_codes = index.get_codes_by_market("深证A股")
    assert sz_codes == ["000001", "000002"]

    all_codes = index.all_codes()
    assert all_codes == ["000001", "000002", "600000"]


@pytest.mark.skipif(not LOCKFREE_INDEX_AVAILABLE, reason="LockFreeHashMap 未编译")
def test_lockfree_symbol_index_thread_safety():
    index = LockFreeSymbolIndex()
    index.build(RECORDS)

    def worker(iterations: int) -> None:
        for _ in range(iterations):
            symbol = index.get_symbol("000001")
            assert symbol is not None
            assert symbol["name"] == "平安银行"
            codes = index.get_codes_by_market("深证A股")
            assert codes == ["000001", "000002"]

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(worker, 128) for _ in range(8)]
        for future in futures:
            future.result()


@pytest.mark.parametrize("impl", list(_available_impls()))
def test_symbol_loader_native_interfaces(impl: str):
    loader = SymbolLoader()
    loader.classified_symbols = {market: list(records) for market, records in CLASSIFIED.items()}

    loader._symbol_index = create_symbol_index(use_native=impl != "python", impl=impl)
    loader._symbol_index_engine = getattr(loader._symbol_index, "ENGINE", "python")
    loader._using_native_symbol_index = bool(
        getattr(loader._symbol_index, "IS_NATIVE", False)
    )
    loader._rebuild_symbol_index(loader.classified_symbols)

    native_codes = loader.get_all_codes_native()
    assert native_codes == ["000001", "000002", "600000"]

    sz_codes = loader.get_codes_by_market_native("深证A股")
    assert sz_codes == ["000001", "000002"]

    symbol = loader.get_symbol_info_native("000002")
    assert symbol is not None
    assert symbol["name"] == "万科A"

    extracted_all = loader.extract_all_codes()
    assert extracted_all == ["000001", "000002", "600000"]

    extracted_sz = loader.extract_codes_by_market(["深证A股"])
    assert extracted_sz == ["000001", "000002"]

