# 队列深度增长率监控 E2E 测试结果

## 目录说明

此目录用于存储 E2E 测试的结果文件。

## 文件类型

### 1. 日志文件 (`queue_depth_e2e_*.log`)
- 包含完整的测试执行日志
- 每秒输出一行资源监控数据
- 记录所有协程调整操作

### 2. 指标文件 (`metrics_*.json`)
- JSON格式的结构化数据
- 包含以下内容：
  - `test_info`: 测试基本信息
  - `data_points`: 每秒采集的资源数据点
  - `adjustment_history`: 协程调整历史
  - `stats`: 统计汇总

## 日志格式示例

```
[0001] 14:23:45 | CPU:  45.2% | 内存:  52.3% | 队列深度:   2.0
[0002] 14:23:46 | CPU:  48.5% | 内存:  53.1% | 队列深度:   3.5
>>> 📉 减少协程: 20 -> 19 (-1) | 原因: 磁盘队列快速累积
[0003] 14:23:47 | CPU:  46.8% | 内存:  52.8% | 队列深度:   2.1
```

## 指标文件结构

```json
{
  "test_info": {
    "start_time": "14:23:45",
    "end_time": "14:25:30",
    "duration_seconds": 105,
    "monitor_interval": 1.0
  },
  "data_points": [
    {
      "seq": 1,
      "timestamp": 1698234225.123,
      "datetime": "14:23:45",
      "cpu_percent": 45.2,
      "memory_percent": 52.3,
      "queue_depth": 2.0
    }
  ],
  "adjustment_history": [
    {
      "timestamp": 1698234226.456,
      "datetime": "14:23:46",
      "old_concurrency": 20,
      "new_concurrency": 19,
      "delta": -1,
      "reason": "磁盘队列快速累积"
    }
  ],
  "stats": {
    "total_samples": 105,
    "cpu": {"avg": 46.5, "min": 42.1, "max": 51.3, "std": 2.4},
    "memory": {"avg": 52.8, "min": 50.2, "max": 55.1, "std": 1.6},
    "queue_depth": {"avg": 2.5, "min": 0.0, "max": 8.2, "std": 1.8},
    "adjustments": 3
  }
}
```

## 分析要点

1. **资源稳定性**：
   - CPU/内存标准差 < 5% 表示稳定
   - 队列深度标准差 < 3 表示稳定

2. **调整有效性**：
   - 观察调整时机是否合理
   - 调整后资源使用率是否下降

3. **监控周期**：
   - 1秒周期是否能及时捕获变化
   - 是否需要缩短至0.5秒

4. **队列深度增长率**：
   - 预警是否在达到上限前触发
   - 增长率阈值是否合理

