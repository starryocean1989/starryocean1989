# CPU 散热不匹配诊断指南

## 一、散热不匹配的典型迹象

当 CPU 散热器（风扇+散热片）无法有效散热时，会出现以下迹象：

### 1.1 温度相关迹象 ⭐⭐⭐

#### 🔴 **严重迹象**（需要立即处理）

1. **待机/空闲温度过高**
   - **正常**: < 40°C（AMD Ryzen 7 7700）
   - **不匹配**: > 50°C（待机时）
   - **严重**: > 60°C（待机时）
   - **判断**: 开机后等待 10 分钟，不运行任何程序，CPU 温度仍 > 50°C

2. **轻负载温度快速上升**
   - **正常**: 轻度负载（20-30%）< 60°C
   - **不匹配**: 轻度负载就 > 70°C
   - **严重**: 轻度负载就 > 80°C
   - **判断**: 打开几个浏览器标签页，CPU 温度就超过 70°C

3. **满载温度达到或超过安全阈值**
   - **正常**: 满载（100%）< 85°C
   - **不匹配**: 满载 > 90°C
   - **严重**: 满载 > 95°C（触发降频）
   - **极端**: 满载 > 100°C（可能触发保护）

4. **温度无法稳定**
   - **正常**: 满载时温度会上升，但能在某个值稳定（例如 75-80°C）
   - **不匹配**: 温度持续上升，无法稳定
   - **严重**: 温度上升速度 > 1°C/秒

#### 🟡 **警告迹象**（需要关注）

5. **温度上升速度过快**
   - **正常**: 从待机到满载，温度上升时间 > 30 秒
   - **不匹配**: 温度上升时间 < 10 秒
   - **判断**: 运行压力测试，温度在 10 秒内从 40°C 升到 80°C

6. **温度下降缓慢**
   - **正常**: 负载降低后，温度在 1-2 分钟内下降 10-20°C
   - **不匹配**: 负载降低后，温度下降很慢（> 5 分钟才下降 10°C）
   - **判断**: 停止压力测试后，温度下降速度 < 2°C/分钟

### 1.2 性能相关迹象 ⭐⭐⭐

#### 🔴 **严重迹象**

7. **CPU 频繁降频**
   - **正常**: 满载时能维持接近最大频率（例如 5.0+ GHz）
   - **不匹配**: 满载时频率明显低于最大频率（例如 < 4.5 GHz）
   - **严重**: 满载时频率降到基础频率或更低（< 3.8 GHz）
   - **判断**: 使用 CPU-Z 或 HWiNFO 监控频率，发现满载时频率持续下降

8. **性能不稳定**
   - **正常**: 持续满载时性能稳定
   - **不匹配**: 性能波动大，有时快有时慢
   - **判断**: 运行 Cinebench 多次，分数波动 > 10%

9. **系统卡顿或延迟**
   - **正常**: 高负载时系统响应正常
   - **不匹配**: 高负载时系统卡顿、延迟明显
   - **严重**: 高负载时系统无响应或蓝屏

### 1.3 风扇行为相关迹象 ⭐⭐

#### 🔴 **严重迹象**

10. **风扇长期满速运行**
    - **正常**: 待机时风扇低转速（< 1500 RPM），满载时高转速（3000-4000 RPM）
    - **不匹配**: 待机时风扇就高转速（> 2500 RPM）
    - **严重**: 风扇一直 100% 转速（最大转速）
    - **判断**: 即使 CPU 负载很低，风扇转速仍然很高

11. **风扇转速无法有效降温**
    - **正常**: 风扇转速提升后，温度会在 1-2 分钟内下降
    - **不匹配**: 风扇 100% 转速，但温度仍在上升或无法下降
    - **判断**: 风扇满速运行 5 分钟，温度仍 > 85°C

12. **风扇噪音持续过大**
    - **正常**: 待机时安静，满载时有一定噪音
    - **不匹配**: 待机时就有明显噪音
    - **严重**: 风扇噪音持续过大，影响使用体验

### 1.4 功耗相关迹象 ⭐

13. **功耗与温度不匹配**
    - **正常**: 低功耗（< 30W）时温度 < 50°C
    - **不匹配**: 低功耗时温度就 > 60°C
    - **判断**: CPU 功耗 20W，但温度 > 60°C

14. **功耗受限**
    - **正常**: 满载时能达到标称 TDP（65W for Ryzen 7 7700）
    - **不匹配**: 满载时功耗被限制（< 50W），因为温度过高

## 二、诊断测试方法

### 2.1 待机温度测试

**测试步骤**：
1. 开机后等待 10 分钟，不运行任何程序
2. 监控 CPU 温度 5 分钟，记录平均值
3. **判断标准**：
   - ✅ **正常**: < 40°C
   - ⚠️ **不匹配**: 40-50°C
   - 🔴 **严重不匹配**: > 50°C

### 2.2 轻负载温度测试

**测试步骤**：
1. 打开 5-10 个浏览器标签页
2. 运行一些轻量级应用（例如文本编辑器、音乐播放器）
3. CPU 负载约 20-30%
4. 监控 CPU 温度 5 分钟
5. **判断标准**：
   - ✅ **正常**: < 60°C
   - ⚠️ **不匹配**: 60-70°C
   - 🔴 **严重不匹配**: > 70°C

### 2.3 满载温度测试（压力测试）

**测试工具**：
- Prime95（CPU 压力测试）
- AIDA64（系统稳定性测试）
- Cinebench（CPU 渲染测试）
- HWiNFO（监控温度、频率、功耗）

**测试步骤**：
1. 启动监控软件（HWiNFO 或 LibreHardwareMonitor）
2. 运行压力测试 10-15 分钟
3. 记录以下指标：
   - 最高温度
   - 稳定温度（5 分钟后的平均值）
   - CPU 频率（是否降频）
   - 风扇转速
   - CPU 功耗

**判断标准**：
- ✅ **正常**:
  - 最高温度 < 85°C
  - 稳定温度 < 80°C
  - 频率接近最大频率（> 4.5 GHz）
  - 风扇转速 < 3500 RPM
- ⚠️ **不匹配**:
  - 最高温度 85-90°C
  - 稳定温度 80-85°C
  - 频率轻微下降（4.0-4.5 GHz）
  - 风扇转速 > 3500 RPM
- 🔴 **严重不匹配**:
  - 最高温度 > 90°C
  - 稳定温度 > 85°C
  - 频率明显下降（< 4.0 GHz 或降到基础频率）
  - 风扇转速 100%（最大转速）

### 2.4 温度响应速度测试

**测试步骤**：
1. 记录待机温度（例如 40°C）
2. 立即运行压力测试
3. 记录温度达到 80°C 的时间
4. **判断标准**：
   - ✅ **正常**: > 30 秒
   - ⚠️ **不匹配**: 10-30 秒
   - 🔴 **严重不匹配**: < 10 秒

### 2.5 温度下降速度测试

**测试步骤**：
1. 运行压力测试直到温度稳定（例如 85°C）
2. 立即停止压力测试
3. 记录温度下降到 60°C 的时间
4. **判断标准**：
   - ✅ **正常**: < 2 分钟
   - ⚠️ **不匹配**: 2-5 分钟
   - 🔴 **严重不匹配**: > 5 分钟

## 三、诊断代码示例

### 3.1 使用 LibreHardwareMonitor 诊断

```python
from backend.infrastructure.system_vnpy.librehardwaremonitor.lhm_extended import ExtendedLHMWrapper
import time

def diagnose_cpu_cooling():
    """诊断 CPU 散热是否匹配"""
    lhm = ExtendedLHMWrapper()

    # 1. 待机温度测试
    print("=== 待机温度测试 ===")
    time.sleep(10)  # 等待系统稳定
    sensor_data = lhm.get_all_sensor_data()
    idle_temp = get_cpu_temp(sensor_data)
    print(f"待机温度: {idle_temp}°C")

    if idle_temp > 50:
        print("🔴 警告: 待机温度过高，散热可能不匹配")
    elif idle_temp > 40:
        print("⚠️  注意: 待机温度偏高")
    else:
        print("✅ 待机温度正常")

    # 2. 检查风扇转速
    fan_rpm = get_cpu_fan_rpm(sensor_data)
    print(f"风扇转速: {fan_rpm} RPM")

    if idle_temp > 50 and fan_rpm < 1500:
        print("🔴 严重警告: 温度高但风扇转速低，散热不匹配")
    elif idle_temp > 50 and fan_rpm > 3000:
        print("🔴 警告: 温度高且风扇满速，散热不足")

    # 3. 满载测试（需要用户手动运行压力测试）
    print("\n=== 满载测试 ===")
    print("请运行压力测试（Prime95 或 AIDA64）10 分钟...")
    input("按 Enter 继续...")

    sensor_data = lhm.get_all_sensor_data()
    load_temp = get_cpu_temp(sensor_data)
    load_freq = get_cpu_freq(sensor_data)
    load_fan_rpm = get_cpu_fan_rpm(sensor_data)

    print(f"满载温度: {load_temp}°C")
    print(f"CPU 频率: {load_freq} GHz")
    print(f"风扇转速: {load_fan_rpm} RPM")

    # 判断
    if load_temp > 90:
        print("🔴 严重警告: 满载温度过高，散热严重不匹配")
    elif load_temp > 85:
        print("⚠️  警告: 满载温度偏高，散热可能不匹配")

    if load_freq < 3.8:
        print("🔴 严重警告: CPU 降频，散热不足")
    elif load_freq < 4.5:
        print("⚠️  警告: CPU 频率下降，散热可能不足")

    if load_fan_rpm > 3500 and load_temp > 85:
        print("🔴 警告: 风扇满速但温度仍高，散热不匹配")

def get_cpu_temp(sensor_data):
    """获取 CPU 温度"""
    temp_data = sensor_data.get("temperature", {})
    for device, sensors in temp_data.items():
        if "CPU" in device and sensors:
            return sensors[0].get("current", 0)
    return None

def get_cpu_fan_rpm(sensor_data):
    """获取 CPU 风扇转速"""
    fan_data = sensor_data.get("fan", {})
    for device, sensors in fan_data.items():
        for sensor in sensors:
            if "CPU" in sensor.get("label", ""):
                return sensor.get("current", 0)
    return None

def get_cpu_freq(sensor_data):
    """获取 CPU 频率"""
    clock_data = sensor_data.get("clock", {})
    for device, sensors in clock_data.items():
        if "CPU" in device and sensors:
            # 取所有核心的平均频率
            freqs = [s.get("current", 0) for s in sensors if s.get("current")]
            if freqs:
                return sum(freqs) / len(freqs) / 1000  # MHz to GHz
    return None
```

### 3.2 自动诊断脚本

```python
def auto_diagnose_cooling_mismatch(sensor_data, cpu_model="AMD Ryzen 7 7700"):
    """自动诊断散热是否匹配"""
    issues = []
    warnings = []

    temp_data = sensor_data.get("temperature", {})
    fan_data = sensor_data.get("fan", {})
    clock_data = sensor_data.get("clock", {})
    power_data = sensor_data.get("power", {})

    # 获取 CPU 温度
    cpu_temp = None
    for device, sensors in temp_data.items():
        if "CPU" in device and sensors:
            cpu_temp = sensors[0].get("current", 0)
            break

    if cpu_temp is None:
        return {"status": "unknown", "message": "无法读取 CPU 温度"}

    # 获取 CPU 风扇转速
    cpu_fan_rpm = None
    for device, sensors in fan_data.items():
        for sensor in sensors:
            if "CPU" in sensor.get("label", ""):
                cpu_fan_rpm = sensor.get("current", 0)
                break
        if cpu_fan_rpm:
            break

    # 获取 CPU 功耗
    cpu_power = None
    for device, sensors in power_data.items():
        if "CPU" in device and sensors:
            cpu_power = sensors[0].get("current", 0)
            break

    # 诊断规则
    # 1. 待机温度过高
    if cpu_temp > 50 and cpu_power and cpu_power < 20:
        issues.append({
            "severity": "严重",
            "type": "待机温度过高",
            "message": f"待机温度 {cpu_temp}°C 过高（功耗 {cpu_power}W），散热可能不匹配"
        })
    elif cpu_temp > 40 and cpu_power and cpu_power < 20:
        warnings.append({
            "type": "待机温度偏高",
            "message": f"待机温度 {cpu_temp}°C 偏高"
        })

    # 2. 风扇转速与温度不匹配
    if cpu_fan_rpm:
        if cpu_temp > 70 and cpu_fan_rpm < 2000:
            issues.append({
                "severity": "严重",
                "type": "风扇转速不足",
                "message": f"温度 {cpu_temp}°C 但风扇转速仅 {cpu_fan_rpm} RPM，可能风扇故障或控制异常"
            })
        elif cpu_temp > 50 and cpu_fan_rpm > 3500:
            warnings.append({
                "type": "风扇转速过高",
                "message": f"温度 {cpu_temp}°C 但风扇转速 {cpu_fan_rpm} RPM 很高，散热可能不足"
            })

    # 3. 功耗与温度不匹配
    if cpu_power and cpu_temp:
        temp_per_watt = cpu_temp / cpu_power if cpu_power > 0 else 0
        if temp_per_watt > 1.5:  # 每瓦特温度 > 1.5°C/W
            issues.append({
                "severity": "警告",
                "type": "散热效率低",
                "message": f"温度功耗比 {temp_per_watt:.2f}°C/W 过高，散热效率低"
            })

    # 4. CPU 频率检查（如果可用）
    cpu_freq = None
    if clock_data:
        for device, sensors in clock_data.items():
            if "CPU" in device and sensors:
                freqs = [s.get("current", 0) for s in sensors if s.get("current") and s.get("current") > 0]
                if freqs:
                    cpu_freq = sum(freqs) / len(freqs) / 1000  # MHz to GHz
                    break

    if cpu_freq and cpu_freq < 3.8:  # 低于基础频率
        issues.append({
            "severity": "严重",
            "type": "CPU 降频",
            "message": f"CPU 频率 {cpu_freq:.2f} GHz 低于基础频率，可能因过热降频"
        })

    # 汇总结果
    if issues:
        status = "不匹配"
        severity = max([i["severity"] for i in issues])
    elif warnings:
        status = "可能不匹配"
        severity = "警告"
    else:
        status = "正常"
        severity = None

    return {
        "status": status,
        "severity": severity,
        "cpu_temp": cpu_temp,
        "cpu_fan_rpm": cpu_fan_rpm,
        "cpu_power": cpu_power,
        "cpu_freq": cpu_freq,
        "issues": issues,
        "warnings": warnings
    }
```

## 四、散热匹配标准（AMD Ryzen 7 7700）

### 4.1 理想散热表现

| 场景 | CPU 温度 | CPU 频率 | 风扇转速 | CPU 功耗 |
|------|---------|---------|---------|---------|
| **待机** | < 40°C | 3.8-5.3 GHz（动态） | < 1500 RPM | < 20W |
| **轻负载（30%）** | < 60°C | 4.5-5.0 GHz | 1500-2500 RPM | 30-40W |
| **中等负载（60%）** | < 70°C | 4.5-5.0 GHz | 2500-3200 RPM | 50-60W |
| **满载（100%）** | < 85°C | 4.5-5.3 GHz | 3000-4000 RPM | 65W（TDP） |

### 4.2 不匹配的表现

| 场景 | CPU 温度 | CPU 频率 | 风扇转速 | 判断 |
|------|---------|---------|---------|------|
| **待机** | > 50°C | 正常 | > 2500 RPM | 🔴 不匹配 |
| **轻负载** | > 70°C | 正常 | > 3000 RPM | 🔴 不匹配 |
| **满载** | > 90°C | < 4.5 GHz | 100%（最大） | 🔴 严重不匹配 |
| **满载** | > 85°C | < 4.0 GHz | 100%（最大） | 🔴 严重不匹配 |

## 五、可能的原因

### 5.1 散热器问题

1. **散热器规格不足**
   - 散热器 TDP 能力 < CPU TDP（例如：40W 散热器用于 65W CPU）
   - 散热器太小或设计不佳

2. **安装问题**
   - 散热器未正确安装（未贴紧 CPU）
   - 硅脂涂抹不当（太多、太少、不均匀）
   - 硅脂老化或质量差

3. **散热器损坏**
   - 散热片堵塞（灰尘过多）
   - 热管失效（水冷系统的泵故障）
   - 风扇故障或转速不足

### 5.2 机箱环境问题

1. **风道不畅**
   - 机箱进气不足
   - 机箱排气不足
   - 线缆阻挡风道

2. **环境温度过高**
   - 机箱内环境温度高
   - 周围设备散热影响

### 5.3 BIOS 设置问题

1. **风扇控制设置不当**
   - 风扇曲线设置过于保守
   - 风扇转速限制过低

2. **CPU 功耗设置**
   - PPT/TDC/EDC 限制设置不当
   - 电压设置不当

## 六、解决方案

### 6.1 立即措施

1. **检查散热器安装**
   - 重新安装散热器，确保贴紧 CPU
   - 更换硅脂（使用高质量硅脂）

2. **清理灰尘**
   - 清理散热器灰尘
   - 清理机箱灰尘
   - 清理风扇灰尘

3. **检查风扇**
   - 确认风扇正常工作
   - 检查风扇连接
   - 在 BIOS 中检查风扇转速

### 6.2 长期措施

1. **升级散热器**
   - 选择 TDP 能力 > CPU TDP 的散热器（建议 1.5 倍以上）
   - 选择知名品牌的优质散热器
   - 考虑水冷散热器（更好的散热能力）

2. **改善机箱环境**
   - 增加机箱风扇
   - 优化风道设计
   - 改善机箱布局

3. **调整 BIOS 设置**
   - 优化风扇曲线
   - 调整 CPU 功耗限制（如果需要）

## 七、总结

### 关键判断标准：

1. **待机温度 > 50°C** → 🔴 散热不匹配
2. **轻负载温度 > 70°C** → 🔴 散热不匹配
3. **满载温度 > 90°C** → 🔴 严重不匹配
4. **CPU 降频（频率 < 基础频率）** → 🔴 严重不匹配
5. **风扇满速但温度仍高** → 🔴 散热不匹配

### 诊断流程：

1. ✅ 检查待机温度
2. ✅ 检查轻负载温度
3. ✅ 运行满载测试
4. ✅ 检查 CPU 频率（是否降频）
5. ✅ 检查风扇行为
6. ✅ 综合判断

如果出现多个不匹配迹象，建议：
- 立即检查散热器安装
- 清理灰尘
- 考虑升级散热器

