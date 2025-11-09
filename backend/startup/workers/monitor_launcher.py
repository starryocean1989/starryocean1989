# -*- coding: utf-8 -*-
"""
监控进程启动Worker - 启动监控进程

负责启动监控进程并等待其就绪。
"""

import asyncio
import atexit
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from backend.startup.workers.base import StartupWorker, WorkerResult
from backend.startup.context import StartupContext
from backend.infrastructure.system_vnpy.logging_system import (
    LOGGING_QUEUE_TOKEN_ENV,
    alert_log,
    get_alert_logger,
    get_configured_logger,
)


def get_root() -> Path:
    """获取项目根目录路径（统一方法，与工作目录解绑）
    
    通过当前文件的路径向上查找项目根目录。
    monitor_launcher.py 位于 backend/startup/workers/
    需要向上4级到达项目根目录。
    
    Returns:
        Path: 项目根目录的Path对象
    """
    current_file = Path(__file__).resolve()
    root_path = current_file.parent.parent.parent.parent
    return root_path

logger = get_configured_logger(
    "backend.startup.workers.monitor_launcher",
    scenario="monitor_launch",
)
alert_logger = get_alert_logger(
    "backend.startup.workers.monitor_launcher.alert",
    scenario="monitor_launch",
)

STARTUP_SCENARIO = "application_startup"
MONITOR_NODE_ID = "backend_init.monitor"

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
        self.logger = get_configured_logger(
            f"backend.startup.workers.{self.name}",
            scenario="monitor_launch",
        )
        self._alert_logger = alert_logger
        self.monitor_process_handle: Optional[subprocess.Popen] = None
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
            stage_data: dict[str, Any] = {}
            # 启动监控进程
            monitor_info = await self._launch_monitor_process(context)

            # 设置监控进程到上下文
            if monitor_info and self.monitor_process_handle:
                context.set_monitor_process(self.monitor_process_handle)

            elapsed_ms = (time.time() - start_time) * 1000
            stage_data.update(
                {
                    "monitor_info": monitor_info,
                    "watchdog_started": self.watchdog_running,
                    "log_collector_attached": bool(getattr(context, "log_queue_token", None)),
                    "elapsed_ms": elapsed_ms,
                }
            )

            return WorkerResult(
                success=True,
                message="监控进程启动完成",
                elapsed_ms=elapsed_ms,
                data=stage_data,
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000

            self._alert_logger.error(
                f"❌ [MonitorLauncherWorker] 监控进程启动Worker异常: {e}",
                exc_info=True,
            )
            self._mark_failure(
                context,
                MONITOR_NODE_ID,
                f"监控进程启动异常: {e}",
                extra={"elapsed_ms": elapsed_ms},
            )

            return WorkerResult(
                success=False,
                message=f"监控进程启动失败: {str(e)}",
                elapsed_ms=elapsed_ms,
                error=e,
            )

    async def _launch_monitor_process(self, context: StartupContext) -> dict:
        """启动监控进程并等待其多级就绪."""

        start_time = time.time()
        monitor_script = (
            context.project_root
            / "backend"
            / "infrastructure"
            / "system_vnpy"
            / "monitor_system.py"
        )
        if not monitor_script.exists():
            raise RuntimeError(f"监控进程脚本不存在: {monitor_script}")

        signal_file = context.project_root / "logs" / "monitor_ready.signal"
        if signal_file.exists():
            try:
                signal_file.unlink()
                logger.debug("[MONITOR-PROCESS] 已清理旧的 monitor_ready.signal 文件")
            except Exception as cleanup_error:
                logger.warning(
                    "[MONITOR-PROCESS] 无法删除旧的 monitor_ready.signal: %s",
                    cleanup_error,
                )

        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NO_WINDOW
            try:
                import ctypes

                if ctypes.windll.shell32.IsUserAnAdmin():  # type: ignore[attr-defined]
                    logger.info("[MONITOR-PROCESS] 以管理员权限启动")
            except Exception:
                pass

        import os

        env = os.environ.copy()
        if getattr(context, "log_queue_token", None):
            env[LOGGING_QUEUE_TOKEN_ENV] = context.log_queue_token  # type: ignore[arg-type]
            logger.debug("[MONITOR-PROCESS] 已注入日志队列token")
        else:
            alert_log(
                "⚠️ 未检测到日志队列令牌，监控进程日志将回退至本地输出",
                scenario="monitor_launch",
                stacklevel=3,
            )

        import tempfile

        stderr_file = tempfile.NamedTemporaryFile(
            mode="w+",
            delete=False,
            suffix=".log",
            prefix="monitor_process_stderr_",
        )
        stderr_file.close()
        stderr_path = stderr_file.name

        self.monitor_process_handle = subprocess.Popen(
            [sys.executable, str(monitor_script)],
            stdout=subprocess.DEVNULL,
            stderr=open(stderr_path, "w"),
            cwd=str(context.project_root),
            creationflags=creation_flags,
            env=env,
        )
        self.monitor_process_stderr_path = stderr_path
        pid = self.monitor_process_handle.pid
        logger.info("[MONITOR-PROCESS] 进程已启动 (PID: %s)", pid)
        self._mark_ready(
            context,
            MONITOR_NODE_ID,
            level="level0",
            message=f"监控进程已启动 (PID: {pid})",
            extra={"pid": pid},
        )

        atexit.register(self.cleanup_monitor)
        self._start_watchdog(context)
        logger.info("[MONITOR-PROCESS] 看门狗线程已启动 (2s 轮询)")

        level1_ports = await self._wait_monitor_ready(max_wait=15.0, wait_for_level=1)
        port_names: list[str] = []
        if isinstance(level1_ports, dict) and level1_ports:
            port_names = list(level1_ports.keys())
            logger.info(
                "[MONITOR-PROCESS] Level 1 就绪 (IPC: %s)", " / ".join(port_names)
            )
        else:
            logger.info("[MONITOR-PROCESS] Level 1 就绪 (IPC 管道准备完成)")
        self._mark_ready(
            context,
            MONITOR_NODE_ID,
            level="level1",
            message="监控进程 IPC 管道已就绪",
            extra={"ports": port_names},
        )

        await self._wait_monitor_ready(max_wait=90.0, wait_for_level=2)
        logger.info("[MONITOR-PROCESS] Level 2 就绪 (监控能力完整)")
        elapsed = time.time() - start_time
        self._mark_ready(
            context,
            MONITOR_NODE_ID,
            level="level2",
            message="监控能力已激活",
            extra={"elapsed": elapsed},
        )

        return {
            "pid": pid,
            "ipc_ports": port_names,
            "level1_ports": level1_ports,
            "elapsed": elapsed,
            "stderr": stderr_path,
            "signal_file": str(signal_file),
        }

    async def _wait_monitor_ready(self, max_wait: float = 15.0, wait_for_level: int = 1) -> dict:
        """等待监控进程就绪（多维度验证架构）

        验证策略（按优先级）：
        1. PID验证（基础验证）
        2. 时间戳验证（Windows PID不一致时的主要验证）
        3. IPC连接验证（最可靠，可选）

        Args:
            max_wait: 最大等待时间（秒）
            wait_for_level: 等待的就绪级别（1=管道就绪, 2=功能完整）

        Returns:
            dict: 端口信息（仅Level 1时返回）
        """
        # 使用绝对路径（与工作目录解绑）
        signal_file = get_root() / "logs" / "monitor_ready.signal"
        wait_start = time.time()
        
        # 获取当前监控进程的PID
        current_monitor_pid = self.monitor_process_handle.pid if self.monitor_process_handle else None
        
        # 获取进程启动时间（用于时间戳验证）
        process_start_time = time.time()
        if self.monitor_process_handle:
            try:
                import psutil
                proc = psutil.Process(self.monitor_process_handle.pid)
                process_start_time = proc.create_time()
                self.logger.debug(
                    f"[MONITOR-PROCESS] 进程启动时间: {process_start_time} (PID={current_monitor_pid})"
                )
            except ImportError:
                self.logger.debug(
                    "[MONITOR-PROCESS] psutil不可用，使用当前时间作为进程启动时间"
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                self.logger.debug(
                    f"[MONITOR-PROCESS] 无法获取进程创建时间: {e}，使用当前时间"
                )
        
        if current_monitor_pid:
            self.logger.debug(
                f"[MONITOR-PROCESS] 等待监控进程就绪: 期望PID={current_monitor_pid}, 等待级别={wait_for_level}, 进程启动时间={process_start_time}"
            )

        # 等待信号文件出现，并验证PID匹配和时间戳
        import json
        current_level = 0
        
        while (time.time() - wait_start) < max_wait:
            if signal_file.exists():
                try:
                    with open(signal_file, "r", encoding="utf-8") as f:
                        signal_data = json.load(f)
                    
                    signal_pid = signal_data.get("pid")
                    signal_timestamp = signal_data.get("timestamp", 0)
                    
                    # 多维度验证
                    pid_valid = (not current_monitor_pid) or (signal_pid == current_monitor_pid)
                    timestamp_valid = signal_timestamp >= (process_start_time - 1.0)  # 允许1秒误差
                    
                    self.logger.debug(
                        f"[MONITOR-PROCESS] 验证信号文件: PID={signal_pid}, 时间戳={signal_timestamp}, "
                        f"PID验证={'通过' if pid_valid else '失败'}, 时间戳验证={'通过' if timestamp_valid else '失败'}"
                    )
                    
                    # 验证决策
                    if pid_valid:
                        # PID匹配，直接通过
                        self.logger.debug(
                            f"[MONITOR-PROCESS] PID验证通过: {signal_pid}"
                        )
                    elif timestamp_valid:
                        # PID不匹配但时间戳有效（Windows正常情况）
                        self.logger.info(
                            f"[MONITOR-PROCESS] PID不一致但时间戳有效（Windows正常情况）: "
                            f"期望PID={current_monitor_pid}, 实际PID={signal_pid}, "
                            f"时间戳={signal_timestamp}, 进程启动时间={process_start_time}"
                        )
                    else:
                        # 所有验证都失败，删除旧文件
                        self.logger.warning(
                            f"[MONITOR-PROCESS] 信号文件验证失败（PID和时间戳都不匹配）: "
                            f"期望PID={current_monitor_pid}, 实际PID={signal_pid}, "
                            f"时间戳={signal_timestamp}, 进程启动时间={process_start_time}，删除旧文件并继续等待"
                        )
                        try:
                            signal_file.unlink()
                            self.logger.debug(
                                f"[MONITOR-PROCESS] 已删除旧信号文件（PID={signal_pid}）"
                            )
                        except Exception as e:
                            self.logger.warning(
                                f"[MONITOR-PROCESS] 删除旧信号文件失败: {e}"
                            )
                        await asyncio.sleep(0.5)
                        continue
                    
                    # 验证通过（PID匹配或时间戳有效），检查级别
                    current_level = signal_data.get("level", 0)
                    ports_info = signal_data.get("ports", {})
                    
                    self.logger.debug(
                        f"[MONITOR-PROCESS] 信号文件有效: PID={signal_pid}, level={current_level}, 目标级别={wait_for_level}, 时间戳={signal_timestamp}"
                    )
                    
                    # 如果已达到目标级别，返回
                    if current_level >= wait_for_level:
                        self.logger.info(
                            f"[MONITOR-PROCESS] ✅ 监控进程Level {wait_for_level}已就绪（PID={signal_pid}, 时间戳={signal_timestamp}）"
                        )
                        return ports_info
                    
                    # 否则继续等待
                    await asyncio.sleep(0.5)
                except json.JSONDecodeError as e:
                    self.logger.warning(
                        f"[MONITOR-PROCESS] 解析信号文件失败: {e}，删除并继续等待"
                    )
                    try:
                        signal_file.unlink()
                    except Exception as cleanup_error:
                        self.logger.debug(
                            f"[MONITOR-PROCESS] 删除损坏信号文件失败: {cleanup_error}"
                        )
                    await asyncio.sleep(0.5)
                    continue
                except Exception as e:
                    self.logger.warning(
                        f"[MONITOR-PROCESS] 读取信号文件失败: {e}"
                    )
                    await asyncio.sleep(0.5)
                    continue
            else:
                # 文件不存在，继续等待
                await asyncio.sleep(0.5)
        
        # 超时仍未找到匹配的信号文件
        # 🔧 读取stderr输出以诊断问题
        stderr_content = ""
        if hasattr(self, 'monitor_process_stderr_path'):
            try:
                with open(self.monitor_process_stderr_path, 'r', encoding='utf-8', errors='ignore') as f:
                    stderr_content = f.read()
                if stderr_content:
                    self._alert_logger.error(
                        f"[MONITOR-PROCESS] 监控进程 stderr 输出:\n{stderr_content}"
                    )
            except Exception as read_err:
                self._alert_logger.warning(f"[MONITOR-PROCESS] 无法读取stderr: {read_err}")
        
        if current_monitor_pid:
            error_msg = f"监控进程就绪超时（等待 {max_wait} 秒，期望PID={current_monitor_pid}，当前级别={current_level}）"
            self._alert_logger.error(f"[MONITOR-PROCESS] ❌ {error_msg}")
            raise RuntimeError(error_msg)
        else:
            error_msg = f"监控进程就绪超时（等待 {max_wait} 秒，当前级别={current_level}）"
            self._alert_logger.error(f"[MONITOR-PROCESS] ❌ {error_msg}")
            raise RuntimeError(error_msg)

    def _start_watchdog(self, context: StartupContext):
        """启动看门狗线程（监控监控进程健康状态）

        Args:
            context: 启动上下文
        """
        import threading

        def watchdog():
            """看门狗线程"""
            interval = 2.0
            while self.watchdog_running:
                if self.monitor_process_handle:
                    # 检查进程是否还在运行
                    if self.monitor_process_handle.poll() is not None:
                        # 进程已退出
                        self._alert_logger.error(
                            "❌ [MonitorLauncherWorker] 监控进程意外退出",
                            exc_info=True,
                        )
                        self.watchdog_running = False
                        break
                time.sleep(interval)  # 每2秒检查一次

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
                self.logger.warning("监控进程终止超时，强制结束...")
                try:
                    self.monitor_process_handle.kill()
                    self.monitor_process_handle.wait(timeout=2)
                    self.logger.info("监控进程已强制结束")
                except Exception as e:
                    self._alert_logger.error(
                        f"❌ [MonitorLauncherWorker] 强制结束监控进程失败: {e}",
                        exc_info=True,
                    )
            except Exception as e:
                self.logger.warning(f"⚠️ [MonitorLauncherWorker] 终止监控进程失败: {e}")
                try:
                    self.monitor_process_handle.kill()
                    self.monitor_process_handle.wait(timeout=2)
                except Exception:
                    pass
            finally:
                self.monitor_process_handle = None

        self.watchdog_running = False

        # 清理监控就绪信号文件
        self._cleanup_signal_file()

    def _cleanup_signal_file(self):
        """清理监控就绪信号文件"""
        try:
            signal_file = get_root() / "logs" / "monitor_ready.signal"
            if signal_file.exists():
                signal_file.unlink()
                self.logger.debug("[MONITOR-PROCESS] 已清理 monitor_ready.signal 文件")
        except Exception as e:
            self.logger.debug(f"[MONITOR-PROCESS] 清理信号文件失败（可接受）: {e}")


def cleanup_all_processes():
    """全局进程清理函数 - 可以从任何地方调用"""
    global _global_monitor_worker

    if _global_monitor_worker:
        try:
            _global_monitor_worker.cleanup_monitor()
        except Exception as e:
            alert_logger.error(
                f"❌ [MonitorLauncherWorker] 清理监控进程失败: {e}",
                exc_info=True,
            )

    # 也可以清理其他进程
    # 从StartupContext获取监控进程并清理（备用方案）
    try:
        # 尝试从StartupContext获取监控进程
        # 注意：这个方法可能无法访问到StartupOrchestrator实例
        # 所以主要依赖上面的_global_monitor_worker
        pass
    except Exception:
        pass

    # 清理监控就绪信号文件（无论监控进程是否正常退出）
    _cleanup_signal_file()


def _cleanup_signal_file():
    """清理监控就绪信号文件（独立函数，可在任何地方调用）"""
    try:
        signal_file = get_root() / "logs" / "monitor_ready.signal"
        if signal_file.exists():
            signal_file.unlink()
            logger.debug("[CLEANUP] 已清理 monitor_ready.signal 文件")
    except Exception as e:
        # 清理失败不影响程序退出，只记录调试日志
        logger.debug(f"[CLEANUP] 清理信号文件失败（可接受）: {e}")


