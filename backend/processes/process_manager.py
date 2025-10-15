# -*- coding: utf-8 -*-
"""
进程管理器.

提供子进程的生命周期管理、健康监控、自动重启等功能。
"""

import multiprocessing
import os
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional

import msgpack
import zmq


class ProcessState(str, Enum):
    """进程状态."""

    STOPPED = "stopped"  # 已停止
    STARTING = "starting"  # 启动中
    RUNNING = "running"  # 运行中
    STOPPING = "stopping"  # 停止中
    ERROR = "error"  # 错误


class ManagedProcess:
    """托管进程."""

    def __init__(
        self,
        name: str,
        target_module: str,
        health_port: int,
        max_restarts: int = 5,
        restart_delay_base: float = 1.0,
    ):
        """初始化托管进程.

        Args:
            name: 进程名称
            target_module: 目标模块（如"backend.processes.log_alert_process"）
            health_port: 健康检查端口
            max_restarts: 最大重启次数
            restart_delay_base: 重启延迟基数（秒）
        """
        self.name = name
        self.target_module = target_module
        self.health_port = health_port
        self.max_restarts = max_restarts
        self.restart_delay_base = restart_delay_base

        # 进程对象
        self.process: Optional[multiprocessing.Process] = None

        # 状态
        self.state = ProcessState.STOPPED
        self.start_time: Optional[datetime] = None
        self.restart_count = 0

        # ZeroMQ健康检查
        self.context: Optional[zmq.Context] = None
        self.health_socket: Optional[zmq.Socket] = None

    def start(self) -> bool:
        """启动进程.

        Returns:
            是否启动成功
        """
        if self.state == ProcessState.RUNNING:
            print(f"[ProcessManager] 进程 {self.name} 已在运行")
            return True

        try:
            self.state = ProcessState.STARTING
            print(f"[ProcessManager] 启动进程: {self.name}")

            # 创建进程
            self.process = multiprocessing.Process(
                target=self._run_process,
                name=self.name,
                daemon=True,
            )
            self.process.start()

            # 等待进程启动（最多5秒）
            max_wait = 5.0
            wait_interval = 0.1
            elapsed = 0.0

            while elapsed < max_wait:
                if self.process.is_alive():
                    # 检查健康状态
                    if self._check_health_quick():
                        self.state = ProcessState.RUNNING
                        self.start_time = datetime.now()
                        print(f"[ProcessManager] 进程 {self.name} 启动成功，PID={self.process.pid}")
                        return True

                time.sleep(wait_interval)
                elapsed += wait_interval

            # 启动超时
            print(f"[ProcessManager] 进程 {self.name} 启动超时")
            self.state = ProcessState.ERROR
            return False

        except Exception as e:
            print(f"[ProcessManager] 启动进程 {self.name} 失败: {e}")
            self.state = ProcessState.ERROR
            return False

    def stop(self, timeout: float = 5.0) -> bool:
        """停止进程.

        Args:
            timeout: 超时时间（秒）

        Returns:
            是否停止成功
        """
        if self.state == ProcessState.STOPPED:
            print(f"[ProcessManager] 进程 {self.name} 已停止")
            return True

        try:
            self.state = ProcessState.STOPPING
            print(f"[ProcessManager] 停止进程: {self.name}")

            if self.process and self.process.is_alive():
                # 优雅终止
                self.process.terminate()

                # 等待进程退出
                self.process.join(timeout=timeout)

                # 如果仍未退出，强制杀死
                if self.process.is_alive():
                    print(f"[ProcessManager] 进程 {self.name} 未响应，强制杀死")
                    self.process.kill()
                    self.process.join(timeout=1.0)

            self.state = ProcessState.STOPPED
            self.process = None
            print(f"[ProcessManager] 进程 {self.name} 已停止")
            return True

        except Exception as e:
            print(f"[ProcessManager] 停止进程 {self.name} 失败: {e}")
            self.state = ProcessState.ERROR
            return False

    def restart(self) -> bool:
        """重启进程.

        Returns:
            是否重启成功
        """
        print(f"[ProcessManager] 重启进程: {self.name}")

        # 检查重启次数
        if self.restart_count >= self.max_restarts:
            print(f"[ProcessManager] 进程 {self.name} 达到最大重启次数 ({self.max_restarts})，放弃重启")
            self.state = ProcessState.ERROR
            return False

        # 停止进程
        self.stop()

        # 计算退避延迟（指数退避）
        delay = self.restart_delay_base * (2 ** self.restart_count)
        print(f"[ProcessManager] 等待 {delay:.1f}秒 后重启...")
        time.sleep(delay)

        # 启动进程
        self.restart_count += 1
        success = self.start()

        if success:
            print(f"[ProcessManager] 进程 {self.name} 重启成功（第{self.restart_count}次重启）")
        else:
            print(f"[ProcessManager] 进程 {self.name} 重启失败")

        return success

    def check_health(self) -> Dict[str, Any]:
        """检查进程健康状态.

        Returns:
            健康状态数据
        """
        if self.state != ProcessState.RUNNING:
            return {
                "healthy": False,
                "state": self.state.value,
                "reason": "进程未运行",
            }

        if not self.process or not self.process.is_alive():
            return {
                "healthy": False,
                "state": ProcessState.ERROR.value,
                "reason": "进程已退出",
            }

        # ZeroMQ健康检查
        health_data = self._check_health_detailed()

        if health_data:
            return {
                "healthy": True,
                "state": self.state.value,
                "pid": self.process.pid,
                **health_data,
            }
        else:
            return {
                "healthy": False,
                "state": ProcessState.ERROR.value,
                "reason": "健康检查失败",
            }

    def _run_process(self) -> None:
        """运行进程（进程内部）."""
        # 导入目标模块并运行
        import importlib

        module = importlib.import_module(self.target_module)
        module.main()

    def _check_health_quick(self) -> bool:
        """快速健康检查（用于启动验证）.

        Returns:
            是否健康
        """
        try:
            # 每次检查都创建新的socket，避免状态问题
            context = zmq.Context()
            health_socket = context.socket(zmq.REQ)
            health_socket.setsockopt(zmq.RCVTIMEO, 500)  # 500ms超时
            health_socket.setsockopt(zmq.SNDTIMEO, 500)
            health_socket.setsockopt(zmq.LINGER, 0)
            health_socket.connect(f"tcp://127.0.0.1:{self.health_port}")

            # 发送健康检查请求
            health_socket.send(b"ping")

            # 接收响应
            response = health_socket.recv()

            # 解析响应
            health_data = msgpack.unpackb(response, raw=False)
            
            # 清理socket
            health_socket.close()
            context.term()

            return health_data.get("status") == "healthy"

        except zmq.Again:
            # 超时
            return False
        except Exception as e:
            # print(f"[ProcessManager] 快速健康检查失败: {e}")
            return False

    def _check_health_detailed(self) -> Optional[Dict[str, Any]]:
        """详细健康检查.

        Returns:
            健康状态数据，失败返回None
        """
        try:
            if self.context is None:
                self.context = zmq.Context()

            # 重新创建socket，避免状态错误
            if self.health_socket:
                self.health_socket.close()

            self.health_socket = self.context.socket(zmq.REQ)
            self.health_socket.setsockopt(zmq.RCVTIMEO, 2000)  # 2秒超时
            self.health_socket.setsockopt(zmq.SNDTIMEO, 2000)
            self.health_socket.setsockopt(zmq.LINGER, 0)
            self.health_socket.connect(f"tcp://127.0.0.1:{self.health_port}")

            # 发送健康检查请求
            self.health_socket.send(b"ping")

            # 接收响应
            response = self.health_socket.recv()

            # 解析响应
            health_data = msgpack.unpackb(response, raw=False)

            return health_data

        except zmq.Again:
            # 超时
            return None
        except Exception as e:
            print(f"[ProcessManager] 详细健康检查失败: {e}")
            return None

    def cleanup(self) -> None:
        """清理资源."""
        if self.health_socket:
            self.health_socket.close()
            self.health_socket = None

        if self.context:
            self.context.term()
            self.context = None


class ProcessManager:
    """进程管理器.

    管理所有子进程的生命周期。
    """

    def __init__(self):
        """初始化进程管理器."""
        self.processes: Dict[str, ManagedProcess] = {}
        self.monitoring_enabled = False
        self.monitor_thread: Optional[Any] = None

    def register_process(
        self,
        name: str,
        target_module: str,
        health_port: int,
        max_restarts: int = 5,
    ) -> None:
        """注册进程.

        Args:
            name: 进程名称
            target_module: 目标模块
            health_port: 健康检查端口
            max_restarts: 最大重启次数
        """
        process = ManagedProcess(
            name=name,
            target_module=target_module,
            health_port=health_port,
            max_restarts=max_restarts,
        )

        self.processes[name] = process
        print(f"[ProcessManager] 已注册进程: {name}")

    def start_process(self, name: str) -> bool:
        """启动进程.

        Args:
            name: 进程名称

        Returns:
            是否启动成功
        """
        if name not in self.processes:
            print(f"[ProcessManager] 进程 {name} 未注册")
            return False

        return self.processes[name].start()

    def stop_process(self, name: str, timeout: float = 5.0) -> bool:
        """停止进程.

        Args:
            name: 进程名称
            timeout: 超时时间（秒）

        Returns:
            是否停止成功
        """
        if name not in self.processes:
            print(f"[ProcessManager] 进程 {name} 未注册")
            return False

        return self.processes[name].stop(timeout)

    def restart_process(self, name: str) -> bool:
        """重启进程.

        Args:
            name: 进程名称

        Returns:
            是否重启成功
        """
        if name not in self.processes:
            print(f"[ProcessManager] 进程 {name} 未注册")
            return False

        return self.processes[name].restart()

    def check_health(self, name: str) -> Dict[str, Any]:
        """检查进程健康状态.

        Args:
            name: 进程名称

        Returns:
            健康状态数据
        """
        if name not in self.processes:
            return {
                "healthy": False,
                "reason": "进程未注册",
            }

        return self.processes[name].check_health()

    def start_all(self) -> bool:
        """启动所有进程.

        Returns:
            是否全部启动成功
        """
        success = True

        for name in self.processes:
            if not self.start_process(name):
                success = False

        return success

    def stop_all(self) -> None:
        """停止所有进程."""
        for name in self.processes:
            self.stop_process(name)

    def monitor_all(self) -> None:
        """监控所有进程（自动重启崩溃的进程）."""
        import threading

        if self.monitoring_enabled:
            print(f"[ProcessManager] 监控已启动")
            return

        def monitor_loop():
            while self.monitoring_enabled:
                for name, process in self.processes.items():
                    # 检查进程状态
                    if process.state == ProcessState.RUNNING:
                        health = process.check_health()

                        if not health.get("healthy"):
                            print(f"[ProcessManager] 进程 {name} 不健康: {health.get('reason')}")
                            # 自动重启
                            process.restart()

                time.sleep(5)  # 每5秒检查一次

        self.monitoring_enabled = True
        self.monitor_thread = threading.Thread(
            target=monitor_loop,
            daemon=True,
            name="ProcessMonitor",
        )
        self.monitor_thread.start()

        print(f"[ProcessManager] 进程监控已启动")

    def stop_monitoring(self) -> None:
        """停止监控."""
        self.monitoring_enabled = False

        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)

        print(f"[ProcessManager] 进程监控已停止")

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有进程状态.

        Returns:
            所有进程的状态
        """
        status = {}

        for name, process in self.processes.items():
            health = process.check_health()
            status[name] = {
                "state": process.state.value,
                "restart_count": process.restart_count,
                **health,
            }

        return status

    def cleanup(self) -> None:
        """清理资源."""
        self.stop_monitoring()
        self.stop_all()

        for process in self.processes.values():
            process.cleanup()


# 全局实例（单例模式）
_process_manager: Optional[ProcessManager] = None


def get_process_manager() -> ProcessManager:
    """获取进程管理器（单例）.

    Returns:
        进程管理器实例
    """
    global _process_manager

    if _process_manager is None:
        _process_manager = ProcessManager()

    return _process_manager
