# 步骤5 - IPO日期下载重试机制说明

## 配置参数

```python
MAX_RETRY = 10  # 最多重试10次
```

**总请求次数 = 初次请求 + 重试次数 = 1 + 10 = 11次**

## 重试触发条件

### 1. 数据异常（无效数据）

当满足以下条件时触发重试：
- `ipo_date` 为 `None` 或 `0`
- `industry` 为 `0`（无行业数据）
- 或者所有33个字段都为0（全零数据）

**代码位置**：`data_acquisition.py:3282-3301`

```python
if ipo_date is not None:
    # 已上市，有IPO日期
    await asyncio.to_thread(result_queue.put, (symbol, finance_info))
    await asyncio.to_thread(progress_queue.put, (symbol, "success"))
elif industry > 0:
    # 有行业数据，认为是有效品种
    await asyncio.to_thread(result_queue.put, (symbol, finance_info))
    await asyncio.to_thread(progress_queue.put, (symbol, "success"))
else:
    # 数据异常，触发重试
    if retry_count < MAX_RETRY:
        new_task = ("ipo", symbol, market, retry_count + 1)
        await asyncio.to_thread(task_queue.put, new_task)
        await asyncio.to_thread(progress_queue.put, (symbol, "retry"))
    else:
        # 达到最大重试次数，标记为failed
        await asyncio.to_thread(progress_queue.put, (symbol, "failed"))
```

### 2. 下载异常（网络/API错误）

当发生以下异常时触发重试：
- 网络连接失败
- API调用超时
- TDX客户端异常
- 其他运行时错误

**代码位置**：`data_acquisition.py:3317-3330`

```python
except Exception as e:
    # 异常处理，触发重试
    if retry_count < MAX_RETRY:
        new_task = ("ipo", symbol, market, retry_count + 1)
        await asyncio.to_thread(task_queue.put, new_task)
        await asyncio.to_thread(progress_queue.put, (symbol, "retry"))
    else:
        # 达到最大重试次数，标记为failed
        await asyncio.to_thread(progress_queue.put, (symbol, "failed"))
```

## 重试机制特点

### 1. 自动服务器切换

每次重试会自动使用不同的服务器：
- 多个worker并发工作
- 每个worker使用不同的服务器连接
- 任务重新入队后，可能被不同worker（不同服务器）处理
- **效果**：4次请求可能分布在4个不同的TDX服务器上

### 2. 任务格式支持

支持新旧两种任务格式：

```python
# 旧格式（初次请求）
task = ("ipo", symbol, market)
# retry_count 默认为 0

# 新格式（重试请求）
task = ("ipo", symbol, market, retry_count)
# retry_count = 1/2/3
```

### 3. 进度追踪

每次状态变化都会推送进度事件：

| 状态 | 说明 | 进度队列 |
|------|------|----------|
| `"success"` | 下载成功 | `(symbol, "success")` |
| `"retry"` | 触发重试 | `(symbol, "retry")` |
| `"failed"` | 达到重试上限，下载失败 | `(symbol, "failed")` |

### 4. 防止无限循环

**关键设计**：`retry_count` 作为任务的一部分传递

```python
# 初次请求
retry_count = 0

# 第1次重试
retry_count = 1 → 创建新任务 (symbol, market, 1)

# 第2次重试
retry_count = 2 → 创建新任务 (symbol, market, 2)

# 第3次重试
retry_count = 3 → 创建新任务 (symbol, market, 3)

# 第4次失败
retry_count = 3 → 不再创建新任务，标记为 "failed"
```

## 失败处理

达到 `MAX_RETRY` 后，品种会被标记为下载失败：

1. **不保存数据**：`result_queue` 中不会有该品种的数据
2. **标记为failed**：`progress_queue.put((symbol, "failed"))`
3. **后续处理**：`incremental_update()` 方法会识别这些品种为 `unlisted`
4. **保存到文件**：写入 `unlisted_symbols.json`
5. **从列表移除**：从 `stock_list_classified.json` 中删除

## 日志输出

### 重试日志（Debug级别）

```
品种 123456 数据异常，重试 1/10
品种 123456 数据异常，重试 2/10
...
品种 123456 数据异常，重试 10/10
```

### 失败日志（Warning级别）

```
⚠️ 品种 123456 达到最大重试次数(10)，所有服务器均返回无效数据，标记为下载失败
⚠️ 品种 123456 异常重试达到上限(10)，标记为失败
```

## 性能影响

### 单品种最大耗时

假设每次请求耗时 0.5秒：
- 初次请求：0.5秒
- 10次重试：10 × 0.5 = 5秒
- **总计**：最多 5.5秒（单品种）

### 批量下载影响

由于采用多进程+多worker异步并发：
- **并发数**：通常 4-8 个worker同时工作
- **队列机制**：失败品种自动重新排队
- **整体影响**：对批量下载的总时间影响较小
- **IPv6优先策略**：优先使用IPv6乱序服务器池，提高成功率

## 配置建议

**当前配置（`MAX_RETRY = 10`）** 平衡可靠性与性能：
- ✅ 提供充分的容错能力（11次请求）
- ✅ 配合IPv6乱序池，覆盖多个服务器
- ✅ 单品种最多5.5秒，批量下载影响可控
- ✅ 显著降低误判为unlisted的概率

### 如需调整：

**增加重试次数**（如 `MAX_RETRY = 20`）：
- 优点：进一步提高成功率
- 缺点：单品种最大耗时更长

**减少重试次数**（如 `MAX_RETRY = 5`）：
- 优点：更快失败
- 缺点：可能增加误判概率

**推荐**：保持 `MAX_RETRY = 10`（当前设置）

## 相关代码

| 文件 | 行号 | 功能 |
|------|------|------|
| `data_acquisition.py` | 3243-3250 | 任务格式解析，设置初始 `retry_count` |
| `data_acquisition.py` | 3282-3301 | 数据异常重试逻辑 |
| `data_acquisition.py` | 3317-3330 | 下载异常重试逻辑 |
| `data_quality.py` | 增量更新方法 | 处理 failed 品种，生成 unlisted_symbols.json |

## 总结

步骤5的IPO下载重试机制设计：
- ✅ **重试次数**：10次（总共11次请求）
- ✅ **IPv6优先**：服务器池配置为 IPv6乱序 + IPv4
- ✅ **自动切换服务器**：每次重试可能使用不同服务器
- ✅ **防止无限循环**：通过 `retry_count` 计数器强制停止
- ✅ **异常容错**：网络异常和数据异常都会触发重试
- ✅ **性能平衡**：多worker并发，对整体时间影响小

