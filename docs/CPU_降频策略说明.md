# CPU 降频策略说明

## 一、降频机制概述

CPU 降频（Thermal Throttling / Frequency Scaling）是 CPU 的一种自我保护机制，当温度过高或功耗超过限制时，CPU 会自动降低运行频率以减少热量产生，防止硬件损坏。

## 二、AMD Ryzen 7 7700 降频策略

### 2.1 温度阈值

根据 AMD Ryzen 7000 系列（Zen 4 架构）的设计规范：

- **正常温度范围**: 30-70°C
- **警告温度**: **80°C** - 开始监控，但通常不降频
- **严重温度**: **90°C** - 接近温度上限
- **降频起始温度**: **95°C** - 开始轻微降频
- **最大安全温度 (Tjmax)**: **100°C** - 温度上限，超过会强制降频保护

### 2.2 降频阶段

AMD Ryzen 7 7700 的降频通常分为以下几个阶段：

1. **阶段 1 (95-100°C)**:
   - 轻微降频（约降低 100-200 MHz）
   - 降低电压
   - 目的是减缓温度上升

2. **阶段 2 (100°C)**:
   - 强制降频至基础频率（3.8 GHz）或更低
   - 大幅降低电压
   - 保护硬件安全

3. **极端情况 (>100°C)**:
   - 可能触发系统保护机制
   - 强制关闭部分核心
   - 或触发系统自动关机

### 2.3 降频触发条件

CPU 降频可能由以下因素触发：

1. **温度过高**（主要因素）
   - CPU 核心温度（Tdie）达到 95°C
   - CPU 封装温度（Tctl/Tdie）达到阈值

2. **功耗限制**
   - TDP (Thermal Design Power) 限制：65W（Ryzen 7 7700）
   - PPT (Package Power Tracking) 限制
   - 长时间高负载导致功耗累积

3. **电源管理策略**
   - Windows 电源计划设置
   - BIOS/UEFI 中的 CPU 功率限制
   - 主板供电能力限制

## 三、实际监控建议

### 3.1 监控指标

基于本项目中的系统监控指标定义（`系统监控指标.md`）：

```yaml
cpu_temperature:
  警告阈值: >80°C
  严重阈值: >90°C
  影响: 自动降频，性能下降
  调优: 改善散热

cpu_frequency_ratio:
  说明: CPU频率比率（实际/最大）
  分析: 是否降频运行
  场景: 温度过高时自动降频
```

### 3.2 监控频率变化

可以通过以下方式检测是否发生降频：

1. **实时频率监控**
   - 当前频率 < 最大频率（5.3 GHz）
   - 频率比率 < 1.0

2. **温度-频率关联**
   - 温度 > 95°C 且频率明显下降
   - 频率突然下降伴随温度上升

3. **性能下降检测**
   - CPU 性能计数器显示性能下降
   - 任务执行时间变长

## 四、避免降频的措施

### 4.1 硬件层面

1. **改善散热**
   - 使用高质量 CPU 散热器
   - 确保机箱通风良好
   - 定期清理灰尘
   - 检查硅脂是否需要更换

2. **优化机箱环境**
   - 确保机箱有足够的进气和排气风扇
   - 保持环境温度适宜（<25°C）
   - 避免机箱内部线缆阻挡风道

### 4.2 软件层面

1. **电源管理设置**
   - Windows 电源计划设置为"高性能"或"平衡"
   - 避免使用"节能"模式（可能导致不必要的降频）

2. **BIOS/UEFI 设置**
   - Precision Boost Overdrive (PBO) 设置
   - 温度限制设置
   - 风扇曲线优化

3. **负载管理**
   - 避免长时间 100% CPU 负载
   - 合理分配任务，避免突发高负载

## 五、AMD Ryzen 7 7700 规格参考

- **基础频率**: 3.8 GHz
- **最大加速频率**: 5.3 GHz（单核）
- **TDP**: 65W
- **最大工作温度 (Tjmax)**: 100°C
- **推荐工作温度**: <80°C（最佳性能）

## 六、监控代码示例

### 6.1 温度监控

```python
# 在 lhm_extended.py 中已经实现
cpu_temp = sensor_data.get("temperature", {}).get("CPU", [])
if cpu_temp:
    current_temp = cpu_temp[0].get("current")
    if current_temp > 90:
        logger.warning(f"CPU 温度过高: {current_temp}°C，可能触发降频")
```

### 6.2 频率监控

```python
# 监控频率比率
cpu_clocks = sensor_data.get("clock", {}).get("CPU", [])
if cpu_clocks:
    max_freq = cpu_clocks[0].get("max")  # 最大频率（5.3 GHz）
    current_freq = cpu_clocks[0].get("current")  # 当前频率

    if max_freq and current_freq:
        freq_ratio = current_freq / max_freq
        if freq_ratio < 0.9:  # 频率低于最大值的 90%
            logger.warning(f"CPU 可能正在降频: {current_freq}/{max_freq} GHz (比率: {freq_ratio:.2%})")
```

## 七、参考资料

1. AMD Ryzen 7000 系列官方规格
2. AMD Precision Boost 技术文档
3. 本项目系统监控指标定义：`backend/infrastructure/system_vnpy/系统监控指标.md`

## 八、总结

- **主要降频触发温度**: **95°C** 开始，**100°C** 强制降频
- **警告温度**: **80°C**（建议改善散热）
- **严重温度**: **90°C**（接近降频阈值）
- **最佳工作温度**: **<80°C**（保持最佳性能）

对于 AMD Ryzen 7 7700，建议保持 CPU 温度在 **80°C 以下**，以确保：
- 不会触发降频
- 保持最大性能（5.3 GHz 加速频率）
- 延长硬件寿命

