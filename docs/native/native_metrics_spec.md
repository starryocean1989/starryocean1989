# -*- coding: utf-8 -*-
# native_metrics C 扩展接口规范

## 1. 设计目标

- **进程指标聚合（`native_process_metrics`）**：以单次 C 调用返回监控进程所需的系统 / 进程概览数据，替代 `psutil.process_iter` 多次遍历。
- **Socket 缓冲区增强（`native_socket_metrics` 扩展）**：在现有 `get_socket_metrics()` 基础上补充连接状态与失败原因统计，确保在权限受限或连接量大时仍可快速返回结果。
- **兼容性要求**：
  - Windows 平台优先实现，接口留出 Linux/macOS 回退路径。
  - 若 C 扩展不可用，Python 端继续沿用 `psutil`/WMI 回退逻辑。
  - 所有函数在发生错误时返回 `None` 或抛出 `RuntimeError`，由 Python 层捕获并降级。

## 2. `native_process_metrics` 接口定义

### 2.1 导出符号

```c
PyObject *get_system_metrics(PyObject *self, PyObject *args);
PyObject *get_process_snapshot(PyObject *self, PyObject *args);
```

### 2.2 `get_system_metrics`

**输入参数**：无。

**返回结构（PyDict）**：

```json
{
  "cpu_percent": float,          // 总体 CPU 使用率（0-100）
  "memory_percent": float,       // 总体内存使用率
  "swap_percent": float,         // 交换区使用率（无交换区则为 0）
  "disk_read_bytes": uint64,     // 累计磁盘读取字节
  "disk_write_bytes": uint64,    // 累计磁盘写入字节
  "net_sent_bytes": uint64,      // 累计网络发送字节
  "net_recv_bytes": uint64,      // 累计网络接收字节
  "timestamp": uint64            // UNIX 毫秒时间戳
}
```

**实现建议**：
- Windows：使用 `PdhCollectQueryData`/`GetSystemTimes`/`GetIfEntry2` 等 API。
- Linux：可使用 `/proc/stat`、`/proc/net/dev`，作为后续拓展。

### 2.3 `get_process_snapshot`

**输入参数**：

```python
get_process_snapshot(pid: int) -> dict | None
```

- `pid == 0` 时返回系统内所有进程的聚合信息。
- 其他正整数时返回指定进程信息；若进程不存在返回 `None`。

**返回结构**：

```json
{
  "pid": int,
  "name": str,
  "exe": str,                    // 可执行路径，权限不足时为空串
  "username": str,
  "cpu_percent": float,
  "memory_percent": float,
  "memory_rss": uint64,
  "memory_vms": uint64,
  "num_threads": uint32,
  "handles": uint32,             // Windows 句柄数
  "io_read_bytes": uint64,
  "io_write_bytes": uint64,
  "create_time": uint64,         // UNIX 秒
  "cmdline": list[str],
  "status": str,                 // running/sleeping/其他（与 psutil 对齐）
  "children": list[int]          // 子进程 PID（顶层汇总使用，可选）
}
```

**批量获取**：当 `pid == 0` 时，返回结构为 `{"processes": [ ... ], "aggregate": {...}}`，其中 `aggregate` 提供进程总数、线程总数、僵尸进程计数等。

**错误处理**：权限不足时应将对应字段置空，并附加键 `"permission_error": true`。

## 3. `native_socket_metrics` 扩展

### 3.1 现状
`native_socket_metrics.get_socket_metrics()` 当前仅返回缓冲区容量/估算使用率，对连接状态统计仍需回退到 `psutil.net_connections`。

### 3.2 新增字段

```json
{
  "recv_buffer_size_avg": int,
  "send_buffer_size_avg": int,
  ...,
  "tcp_states": {
    "ESTABLISHED": int,
    "LISTEN": int,
    "TIME_WAIT": int,
    ...
  },
  "socket_failures": {
    "permission_denied": int,
    "other_error": int
  }
}
```

- `tcp_states`：统计所有 TCP 套接字状态，便于 UI/告警模块快速评估连接情况。
- `socket_failures`：记录枚举过程中的权限或系统错误次数，供日志输出和降级判断。

### 3.3 API 扩充

```c
PyObject *get_socket_metrics(PyObject *self, PyObject *args);
PyObject *get_socket_metrics_detailed(PyObject *self, PyObject *args);
```

- `get_socket_metrics()`：保持兼容（返回核心字段）。
- `get_socket_metrics_detailed(include_udp: bool = False)`：新增详细接口；当 `include_udp=True` 时统计 UDP 套接字。

## 4. 错误与降级约定

| 场景 | C 扩展行为 | Python 回退 | 监控日志 |
| --- | --- | --- | --- |
| 权限不足 | 抛出 `PermissionError` | 捕获后返回 `{}`/`None`，调用现有 `psutil` 逻辑 | 输出 `logger.debug("native metrics fallback...")` |
| API 不可用（XP、旧版本） | 抛出 `NotImplementedError` | Python 层直接降级 | 记 INFO 级日志，提示操作系统版本 |
| 其他异常 | 抛出 `RuntimeError` | Python 层捕获后降级 | 记录 ALERT 级日志并附带异常栈 |

## 5. 集成步骤概览

1. **编写 C 扩展**：
   - 目录建议：`backend/infrastructure/native/native_process_metrics/`、`native_socket_metrics/`（扩展现有模块）。
   - `setup.py` 更新统一注册。

2. **Python 层适配**：
   - `monitor_system.py`：
     - 优先调用新接口；失败时落回 `psutil`。
     - 新增诊断字段输出。
   - `monitor_toolkit.py`：为测试/CLI 工具提供快速自检函数。

3. **单元与基准测试**：
   - 在 `backend/infrastructure/native/tests/` 新增针对 API 的单测。
   - 提供 `perf_monitor_baseline.py` 基准脚本，对比 psutil 与原生路径的耗时。

4. **文档与配置**：
   - 更新 `native/README.md`，说明新模块与编译条件。
   - 在启动文档 & 优化5 报告中标注实际落地进展。

## 6. 未决问题

- Linux/macOS 支持优先级：短期内可标记为 TODO，确保接口可编译但返回 `NotImplementedError`。
- 跨平台依赖：Windows 实现可使用 `Pdh`/`NtQuerySystemInformation`/`GetExtendedTcpTable`；需要在 README 指出最低支持版本（建议 Win10+）。
- 安全性：访问句柄信息或带宽统计可能触发杀毒软件或 UAC；需在文档中提示权限需求。

---

本规范用于指导 `native_process_metrics` 与强化版 `native_socket_metrics` 的实现与集成，后续迭代可在此基础上补充更多平台及指标。 

