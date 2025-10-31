# -*- coding: utf-8 -*-
"""
测试脚本：验证 AMD Ryzen 7 7700 时钟传感器读取功能

测试修复后的 LibreHardwareMonitor DLL 调用是否能正确读取时钟频率（最大 5.3 GHz）
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import logging
import math
import time

# 配置日志
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_extended_lhm_wrapper():
    """测试 ExtendedLHMWrapper 是否能正确读取时钟传感器"""
    print("=" * 80)
    print("测试：ExtendedLHMWrapper 时钟传感器读取")
    print("=" * 80)

    try:
        from backend.infrastructure.system_vnpy.librehardwaremonitor.lhm_extended import (
            ExtendedLHMWrapper
        )

        print("\n1. 初始化 ExtendedLHMWrapper...")
        wrapper = ExtendedLHMWrapper()

        if not wrapper.is_available():
            print("❌ ExtendedLHMWrapper 不可用")
            print("   请检查：")
            print("   1. LibreHardwareMonitorLib.dll 是否存在")
            print("   2. 是否以管理员权限运行")
            print("   3. pythonnet 是否已安装")
            return False

        print("✅ ExtendedLHMWrapper 初始化成功")
        print(f"   状态: {wrapper.get_status_summary()}")

        # 多次测试，看看是否能稳定读取
        print("\n2. 测试时钟传感器读取（多次更新）...")
        print("-" * 80)

        clock_sensors_found = []
        max_frequencies = []

        for attempt in range(5):
            print(f"\n第 {attempt + 1} 次尝试...")
            time.sleep(0.5)  # 每次尝试之间等待 0.5 秒

            sensor_data = wrapper.get_all_sensor_data()
            clock_sensors = sensor_data.get("clock", {})

            if not clock_sensors:
                print("   ⚠️  未找到时钟传感器")
                continue

            print(f"   找到 {len(clock_sensors)} 个设备的时钟传感器")

            for device_name, sensors in clock_sensors.items():
                print(f"\n   设备: {device_name}")
                print(f"   传感器数量: {len(sensors)}")

                for sensor in sensors:
                    label = sensor.get("label", "Unknown")
                    current = sensor.get("current")
                    min_val = sensor.get("min")
                    max_val = sensor.get("max")
                    unit = sensor.get("unit", "")

                    # 检查值是否有效
                    current_valid = current is not None and not math.isnan(current) if current is not None else False
                    min_valid = min_val is not None and not math.isnan(min_val) if min_val is not None else False
                    max_valid = max_val is not None and not math.isnan(max_val) if max_val is not None else False

                    print(f"\n     传感器: {label}")

                    if current_valid:
                        print(f"       当前频率: {current:.2f} {unit} ✅")
                    else:
                        print(f"       当前频率: {'NaN' if current is not None and math.isnan(current) else 'None'} ❌")

                    if min_valid:
                        print(f"       最小频率: {min_val:.2f} {unit} ✅")
                    else:
                        print(f"       最小频率: {'NaN' if min_val is not None and math.isnan(min_val) else 'None'}")

                    if max_valid:
                        print(f"       最大频率: {max_val:.2f} {unit} ✅")
                        max_frequencies.append(max_val)

                        # 检查是否接近 5.3 GHz (5300 MHz)
                        if max_val >= 5000:  # 5 GHz 以上
                            print(f"       🎯 检测到高频率！可能是最大频率")
                    else:
                        print(f"       最大频率: {'NaN' if max_val is not None and math.isnan(max_val) else 'None'} ❌")

                    # 检查是否是 CPU 相关的时钟传感器
                    if any(keyword in device_name.lower() for keyword in ["cpu", "processor", "ryzen", "amd"]):
                        if any(keyword in label.lower() for keyword in ["cpu", "core", "clock", "frequency"]):
                            clock_sensors_found.append({
                                "device": device_name,
                                "label": label,
                                "current": current if current_valid else None,
                                "min": min_val if min_valid else None,
                                "max": max_val if max_valid else None,
                                "unit": unit
                            })

        # 总结
        print("\n" + "=" * 80)
        print("测试总结")
        print("=" * 80)

        if clock_sensors_found:
            print(f"\n✅ 找到 {len(clock_sensors_found)} 个 CPU 相关的时钟传感器：")
            for idx, sensor in enumerate(clock_sensors_found, 1):
                print(f"\n  {idx}. {sensor['device']} - {sensor['label']}")
                if sensor['current'] is not None:
                    print(f"     当前: {sensor['current']:.2f} {sensor['unit']}")
                if sensor['min'] is not None:
                    print(f"     最小: {sensor['min']:.2f} {sensor['unit']}")
                if sensor['max'] is not None:
                    print(f"     最大: {sensor['max']:.2f} {sensor['unit']}")
                    if sensor['max'] >= 5000:
                        print(f"     ⭐ 这个可能是最大频率（接近 5.3 GHz）")
        else:
            print("\n❌ 未找到 CPU 相关的时钟传感器")

        if max_frequencies:
            highest_max = max(max_frequencies)
            print(f"\n📊 找到的最大频率值: {highest_max:.2f} MHz")
            if highest_max >= 5000:
                print(f"   ✅ 成功读取到高频率值（接近 5.3 GHz）")
            else:
                print(f"   ⚠️  频率值较低，可能不是最大频率")
        else:
            print("\n❌ 未找到有效的最大频率值")

        # 关闭
        wrapper.close()

        return len(clock_sensors_found) > 0 and len(max_frequencies) > 0

    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("   请确保已安装 pythonnet: pip install pythonnet")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_direct_lhm_access():
    """直接访问 LibreHardwareMonitor，查看原始传感器值"""
    print("\n" + "=" * 80)
    print("测试：直接访问 LibreHardwareMonitor 原始值")
    print("=" * 80)

    try:
        import clr

        dll_path = project_root / "backend" / "infrastructure" / "system_vnpy" / "librehardwaremonitor" / "LibreHardwareMonitorLib.dll"
        if not dll_path.exists():
            print(f"❌ DLL文件不存在: {dll_path}")
            return False

        dll_dir = str(dll_path.parent)
        if dll_dir not in sys.path:
            sys.path.append(dll_dir)

        clr.AddReference("LibreHardwareMonitorLib")
        from LibreHardwareMonitor.Hardware import Computer, SensorType

        print("\n1. 创建 Computer 实例...")
        computer = Computer()
        computer.IsCpuEnabled = True
        computer.IsGpuEnabled = False
        computer.IsStorageEnabled = False
        computer.IsMotherboardEnabled = False
        computer.IsMemoryEnabled = False
        computer.IsControllerEnabled = False
        computer.IsNetworkEnabled = False

        print("2. 打开硬件监控...")
        computer.Open()

        print("3. 查找时钟传感器...")
        print("-" * 80)

        clock_sensors = []

        def find_clock_sensors(hardware, indent=0):
            """递归查找时钟传感器"""
            prefix = "  " * indent
            device_name = str(hardware.Name)

            # 更新硬件
            hardware.Update()

            # 检查是否是 CPU 相关
            is_cpu_related = any(keyword in device_name.upper() for keyword in ["CPU", "RYZEN", "AMD", "PROCESSOR"])

            if is_cpu_related:
                print(f"\n{prefix}🔍 CPU 相关硬件: {device_name}")

            # 查找时钟传感器
            for sensor in hardware.Sensors:
                if sensor.SensorType == SensorType.Clock:
                    sensor_name = str(sensor.Name)
                    raw_value = sensor.Value

                    # 尝试转换为数值
                    current = None
                    max_val = None
                    min_val = None

                    if raw_value is not None:
                        try:
                            current = float(raw_value)
                            if math.isnan(current):
                                current = None
                        except (ValueError, TypeError):
                            pass

                    try:
                        max_val = float(sensor.Max) if sensor.Max is not None else None
                        if max_val is not None and math.isnan(max_val):
                            max_val = None
                    except (ValueError, TypeError):
                        pass

                    try:
                        min_val = float(sensor.Min) if sensor.Min is not None else None
                        if min_val is not None and math.isnan(min_val):
                            min_val = None
                    except (ValueError, TypeError):
                        pass

                    sensor_info = {
                        "device": device_name,
                        "name": sensor_name,
                        "current": current,
                        "min": min_val,
                        "max": max_val,
                        "is_cpu": is_cpu_related
                    }

                    clock_sensors.append(sensor_info)

                    if is_cpu_related:
                        print(f"{prefix}  ⏰ 时钟传感器: {sensor_name}")
                        if current is not None:
                            print(f"{prefix}     当前: {current:.2f} MHz ✅")
                        else:
                            print(f"{prefix}     当前: {'NaN' if raw_value is not None else 'None'} ❌")
                        if max_val is not None:
                            print(f"{prefix}     最大: {max_val:.2f} MHz ✅")
                            if max_val >= 5000:
                                print(f"{prefix}     🎯 检测到高频率！")
                        else:
                            print(f"{prefix}     最大: {'NaN' if sensor.Max is not None else 'None'} ❌")

            # 递归处理子硬件
            for subhardware in hardware.SubHardware:
                find_clock_sensors(subhardware, indent + 1)

        # 多次更新尝试
        print("\n4. 多次更新硬件并查找传感器...")
        for i in range(3):
            print(f"\n更新轮次 {i + 1}:")
            for hardware in computer.Hardware:
                find_clock_sensors(hardware)
            if i < 2:
                time.sleep(0.1)

        # 总结
        print("\n" + "=" * 80)
        print("直接访问总结")
        print("=" * 80)

        cpu_clock_sensors = [s for s in clock_sensors if s["is_cpu"]]

        if cpu_clock_sensors:
            print(f"\n✅ 找到 {len(cpu_clock_sensors)} 个 CPU 相关的时钟传感器：")
            for idx, sensor in enumerate(cpu_clock_sensors, 1):
                print(f"\n  {idx}. {sensor['device']} - {sensor['name']}")
                if sensor['current'] is not None:
                    print(f"     当前: {sensor['current']:.2f} MHz")
                if sensor['max'] is not None:
                    print(f"     最大: {sensor['max']:.2f} MHz")
                    if sensor['max'] >= 5000:
                        print(f"     ⭐ 这可能是最大频率（接近 5.3 GHz）")
        else:
            print("\n❌ 未找到 CPU 相关的时钟传感器")

        computer.Close()

        return len(cpu_clock_sensors) > 0

    except Exception as e:
        print(f"❌ 直接访问测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "=" * 80)
    print("AMD Ryzen 7 7700 时钟传感器读取测试")
    print("目标：验证是否能读取到最大频率 5.3 GHz (5300 MHz)")
    print("=" * 80)

    # 测试1：使用 ExtendedLHMWrapper
    result1 = test_extended_lhm_wrapper()

    # 测试2：直接访问 LibreHardwareMonitor
    result2 = test_direct_lhm_access()

    # 最终总结
    print("\n" + "=" * 80)
    print("最终测试结果")
    print("=" * 80)

    if result1:
        print("\n✅ ExtendedLHMWrapper 测试：成功")
    else:
        print("\n❌ ExtendedLHMWrapper 测试：失败")

    if result2:
        print("✅ 直接访问测试：成功")
    else:
        print("❌ 直接访问测试：失败")

    if result1 or result2:
        print("\n🎉 至少一种方法成功读取到时钟传感器数据！")
    else:
        print("\n⚠️  两种方法都未能成功读取时钟传感器数据")
        print("   请检查：")
        print("   1. 是否以管理员权限运行")
        print("   2. LibreHardwareMonitorLib.dll 版本是否正确")
        print("   3. 查看上面的详细错误信息")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()


