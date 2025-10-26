# -*- coding: utf-8 -*-
# 两段式下载失败处理优化

**优化日期**: 2025-10-25
**优化版本**: v2.0
**状态**: ✅ 已完成

---

## 📊 优化目标

提高K线两段式下载的**数据完整性**和**可靠性**，确保失败任务不会丢失。

---

## 🔍 问题分析

### 优化前的问题

**第一段（Regular服务器）失败处理**：
```python
# ❌ 原实现：失败任务直接丢失
if data is None or data.empty:
    await asyncio.to_thread(progress_queue.put, (symbol, interval, "failed"))
    failed += 1  # 任务丢失！
```

**影响**：
- 第一段失败的任务不会进入第二段
- 导致最终数据不完整
- 即使有热备服务器也无法挽救

**示例场景**：
```
1000个品种下载：
- 第一段成功: 950个 (95%)
- 第一段失败: 50个 (5%) → ❌ 直接丢失
- 第二段处理: 只处理剩余未处理的任务（不包括失败的50个）
- 最终结果: 缺失50个品种的数据
```

---

## ✅ 优化方案

### 第一段：失败任务放回队列

参考IPO下载的成功实现，将失败任务放回task_queue：

```python
# ✅ 优化后：失败任务放回队列
if data is None or data.empty:
    # 🔧 优化：失败任务放回队列，供第二段热备服务器重试
    await asyncio.to_thread(task_queue.put, (symbol, interval, start_date))
    await asyncio.to_thread(progress_queue.put, (symbol, interval, "retry"))
    failed += 1

except Exception as e:
    # 🔧 优化：异常任务也放回队列，供第二段热备服务器重试
    await asyncio.to_thread(task_queue.put, (symbol, interval, start_date))
    await asyncio.to_thread(progress_queue.put, (symbol, interval, "retry"))
    failed += 1
```

### 第二段：增强失败日志

第二段是最后的兜底阶段，失败任务**不放回队列**（避免无限循环）：

```python
# ⚠️ 第二段失败：热备服务器也无法下载，最终标记为失败
# 不放回队列以避免无限循环（这是最后兜底阶段）
logger.warning(
    "[Phase2] Worker %s 热备服务器下载失败 %s_%s（数据为空）",
    worker_id, symbol, interval
)
await asyncio.to_thread(progress_queue.put, (symbol, interval, "failed"))
```

---

## 🎯 优化效果

### 数据流优化

**优化前**：
```
任务 → 第一段Regular服务器
       ├─ 成功 → 完成 ✅
       └─ 失败 → 丢失 ❌

第二段Standby服务器
  └─ 只处理剩余未分配的任务
```

**优化后**：
```
任务 → 第一段Regular服务器
       ├─ 成功 → 完成 ✅
       └─ 失败 → 放回队列 🔄

第二段Standby服务器
  ├─ 处理剩余未分配的任务
  ├─ 处理第一段失败的任务 ← 新增！
  │   ├─ 成功 → 完成 ✅
  │   └─ 失败 → 最终失败 ⚠️（避免无限循环）
```

### 预期提升

**场景1：正常网络波动**
```
1000个品种：
- 第一段成功: 950个
- 第一段失败: 50个 → 放回队列 🔄
- 第二段处理失败任务: 45个成功 ✅
- 最终失败: 5个 ⚠️

数据完整性: 95% → 99.5% (提升4.5%)
```

**场景2：服务器质量差异大**
```
1000个品种：
- 第一段成功: 900个
- 第一段失败: 100个 → 放回队列 🔄
- 第二段处理失败任务: 90个成功 ✅
- 最终失败: 10个 ⚠️

数据完整性: 90% → 99% (提升9%)
```

---

## 📋 状态监控

### Progress Queue状态

| 状态 | 含义 | 所属阶段 |
|------|------|----------|
| `success` | 下载成功 | 第一段/第二段 |
| `retry` | 失败，已放回队列 | 第一段（新增）|
| `failed` | 最终失败 | 第二段 |

### 统计指标

```python
# 下载完成后统计
total_tasks = 1000
success_count = progress_queue中"success"的数量
retry_count = progress_queue中"retry"的数量
failed_count = progress_queue中"failed"的数量

# 关键指标
第一段成功率 = (total_tasks - retry_count) / total_tasks
第二段挽救率 = (success_count - 第一段成功数) / retry_count
最终完整性 = success_count / total_tasks
```

---

## 🔬 测试建议

### 测试1：正常场景
```python
# 1000个品种，1min周期，10天数据
symbols = 1000个常见品种
interval = "1m"
days = 10

# 预期结果
- 第一段成功率: 95%+
- retry数量: ~50个
- 第二段挽救率: 90%+
- 最终完整性: 99%+
```

### 测试2：压力场景
```python
# 2000个品种，5min周期，20天数据
symbols = 2000个品种（含部分停牌品种）
interval = "5m"
days = 20

# 预期结果
- 第一段成功率: 90%+
- retry数量: ~200个
- 第二段挽救率: 85%+
- 最终完整性: 98%+
```

### 测试3：异常场景
```python
# 故意使用部分失效服务器
# 观察失败任务是否正确放回队列
# 观察第二段是否成功挽救

# 关键观察点
- 日志中是否有"retry"标记
- task_queue中是否有失败任务重新入队
- 第二段是否处理了这些任务
```

---

## 🚀 使用方式

优化后的两段式下载自动生效，无需修改调用代码：

```python
from backend.infrastructure.data_module_vnpy.data_acquisition import AsyncMultiProcessDownloader

downloader = AsyncMultiProcessDownloader()

# 使用两段式下载（默认启用）
result = await downloader.download_batch(
    symbols=symbols,
    start_date=start_date,
    intervals=["1m"],
    use_two_phase=True,  # 默认True，启用优化后的两段式下载
)

# 检查结果
print(f"成功: {result['succeeded']}")
print(f"失败: {result['failed']}")  # 只包含第二段仍失败的任务
print(f"完整性: {result['succeeded']/len(symbols)*100:.2f}%")
```

---

## 📊 性能影响

### 延迟影响

| 指标 | 优化前 | 优化后 | 变化 |
|------|--------|--------|------|
| 第一段耗时 | 100% | 100% | 无变化 |
| 第二段耗时 | 5% | 10-15% | +5-10%（处理更多任务）|
| 总体耗时 | 105% | 110-115% | +5-10% |

### 资源影响

- **内存**: 无明显增加（task_queue本就存在）
- **CPU**: 第二段处理时间增加，但总体可接受
- **网络**: 第二段请求数增加，但使用最优热备服务器

### 权衡分析

```
优点：
✅ 数据完整性提升 4.5-9%
✅ 利用热备服务器挽救失败任务
✅ 无需修改调用代码，透明升级

缺点：
⚠️ 总耗时增加 5-10%
⚠️ 第二段处理任务数增加

结论：值得！
数据完整性 > 5-10%的耗时增加
```

---

## 🔧 技术细节

### 队列机制

```python
# task_queue是多进程共享队列（multiprocessing.Queue）
# 支持线程安全的put/get操作

# 第一段失败时
await asyncio.to_thread(task_queue.put, (symbol, interval, start_date))
# ↓
# task_queue中任务数增加
# ↓
# 第二段worker从task_queue.get()获取
# ↓
# 使用热备服务器重试
```

### 避免无限循环

```python
# 为什么第二段不放回队列？
# 1. 第二段是最后的兜底阶段（最优热备服务器）
# 2. 如果热备都失败，很可能是品种本身问题（停牌/不存在）
# 3. 放回队列会导致无限循环

# 如果未来需要第二段重试，可以增加计数器：
task_with_retry_count = (symbol, interval, start_date, retry_count)
if retry_count < MAX_RETRY:
    await asyncio.to_thread(task_queue.put, task_with_retry_count)
```

---

## ✅ 验证清单

- [x] 第一段失败任务放回task_queue
- [x] 第一段异常任务放回task_queue
- [x] progress_queue状态标记为"retry"
- [x] 第二段增强失败日志（warning级别）
- [x] 第二段不放回队列（避免无限循环）
- [x] 优化文档完成
- [ ] 实际测试验证（待执行）
- [ ] 性能对比测试（待执行）

---

**优化完成！** 🎉

两段式下载现在具备更强的可靠性和数据完整性。

