# Socket缓冲区监控 - 前后端联调测试方案

**版本**: v1.0
**创建日期**: 2025-11-06
**测试范围**: Socket缓冲区监控功能的前后端联调测试

---

## 一、测试目标

验证Socket缓冲区监控功能的完整实现，包括：
1. 后端数据采集功能
2. 数据传递路径（监控进程 → 服务层 → 前端）
3. 前端UI展示功能
4. 预警机制
5. 日志埋点

---

## 二、测试环境准备

### 2.1 前置条件

- ✅ 系统已启动，监控进程正常运行
- ✅ 前端UI已打开系统管理界面
- ✅ 网络连接正常（用于产生TCP连接）

### 2.2 测试工具

- 浏览器开发者工具（F12）
- 网络连接监控工具（如 `netstat -an` 或 `ss -tun`）
- 日志查看工具（查看 `logs/` 目录下的日志文件）

---

## 三、后端功能测试

### 3.1 Socket缓冲区数据采集测试

**测试步骤**：
1. 打开Python交互式终端
2. 导入并测试 `get_socket_buffer_info()` 方法

**测试代码**：
```python
from backend.infrastructure.system_vnpy.monitor_system import SystemMonitor

monitor = SystemMonitor()
buffer_info = monitor.get_socket_buffer_info()

# 验证返回数据结构
print("=== Socket缓冲区信息 ===")
print(f"TCP连接数: {buffer_info.get('tcp_connections', 0)}")
print(f"ESTABLISHED连接数: {buffer_info.get('established_connections', 0)}")
print(f"接收缓冲区平均大小: {buffer_info.get('recv_buffer_size_avg', 0) / 1024:.0f}KB")
print(f"发送缓冲区平均大小: {buffer_info.get('send_buffer_size_avg', 0) / 1024:.0f}KB")
print(f"接收缓冲区使用率: {buffer_info.get('recv_buffer_usage_ratio', 0.0):.1f}%")
print(f"发送缓冲区使用率: {buffer_info.get('send_buffer_usage_ratio', 0.0):.1f}%")
```

**预期结果**：
- ✅ 返回字典包含所有必需字段
- ✅ 数值类型正确（int/float）
- ✅ 缓冲区大小 > 0（如果系统有TCP连接）
- ✅ 使用率在 0-100% 范围内

### 3.2 网络子系统指标集成测试

**测试步骤**：
1. 测试 `get_network_subsystem_metrics()` 方法
2. 验证socket_buffer_info字段存在

**测试代码**：
```python
from backend.infrastructure.system_vnpy.monitor_system import SystemMonitor

monitor = SystemMonitor()
network_metrics = monitor.get_network_subsystem_metrics()

# 验证socket_buffer_info字段
socket_buffer = network_metrics.get('socket_buffer_info', {})
assert 'socket_buffer_info' in network_metrics, "socket_buffer_info字段缺失"
assert isinstance(socket_buffer, dict), "socket_buffer_info应该是字典类型"
assert 'recv_buffer_size_avg' in socket_buffer, "缺少recv_buffer_size_avg字段"
assert 'send_buffer_size_avg' in socket_buffer, "缺少send_buffer_size_avg字段"

print("✅ 网络子系统指标集成测试通过")
```

**预期结果**：
- ✅ `socket_buffer_info` 字段存在于返回字典中
- ✅ 字段类型为字典
- ✅ 包含所有必需的子字段

### 3.3 阈值配置测试

**测试步骤**：
1. 验证阈值配置已注册

**测试代码**：
```python
from backend.infrastructure.system_vnpy.monitor_system import AdaptiveThresholdManager

threshold_manager = AdaptiveThresholdManager()
all_thresholds = threshold_manager.get_all_thresholds()

# 验证socket缓冲区阈值已注册
socket_metrics = ['socket_recv_buffer_usage_ratio', 'socket_send_buffer_usage_ratio']
for metric in socket_metrics:
    assert metric in all_thresholds, f"阈值指标 {metric} 未注册"
    print(f"✅ {metric} 阈值已注册: {all_thresholds[metric]}")
```

**预期结果**：
- ✅ 两个socket缓冲区阈值指标已注册
- ✅ 警告阈值为80%
- ✅ 严重阈值为95%

---

## 四、数据传递路径测试

### 4.1 监控进程数据采集测试

**测试步骤**：
1. 通过native_ipc查询监控数据
2. 验证socket缓冲区数据存在

**测试代码**：
```python
import asyncio
import json
from backend.infrastructure.native.native_ipc import AsyncIPCPipe

async def test_monitoring_data():
    async with AsyncIPCPipe.client("monitor_query") as pipe:
        request = json.dumps({'action': 'get_data'}).encode()
        await pipe.write(request)
        response_data = await pipe.read()
        data = json.loads(response_data.decode())

        # 验证socket缓冲区数据
        network_subsystem = data.get('system', {}).get('network_subsystem', {})
        socket_buffer = network_subsystem.get('socket_buffer_info', {})

        assert socket_buffer, "Socket缓冲区数据不存在"
        print("✅ 监控进程数据采集测试通过")
        print(f"   TCP连接数: {socket_buffer.get('tcp_connections', 0)}")
        print(f"   接收缓冲区: {socket_buffer.get('recv_buffer_size_avg', 0) / 1024:.0f}KB")

asyncio.run(test_monitoring_data())
```

**预期结果**：
- ✅ 可以通过native_ipc获取数据
- ✅ socket_buffer_info字段存在且包含数据

### 4.2 服务层数据传递测试

**测试步骤**：
1. 通过SystemManagerService获取系统摘要
2. 验证socket缓冲区数据传递

**测试代码**：
```python
from backend.core.base import get_service_manager

service_mgr = get_service_manager()
system_service = service_mgr.get_service('system_manager_service')

# 获取监控数据
summary = system_service.get_system_summary()

# 验证数据路径
# 注意：实际数据路径可能需要根据get_system_summary的实现调整
print("✅ 服务层数据传递测试")
```

**预期结果**：
- ✅ 服务能够获取监控数据
- ✅ 数据包含socket缓冲区信息

---

## 五、前端UI测试

### 5.1 统一监控卡片显示测试

**测试步骤**：
1. 打开系统管理界面
2. 查看统一监控卡片（UnifiedMonitorCard）
3. 验证Socket缓冲区信息显示

**验证点**：
- ✅ 在卡片底部显示Socket缓冲区信息
- ✅ 格式：`Socket缓冲区: 接收XXKB(XX%) 发送XXKB(XX%)`
- ✅ 数值实时更新（每秒刷新）
- ✅ 颜色预警正常工作：
  - 使用率 < 80%：灰色
  - 使用率 80-95%：橙色（警告）
  - 使用率 > 95%：红色（严重）

**操作步骤**：
1. 启动应用
2. 打开"系统管理"界面
3. 观察统一监控卡片底部
4. 验证Socket缓冲区信息显示

### 5.2 详细数据表格显示测试

**测试步骤**：
1. 在系统管理界面中找到"详细数据表格"
2. 验证Socket缓冲区相关行

**验证点**：
- ✅ 显示"Socket接收缓冲区"行
  - 当前值：显示大小和使用率
  - 平均值：显示平均大小
  - 阈值：80%
- ✅ 显示"Socket发送缓冲区"行
  - 格式同上
- ✅ 显示"TCP连接数"行
  - 格式：ESTABLISHED/总数

**操作步骤**：
1. 在系统管理界面中找到详细数据表格
2. 滚动查看网络子系统部分
3. 验证Socket缓冲区相关行存在且数据正确

### 5.3 预警颜色测试

**测试步骤**：
1. 模拟高缓冲区使用率场景（需要实际网络活动）
2. 验证颜色预警

**验证点**：
- ✅ 使用率超过80%时，文字变为橙色
- ✅ 使用率超过95%时，文字变为红色
- ✅ 颜色变化实时生效

**模拟方法**：
- 启动大量网络连接（如批量下载）
- 观察Socket缓冲区使用率变化
- 验证颜色预警

---

## 六、日志埋点测试

### 6.1 日志输出验证

**测试步骤**：
1. 查看日志文件 `logs/application_startup_*.log`
2. 搜索Socket缓冲区相关日志

**验证点**：
- ✅ 存在 `[SOCKET-BUFFER]` 前缀的日志
- ✅ 存在 `[NETWORK-SUBSYSTEM]` 前缀的日志
- ✅ 日志级别正确（DEBUG/INFO/WARNING）
- ✅ 日志包含 `extra={"log_type": "SYSTEM"}` 或 `extra={"log_type": "ALERT"}`

**搜索关键词**：
```
[SOCKET-BUFFER]
[NETWORK-SUBSYSTEM]
socket_buffer_info
```

**预期日志示例**：
```
[SOCKET-BUFFER] 获取到 150 个网络连接
[SOCKET-BUFFER] 统计完成: TCP连接=120, ESTABLISHED=85, ...
[NETWORK-SUBSYSTEM] Socket缓冲区信息已集成: TCP=120, ...
```

### 6.2 告警日志测试

**测试步骤**：
1. 模拟高使用率场景
2. 验证告警日志

**验证点**：
- ✅ 使用率 > 80% 时，输出INFO级别日志
- ✅ 使用率 > 95% 时，输出WARNING级别日志（ALERT类型）
- ✅ 告警日志包含使用率数值

**预期日志示例**：
```
[SOCKET-BUFFER] ⚠️ Socket缓冲区使用率警告: 接收=85.2%, 发送=82.1%
[SOCKET-BUFFER] ⚠️ Socket缓冲区使用率严重告警: 接收=96.5%, 发送=94.2%
```

---

## 七、性能测试

### 7.1 采集性能测试

**测试步骤**：
1. 测量 `get_socket_buffer_info()` 执行时间
2. 验证性能指标

**测试代码**：
```python
import time
from backend.infrastructure.system_vnpy.monitor_system import SystemMonitor

monitor = SystemMonitor()

# 测试执行时间
times = []
for i in range(10):
    start = time.perf_counter()
    buffer_info = monitor.get_socket_buffer_info()
    elapsed = (time.perf_counter() - start) * 1000  # 转换为毫秒
    times.append(elapsed)
    print(f"第{i+1}次: {elapsed:.2f}ms")

avg_time = sum(times) / len(times)
max_time = max(times)
print(f"\n平均时间: {avg_time:.2f}ms")
print(f"最大时间: {max_time:.2f}ms")

# 验证性能指标
assert avg_time < 50, f"平均执行时间过长: {avg_time:.2f}ms"
assert max_time < 100, f"最大执行时间过长: {max_time:.2f}ms"
print("✅ 性能测试通过")
```

**预期结果**：
- ✅ 平均执行时间 < 50ms
- ✅ 最大执行时间 < 100ms
- ✅ 不影响系统性能

### 7.2 大量连接场景测试

**测试步骤**：
1. 创建大量TCP连接（模拟高负载）
2. 验证性能

**测试代码**：
```python
import socket
import threading
import time

# 创建多个TCP连接（模拟高负载）
connections = []
for i in range(100):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('www.baidu.com', 80))
        connections.append(sock)
    except:
        pass

print(f"创建了 {len(connections)} 个连接")

# 测试性能
monitor = SystemMonitor()
start = time.perf_counter()
buffer_info = monitor.get_socket_buffer_info()
elapsed = (time.perf_counter() - start) * 1000

print(f"执行时间: {elapsed:.2f}ms")
print(f"TCP连接数: {buffer_info.get('tcp_connections', 0)}")

# 清理连接
for sock in connections:
    try:
        sock.close()
    except:
        pass
```

**预期结果**：
- ✅ 即使有大量连接，执行时间仍在可接受范围内
- ✅ 数据采集正确

---

## 八、异常场景测试

### 8.1 权限不足测试

**测试场景**：无权限访问网络连接信息

**验证点**：
- ✅ 返回空字典而不是抛出异常
- ✅ 记录警告日志
- ✅ 不影响其他监控功能

### 8.2 无网络连接测试

**测试场景**：系统无网络连接

**验证点**：
- ✅ 返回空连接数据
- ✅ 缓冲区大小和使用率为0
- ✅ 不抛出异常

### 8.3 psutil不可用测试

**测试场景**：psutil模块未安装

**验证点**：
- ✅ 返回空字典
- ✅ 记录调试日志
- ✅ 不影响系统运行

---

## 九、前后端联调测试流程

### 9.1 完整测试流程

1. **启动系统**
   ```bash
   # 启动应用
   python main.py
   ```

2. **验证后端数据采集**
   - 执行测试代码3.1和3.2
   - 验证数据采集正常

3. **验证数据传递**
   - 执行测试代码4.1
   - 验证数据通过native_ipc传递

4. **验证前端显示**
   - 打开系统管理界面
   - 验证UI显示（测试5.1和5.2）

5. **验证预警机制**
   - 模拟高使用率场景
   - 验证颜色预警（测试5.3）

6. **验证日志埋点**
   - 查看日志文件
   - 验证日志输出（测试6.1和6.2）

7. **性能测试**
   - 执行性能测试（测试7.1和7.2）

8. **异常测试**
   - 测试异常场景（测试8.1-8.3）

### 9.2 测试检查清单

- [ ] 后端数据采集功能正常
- [ ] 数据传递路径完整
- [ ] 前端UI正确显示
- [ ] 预警机制工作正常
- [ ] 日志埋点正确
- [ ] 性能指标达标
- [ ] 异常场景处理正确
- [ ] 文档更新完整

---

## 十、测试结果记录

### 10.1 测试结果模板

```
测试日期: 2025-11-06
测试环境: Windows 10 / Python 3.10
测试人员: [姓名]

测试项 | 状态 | 备注
-------|------|------
后端数据采集 | ✅/❌ |
数据传递 | ✅/❌ |
前端UI显示 | ✅/❌ |
预警机制 | ✅/❌ |
日志埋点 | ✅/❌ |
性能测试 | ✅/❌ |
异常处理 | ✅/❌ |

问题记录:
1. [问题描述]
2. [问题描述]

修复记录:
1. [修复内容]
2. [修复内容]
```

### 10.2 性能测试结果

```
平均执行时间: XX.XX ms
最大执行时间: XX.XX ms
TCP连接数: XXX
缓冲区大小: XX KB
使用率: XX.XX%
```

---

## 十一、问题排查指南

### 11.1 数据未显示

**可能原因**：
1. 监控进程未启动
2. native_ipc连接失败
3. 数据采集失败（权限不足）

**排查步骤**：
1. 检查监控进程是否运行
2. 查看日志文件中的错误信息
3. 验证系统权限

### 11.2 数据异常

**可能原因**：
1. 缓冲区大小计算错误
2. 使用率估算不准确
3. 连接统计错误

**排查步骤**：
1. 对比系统工具（netstat）的统计结果
2. 检查日志中的调试信息
3. 验证计算公式

### 11.3 UI显示异常

**可能原因**：
1. 前端代码错误
2. 数据格式不匹配
3. 更新逻辑错误

**排查步骤**：
1. 检查浏览器控制台错误
2. 验证数据格式
3. 检查更新方法调用

---

## 十二、回归测试

### 12.1 回归测试项

- [ ] 原有网络监控功能不受影响
- [ ] 其他监控指标正常
- [ ] 系统性能无下降
- [ ] 日志系统正常

### 12.2 兼容性测试

- [ ] Windows平台测试
- [ ] Linux平台测试（如可用）
- [ ] 不同Python版本测试

---

**测试完成标准**：
- 所有测试项通过
- 无严重性能问题
- 无阻塞性bug
- 文档完整

