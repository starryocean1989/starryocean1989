# LoadBalancer E2E测试套件

## 概述

这个E2E测试套件用于测试新LoadBalancer架构在实际任务中的性能表现，并收集数据用于优化决策矩阵和配置参数。

## 测试文件

### 1. `test_loadbalancer_e2e_basic.py`
**基础功能测试**

- 测试数据质量扫描基本功能
- 收集资源压力数据
- 记录执行时间

**运行方式**：
```bash
python tests/e2e/test_loadbalancer_e2e_basic.py
```

### 2. `test_loadbalancer_e2e_variants.py`
**参数变化测试**

- 测试不同品种数量（50, 100, 200, 500）的性能
- 测试不同周期组合（1d, 1d+5m, 1d+5m+1m）的性能
- 分析扩展性

**运行方式**：
```bash
python tests/e2e/test_loadbalancer_e2e_variants.py
```

### 3. `analyze_performance.py`
**性能分析和优化建议生成器**

自动分析收集的性能数据，生成：
- 任务类型统计
- 扩展性分析（品种数量 vs 耗时）
- 资源瓶颈分布
- 优化建议

**运行方式**：
```bash
python tests/e2e/analyze_performance.py
```

### 4. `run_all_e2e_tests.py`
**一键运行所有测试**

自动执行所有E2E测试并生成分析报告。

**运行方式**：
```bash
python tests/e2e/run_all_e2e_tests.py
```

## 数据收集

所有测试数据会自动保存到：
```
tests/e2e/performance_data.json
```

数据格式：
```json
[
  {
    "timestamp": "2025-10-24T16:30:00",
    "test_name": "scan_100_symbols",
    "task_type": "data_quality_scan",
    "config": {
      "symbols_count": 100,
      "intervals": ["1d"]
    },
    "duration_seconds": 12.5,
    "success": true,
    "resource_info": {
      "initial_pressure": 45.2,
      "final_pressure": 62.8,
      "bottleneck": "disk"
    },
    "dynamic_adjustments": []
  }
]
```

## 使用流程

### 完整测试流程

1. **运行所有E2E测试**：
   ```bash
   cd C:\Users\USER\Desktop\terminal_v0.50
   venv310\Scripts\python.exe tests\e2e\run_all_e2e_tests.py
   ```

2. **查看性能数据**：
   ```bash
   # 数据文件位置
   tests\e2e\performance_data.json
   ```

3. **分析结果**：
   测试会自动生成分析报告，包括：
   - 任务类型性能统计
   - 扩展性分析
   - 资源瓶颈分布
   - 优化建议

### 单独运行某个测试

```bash
# 只运行基础测试
venv310\Scripts\python.exe tests\e2e\test_loadbalancer_e2e_basic.py

# 只运行参数变化测试
venv310\Scripts\python.exe tests\e2e\test_loadbalancer_e2e_variants.py

# 只运行性能分析
venv310\Scripts\python.exe tests\e2e\analyze_performance.py
```

## 优化建议使用

分析报告会生成具体的优化建议，例如：

### 示例建议1：扩展性问题
```
⚠️  扩展性问题：大数据集(500品种)的单品种耗时(0.0250秒)
比小数据集(50品种)(0.0150秒)高67%。
建议：增加批处理大小或优化缓存策略。
```

**对应优化**：
- 修改 `policy.py` 中 `_plan_for_disk_task()` 方法
- 增大 `base_batch_size` 从 1000 到 2000
- 或调整缓存TTL

### 示例建议2：磁盘瓶颈
```
⚠️  磁盘瓶颈频繁(15次)。
建议：增大批处理大小，减少磁盘IO次数；或考虑使用SSD加速。
```

**对应优化**：
- 修改 `policy.py` 中的决策矩阵
- 磁盘瓶颈时的 `batch_size` 增大到 5000
- 或修改 `adjustment_strategy` 的 `aggressive_decrease` 参数

### 示例建议3：资源压力
```
⚠️  平均资源压力过高(78.5%)。
建议：降低初始并发配置，让动态调整有更多空间。
```

**对应优化**：
- 修改 `policy.py` 中的 `base_workers` 计算
- 从 `cpu_count // 2` 降低到 `cpu_count // 3`

## 扩展测试

### 添加新的测试场景

1. 创建新的测试文件（例如 `test_loadbalancer_e2e_tdx.py`）
2. 使用 `performance_collector` 记录数据
3. 在 `run_all_e2e_tests.py` 中添加到 `test_scripts` 列表

示例代码：
```python
from test_loadbalancer_e2e_basic import performance_collector

def test_tdx_read():
    # 执行测试
    start_time = time.time()
    # ... 测试代码 ...
    duration = time.time() - start_time

    # 记录结果
    performance_collector.record_test(
        test_name="tdx_read_test",
        task_type="tdx_read",
        config={"file_count": 100},
        duration=duration,
        success=True,
        resource_info={...},
    )
```

### 添加新的分析维度

修改 `analyze_performance.py` 中的 `PerformanceAnalyzer` 类：

```python
def analyze_new_dimension(self) -> Dict[str, Any]:
    """新的分析维度"""
    # 实现分析逻辑
    pass
```

## 注意事项

1. **测试环境**：
   - 建议在相对空闲的系统上运行，避免其他程序干扰
   - 多次运行以获得稳定的性能数据

2. **数据量**：
   - 默认测试使用较小的数据集（50-500品种）
   - 可以修改测试代码增加数据量

3. **结果解读**：
   - 单次测试结果可能有波动，关注趋势而非绝对值
   - 对比不同配置的相对性能更有意义

4. **优化应用**：
   - 根据建议修改代码后，重新运行测试验证效果
   - 保留历史性能数据用于对比

## 文件清单

```
tests/e2e/
├── README_E2E.md                          # 本文档
├── test_loadbalancer_e2e_basic.py         # 基础功能测试
├── test_loadbalancer_e2e_variants.py      # 参数变化测试
├── analyze_performance.py                 # 性能分析脚本
├── run_all_e2e_tests.py                   # 一键运行脚本
└── performance_data.json                  # 性能数据（自动生成）
```

## 预期结果

运行完整测试套件后，你将获得：

1. ✅ **性能基准数据**：不同配置下的真实性能表现
2. ✅ **扩展性报告**：品种数量增加时的性能趋势
3. ✅ **瓶颈分析**：识别系统的主要瓶颈类型
4. ✅ **优化建议**：具体的、可操作的优化方向
5. ✅ **数据支持**：为调整决策矩阵和配置参数提供依据

## 常见问题

### Q: 测试运行很慢怎么办？
A: 可以减少测试的品种数量或跳过某些测试场景，修改 `test_counts` 或 `interval_configs`。

### Q: 如何清空历史数据？
A: 删除 `tests/e2e/performance_data.json` 文件即可。

### Q: 优化建议如何应用到代码？
A: 建议会指出具体的文件和方法，按照建议修改对应的配置参数或决策逻辑。

### Q: 可以添加自定义分析吗？
A: 可以，修改 `analyze_performance.py` 添加新的分析方法。

---

**最后更新**: 2025-10-24
**维护者**: LoadBalancer架构团队

