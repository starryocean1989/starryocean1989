# -*- coding: utf-8 -*-
"""
测试脚本：在 CPU 负载下测试 AMD Ryzen 7 7700 时钟传感器读取

某些时钟传感器只有在 CPU 有负载时才能返回有效值
"""
import sys
import os
from pathlib import Path
import threading
import time

# 添加项目根目录到路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import logging
import math

# 配置日志
logging.basicConfig(
    level=logging.INFO,  # 降低日志级别，避免太多 DEBUG 信息
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# CPU 负载生成器
cpu_load_running = False

def cpu_load_worker():
    """生成 CPU 负载"""
    global cpu_load_running
    while cpu_load_running:
        # 简单的计算密集型任务
        result = 0
        for i in range(1000000):
            result += i * i
        time.sleep(0.001)  # 避免完全占用 CPU


def test_clock_with_cpu_load():
    """在 CPU 负载下测试时钟传感器"""
    global cpu_load_running

    print("=" * 80)
    print("测试：在 CPU 负载下读取 AMD Ryzen 7 7700 时钟传感器")
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

        # 查找 CPU 硬件
        cpu_hardware = None
        for hardware in computer.Hardware:
            if "AMD" in str(hardware.Name) or "RYZEN" in str(hardware.Name).upper() or "CPU" in str(hardware.Name).upper():
                cpu_hardware = hardware
                break

        if not cpu_hardware:
            print("❌ 未找到 CPU 硬件")
            computer.Close()
            return False

        print(f"✅ 找到 CPU 硬件: {cpu_hardware.Name}")

        # 查找时钟传感器
        clock_sensors = []
        cpu_hardware.Update()
        for sensor in cpu_hardware.Sensors:
            if sensor.SensorType == SensorType.Clock:
                clock_sensors.append(sensor)

        # 检查子硬件
        for subhardware in cpu_hardware.SubHardware:
            subhardware.Update()
            for sensor in subhardware.Sensors:
                if sensor.SensorType == SensorType.Clock:
                    clock_sensors.append(sensor)

        if not clock_sensors:
            print("❌ 未找到时钟传感器")
            computer.Close()
            return False

        print(f"✅ 找到 {len(clock_sensors)} 个时钟传感器")

        # 测试1：无负载时读取
        print("\n3. 测试1：无 CPU 负载时读取...")
        print("-" * 80)

        cpu_hardware.Update()
        for subhardware in cpu_hardware.SubHardware:
            subhardware.Update()

        time.sleep(0.1)

        found_valid_value = False
        for sensor in clock_sensors:
            raw_value = sensor.Value
            try:
                if raw_value is not None:
                    val = float(raw_value)
                    if not math.isnan(val) and val > 0:
                        print(f"   ✅ {sensor.Name}: {val:.2f} MHz")
                        found_valid_value = True
                    else:
                        print(f"   ❌ {sensor.Name}: NaN")
                else:
                    print(f"   ❌ {sensor.Name}: None")
            except (ValueError, TypeError):
                print(f"   ❌ {sensor.Name}: 无法转换")

        if found_valid_value:
            print("\n✅ 无负载时已能读取到有效值！")
            computer.Close()
            return True

        # 测试2：有负载时读取
        print("\n4. 测试2：启动 CPU 负载后读取...")
        print("-" * 80)

        # 启动多个线程生成 CPU 负载
        cpu_load_running = True
        num_threads = 4  # 使用4个线程生成负载
        threads = []

        print(f"   启动 {num_threads} 个负载线程...")
        for i in range(num_threads):
            t = threading.Thread(target=cpu_load_worker, daemon=True)
            t.start()
            threads.append(t)

        # 等待 CPU 负载生效
        print("   等待 CPU 负载生效（2秒）...")
        time.sleep(2)

        # 多次更新并读取
        print("   开始读取时钟传感器（多次更新）...")
        for attempt in range(10):
            cpu_hardware.Update()
            for subhardware in cpu_hardware.SubHardware:
                subhardware.Update()

            time.sleep(0.1)  # 每次更新后等待

            # 检查是否有有效值
            for sensor in clock_sensors:
                raw_value = sensor.Value
                try:
                    if raw_value is not None:
                        val = float(raw_value)
                        if not math.isnan(val) and val > 0:
                            print(f"   ✅ [{attempt+1}] {sensor.Name}: {val:.2f} MHz")
                            found_valid_value = True
                except (ValueError, TypeError):
                    pass

            if found_valid_value:
                break

        # 停止 CPU 负载
        cpu_load_running = False
        time.sleep(0.5)

        if found_valid_value:
            print("\n✅ 在 CPU 负载下成功读取到有效值！")
        else:
            print("\n❌ 即使在 CPU 负载下也未能读取到有效值")
            print("   可能的原因：")
            print("   1. 需要更长的等待时间")
            print("   2. 需要更高的 CPU 负载")
            print("   3. LibreHardwareMonitor DLL 版本问题")
            print("   4. 权限问题（需要管理员权限）")

        computer.Close()
        return found_valid_value

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        cpu_load_running = False
        return False


def test_with_wmi_fallback():
    """尝试使用 WMI 作为备选方案"""
    print("\n" + "=" * 80)
    print("备选方案：尝试使用 WMI 读取 CPU 频率")
    print("=" * 80)

    try:
        import wmi

        print("\n1. 连接 WMI...")
        w = wmi.WMI()

        print("2. 查询 CPU 信息...")
        processors = w.Win32_Processor()

        for proc in processors:
            print(f"\n   CPU: {proc.Name}")
            if proc.MaxClockSpeed:
                print(f"   最大时钟速度: {proc.MaxClockSpeed} MHz")
            if proc.CurrentClockSpeed:
                print(f"   当前时钟速度: {proc.CurrentClockSpeed} MHz")

        return True

    except ImportError:
        print("❌ WMI 模块未安装（可选）")
        return False
    except Exception as e:
        print(f"❌ WMI 查询失败: {e}")
        return False


def main():
    """主测试函数"""
    print("\n" + "=" * 80)
    print("AMD Ryzen 7 7700 时钟传感器读取测试（带 CPU 负载）")
    print("目标：验证在 CPU 负载下是否能读取到时钟频率")
    print("=" * 80)

    # 测试1：带 CPU 负载
    result1 = test_clock_with_cpu_load()

    # 测试2：WMI 备选方案
    result2 = test_with_wmi_fallback()

    # 最终总结
    print("\n" + "=" * 80)
    print("最终测试结果")
    print("=" * 80)

    if result1:
        print("\n✅ CPU 负载测试：成功读取到时钟频率")
    else:
        print("\n❌ CPU 负载测试：未能读取到时钟频率")

    if result2:
        print("✅ WMI 备选方案：可用")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    main()


