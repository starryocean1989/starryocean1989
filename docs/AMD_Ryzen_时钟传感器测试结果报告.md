# -*- coding: utf-8 -*-
# AMD Ryzen 7 7700 时钟传感器测试结果报告

## 测试环境

- CPU: AMD Ryzen 7 7700
- 目标最大频率: 5.3 GHz (5300 MHz)
- EXE 版本状态: ✅ 可以正常显示最大频率 5.3 GHz

## 测试结果

### 1. LibreHardwareMonitor DLL 直接访问

**结果**: ❌ 失败

**现象**:
- 能够找到 8 个核心的时钟传感器（Core #1 到 Core #8）
- 所有传感器的 `Value` 和 `Max` 属性都返回 `NaN`
- 即使添加 CPU 负载，仍然返回 `NaN`

**日志示例**:
```
时钟传感器返回 NaN: 设备=AMD Ryzen 7 7700, 传感器=Core #1, 标识=/amdcpu/0/clock/1
```

### 2. WMI 备选方案

**结果**: ⚠️ 部分成功

**现象**:
- WMI 可以读取 CPU 频率
- 但只能读取到基础频率：3801 MHz
- **无法读取最大频率（5.3 GHz）**

**WMI 输出**:
```
CPU: AMD Ryzen 7 7700 8-Core Processor
最大时钟速度: 3801 MHz
当前时钟速度: 3801 MHz
```

## 问题分析

### 为什么 EXE 版本可以工作？

EXE 版本可能使用了以下方法之一：

1. **特殊的访问方式**
   - 可能使用了不同的 API 或方法访问时钟传感器
   - 可能有特定的初始化顺序或参数

2. **不同的更新策略**
   - 可能使用了更复杂的更新策略
   - 可能有特殊的等待或重试机制

3. **权限或驱动**
   - 可能使用了不同的权限级别
   - 可能加载了特定的驱动程序

4. **DLL 版本差异**
   - EXE 版本可能使用了不同版本的 LibreHardwareMonitor DLL
   - 或者 DLL 版本相同，但调用方式不同

## 可能的解决方案

### 方案1：检查 DLL 版本

**步骤**:
1. 检查 EXE 版本使用的 LibreHardwareMonitor DLL 版本
2. 确保项目中使用相同版本的 DLL
3. 检查 DLL 文件的签名和日期

**命令**:
```powershell
# 查看 DLL 文件信息
Get-Item "path\to\LibreHardwareMonitorLib.dll" | Select-Object VersionInfo
```

### 方案2：使用 WMI 获取最大频率

**优点**:
- WMI 可以读取基础频率
- 实现简单，稳定可靠

**缺点**:
- 无法读取最大频率（Turbo Boost）
- 只能读取到基础频率 3801 MHz

**实现**:
```python
import wmi
w = wmi.WMI()
for proc in w.Win32_Processor():
    base_freq = proc.MaxClockSpeed  # 基础频率
    current_freq = proc.CurrentClockSpeed  # 当前频率
```

### 方案3：使用 psutil 作为备选

**优点**:
- Python 标准库，跨平台
- 可以读取当前频率

**缺点**:
- 在某些系统上可能无法读取最大频率
- Windows 上可能受限

**实现**:
```python
import psutil
cpu_freq = psutil.cpu_freq()
if cpu_freq:
    current = cpu_freq.current
    min_freq = cpu_freq.min
    max_freq = cpu_freq.max  # 可能不包含 Turbo Boost
```

### 方案4：检查 EXE 版本的实现

**步骤**:
1. 使用反编译工具查看 EXE 版本的实现
2. 或者查看 LibreHardwareMonitor 的源代码
3. 对比 DLL 调用方式的差异

**GitHub 仓库**:
- https://github.com/LibreHardwareMonitor/LibreHardwareMonitor

### 方案5：使用其他监控库

**选项**:
1. **HWiNFO** - 商业软件，功能强大
2. **Open Hardware Monitor** - LibreHardwareMonitor 的前身
3. **CoreTemp** - 专门用于 CPU 温度监控

## 当前代码状态

### ✅ 已完成的修复

1. **NaN 值过滤**
   - 正确过滤 NaN 值，不会返回无效数据
   - 添加了诊断日志

2. **改进的更新策略**
   - 先更新所有硬件
   - 等待传感器稳定
   - 多次更新确保值已刷新

3. **诊断工具**
   - 创建了详细的测试脚本
   - 可以诊断问题

### ⚠️ 仍存在的问题

1. **时钟传感器返回 NaN**
   - LibreHardwareMonitor DLL 无法读取 AMD Ryzen 7 7700 的时钟频率
   - 即使采用多种策略（多次更新、CPU 负载）仍然失败

## 建议

### 短期方案

1. **使用 WMI 作为备选**
   - 虽然只能读取基础频率，但至少可以正常工作
   - 对于大多数用途，基础频率已经足够

2. **组合使用多个数据源**
   ```python
   # 优先级：LibreHardwareMonitor > WMI > psutil
   max_freq = None

   # 尝试 LibreHardwareMonitor
   if lhm_max_freq and not math.isnan(lhm_max_freq):
       max_freq = lhm_max_freq
   # 备选：WMI
   elif wmi_max_freq:
       max_freq = wmi_max_freq
   # 最后：psutil
   elif psutil_max_freq:
       max_freq = psutil_max_freq
   ```

### 长期方案

1. **深入调查 EXE 版本的实现**
   - 查看 LibreHardwareMonitor 源代码
   - 对比 EXE 和 DLL 的调用差异

2. **联系 LibreHardwareMonitor 开发者**
   - 报告 AMD Ryzen 7 7700 时钟传感器问题
   - 寻求技术支持

3. **考虑使用其他监控库**
   - 如果问题持续存在，考虑使用其他库

## 测试脚本

已创建以下测试脚本：

1. `test_amd_ryzen_clock_sensor.py` - 基础测试
2. `test_amd_ryzen_clock_with_load.py` - 带 CPU 负载的测试

## 结论

虽然 LibreHardwareMonitor EXE 版本可以正常工作，但通过 DLL 调用仍然无法读取 AMD Ryzen 7 7700 的时钟频率。建议：

1. **暂时使用 WMI 作为备选方案**，至少可以读取基础频率
2. **继续调查 EXE 版本的实现方式**，找出差异
3. **向 LibreHardwareMonitor 项目报告问题**，寻求官方支持

## 相关文件

- `backend/infrastructure/system_vnpy/librehardwaremonitor/lhm_extended.py` - 主要实现
- `test_amd_ryzen_clock_sensor.py` - 测试脚本
- `test_amd_ryzen_clock_with_load.py` - 带负载的测试脚本
- `docs/LibreHardwareMonitor_AMD_Ryzen_NaN_问题修复报告.md` - 修复报告


