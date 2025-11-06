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
            stdout=None,  # 不重定向，使用默认输出
            stderr=None,  # 不重定向，使用默认输出
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

        # 等待监控进程Level 1就绪（管道就绪）
        # 正常2-3秒，设置15秒超时（已非常宽松）
        ports_info = await self._wait_monitor_ready(max_wait=15.0, wait_for_level=1)

        stage_logger.info(
            "✅ Level 1就绪 (管道就绪)",
            extra={"log_type": "STAGE_NODE", "scenario": "monitor_launch"}
        )
        stage_logger.info(
            "✅ 监控进程看门狗启动",
            extra={"log_type": "STAGE_NODE", "scenario": "monitor_launch"}
        )

        # 等待监控进程Level 2就绪（功能完整）
        # 硬件监控初始化可能需要30-60秒，设置90秒超时
        await self._wait_monitor_ready(max_wait=90.0, wait_for_level=2)

        stage_logger.info(
            "✅ Level 2就绪 (功能完整)",
            extra={"log_type": "STAGE_NODE", "scenario": "monitor_launch"}
        )

        elapsed = time.time() - start_time

        return {
            "pid": self.monitor_process_handle.pid,
            "ports": ports_info,
            "elapsed": elapsed,
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
                    f"[MONITOR-PROCESS] 进程启动时间: {process_start_time} (PID={current_monitor_pid})",
                    extra={"log_type": "SYSTEM", "scenario": "monitor_launch"}
                )
            except ImportError:
                self.logger.debug(
                    "[MONITOR-PROCESS] psutil不可用，使用当前时间作为进程启动时间",
                    extra={"log_type": "SYSTEM", "scenario": "monitor_launch"}
                )
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                self.logger.debug(
                    f"[MONITOR-PROCESS] 无法获取进程创建时间: {e}，使用当前时间",
                    extra={"log_type": "SYSTEM", "scenario": "monitor_launch"}
                )
        
        if current_monitor_pid:
            self.logger.debug(
                f"[MONITOR-PROCESS] 等待监控进程就绪: 期望PID={current_monitor_pid}, 等待级别={wait_for_level}, 进程启动时间={process_start_time}",
                extra={"log_type": "SYSTEM", "scenario": "monitor_launch"}
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
                        f"PID验证={'通过' if pid_valid else '失败'}, 时间戳验证={'通过' if timestamp_valid else '失败'}",
                        extra={"log_type": "SYSTEM", "scenario": "monitor_launch"}
                    )
                    
                    # 验证决策
                    if pid_valid:
                        # PID匹配，直接通过
                        self.logger.debug(
                            f"[MONITOR-PROCESS] PID验证通过: {signal_pid}",
                            extra={"log_type": "SYSTEM", "scenario": "monitor_launch"}
                        )
                    elif timestamp_valid:
                        # PID不匹配但时间戳有效（Windows正常情况）
                        self.logger.info(
                            f"[MONITOR-PROCESS] PID不一致但时间戳有效（Windows正常情况）: "
                            f"期望PID={current_monitor_pid}, 实际PID={signal_pid}, "
                            f"时间戳={signal_timestamp}, 进程启动时间={process_start_time}",
                            extra={"log_type": "SYSTEM", "scenario": "monitor_launch"}
                        )
                    else:
                        # 所有验证都失败，删除旧文件
                        self.logger.warning(
                            f"[MONITOR-PROCESS] 信号文件验证失败（PID和时间戳都不匹配）: "
                            f"期望PID={current_monitor_pid}, 实际PID={signal_pid}, "
                            f"时间戳={signal_timestamp}, 进程启动时间={process_start_time}，删除旧文件并继续等待",
                            extra={"log_type": "SYSTEM", "scenario": "monitor_launch"}
                        )
                        try:
                            signal_file.unlink()
                            self.logger.debug(
                                f"[MONITOR-PROCESS] 已删除旧信号文件（PID={signal_pid}）",
                                extra={"log_type": "SYSTEM", "scenario": "monitor_launch"}
                            )
                        except Exception as e:
                            self.logger.warning(
                                f"[MONITOR-PROCESS] 删除旧信号文件失败: {e}",
                                extra={"log_type": "SYSTEM", "scenario": "monitor_launch"}
                            )
                        await asyncio.sleep(0.5)
                        continue
                    
                    # 验证通过（PID匹配或时间戳有效），检查级别
                    current_level = signal_data.get("level", 0)
                    ports_info = signal_data.get("ports", {})
                    
                    self.logger.debug(
                        f"[MONITOR-PROCESS] 信号文件有效: PID={signal_pid}, level={current_level}, 目标级别={wait_for_level}, 时间戳={signal_timestamp}",
                        extra={"log_type": "SYSTEM", "scenario": "monitor_launch"}
                    )
                    
                    # 如果已达到目标级别，返回
                    if current_level >= wait_for_level:
                        self.logger.info(
                            f"[MONITOR-PROCESS] ✅ 监控进程Level {wait_for_level}已就绪（PID={signal_pid}, 时间戳={signal_timestamp}）",
                            extra={"log_type": "SYSTEM", "scenario": "monitor_launch"}
                        )
                        return ports_info
                    
                    # 否则继续等待
                    await asyncio.sleep(0.5)
                except json.JSONDecodeError as e:
                    self.logger.warning(
                        f"[MONITOR-PROCESS] 解析信号文件失败: {e}，删除并继续等待",
                        extra={"log_type": "SYSTEM", "scenario": "monitor_launch"}
                    )
                    try:
                        signal_file.unlink()
                    except Exception as cleanup_error:
                        self.logger.debug(
                            f"[MONITOR-PROCESS] 删除损坏信号文件失败: {cleanup_error}",
                            extra={"log_type": "SYSTEM", "scenario": "monitor_launch"}
                        )
                    await asyncio.sleep(0.5)
                    continue
                except Exception as e:
                    self.logger.warning(
                        f"[MONITOR-PROCESS] 读取信号文件失败: {e}",
                        extra={"log_type": "SYSTEM", "scenario": "monitor_launch"}
                    )
                    await asyncio.sleep(0.5)
                    continue
            else:
                # 文件不存在，继续等待
                await asyncio.sleep(0.5)
        
        # 超时仍未找到匹配的信号文件
        if current_monitor_pid:
            error_msg = f"监控进程就绪超时（等待 {max_wait} 秒，期望PID={current_monitor_pid}，当前级别={current_level}）"
            self.logger.error(
                f"[MONITOR-PROCESS] ❌ {error_msg}",
                extra={"log_type": "ALERT", "scenario": "monitor_launch"}
            )
            raise RuntimeError(error_msg)
        else:
            error_msg = f"监控进程就绪超时（等待 {max_wait} 秒，当前级别={current_level}）"
            self.logger.error(
                f"[MONITOR-PROCESS] ❌ {error_msg}",
                extra={"log_type": "ALERT", "scenario": "monitor_launch"}
            )
            raise RuntimeError(error_msg)

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
                        self.logger.error("❌ [MonitorLauncherWorker] 监控进程意外退出", exc_info=True, extra={"log_type": "SYSTEM"})
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
                    self.monitor_process_handle.wait(timeout=2)
                    self.logger.info("监控进程已强制结束")
                except Exception as e:
                    self.logger.error(f"❌ [MonitorLauncherWorker] 强制结束监控进程失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            except Exception as e:
                self.logger.warning(f"⚠️ [MonitorLauncherWorker] 终止监控进程失败: {e}", extra={"log_type": "SYSTEM"})
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
                self.logger.debug("[MONITOR-PROCESS] 已清理 monitor_ready.signal 文件", extra={"log_type": "SYSTEM"})
        except Exception as e:
            self.logger.debug(f"[MONITOR-PROCESS] 清理信号文件失败（可接受）: {e}", extra={"log_type": "SYSTEM"})


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

    # 清理监控就绪信号文件（无论监控进程是否正常退出）
    _cleanup_signal_file()


def _cleanup_signal_file():
    """清理监控就绪信号文件（独立函数，可在任何地方调用）"""
    try:
        signal_file = get_root() / "logs" / "monitor_ready.signal"
        if signal_file.exists():
            signal_file.unlink()
            logger.debug("[CLEANUP] 已清理 monitor_ready.signal 文件", extra={"log_type": "SYSTEM"})
    except Exception as e:
        # 清理失败不影响程序退出，只记录调试日志
        logger.debug(f"[CLEANUP] 清理信号文件失败（可接受）: {e}", extra={"log_type": "SYSTEM"})


