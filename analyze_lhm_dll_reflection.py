# -*- coding: utf-8 -*-
"""
使用反射深入分析 LibreHardwareMonitor DLL 的内部实现
查看 Sensor.Max 的实现和 CPU 时钟传感器的处理逻辑
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import logging
import math
logging.basicConfig(level=logging.INFO)

def analyze_dll_with_reflection():
    """使用反射分析 DLL 的内部结构"""
    print("=" * 80)
    print("使用反射分析 LibreHardwareMonitor DLL")
    print("=" * 80)

    try:
        import clr
        import System

        # 加载 DLL
        dll_path = project_root / "backend" / "infrastructure" / "system_vnpy" / "librehardwaremonitor" / "LibreHardwareMonitorLib.dll"
        if not dll_path.exists():
            # 尝试使用 EXE 目录中的 DLL
            exe_dll_path = Path(r"C:\Users\USER\LibreHardwareMonitor\LibreHardwareMonitorLib.dll")
            if exe_dll_path.exists():
                dll_path = exe_dll_path
            else:
                print(f"❌ DLL 文件不存在")
                return

        dll_dir = str(dll_path.parent)
        if dll_dir not in sys.path:
            sys.path.append(dll_dir)

        clr.AddReference("LibreHardwareMonitorLib")

        # 导入主要类型
        from LibreHardwareMonitor.Hardware import Computer, SensorType

        # 通过反射查找 Sensor 类
        hardware_assembly = System.Reflection.Assembly.GetAssembly(Computer)
        sensor_type = hardware_assembly.GetType("LibreHardwareMonitor.Hardware.Sensor")

        if sensor_type is None:
            print("⚠️  无法直接找到 Sensor 类，尝试其他方式...")
            # 尝试通过 ISensor 接口
            sensor_type = hardware_assembly.GetType("LibreHardwareMonitor.Hardware.ISensor")

        if sensor_type is None:
            print("❌ 无法找到 Sensor 或 ISensor 类型")
            return

        print("\n1. 分析 Sensor 类的结构...")
        print("-" * 80)
        print(f"Sensor CLR 类型: {sensor_type}")
        print(f"命名空间: {sensor_type.Namespace}")
        print(f"完整名称: {sensor_type.FullName}")

        # 查看所有属性
        print("\nSensor 类的属性:")
        for prop in sensor_type.GetProperties():
            prop_type = prop.PropertyType
            getter = prop.GetGetMethod()
            setter = prop.GetSetMethod()

            print(f"  {prop.Name}:")
            print(f"    类型: {prop_type}")
            if getter:
                print(f"    有 Getter: {getter.Name}")
            if setter:
                print(f"    有 Setter: {setter.Name}")

            # 特别关注 Max 属性
            if prop.Name == "Max":
                print(f"    ⭐ Max 属性的详细信息:")
                # 查看 Getter 的实现
                getter_il = getter.GetMethodBody()
                if getter_il:
                    print(f"    Getter IL 代码长度: {len(getter_il.GetILAsByteArray())} 字节")

        # 查看所有字段（包括私有字段）
        print("\nSensor 类的字段:")
        for field in sensor_type.GetFields(
            System.Reflection.BindingFlags.NonPublic |
            System.Reflection.BindingFlags.Public |
            System.Reflection.BindingFlags.Instance |
            System.Reflection.BindingFlags.Static
        ):
            print(f"  {field.Name}: {field.FieldType} ({'私有' if field.IsPrivate else '公有'})")

        # 查看所有方法
        print("\nSensor 类的方法（前20个）:")
        methods = list(sensor_type.GetMethods(
            System.Reflection.BindingFlags.NonPublic |
            System.Reflection.BindingFlags.Public |
            System.Reflection.BindingFlags.Instance |
            System.Reflection.BindingFlags.Static
        ))
        for i, method in enumerate(methods[:20]):
            params = ", ".join([f"{p.ParameterType.Name} {p.Name}" for p in method.GetParameters()])
            print(f"  {method.Name}({params})")

        print("\n2. 查找 CPU 相关的类...")
        print("-" * 80)

        # 尝试通过反射查找 Amd17Cpu 类
        hardware_assembly = System.Reflection.Assembly.GetAssembly(Computer)

        # 尝试不同的命名空间路径
        amd17_type = hardware_assembly.GetType("LibreHardwareMonitor.Hardware.Cpu.Amd17Cpu")
        if amd17_type is None:
            amd17_type = hardware_assembly.GetType("LibreHardwareMonitor.Hardware.CPU.Amd17Cpu")

        if amd17_type:
            print(f"✅ 找到 Amd17Cpu 类: {amd17_type.FullName}")

            # 查看 Amd17Cpu 的字段和方法
            print("\nAmd17Cpu 类的字段:")
            for field in amd17_type.GetFields(
                System.Reflection.BindingFlags.NonPublic |
                System.Reflection.BindingFlags.Public |
                System.Reflection.BindingFlags.Instance |
                System.Reflection.BindingFlags.Static
            ):
                try:
                    if "frequency" in field.Name.lower() or "max" in field.Name.lower() or "clock" in field.Name.lower():
                        print(f"  ⭐ {field.Name}: {field.FieldType}")
                except:
                    pass

            print("\nAmd17Cpu 类的方法（包含 clock 或 frequency 的）:")
            methods = list(amd17_type.GetMethods(
                System.Reflection.BindingFlags.NonPublic |
                System.Reflection.BindingFlags.Public |
                System.Reflection.BindingFlags.Instance
            ))
            for method in methods:
                if "clock" in method.Name.lower() or "frequency" in method.Name.lower() or "update" in method.Name.lower():
                    params = ", ".join([f"{p.ParameterType.Name}" for p in method.GetParameters()])
                    print(f"  ⭐ {method.Name}({params})")
        else:
            print("⚠️  无法通过反射找到 Amd17Cpu 类")
            # 尝试查找所有 CPU 相关的类
            print("\n查找所有 CPU 相关的类型:")
            for type_name in hardware_assembly.GetTypes():
                type_name_str = str(type_name)
                if "Amd" in type_name_str and "Cpu" in type_name_str:
                    print(f"  ⭐ 找到: {type_name_str}")

        print("\n3. 创建 Computer 实例并分析实际传感器...")
        print("-" * 80)

        computer = Computer()
        computer.IsCpuEnabled = True
        computer.IsGpuEnabled = False
        computer.IsStorageEnabled = False
        computer.IsMotherboardEnabled = False
        computer.IsMemoryEnabled = False
        computer.IsControllerEnabled = False
        computer.IsNetworkEnabled = False

        computer.Open()

        # 查找 CPU 硬件
        cpu_hardware = None
        cpu_hardware_actual = None
        for hardware in computer.Hardware:
            if "AMD" in str(hardware.Name) or "RYZEN" in str(hardware.Name).upper():
                cpu_hardware = hardware
                # 尝试获取实际对象类型
                hw_type = clr.GetClrType(type(hardware))
                print(f"   CPU 硬件接口类型: {hw_type.FullName}")
                cpu_hardware_actual = hardware  # 先使用接口对象
                break

        if not cpu_hardware:
            print("❌ 未找到 CPU 硬件")
            computer.Close()
            return

        print(f"✅ 找到 CPU: {cpu_hardware.Name}")

        # 更新硬件
        cpu_hardware.Update()
        for subhardware in cpu_hardware.SubHardware:
            subhardware.Update()

        # 查找时钟传感器
        clock_sensors = []
        def find_clock_sensors(hardware):
            hardware.Update()
            for sensor in hardware.Sensors:
                if sensor.SensorType == SensorType.Clock:
                    clock_sensors.append(sensor)
            for subhardware in hardware.SubHardware:
                find_clock_sensors(subhardware)

        find_clock_sensors(cpu_hardware)

        if not clock_sensors:
            print("❌ 未找到时钟传感器")
            computer.Close()
            return

        print(f"✅ 找到 {len(clock_sensors)} 个时钟传感器")

        # 深入分析第一个时钟传感器和 CPU 硬件对象
        sensor = clock_sensors[0]
        print(f"\n4. 深入分析时钟传感器和 CPU 硬件对象")
        print("-" * 80)

        sensor_clr_type = clr.GetClrType(type(sensor))
        print(f"传感器 CLR 类型: {sensor_clr_type.FullName}")

        # 尝试获取实际的 CPU 硬件类型
        if cpu_hardware_actual is None:
            cpu_hardware_actual = cpu_hardware

        cpu_hardware_type = clr.GetClrType(type(cpu_hardware_actual))
        print(f"\nCPU 硬件实际类型: {cpu_hardware_type.FullName}")

        # 尝试通过反射直接访问 Amd17Cpu 类型
        amd17_type = hardware_assembly.GetType("LibreHardwareMonitor.Hardware.Cpu.Amd17Cpu")
        if amd17_type:
            print(f"✅ 找到 Amd17Cpu 类型定义: {amd17_type.FullName}")
            print(f"   实际对象是否为 Amd17Cpu: {amd17_type.IsAssignableFrom(cpu_hardware_type)}")

        # 查看 CPU 硬件对象的所有字段
        print("\nCPU 硬件对象的所有字段:")
        cpu_fields = list(cpu_hardware_type.GetFields(
            System.Reflection.BindingFlags.NonPublic |
            System.Reflection.BindingFlags.Public |
            System.Reflection.BindingFlags.Instance |
            System.Reflection.BindingFlags.Static
        ))
        print(f"  共找到 {len(cpu_fields)} 个字段")
        for field in cpu_fields:
            field_name_lower = field.Name.lower()
            if any(keyword in field_name_lower for keyword in ["max", "frequency", "clock", "spec", "7700", "5300", "turbo", "boost", "base"]):
                try:
                    field_value = field.GetValue(cpu_hardware)
                    print(f"  ⭐ {field.Name}: {field_value} (类型: {field.FieldType})")
                except Exception as e:
                    print(f"  ⭐ {field.Name}: 无法访问 (类型: {field.FieldType}, 错误: {e})")

        # 查看 CPU 硬件对象的所有方法
        print("\nCPU 硬件对象的方法（查找 Max 或 Frequency 相关）:")
        cpu_methods = list(cpu_hardware_type.GetMethods(
            System.Reflection.BindingFlags.NonPublic |
            System.Reflection.BindingFlags.Public |
            System.Reflection.BindingFlags.Instance |
            System.Reflection.BindingFlags.Static
        ))
        relevant_methods = []
        for method in cpu_methods:
            method_name_lower = method.Name.lower()
            if any(keyword in method_name_lower for keyword in ["max", "frequency", "clock", "spec", "update", "init", "read", "get"]):
                params = ", ".join([f"{p.ParameterType.Name}" for p in method.GetParameters()])
                relevant_methods.append((method.Name, params, method))

        print(f"  共找到 {len(relevant_methods)} 个相关方法")
        for method_name, params, method in relevant_methods[:30]:  # 限制显示前30个
            print(f"  ⭐ {method_name}({params})")

        # 特别查找设置 Max 值的方法
        print("\n查找可能设置传感器 Max 值的方法:")
        for method_name, params, method in relevant_methods:
            if "set" in method_name.lower() or "update" in method_name.lower() or "read" in method_name.lower():
                print(f"  🔍 {method_name}({params})")

        # 查看 Amd17Cpu 类的静态字段（可能包含 CPU 规格数据库）
        print("\nCPU 硬件类的静态字段（可能包含 CPU 规格数据库）:")
        static_fields = list(cpu_hardware_type.GetFields(
            System.Reflection.BindingFlags.NonPublic |
            System.Reflection.BindingFlags.Public |
            System.Reflection.BindingFlags.Static
        ))
        for field in static_fields:
            field_name_lower = field.Name.lower()
            if any(keyword in field_name_lower for keyword in ["spec", "table", "dict", "db", "data", "7700"]):
                try:
                    field_value = field.GetValue(None)  # 静态字段
                    print(f"  ⭐ {field.Name}: {field_value} (类型: {field.FieldType})")
                except Exception as e:
                    print(f"  ⭐ {field.Name}: 无法访问 (类型: {field.FieldType}, 错误: {e})")

        # 查看传感器的所有字段值（特别关注 Max 相关字段）
        print("\n传感器的字段值（特别关注 Max 相关）:")
        fields = list(sensor_clr_type.GetFields(
            System.Reflection.BindingFlags.NonPublic |
            System.Reflection.BindingFlags.Public |
            System.Reflection.BindingFlags.Instance
        ))
        for field in fields:
            try:
                # 特别关注 Max 相关的字段
                if "max" in field.Name.lower() or "frequency" in field.Name.lower() or "clock" in field.Name.lower():
                    field_value = field.GetValue(sensor)
                    print(f"  ⭐ {field.Name}: {field_value} (类型: {field.FieldType})")
                elif field.Name in ["_trackMinMax", "_currentValue", "_sum", "_count"]:
                    field_value = field.GetValue(sensor)
                    print(f"  {field.Name}: {field_value} (类型: {field.FieldType})")
            except Exception as e:
                if "max" in field.Name.lower():
                    print(f"  ⭐ {field.Name}: 无法访问 ({e})")

        # 查看传感器的属性值
        print("\n传感器的属性值:")
        for prop in sensor_clr_type.GetProperties():
            try:
                prop_value = prop.GetValue(sensor)
                if prop_value is not None:
                    prop_str = str(prop_value)
                    if len(prop_str) > 100:
                        prop_str = prop_str[:100] + "..."
                    print(f"  {prop.Name}: {prop_str}")
            except Exception as e:
                pass

        # 多次更新并观察 Max 值的变化
        print("\n5. 观察 Max 值的变化（多次更新）...")
        print("-" * 80)

        import time
        for i in range(5):
            cpu_hardware.Update()
            for subhardware in cpu_hardware.SubHardware:
                subhardware.Update()

            time.sleep(0.1)

            for j, s in enumerate(clock_sensors[:3]):  # 只检查前3个
                raw_value = s.Value
                raw_max = s.Max
                raw_min = s.Min

                print(f"更新 {i+1} - 传感器 {j+1} ({s.Name}):")
                print(f"  Value: {raw_value} (类型: {type(raw_value)})")
                print(f"  Max: {raw_max} (类型: {type(raw_max)})")
                print(f"  Min: {raw_min} (类型: {type(raw_min)})")

                # 检查是否是 NaN
                if raw_value is not None:
                    try:
                        val = float(raw_value)
                        if math.isnan(val):
                            print(f"  ⚠️  Value 是 NaN")
                    except:
                        pass

                if raw_max is not None:
                    try:
                        max_val = float(raw_max)
                        if math.isnan(max_val):
                            print(f"  ⚠️  Max 是 NaN")
                        else:
                            print(f"  ✅ Max 有有效值: {max_val}")
                    except:
                        pass

        computer.Close()

        print("\n" + "=" * 80)
        print("反射分析完成")
        print("=" * 80)

    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        print("请确保已安装 pythonnet: pip install pythonnet")
    except Exception as e:
        print(f"❌ 分析失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    analyze_dll_with_reflection()

