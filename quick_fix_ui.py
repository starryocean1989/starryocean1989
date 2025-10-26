# -*- coding: utf-8 -*-
"""快速修复UI显示问题 - 添加临时调试代码.

此脚本会在UI代码中添加调试日志，帮助定位问题。
"""

import os
import shutil
from datetime import datetime


def backup_file(file_path):
    """备份文件."""
    if os.path.exists(file_path):
        backup_path = f"{file_path}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy2(file_path, backup_path)
        print(f"✅ 已备份: {backup_path}")
        return True
    return False


def add_debug_to_ui():
    """在UI中添加调试代码."""
    ui_file = "ui/modules/system_manager_view.py"

    if not os.path.exists(ui_file):
        print(f"❌ 文件不存在: {ui_file}")
        return False

    print("=" * 80)
    print("快速修复UI显示问题")
    print("=" * 80)
    print()

    # 备份原文件
    if not backup_file(ui_file):
        print("❌ 备份失败")
        return False

    # 读取文件
    with open(ui_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 检查是否已经添加过调试代码
    if "🔥 UI_DEBUG:" in content:
        print("⚠️ 调试代码已存在，跳过")
        return True

    # 在 _on_hardware_sensors_event 方法开头添加调试代码
    debug_code = """        # 🔥 UI_DEBUG: 添加调试日志
        print("=" * 80)
        print(f"🔥 UI_DEBUG: _on_hardware_sensors_event 被调用！")
        print(f"🔥 UI_DEBUG: hardware_data keys: {list(event.data.keys()) if isinstance(event.data, dict) else 'N/A'}")
        if isinstance(event.data, dict) and "temperature" in event.data:
            print(f"🔥 UI_DEBUG: 温度设备: {list(event.data['temperature'].keys())}")
        print("=" * 80)
"""

    # 查找插入位置
    target = '    def _on_hardware_sensors_event(self, event):\n        """处理硬件传感器事件（独立）."""\n        try:'

    if target in content:
        new_content = content.replace(
            target,
            f'    def _on_hardware_sensors_event(self, event):\n        """处理硬件传感器事件（独立）."""\n{debug_code}\n        try:',
        )

        # 写回文件
        with open(ui_file, "w", encoding="utf-8") as f:
            f.write(new_content)

        print("✅ 已添加调试代码到 _on_hardware_sensors_event")
        print(f"✅ 文件已更新: {ui_file}")
        print()
        print("下一步:")
        print("  1. 重启程序")
        print("  2. 查看终端输出的 🔥 UI_DEBUG 信息")
        print("  3. 如果没有看到调试信息，说明事件未被触发")
        print()
        return True
    else:
        print("❌ 未找到目标代码位置")
        print("   可能UI代码结构已改变")
        return False


def add_debug_to_system_status_update():
    """在系统状态更新方法中添加调试."""
    ui_file = "ui/modules/system_manager_view.py"

    if not os.path.exists(ui_file):
        return False

    with open(ui_file, "r", encoding="utf-8") as f:
        content = f.read()

    # 在 _update_system_status_from_data 中添加调试
    debug_code_2 = """        # 🔥 UI_DEBUG: 热力图更新
        if hasattr(self, "status_heatmap_network_speed"):
            print(f"🔥 UI_DEBUG: 更新网络速度热力图: {max_network_speed:.2f} MB/s")
        else:
            print(f"🔥 UI_DEBUG: ⚠️ status_heatmap_network_speed 不存在！")

        if hasattr(self, "status_heatmap_cpu_temp"):
            print(f"🔥 UI_DEBUG: 更新CPU温度热力图: {cpu_temp:.1f}°C")
        else:
            print(f"🔥 UI_DEBUG: ⚠️ status_heatmap_cpu_temp 不存在！")
"""

    # 查找插入位置 - 在热力图更新之前
    target_2 = '            if hasattr(self, "status_heatmap_network_speed"):\n                self.status_heatmap_network_speed.update_value(max_network_speed)'

    if target_2 in content and "🔥 UI_DEBUG: 热力图更新" not in content:
        new_content = content.replace(target_2, f"{debug_code_2}\n{target_2}")

        with open(ui_file, "w", encoding="utf-8") as f:
            f.write(new_content)

        print("✅ 已添加调试代码到 _update_system_status_from_data")
        return True

    return False


if __name__ == "__main__":
    print()
    print("⚠️  此脚本会修改UI代码，请确保:")
    print("   1. 程序当前未运行")
    print("   2. 已备份重要数据")
    print()
    input("按 Enter 键继续，或 Ctrl+C 取消...")
    print()

    success1 = add_debug_to_ui()
    success2 = add_debug_to_system_status_update()

    if success1 or success2:
        print()
        print("=" * 80)
        print("✅ 调试代码添加完成！")
        print()
        print("恢复方法:")
        print("  如果需要恢复原文件，运行:")
        print("  - 找到 ui/modules/system_manager_view.py.backup.* 文件")
        print("  - 复制回 system_manager_view.py")
        print("=" * 80)
    else:
        print()
        print("❌ 添加调试代码失败")
        print("   请手动添加或查看文件结构")
