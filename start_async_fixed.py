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

import logging
import os
import sys
import time
from pathlib import Path


def setup_environment():
    """阶段0：环境准备（< 100ms）.

    设置必要的环境变量和Python路径，不涉及任何业务逻辑。
    """
    start_time = time.time()

    # 禁用Python字节码缓存，确保总是使用最新代码
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    sys.dont_write_bytecode = True

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
    """设置日志系统 - 使用MemoryHandler缓冲.

    Returns:
        tuple: (logger, memory_handler) - 启动logger和MemoryHandler实例
    """
    import sys
    from logging.handlers import MemoryHandler

    # 🔧 修复编码问题：确保stdout/stderr使用UTF-8编码
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore

    # 🔧 配置root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # 接收所有级别的日志

    # 创建MemoryHandler作为临时缓冲（容量10000条）
    # target先设为None，LoggingHub初始化后再设置
    memory_handler = MemoryHandler(capacity=10000, target=None)
    memory_handler.setLevel(logging.DEBUG)
    root_logger.addHandler(memory_handler)

    # 返回logger和memory_handler供后续使用
    from backend.core.base import setup_logging as base_setup_logging

    logger = base_setup_logging(name="StartupOptimized", level="INFO")

    # ✅ 关键修复：移除logger自己的handlers，避免绕过LoggingHub
    # base_setup_logging会给logger添加StreamHandler，导致日志直接输出到stdout
    # 我们需要所有日志都通过LoggingHub统一路由
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
        handler.close()

    # ✅ 设置propagate=True，让日志传播到root logger，经过LoggingHub处理
    logger.propagate = True

    return logger, memory_handler


def cleanup_all_logger_handlers():
    """清理所有logger的handlers，确保所有日志都经过LoggingHub.

    这个函数会：
    1. 移除所有logger的StreamHandler（避免绕过LoggingHub直接输出）
    2. 设置所有logger的propagate=True（让日志传播到root logger）
    """
    import logging

    # 获取所有已创建的logger
    # 使用getattr避免linter错误，loggerDict是标准的logging API
    logger_dict = getattr(logging.root.manager, "loggerDict", {})
    all_loggers = [logging.getLogger(name) for name in logger_dict]
    all_loggers.append(logging.root)

    cleaned_count = 0

    for lgr in all_loggers:
        # 跳过root logger（它应该只有LoggingHub和MemoryHandler）
        if lgr == logging.root:
            continue

        # 移除所有StreamHandler（这些会直接输出到stdout，绕过LoggingHub）
        handlers_to_remove = []
        for handler in lgr.handlers[:]:
            if isinstance(handler, logging.StreamHandler):
                handlers_to_remove.append(handler)

        for handler in handlers_to_remove:
            lgr.removeHandler(handler)
            handler.close()
            cleaned_count += 1

        # 设置propagate=True，让日志传播到root logger
        if not lgr.propagate:
            lgr.propagate = True

    return cleaned_count


def initialize_logging_hub(logger, memory_handler):
    """初始化LoggingHub并重放缓冲日志.

    Args:
        logger: 启动logger
        memory_handler: MemoryHandler实例

    Returns:
        logging_hub实例或None
    """
    try:
        from backend.infrastructure.system_vnpy.unified_log_system import get_ai_log_handler
        from backend.infrastructure.system_vnpy.unified_log_system import get_logging_hub
        from backend.infrastructure.system_vnpy.unified_log_system import start_ai_process

        root_logger = logging.getLogger()

        # 1. 初始化LoggingHub
        logging_hub = get_logging_hub()

        # 2. v5.0已移除set_replay_targets，不再需要配置重放目标
        # LoggingHub会自动处理所有日志分发

        # 3. 创建并注入handlers
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.DEBUG)  # LoggingHub内部会根据规则过滤
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        )
        console_handler.setFormatter(formatter)
        logging_hub.set_console_handler(console_handler)

        # ✅ 创建常规文件Handler（logs/terminal.log）
        log_dir = Path("logs")
        log_dir.mkdir(exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "terminal.log", mode="a", encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)  # 接收所有级别
        file_handler.setFormatter(formatter)
        logging_hub.set_file_handler(file_handler)

        ai_handler = get_ai_log_handler()
        logging_hub.set_ai_log_handler(ai_handler)

        # 4. 启动AI流程
        ai_log_file = start_ai_process(
            "startup",
            metadata={
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "platform": sys.platform,
            },
        )

        # 5. 将LoggingHub添加到root logger
        root_logger.addHandler(logging_hub)

        # 6. 设置MemoryHandler的target为LoggingHub
        memory_handler.setTarget(logging_hub)

        # 7. v5.0不再需要replay模式，直接刷新MemoryHandler
        # LoggingHub会自动通过emit方法处理所有日志
        buffered_count = len(memory_handler.buffer)
        memory_handler.flush()

        # 8. 移除MemoryHandler（已完成使命）
        root_logger.removeHandler(memory_handler)
        memory_handler.close()

        # 11. 全局清理：移除所有logger的StreamHandler，确保所有日志都经过LoggingHub
        cleaned_count = cleanup_all_logger_handlers()

        # 12. 使用logger输出（此时已经过LoggingHub）
        logger.info(f"✅ LoggingHub已初始化（v5.0），重放了 {buffered_count} 条缓冲日志")
        logger.info(f"✅ 全局清理了 {cleaned_count} 个StreamHandler，确保所有日志统一路由")
        logger.info(f"AI日志文件: {ai_log_file}")

        return logging_hub

    except Exception as e:
        # 降级处理
        print(f"[日志系统] ❌ LoggingHub初始化失败: {e}")
        import traceback

        traceback.print_exc()

        # 添加简单的StreamHandler作为降级
        root_logger = logging.getLogger()
        if not any(isinstance(h, logging.StreamHandler) for h in root_logger.handlers):
            fallback = logging.StreamHandler(sys.stdout)
            fallback.setLevel(logging.INFO)
            root_logger.addHandler(fallback)

        # 刷新MemoryHandler到降级handler
        memory_handler.setTarget(fallback)
        memory_handler.flush()

        return None


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

    # ==================== 启动早期阶段：使用print ====================
    # 注：此时日志系统尚未初始化，使用print输出
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
            # 注：此时日志系统尚未初始化，使用print输出
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

        # 初始化日志系统（使用MemoryHandler缓冲）
        logger, memory_handler = setup_logging()

        # 此时所有日志调用都会被MemoryHandler缓冲，不会输出到控制台
        # 只有print_stage的直接打印会显示

        # ==================== 阶段切换：进入startup阶段 ====================
        from backend.infrastructure.system_vnpy.unified_log_system import get_logging_hub

        hub = get_logging_hub()
        hub.set_stage("startup")

        # 创建阶段logger（在LoggingHub初始化前，日志会被缓冲）
        stage_logger = logging.getLogger("startup.stage")
        stage_logger.info("📍 系统启动开始")

        logger.debug("[ENV-SETUP] 环境准备完成，耗时 %.0fms", env_time)

        # 配置Debug输出
        from backend.core.terminal_output import configure_debug

        # 启用Debug模块（监控、数据、行情看板）
        configure_debug(
            enabled_modules=["monitor", "data", "market_board", "data_center", "system_manager"],
            debug_level="normal",  # brief | normal | detailed
            terminal_output=True,
        )
        logger.debug("[DEBUG-CONFIG] Debug输出已配置（normal级别）")

        # ==================== 阶段1：Qt框架初始化 ====================
        stage1_start = time.time()
        logger.debug("[QT-INIT] Qt框架初始化中...")

        from PySide6.QtWidgets import QApplication

        app = QApplication(sys.argv)
        app.setApplicationName("星辰金融终端")
        app.setApplicationVersion("5.0.0")
        app.setOrganizationName("星辰科技")

        stage1_time = (time.time() - stage1_start) * 1000
        logger.debug("[QT-INIT] QApplication创建成功，耗时 %.0fms", stage1_time)

        # 加载配置文件
        from backend.core.config import init_settings

        config_file = os.getenv("CONFIG_FILE")
        if config_file:
            logger.debug("[QT-INIT] 从环境变量加载配置: %s", config_file)
            init_settings(config_file)
        else:
            logger.debug("[QT-INIT] 使用默认配置")
            init_settings()

        # ==================== 初始化LoggingHub并重放缓冲日志 ====================
        # 在配置加载完成后，初始化LoggingHub并重放所有缓冲的日志
        logging_hub = initialize_logging_hub(logger, memory_handler)
        if not logging_hub:
            logger.warning("LoggingHub初始化失败，使用降级日志输出")

        # 创建启动协调器
        from ui.startup_coordinator import StartupCoordinator

        coordinator = StartupCoordinator(app, config_already_initialized=True)

        qt_total_time = (time.time() - stage1_start) * 1000
        print_stage("QT-INIT", "Qt框架初始化完成", success=True)
        stage_logger.info("Qt框架初始化完成（耗时: %.0fms）", qt_total_time)

        # ==================== 阶段2：UI框架创建 ====================
        stage2_start = time.time()
        logger.debug("[UI-FRAME] 创建UI框架中...")

        from ui.main_window import MainWindow

        main_window = MainWindow(backend_ready=False)

        stage2_time = (time.time() - stage2_start) * 1000
        logger.debug("[UI-FRAME] 主窗口框架创建完成，耗时 %.0fms", stage2_time)

        # 显示主窗口
        main_window.show()
        main_window.raise_()
        main_window.activateWindow()

        ui_visible_time = (time.time() - startup_start) * 1000
        print_stage("UI-FRAME", "主窗口已显示", success=True)
        stage_logger.info("主窗口已显示（耗时: %.0fms）", ui_visible_time)
        try:
            from backend.core.config import get_settings as _get_settings

            target_ms = int(getattr(_get_settings().startup, "ui_target_ms", 2000))
        except Exception:
            target_ms = 2000
        logger.debug(
            "[UI-FRAME] 从启动到UI可见耗时 %.0fms（目标：< %dms）",
            ui_visible_time,
            target_ms,
        )
        # 启动指标：UI可见时延
        try:
            logger_metric = logging.getLogger("metric.startup")
            logger_metric.info("ui_visible_ms=%d", int(ui_visible_time))
        except Exception:
            pass

        # ==================== 阶段2.5：主线程初始化 EventEngine/MainEngine ====================
        logger.debug("[VNPY-CORE] VnPy核心初始化中...")

        vnpy_start = time.time()
        vnpy_success = True
        vnpy_error_detail = ""

        try:
            from vnpy.event import EventEngine
            from vnpy.trader.engine import MainEngine
            from backend.core.base import set_event_engine, set_main_engine

            # 创建 EventEngine（会自动启动工作线程）
            event_engine = EventEngine(interval=1)
            logger.debug("[VNPY-CORE] EventEngine 创建成功（工作线程已启动）")

            # 创建 MainEngine
            main_engine = MainEngine(event_engine)
            logger.debug("[VNPY-CORE] MainEngine 创建成功")

            # 注册到全局
            set_event_engine(event_engine)
            set_main_engine(main_engine)
            logger.debug("[VNPY-CORE] EventEngine 和 MainEngine 已注册到全局")

            # 🔧 立即注入占位方法（供 vnpy_chartwizard 使用）
            try:
                logger.debug("[VNPY-CORE] 注入 MainEngine 数据接口占位方法...")

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

                logger.debug(
                    "[VNPY-CORE] MainEngine 占位方法已注入（后续将由 UnifiedDataManager 更新）"
                )

            except Exception as e:
                logger.exception("[VNPY-CORE] 注入占位方法失败: %s", e)

            # VnPy Apps延迟加载：移至后台线程
            logger.debug("[VNPY-CORE] VnPy Apps将在后台线程加载")

            vnpy_time = (time.time() - vnpy_start) * 1000
            stage_logger.info("VnPy核心初始化完成（耗时: %.0fms）", vnpy_time)

            # ==================== 阶段2.55：初始化日志管理系统 ====================
            # 🔧 关键修复：在EventEngine创建后立即初始化LogManager
            # 这样后续的所有日志都会被记录到数据库
            logger.debug("[LOG-MANAGER] 日志持久化系统初始化中...")

            try:
                from backend.services.system_manager_service import get_log_manager

                # 获取LogManager并强制初始化（注入EventEngine）
                _ = get_log_manager(event_engine=event_engine, force_reinit=True)
                stage_logger.info("日志持久化已启用")
                print_stage("LOG-MANAGER", "日志持久化已启用", success=True)

            except Exception as e:
                logger.exception("[LOG-MANAGER] 日志管理系统初始化失败: %s", e)
                print_stage("LOG-MANAGER", "日志持久化启用失败", success=False, error_detail=str(e))
                # 不中断启动流程

        except Exception as e:
            logger.exception("[VNPY-CORE] VnPy 核心初始化失败: %s", e)
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

        # ==================== 阶段2.6-2.7：已移至BackendInitializerWorker ====================
        # 服务器池和监控进程现在在BackendInitializerWorker中并行启动
        # 优化效果：主线程减少阻塞3-5秒

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
                            self.logger.exception("可选服务后台加载异常: %s", e)
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
                logger.exception("[OPTIONAL-SERVICES] 启动后台加载器失败: %s", e)

        # ==================== 连接后端初始化回调 ====================
        def on_startup_completed():
            """阶段4：UI功能激活（后端就绪后）."""
            # 🔍 DEBUG: 确认回调被调用
            print("[DEBUG-IPO] on_startup_completed() 被调用")
            logger.info("[DEBUG-IPO] on_startup_completed() 被调用")
            logger.info("[UI-ACTIVATE] 开始激活UI功能...")

            try:
                activation_start = time.time()

                # ==================== 阶段切换：切换到sensing阶段 ====================
                from backend.infrastructure.system_vnpy.unified_log_system import get_logging_hub

                ctx = get_logging_hub()
                ctx.set_stage("sensing")
                logger.info("📍 启动完成，切换到数据感知阶段")

                # 🔧 修复：在后端真正完成后，先标记backend_ready
                try:
                    if hasattr(main_window, "boot_orchestrator") and main_window.boot_orchestrator:
                        main_window.boot_orchestrator.mark_ready("backend_ready")
                        logger.info("[UI-ACTIVATE] ✅ backend_ready事件已触发")
                except Exception as e:
                    logger.exception("[UI-ACTIVATE] ❌ 触发backend_ready事件失败: %s", e)

                # 步骤1: 初始化主窗口的功能界面
                logger.info("[UI-ACTIVATE] 调用 initialize_function_interfaces_after_backend()")
                main_window.initialize_function_interfaces_after_backend()
                logger.info("[UI-ACTIVATE] ✅ 功能界面初始化完成")

                # 步骤2: 隐藏启动画面
                logger.info("[UI-ACTIVATE] 隐藏启动画面")
                coordinator.hide_splash(main_window)
                logger.info("[UI-ACTIVATE] ✅ 启动画面已隐藏")

                # 后台验证现在由coordinator的initialization_completed信号触发
                # 不再需要延迟500ms，立即触发
                logger.info("[UI-ACTIVATE] 后台验证将由coordinator信号触发")

                # 步骤3: 启动后台服务加载器（快速启动优化）
                logger.info("[UI-ACTIVATE] 启动可选服务后台加载...")
                _start_optional_services_loader(coordinator.backend_result, main_window)

                activation_time = (time.time() - activation_start) * 1000
                total_time = (time.time() - startup_start) * 1000

                print_stage("UI-ACTIVATE", "UI功能激活完成", success=True)

                logger.info("\n" + "=" * 70)
                logger.info("✅ 系统启动完成！")
                logger.info("   - 总启动时间: %.0fms", total_time)
                logger.info("=" * 70)

                logger.info("[UI-ACTIVATE] ✅ UI功能激活完成，耗时 %.0fms", activation_time)
                logger.info("=" * 60)
                logger.info("✅ 系统启动完成，总耗时 %.0fms（目标：< 5000ms）", total_time)
                logger.info("=" * 60)
                # 启动指标：后端就绪时延
                try:
                    logger_metric = logging.getLogger("metric.startup")
                    logger_metric.info("backend_ready_ms=%d", int(total_time))
                    logger_metric.info("total_startup_ms=%d", int(total_time))
                except Exception:
                    pass

                # ❌ 不在这里结束AI日志流程，等待ValidationWorker完成后再结束
                # AI日志流程将在MainWindow._on_validation_finished()中结束

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
                                logger_metric = logging.getLogger("metric.server_pool")
                                logger_metric.info("warmup_ms=%d", warm_ms)
                            except Exception:
                                pass
                        except Exception as warm_e:
                            logger.exception("[SERVER-POOL] 预热失败: %s", warm_e)

                    import threading as _th

                    _th.Thread(
                        target=_warmup_server_pool, name="ServerPoolWarmup", daemon=True
                    ).start()
                except Exception as e:
                    logger.error("[SERVER-POOL] 启动后台预热线程失败: %s", e)

            except Exception as e:
                logger.exception("[UI-ACTIVATE] ❌ UI激活过程发生异常: %s", e)
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

        # 🆕 连接后端初始化完成信号到validation启动
        # 当BackendInitializerWorker完成后，自动触发CacheValidationWorker
        coordinator.initialization_completed.connect(
            lambda success, result: main_window._start_background_validation() if success else None
        )

        # ==================== 阶段3：启动后端初始化（异步）====================
        logger.info("[BACKEND-INIT] 启动后端初始化工作线程")
        coordinator.start()
        print_stage("BACKEND-INIT", "后端初始化已开始（后台线程运行）", success=True)
        logger.info("[BACKEND-INIT] ✅ 后台初始化线程已启动")

        # ==================== 启动Qt事件循环 ====================
        logger.info("[EVENT-LOOP] 启动Qt主事件循环")
        logger.info("=" * 70)

        # ❌ 不再在这里结束AI日志流程，让它持续运行直到后台初始化完成
        # AI日志流程将在on_startup_completed()中结束，确保所有后台初始化日志都被记录

        return app.exec()

    except Exception as e:
        # 使用print输出，因为logger可能已损坏
        print("\n" + "=" * 70)
        print(f"❌ 启动失败: {e}")
        print("=" * 70)
        import traceback

        traceback.print_exc()

        if "logger" in locals():
            logger.exception("💥 启动流程发生严重异常: %s", e)

        return 1


if __name__ == "__main__":
    sys.exit(main())
