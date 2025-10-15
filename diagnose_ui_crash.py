# -*- coding: utf-8 -*-
"""
诊断UI崩溃问题 - 逐步测试
"""

import os
import sys
from pathlib import Path

# 设置环境
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))
os.environ["CONFIG_FILE"] = str(project_root / "config" / "terminal_config.json")

print("=" * 70)
print("UI崩溃诊断")
print("=" * 70)

# 步骤1: 测试PySide6导入
print("\n[步骤1] 测试PySide6导入...")
try:
    from PySide6.QtWidgets import QApplication, QMainWindow, QLabel
    from PySide6.QtCore import Qt, QTimer

    print("✅ PySide6导入成功")
except Exception as e:
    print(f"❌ 导入失败: {e}")
    sys.exit(1)

# 步骤2: 创建QApplication
print("\n[步骤2] 创建QApplication...")
try:
    app = QApplication(sys.argv)
    print("✅ QApplication创建成功")
except Exception as e:
    print(f"❌ 创建失败: {e}")
    sys.exit(1)

# 步骤3: 创建简单窗口
print("\n[步骤3] 创建简单窗口...")
try:
    window = QMainWindow()
    window.setWindowTitle("诊断测试")
    window.resize(400, 300)
    print("✅ 窗口创建成功")
except Exception as e:
    print(f"❌ 窗口创建失败: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# 步骤4: 显示窗口
print("\n[步骤4] 显示窗口...")
try:
    window.show()
    print("✅ 窗口显示成功")
except Exception as e:
    print(f"❌ 显示失败: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

# 步骤5: 设置自动退出定时器
print("\n[步骤5] 设置5秒自动退出定时器...")
try:

    def auto_exit():
        print("\n✅ 窗口显示正常！5秒后自动退出")
        app.quit()

    QTimer.singleShot(5000, auto_exit)
    print("✅ 定时器设置成功")
except Exception as e:
    print(f"❌ 定时器设置失败: {e}")

# 步骤6: 进入事件循环
print("\n[步骤6] 进入Qt事件循环...")
print("  (窗口将显示5秒后自动关闭)")
try:
    exit_code = app.exec()
    print(f"\n✅ 事件循环正常退出，退出码: {exit_code}")
except Exception as e:
    print(f"\n❌ 事件循环异常: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 70)
print("✅ 所有测试通过！UI框架工作正常")
print("=" * 70)
