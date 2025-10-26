# K线下载任务详细日志说明

## 功能简介

每次K线下载时，系统会自动创建一个详细的CSV日志文件，记录每个下载任务的详细信息，包括：

- 品种代码、周期
- 使用的服务器IP和端口
- 服务器所属的券商/机构名称
- 任务状态（成功/失败/超时/异常）
- 数据条数、耗时
- Worker ID、连接ID、阶段标识

## 日志文件位置

日志文件会自动保存在 `logs/` 目录下，文件名格式：
```
kline_task_details_YYYYMMDD_HHMMSS.csv
```

例如：`logs/kline_task_details_20251025_191723.csv`

## CSV文件格式

| 列名 | 说明 | 示例 |
|------|------|------|
| 时间戳 | 任务完成时间 | 2025-10-25 19:17:23.145 |
| 任务ID | 唯一任务标识 | 000001_1m_1729851443145 |
| 品种代码 | 股票代码 | 000001 |
| 周期 | K线周期 | 1m, 5m, 1d |
| 服务器IP | 服务器IP地址 | 110.41.147.114 |
| 服务器Port | 服务器端口 | 7709 |
| 所属券商/机构 | 券商或机构名称 | 深圳双线主站1 |
| 任务状态 | success/failed/timeout/exception | success |
| 错误信息 | 失败原因（如有） | 请求超时0.2s |
| 数据条数 | 返回的数据条数 | 800 |
| 耗时(秒) | 任务执行时长 | 0.152 |
| Worker ID | Worker进程ID | 0 |
| Connection ID | 连接ID | 5 |
| Phase | 阶段标识 | Phase1, Phase2 |

## 使用场景

### 1. 分析失败任务与服务器的关系

```python
import pandas as pd

# 读取日志文件
df = pd.read_csv('logs/kline_task_details_20251025_191723.csv')

# 查看失败任务
failed_tasks = df[df['任务状态'] != 'success']

# 按券商统计失败率
failure_by_broker = failed_tasks.groupby('所属券商/机构').size()
print(failure_by_broker.sort_values(ascending=False))

# 查看哪些券商的服务器失败最多
broker_stats = df.groupby('所属券商/机构').agg({
    '任务状态': lambda x: (x != 'success').sum(),  # 失败数
    '品种代码': 'count'  # 总数
})
broker_stats['失败率'] = broker_stats['任务状态'] / broker_stats['品种代码']
print(broker_stats.sort_values('失败率', ascending=False))
```

### 2. 分析超时问题

```python
# 查看超时任务
timeout_tasks = df[df['任务状态'] == 'timeout']

# 按服务器IP统计超时次数
timeout_by_server = timeout_tasks.groupby('服务器IP').size()
print(timeout_by_server.sort_values(ascending=False))

# 查看超时最多的券商
timeout_by_broker = timeout_tasks.groupby('所属券商/机构').size()
print(timeout_by_broker.sort_values(ascending=False))
```

### 3. 分析性能问题

```python
# 查看平均耗时
avg_time_by_broker = df[df['任务状态'] == 'success'].groupby('所属券商/机构')['耗时(秒)'].mean()
print(avg_time_by_broker.sort_values(ascending=False))

# 查看哪些服务器最慢
avg_time_by_server = df[df['任务状态'] == 'success'].groupby('服务器IP')['耗时(秒)'].mean()
print(avg_time_by_server.sort_values(ascending=False))
```

### 4. 查看socket.send()异常的服务器

```python
# 查看异常任务
exception_tasks = df[df['任务状态'] == 'exception']

# 按券商统计
exception_by_broker = exception_tasks.groupby('所属券商/机构').size()
print("异常最多的券商:")
print(exception_by_broker.sort_values(ascending=False).head(10))

# 按服务器IP统计
exception_by_ip = exception_tasks.groupby('服务器IP').size()
print("\n异常最多的服务器IP:")
print(exception_by_ip.sort_values(ascending=False).head(10))

# 查看具体异常信息
print("\n具体异常信息:")
print(exception_tasks[['品种代码', '周期', '服务器IP', '所属券商/机构', '错误信息']].head(20))
```

## 特性

1. **实时写入**：每个任务完成后立即写入磁盘（使用`flush`和`fsync`），即使下载中断也能保存已记录的数据
2. **自动映射**：自动从constants.py加载服务器-券商映射，无需手动配置
3. **全面覆盖**：记录所有任务状态（成功、失败、超时、异常）
4. **详细信息**：包含服务器、耗时、阶段等完整信息

## 注意事项

1. 日志文件使用UTF-8编码，可用Excel或任何文本编辑器打开
2. 建议定期清理旧日志文件，避免占用过多磁盘空间
3. 每次下载会创建新的日志文件，不会覆盖之前的记录
4. 如果下载被中断（Ctrl+C），已记录的数据仍然会保存在文件中

## 快速诊断示例

```python
# 一键诊断脚本
import pandas as pd
import glob
import os

# 找到最新的日志文件
log_files = glob.glob('logs/kline_task_details_*.csv')
latest_log = max(log_files, key=os.path.getctime)

print(f"分析日志: {latest_log}")
df = pd.read_csv(latest_log)

print("\n=== 总体统计 ===")
print(f"总任务数: {len(df)}")
print(f"成功: {(df['任务状态'] == 'success').sum()}")
print(f"失败: {(df['任务状态'] == 'failed').sum()}")
print(f"超时: {(df['任务状态'] == 'timeout').sum()}")
print(f"异常: {(df['任务状态'] == 'exception').sum()}")

print("\n=== 问题最多的券商 (Top 5) ===")
failed = df[df['任务状态'] != 'success']
print(failed.groupby('所属券商/机构').size().sort_values(ascending=False).head(5))

print("\n=== 问题最多的服务器 (Top 5) ===")
print(failed.groupby('服务器IP').size().sort_values(ascending=False).head(5))

print("\n=== 平均耗时 (Top 5 最慢) ===")
success = df[df['任务状态'] == 'success']
print(success.groupby('所属券商/机构')['耗时(秒)'].mean().sort_values(ascending=False).head(5))
```

保存为 `analyze_task_log.py` 并运行：
```bash
cd C:\Users\USER\Desktop\terminal_v0.50
python analyze_task_log.py
```

