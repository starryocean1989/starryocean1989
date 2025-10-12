#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试应用退出问题的诊断脚本
"""

import sys
import os
import logging
import traceback
import signal
import atexit
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 设置详细的日志记录
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('debug_exit.log', encoding='utf-8')
    ]
)

logger = logging.getLogger('DebugExit')

def exit_handler():
    """退出处理器"""
    logger.critical("🚨 应用即将退出！")
    print("🚨 exit_handler: 应用即将退出！")

def signal_handler(signum, frame):
    """信号处理器"""
    logger.critical(f"🚨 收到信号: {signum}")
    print(f"🚨 signal_handler: 收到信号 {signum}")
    sys.exit(1)

def excepthook(exc_type, exc_value, exc_traceback):
    """全局异常处理器"""
    logger.critical("🚨 未捕获的异常:")
    logger.critical(f"异常类型: {exc_type}")
    logger.critical(f"异常值: {exc_value}")
    logger.critical(f"异常追踪:\n{''.join(traceback.format_tb(exc_traceback))}")
    print(f"🚨 未捕获的异常: {exc_type.__name__}: {exc_value}")

def main():
    """主函数"""
    print("🔍 调试应用退出问题")
    print("=" * 60)
    
    # 注册退出和信号处理器
    atexit.register(exit_handler)
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    sys.excepthook = excepthook
    
    try:
        # 设置Qt环境变量 - 抑制QStyleHints警告
        os.environ['QT_LOGGING_RULES'] = 'qt.core.qobject.connect.debug=false'
        os.environ['QT_AUTO_SCREEN_SCALE_FACTOR'] = '1'
        os.environ['QT_ENABLE_HIGHDPI_SCALING'] = '0'
        
        print("1. 导入PySide6...")
        from PySide6.QtWidgets import QApplication, QMainWindow, QLabel, QVBoxLayout, QWidget
        from PySide6.QtCore import Qt, QTimer, Signal, QObject
        from PySide6.QtGui import QCloseEvent
        
        print("2. 创建QApplication...")
        app = QApplication.instance() or QApplication(sys.argv)
        app.setAttribute(Qt.AA_ShareOpenGLContexts)
        
        print("3. 创建测试窗口...")
        class TestWindow(QMainWindow):
            def __init__(self):
                super().__init__()
                self.setWindowTitle("调试窗口 - 监控退出")
                self.setGeometry(100, 100, 400, 300)
                
                # 创建中央部件
                central = QWidget()
                self.setCentralWidget(central)
                layout = QVBoxLayout(central)
                
                label = QLabel("应用正在运行...\n监控退出事件")
                label.setAlignment(Qt.AlignCenter)
                layout.addWidget(label)
                
                # 定时器更新状态
                self.timer = QTimer()
                self.timer.timeout.connect(self.update_status)
                self.timer.start(1000)
                self.counter = 0
                self.label = label
                
            def update_status(self):
                self.counter += 1
                self.label.setText(f"应用正在运行... ({self.counter}秒)\n监控退出事件")
                logger.debug(f"应用运行状态: {self.counter}秒")
                
            def closeEvent(self, event: QCloseEvent):
                logger.critical("🚨 窗口关闭事件被触发！")
                print("🚨 窗口关闭事件被触发！")
                event.accept()
        
        print("4. 显示窗口...")
        window = TestWindow()
        window.show()
        
        print("5. 检查窗口状态...")
        print(f"窗口可见: {window.isVisible()}")
        print(f"窗口位置: {window.pos()}")
        print(f"窗口大小: {window.size()}")
        
        print("6. 现在导入后端组件（可能触发退出）...")
        
        # 逐步导入后端组件，观察哪个导致退出
        try:
            print("  导入启动协调器...")
            from ui.startup_coordinator import StartupCoordinator
            print("  ✓ 启动协调器导入成功")
            
            print("  导入主窗口...")
            from ui.main_window import MainWindow
            print("  ✓ 主窗口导入成功")
            
            print("  创建启动协调器...")
            coordinator = StartupCoordinator(app)
            print("  ✓ 启动协调器创建成功")
            
            print("  创建主窗口...")
            main_window = MainWindow()
            print("  ✓ 主窗口创建成功")
            
            print("  启动后端初始化...")
            coordinator.initialize_backend_async()
            print("  ✓ 后端初始化启动成功")
            
        except Exception as e:
            logger.error(f"后端组件导入/初始化失败: {e}", exc_info=True)
            print(f"❌ 后端组件失败: {e}")
        
        print("7. 启动事件循环...")
        logger.info("开始运行Qt事件循环")
        
        # 启动事件循环
        exit_code = app.exec()
        logger.critical(f"🚨 Qt事件循环退出，退出码: {exit_code}")
        print(f"🚨 Qt事件循环退出，退出码: {exit_code}")
        
    except Exception as e:
        logger.critical(f"主函数异常: {e}", exc_info=True)
        print(f"❌ 主函数异常: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    try:
        exit_code = main()
        print(f"脚本退出，退出码: {exit_code}")
        sys.exit(exit_code)
    except Exception as e:
        print(f"❌ 脚本执行异常: {e}")
        sys.exit(1)