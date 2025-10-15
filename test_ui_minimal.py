# -*- coding: utf-8 -*-
"""
最小化UI测试 - 验证Qt框架是否能正常启动
"""

import os
import sys
from pathlib import Path

# 设置项目路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 设置环境变量
os.environ["CONFIG_FILE"] = str(project_root / "config" / "terminal_config.json")
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"

print("=" * 70)
print("最小化UI测试")
print("=" * 70)

try:
    print("\n[1/3] 导入PySide6...")
    from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
    from PySide6.QtCore import Qt

    print("✅ PySide6导入成功")

    print("\n[2/3] 创建QApplication...")
    app = QApplication(sys.argv)
    app.setApplicationName("UI测试")
    print("✅ QApplication创建成功")

    print("\n[3/3] 创建测试窗口...")
    window = QMainWindow()
    window.setWindowTitle("UI框架测试 - 基本窗口")
    window.resize(600, 400)

    central_widget = QWidget()
    layout = QVBoxLayout(central_widget)

    label = QLabel("✅ UI框架正常工作！\n\n这是一个最小化测试窗口。")
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setStyleSheet("font-size: 16px; padding: 20px;")
    layout.addWidget(label)

    window.setCentralWidget(central_widget)
    print("✅ 测试窗口创建成功")

    print("\n" + "=" * 70)
    print("显示窗口...")
    print("=" * 70)
    window.show()

    sys.exit(app.exec())

except Exception as e:
    print(f"\n❌ 测试失败: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)
