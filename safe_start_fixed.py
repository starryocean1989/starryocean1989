# -*- coding: utf-8 -*-
"""
安全启动脚本 - 修复版本.

专门解决QStyleHints连接问题和UI进程崩溃问题。
"""

import logging
import os
import sys
import time
from pathlib import Path

def setup_environment():
    """设置环境变量和Qt参数."""
    # 设置Python解释器路径
    if not os.environ.get("PYTHONEXECUTABLE"):
        os.environ["PYTHONEXECUTABLE"] = sys.executable
    if not os.environ.get("QT_WEBENGINE_PYTHON_EXECUTABLE"):
        os.environ["QT_WEBENGINE_PYTHON_EXECUTABLE"] = sys.executable
    
    # 设置Qt环境变量以避免QStyleHints问题
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
    os.environ["QT_SCALE_FACTOR"] = "1"
    os.environ["QT_SCREEN_SCALE_FACTORS"] = "1"
    
    # 禁用Qt的一些可能导致问题的功能
    os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = ""
    os.environ["QT_LOGGING_RULES"] = "*.debug=false"
    
    # 确保项目根目录在Python路径中
    project_root = Path(__file__).parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))
    
    # 设置配置文件路径
    config_file = project_root / "config" / "terminal_config.json"
    os.environ["CONFIG_FILE"] = str(config_file)


def setup_logging():
    """设置日志系统."""
    logger = logging.getLogger("SafeStart")
    logger.setLevel(logging.INFO)
    
    # 控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # 文件处理器
    logs_path = Path(__file__).parent / "logs"
    logs_path.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(logs_path / "safe_start.log", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    return logger


def main():
    """主函数."""
    print("🚀 安全启动脚本 - 修复版本")
    print("=" * 60)
    
    # 设置环境
    setup_environment()
    logger = setup_logging()
    
    try:
        logger.info("开始安全启动流程...")
        
        # 延迟导入PySide6以确保环境变量生效
        logger.info("导入PySide6...")
        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication
        
        logger.info("创建QApplication...")
        app = QApplication(sys.argv)
        app.setApplicationName("星辰金融终端")
        app.setApplicationVersion("5.0.0")
        app.setOrganizationName("星辰科技")
        
        # 设置Qt属性以避免问题
        try:
            app.setAttribute(Qt.AA_DisableWindowContextHelpButton, True)
        except (AttributeError, TypeError):
            logger.warning("无法设置AA_DisableWindowContextHelpButton属性")
        
        try:
            app.setAttribute(Qt.AA_DontShowIconsInMenus, False)
        except (AttributeError, TypeError):
            logger.warning("无法设置AA_DontShowIconsInMenus属性")
        
        # 设置应用程序为前台
        try:
            import ctypes
            from ctypes import wintypes
            # Windows API调用以设置前台窗口
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception as e:
            logger.warning("无法设置进程为DPI感知: %s", e)
        
        logger.info("导入主窗口...")
        from ui.main_window import MainWindow
        
        logger.info("创建主窗口...")
        # 使用同步模式避免异步初始化问题
        main_window = MainWindow(backend_ready=True)
        
        logger.info("主窗口创建完成，准备显示...")
        
        logger.info("显示主窗口...")
        main_window.show()
        
        # 🔧 强制窗口显示并置顶
        main_window.raise_()
        main_window.activateWindow()
        main_window.setWindowState(main_window.windowState() & ~Qt.WindowState.WindowMinimized | Qt.WindowState.WindowActive)
        
        logger.info("主窗口已显示，检查状态...")
        if main_window.isVisible():
            logger.info("✅ 主窗口状态: 可见")
        else:
            logger.warning("⚠️ 主窗口状态: 不可见")
            
        # 检查窗口尺寸和位置
        geometry = main_window.geometry()
        logger.info("窗口几何信息: x=%d, y=%d, width=%d, height=%d", 
                   geometry.x(), geometry.y(), geometry.width(), geometry.height())
        
        # 尝试使用Windows API强制显示窗口
        try:
            import ctypes
            import time
            
            # 等待窗口完全初始化
            app.processEvents()
            time.sleep(0.5)
            
            # 获取窗口句柄
            hwnd = int(main_window.winId())
            if hwnd:
                # 强制显示窗口
                ctypes.windll.user32.ShowWindow(hwnd, 1)  # SW_SHOWNORMAL
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                ctypes.windll.user32.BringWindowToTop(hwnd)
                logger.info("✅ 使用Windows API强制显示窗口")
            else:
                logger.warning("⚠️ 无法获取窗口句柄")
        except Exception as e:
            logger.warning("无法使用Windows API显示窗口: %s", e)
        
        logger.info("✅ 启动成功！")
        print("✅ 应用启动成功！")
        print("💻 主窗口已显示")
        print("💡 如果遇到问题，请查看 logs/safe_start.log")
        
        # 运行事件循环
        logger.info("启动事件循环...")
        exit_code = app.exec()
        logger.info("事件循环结束，退出码: %d", exit_code)
        logger.info("应用退出")
        return exit_code
        
    except ImportError as e:
        logger.error("导入错误: %s", e)
        print(f"❌ 导入错误: {e}")
        print("💡 请确保已安装所有必要的依赖包")
        return 1
        
    except Exception as e:
        logger.error("启动失败: %s", e, exc_info=True)
        print(f"❌ 启动失败: {e}")
        print("💡 请查看 logs/safe_start.log 了解详细错误信息")
        return 1


if __name__ == "__main__":
    sys.exit(main())