# -*- coding: utf-8 -*-
"""
监控进程启动Worker - 启动监控进程

负责启动监控进程并等待其就绪。
"""

import asyncio
import atexit
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from backend.startup.workers.base import StartupWorker, WorkerResult
from backend.startup.context import StartupContext

logger = logging.getLogger("backend.startup.workers.monitor_launcher")

# 全局变量用于进程清理
_global_monitor_worker: Optional['MonitorLauncherWorker'] = None


class MonitorLauncherWorker(StartupWorker):
    """监控进程启动Worker

    职责：
    - 启动监控进程
    - 等待监控进程就绪
    - 管理监控进程生命周期
    """

    def __init__(self):
        """初始化监控进程启动Worker"""
        super().__init__(
            name="monitor_launcher",
            description="监控进程启动Worker - 启动监控进程",
        )
        self.monitor_process_handle: Optional[subprocess.Popen] = None
        self.monitor_file_handles = []
        self.watchdog_running = False

        # 注册为全局实例
        global _global_monitor_worker
        _global_monitor_worker = self

    async def _run(self, context: StartupContext) -> WorkerResult:
        """执行监控进程启动逻辑

        Args:
            context: 启动上下文

        Returns:
            WorkerResult: Worker执行结果
        """
        start_time = time.time()

        try:
            stage_logger = logging.getLogger("startup.stage")

            stage_logger.info("", extra={"log_type": "STAGE_NODE"})
            stage_logger.info(
                "┌" + "─" * 66 + "┐", extra={"log_type": "STAGE_NODE"}
            )
            stage_logger.info(
                "│ 分支A: 监控进程                                                   │",
                extra={"log_type": "STAGE_NODE"},
            )
            stage_logger.info(
                "└" + "─" * 66 + "┘", extra={"log_type": "STAGE_NODE"}
            )
            stage_logger.info("", extra={"log_type": "STAGE_NODE"})

            stage_logger.info("📍 监控进程启动开始", extra={"log_type": "STAGE_NODE"})

            # 启动监控进程
            monitor_info = await self._launch_monitor_process(context)

            # 设置监控进程到上下文
            if monitor_info and self.monitor_process_handle:
                context.set_monitor_process(self.monitor_process_handle)

            elapsed_ms = (time.time() - start_time) * 1000

            stage_logger.info(
                f"✅ 监控进程完全就绪 ({elapsed_ms/1000:.1f}s)",
                extra={"log_type": "STAGE_NODE"},
            )

            return WorkerResult(
                success=True,
                message="监控进程启动完成",
                elapsed_ms=elapsed_ms,
                data={"monitor_info": monitor_info},
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000

            self.logger.error(f"❌ [MonitorLauncherWorker] 监控进程启动Worker异常: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

            return WorkerResult(
                success=False,
                message=f"监控进程启动失败: {str(e)}",
                elapsed_ms=elapsed_ms,
                error=e,
            )

    async def _launch_monitor_process(self, context: StartupContext) -> dict:
        """启动监控进程

        Args:
            context: 启动上下文

        Returns:
            dict: 监控进程信息 {"pid": int, "ports": dict, "elapsed": float}

        Raises:
            RuntimeError: 监控进程启动失败
        """
        start_time = time.time()
        stage_logger = logging.getLogger("startup.stage")

        monitor_script = (
            context.project_root
            / "backend"
            / "infrastructure"
            / "system_vnpy"
            / "monitor_system.py"
        )

        if not monitor_script.exists():
            raise RuntimeError(f"监控进程脚本不存在: {monitor_script}")

        # 清理可能遗留的就绪信号文件，避免误判
        signal_file = context.project_root / "logs" / "monitor_ready.signal"
        if signal_file.exists():
            try:
                signal_file.unlink()
                logger.debug("[MONITOR-PROCESS] 已清理旧的 monitor_ready.signal 文件")
            except Exception as cleanup_error:
                logger.warning(
                    "[MONITOR-PROCESS] 无法删除旧的 monitor_ready.signal: %s",
                    cleanup_error,
                    extra={"log_type": "SYSTEM"}
                )

        # 准备日志文件
        log_dir = context.project_root / "logs"
        log_dir.mkdir(exist_ok=True)

        monitor_stdout_file = open(log_dir / "monitor_stdout.log", "w", encoding="utf-8")
        monitor_stderr_file = open(log_dir / "monitor_stderr.log", "w", encoding="utf-8")
        self.monitor_file_handles = [monitor_stdout_file, monitor_stderr_file]

        # 启动监控进程（指定工作目录为项目根目录）
        # 在Windows上确保权限传递
        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NO_WINDOW
            # 检查当前是否有管理员权限
            try:
                import ctypes

                if ctypes.windll.shell32.IsUserAnAdmin():
                    # 如果有管理员权限，确保子进程也有
                    self.logger.info(
                        "[MONITOR-PROCESS] 检测到管理员权限，将传递给监控进程"
                    )
            except Exception:
                pass

        self.monitor_process_handle = subprocess.Popen(
            [sys.executable, str(monitor_script)],
            stdout=monitor_stdout_file,
            stderr=monitor_stderr_file,
            cwd=str(context.project_root),  # 确保监控进程在项目根目录工作
            creationflags=creation_flags,
        )

        # 获取PID并显示
        pid = self.monitor_process_handle.pid
        stage_logger.info(
            f"✅ monitor_system.py进程已启动 (PID: {pid})",
            extra={"log_type": "STAGE_NODE"},
        )

        # 注册清理函数
        atexit.register(self.cleanup_monitor)

        # 启动看门狗线程
        self._start_watchdog(context)

        # 显示native_ipc管道创建过程
        stage_logger.info("✅ 创建native_ipc管道", extra={"log_type": "STAGE_NODE"})
        stage_logger.info(
            "  ├─ monitor_alerts ✅", extra={"log_type": "STAGE_NODE"}
        )
        stage_logger.info(
            "  ├─ monitor_status ✅", extra={"log_type": "STAGE_NODE"}
        )
        stage_logger.info(
            "  └─ monitor_query ✅", extra={"log_type": "STAGE_NODE"}
        )

        # 显示监控组件初始化
        stage_logger.info("✅ 监控组件初始化", extra={"log_type": "STAGE_NODE"})
        stage_logger.info("  ├─ SystemMonitor ✅", extra={"log_type": "STAGE_NODE"})
        stage_logger.info("  ├─ ProcessMonitor ✅", extra={"log_type": "STAGE_NODE"})
        stage_logger.info(
            "  ├─ HardwareMonitor (后台异步) ⏳", extra={"log_type": "STAGE_NODE"}
        )
        stage_logger.info("  └─ BandwidthMonitor ✅", extra={"log_type": "STAGE_NODE"})

        # 等待监控进程就绪
        # 正常2-3秒，设置15秒超时（已非常宽松）
        ports_info = await self._wait_monitor_ready(max_wait=15.0)

        stage_logger.info(
            "✅ Level 1就绪 (管道就绪)", extra={"log_type": "STAGE_NODE"}
        )
        stage_logger.info(
            "✅ 监控进程看门狗启动", extra={"log_type": "STAGE_NODE"}
        )

        elapsed = time.time() - start_time

        return {
            "pid": self.monitor_process_handle.pid,
            "ports": ports_info,
            "elapsed": elapsed,
        }

    async def _wait_monitor_ready(self, max_wait: float = 15.0) -> dict:
        """等待监控进程就绪

        Args:
            max_wait: 最大等待时间（秒）

        Returns:
            dict: 端口信息
        """
        signal_file = Path("logs/monitor_ready.signal")
        wait_start = time.time()

        while not signal_file.exists() and (time.time() - wait_start) < max_wait:
            await asyncio.sleep(0.5)

        if not signal_file.exists():
            raise RuntimeError(f"监控进程就绪超时（等待 {max_wait} 秒）")

        # 读取信号文件
        try:
            import json

            with open(signal_file, "r", encoding="utf-8") as f:
                signal_data = json.load(f)
            ports_info = signal_data.get("ports", {})
        except Exception as e:
            self.logger.warning(f"读取监控进程信号文件失败: {e}", extra={"log_type": "SYSTEM"})
            ports_info = {}

        return ports_info

    def _start_watchdog(self, context: StartupContext):
        """启动看门狗线程（监控监控进程健康状态）

        Args:
            context: 启动上下文
        """
        import threading

        def watchdog():
            """看门狗线程"""
            while self.watchdog_running:
                if self.monitor_process_handle:
                    # 检查进程是否还在运行
                    if self.monitor_process_handle.poll() is not None:
                        # 进程已退出
                        self.logger.error("❌ [MonitorLauncherWorker] 监控进程意外退出", extra={"log_type": "SYSTEM"})
                        self.watchdog_running = False
                        break
                time.sleep(5)  # 每5秒检查一次

        self.watchdog_running = True
        watchdog_thread = threading.Thread(target=watchdog, daemon=True)
        watchdog_thread.start()

    def cleanup_monitor(self):
        """清理监控进程"""
        if self.monitor_process_handle:
            try:
                self.logger.info("正在终止监控进程...")
                self.monitor_process_handle.terminate()
                self.monitor_process_handle.wait(timeout=5)
                self.logger.info("监控进程已终止")
            except subprocess.TimeoutExpired:
                self.logger.warning("监控进程终止超时，强制结束...", extra={"log_type": "SYSTEM"})
                try:
                    self.monitor_process_handle.kill()
                    self.logger.info("监控进程已强制结束")
                except Exception as e:
                    self.logger.error(f"❌ [MonitorLauncherWorker] 强制结束监控进程失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            except Exception as e:
                self.logger.warning(f"⚠️ [MonitorLauncherWorker] 终止监控进程失败: {e}", extra={"log_type": "SYSTEM"})
                try:
                    self.monitor_process_handle.kill()
                except Exception:
                    pass
            finally:
                self.monitor_process_handle = None

        # 关闭文件句柄
        for fh in self.monitor_file_handles:
            try:
                fh.close()
            except Exception:
                pass

        self.watchdog_running = False


def cleanup_all_processes():
    """全局进程清理函数 - 可以从任何地方调用"""
    global _global_monitor_worker

    if _global_monitor_worker:
        try:
            _global_monitor_worker.cleanup_monitor()
        except Exception as e:
            logger.error(f"❌ [MonitorLauncherWorker] 清理监控进程失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    # 也可以清理其他进程
    # 从StartupContext获取监控进程并清理（备用方案）
    try:
        # 尝试从StartupContext获取监控进程
        # 注意：这个方法可能无法访问到StartupOrchestrator实例
        # 所以主要依赖上面的_global_monitor_worker
        pass
    except Exception:
        pass

