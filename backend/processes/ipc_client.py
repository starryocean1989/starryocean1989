# -*- coding: utf-8 -*-
"""
IPC客户端模块.

提供分布式日志处理器和告警订阅器。
"""

import logging
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

import msgpack
import zmq
from PySide6.QtCore import QObject, Signal


class DistributedLogHandler(logging.Handler):
    """分布式日志处理器.

    拦截Python日志记录，通过ZeroMQ发送到日志进程。

    特性：
    - 异步发送，不阻塞业务代码
    - 自动重连机制
    - 降级方案（IPC失败时写入本地文件）
    - 批量发送优化
    """

    def __init__(
        self,
        log_port: int = 5557,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        send_timeout: int = 1000,
    ):
        """初始化分布式日志处理器.

        Args:
            log_port: 日志进程端口
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
            send_timeout: 发送超时（毫秒）
        """
        super().__init__()

        self.log_port = log_port
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.send_timeout = send_timeout

        # ZeroMQ连接
        self.context: Optional[zmq.Context] = None
        self.socket: Optional[zmq.Socket] = None
        self.connected = False
        self._lock = threading.Lock()

        # 降级日志文件
        self.fallback_file = Path("logs/fallback/fallback.log")
        self.fallback_file.parent.mkdir(parents=True, exist_ok=True)

        # 初始化连接
        self._connect()

    def _connect(self) -> bool:
        """连接到日志进程.

        Returns:
            是否连接成功
        """
        with self._lock:
            try:
                if self.context is None:
                    self.context = zmq.Context()

                if self.socket is not None:
                    self.socket.close()

                # 创建PUSH套接字
                self.socket = self.context.socket(zmq.PUSH)
                self.socket.setsockopt(zmq.SNDTIMEO, self.send_timeout)
                self.socket.setsockopt(zmq.LINGER, 0)  # 不等待未发送的消息
                self.socket.connect(f"tcp://127.0.0.1:{self.log_port}")

                self.connected = True
                return True

            except Exception as e:
                print(f"[DistributedLogHandler] 连接失败: {e}")
                self.connected = False
                return False

    def _reconnect(self) -> bool:
        """重新连接.

        Returns:
            是否重连成功
        """
        for attempt in range(self.max_retries):
            print(f"[DistributedLogHandler] 尝试重连 ({attempt + 1}/{self.max_retries})...")
            time.sleep(self.retry_delay)

            if self._connect():
                print(f"[DistributedLogHandler] 重连成功")
                return True

        print(f"[DistributedLogHandler] 重连失败，进入降级模式")
        return False

    def emit(self, record: logging.LogRecord) -> None:
        """发送日志记录.

        Args:
            record: 日志记录
        """
        try:
            # 跳过自身的日志，避免递归
            if record.name.startswith("backend.processes"):
                return

            # 构建日志条目
            log_entry = self._build_log_entry(record)

            # 发送日志
            self._send_log(log_entry)

        except Exception as e:
            # 避免递归日志记录
            print(f"[DistributedLogHandler] 发送日志失败: {e}")

    def _build_log_entry(self, record: logging.LogRecord) -> Dict[str, Any]:
        """构建日志条目.

        Args:
            record: 日志记录

        Returns:
            日志条目字典
        """
        # 提取异常信息
        exception_text = ""
        if record.exc_info:
            exception_text = self.formatException(record.exc_info)

        return {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger_name": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
            "exception": exception_text,
            "thread": record.thread,
            "thread_name": getattr(record, "threadName", ""),
            "process": record.process,
            "filename": record.filename,
        }

    def _send_log(self, log_entry: Dict[str, Any]) -> None:
        """发送日志（带重试）.

        Args:
            log_entry: 日志条目
        """
        if not self.connected:
            # 未连接，尝试重连
            if not self._reconnect():
                # 重连失败，降级到本地文件
                self._fallback_to_file(log_entry)
                return

        try:
            # 序列化日志
            data = msgpack.packb(log_entry)

            # 发送
            with self._lock:
                self.socket.send(data, zmq.NOBLOCK)

        except zmq.Again:
            # 发送超时
            print(f"[DistributedLogHandler] 发送超时")
            self._fallback_to_file(log_entry)

        except Exception as e:
            # 发送失败
            print(f"[DistributedLogHandler] 发送失败: {e}")
            self.connected = False
            self._fallback_to_file(log_entry)

    def _fallback_to_file(self, log_entry: Dict[str, Any]) -> None:
        """降级到本地文件.

        Args:
            log_entry: 日志条目
        """
        try:
            with open(self.fallback_file, "a", encoding="utf-8") as f:
                import json
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        except Exception as e:
            print(f"[DistributedLogHandler] 降级日志写入失败: {e}")

    def close(self) -> None:
        """关闭处理器."""
        with self._lock:
            if self.socket:
                self.socket.close()
                self.socket = None

            if self.context:
                self.context.term()
                self.context = None

        super().close()


class AlertSubscriber(QObject):
    """告警订阅器.

    订阅日志进程的告警事件，通过Qt信号安全更新UI。

    特性：
    - 后台线程接收，不阻塞主线程
    - Qt信号机制，保证线程安全
    - 自动重连
    - 主题过滤
    """

    # Qt信号（在主线程中触发）
    alert_received = Signal(dict)

    def __init__(
        self,
        alert_port: int = 5558,
        max_retries: int = 3,
        retry_delay: float = 2.0,
        recv_timeout: int = 5000,
    ):
        """初始化告警订阅器.

        Args:
            alert_port: 告警推送端口
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
            recv_timeout: 接收超时（毫秒）
        """
        super().__init__()

        self.alert_port = alert_port
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.recv_timeout = recv_timeout

        # ZeroMQ连接
        self.context: Optional[zmq.Context] = None
        self.socket: Optional[zmq.Socket] = None
        self.connected = False

        # 接收线程
        self.receive_thread: Optional[threading.Thread] = None
        self.running = False

    def start(self) -> bool:
        """启动订阅.

        Returns:
            是否启动成功
        """
        if self.running:
            print(f"[AlertSubscriber] 已经在运行")
            return True

        # 连接到告警推送端口
        if not self._connect():
            print(f"[AlertSubscriber] 连接失败")
            return False

        # 启动接收线程
        self.running = True
        self.receive_thread = threading.Thread(
            target=self._receive_loop,
            daemon=True,
            name="AlertSubscriber",
        )
        self.receive_thread.start()

        print(f"[AlertSubscriber] 已启动，订阅端口: {self.alert_port}")
        return True

    def stop(self) -> None:
        """停止订阅."""
        self.running = False

        if self.receive_thread:
            self.receive_thread.join(timeout=2.0)

        self._disconnect()

        print(f"[AlertSubscriber] 已停止")

    def _connect(self) -> bool:
        """连接到告警推送端口.

        Returns:
            是否连接成功
        """
        try:
            if self.context is None:
                self.context = zmq.Context()

            if self.socket is not None:
                self.socket.close()

            # 创建SUB套接字
            self.socket = self.context.socket(zmq.SUB)
            self.socket.setsockopt(zmq.RCVTIMEO, self.recv_timeout)
            self.socket.setsockopt(zmq.SUBSCRIBE, b"alert")  # 订阅alert主题
            self.socket.connect(f"tcp://127.0.0.1:{self.alert_port}")

            self.connected = True
            return True

        except Exception as e:
            print(f"[AlertSubscriber] 连接失败: {e}")
            self.connected = False
            return False

    def _disconnect(self) -> None:
        """断开连接."""
        if self.socket:
            self.socket.close()
            self.socket = None

        if self.context:
            self.context.term()
            self.context = None

        self.connected = False

    def _receive_loop(self) -> None:
        """接收循环（后台线程）."""
        while self.running:
            try:
                if not self.connected:
                    # 尝试重连
                    print(f"[AlertSubscriber] 尝试重连...")
                    if not self._connect():
                        time.sleep(self.retry_delay)
                        continue

                # 接收消息
                topic, message = self.socket.recv_multipart()

                # 反序列化告警数据
                alert_data = msgpack.unpackb(message, raw=False)

                # 发射Qt信号（线程安全）
                self.alert_received.emit(alert_data)

            except zmq.Again:
                # 接收超时，继续循环
                continue

            except Exception as e:
                print(f"[AlertSubscriber] 接收错误: {e}")
                self.connected = False
                time.sleep(self.retry_delay)


# 全局实例（单例模式）
_distributed_log_handler: Optional[DistributedLogHandler] = None
_alert_subscriber: Optional[AlertSubscriber] = None


def get_distributed_log_handler() -> DistributedLogHandler:
    """获取分布式日志处理器（单例）.

    Returns:
        分布式日志处理器实例
    """
    global _distributed_log_handler

    if _distributed_log_handler is None:
        _distributed_log_handler = DistributedLogHandler()

    return _distributed_log_handler


def get_alert_subscriber() -> AlertSubscriber:
    """获取告警订阅器（单例）.

    Returns:
        告警订阅器实例
    """
    global _alert_subscriber

    if _alert_subscriber is None:
        _alert_subscriber = AlertSubscriber()

    return _alert_subscriber
