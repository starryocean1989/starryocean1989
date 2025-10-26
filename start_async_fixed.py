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
    """设置日志系统（仅Terminal输出，数据库日志自动记录）."""
    import logging

    # 🔧 关键修复：配置root logger，让所有logger都有输出
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # 如果root logger还没有handler，添加控制台handler
    if not root_logger.handlers:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

    # 返回StartupOptimized专用logger
    from backend.core.base import setup_logging as base_setup_logging

    return base_setup_logging(name="StartupOptimized", level="INFO")


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
    print("🚀 星辰金融终端 - 启动中（单进程多线程模式）")
    print("=" * 70)

    # ==================== 阶段-1：管理员权限检查 ====================
    # 设置项目路径（在检查权限前需要先设置）
    project_root_path = Path(__file__).parent
    if str(project_root_path) not in sys.path:
        sys.path.insert(0, str(project_root_path))

    from backend.core.admin_utils import is_admin, run_as_admin
    from backend.core.terminal_output import print_stage
    from backend.core.config import get_settings, update_capabilities

    # 读取启动策略
    startup_settings = get_settings().startup
    admin_policy = getattr(startup_settings, "admin_policy", "auto")

    # 能力位：是否管理员
    has_admin = is_admin()
    update_capabilities(
        {
            "is_admin": bool(has_admin),
            # 缺少管理员权限时，降级禁用硬件传感器与SMART
            "hardware_monitoring_enabled": bool(has_admin),
            "smart_enabled": bool(has_admin),
        }
    )

    if not has_admin:
        print_stage(
            "ADMIN-CHECK",
            "未能获取管理员权限，部分功能将降级",
            success=False,
            error_detail="硬件传感器/SMART将禁用；系统指标仍可用。",
        )
        if admin_policy == "auto":
            print("\n正在请求管理员权限...")
            print("（如果出现UAC提示，请点击'是'）\n")
            # 自动以管理员身份重启（失败则继续降级）
            run_as_admin()
        elif admin_policy == "ask":
            # 交互式策略留空：不阻塞启动
            pass
    else:
        print_stage("ADMIN-CHECK", "已具有管理员权限", success=True)

    # ==================== 阶段-0.5：清理旧监控进程（改为UI后后台执行） ====================
    print_stage("CLEANUP-OLD", "已延后至UI显示后在后台执行", success=True)

    try:
        # ==================== 阶段0：环境准备 ====================
        env_time = setup_environment()
        print_stage("ENV-SETUP", "环境准备完成", success=True)

        # 初始化日志系统
        logger = setup_logging()
        logger.info("[ENV-SETUP] 环境准备完成，耗时 %.0fms", env_time)
        logger.info("=" * 60)
        logger.info("系统启动优化流程开始")
        logger.info("=" * 60)

        # 配置Debug输出
        from backend.core.terminal_output import configure_debug

        # 启用Debug模块（监控、数据、行情看板）
        configure_debug(
            enabled_modules=["monitor", "data", "market_board", "data_center", "system_manager"],
            debug_level="normal",  # brief | normal | detailed
            terminal_output=True,
        )
        logger.info("[DEBUG-CONFIG] Debug输出已配置（normal级别）")

        # ==================== 阶段1：Qt框架初始化 ====================
        stage1_start = time.time()
        logger.info("[QT-INIT] 开始Qt框架初始化")

        from PySide6.QtWidgets import QApplication

        app = QApplication(sys.argv)
        app.setApplicationName("星辰金融终端")
        app.setApplicationVersion("5.0.0")
        app.setOrganizationName("星辰科技")

        stage1_time = (time.time() - stage1_start) * 1000
        logger.info("[QT-INIT] ✅ QApplication创建成功，耗时 %.0fms", stage1_time)

        # 加载配置文件
        from backend.core.config import init_settings

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
        print_stage("QT-INIT", "Qt框架初始化完成", success=True)
        logger.info("[QT-INIT] ✅ Qt框架初始化完成，总耗时 %.0fms", qt_total_time)

        # ==================== 阶段2：UI框架创建 ====================
        stage2_start = time.time()
        logger.info("[UI-FRAME] 开始创建UI框架（backend_ready=False）")

        from ui.main_window import MainWindow

        main_window = MainWindow(backend_ready=False)

        stage2_time = (time.time() - stage2_start) * 1000
        logger.info("[UI-FRAME] ✅ 主窗口框架创建完成，耗时 %.0fms", stage2_time)

        # 显示主窗口
        main_window.show()
        main_window.raise_()
        main_window.activateWindow()

        ui_visible_time = (time.time() - startup_start) * 1000
        print_stage("UI-FRAME", "主窗口已显示", success=True)
        try:
            from backend.core.config import get_settings as _get_settings

            target_ms = int(getattr(_get_settings().startup, "ui_target_ms", 2000))
        except Exception:
            target_ms = 2000
        logger.info(
            "[UI-FRAME] ✅ 主窗口已显示，从启动到UI可见耗时 %.0fms（目标：< %dms）",
            ui_visible_time,
            target_ms,
        )
        # 启动指标：UI可见时延
        try:
            logger.info("[METRIC] startup.ui_visible_ms=%d", int(ui_visible_time))
        except Exception:
            pass

        # ==================== 阶段2.5：主线程初始化 EventEngine/MainEngine ====================
        logger.info("[VNPY-CORE] 开始在主线程初始化 EventEngine 和 MainEngine")

        vnpy_start = time.time()
        vnpy_success = True
        vnpy_error_detail = ""

        try:
            from vnpy.event import EventEngine
            from vnpy.trader.engine import MainEngine
            from backend.core.base import set_event_engine, set_main_engine

            # 创建 EventEngine（会自动启动工作线程）
            event_engine = EventEngine(interval=1)
            logger.info("[VNPY-CORE] ✅ EventEngine 创建成功（工作线程已启动）")

            # 创建 MainEngine
            main_engine = MainEngine(event_engine)
            logger.info("[VNPY-CORE] ✅ MainEngine 创建成功")

            # 注册到全局
            set_event_engine(event_engine)
            set_main_engine(main_engine)
            logger.info("[VNPY-CORE] ✅ EventEngine 和 MainEngine 已注册到全局")

            # 🔧 立即注入占位方法（供 vnpy_chartwizard 使用）
            try:
                logger.info("[VNPY-CORE] 开始注入 MainEngine 数据接口占位方法...")

                def placeholder_get_contracts():
                    """占位方法：返回空列表，等待后台更新"""
                    logger.debug("[PLACEHOLDER] get_all_contracts 被调用（等待后台更新）")
                    return []

                def placeholder_load_bars(*_args, **_kwargs):
                    """占位方法：返回空列表，等待后台更新"""
                    logger.debug("[PLACEHOLDER] load_bar_data 被调用（等待后台更新）")
                    return []

                main_engine.get_all_contracts = placeholder_get_contracts  # type: ignore[attr-defined]
                main_engine.load_bar_data = placeholder_load_bars  # type: ignore[attr-defined]

                logger.info(
                    "[VNPY-CORE] ✅ MainEngine 占位方法已注入（后续将由 UnifiedDataManager 更新）"
                )

            except Exception as e:
                logger.error("[VNPY-CORE] ❌ 注入占位方法失败: %s", e, exc_info=True)

            # 添加策略应用（静默失败）
            app_failed = []
            try:
                from vnpy_ctastrategy import CtaStrategyApp

                main_engine.add_app(CtaStrategyApp)
                logger.info("[VNPY-CORE] ✅ CtaStrategyApp 已添加")
            except Exception as e:
                logger.error(
                    "[VNPY-CORE] ❌ 添加 CtaStrategyApp 失败: %s (类型: %s)",
                    e,
                    type(e).__name__,
                    exc_info=True,
                )
                app_failed.append("CtaStrategy")

            try:
                from vnpy_algotrading import AlgoTradingApp

                main_engine.add_app(AlgoTradingApp)
                logger.info("[VNPY-CORE] ✅ AlgoTradingApp 已添加")
            except Exception as e:
                logger.error(
                    "[VNPY-CORE] ❌ 添加 AlgoTradingApp 失败: %s (类型: %s)",
                    e,
                    type(e).__name__,
                    exc_info=True,
                )
                app_failed.append("AlgoTrading")

            try:
                from vnpy_optionmaster import OptionMasterApp

                main_engine.add_app(OptionMasterApp)
                logger.info("[VNPY-CORE] ✅ OptionMasterApp 已添加")
            except Exception as e:
                logger.error(
                    "[VNPY-CORE] ❌ 添加 OptionMasterApp 失败: %s (类型: %s)",
                    e,
                    type(e).__name__,
                    exc_info=True,
                )
                app_failed.append("OptionMaster")

            try:
                from vnpy_portfoliostrategy import PortfolioStrategyApp

                main_engine.add_app(PortfolioStrategyApp)
                logger.info("[VNPY-CORE] ✅ PortfolioStrategyApp 已添加")
            except Exception as e:
                logger.error(
                    "[VNPY-CORE] ❌ 添加 PortfolioStrategyApp 失败: %s (类型: %s)",
                    e,
                    type(e).__name__,
                    exc_info=True,
                )
                app_failed.append("PortfolioStrategy")

            vnpy_time = (time.time() - vnpy_start) * 1000
            logger.info("[VNPY-CORE] ✅ VnPy 核心初始化完成，耗时 %.0fms", vnpy_time)

            if app_failed:
                vnpy_error_detail = f"部分应用未能加载: {', '.join(app_failed)}"

            # ==================== 阶段2.55：初始化日志管理系统 ====================
            # 🔧 关键修复：在EventEngine创建后立即初始化LogManager
            # 这样后续的所有日志都会被记录到数据库
            logger.info("[LOG-MANAGER] 开始初始化日志持久化系统")

            try:
                from backend.services.system_manager_service import get_log_manager

                # 获取LogManager并强制初始化（注入EventEngine）
                _ = get_log_manager(event_engine=event_engine, force_reinit=True)
                logger.info("[LOG-MANAGER] ✅ 日志管理系统初始化成功（日志将持久化到数据库）")
                print_stage("LOG-MANAGER", "日志持久化已启用", success=True)

            except Exception as e:
                logger.error("[LOG-MANAGER] ❌ 日志管理系统初始化失败: %s", e, exc_info=True)
                print_stage("LOG-MANAGER", "日志持久化启用失败", success=False, error_detail=str(e))
                # 不中断启动流程

        except Exception as e:
            logger.error("[VNPY-CORE] ❌ VnPy 核心初始化失败: %s", e, exc_info=True)
            vnpy_success = False
            vnpy_error_detail = str(e)

        # 输出统一状态
        print_stage(
            "VNPY-CORE", "VnPy核心初始化完成", success=vnpy_success, error_detail=vnpy_error_detail
        )

        # ==================== 后台任务：清理旧监控进程与端口预检 ====================
        try:
            import threading as _th_bg

            def _scan_listeners(_ports):
                """返回 {port: (pid, name, cmdline_str) or None}."""
                result = {}
                try:
                    import psutil as _ps

                    conns = _ps.net_connections(kind="inet")
                    port_to_pid = {}
                    for c in conns:
                        if c.laddr and c.status and str(c.status).lower() == "listen":
                            try:
                                port_to_pid[c.laddr.port] = c.pid
                            except Exception:
                                pass
                    for p in _ports:
                        pid = port_to_pid.get(p)
                        if pid:
                            try:
                                proc = _ps.Process(pid)
                                name = proc.name()
                                cmd = " ".join(proc.cmdline())
                                result[p] = (pid, name, cmd)
                            except Exception:
                                result[p] = (pid, None, None)
                        else:
                            result[p] = None
                except Exception:
                    for p in _ports:
                        result[p] = None
                return result

            def _background_cleanup_old_monitors_and_ports():
                try:
                    from backend.core.config import get_settings as _gs

                    _mon = _gs().monitor
                    default_ports = [
                        int(getattr(_mon, "port_alert_push", 5555)),
                        int(getattr(_mon, "port_status_pull", 5556)),
                        int(getattr(_mon, "port_query_rep", 5557)),
                    ]
                    fb_enabled = bool(getattr(_mon, "port_fallback_enabled", True))
                    fb_base = int(getattr(_mon, "port_fallback_base", 5565))
                    fb_span = int(getattr(_mon, "port_fallback_span", 3))
                    ports = list(default_ports)
                    if fb_enabled:
                        ports.extend([fb_base + i for i in range(max(3, fb_span))])

                    occ = _scan_listeners(ports)
                    to_kill = []
                    try:
                        import psutil as _ps

                        for port, info in occ.items():
                            if not info:
                                continue
                            pid, name, cmd = info
                            if pid and cmd and "monitor_process_entry.py" in cmd:
                                try:
                                    p = _ps.Process(pid)
                                    to_kill.append(p)
                                except Exception:
                                    pass

                        # 终止旧监控进程（如存在）
                        for p in to_kill:
                            try:
                                p.terminate()
                            except Exception:
                                pass
                        # 轮询等待端口释放（最多3秒，50ms步进）
                        end_t = time.time() + 3.0
                        while time.time() < end_t:
                            occ = _scan_listeners(ports)
                            if all(v is None for v in occ.values()):
                                break
                            time.sleep(0.05)

                        freed = [p for p, v in occ.items() if v is None]
                        logger.info(
                            "[CLEANUP-BG] 端口预检完成，已释放端口: %s",
                            ",".join(str(x) for x in freed),
                        )
                    except Exception as _e:
                        logger.warning("[CLEANUP-BG] 端口预检/清理失败: %s", _e)
                except Exception as _e:
                    logger.warning("[CLEANUP-BG] 后台清理任务异常: %s", _e)

            _th_bg.Thread(
                target=_background_cleanup_old_monitors_and_ports,
                name="BgCleanupOldMonitors",
                daemon=True,
            ).start()
        except Exception as _e:
            logger.warning("[CLEANUP-BG] 启动后台清理线程失败: %s", _e)

        # ==================== 阶段2.6：服务器池延迟初始化 ====================
        # 🔧 服务器池延迟初始化：由后台线程在首次使用时自动启动
        print_stage("SERVER-POOL", "延迟初始化（后台按需启动）", success=True)
        logger.info("[SERVER-POOL] 服务器池延迟初始化模式（后台线程按需启动）")

        # ==================== 阶段2.7：启动独立监控进程 ====================
        logger.info("[MONITOR-PROCESS] 启动独立监控进程")

        import subprocess

        # Path已在文件顶部导入，无需重复导入

        project_root = Path(__file__).parent
        monitor_script = (
            project_root / "backend" / "infrastructure" / "system_vnpy" / "monitor_process_entry.py"
        )

        # 修复：重定向到文件而不是PIPE，避免PIPE缓冲区填满导致死锁
        log_dir = project_root / "logs"
        log_dir.mkdir(exist_ok=True)

        monitor_stdout_file = open(log_dir / "monitor_stdout.log", "w", encoding="utf-8")
        monitor_stderr_file = open(log_dir / "monitor_stderr.log", "w", encoding="utf-8")

        monitor_process = subprocess.Popen(
            [sys.executable, str(monitor_script)],
            stdout=monitor_stdout_file,  # 重定向到文件
            stderr=monitor_stderr_file,  # 重定向到文件
            creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )

        # 保存进程句柄和文件句柄到全局，以便退出时清理
        import atexit
        import threading

        # 监控进程控制变量
        monitor_process_handle = [monitor_process]  # 使用列表以便在闭包中修改
        monitor_file_handles = [monitor_stdout_file, monitor_stderr_file]  # 文件句柄
        watchdog_running = [True]

        def cleanup_monitor():
            """清理监控进程（主进程退出时调用）."""
            watchdog_running[0] = False  # 停止看门狗线程
            logger.info("[CLEANUP] 开始清理监控进程...")

            if monitor_process_handle[0]:
                if monitor_process_handle[0].poll() is None:
                    # 进程仍在运行，先尝试优雅关闭
                    logger.info("[CLEANUP] 发送SIGTERM信号...")
                    monitor_process_handle[0].terminate()
                    try:
                        monitor_process_handle[0].wait(timeout=3)
                        logger.info("[CLEANUP] ✅ 监控进程已正常退出")
                    except subprocess.TimeoutExpired:
                        # 超时，强制kill
                        logger.warning("[CLEANUP] 监控进程未响应，强制终止...")
                        monitor_process_handle[0].kill()
                        try:
                            monitor_process_handle[0].wait(timeout=2)
                            logger.info("[CLEANUP] ✅ 监控进程已强制终止")
                        except Exception as e:
                            logger.error("[CLEANUP] ❌ 强制终止失败: %s", e)
                else:
                    logger.info(
                        "[CLEANUP] 监控进程已退出（退出码: %d）",
                        monitor_process_handle[0].returncode,
                    )

            # 额外等待，确保ZMQ端口完全释放
            logger.info("[CLEANUP] 等待5秒确保端口释放...")
            time.sleep(5)

            # 关闭文件句柄
            for f in monitor_file_handles:
                try:
                    if f:
                        f.close()
                except Exception:
                    pass

            logger.info("[CLEANUP] ✅ 监控进程清理完成")

        atexit.register(cleanup_monitor)

        def start_monitor_process():
            """启动监控进程（供看门狗调用）."""
            # 重新打开日志文件（追加模式）
            stdout_file = open(log_dir / "monitor_stdout.log", "a", encoding="utf-8")
            stderr_file = open(log_dir / "monitor_stderr.log", "a", encoding="utf-8")

            # 保存新的文件句柄
            monitor_file_handles[0] = stdout_file
            monitor_file_handles[1] = stderr_file

            return subprocess.Popen(
                [sys.executable, str(monitor_script)],
                stdout=stdout_file,  # 重定向到文件
                stderr=stderr_file,  # 重定向到文件
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )

        def monitor_watchdog():
            """监控进程看门狗线程（自动重启崩溃的监控进程）."""
            logger.info("[WATCHDOG] 监控进程看门狗线程已启动")
            restart_count = 0
            max_restarts_per_minute = 3  # 每分钟最多重启3次
            restart_timestamps = []

            while watchdog_running[0]:
                try:
                    # 检查监控进程是否存活
                    if monitor_process_handle[0] and monitor_process_handle[0].poll() is not None:
                        # 进程已退出
                        exit_code = monitor_process_handle[0].returncode
                        logger.warning(
                            "[WATCHDOG] 监控进程已退出（退出码: %d），准备重启...", exit_code
                        )

                        # 检查重启频率（防止无限重启）
                        current_time = time.time()
                        restart_timestamps = [
                            t for t in restart_timestamps if current_time - t < 60
                        ]

                        if len(restart_timestamps) >= max_restarts_per_minute:
                            logger.error(
                                "[WATCHDOG] ❌ 监控进程在1分钟内重启了%d次，超过限制，停止重启",
                                max_restarts_per_minute,
                            )
                            break

                        # 记录重启时间
                        restart_timestamps.append(current_time)
                        restart_count += 1

                        # 第1步：确保旧进程彻底终止
                        logger.info("[WATCHDOG] 第1步：清理旧进程...")
                        old_process = monitor_process_handle[0]
                        if old_process.poll() is None:
                            # 如果还在运行（不应该发生，但以防万一）
                            logger.warning("[WATCHDOG] 旧进程仍在运行，强制终止...")
                            old_process.kill()
                            try:
                                old_process.wait(timeout=2)
                            except Exception as e:
                                logger.error("[WATCHDOG] 强制终止旧进程失败: %s", e)

                        # 关闭旧的文件句柄
                        for f in monitor_file_handles:
                            try:
                                if f:
                                    f.close()
                            except Exception:
                                pass

                        # 第2步：等待端口释放
                        logger.info("[WATCHDOG] 第2步：等待10秒确保ZMQ端口完全释放...")
                        time.sleep(10)

                        # 第3步：重启监控进程
                        logger.info(
                            "[WATCHDOG] 第3步：启动新的监控进程（第%d次重启）...", restart_count
                        )
                        try:
                            monitor_process_handle[0] = start_monitor_process()
                            logger.info(
                                "[WATCHDOG] ✅ 监控进程已重启（PID: %d）",
                                monitor_process_handle[0].pid,
                            )

                            # 等待新进程初始化
                            # logger.info(...)  # 🔧 已精简：避免重启时刷屏
                            time.sleep(2)

                            # 验证新进程是否存活
                            if monitor_process_handle[0].poll() is not None:
                                logger.error(
                                    "[WATCHDOG] ❌ 新进程启动后立即退出（退出码: %d）",
                                    monitor_process_handle[0].returncode,
                                )
                            else:
                                logger.info("[WATCHDOG] ✅ 新进程运行正常")
                        except Exception as e:
                            logger.error("[WATCHDOG] ❌ 重启监控进程失败: %s", e, exc_info=True)

                    # 检查间隔
                    time.sleep(3)

                except Exception as e:
                    logger.error("[WATCHDOG] 看门狗线程异常: %s", e)
                    time.sleep(5)

            logger.info("[WATCHDOG] 监控进程看门狗线程已停止")

        # 启动看门狗线程
        watchdog_thread = threading.Thread(
            target=monitor_watchdog, name="MonitorWatchdog", daemon=True
        )
        watchdog_thread.start()

        logger.info("[MONITOR-PROCESS] ✅ 监控进程已启动（PID: %d）", monitor_process.pid)
        logger.info("[MONITOR-PROCESS] ✅ 监控进程看门狗已启动")
        print_stage(
            "MONITOR-PROCESS", f"监控进程已启动（PID: {monitor_process.pid}）", success=True
        )

        # 🎯 架构修复：监控握手延迟到SystemManagerService初始化时
        # 不在主流程中等待握手，避免阻塞启动（原来阻塞6.31秒）
        logger.info("[MONITOR-PROCESS] 监控进程已启动（握手延迟到SystemManagerService初始化）")

        # 设置环境变量，告知服务监控进程PID
        os.environ["MONITOR_PROCESS_PID"] = str(monitor_process.pid)
        logger.info("[MONITOR-PROCESS] 已设置环境变量 MONITOR_PROCESS_PID=%s", monitor_process.pid)

        # ==================== 定义可选服务后台加载器 ====================
        def _start_optional_services_loader(backend_result, main_window_instance):
            """启动可选服务后台加载器（快速启动优化）."""
            try:
                # 检查是否为快速启动模式
                if not backend_result.get("fast_startup", False):
                    logger.info("[OPTIONAL-SERVICES] 非快速启动模式，所有服务已加载")
                    return

                # 获取initializer实例
                initializer = backend_result.get("initializer")
                if not initializer:
                    logger.warning("[OPTIONAL-SERVICES] ⚠️ 未找到initializer实例，跳过可选服务加载")
                    return

                # 创建Qt后台加载器
                from PySide6.QtCore import QThread, QObject, Signal
                import logging as _logging

                class OptionalServicesLoader(QObject):
                    """可选服务后台加载器（Qt原生）."""

                    service_ready = Signal(str, bool)  # (service_name, success)
                    all_completed = Signal(dict)  # (results)

                    def __init__(self, service_initializer):
                        super().__init__()
                        self.initializer = service_initializer
                        self.logger = _logging.getLogger("OptionalServicesLoader")

                    def run(self):
                        """在QThread中执行可选服务加载."""
                        try:
                            self.logger.info("=" * 60)
                            self.logger.info("🚀 开始后台加载可选服务...")
                            self.logger.info("=" * 60)

                            def service_ready_callback(service_name, success):
                                """服务就绪回调."""
                                self.logger.info(
                                    "✅ 服务就绪: %s (%s)",
                                    service_name,
                                    "成功" if success else "失败",
                                )
                                self.service_ready.emit(service_name, success)

                            # 执行可选服务初始化
                            results = self.initializer.initialize_optional_services(
                                service_ready_callback
                            )

                            self.logger.info("✅ 可选服务后台加载完成")
                            self.all_completed.emit(results)

                        except Exception as e:
                            self.logger.error("可选服务后台加载异常: %s", e, exc_info=True)
                            self.all_completed.emit({})

                # 创建加载器和线程
                loader = OptionalServicesLoader(initializer)
                loader_thread = QThread()
                loader.moveToThread(loader_thread)

                # 连接信号
                loader_thread.started.connect(loader.run)
                loader.all_completed.connect(loader_thread.quit)

                # 连接到UI的服务就绪处理器
                if hasattr(main_window_instance, "on_service_ready"):
                    loader.service_ready.connect(main_window_instance.on_service_ready)
                else:
                    # 如果UI还未实现on_service_ready，只记录日志
                    loader.service_ready.connect(
                        lambda name, success: logger.info(
                            "[SERVICE-READY] %s: %s", name, "✅" if success else "❌"
                        )
                    )

                # 启动线程
                loader_thread.start()
                logger.info("[OPTIONAL-SERVICES] ✅ 后台加载器已启动")

                # 保存引用避免被垃圾回收
                main_window_instance._optional_loader = loader
                main_window_instance._optional_loader_thread = loader_thread

            except Exception as e:
                logger.error("[OPTIONAL-SERVICES] 启动后台加载器失败: %s", e, exc_info=True)

        # ==================== 连接后端初始化回调 ====================
        def on_startup_completed():
            """阶段4：UI功能激活（后端就绪后）."""
            logger.info("[UI-ACTIVATE] 开始激活UI功能...")

            try:
                activation_start = time.time()

                # 🔧 修复：在后端真正完成后，先标记backend_ready
                try:
                    if hasattr(main_window, "boot_orchestrator") and main_window.boot_orchestrator:
                        main_window.boot_orchestrator.mark_ready("backend_ready")
                        logger.info("[UI-ACTIVATE] ✅ backend_ready事件已触发")
                except Exception as e:
                    logger.error("[UI-ACTIVATE] ❌ 触发backend_ready事件失败: %s", e)

                # 步骤1: 初始化主窗口的功能界面
                logger.info("[UI-ACTIVATE] 调用 initialize_function_interfaces_after_backend()")
                main_window.initialize_function_interfaces_after_backend()
                logger.info("[UI-ACTIVATE] ✅ 功能界面初始化完成")

                # 步骤2: 隐藏启动画面
                logger.info("[UI-ACTIVATE] 隐藏启动画面")
                coordinator.hide_splash(main_window)
                logger.info("[UI-ACTIVATE] ✅ 启动画面已隐藏")

                # 🔧 修复Qt Timer跨线程问题：在UI激活完成后触发Qt原生的后台验证
                # 延迟500ms确保UI完全就绪
                logger.info("[UI-ACTIVATE] 准备启动Qt原生后台验证...")
                from PySide6.QtCore import QTimer

                QTimer.singleShot(500, lambda: main_window._start_background_validation())

                # 步骤3: 启动后台服务加载器（快速启动优化）
                logger.info("[UI-ACTIVATE] 启动可选服务后台加载...")
                _start_optional_services_loader(coordinator.backend_result, main_window)

                activation_time = (time.time() - activation_start) * 1000
                total_time = (time.time() - startup_start) * 1000

                print_stage("UI-ACTIVATE", "UI功能激活完成", success=True)

                print("\n" + "=" * 70)
                print("✅ 系统启动完成！")
                print(f"   - 总启动时间: {total_time:.0f}ms")
                print("=" * 70)

                logger.info("[UI-ACTIVATE] ✅ UI功能激活完成，耗时 %.0fms", activation_time)
                logger.info("=" * 60)
                logger.info("✅ 系统启动完成，总耗时 %.0fms（目标：< 5000ms）", total_time)
                logger.info("=" * 60)
                # 启动指标：后端就绪时延
                try:
                    logger.info("[METRIC] startup.backend_ready_ms=%d", int(total_time))
                except Exception:
                    pass

                # ==================== 服务器池后台预热（非阻塞） ====================
                try:

                    def _warmup_server_pool():
                        try:
                            # ✅ 修复：导入模块中的单例实例，而不是模块本身
                            from backend.infrastructure.data_module_vnpy.load_balancer import (
                                server_pool_manager,
                            )

                            t0 = time.time()
                            # 若已在运行或缓存有效，跳过
                            try:
                                if (
                                    hasattr(server_pool_manager, "is_running")
                                    and server_pool_manager.is_running()
                                ):
                                    logger.info("[SERVER-POOL] 已在运行，跳过预热")
                                    return
                            except Exception:
                                pass
                            try:
                                if (
                                    hasattr(server_pool_manager, "is_cache_valid")
                                    and server_pool_manager.is_cache_valid()
                                ):
                                    logger.info("[SERVER-POOL] 缓存有效，跳过预热")
                                    return
                            except Exception:
                                pass

                            logger.info("[SERVER-POOL] 开始后台预热...")
                            server_pool_manager.start()
                            warm_ms = int((time.time() - t0) * 1000)
                            logger.info("[SERVER-POOL] ✅ 预热完成，用时 %dms", warm_ms)
                            try:
                                logger.info("[METRIC] server_pool.warmup_ms=%d", warm_ms)
                            except Exception:
                                pass
                        except Exception as warm_e:
                            logger.error("[SERVER-POOL] 预热失败: %s", warm_e, exc_info=True)

                    import threading as _th

                    _th.Thread(
                        target=_warmup_server_pool, name="ServerPoolWarmup", daemon=True
                    ).start()
                except Exception as e:
                    logger.error("[SERVER-POOL] 启动后台预热线程失败: %s", e)

            except Exception as e:
                logger.error("[UI-ACTIVATE] ❌ UI激活过程发生异常: %s", e, exc_info=True)
                print_stage(
                    "UI-ACTIVATE",
                    "UI激活失败",
                    success=False,
                    error_detail=f"{e}\n主窗口框架仍可使用，但部分功能可能不可用",
                )
                # 不抛出异常，让主窗口保持显示

        def on_startup_failed(error: str):
            """启动失败处理."""
            logger.error("[BACKEND-INIT] ❌ 后端初始化失败: %s", error)
            coordinator.hide_splash()
            print_stage(
                "BACKEND-INIT",
                "后端初始化失败",
                success=False,
                error_detail=f"{error}\nUI框架仍可使用，但功能受限",
            )

        coordinator.startup_completed.connect(on_startup_completed)
        coordinator.startup_failed.connect(on_startup_failed)

        # ==================== 阶段3：启动后端初始化（异步）====================
        logger.info("[BACKEND-INIT] 启动后端初始化工作线程")
        coordinator.start()
        print_stage("BACKEND-INIT", "后端初始化已开始（后台线程运行）", success=True)
        logger.info("[BACKEND-INIT] ✅ 后台初始化线程已启动")

        # ==================== 启动Qt事件循环 ====================
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
