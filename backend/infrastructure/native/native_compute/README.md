# -*- coding: utf-8 -*-
# Native Compute扩展模块

## 概述

提供高性能数值运算和哈希计算功能。

### 核心特性

- ✅ **批量数值运算**：批量执行数值运算，减少Python调用开销
- ✅ **批量哈希计算**：批量计算哈希值

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

## 注意事项

- 支持add、multiply、square、divide、divide_by_100、divide_by_1000等操作
- 支持md5、sha1、sha256等哈希算法
- 批量操作减少Python调用开销
- 仅支持Windows平台
