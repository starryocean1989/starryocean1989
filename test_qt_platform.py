# -*- coding: utf-8 -*-
"""测试Qt平台插件"""
import os
import sys

# 设置Qt平台插件调试
os.environ["QT_DEBUG_PLUGINS"] = "1"
os.environ["QT_QPA_PLATFORM"] = "windows"

print("测试Qt平台插件...")
print(f"Python版本: {sys.version}")
print(f"Python路径: {sys.executable}")

try:
    from PySide6 import QtCore

    print(f"✅ PySide6版本: {QtCore.qVersion()}")
    print(f"✅ Qt binding: {QtCore.__file__}")

    # 测试导入QApplication
    from PySide6.QtWidgets import QApplication

    print("✅ QApplication导入成功")

    # 尝试创建应用（但不启动事件循环）
    print("\n尝试创建QApplication实例...")
    app = QApplication([])
    print("✅ QApplication实例创建成功")
    print(f"  平台名称: {app.platformName()}")

except Exception as e:
    print(f"❌ 错误: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)

print("\n✅ 所有测试通过！")
