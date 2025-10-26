# -*- coding: utf-8 -*-
"""实时监控测试 - 持续监控网络速度和CPU温度数据.

此脚本持续查询监控进程，模拟UI的数据获取过程。
"""

import zmq
import time
import sys
from datetime import datetime


def realtime_monitoring():
    """实时监控."""
    print("=" * 80)
    print("实时监控测试 - 模拟UI数据获取")
    print("=" * 80)
    print("\n按 Ctrl+C 停止\n")

    context = zmq.Context()
    socket = context.socket(zmq.REQ)
    socket.connect("tcp://127.0.0.1:5557")
    socket.setsockopt(zmq.RCVTIMEO, 3000)

    iteration = 0
    network_speed_count = 0
    cpu_temp_count = 0

    try:
        while True:
            iteration += 1
            timestamp = datetime.now().strftime("%H:%M:%S")

            try:
                # 查询监控数据
                socket.send_json({"action": "get_data"})
                data = socket.recv_json()

                # 检查网络速度
                network_speed = data.get("system", {}).get("network_speed", {})
                upload = network_speed.get("upload_speed_kbps", 0)
                download = network_speed.get("download_speed_kbps", 0)

                if upload > 0 or download > 0:
                    network_speed_count += 1

                # 检查CPU温度
                hardware_data = data.get("hardware", {})
                temperature_data = hardware_data.get("temperature", {})

                cpu_temp = None
                cpu_device = None
                for device_name, sensors in temperature_data.items():
                    if any(k in device_name for k in ["CPU", "Ryzen", "Intel", "ACPI"]):
                        if sensors and len(sensors) > 0:
                            cpu_temp = sensors[0].get("current", 0)
                            cpu_device = device_name
                            if cpu_temp > 0:
                                cpu_temp_count += 1
                                break

                # 显示结果
                print(f"[{timestamp}] 第 {iteration} 次查询:")
                print(
                    f"  网络速度: ↑{upload:6.2f} KB/s | ↓{download:7.2f} KB/s  "
                    + ("✅" if (upload > 0 or download > 0) else "⚠️ 0")
                )

                if cpu_temp and cpu_temp > 0:
                    print(f"  CPU温度:  {cpu_temp:.1f}°C ({cpu_device})  ✅")
                else:
                    print(f"  CPU温度:  N/A  ❌")

                print(
                    f"  统计: 网络有数据{network_speed_count}/{iteration}, CPU温度有数据{cpu_temp_count}/{iteration}"
                )
                print()

            except zmq.Again:
                print(f"[{timestamp}] ❌ 查询超时")
                print()

            except Exception as e:
                print(f"[{timestamp}] ❌ 错误: {e}")
                print()

            # 等待2秒（与UI更新频率一致）
            time.sleep(2)

    except KeyboardInterrupt:
        print("\n\n用户中断")
        print("=" * 80)
        print("统计结果:")
        print(f"  总查询次数: {iteration}")
        print(
            f"  网络速度有数据: {network_speed_count} 次 ({network_speed_count/iteration*100:.1f}%)"
        )
        print(f"  CPU温度有数据: {cpu_temp_count} 次 ({cpu_temp_count/iteration*100:.1f}%)")
        print("=" * 80)

    finally:
        socket.close()
        context.term()


if __name__ == "__main__":
    try:
        realtime_monitoring()
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
