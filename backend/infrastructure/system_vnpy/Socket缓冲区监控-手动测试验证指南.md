# Socket缓冲区监控 - 手动测试验证指南

**版本**: v1.0  
**创建日期**: 2025-11-06

---

## 一、代码验证（已完成）

### ✅ 1.1 后端代码验证

**验证项**:
- ✅ `get_socket_buffer_info()` 方法已实现（monitor_system.py 行6039-6295）
- ✅ `get_network_subsystem_metrics()` 已集成socket缓冲区数据（行6318-6347）
- ✅ 阈值配置已注册（行2694-2706）
- ✅ 日志埋点已添加（9处）

**验证方法**:
```bash
# 查看代码实现
grep -n "def get_socket_buffer_info" backend/infrastructure/system_vnpy/monitor_system.py
grep -n "socket_buffer_info" backend/infrastructure/system_vnpy/monitor_system.py
```

### ✅ 1.2 前端代码验证

**验证项**:
- ✅ UnifiedMonitorCard已添加socket缓冲区显示（system_manager_view.py 行917-924, 951-993）
- ✅ NetworkMonitorCard已添加socket缓冲区显示（行1026-1033, 1084-1126）
- ✅ 详细数据表格已添加socket缓冲区行（行10084-10121）
- ✅ 数据更新调用已添加（行3892-3896）

**验证方法**:
```bash
# 查看前端实现
grep -n "update_socket_buffer_info" ui/modules/system_manager_view.py
grep -n "socket_buffer_info" ui/modules/system_manager_view.py
```

---

## 二、功能测试（需要应用运行）

### 2.1 启动应用

1. **启动应用**
   ```bash
   python main.py
   ```

2. **等待应用完全启动**
   - 等待监控进程启动
   - 等待前端UI加载完成

### 2.2 前端UI验证

#### 步骤1: 打开系统管理界面

1. 点击左侧菜单"系统管理"
2. 等待界面加载完成

#### 步骤2: 验证统一监控卡片

1. 找到"统一监控卡片"（显示CPU、网络、内存等指标的大卡片）
2. 查看卡片底部
3. **验证点**:
   - ✅ 应显示：`Socket缓冲区: 接收XXKB(XX%) 发送XXKB(XX%)`
   - ✅ 数值应实时更新（每秒刷新）
   - ✅ 如果使用率 > 80%，文字应为橙色
   - ✅ 如果使用率 > 95%，文字应为红色

#### 步骤3: 验证详细数据表格

1. 在系统管理界面中找到"详细数据表格"或"系统状态详情"
2. 滚动到"网络子系统"部分
3. **验证点**:
   - ✅ 应显示"Socket接收缓冲区"行
   - ✅ 应显示"Socket发送缓冲区"行
   - ✅ 应显示"TCP连接数"行
   - ✅ 数值应正确显示

#### 步骤4: 验证数据更新

1. 观察Socket缓冲区信息
2. 等待几秒钟
3. **验证点**:
   - ✅ 数值应实时更新
   - ✅ 使用率变化应反映在颜色上

### 2.3 日志验证

#### 步骤1: 查看日志文件

```bash
# Windows PowerShell
Get-Content logs\application_startup_*.log -Tail 100 | Select-String -Pattern "SOCKET-BUFFER"
```

#### 步骤2: 验证日志内容

**预期日志**:
```
[SOCKET-BUFFER] 获取到 XXX 个网络连接
[SOCKET-BUFFER] 统计完成: TCP连接=XX, ESTABLISHED=XX, ...
[NETWORK-SUBSYSTEM] Socket缓冲区信息已集成: TCP=XX, ...
```

**验证点**:
- ✅ 日志包含 `[SOCKET-BUFFER]` 前缀
- ✅ 日志包含 `[NETWORK-SUBSYSTEM]` 前缀
- ✅ 日志级别正确（DEBUG/INFO/WARNING）

---

## 三、Python交互式测试

### 3.1 启动Python交互式终端

```bash
python
```

### 3.2 测试数据采集

```python
# 导入模块
from backend.infrastructure.system_vnpy.monitor_system import SystemMonitor

# 创建监控器
monitor = SystemMonitor()

# 测试数据采集
buffer_info = monitor.get_socket_buffer_info()

# 查看结果
print("Socket缓冲区信息:")
print(f"  TCP连接数: {buffer_info.get('tcp_connections', 0)}")
print(f"  ESTABLISHED连接数: {buffer_info.get('established_connections', 0)}")
print(f"  接收缓冲区: {buffer_info.get('recv_buffer_size_avg', 0) / 1024:.0f}KB")
print(f"  发送缓冲区: {buffer_info.get('send_buffer_size_avg', 0) / 1024:.0f}KB")
print(f"  接收使用率: {buffer_info.get('recv_buffer_usage_ratio', 0.0):.1f}%")
print(f"  发送使用率: {buffer_info.get('send_buffer_usage_ratio', 0.0):.1f}%")
```

**预期输出**:
```
Socket缓冲区信息:
  TCP连接数: 120
  ESTABLISHED连接数: 85
  接收缓冲区: 85KB
  发送缓冲区: 85KB
  接收使用率: 15.2%
  发送使用率: 12.5%
```

### 3.3 测试网络子系统集成

```python
# 测试网络子系统集成
network_metrics = monitor.get_network_subsystem_metrics()

# 验证socket_buffer_info字段
if 'socket_buffer_info' in network_metrics:
    print("✅ socket_buffer_info字段存在")
    socket_buffer = network_metrics['socket_buffer_info']
    print(f"  TCP连接数: {socket_buffer.get('tcp_connections', 0)}")
else:
    print("❌ socket_buffer_info字段不存在")
```

---

## 四、浏览器开发者工具验证

### 4.1 打开开发者工具

1. 在应用界面按 `F12` 打开开发者工具
2. 切换到"Console"标签

### 4.2 检查前端错误

**验证点**:
- ✅ 控制台无JavaScript错误
- ✅ 无Socket缓冲区相关的错误信息

### 4.3 检查网络请求（可选）

1. 切换到"Network"标签
2. 观察是否有监控数据请求
3. 检查响应数据是否包含socket_buffer_info

---

## 五、验证检查清单

### 代码验证

- [x] 后端方法实现完整
- [x] 前端UI组件完整
- [x] 数据传递路径完整
- [x] 日志埋点完整

### 功能验证（需要应用运行）

- [ ] 前端UI显示Socket缓冲区信息
- [ ] 详细数据表格显示Socket缓冲区行
- [ ] 颜色预警机制工作正常
- [ ] 数据实时更新
- [ ] 日志输出正确

### 性能验证

- [ ] 数据采集性能正常（< 50ms）
- [ ] UI更新流畅
- [ ] 不影响系统性能

---

## 六、常见问题

### 6.1 数据未显示

**可能原因**:
1. 监控进程未启动
2. 权限不足无法获取socket信息
3. 无网络连接

**解决方法**:
1. 检查监控进程是否运行
2. 查看日志文件中的错误信息
3. 尝试以管理员权限运行

### 6.2 数据显示为0

**可能原因**:
1. 系统无TCP连接
2. 无法获取socket缓冲区大小（权限问题）

**解决方法**:
1. 启动一些网络连接（如浏览器访问网页）
2. 检查系统权限

### 6.3 UI更新延迟

**可能原因**:
1. 监控数据更新频率问题
2. 前端更新逻辑问题

**解决方法**:
1. 等待几秒钟观察
2. 检查前端更新逻辑

---

## 七、测试结果记录

### 测试环境

- **操作系统**: Windows 10
- **Python版本**: 3.10
- **测试时间**: 2025-11-06

### 测试结果

| 测试项 | 状态 | 备注 |
|--------|------|------|
| 代码实现 | ✅ | 所有代码已实现 |
| 数据采集 | ⏳ | 需要应用运行 |
| 前端显示 | ⏳ | 需要应用运行 |
| 日志输出 | ⏳ | 需要应用运行 |
| 性能测试 | ⏳ | 需要应用运行 |

---

## 八、下一步

1. **启动应用**进行实际功能测试
2. **验证前端UI**显示是否正确
3. **查看日志文件**验证日志埋点
4. **性能测试**验证性能指标

---

**测试状态**: 代码验证完成，等待应用运行后进行功能测试

