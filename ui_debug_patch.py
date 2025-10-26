# -*- coding: utf-8 -*-
"""UI调试补丁 - 添加到UI中以诊断事件接收问题.

使用方法：
1. 将此代码添加到 ui/modules/system_manager_view.py 的 _on_hardware_sensors_event 方法开头
2. 重启程序
3. 查看终端输出
"""

# ============ 添加到 _on_hardware_sensors_event 方法开头 ============


def _on_hardware_sensors_event_DEBUG(self, event):
    """处理硬件传感器事件（DEBUG版本）."""

    # 🔥 DEBUG: 添加这些日志
    print("=" * 80)
    print(f"🔥 DEBUG: _on_hardware_sensors_event 被调用！")
    print(f"   - 事件类型: {type(event)}")
    print(f"   - 事件数据类型: {type(event.data)}")
    print(
        f"   - 事件数据keys: {list(event.data.keys()) if isinstance(event.data, dict) else 'N/A'}"
    )

    if isinstance(event.data, dict):
        hardware_data = event.data
        print(f"   - hardware_data keys: {list(hardware_data.keys())}")

        if "temperature" in hardware_data:
            temperature_data = hardware_data["temperature"]
            print(f"   - 温度设备数量: {len(temperature_data)}")
            for i, device_name in enumerate(list(temperature_data.keys())[:3]):
                print(f"     [{i+1}] {device_name}")
        else:
            print(f"   - ⚠️ temperature字段不存在")

    print("=" * 80)

    # 原有代码继续...
    try:
        hardware_data = event.data
        if not hardware_data:
            print("🔥 DEBUG: hardware_data为空，返回")
            return

        # 复用现有的更新逻辑
        self._update_hardware_sensors_from_data(hardware_data)

        print("🔥 DEBUG: 调用了 _update_hardware_sensors_from_data")

        # 更新CPU温度卡片
        if hasattr(self, "metric_card_cpu_temp"):
            print("🔥 DEBUG: metric_card_cpu_temp 存在")

            # 从hardware数据中提取CPU温度
            temperature_data = hardware_data.get("temperature", {})

            cpu_temp = None
            for device, sensors in temperature_data.items():
                if sensors and isinstance(sensors, list) and len(sensors) > 0:
                    if any(
                        keyword in device
                        for keyword in ["CPU", "ACPI", "processor", "Ryzen", "Intel"]
                    ):
                        temp = sensors[0].get("current", 0)
                        if temp > 0:
                            cpu_temp = temp
                            print(f"🔥 DEBUG: 找到CPU温度: {cpu_temp}°C (设备: {device})")
                            break

            if cpu_temp is not None:
                self.metric_card_cpu_temp.update_value(cpu_temp)
                print(f"🔥 DEBUG: 更新了CPU温度卡片: {cpu_temp}°C")
            else:
                print("🔥 DEBUG: ⚠️ 未找到CPU温度数据")
        else:
            print("🔥 DEBUG: ⚠️ metric_card_cpu_temp 不存在")

    except Exception as e:
        print(f"🔥 DEBUG: ❌ 异常: {e}")
        import traceback

        traceback.print_exc()
        self.logger.error("处理硬件传感器事件失败: %s", e)


# ============ 或者添加一个简单的测试函数 ============


def test_event_subscription():
    """测试事件订阅（在UI初始化后调用）."""
    print("\n" + "=" * 80)
    print("🔍 测试事件订阅")
    print("=" * 80)

    # 获取EventEngine
    from backend.core.base import get_service_manager

    service_manager = get_service_manager()
    system_service = service_manager.get_service("system_manager_service")

    if not system_service:
        print("❌ SystemManagerService未找到")
        return

    if not system_service.event_engine:
        print("❌ EventEngine不可用")
        return

    print(f"✅ EventEngine可用: {type(system_service.event_engine)}")

    # 检查是否有处理器注册
    from backend.core.monitoring_events import EVENT_HARDWARE_SENSORS

    # 注册一个测试处理器
    def test_handler(event):
        print(f"\n🎉 测试处理器收到事件: {EVENT_HARDWARE_SENSORS}")
        print(f"   数据keys: {list(event.data.keys())}")

    system_service.event_engine.register(EVENT_HARDWARE_SENSORS, test_handler)
    print(f"✅ 测试处理器已注册")

    # 等待5秒
    import time

    print("⏳ 等待5秒接收事件...")
    time.sleep(5)

    # 取消注册
    system_service.event_engine.unregister(EVENT_HARDWARE_SENSORS, test_handler)
    print("✅ 测试完成")
    print("=" * 80 + "\n")


# ============ 使用说明 ============
"""
方法1: 替换整个 _on_hardware_sensors_event 方法
1. 找到 ui/modules/system_manager_view.py 的 _on_hardware_sensors_event 方法
2. 用上面的 _on_hardware_sensors_event_DEBUG 替换它
3. 重启程序
4. 查看终端输出的DEBUG信息

方法2: 在UI初始化后调用测试函数
1. 在 ui/modules/system_manager_view.py 的 __init__ 方法最后添加:
   # DEBUG: 测试事件订阅
   from ui_debug_patch import test_event_subscription
   QTimer.singleShot(5000, test_event_subscription)  # 5秒后测试
2. 重启程序
3. 查看终端输出
"""
