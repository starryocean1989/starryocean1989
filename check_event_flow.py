# -*- coding: utf-8 -*-
"""检查事件流：从监控进程到SystemManagerService到UI.

此脚本用于检查监控数据的完整流程。
"""

import time
import logging

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def check_event_flow():
    """检查事件流."""
    print("=" * 80)
    print("事件流检查工具")
    print("=" * 80)
    print()

    # 1. 导入必要的模块
    print("[步骤 1/4] 导入模块...")
    try:
        from backend.core.base import get_service_manager
        from backend.core.monitoring_events import (
            EVENT_SYSTEM_METRICS,
            EVENT_HARDWARE_SENSORS,
        )

        print("✅ 模块导入成功")
    except ImportError as e:
        print(f"❌ 模块导入失败: {e}")
        return False

    print()

    # 2. 获取SystemManagerService
    print("[步骤 2/4] 获取SystemManagerService...")
    try:
        service_manager = get_service_manager()
        system_service = service_manager.get_service("system_manager_service")

        if not system_service:
            print("❌ SystemManagerService未初始化")
            return False

        print("✅ SystemManagerService已初始化")
        print(f"   - 服务类型: {type(system_service)}")
        print(
            f"   - EventEngine: {'✅' if hasattr(system_service, 'event_engine') and system_service.event_engine else '❌'}"
        )

        if not hasattr(system_service, "event_engine") or not system_service.event_engine:
            print("❌ EventEngine不可用")
            return False

        print(f"   - EventEngine类型: {type(system_service.event_engine)}")

    except Exception as e:
        print(f"❌ 获取SystemManagerService失败: {e}")
        import traceback

        traceback.print_exc()
        return False

    print()

    # 3. 测试事件订阅
    print("[步骤 3/4] 测试事件订阅...")

    event_received = {
        EVENT_SYSTEM_METRICS: False,
        EVENT_HARDWARE_SENSORS: False,
    }

    def on_system_metrics(event):
        """系统指标事件处理器."""
        event_received[EVENT_SYSTEM_METRICS] = True
        data = event.data
        print(f"\n  ✅ 收到EVENT_SYSTEM_METRICS事件")
        print(f"     - 数据keys: {list(data.keys())}")
        print(f"     - CPU: {data.get('cpu_percent', 'N/A')}%")
        print(f"     - 网络速度: {data.get('network_speed', 'N/A')}")

    def on_hardware_sensors(event):
        """硬件传感器事件处理器."""
        event_received[EVENT_HARDWARE_SENSORS] = True
        data = event.data
        print(f"\n  ✅ 收到EVENT_HARDWARE_SENSORS事件")
        print(f"     - 数据keys: {list(data.keys())}")

        temperature_data = data.get("temperature", {})
        if temperature_data:
            print(f"     - 温度设备数量: {len(temperature_data)}")
            for device_name in list(temperature_data.keys())[:3]:
                print(f"       - {device_name}")
        else:
            print(f"     - 温度数据: 无")

    try:
        # 注册事件处理器
        event_engine = system_service.event_engine
        event_engine.register(EVENT_SYSTEM_METRICS, on_system_metrics)
        event_engine.register(EVENT_HARDWARE_SENSORS, on_hardware_sensors)

        print("✅ 事件处理器已注册")
        print("   等待事件（最多15秒）...")

        # 等待事件
        start_time = time.time()
        timeout = 15

        while (time.time() - start_time) < timeout:
            if all(event_received.values()):
                break
            time.sleep(0.1)

        # 取消注册
        event_engine.unregister(EVENT_SYSTEM_METRICS, on_system_metrics)
        event_engine.unregister(EVENT_HARDWARE_SENSORS, on_hardware_sensors)

        print()

    except Exception as e:
        print(f"❌ 事件订阅测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False

    print()

    # 4. 分析结果
    print("[步骤 4/4] 分析结果...")
    print("=" * 80)

    print("\n事件接收情况:")
    print(
        f"  - EVENT_SYSTEM_METRICS: {'✅ 已接收' if event_received[EVENT_SYSTEM_METRICS] else '❌ 未接收'}"
    )
    print(
        f"  - EVENT_HARDWARE_SENSORS: {'✅ 已接收' if event_received[EVENT_HARDWARE_SENSORS] else '❌ 未接收'}"
    )

    print("\n" + "=" * 80)
    print("【诊断结论】")
    print("-" * 40)

    if all(event_received.values()):
        print("✅ 事件流正常！所有事件都能正确接收。")
        print("\n如果UI仍然没有显示数据，请检查:")
        print("  1. UI是否正确订阅了这些事件")
        print("  2. UI的事件处理函数是否有错误")
        print("  3. UI更新是否被节流机制过度限制")
        print("  4. 检查浏览器控制台或UI日志")
    else:
        if not event_received[EVENT_SYSTEM_METRICS]:
            print("❌ EVENT_SYSTEM_METRICS事件未接收")
            print("   可能原因:")
            print("     - SystemManagerService的监控推送线程未启动")
            print("     - ZMQ连接失败")
            print("     - EventEngine未正确分发事件")

        if not event_received[EVENT_HARDWARE_SENSORS]:
            print("❌ EVENT_HARDWARE_SENSORS事件未接收")
            print("   可能原因:")
            print("     - 监控进程未采集hardware数据")
            print("     - SystemManagerService未分发hardware事件")
            print("     - data['hardware']为空导致事件未创建")
            print("\n   建议:")
            print("     - 在SystemManagerService._dispatch_monitoring_events()添加debug日志")
            print("     - 检查监控进程的hardware数据采集逻辑")

    print("\n" + "=" * 80)

    return all(event_received.values())


if __name__ == "__main__":
    import sys

    # 需要在主程序运行时执行此脚本
    print("\n⚠️  注意: 此脚本需要在主程序运行时执行")
    print("   请先启动主程序，然后在另一个终端运行此脚本\n")

    try:
        success = check_event_flow()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n用户中断")
        sys.exit(130)
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
