# -*- coding: utf-8 -*-
"""
启动日志系统 - 启动专用日志记录器

提供启动流程的专用日志系统，支持：
- 有序日志队列（确保并发启动时日志按顺序展示）
- 启动AI日志处理器（每次启动生成一个log文件到logs/ai/）
- 简洁的Terminal输出（阶段开始/成功/结束，异常时输出Warning/Error/Critical）
"""

import heapq
import logging
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple, Callable

logger = logging.getLogger("backend.startup.logging")


class OrderedLogQueue:
    """有序日志队列 - 确保并发启动时日志按执行时间顺序展示

    支持：
    - 按执行时间排序（而非序列号）
    - 并发启动时日志按时间顺序展示
    - 日志滞后处理（可以滞后但不能丢失）
    """

    def __init__(self, max_wait_seconds: int = 30):
        """初始化有序日志队列

        Args:
            max_wait_seconds: 最大等待时间（秒），超过此时间即使前面的日志未到也输出
        """
        self.queue: List[Tuple[float, Any]] = []  # [(timestamp, record), ...]
        self.lock = threading.Lock()
        self.max_wait_seconds = max_wait_seconds
        self.logger = logging.getLogger("backend.startup.logging.ordered_queue")

        # 记录日志的时间戳（用于超时检测）
        self._record_timestamps: Dict[float, float] = {}
        self._output_callback: Optional[Callable[[Any], None]] = None

        # 后台线程：定期检查并输出超时的日志
        self._running = True
        self._check_thread = threading.Thread(target=self._check_timeout_logs, daemon=True)
        self._check_thread.start()

    def set_output_callback(self, callback: Callable[[Any], None]):
        """设置输出回调函数

        Args:
            callback: 回调函数，接收 UnifiedLogRecord 作为参数
        """
        self._output_callback = callback

    def add_log(self, record: Any, sequence: int):
        """添加日志到队列（按执行时间排序）

        Args:
            record: 日志记录（UnifiedLogRecord）
            sequence: 日志序列号（用于兼容性，实际按时间排序）
        """
        with self.lock:
            # 使用记录的时间戳作为排序键（更准确的时间顺序）
            timestamp = record.timestamp.timestamp()
            record.sequence = sequence
            heapq.heappush(self.queue, (timestamp, record))
            self._record_timestamps[timestamp] = time.time()
            self._try_flush()

    def _try_flush(self):
        """尝试输出队列中已准备好的日志（按时间顺序）"""
        # 按时间顺序输出所有日志，不再等待序列号连续
        while self.queue:
            timestamp, record = heapq.heappop(self.queue)
            # 输出日志
            self._output_log(record)
            # 清理时间戳
            self._record_timestamps.pop(timestamp, None)

    def _output_log(self, record: Any):
        """输出日志到Terminal/AI文件

        Args:
            record: 日志记录（UnifiedLogRecord）
        """
        if self._output_callback:
            try:
                self._output_callback(record)
            except Exception as e:
                self.logger.exception(f"输出日志回调失败: {e}")

    def _check_timeout_logs(self):
        """后台线程：定期检查并输出超时的日志"""
        while self._running:
            time.sleep(0.5)  # 每0.5秒检查一次

            with self.lock:
                if not self.queue:
                    continue

                # 检查是否有超时的日志
                current_time = time.time()
                timeout_timestamps = [
                    timestamp
                    for timestamp, added_time in self._record_timestamps.items()
                    if current_time - added_time > self.max_wait_seconds
                ]

                # 输出超时的日志（按时间顺序）
                if timeout_timestamps:
                    # 对超时的日志按时间排序
                    timeout_timestamps.sort()

                    for timeout_ts in timeout_timestamps:
                        # 找到对应的日志记录
                        for i, (q_ts, q_record) in enumerate(self.queue):
                            if q_ts == timeout_ts:
                                # 输出日志
                                self._output_log(q_record)
                                # 从队列中移除
                                self.queue.pop(i)
                                heapq.heapify(self.queue)
                                # 清理时间戳
                                self._record_timestamps.pop(timeout_ts, None)
                                break

                # 继续尝试正常输出（现在会输出所有日志，因为不再等待序列号连续）
                self._try_flush()

    def close(self):
        """关闭队列"""
        self._running = False
        if self._check_thread.is_alive():
            self._check_thread.join(timeout=1.0)



class StartupLogger:
    """启动专用日志记录器

    提供简洁的Terminal输出接口：
    - 阶段开始日志（📍 标记）
    - 阶段成功日志（✅ 标记）
    - 阶段结束日志（✅ 标记）
    - 异常时输出 Warning/Error/Critical
    """

    def __init__(self):
        """初始化启动日志记录器"""
        self.logger = logging.getLogger("startup.stage")
        self.ordered_queue: Optional[OrderedLogQueue] = None
        self._sequence_counter = 0
        self._sequence_lock = threading.Lock()
        self._is_startup_phase = True  # 是否处于启动阶段

    def initialize(self, enable_ordered_queue: bool = True):
        """初始化日志系统

        🔧 优化：已删除StartupAILogHandler，AI日志统一通过LoggingHub的AILogFileHandler处理

        Args:
            enable_ordered_queue: 是否启用有序队列（启动阶段建议启用）
        """
        if enable_ordered_queue:
            self.ordered_queue = OrderedLogQueue(max_wait_seconds=30)
            # 设置输出回调（只输出到Terminal，AI日志由LoggingHub统一处理）
            self.ordered_queue.set_output_callback(self._output_record)

    def stage_start(self, stage_name: str):
        """阶段开始日志

        Args:
            stage_name: 阶段名称
        """
        message = f"📍 {stage_name} 开始"
        self._log_stage_node(message)

    def stage_success(self, stage_name: str, elapsed_ms: float):
        """阶段成功日志

        Args:
            stage_name: 阶段名称
            elapsed_ms: 耗时（毫秒）
        """
        message = f"✅ {stage_name} 完成 ({elapsed_ms:.0f}ms)"
        self._log_stage_node(message)

    def stage_error(self, stage_name: str, error: Optional[Exception] = None):
        """阶段错误日志

        Args:
            stage_name: 阶段名称
            error: 错误异常（可选）
        """
        if error:
            message = f"❌ {stage_name} 失败: {str(error)}"
        else:
            message = f"❌ {stage_name} 失败"
        self._log_stage_node(message)

        # 如果异常，输出完整堆栈
        if error:
            self.logger.exception(f"阶段 {stage_name} 异常", exc_info=error)

    def _log_stage_node(self, message: str):
        """记录阶段节点日志（使用STAGE_NODE类型）

        Args:
            message: 日志消息
        """
        # 获取序列号（用于兼容性）
        with self._sequence_lock:
            sequence = self._sequence_counter
            self._sequence_counter += 1

        # 如果是启动阶段且启用了有序队列，使用有序队列（按时间排序）
        if self._is_startup_phase and self.ordered_queue:
            # 创建UnifiedLogRecord（简化版）
            record = type(
                "UnifiedLogRecord",
                (),
                {
                    "sequence": sequence,
                    "timestamp": datetime.now(),
                    "level": logging.INFO,
                    "logger_name": "startup.stage",
                    "message": message,
                    "type": "STAGE_NODE",
                    "exception": None,
                },
            )()

            # 添加到有序队列（内部按时间排序）
            self.ordered_queue.add_log(record, sequence)
        else:
            # 直接输出（非启动阶段或不使用有序队列）
            self.logger.info(message, extra={"log_type": "STAGE_NODE"})

    def _output_record(self, record: Any):
        """输出日志记录（回调函数）

        🔧 优化：只输出到Terminal，AI日志由LoggingHub的AILogFileHandler统一处理

        Args:
            record: 日志记录（UnifiedLogRecord）
        """
        # 输出到Terminal（通过标准logger）
        self.logger.info(record.message, extra={"log_type": "STAGE_NODE"})

    def close(self, success: bool = True, summary: Optional[str] = None):
        """关闭日志系统

        Args:
            success: 是否成功
            summary: 摘要信息（可选）
        """
        # 关闭有序队列
        if self.ordered_queue:
            self.ordered_queue.close()

        # 🔧 修复：不再调用 StartupAILogHandler.end_startup_log
        # AI日志文件的结束由统一日志系统的 end_ai_process 处理（在 orchestrator 中调用）

