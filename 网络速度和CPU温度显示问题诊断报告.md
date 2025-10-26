# 网络速度和CPU温度显示问题诊断报告

**日期**: 2025-10-26
**问题**: 系统状态监控界面中网络速度和CPU温度没有读数
**诊断工具**: `diagnose_monitoring_data.py`

---

## 📊 诊断结果总结

### ✅ 监控进程数据采集正常

运行 `diagnose_monitoring_data.py` 的结果显示：

1. **网络速度数据** ✅ 正常
   - 上传速度: 1.58 KB/s
   - 下载速度: 72.52 KB/s
   - 数据路径: `data['system']['network_speed']`
   - 字段结构完整

2. **CPU温度数据** ✅ 正常
   - CPU: AMD Ryzen 7 7700
   - 温度: 70.37°C
   - 数据路径: `data['hardware']['temperature']['AMD Ryzen 7 7700']`
   - 字段结构完整

**结论**: 监控进程（端口5557）采集数据完全正常，问题在于数据流向UI的过程中。

---

## 🔍 问题分析

### 可能的原因

#### 1. 网络速度显示为0（正常现象）
- **分析**: 网络速度在系统空闲时确实可能为0
- **验证方法**:
  - 在网络活动时（如下载文件）查看是否有数据
  - 检查热力图的阈值设置是否合理

#### 2. CPU温度没有显示（需要检查事件流）

可能的断点位置：

**断点1: SystemManagerService事件分发**
- 位置: `backend/services/system_manager_service.py:3273-3278`
- 检查: `EVENT_HARDWARE_SENSORS` 事件是否被正确分发
- 日志关键字: `[DispatchEvents] ✅ 已分发 EVENT_HARDWARE_SENSORS`

**断点2: UI事件订阅**
- 位置: `ui/modules/system_manager_view.py:2136`
- 检查: UI是否正确订阅了 `EVENT_HARDWARE_SENSORS` 事件
- 日志关键字: `EventEngine已就绪，事件订阅成功`

**断点3: UI事件处理**
- 位置: `ui/modules/system_manager_view.py:2232-2261`
- 检查: `_on_hardware_sensors_event()` 是否被调用
- 检查: CPU温度卡片 `self.metric_card_cpu_temp` 是否存在

**断点4: UI更新节流**
- 位置: `ui/modules/system_manager_view.py:2407-2418`
- 检查: 热力图 `self.status_heatmap_cpu_temp` 是否存在
- 检查: `update_value()` 是否被调用

---

## 🛠️ 修复方案

### 方案1: 启用调试日志（已完成）

我已经在 `backend/services/system_manager_service.py` 中添加了硬件传感器事件的debug日志：

```python
# 事件2：硬件传感器
if "hardware" in data and data["hardware"]:
    event = Event(EVENT_HARDWARE_SENSORS, data["hardware"])
    self.event_engine.put(event)
    self.logger.debug(
        f"[DispatchEvents] ✅ 已分发 EVENT_HARDWARE_SENSORS, 数据keys: {list(data['hardware'].keys())}"
    )
```

**操作步骤**:
1. 重启程序
2. 设置日志级别为DEBUG（如果需要）
3. 查看日志中是否有 `[DispatchEvents] ✅ 已分发 EVENT_HARDWARE_SENSORS`

### 方案2: 检查UI事件订阅

检查 `ui/modules/system_manager_view.py` 中的事件订阅：

```python
# 检查这些代码是否执行
self.event_engine.register(EVENT_HARDWARE_SENSORS, self._on_hardware_sensors_event)
```

**验证方法**:
- 在 `_on_hardware_sensors_event` 方法开头添加日志
- 确认该方法是否被调用

### 方案3: 检查热力图组件初始化

检查 `ui/modules/system_manager_view.py` 中的热力图组件：

```python
# 确认这些组件是否被创建
self.status_heatmap_network_speed  # 网络速度热力图
self.status_heatmap_cpu_temp       # CPU温度热力图
```

**验证方法**:
- 检查 `_create_system_status_tab()` 是否被调用
- 确认该Tab是否被用户点击过（延迟创建机制）

### 方案4: 临时诊断脚本

运行以下脚本进行完整的事件流诊断：

```bash
# 1. 先启动主程序
.\启动终端（增强版）.bat

# 2. 在另一个终端运行诊断脚本
python check_event_flow.py
```

这将测试从监控进程到UI的完整事件流。

---

## 📝 详细检查清单

### 步骤1: 检查监控进程
- ✅ 监控进程是否运行: `tasklist | findstr python`
- ✅ ZMQ端口是否监听: `netstat -ano | findstr 5557`
- ✅ 监控数据是否正常: `python diagnose_monitoring_data.py`

### 步骤2: 检查SystemManagerService
- [ ] 监控推送线程是否启动
- [ ] ZMQ连接是否正常
- [ ] 事件分发日志是否存在
- [ ] EventEngine是否可用

**检查命令**:
```python
from backend.core.service_base import get_service_manager
service_manager = get_service_manager()
system_service = service_manager.get_service("system_manager_service")
print(f"EventEngine: {system_service.event_engine}")
print(f"监控推送运行: {system_service._monitoring_push_running}")
```

### 步骤3: 检查UI组件
- [ ] UI是否订阅了事件
- [ ] 事件处理函数是否被调用
- [ ] 热力图组件是否创建
- [ ] UI更新是否被节流阻止

**检查方法**:
在 `ui/modules/system_manager_view.py` 的以下位置添加日志：

```python
def _on_hardware_sensors_event(self, event):
    """处理硬件传感器事件."""
    # 添加日志
    print(f"🔥 收到硬件传感器事件: {event.data.keys()}")
    # ... 原有代码
```

### 步骤4: 检查数据路径
确认UI从正确的路径获取数据：

**网络速度**:
```python
# UI期望路径
network_speed = metrics.get("network_speed", {})
upload_speed = network_speed.get("upload_speed_kbps", 0)
download_speed = network_speed.get("download_speed_kbps", 0)
```

**CPU温度**:
```python
# UI期望路径
hardware_data = metrics.get("hardware", {})
temperature_data = hardware_data.get("temperature", {})
# 遍历查找CPU设备
for device_name, sensors in temperature_data.items():
    if any(keyword in device_name for keyword in ["CPU", "ACPI", "Ryzen", "Intel"]):
        cpu_temp = sensors[0].get("current", 0)
```

---

## 🎯 快速修复建议

### 如果网络速度始终为0

1. **增加网络活动**: 下载文件或播放在线视频
2. **调整热力图阈值**: 将警告阈值从50MB/s降低到5MB/s
3. **检查采样间隔**: 网络速度采样间隔为100ms，可能需要调整

### 如果CPU温度始终为0

1. **检查管理员权限**: LibreHardwareMonitor需要管理员权限
2. **重启程序**: 以管理员身份运行 `.\启动终端（增强版）.bat`
3. **检查DLL文件**: 确认 `backend/infrastructure/system_vnpy/librehardwaremonitor/LibreHardwareMonitorLib.dll` 存在
4. **查看错误日志**: 检查 `logs/monitor_stderr.log`

### 通用修复步骤

```bash
# 1. 停止所有Python进程
taskkill /F /IM python.exe

# 2. 清理日志（可选）
del logs\monitor_*.log
del logs\systemmanager_*.log

# 3. 以管理员身份重启
.\启动终端（增强版）.bat

# 4. 等待30秒让监控系统初始化
# 5. 切换到"系统管理"Tab
# 6. 等待数据更新（约1-2秒）
```

---

## 📚 相关文件

### 监控系统核心文件
- `backend/infrastructure/system_vnpy/monitor_system.py` - 监控进程
- `backend/infrastructure/system_vnpy/librehardwaremonitor/` - LibreHardwareMonitor
- `backend/services/system_manager_service.py` - 系统管理服务

### UI组件文件
- `ui/modules/system_manager_view.py` - 系统管理界面
- `ui/components/` - UI组件库

### 诊断工具
- `diagnose_monitoring_data.py` - 监控数据诊断
- `check_event_flow.py` - 事件流检查

### 日志文件
- `logs/monitor_process.log` - 监控进程日志
- `logs/monitor_stderr.log` - 监控进程错误日志
- `logs/systemmanager_debug.log` - UI调试日志（如果存在）

---

## 🔧 下一步行动

### 立即执行
1. ✅ 已添加debug日志到 `SystemManagerService._dispatch_monitoring_events()`
2. ⏳ 重启程序并查看日志
3. ⏳ 运行 `check_event_flow.py` 检查事件流

### 如果问题仍然存在
1. 在UI的 `_on_hardware_sensors_event()` 添加日志
2. 检查热力图组件的创建时机
3. 确认UI更新节流间隔是否合理

### 长期优化
1. 添加UI数据更新状态指示器
2. 在UI显示"数据源状态"（连接/断开/降级）
3. 为关键组件添加自检功能

---

## 💡 提示

### 网络速度为0是正常的
- 系统空闲时网络速度确实可能为0
- 不代表监控系统有问题
- 可以通过打开浏览器或下载文件来测试

### CPU温度需要管理员权限
- LibreHardwareMonitor必须以管理员权限运行
- 否则无法读取硬件传感器
- 启动脚本会自动请求管理员权限

### 事件驱动架构的特点
- 数据更新频率: 1-2秒
- UI更新节流: 1.5秒
- 可能会有1-3秒的延迟

---

**报告完成时间**: 2025-10-26
**工具版本**: v1.0
**状态**: ✅ 监控数据正常，待验证UI显示

