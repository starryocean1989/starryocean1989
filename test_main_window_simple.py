# -*- coding: utf-8 -*-
"""
简化主窗口测试脚本.
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
os.environ["CONFIG_FILE"] = str(project_root / "config" / "terminal_config.json")

def main():
    """简化主窗口测试."""
    print("🧪 简化主窗口测试")
    print("=" * 40)
    
    try:
        print("1. 导入PySide6...")
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        
        print("2. 创建QApplication...")
        app = QApplication(sys.argv)
        app.setApplicationName("星辰金融终端")
        
        print("3. 导入主窗口类...")
        from ui.main_window import MainWindow
        
        print("4. 创建主窗口（不初始化后端）...")
        # 使用异步模式，避免后端初始化
        main_window = MainWindow(backend_ready=False)
        
        print("5. 设置窗口属性...")
        main_window.setWindowTitle("星辰金融终端 - 简化测试")
        main_window.resize(1200, 800)
        
        print("6. 显示窗口...")
        main_window.show()
        main_window.raise_()
        main_window.activateWindow()
        
        print(f"窗口可见性: {main_window.isVisible()}")
        print(f"窗口位置: ({main_window.x()}, {main_window.y()})")
        print(f"窗口大小: {main_window.width()}x{main_window.height()}")
        
        app.processEvents()
        
        print("7. ✅ 简化主窗口已显示，启动事件循环...")
        print("💡 这是不包含后端服务的UI框架")
        
        return app.exec()
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())