# -*- coding: utf-8 -*-
"""
UI应用测试脚本
直接运行UI应用并捕获错误
"""

import sys
import os
import traceback

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_ui_app():
    """测试UI应用"""
    print("🖥️  测试星辰金融终端UI应用")
    print("=" * 50)

    try:
        # 导入必要的模块
        print("📦 导入模块...")
        from PySide6.QtWidgets import QApplication
        from ui.main_window import MainWindow
        print("✅ 模块导入成功")

        # 创建应用
        print("🚀 创建应用程序...")
        app = QApplication(sys.argv)
        app.setApplicationName("星辰金融终端")
        app.setApplicationVersion("5.0.0")
        print("✅ 应用程序创建成功")

        # 创建主窗口
        print("🏠 创建主窗口...")
        main_window = MainWindow()
        print("✅ 主窗口创建成功")

        # 显示窗口
        print("👁️ 显示窗口...")
        main_window.show()
        print("✅ 窗口显示成功")

        # 设置窗口大小和位置
        main_window.resize(1200, 800)
        main_window.move(100, 100)
        print("✅ 窗口布局设置完成")

        print("\n🎯 应用程序已启动！")
        print("💡 提示:")
        print("  - 窗口应该已经显示在屏幕上")
        print("  - 如果看不到窗口，请检查任务栏或使用Alt+Tab切换")
        print("  - 按窗口的关闭按钮退出")

        # 运行应用
        print("🔄 启动事件循环...")
        exit_code = app.exec()
        print(f"✅ 应用程序正常退出，退出码: {exit_code}")

        return True

    except Exception as e:
        print(f"❌ UI应用启动失败: {e}")
        print("\n📋 错误详情:")
        traceback.print_exc()
        return False


def main():
    """主函数"""
    success = test_ui_app()

    if success:
        print("\n🎉 UI应用测试成功！")
        return 0
    else:
        print("\n❌ UI应用测试失败！")
        return 1


if __name__ == "__main__":
    sys.exit(main())
