# -*- coding: utf-8 -*-
# 测试套件使用指南

**更新日期**: 2025-10-25

---

## 📋 目录结构

```
tests/
├── CLEANUP_ANALYSIS_REPORT.md          # 测试清理分析报告
├── README.md                            # 本文档
├── benchmark_2000tasks.py               # 2000任务量级性能测试（新增）
├── performance_monitoring.py            # 性能监控系统（新增）
├── performance_history.db               # 性能历史数据库（自动生成）
├── PERFORMANCE_REPORT.html              # 性能监控报告（自动生成）
├── BENCHMARK_2000TASKS_REPORT.md        # 2000任务测试报告（自动生成）
│
├── e2e/                                 # E2E测试目录
│   ├── benchmark_suite.py               # 基准测试套件（已扩展）
│   ├── conftest.py                      # pytest配置
│   ├── test_*.py                        # 各种E2E测试
│   └── ...
│
├── test_*.py                            # 根目录测试
└── archive/                             # 归档目录（清理后的旧文件）
```

---

## 🎯 快速开始

### 1. 测试清理（推荐先执行）

**步骤1**：查看清理分析报告
```bash
# 查看报告
cat tests/CLEANUP_ANALYSIS_REPORT.md
```

**步骤2**：执行清理（需要用户确认）
- 报告提供了详细的清理方案
- 建议采用保守清理方案（方案A）
- 可减少30%的测试文件数量

### 2. 2000任务量级性能测试

**快速测试**（约20个参数组合，耗时~10分钟）：
```bash
cd C:\Users\USER\Desktop\terminal_v0.50
python tests/benchmark_2000tasks.py quick
```

**完整测试**（约100个参数组合，耗时~2-3小时）：
```bash
python tests/benchmark_2000tasks.py full
```

**输出文件**：
- `tests/benchmark_2000tasks_raw.jsonl` - 原始数据（JSONL格式）
- `tests/benchmark_2000tasks_summary.json` - 汇总数据
- `tests/BENCHMARK_2000TASKS_REPORT.md` - 性能报告

### 3. 性能监控系统

**记录测试结果**：
```python
from tests.performance_monitoring import PerformanceMonitor, TestRecord
from datetime import datetime

monitor = PerformanceMonitor()

# 记录测试结果
record = TestRecord(
    test_id="test_20251025_001",
    test_date=datetime.now().isoformat(),
    test_type="quick",  # 或 "full" 或 "scalability"
    config={"worker_count": 8, "batch_size": 50},
    duration=12.5,
    cpu_avg=65.3,
    memory_avg=320.5,
    throughput=160.0,
    score=85.6,
)

monitor.record_test_result(record)
```

**建立性能基线**：
```python
# 建立基线（使用最近10次测试）
baseline = monitor.establish_baseline("quick", sample_count=10)
```

**对比基线**：
```python
# 对比当前测试与基线
comparison = monitor.compare_with_baseline(record)
print(comparison['message'])
```

**生成HTML报告**：
```python
# 生成可视化HTML报告
monitor.generate_html_report()
# 输出: tests/PERFORMANCE_REPORT.html
```

---

## 📊 测试类型说明

### E2E测试（tests/e2e/）

#### LoadBalancer相关
- `test_loadbalancer_e2e_basic.py` - 基础性能数据收集
- `test_loadbalancer_e2e_variants.py` - 参数变化测试
- `test_multiprocess_optimization.py` - 多进程优化验证
- `test_scalability.py` - 扩展性测试
- `test_pressure_scenarios.py` - 压力场景测试
- `test_dynamic_adjustment.py` - 动态调整测试
- `test_production_integration.py` - 生产环境集成
- `test_ab_testing_real_data.py` - A/B测试（真实数据）
- `test_parameter_tuning.py` - 参数调优

#### 监控系统测试
- `test_monitor_lifecycle.py` - 监控进程生命周期
- `test_monitor_handshake.py` - 监控进程握手
- `test_monitor_port_conflict.py` - 端口冲突处理

#### 数据模块测试
- `test_data_quality.py` - 数据质量扫描
- `test_data_download.py` - 数据下载
- `test_data_center_reload_symbols.py` - 品种重载
- `test_unified_data_manager.py` - 统一数据管理器

#### 任务队列测试
- `test_queue_integration.py` - 队列集成测试

### 根目录测试（tests/）

#### UI测试
- `test_ui_components.py` - UI组件单元测试
- `test_ui_integration.py` - UI集成测试
- `test_ui_performance_tab.py` - 性能标签页测试
- `test_ui_refactoring_phase2.py` - UI重构测试

#### 数据测试
- `test_chart_data_integration.py` - 图表数据集成
- `test_ipo_cache.py` - IPO缓存测试
- `test_module_integration.py` - 模块集成

#### 任务队列测试
- `test_task_queue.py` - 任务队列单元测试

---

## 🔧 运行测试

### 使用pytest

**运行所有测试**：
```bash
pytest tests/ -v
```

**运行E2E测试**：
```bash
pytest tests/e2e/ -v
```

**运行快速测试**：
```bash
pytest -m quick tests/
```

**运行慢速测试**（完整测试）：
```bash
pytest -m slow tests/
```

**并行运行**（需要pytest-xdist）：
```bash
pytest tests/ -n auto -v
```

### 直接运行

某些测试文件可以直接运行：
```bash
python tests/benchmark_2000tasks.py
python tests/performance_monitoring.py
python tests/e2e/test_loadbalancer_e2e_basic.py
```

---

## 📈 性能基线管理

### 建立基线的最佳实践

1. **首次运行时建立基线**
   ```python
   monitor = PerformanceMonitor()
   baseline = monitor.establish_baseline("quick", sample_count=10)
   ```

2. **定期更新基线**（每月或重大优化后）
   ```python
   # 重新建立基线
   baseline = monitor.establish_baseline("quick", sample_count=20)
   ```

3. **每次测试后对比基线**
   ```python
   comparison = monitor.compare_with_baseline(test_record)
   if comparison['status'] == 'regression':
       print("⚠️ 性能退化，需要关注！")
   ```

### 基线数据管理

- 基线数据存储在`tests/performance_history.db`
- 使用SQLite数据库，可用任何SQLite工具查看
- 支持多种测试类型的独立基线

---

## 🎨 生成报告

### 性能监控HTML报告

```python
from tests.performance_monitoring import PerformanceMonitor

monitor = PerformanceMonitor()
monitor.generate_html_report()
# 输出: tests/PERFORMANCE_REPORT.html
```

**报告包含**：
- 测试总数统计
- 平均性能指标
- 按测试类型分组的详细数据
- 性能趋势图占位符

### 2000任务测试报告

```python
from tests.benchmark_2000tasks import Benchmark2000Tasks

benchmark = Benchmark2000Tasks()
# ... 运行测试 ...
benchmark.generate_report()
# 输出: tests/BENCHMARK_2000TASKS_REPORT.md
```

**报告包含**：
- 最优配置Top 10
- 推荐配置参数
- 性能表现分析
- 参数影响分析

---

## 🔍 测试清理方案

根据`CLEANUP_ANALYSIS_REPORT.md`的分析：

### 建议删除（移动到archive/）

**临时验证脚本**（3个）：
- `simple_verification.py`
- `verify_improvements.py`
- `verify_performance.py`

**重复测试**（6个）：
- `e2e/test_500_symbols.py`（已被test_scalability.py覆盖）
- `e2e/test_1000_symbols.py`（已被test_scalability.py覆盖）
- `e2e/test_short_term_simple.py`（简化版，已过时）
- `e2e/test_ab_testing_real_data_quick.py`（可合并）
- `e2e/test_ab_testing_real_sample.py`（可合并）
- `e2e/test_parameter_tuning_quick.py`（可合并）

### 建议合并（5个 → 2个）

**A/B测试合并**：
- 保留：`test_ab_testing_real_data.py` → 重命名为 `test_ab_testing.py`
- 删除：`test_ab_testing_real_data_quick.py`、`test_ab_testing_real_sample.py`

**参数调优合并**：
- 保留：`test_parameter_tuning.py`
- 删除：`test_parameter_tuning_quick.py`

**短期优化合并**：
- 保留：`test_short_term_optimization.py`
- 删除：`test_short_term_safe.py`

### 执行清理

```bash
# 创建归档目录
mkdir tests/archive

# 移动文件到归档
mv tests/simple_verification.py tests/archive/
mv tests/verify_improvements.py tests/archive/
mv tests/verify_performance.py tests/archive/
# ... 其他文件
```

**清理收益**：
- 减少14个文件（30%）
- 测试结构更清晰
- 减少维护成本

---

## 🚀 下一步优化

### 阶段四：优化system_vnpy与LoadBalancer集成

- [ ] 增强ResourcePressureEvaluator使用V2.5子系统指标
- [ ] 在LoadBalancer中集成实时监控事件订阅
- [ ] 创建集成测试验证监控与LoadBalancer协同

### 阶段五：应用最优配置

- [ ] 根据benchmark_2000tasks测试结果提取最优参数
- [ ] 更新LoadBalancer默认参数
- [ ] 创建场景化配置文件`config/loadbalancer_profiles.json`
- [ ] 更新文档

---

## 📚 相关文档

- `CLEANUP_ANALYSIS_REPORT.md` - 测试清理分析报告
- `BENCHMARK_2000TASKS_REPORT.md` - 2000任务测试报告（运行后生成）
- `PERFORMANCE_REPORT.html` - 性能监控HTML报告（运行后生成）
- `e2e/README.md` - E2E测试文档（数据中心）
- `e2e/README_E2E.md` - LoadBalancer E2E文档

---

## ⚠️ 注意事项

1. **测试环境**：
   - 建议在系统相对空闲时运行性能测试
   - 关闭其他占用资源的应用
   - 确保有足够的磁盘空间

2. **测试数据**：
   - 某些测试需要真实的本地数据
   - 确保`data/cache/stock_list_classified.json`存在
   - TDX和Parquet数据文件应该准备好

3. **性能测试耗时**：
   - 快速测试（quick）：约10-20分钟
   - 完整测试（full）：约2-3小时
   - 建议先运行quick模式验证

4. **数据库管理**：
   - `performance_history.db`会持续增长
   - 可定期清理旧数据（保留最近3-6个月）
   - 备份重要的基线数据

---

## 🤝 贡献指南

### 添加新测试

1. 在合适的目录创建测试文件
2. 遵循命名规范：`test_<feature>_<type>.py`
3. 添加适当的pytest标记（@pytest.mark.quick/@pytest.mark.slow）
4. 更新本README文档

### 报告问题

- 记录测试失败时的详细错误信息
- 包含系统环境信息
- 提供可复现的步骤

---

**文档版本**: v1.0
**最后更新**: 2025-10-25

