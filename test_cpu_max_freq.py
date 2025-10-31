# -*- coding: utf-8 -*-
"""
测试脚本：验证从LibreHardwareMonitor获取CPU最大频率（包括Turbo Boost）
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.system_vnpy.monitor_system import HardwareMonitorFactory
import psutil

def test_psutil_cpu_freq():
    """测试psutil获取CPU频率"""
    print("=" * 80)
    print("1. 测试 psutil.cpu_freq()")
    print("=" * 80)
    try:
        cpu_freq = psutil.cpu_freq()
        if cpu_freq:
            print(f"✅ psutil.cpu_freq() 可用")
            print(f"   当前频率: {cpu_freq.current:.2f} MHz")
            print(f"   最小频率: {cpu_freq.min:.2f} MHz")
            print(f"   最大频率: {cpu_freq.max:.2f} MHz")
            print(f"   注意: 在Windows上，max通常是基础频率，不是Turbo Boost上限")
            return cpu_freq.max
        else:
            print("❌ psutil.cpu_freq() 返回 None")
            return None
    except Exception as e:
        print(f"❌ psutil.cpu_freq() 失败: {e}")
        return None

def test_librehardwaremonitor_cpu_freq():
    """测试LibreHardwareMonitor获取CPU频率"""
    print("\n" + "=" * 80)
    print("2. 测试 LibreHardwareMonitor 获取CPU频率")
    print("=" * 80)
    
    try:
        # 创建硬件监控器
        print("正在初始化LibreHardwareMonitor...")
        monitor = HardwareMonitorFactory.create_monitor()
        
        if not monitor:
            print("❌ LibreHardwareMonitor 不可用")
            return None
        
        if not monitor.is_available():
            print("❌ LibreHardwareMonitor 未就绪")
            return None
        
        print("✅ LibreHardwareMonitor 初始化成功")
        
        # 获取所有传感器数据（内部会自动更新）
        print("\n正在获取传感器数据（首次获取可能需要一些时间）...")
        import time
        time.sleep(2)  # 等待传感器初始化
        sensor_data = monitor.get_all_sensor_data()
        
        # 再次获取，确保数据更新
        print("正在再次获取传感器数据（确保数据已更新）...")
        time.sleep(1)
        sensor_data = monitor.get_all_sensor_data()
        
        # 打印所有传感器类型以便调试
        print("\n所有传感器类型:")
        for category, devices in sensor_data.items():
            if devices:
                print(f"  {category}: {len(devices)} 个设备")
                for device_name, sensors in devices.items():
                    print(f"    - {device_name}: {len(sensors)} 个传感器")
        
        # 查找CPU相关的clock传感器
        clock_sensors = sensor_data.get("clock", {})
        print(f"\n找到 {len(clock_sensors)} 个设备的时钟传感器")
        
        # 也检查load传感器（CPU负载可能包含频率信息）
        load_sensors = sensor_data.get("load", {})
        print(f"找到 {len(load_sensors)} 个设备的负载传感器")
        
        cpu_max_freqs = []
        cpu_current_freqs = []
        
        for device_name, sensors in clock_sensors.items():
            print(f"\n设备: {device_name}")
            print(f"  传感器数量: {len(sensors)}")
            
            for sensor in sensors:
                label = sensor.get("label", "Unknown")
                current = sensor.get("current")
                max_val = sensor.get("max")
                min_val = sensor.get("min")
                unit = sensor.get("unit", "")
                
                print(f"    - {label}:")
                # 检查是否为NaN
                import math
                if current is not None and not math.isnan(current):
                    print(f"      当前: {current:.2f} {unit}")
                    cpu_current_freqs.append(current)
                else:
                    print(f"      当前: 不可用 (NaN)")
                
                if min_val is not None and not math.isnan(min_val):
                    print(f"      最小: {min_val:.2f} {unit}")
                else:
                    print(f"      最小: 不可用 (NaN)")
                
                if max_val is not None and not math.isnan(max_val):
                    print(f"      最大: {max_val:.2f} {unit}")
                    cpu_max_freqs.append(max_val)
                else:
                    print(f"      最大: 不可用 (NaN)")
        
        # 计算CPU最大频率（可能是Turbo Boost上限）
        if cpu_max_freqs:
            max_turbo_freq = max(cpu_max_freqs)
            print(f"\n✅ CPU最大频率（可能包含Turbo Boost）: {max_turbo_freq:.2f} MHz")
            
            if cpu_current_freqs:
                max_current = max(cpu_current_freqs)
                print(f"✅ CPU当前最大频率: {max_current:.2f} MHz")
            
            return max_turbo_freq
        else:
            print("\n❌ 未找到CPU频率传感器")
            return None
            
    except Exception as e:
        print(f"\n❌ LibreHardwareMonitor 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_wmi_cpu_freq():
    """测试WMI获取CPU频率"""
    print("\n" + "=" * 80)
    print("4. 测试 WMI 获取CPU频率")
    print("=" * 80)
    
    try:
        import wmi
        c = wmi.WMI()
        processors = c.Win32_Processor()
        
        if processors:
            proc = processors[0]
            print(f"✅ WMI查询成功")
            print(f"   CPU名称: {proc.Name}")
            print(f"   最大时钟速度: {proc.MaxClockSpeed} MHz")
            print(f"   当前时钟速度: {proc.CurrentClockSpeed} MHz")
            print(f"   注意: MaxClockSpeed通常是基础频率，不是Turbo Boost上限")
            return proc.MaxClockSpeed
        else:
            print("❌ WMI未找到CPU信息")
            return None
    except ImportError:
        print("❌ WMI模块未安装 (pip install wmi)")
        return None
    except Exception as e:
        print(f"❌ WMI查询失败: {e}")
        return None

def compare_frequencies():
    """比较psutil和LibreHardwareMonitor获取的频率"""
    print("\n" + "=" * 80)
    print("3. 频率对比")
    print("=" * 80)
    
    psutil_max = test_psutil_cpu_freq()
    lhm_max = test_librehardwaremonitor_cpu_freq()
    wmi_max = test_wmi_cpu_freq()
    
    print("\n" + "=" * 80)
    print("对比结果:")
    print("=" * 80)
    if psutil_max:
        print(f"psutil.cpu_freq().max: {psutil_max:.2f} MHz")
    else:
        print("psutil.cpu_freq().max: 不可用")
    
    if lhm_max:
        print(f"LibreHardwareMonitor最大频率: {lhm_max:.2f} MHz")
    else:
        print("LibreHardwareMonitor最大频率: 不可用")
    
    if wmi_max:
        print(f"WMI MaxClockSpeed: {wmi_max} MHz")
    else:
        print("WMI MaxClockSpeed: 不可用")
    
    print("\n建议:")
    print("=" * 80)
    # 找出最大值
    available_freqs = [f for f in [psutil_max, lhm_max, wmi_max] if f]
    if available_freqs:
        max_available = max(available_freqs)
        print(f"✅ 当前可用的最大频率: {max_available:.2f} MHz")
        print("\n注意:")
        print("  - 在Windows上，psutil和WMI通常返回基础频率")
        print("  - Turbo Boost最大频率通常比基础频率高15-30%")
        print("  - AMD Ryzen 7 7700 官方规格:")
        print("    * 基础频率: 3.8 GHz (3800 MHz)")
        print("    * 最大加速频率: 5.3 GHz (5300 MHz)")
        print("  - 如需获取Turbo Boost上限，可能需要:")
        print("    1. 查询CPU官方规格文档")
        print("    2. 使用专业的硬件监控工具（如HWiNFO64）")
        print("    3. 在CPU高负载时监控实际达到的最高频率")

if __name__ == "__main__":
    print("CPU最大频率获取测试")
    print("=" * 80)
    compare_frequencies()

