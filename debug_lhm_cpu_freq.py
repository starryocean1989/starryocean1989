# -*- coding: utf-8 -*-
"""
调试脚本：深入分析LibreHardwareMonitor返回NaN的原因
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import logging
logging.basicConfig(level=logging.DEBUG)

def debug_sensor_raw_values():
    """直接访问传感器原始值，查看详细属性"""
    print("=" * 80)
    print("调试：直接访问LibreHardwareMonitor传感器原始值")
    print("=" * 80)

    try:
        import clr
        import sys

        # 添加DLL路径
        dll_path = project_root / "backend" / "infrastructure" / "system_vnpy" / "librehardwaremonitor" / "LibreHardwareMonitorLib.dll"
        if not dll_path.exists():
            print(f"❌ DLL文件不存在: {dll_path}")
            return

        dll_dir = str(dll_path.parent)
        if dll_dir not in sys.path:
            sys.path.append(dll_dir)

        # 加载程序集
        clr.AddReference("LibreHardwareMonitorLib")
        from LibreHardwareMonitor.Hardware import Computer, SensorType

        # 创建Computer实例
        computer = Computer()
        computer.IsCpuEnabled = True
        computer.IsGpuEnabled = False
        computer.IsStorageEnabled = False
        computer.IsMotherboardEnabled = False
        computer.IsMemoryEnabled = False
        computer.IsControllerEnabled = False
        computer.IsNetworkEnabled = False

        print("\n正在打开硬件监控...")
        computer.Open()

        print("\n遍历所有硬件和传感器...")
        print("-" * 80)

        def inspect_hardware(hardware, indent=0):
            """递归检查硬件"""
            prefix = "  " * indent
            print(f"{prefix}硬件: {hardware.Name}")
            print(f"{prefix}  类型: {hardware.HardwareType}")
            print(f"{prefix}  标识: {hardware.Identifier}")

            # 更新硬件
            print(f"{prefix}  正在更新硬件数据...")
            hardware.Update()

            # 检查所有传感器
            sensors = list(hardware.Sensors)
            print(f"{prefix}  传感器数量: {len(sensors)}")

            for sensor in sensors:
                print(f"\n{prefix}  传感器:")
                print(f"{prefix}    名称: {sensor.Name}")
                print(f"{prefix}    类型: {sensor.SensorType}")
                print(f"{prefix}    标识: {sensor.Identifier}")

                # 原始值访问
                try:
                    raw_value = sensor.Value
                    print(f"{prefix}    Value (原始): {raw_value} (类型: {type(raw_value)})")

                    if raw_value is not None:
                        try:
                            float_value = float(raw_value)
                            print(f"{prefix}    Value (float): {float_value}")
                            import math
                            if math.isnan(float_value):
                                print(f"{prefix}    ⚠️  Value是NaN!")
                        except (ValueError, TypeError) as e:
                            print(f"{prefix}    ❌ 无法转换为float: {e}")
                    else:
                        print(f"{prefix}    ⚠️  Value是None")
                except Exception as e:
                    print(f"{prefix}    ❌ 访问Value失败: {e}")

                # Min/Max值
                try:
                    min_val = sensor.Min
                    max_val = sensor.Max
                    print(f"{prefix}    Min: {min_val} (类型: {type(min_val)})")
                    print(f"{prefix}    Max: {max_val} (类型: {type(max_val)})")
                except Exception as e:
                    print(f"{prefix}    ❌ 访问Min/Max失败: {e}")

                # 其他属性
                try:
                    print(f"{prefix}    索引: {sensor.Index}")
                    print(f"{prefix}    索引: {sensor.Index}")
                except:
                    pass

            # 递归处理子硬件
            for subhardware in hardware.SubHardware:
                inspect_hardware(subhardware, indent + 1)

        # 遍历所有硬件
        for hardware in computer.Hardware:
            inspect_hardware(hardware)

        print("\n" + "=" * 80)
        print("检查AMD Ryzen特殊处理...")
        print("=" * 80)

        # 专门查找CPU相关的时钟传感器
        cpu_clock_sensors = []
        for hardware in computer.Hardware:
            if "CPU" in str(hardware.Name).upper() or "RYZEN" in str(hardware.Name).upper() or "PROCESSOR" in str(hardware.Name).upper():
                print(f"\n找到CPU硬件: {hardware.Name}")
                hardware.Update()

                for sensor in hardware.Sensors:
                    if sensor.SensorType == SensorType.Clock:
                        print(f"  时钟传感器: {sensor.Name}")
                        print(f"    Value: {sensor.Value}")
                        print(f"    Min: {sensor.Min}")
                        print(f"    Max: {sensor.Max}")
                        cpu_clock_sensors.append(sensor)

                # 检查子硬件
                for subhardware in hardware.SubHardware:
                    print(f"  子硬件: {subhardware.Name}")
                    subhardware.Update()
                    for sensor in subhardware.Sensors:
                        if sensor.SensorType == SensorType.Clock:
                            print(f"    时钟传感器: {sensor.Name}")
                            print(f"      Value: {sensor.Value}")
                            print(f"      Min: {sensor.Min}")
                            print(f"      Max: {sensor.Max}")
                            cpu_clock_sensors.append(sensor)

        print(f"\n总共找到 {len(cpu_clock_sensors)} 个CPU时钟传感器")

        # 关闭
        computer.Close()

    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("请确保已安装pythonnet: pip install pythonnet")
    except Exception as e:
        print(f"❌ 调试失败: {e}")
        import traceback
        traceback.print_exc()

def test_multiple_updates():
    """测试多次更新是否能获取到有效值"""
    print("\n" + "=" * 80)
    print("测试：多次更新硬件数据")
    print("=" * 80)

    try:
        from backend.infrastructure.system_vnpy.monitor_system import HardwareMonitorFactory

        monitor = HardwareMonitorFactory.create_monitor()
        if not monitor or not monitor.is_available():
            print("❌ LibreHardwareMonitor不可用")
            return

        print("✅ LibreHardwareMonitor初始化成功")

        # 多次更新并检查
        import time
        for i in range(5):
            print(f"\n第 {i+1} 次更新...")
            time.sleep(1)
            sensor_data = monitor.get_all_sensor_data()

            clock_sensors = sensor_data.get("clock", {})
            for device_name, sensors in clock_sensors.items():
                if "cpu" in device_name.lower() or "ryzen" in device_name.lower():
                    print(f"  设备: {device_name}")
                    for sensor in sensors:
                        label = sensor.get("label")
                        current = sensor.get("current")
                        max_val = sensor.get("max")
                        import math
                        if current is not None and not math.isnan(current):
                            print(f"    ✅ {label}: {current:.2f} MHz")
                        else:
                            print(f"    ❌ {label}: NaN")
                        if max_val is not None and not math.isnan(max_val):
                            print(f"        Max: {max_val:.2f} MHz")
                        else:
                            print(f"        Max: NaN")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("LibreHardwareMonitor AMD Ryzen 7 7700 时钟传感器NaN问题诊断")
    print("=" * 80)

    # 方法1：直接访问原始传感器值
    debug_sensor_raw_values()

    # 方法2：测试多次更新
    test_multiple_updates()

    print("\n" + "=" * 80)
    print("诊断完成")
    print("=" * 80)

