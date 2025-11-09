# -*- coding: utf-8 -*-
# Native Serialization扩展模块

## 概述

提供高性能序列化功能，包括批量序列化/反序列化。

### 核心特性

- ✅ **批量序列化**：批量处理多个对象，减少Python调用开销
- ✅ **批量反序列化**：批量处理多个序列化数据
- ✅ **零拷贝序列化**：简化实现

## 日志埋点（阶段5）

### C层日志
- **序列化操作**：记录批量序列化开始、每个对象的处理、成功完成
- **反序列化操作**：记录批量反序列化开始、数据处理、错误恢复
- **内存分配**：记录内存分配失败、释放操作
- **错误处理**：记录pickle序列化失败、数据损坏等异常

### Python层守卫器
- 为所有导出函数添加 `@native_call_guard(component="backend.native.native_serialization.wrapper")` 装饰器
- 捕获序列化异常并通过统一日志系统记录，包含操作类型和错误上下文
- 降级模式使用 `@native_call_guard(component="backend.native.native_serialization.fallback")`
- 平台错误使用 `@native_call_guard(component="backend.native.native_serialization.platform")`

### 零拷贝序列化日志
- **对象类型检测**：记录检测到的对象类型（bytes、DataFrame、buffer等）
- **序列化策略选择**：记录选择的序列化方法（直接引用、Arrow转换、memoryview、pickle回退）
- **性能优化**：记录零拷贝优化的应用情况

### 关键日志场景
1. **序列化失败**：`ERROR` 级别，记录失败对象索引和错误原因
2. **内存错误**：`ERROR` 级别，记录分配失败的上下文
3. **类型检测**：`DEBUG` 级别，记录对象类型识别过程
4. **性能优化**：`INFO` 级别，记录零拷贝序列化的应用
5. **批量操作统计**：`INFO` 级别，记录处理的批量大小和成功率

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

## 测试

### 集成测试
运行 `python test_stage5_simple.py` 验证：
- 日志桥接功能正常
- 批量序列化/反序列化工作
- 零拷贝序列化优化正常

### 性能测试
```python
import time
from backend.infrastructure.native.native_serialization import batch_serialize, batch_deserialize

# 测试批量性能
test_data = [{"id": i, "value": f"data_{i}"} for i in range(1000)]

start = time.time()
serialized = batch_serialize(test_data)
serialize_time = time.time() - start

start = time.time()
deserialized = batch_deserialize(serialized)
deserialize_time = time.time() - start

print(f"序列化: {serialize_time:.4f}s, 反序列化: {deserialize_time:.4f}s")
```

## 调试方式

### 日志配置
```python
import logging
from backend.infrastructure.native.logging_bridge import install_native_logging_bridge

# 配置详细日志查看序列化过程
logger = logging.getLogger("backend.native.bridge")
logger.setLevel(logging.DEBUG)

# 安装桥接
install_native_logging_bridge(logger=logger)
```

### 常见问题排查
1. **序列化失败**：查看 `ERROR` 级别日志，检查对象是否可序列化
2. **内存不足**：查看内存分配相关的错误日志
3. **性能问题**：检查是否使用了零拷贝优化，查看 `INFO` 级别日志
4. **类型错误**：查看对象类型检测日志，确认序列化策略选择

### 配置开关
- **SERIALIZATION_AVAILABLE**：指示序列化扩展是否可用
- **零拷贝优化**：自动检测并应用，无需手动配置
- **回退策略**：扩展不可用时自动使用Python实现

## 注意事项

- 使用Python pickle模块实现
- 批量操作减少Python调用开销
- 仅支持Windows平台
- 零拷贝序列化优先使用Arrow处理pandas DataFrame
- 自动降级到标准库实现（当扩展不可用时）
