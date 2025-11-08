# -*- coding: utf-8 -*-
import pytest

conversion = pytest.importorskip("native_vnpy_conversion")

try:  # pragma: no cover - 可选依赖
    import pyarrow  # type: ignore  # noqa: F401
except Exception:  # pragma: no cover
    pyarrow = None  # type: ignore


class Sample:
    __slots__ = ("symbol", "price", "volume")

    def __init__(self, symbol: str, price: float, volume: int) -> None:
        self.symbol = symbol
        self.price = price
        self.volume = volume


def test_batch_convert_to_dict():
    rows = conversion.batch_convert(
        [Sample("IF88", 4300.5, 10), {"symbol": "IF88", "price": 4300.6, "volume": 2}],
        data_type="tick",
        output="dict",
        fields=["symbol", "price", "volume"],
    )
    assert isinstance(rows, list)
    assert rows[0]["symbol"] == "IF88"
    assert "_repeat" not in rows[0]


def test_convert_one_with_dict():
    row = conversion.convert_one({"symbol": "ag", "price": 5})
    assert row["symbol"] == "ag"


@pytest.mark.skipif(pyarrow is None, reason="pyarrow not installed")
def test_batch_convert_to_arrow():
    table = conversion.batch_convert(
        [Sample("rb", 3700.0, 1)],
        output="arrow",
        fields=["symbol", "price", "volume"],
    )
    assert hasattr(table, "num_rows")
    assert table.num_rows == 1

