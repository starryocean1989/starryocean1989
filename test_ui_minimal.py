# -*- coding: utf-8 -*-
"""
最小化UI测试脚本 - 用于诊断UI显示问题.
"""

import os
import sys
from pathlib import Path

# 设置环境
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 设置Qt环境变量
os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"

def main():
    """最小化测试主函数."""
    print("🧪 最小化UI测试")
    print("=" * 40)
    
    try:
        print("1. 导入PySide6...")
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
        
        print("2. 创建QApplication...")
        app = QApplication(sys.argv)
        
        print("3. 创建简单窗口...")
        window = QMainWindow()
        window.setWindowTitle("星辰金融终端 - 测试窗口")
        window.resize(800, 600)
        
        # 创建中央控件
        central_widget = QWidget()
        window.setCentralWidget(central_widget)
        
        # 创建布局
        layout = QVBoxLayout(central_widget)
        
        # 添加标签
        label = QLabel("🎉 UI测试成功！\n\n如果您能看到这个窗口，说明UI显示正常。")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                color: #2196F3;
                background-color: #f5f5f5;
                padding: 20px;
                border: 2px solid #2196F3;
                border-radius: 10px;
            }
        """)
        layout.addWidget(label)
        
        print("4. 显示窗口...")
        window.show()
        
        # 强制显示
        window.raise_()
        window.activateWindow()
        
        # 检查窗口状态
        print(f"窗口可见性: {window.isVisible()}")
        print(f"窗口位置: ({window.x()}, {window.y()})")
        print(f"窗口大小: {window.width()}x{window.height()}")
        
        # 强制刷新
        app.processEvents()
        
        print("5. ✅ 窗口已显示，启动事件循环...")
        print("💡 如果您看不到窗口，请检查任务栏或Alt+Tab切换")
        
        # 运行事件循环
        return app.exec()
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())