# -*- coding: utf-8 -*-
"""
异步启动脚本 - 系统启动优化版.

实现分层启动策略：
- 阶段0: 环境准备（< 100ms）
- 阶段1: Qt框架初始化（< 500ms）
- 阶段2: UI框架创建（< 1s）
- 阶段3: 后端服务初始化（异步，2-5s）
- 阶段4: UI功能激活（主线程，1-2s）
"""

import os
import sys
import time
from pathlib import Path


def setup_environment():
    """阶段0：环境准备（< 100ms）.

    设置必要的环境变量和Python路径，不涉及任何业务逻辑。
    """
    start_time = time.time()

    # 设置项目路径
    project_root = Path(__file__).parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # 设置Python解释器路径（WebEngine子进程需要）
    if not os.environ.get("PYTHONEXECUTABLE"):
        os.environ["PYTHONEXECUTABLE"] = sys.executable
    if not os.environ.get("QT_WEBENGINE_PYTHON_EXECUTABLE"):
        os.environ["QT_WEBENGINE_PYTHON_EXECUTABLE"] = sys.executable

    # 设置Qt环境变量（避免缩放问题）
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"

    # 设置配置文件路径
    os.environ["CONFIG_FILE"] = str(project_root / "config" / "terminal_config.json")

    elapsed = (time.time() - start_time) * 1000
    return elapsed


def setup_logging():
    """设置日志系统."""
    import logging
    from backend.core.utils import setup_logging

    return setup_logging(
        name="StartupOptimized", level="INFO", log_file="logs/startup_optimized.log"
    )


def main():
    """优化后的启动主函数.

    分层启动策略：
    1. 环境准备（主线程，同步）
    2. Qt框架（主线程，同步）
    3. UI框架（主线程，同步）
    4. 后端服务（后台线程，异步）
    5. UI激活（主线程，后端就绪后）
    """
    startup_start = time.time()

    print("=" * 70)
    print("🚀 星辰金融终端 - 启动中")
    print("=" * 70)

    try:
        # ==================== 阶段0：环境准备 ====================
        print("\n[ENV-SETUP] 阶段0：环境准备...")
        env_time = setup_environment()
        print(f"[ENV-SETUP] ✅ 环境准备完成 ({env_time:.0f}ms)")

        # 初始化日志系统
        logger = setup_logging()
        logger.info("[ENV-SETUP] 环境准备完成，耗时 %.0fms", env_time)
        logger.info("=" * 60)
        logger.info("系统启动优化流程开始")
        logger.info("=" * 60)

        # ==================== 阶段1：Qt框架初始化 ====================
        stage1_start = time.time()
        print("\n[QT-INIT] 阶段1：Qt框架初始化...")
        logger.info("[QT-INIT] 开始Qt框架初始化")

        from PySide6.QtCore import Qt
        from PySide6.QtWidgets import QApplication

        app = QApplication(sys.argv)
        app.setApplicationName("星辰金融终端")
        app.setApplicationVersion("5.0.0")
        app.setOrganizationName("星辰科技")

        stage1_time = (time.time() - stage1_start) * 1000
        print(f"[QT-INIT] ✅ QApplication创建成功 ({stage1_time:.0f}ms)")
        logger.info("[QT-INIT] ✅ QApplication创建成功，耗时 %.0fms", stage1_time)

        # 加载配置文件
        from backend.config import init_settings

        config_file = os.getenv("CONFIG_FILE")
        if config_file:
            logger.info("[QT-INIT] 从环境变量加载配置: %s", config_file)
            init_settings(config_file)
        else:
            logger.info("[QT-INIT] 使用默认配置")
            init_settings()

        # 创建启动协调器
        from ui.startup_coordinator import StartupCoordinator

        coordinator = StartupCoordinator(app, config_already_initialized=True)

        qt_total_time = (time.time() - stage1_start) * 1000
        print(f"[QT-INIT] ✅ Qt框架初始化完成 ({qt_total_time:.0f}ms)")
        logger.info("[QT-INIT] ✅ Qt框架初始化完成，总耗时 %.0fms", qt_total_time)

        # ==================== 阶段2：UI框架创建 ====================
        stage2_start = time.time()
        print("\n[UI-FRAME] 阶段2：UI框架创建...")
        logger.info("[UI-FRAME] 开始创建UI框架（backend_ready=False）")

        from ui.main_window import MainWindow

        main_window = MainWindow(backend_ready=False)

        stage2_time = (time.time() - stage2_start) * 1000
        print(f"[UI-FRAME] ✅ 主窗口框架创建完成 ({stage2_time:.0f}ms)")
        logger.info("[UI-FRAME] ✅ 主窗口框架创建完成，耗时 %.0fms", stage2_time)

        # 显示主窗口
        main_window.show()
        main_window.raise_()
        main_window.activateWindow()

        ui_visible_time = (time.time() - startup_start) * 1000
        print(f"[UI-FRAME] ✅ 主窗口已显示 ({ui_visible_time:.0f}ms from start)")
        logger.info(
            "[UI-FRAME] ✅ 主窗口已显示，从启动到UI可见耗时 %.0fms（目标：< 2000ms）",
            ui_visible_time,
        )

        # ==================== 连接后端初始化回调 ====================
        def on_startup_completed():
            """阶段4：UI功能激活（后端就绪后）."""
            try:
                activation_start = time.time()
                logger.info("[UI-ACTIVATE] 后端初始化完成，开始激活UI功能")

                # 创建功能界面并连接信号
                logger.info("[UI-ACTIVATE] 开始初始化功能界面...")
                try:
                    main_window.initialize_function_interfaces_after_backend()
                    logger.info("[UI-ACTIVATE] ✅ 功能界面初始化完成")
                except Exception as ui_error:
                    logger.error("[UI-ACTIVATE] ❌ 功能界面初始化失败: %s", ui_error, exc_info=True)
                    # 即使失败，也继续显示主窗口
                    print(f"\n⚠️  功能界面初始化失败: {ui_error}")
                    print("💡 主窗口仍可使用，但部分功能不可用")

                # 确保主窗口可见
                logger.info("[UI-ACTIVATE] 确保主窗口可见...")
                main_window.show()
                main_window.raise_()
                main_window.activateWindow()
                logger.info("[UI-ACTIVATE] ✅ 主窗口已激活")

                # 隐藏启动画面
                logger.info("[UI-ACTIVATE] 隐藏启动画面...")
                coordinator.hide_splash(main_window)
                logger.info("[UI-ACTIVATE] ✅ 启动画面已隐藏")

                activation_time = (time.time() - activation_start) * 1000
                total_time = (time.time() - startup_start) * 1000

                print("\n" + "=" * 70)
                print(f"✅ 系统启动完成！")
                print(f"   - UI激活耗时: {activation_time:.0f}ms")
                print(f"   - 总启动时间: {total_time:.0f}ms")
                print("=" * 70)

                logger.info("[UI-ACTIVATE] ✅ UI功能激活完成，耗时 %.0fms", activation_time)
                logger.info("=" * 60)
                logger.info("✅ 系统启动完成，总耗时 %.0fms（目标：< 5000ms）", total_time)
                logger.info("=" * 60)

            except Exception as e:
                logger.error("[UI-ACTIVATE] ❌ UI激活过程发生异常: %s", e, exc_info=True)
                print("\n" + "=" * 70)
                print(f"⚠️  UI激活失败: {e}")
                print("💡 主窗口框架仍可使用，但部分功能可能不可用")
                print("=" * 70)
                # 不抛出异常，让主窗口保持显示

        def on_startup_failed(error: str):
            """启动失败处理."""
            logger.error("[BACKEND-INIT] ❌ 后端初始化失败: %s", error)
            coordinator.hide_splash()

            print("\n" + "=" * 70)
            print(f"⚠️  后端初始化失败: {error}")
            print("💡 UI框架仍可使用，但功能受限")
            print("=" * 70)

        coordinator.startup_completed.connect(on_startup_completed)
        coordinator.startup_failed.connect(on_startup_failed)

        # ==================== 阶段3：启动后端初始化（异步）====================
        print("\n[BACKEND-INIT] 阶段3：启动后端服务初始化（异步）...")
        logger.info("[BACKEND-INIT] 启动后端初始化工作线程")
        coordinator.start()
        print("[BACKEND-INIT] ✅ 后端初始化已开始（后台线程运行）")
        logger.info("[BACKEND-INIT] ✅ 后台初始化线程已启动")

        # ==================== 启动Qt事件循环 ====================
        print("\n[EVENT-LOOP] 进入Qt事件循环...")
        logger.info("[EVENT-LOOP] 启动Qt主事件循环")
        print("=" * 70)

        return app.exec()

    except Exception as e:
        print("\n" + "=" * 70)
        print(f"❌ 启动失败: {e}")
        print("=" * 70)
        import traceback

        traceback.print_exc()

        if "logger" in locals():
            logger.error("💥 启动流程发生严重异常", exc_info=True)

        return 1


if __name__ == "__main__":
    sys.exit(main())
