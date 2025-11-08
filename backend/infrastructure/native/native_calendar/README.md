# -*- coding: utf-8 -*-
# native_calendar 模块说明

## 核心能力

- 基于 C++/pybind11 的高性能交易日历计算引擎
- 提供 `NativeCalendar` 类用于判断交易日、获取下一交易日等操作
- 采用二进制日历数据（`sse_calendar.bin`）实现常量时间查询
- 与 `data_module_vnpy` 内的交易日逻辑兼容，可直接替换原有 Python 实现

## 导出接口

| 接口 | 说明 |
| ---- | ---- |
| `NativeCalendar` | 原生交易日历类，构造时加载二进制日历数据 |
| `NATIVE_CALENDAR_AVAILABLE` | 标识模块是否加载成功（与其他 native 模块保持一致） |

### `NativeCalendar` 常用方法

| 方法 | 说明 |
| ---- | ---- |
| `is_trading_day(date_str: str) -> bool` | 判断给定（`YYYY-MM-DD`）日期是否为交易日 |
| `get_next_trading_day(date_str: str) -> Optional[str]` | 获取下一个交易日（若无返回 `None`） |
| `get_trading_days(start: str, end: str) -> Iterable[str]` | 获取区间内所有交易日 |

> 具体签名可在 `calendar.cpp` 中查看，Python 层通过 pybind11 自动映射。

## 编译说明

1. 确保已安装 Visual Studio Build Tools（或完整 VS）以及 Python 对应的编译环境。
2. 进入 `backend/infrastructure/native` 后运行 `compile_all.bat`，该脚本会在第 24 步自动编译 `native_calendar`。
3. 或手动编译：

```bash
cd backend/infrastructure/native/native_calendar
python setup.py build_ext --inplace
```

## 降级策略

- 如果扩展未编译成功，`backend.infrastructure.native.__init__` 将返回 `NATIVE_CALENDAR_AVAILABLE = False`，并提供一个兜底的 Python 类，调用时会提示需要编译原生模块。
- 项目可通过 `NATIVE_CALENDAR_AVAILABLE` 判断是否启用原生实现，从而保持兼容性。

## 数据文件

- `sse_calendar.bin`：包含上交所/深交所综合交易日历的压缩数据，构建阶段会自动复制到目标目录。


