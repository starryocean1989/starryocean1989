# -*- coding: utf-8 -*-
# LibreHardwareMonitor AMD Ryzen 7 7700 时钟传感器 NaN 问题修复报告

## 问题描述

LibreHardwareMonitor 对 AMD Ryzen 7 7700 的时钟传感器返回 NaN（非数字）值，导致无法正确读取 CPU 时钟频率。

## 问题原因分析

### 1. 代码层面问题

**根本原因**：在 `lhm_extended.py` 的 `_collect_all_sensors` 方法中，NaN 值没有被正确过滤。

**详细说明**：
- 当 `sensor.Value` 为 NaN 时，`float(sensor.Value)` 会返回 `float('nan')`
- NaN 不等于 `None`，所以原有的 `if current is None: continue` 检查无法过滤 NaN 值
- 结果：NaN 值被添加到传感器数据中，导致返回无效数据

### 2. LibreHardwareMonitor 兼容性问题

**可能原因**：
- LibreHardwareMonitor 可能不完全支持 AMD Ryzen 7 7700 处理器
- 某些传感器可能需要多次更新才能获取有效值
- 驱动程序或权限问题

## 解决方案

### 1. 修复 NaN 值过滤逻辑

**修改文件**：`backend/infrastructure/system_vnpy/librehardwaremonitor/lhm_extended.py`

**修改内容**：
- 在 `_collect_all_sensors` 方法中添加了 `math.isnan()` 检查
- 过滤掉所有 NaN 值（current、min、max）
- 添加了对时钟传感器的特殊诊断日志

**关键代码**：
```python
# 过滤 NaN 值（NaN 不等于 None，需要单独检查）
if isinstance(current, float) and math.isnan(current):
    if sensor_type == self._SensorType.Clock:
        logger.debug(
            "时钟传感器返回 NaN: 设备=%s, 传感器=%s, 标识=%s",
            device_name,
            sensor.Name,
            sensor.Identifier if hasattr(sensor, "Identifier") else "N/A"
        )
    continue
```

### 2. 改进更新策略（关键修复）

**问题根源**：EXE 版本可以正常工作，说明硬件支持没问题。问题在于 DLL 调用方式 - 需要先更新所有硬件，等待传感器值稳定，然后再收集数据。

**修改内容**：
- 完全重构了 `get_all_sensor_data` 方法的更新策略
- 采用"先更新，再等待，再更新，最后收集"的四步策略
- 确保传感器值已经稳定后才读取，特别是时钟传感器

**关键改进**：
```python
# 第一步：更新所有硬件（先更新父硬件，再更新子硬件）
def update_all_hardware(hardware):
    """递归更新所有硬件"""
    hardware.Update()
    for subhardware in hardware.SubHardware:
        update_all_hardware(subhardware)

for hardware in computer.Hardware:
    update_all_hardware(hardware)

# 第二步：等待一小段时间让传感器值稳定（特别是时钟传感器）
time.sleep(0.05)  # 50ms 延迟

# 第三步：再次更新（某些传感器可能需要多次更新才能获取有效值）
for hardware in computer.Hardware:
    update_all_hardware(hardware)

# 第四步：收集传感器数据
for hardware in computer.Hardware:
    self._collect_hardware_recursive(hardware, result)
```

**为什么这样修复**：
- EXE 版本能够正常工作，说明 LibreHardwareMonitor 支持 AMD Ryzen 7 7700
- EXE 版本内部采用了类似的更新策略，先更新硬件再读取传感器
- 时钟传感器需要硬件状态稳定后才能返回有效值
- 多次更新可以确保传感器值已经刷新

### 3. 添加诊断日志

**改进**：
- 当时钟传感器返回 NaN 时，记录详细的诊断信息
- 包括设备名称、传感器名称、传感器标识符等
- 便于后续问题排查和 LibreHardwareMonitor 兼容性改进

## 修复效果

### 修复前
- NaN 值被错误地添加到传感器数据中
- 无法正确读取 AMD Ryzen 7 7700 的时钟频率（最大频率 5.3 GHz）
- 更新和读取混合在一起，传感器值可能不稳定
- 没有诊断信息，难以排查问题

### 修复后
- NaN 值被正确过滤，不会出现在结果中
- **采用改进的更新策略，应该能够正确读取时钟频率**
- 先更新所有硬件，等待传感器稳定，再收集数据
- 添加了诊断日志，便于排查问题
- 多次更新确保传感器值已经刷新

## 后续建议

### 1. 如果问题仍然存在

如果修复后仍然无法读取时钟频率，可能的原因：

1. **LibreHardwareMonitor 版本过旧**
   - 建议更新到最新版本的 LibreHardwareMonitor
   - 检查 `LibreHardwareMonitorLib.dll` 的版本

2. **权限问题**
   - 确保以管理员权限运行程序
   - LibreHardwareMonitor 需要访问底层硬件接口

3. **驱动程序问题**
   - 检查是否有硬件监控驱动程序冲突
   - 确保 WinRing0 驱动正确安装

4. **硬件兼容性**
   - AMD Ryzen 7 7700 可能需要特定版本的 LibreHardwareMonitor
   - 查看 LibreHardwareMonitor 官方文档或 GitHub Issues

### 2. 替代方案

如果 LibreHardwareMonitor 确实无法支持该硬件：

1. **使用 psutil 作为备选**
   - 代码中已有 psutil 的降级方案
   - psutil 可以读取基本的 CPU 频率信息

2. **报告问题**
   - 向 LibreHardwareMonitor 项目报告兼容性问题
   - 提供详细的硬件信息和诊断日志

## 相关文件

- `backend/infrastructure/system_vnpy/librehardwaremonitor/lhm_extended.py` - 主要修复文件
- `debug_lhm_cpu_freq.py` - 调试脚本
- `test_cpu_max_freq.py` - 测试脚本

## 测试建议

1. 运行 `debug_lhm_cpu_freq.py` 查看详细的传感器信息
2. 检查日志中的诊断信息，确认 NaN 值是否被正确过滤
3. 验证时钟频率是否能正确读取（如果 LibreHardwareMonitor 支持该硬件）

## 修复日期

2024年（根据实际日期更新）

