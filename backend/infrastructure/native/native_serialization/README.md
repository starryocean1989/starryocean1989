# -*- coding: utf-8 -*-
# Native Serialization扩展模块

## 概述

提供高性能序列化功能，包括批量序列化/反序列化。

### 核心特性

- ✅ **批量序列化**：批量处理多个对象，减少Python调用开销
- ✅ **批量反序列化**：批量处理多个序列化数据
- ✅ **零拷贝序列化**：简化实现

## 编译

```bash
cd backend/infrastructure/native/native_serialization
python setup.py build_ext --inplace
```

> 推荐使用 `backend/infrastructure/native/compile_all.bat` 一键构建，脚本会顺序编译全部扩展（含本模块），遇错即停便于定位。

## API

### 批量序列化

```python
from backend.infrastructure.native.native_serialization import (
    batch_serialize,
    batch_deserialize,
    zero_copy_serialize,
)

# 批量序列化
data = [1, 2, 3, {"key": "value"}]
serialized = batch_serialize(data)

# 批量反序列化
deserialized = batch_deserialize(serialized)

# 零拷贝序列化
obj = {"test": 123}
serialized_obj = zero_copy_serialize(obj)
```

## 注意事项

- 使用Python pickle模块实现
- 批量操作减少Python调用开销
- 仅支持Windows平台
