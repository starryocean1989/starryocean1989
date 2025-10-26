# -*- coding: utf-8 -*-
"""诊断监控数据问题：检查网络速度和CPU温度数据.

此脚本用于诊断系统监控中网络速度和CPU温度没有读数的问题。
"""

import zmq
import json
import sys
import time


def diagnose_monitoring_data():
    """诊断监控数据问题."""
    print("=" * 80)
    print("系统监控数据诊断工具")
    print("=" * 80)
    print()

    # 1. 连接到监控进程
    print("[步骤 1/3] 连接到监控进程ZMQ服务...")
    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect("tcp://127.0.0.1:5557")
    socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5秒超时

    try:
        # 2. 查询监控数据
        print("[步骤 2/3] 查询监控数据...")
        socket.send_json({"action": "get_data"})
        data = socket.recv_json()

        print("✅ 成功接收监控数据")
        print()

        # 3. 检查系统数据
        print("[步骤 3/3] 分析监控数据...")
        print("=" * 80)

        # 3.1 检查网络速度
        print("\n【网络速度数据检查】")
        print("-" * 40)

        system_data = data.get("system", {})
        network_speed = system_data.get("network_speed", {})

        if not network_speed:
            print("❌ network_speed字段不存在或为空")
            print("\n可能的原因:")
            print("  1. 监控进程未正确采集网络速度数据")
            print("  2. psutil模块的net_io_counters()调用失败")
            print("  3. 网络采集间隔太短导致数据为0")
            print("\n建议检查:")
            print("  - 查看 logs/monitor_stderr.log 中的错误信息")
            print("  - 确认 psutil 模块已安装: pip show psutil")
        else:
            print("✅ network_speed字段存在")
            print(f"  完整数据: {json.dumps(network_speed, indent=2, ensure_ascii=False)}")

            upload_speed = network_speed.get("upload_speed_kbps", 0)
            download_speed = network_speed.get("download_speed_kbps", 0)
            bandwidth_percent = network_speed.get("bandwidth_percent", 0)
            interface = network_speed.get("interface", "未知")

            print(f"\n  上传速度: {upload_speed:.2f} KB/s = {upload_speed/1024:.2f} MB/s")
            print(f"  下载速度: {download_speed:.2f} KB/s = {download_speed/1024:.2f} MB/s")
            print(f"  带宽占用: {bandwidth_percent:.1f}%")
            print(f"  网络接口: {interface}")

            if upload_speed == 0 and download_speed == 0:
                print("\n⚠️  警告: 网络速度为0")
                print("  这可能是正常的（系统空闲时），等待1秒后再次检查...")
                time.sleep(1)

                # 再次查询
                socket2 = context.socket(zmq.REQ)
                socket2.connect("tcp://127.0.0.1:5557")
                socket2.setsockopt(zmq.RCVTIMEO, 5000)
                socket2.send_json({"action": "get_data"})
                data2 = socket2.recv_json()
                socket2.close()

                network_speed2 = data2.get("system", {}).get("network_speed", {})
                upload_speed2 = network_speed2.get("upload_speed_kbps", 0)
                download_speed2 = network_speed2.get("download_speed_kbps", 0)

                print(f"\n  第二次检查:")
                print(f"    上传速度: {upload_speed2:.2f} KB/s")
                print(f"    下载速度: {download_speed2:.2f} KB/s")

                if upload_speed2 == 0 and download_speed2 == 0:
                    print("\n  分析: 网络速度持续为0，可能是系统空闲或网络采集有问题")
                else:
                    print("\n  分析: 网络速度正常（系统之前处于空闲状态）")

        # 3.2 检查CPU温度
        print("\n" + "=" * 80)
        print("\n【CPU温度数据检查】")
        print("-" * 40)

        hardware_data = data.get("hardware", {})

        if not hardware_data:
            print("❌ hardware字段不存在或为空")
            print("\n可能的原因:")
            print("  1. LibreHardwareMonitor DLL未安装或无法加载")
            print("  2. 未以管理员权限运行（硬件监控需要管理员权限）")
            print("  3. 硬件监控协程未正确启动")
            print("  4. 硬件不支持温度读取（如AMD RDNA 3显卡）")
            print("\n建议检查:")
            print(
                "  - 确认DLL文件存在: backend/infrastructure/system_vnpy/librehardwaremonitor/LibreHardwareMonitorLib.dll"
            )
            print("  - 以管理员身份重新运行程序")
            print("  - 查看 logs/monitor_stderr.log 中的错误信息")
        else:
            print("✅ hardware字段存在")

            temperature_data = hardware_data.get("temperature", {})

            if not temperature_data:
                print("⚠️  temperature字段为空")
                print("\n  这意味着:")
                print("    - LibreHardwareMonitor已加载，但未检测到温度传感器")
                print("    - 硬件可能不支持温度读取")
                print("\n  硬件数据keys:", list(hardware_data.keys()))
            else:
                print("✅ temperature字段存在")
                print(f"\n  检测到 {len(temperature_data)} 个温度设备:")

                cpu_temp_found = False

                for device_name, sensors in temperature_data.items():
                    print(f"\n  设备: {device_name}")

                    if not sensors or not isinstance(sensors, list):
                        print("    (无传感器数据)")
                        continue

                    # 检查是否是CPU温度
                    is_cpu = any(
                        keyword in device_name
                        for keyword in [
                            "CPU",
                            "ACPI",
                            "processor",
                            "Ryzen",
                            "Intel",
                            "Threadripper",
                        ]
                    )

                    if is_cpu:
                        cpu_temp_found = True
                        print("    ⭐ (CPU温度设备)")

                    for i, sensor in enumerate(sensors[:3]):  # 只显示前3个传感器
                        label = sensor.get("label", "未知")
                        current = sensor.get("current", 0)
                        high = sensor.get("high", "N/A")
                        critical = sensor.get("critical", "N/A")
                        unit = sensor.get("unit", "")

                        print(f"    传感器 {i+1}: {label}")
                        print(f"      当前值: {current}{unit}")
                        print(f"      高温阈值: {high}")
                        print(f"      临界阈值: {critical}")

                    if len(sensors) > 3:
                        print(f"    ... (共{len(sensors)}个传感器)")

                if not cpu_temp_found:
                    print("\n⚠️  警告: 未找到CPU温度设备")
                    print("  可能的原因:")
                    print("    - CPU型号不在识别列表中")
                    print("    - 需要更新LibreHardwareMonitor版本")

        # 3.3 检查UI显示逻辑
        print("\n" + "=" * 80)
        print("\n【UI显示逻辑检查】")
        print("-" * 40)

        print("\nUI从以下路径获取数据:")
        print(f"  网络速度: data['system']['network_speed']")
        print(f"    - 字段存在: {'✅' if network_speed else '❌'}")

        print(f"  CPU温度: data['hardware']['temperature'][设备名][0]['current']")
        print(f"    - hardware存在: {'✅' if hardware_data else '❌'}")
        print(f"    - temperature存在: {'✅' if temperature_data else '❌'}")

        if temperature_data:
            cpu_devices = [
                name
                for name in temperature_data.keys()
                if any(k in name for k in ["CPU", "ACPI", "processor", "Ryzen", "Intel"])
            ]
            print(f"    - CPU设备数量: {len(cpu_devices)}")
            if cpu_devices:
                print(f"    - CPU设备: {cpu_devices}")

        print("\n" + "=" * 80)
        print("\n【诊断总结】")
        print("-" * 40)

        issues = []

        if not network_speed:
            issues.append("网络速度数据缺失")
        elif (
            network_speed.get("upload_speed_kbps", 0) == 0
            and network_speed.get("download_speed_kbps", 0) == 0
        ):
            issues.append("网络速度为0（可能是空闲状态）")

        if not hardware_data:
            issues.append("硬件监控数据完全缺失")
        elif not temperature_data:
            issues.append("温度数据缺失（硬件可能不支持）")
        elif not cpu_temp_found:
            issues.append("CPU温度设备未识别")

        if not issues:
            print("✅ 所有数据正常！")
            print("\n如果UI仍然没有显示，请检查:")
            print("  1. SystemManagerService是否正确分发EVENT_HARDWARE_SENSORS事件")
            print("  2. UI是否正确订阅并处理事件")
            print("  3. 检查logs/systemmanager_debug.log")
        else:
            print("发现以下问题:")
            for i, issue in enumerate(issues, 1):
                print(f"  {i}. {issue}")

        print("\n" + "=" * 80)

    except zmq.Again:
        print("❌ 连接超时：监控进程未响应")
        print("\n可能的原因:")
        print("  1. 监控进程未启动")
        print("  2. ZMQ端口5557未监听")
        print("  3. 监控进程崩溃")
        print("\n建议:")
        print("  - 检查进程: tasklist | findstr python")
        print("  - 检查端口: netstat -ano | findstr 5557")
        print("  - 重新启动程序")
        return False

    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback

        traceback.print_exc()
        return False

    finally:
        socket.close()
        context.term()

    return True


if __name__ == "__main__":
    try:
        success = diagnose_monitoring_data()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n用户中断")
        sys.exit(130)
