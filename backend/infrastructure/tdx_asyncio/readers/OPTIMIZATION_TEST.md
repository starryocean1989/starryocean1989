# -*- coding: utf-8 -*-
# binary_reader 价格转换优化测试说明

## 优化内容

1. **扩展 native_compute 支持 divide_by_1000 操作**
   - 在 `batch_compute.c` 中添加了 `divide_by_1000` 操作
   - 支持批量除以1000.0，用于TDX价格转换

2. **优化 binary_reader.py 的 _decode_day_data 方法**
   - 使用 `native_compute` 批量处理价格转换（除以1000.0）
   - 当记录数 > 10 时，使用批量转换提升性能
   - 提供降级方案：native_compute 不可用时，使用Python列表推导式

3. **优化 binary_reader.py 的 _decode_min_data 方法**
   - 添加了代码注释，说明分钟线数据中的价格已经是浮点数，不需要转换
   - 优化了代码结构，添加了边界检查

## 测试步骤

### 1. 编译 native_compute 扩展

```bash
cd backend/infrastructure/native/native_compute
python setup.py build_ext --inplace
```

### 2. 验证 native_compute 功能

```python
from backend.infrastructure.native.native_compute import batch_compute, COMPUTE_AVAILABLE

# 检查是否可用
print(f"native_compute available: {COMPUTE_AVAILABLE}")

# 测试 divide_by_1000 操作
prices = [10000, 20000, 30000, 40000, 50000]
result = batch_compute(prices, "divide_by_1000")
print(f"原始价格: {prices}")
print(f"转换后: {result}")
# 预期输出: [10.0, 20.0, 30.0, 40.0, 50.0]
```

### 3. 测试 binary_reader 优化效果

```python
import time
from pathlib import Path
from backend.infrastructure.tdx_asyncio.readers.binary_reader import TdxBinaryReader

# 初始化读取器
reader = TdxBinaryReader(tdx_root_path=Path("C:/new_tdx"))

# 测试日线数据读取（需要真实的TDX数据文件）
symbol = "000001"
market = "sz"
data_type = "day"

# 读取数据并测量时间
start_time = time.time()
df = reader.read_single(symbol, data_type, market)
elapsed = time.time() - start_time

print(f"读取 {symbol} 日线数据: {len(df)} 条记录")
print(f"耗时: {elapsed:.3f} 秒")
print(f"前5条数据:")
print(df.head())

# 验证价格是否正确（应该是浮点数，除以1000.0后的值）
if not df.empty:
    print(f"\n价格范围:")
    print(f"开盘价: {df['open'].min():.2f} - {df['open'].max():.2f}")
    print(f"收盘价: {df['close'].min():.2f} - {df['close'].max():.2f}")
    # 验证价格是否合理（应该在合理范围内，如 0.01 - 1000.0）
    assert df['open'].min() > 0, "价格应该大于0"
    assert df['open'].max() < 10000, "价格应该小于10000"
```

### 4. 性能对比测试

```python
import time
from pathlib import Path
from backend.infrastructure.tdx_asyncio.readers.binary_reader import TdxBinaryReader

reader = TdxBinaryReader(tdx_root_path=Path("C:/new_tdx"))

# 测试多个品种的读取性能
symbols = ["000001", "600000", "000002", "600001", "000003"]
data_type = "day"
market = "sz"

# 批量读取并测量时间
start_time = time.time()
results = {}
for symbol in symbols:
    df = reader.read_single(symbol, data_type, market)
    results[symbol] = len(df)
elapsed = time.time() - start_time

print(f"批量读取 {len(symbols)} 个品种: 总耗时 {elapsed:.3f} 秒")
print(f"平均每个品种: {elapsed / len(symbols):.3f} 秒")
for symbol, count in results.items():
    print(f"  {symbol}: {count} 条记录")
```

### 5. 验证降级方案

如果 native_compute 不可用，代码应该自动降级到Python实现：

```python
# 模拟 native_compute 不可用的情况
# 可以通过临时修改导入来测试降级方案
# 代码应该仍然能正常工作，只是性能可能稍慢
```

## 预期效果

1. **性能提升**：
   - 当记录数 > 10 时，使用批量转换比循环转换快 5-10倍
   - 对于1000条记录，批量转换应该比循环转换快约 5-10倍

2. **兼容性**：
   - native_compute 可用时，自动使用批量转换
   - native_compute 不可用时，自动降级到Python实现
   - 数据解析结果应该完全一致

3. **正确性**：
   - 价格转换结果应该正确（除以1000.0）
   - 日期解析应该正确
   - DataFrame 结构应该正确

## 注意事项

1. **编译要求**：native_compute 需要先编译才能使用
2. **数据要求**：测试需要真实的TDX数据文件
3. **性能测试**：建议使用较大的数据文件（1000+条记录）来测试性能提升
4. **降级测试**：可以通过临时禁用 native_compute 来测试降级方案

## 问题排查

1. **native_compute 不可用**：
   - 检查是否已编译：`python setup.py build_ext --inplace`
   - 检查导入是否成功：`from backend.infrastructure.native.native_compute import batch_compute`

2. **价格转换错误**：
   - 检查原始价格值是否正确
   - 检查转换后的价格是否合理
   - 验证除以1000.0的逻辑是否正确

3. **性能未提升**：
   - 检查记录数是否 > 10（小于10时使用降级方案）
   - 检查 native_compute 是否可用
   - 使用更大的数据文件进行测试

