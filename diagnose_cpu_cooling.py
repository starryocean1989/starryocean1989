#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""CPU 散热匹配诊断脚本

使用方法:
    python diagnose_cpu_cooling.py

该脚本会检查 CPU 温度、风扇转速、频率等指标，判断散热是否匹配 CPU。
"""

import sys
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from backend.infrastructure.system_vnpy.librehardwaremonitor.lhm_extended import ExtendedLHMWrapper
except ImportError as e:
    print(f"❌ 无法导入 LibreHardwareMonitor 包装器: {e}")
    print("请确保已安装 pythonnet 和 LibreHardwareMonitorLib.dll")
    sys.exit(1)


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


def get_cpu_power(sensor_data):
    """获取 CPU 功耗"""
    power_data = sensor_data.get("power", {})
    for device, sensors in power_data.items():
        if "CPU" in device and sensors:
            return sensors[0].get("current", 0)
    return None


def get_cpu_freq(sensor_data):
    """获取 CPU 频率（MHz）"""
    clock_data = sensor_data.get("clock", {})
    for device, sensors in clock_data.items():
        if "CPU" in device and sensors:
            # 取所有核心的平均频率
            freqs = [s.get("current", 0) for s in sensors if s.get("current") and s.get("current") > 0]
            if freqs:
                avg_freq_mhz = sum(freqs) / len(freqs)
                return avg_freq_mhz
    return None


def diagnose_cooling_mismatch(cpu_temp, cpu_fan_rpm, cpu_power, cpu_freq_mhz, cpu_model="AMD Ryzen 7 7700"):
    """诊断散热是否匹配"""
    issues = []
    warnings = []

    # 基础频率（GHz）
    base_freq = 3.8  # AMD Ryzen 7 7700
    max_freq = 5.3   # AMD Ryzen 7 7700

    # 1. 待机温度检查
    if cpu_power and cpu_power < 25:  # 待机或轻负载
        if cpu_temp > 50:
            issues.append({
                "severity": "严重",
                "type": "待机温度过高",
                "message": f"待机温度 {cpu_temp:.1f}°C 过高（功耗 {cpu_power:.1f}W），散热可能不匹配"
            })
        elif cpu_temp > 40:
            warnings.append({
                "type": "待机温度偏高",
                "message": f"待机温度 {cpu_temp:.1f}°C 偏高（功耗 {cpu_power:.1f}W）"
            })

    # 2. 风扇转速与温度匹配检查
    if cpu_fan_rpm:
        if cpu_temp > 70 and cpu_fan_rpm < 2000:
            issues.append({
                "severity": "严重",
                "type": "风扇转速不足",
                "message": f"温度 {cpu_temp:.1f}°C 但风扇转速仅 {cpu_fan_rpm:.0f} RPM，可能风扇故障或控制异常"
            })
        elif cpu_temp > 50 and cpu_fan_rpm > 3500:
            warnings.append({
                "type": "风扇转速过高",
                "message": f"温度 {cpu_temp:.1f}°C 但风扇转速 {cpu_fan_rpm:.0f} RPM 很高，散热可能不足"
            })
        elif cpu_temp < 40 and cpu_fan_rpm > 3000:
            warnings.append({
                "type": "风扇转速异常",
                "message": f"温度 {cpu_temp:.1f}°C 较低但风扇转速 {cpu_fan_rpm:.0f} RPM 很高，可能 BIOS 设置不当"
            })

    # 3. 功耗与温度匹配检查
    if cpu_power and cpu_temp:
        temp_per_watt = cpu_temp / cpu_power if cpu_power > 0 else 0
        if temp_per_watt > 1.5:  # 每瓦特温度 > 1.5°C/W
            issues.append({
                "severity": "警告",
                "type": "散热效率低",
                "message": f"温度功耗比 {temp_per_watt:.2f}°C/W 过高，散热效率低（正常应 < 1.2°C/W）"
            })

    # 4. CPU 频率检查（降频）
    if cpu_freq_mhz:
        cpu_freq_ghz = cpu_freq_mhz / 1000
        if cpu_power and cpu_power > 50:  # 高负载
            if cpu_freq_ghz < base_freq:
                issues.append({
                    "severity": "严重",
                    "type": "CPU 降频",
                    "message": f"CPU 频率 {cpu_freq_ghz:.2f} GHz 低于基础频率 {base_freq} GHz，可能因过热降频"
                })
            elif cpu_freq_ghz < max_freq * 0.85:  # 低于最大频率的 85%
                warnings.append({
                    "type": "CPU 频率下降",
                    "message": f"CPU 频率 {cpu_freq_ghz:.2f} GHz 低于最大频率 {max_freq} GHz，可能因温度过高"
                })

    # 5. 综合温度评估
    if cpu_temp > 90:
        issues.append({
            "severity": "严重",
            "type": "温度过高",
            "message": f"CPU 温度 {cpu_temp:.1f}°C 超过安全阈值（90°C），散热严重不足"
        })
    elif cpu_temp > 85:
        issues.append({
            "severity": "警告",
            "type": "温度偏高",
            "message": f"CPU 温度 {cpu_temp:.1f}°C 偏高，满载时应 < 85°C"
        })
    elif cpu_temp > 80:
        warnings.append({
            "type": "温度较高",
            "message": f"CPU 温度 {cpu_temp:.1f}°C 较高，建议改善散热"
        })

    return issues, warnings


def print_diagnosis_report(cpu_temp, cpu_fan_rpm, cpu_power, cpu_freq_mhz, issues, warnings):
    """打印诊断报告"""
    print("\n" + "=" * 80)
    print("CPU 散热匹配诊断报告")
    print("=" * 80)

    print(f"\n📊 当前状态:")
    print(f"  CPU 温度: {cpu_temp:.1f}°C" if cpu_temp else "  CPU 温度: 无法读取")
    print(f"  风扇转速: {cpu_fan_rpm:.0f} RPM" if cpu_fan_rpm else "  风扇转速: 无法读取")
    print(f"  CPU 功耗: {cpu_power:.1f} W" if cpu_power else "  CPU 功耗: 无法读取")
    print(f"  CPU 频率: {cpu_freq_mhz/1000:.2f} GHz" if cpu_freq_mhz else "  CPU 频率: 无法读取")

    if issues:
        print(f"\n🔴 发现 {len(issues)} 个问题:")
        for i, issue in enumerate(issues, 1):
            print(f"  {i}. [{issue['severity']}] {issue['type']}")
            print(f"     {issue['message']}")

    if warnings:
        print(f"\n⚠️  发现 {len(warnings)} 个警告:")
        for i, warning in enumerate(warnings, 1):
            print(f"  {i}. {warning['type']}")
            print(f"     {warning['message']}")

    if not issues and not warnings:
        print("\n✅ 未发现明显的散热不匹配问题")

    # 总体评估
    print("\n" + "-" * 80)
    if issues:
        severity_levels = [i['severity'] for i in issues]
        if '严重' in severity_levels:
            print("🔴 总体评估: 散热严重不匹配，建议立即检查散热器")
        else:
            print("⚠️  总体评估: 散热可能不匹配，建议检查散热器")
    elif warnings:
        print("⚠️  总体评估: 散热基本正常，但有改进空间")
    else:
        print("✅ 总体评估: 散热正常")

    print("=" * 80)


def main():
    """主函数"""
    print("CPU 散热匹配诊断工具")
    print("=" * 80)
    print("\n正在初始化硬件监控...")

    try:
        lhm = ExtendedLHMWrapper()
        print("✅ 硬件监控初始化成功")
    except Exception as e:
        print(f"❌ 硬件监控初始化失败: {e}")
        return

    print("\n正在读取传感器数据...")
    print("（等待 5 秒以确保数据稳定）")
    time.sleep(5)

    sensor_data = lhm.get_all_sensor_data()

    # 获取各项指标
    cpu_temp = get_cpu_temp(sensor_data)
    cpu_fan_rpm = get_cpu_fan_rpm(sensor_data)
    cpu_power = get_cpu_power(sensor_data)
    cpu_freq_mhz = get_cpu_freq(sensor_data)

    if cpu_temp is None:
        print("❌ 无法读取 CPU 温度，请检查 LibreHardwareMonitor 是否正常工作")
        return

    # 诊断
    issues, warnings = diagnose_cooling_mismatch(
        cpu_temp, cpu_fan_rpm, cpu_power, cpu_freq_mhz
    )

    # 打印报告
    print_diagnosis_report(cpu_temp, cpu_fan_rpm, cpu_power, cpu_freq_mhz, issues, warnings)

    # 建议
    if issues or warnings:
        print("\n💡 建议:")
        print("  1. 检查散热器是否正确安装（是否贴紧 CPU）")
        print("  2. 检查硅脂是否需要更换")
        print("  3. 清理散热器和风扇的灰尘")
        print("  4. 检查机箱风道是否畅通")
        print("  5. 如果问题持续，考虑升级散热器")
        print("\n  详细诊断指南请参考: docs/CPU散热不匹配诊断指南.md")


if __name__ == "__main__":
    main()

