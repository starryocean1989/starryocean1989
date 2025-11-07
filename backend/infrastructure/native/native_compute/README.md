# -*- coding: utf-8 -*-
# Native Compute扩展模块

## 概述

提供高性能数值运算、哈希计算和日期处理功能。

### 核心特性

- ✅ **批量数值运算**：批量执行数值运算，减少Python调用开销
- ✅ **批量哈希计算**：批量计算哈希值
- ✅ **批量日期验证**：批量验证和比较ISO日期字符串（YYYY-MM-DD格式）

## 编译

```bash
cd backend/infrastructure/native/native_compute
python setup.py build_ext --inplace
```

## API

### 批量数值运算

```python
from backend.infrastructure.native.native_compute import batch_compute

data = [1, 2, 3, 4, 5]

# 加法运算
result = batch_compute(data, "add")  # [2, 3, 4, 5, 6]

# 乘法运算
result = batch_compute(data, "multiply")  # [2, 4, 6, 8, 10]

# 平方运算
result = batch_compute(data, "square")  # [1, 4, 9, 16, 25]

# 除法运算：除以100.0
result = batch_compute(data, "divide")  # 或 "divide_by_100"

# 除法运算：除以1000.0（用于TDX价格转换）
prices = [10000, 20000, 30000]
result = batch_compute(prices, "divide_by_1000")  # [10.0, 20.0, 30.0]
```

### 批量哈希计算

```python
from backend.infrastructure.native.native_compute import batch_hash

data = [b"hello", b"world", b"test"]

# 使用MD5算法
hashes = batch_hash(data, "md5")

# 使用SHA256算法
hashes = batch_hash(data, "sha256")
```

### 批量日期验证（新增）

```python
from backend.infrastructure.native.native_compute import (
    batch_validate_iso_dates,
    batch_compare_dates
)

# 批量验证日期格式
dates = ["2024-01-01", "2024-13-01", "invalid", None]
valid_flags = batch_validate_iso_dates(dates)
# 返回: [True, False, False, False]

# 批量比较日期
dates = ["2024-01-01", "2024-01-15", "2023-12-31", "invalid"]
reference = "2024-01-10"
comparisons = batch_compare_dates(dates, reference)
# 返回: [-1, 1, -1, -999]
# -1: 早于参考日期, 0: 等于, 1: 晚于, -999: 无效日期
```

## 使用场景

### IPO日期批量验证（数据模块优化）

```python
from backend.infrastructure.native.native_compute import batch_validate_iso_dates, batch_compare_dates

# 假设有1000个品种的IPO日期需要验证
ipo_dates = ["2024-01-01", "2023-12-15", ...]  # 1000条

# Python方式（慢）
valid_dates = []
for date_str in ipo_dates:
    try:
        date.fromisoformat(date_str)
        valid_dates.append(True)
    except:
        valid_dates.append(False)

# C扩展方式（快60%+）
valid_dates = batch_validate_iso_dates(ipo_dates)

# 批量比较日期（筛选符合条件的品种）
current_date = "2024-01-10"
comparisons = batch_compare_dates(ipo_dates, current_date)
# 筛选早于当前日期的品种
early_ipo_indices = [i for i, cmp in enumerate(comparisons) if cmp == -1]
```

## 性能优势

- 批量操作减少Python调用开销
- 日期验证使用C字符串操作，无需Python对象转换
- 适合处理大量数据（1000+条记录）

## 注意事项

- 支持add、multiply、square、divide、divide_by_100、divide_by_1000等操作
- 支持md5、sha1、sha256等哈希算法
- 日期格式必须是ISO格式（YYYY-MM-DD）
- 仅支持Windows平台

