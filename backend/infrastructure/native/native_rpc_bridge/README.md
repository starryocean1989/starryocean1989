# -*- coding: utf-8 -*-
# native_rpc_bridge 扩展

多语言 RPC 桥接模块，负责在 C 扩展层封装共享内存队列、事件同步与序列化，加速 Python 与子进程（或外部语言）之间的通信。

## 功能概述

- `RpcBridge`：封装请求/响应双向通道，支持同步与异步调用。
- `publish(event, payload)`：向共享缓冲区写入事件并唤醒目标进程。
- `await_response(timeout_ms)`：阻塞等待对端返回结果，支持超时控制。
- Python 层若检测到扩展缺失，会回退到纯 Python IPC 实现。

## 日志埋点（阶段5）

### C层日志
- **协议验证**：检查RPC魔数、版本、头大小，记录协议不匹配错误
- **缓冲区检查**：验证缓冲区长度，记录缓冲区错误和预期大小
- **序列化操作**：记录请求创建、序列化过程和结果
- **反序列化操作**：记录响应解析、数据提取和错误处理

### Python层守卫器
- 为所有导出函数添加 `@native_call_guard(component="backend.native.rpc_bridge")` 装饰器
- 捕获异常并通过统一日志系统记录，包含组件信息和错误上下文
- 降级模式使用 `@native_call_guard(component="backend.native.rpc_bridge.fallback")`

### 关键日志场景
1. **协议不匹配**：`ERROR` 级别，记录期望值vs实际值
2. **缓冲区错误**：`ERROR` 级别，记录缓冲区大小和所需大小
3. **序列化失败**：`ERROR` 级别，记录失败的具体步骤和上下文
4. **正常操作**：`INFO/DEBUG` 级别，记录操作摘要和统计信息

## 编译

```bash
cd backend/infrastructure/native/native_rpc_bridge
python setup.py build_ext --inplace
```

> 推荐运行 `backend/infrastructure/native/compile_all.bat`，脚本会自动编译全部扩展（含本模块），并在遇到错误时暂停输出日志。

## 示例

```python
from native_rpc_bridge import RpcBridge

bridge = RpcBridge(buffer_size=65536)
bridge.publish("load-config", {"service": "strategy"})
reply = bridge.await_response(timeout_ms=500)
```

## 测试

### 集成测试
运行 `python test_stage5_simple.py` 验证：
- 日志桥接功能正常
- RPC桥接头创建和序列化工作
- 序列化批量操作正常

### 日志验证
```python
# 验证日志输出
from backend.infrastructure.native.native_rpc_bridge import create_request_header

# 这将触发 INFO 级别日志记录操作摘要
header = create_request_header(1, 1024)

# 模拟错误情况验证错误日志
# （需要构造特定的错误条件）
```

## 调试方式

### 日志配置
```python
import logging
from backend.infrastructure.native.logging_bridge import install_native_logging_bridge

# 配置详细日志
logger = logging.getLogger("backend.native.bridge")
logger.setLevel(logging.DEBUG)

# 安装桥接
install_native_logging_bridge(logger=logger)
```

### 常见问题排查
1. **无日志输出**：检查 `backend.infrastructure.native.logging_bridge` 模块是否正确导入
2. **协议错误**：查看 `ERROR` 级别日志，检查魔数和版本匹配
3. **缓冲区问题**：查看缓冲区大小相关的错误日志
4. **序列化失败**：检查 pickle 模块是否可用，查看序列化步骤的错误日志

## 依赖

- Windows 平台、Python 3.8+。
- Visual Studio Build Tools、Windows SDK。
- numpy / struct（作为示例中 payload 序列化依赖）。


