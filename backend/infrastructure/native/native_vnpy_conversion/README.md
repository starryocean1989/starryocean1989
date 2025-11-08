# -*- coding: utf-8 -*-
# native_vnpy_conversion 扩展

为 VnPy 风格的数据对象提供高性能的批量转换能力，支持输出 dict 或 PyArrow Table，并在 Python 层保留自动降级方案。

## 功能特性

- `batch_convert(objects, data_type="", output="dict", fields=None)`
  - 支持多种对象输入：dict、带 `to_dict()`/`as_dict()` 的对象、任意拥有 `__dict__` 的 Python 对象。
  - 可选 `fields` 参数，用于显式指定属性列表，不依赖反射。
  - 当 `output="arrow"` 时，若安装了 `pyarrow`，自动生成 Arrow Table；否则抛出 ImportError。
- `convert_one(obj, fields=None)`：单对象转换，便于调试或单独处理。
- `get_version()`：返回扩展版本。

## 编译

```bash
cd backend/infrastructure/native/native_vnpy_conversion
python setup.py build_ext --inplace
```

或执行统一脚本：

```bash
cd backend/infrastructure/native
.\compile_all.bat
```

## 示例

```python
from native_vnpy_conversion import batch_convert, convert_one

class Tick:
    __slots__ = ("symbol", "price", "volume")

    def __init__(self, symbol, price, volume):
        self.symbol = symbol
        self.price = price
        self.volume = volume

ticks = [Tick("IF88", 4300.5, 10), Tick("IF88", 4300.7, 4)]

# 输出 dict 列表
rows = batch_convert(ticks, data_type="tick", fields=["symbol", "price", "volume"])

# 输出 Arrow Table
table = batch_convert(ticks, output="arrow", fields=["symbol", "price", "volume"])
```

> 若未安装 `pyarrow`，`output="arrow"` 会抛出 ImportError；可捕获后回退至 dict 输出。

## 测试

```bash
pytest backend/infrastructure/native/tests/test_native_vnpy_conversion.py
```

测试覆盖属性拉取、dict 输入、Arrow 输出以及错误处理。

