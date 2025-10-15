# -*- coding: utf-8 -*-
"""
异步启动脚本 - 修复UI显示问题.

使用启动协调器实现UI先显示，后端异步加载。
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

def setup_logging():
    """设置日志."""
    import logging
    from backend.core.utils import setup_logging
    return setup_logging(name="AsyncStart", level="INFO", log_file="logs/async_start.log")

def main():
    """异步启动主函数."""
    print("="*70)
    print("🚀 星辰金融终端 - 启动中")
    print("="*70)
    
    try:
        logger = setup_logging()
        logger.info("开始异步启动流程...")
        
        print("\n[步骤 1/9] 导入PySide6模块...")
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        print("        ✅ PySide6模块导入成功")
        
        print("\n[步骤 2/9] 创建QApplication实例...")
        app = QApplication(sys.argv)
        app.setApplicationName("星辰金融终端")
        app.setApplicationVersion("5.0.0")
        app.setOrganizationName("星辰科技")
        print("        ✅ QApplication创建成功")
        
        print("\n[步骤 3/9] 加载配置文件...")
        from backend.config import init_settings
        config_file = os.getenv("CONFIG_FILE")
        if config_file:
            print(f"        ℹ️  配置文件: {config_file}")
            init_settings(config_file)
        else:
            print("        ℹ️  使用默认配置")
            init_settings()
        print("        ✅ 配置加载成功")
        
        print("\n[步骤 4/9] 创建启动协调器...")
        from ui.startup_coordinator import StartupCoordinator
        coordinator = StartupCoordinator(app, config_already_initialized=True)
        print("        ✅ 启动协调器已创建")
        
        print("\n[步骤 5/9] 创建主窗口（异步模式）...")
        from ui.main_window import MainWindow
        main_window = MainWindow(backend_ready=False)
        print("        ✅ 主窗口已创建")
        
        print("\n[步骤 6/9] 显示主窗口界面...")
        main_window.show()
        main_window.raise_()
        main_window.activateWindow()
        print(f"        ✅ 窗口已显示 ({main_window.width()}x{main_window.height()})")
        
        print("\n[步骤 7/9] 连接后端初始化回调...")
        
        # 连接启动协调器信号
        def on_startup_completed():
            """启动完成回调."""
            logger.info("后端初始化完成，连接功能界面...")
            coordinator.hide_splash()
            main_window.initialize_function_interfaces_after_backend()
            print("\n" + "="*70)
            print("✅ 后端服务已就绪，所有功能已激活！")
            print("="*70)
        
        def on_startup_failed(error: str):
            """启动失败回调."""
            logger.error("后端初始化失败: %s", error)
            coordinator.hide_splash()
            print("\n" + "="*70)
            print(f"⚠️  后端初始化失败: {error}")
            print("💡 UI框架仍可使用，但功能受限")
            print("="*70)
        
        coordinator.startup_completed.connect(on_startup_completed)
        coordinator.startup_failed.connect(on_startup_failed)
        print("        ✅ 回调函数已连接")
        
        print("\n[步骤 8/9] 启动后端服务初始化（异步）...")
        coordinator.start()
        print("        ✅ 后端初始化已开始（后台运行）")
        
        print("\n[步骤 9/9] 启动Qt事件循环...")
        print("        ℹ️  应用程序正在运行，等待用户操作...")
        print("="*70)
        
        return app.exec()
        
    except Exception as e:
        print("\n" + "="*70)
        print(f"❌ 启动失败: {e}")
        print("="*70)
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())