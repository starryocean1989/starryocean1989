# -*- coding: utf-8 -*-
# Native Conversion扩展模块

## 概述

提供高性能类型转换和字符串操作功能。

### 核心特性

- ✅ **批量类型转换**：批量转换多个对象类型
- ✅ **批量字符串操作**：批量编码/解码字符串

## 编译

```bash
cd backend/infrastructure/native/native_conversion
python setup.py build_ext --inplace
```

## API

### 批量类型转换

```python
from backend.infrastructure.native.native_conversion import batch_convert

# 转换为整数
data = ['1', '2', '3']
integers = batch_convert(data, int)

# 转换为浮点数
floats = batch_convert(data, float)

# 转换为字符串
strings = batch_convert(data, str)
```

### 批量字符串操作

```python
from backend.infrastructure.native.native_conversion import batch_encode, batch_decode

# 批量编码
strings = ['hello', 'world', 'test']
encoded = batch_encode(strings, encoding='utf-8')

# 批量解码
decoded = batch_decode(encoded, encoding='utf-8')
```

## 注意事项

- 支持int、float、str、bytes等类型转换
- 批量操作减少Python调用开销
- 仅支持Windows平台
