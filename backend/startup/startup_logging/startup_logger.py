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
        self.max_wait = max_wait_seconds
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
                    if current_time - added_time > self.max_wait
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


class StartupAILogHandler:
    """启动专用AI日志处理器

    每次启动生成一个日志文件到 logs/ai/，包含所有级别的日志（DEBUG+）。
    """

    def __init__(self):
        """初始化启动AI日志处理器"""
        self.current_log_file: Optional[Path] = None
        self.log_dir = Path("logs/ai")
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._file_handle: Optional[Any] = None
        self._lock = threading.Lock()

    def start_startup_log(self, metadata: Optional[Dict[str, Any]] = None) -> Path:
        """开始启动日志文件

        Args:
            metadata: 元数据（可选）

        Returns:
            Path: 日志文件路径
        """
        with self._lock:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"application_startup_{timestamp}.log"
            self.current_log_file = self.log_dir / filename

            # 写入文件头
            try:
                self._file_handle = open(self.current_log_file, "w", encoding="utf-8")
                self._file_handle.write("=" * 80 + "\n")
                self._file_handle.write(f"AI助手专用日志文件 - application_startup\n")
                self._file_handle.write(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                if metadata:
                    self._file_handle.write(f"元数据: {metadata}\n")
                self._file_handle.write("=" * 80 + "\n\n")
                self._file_handle.flush()
            except Exception as e:
                logger.exception(f"创建启动日志文件失败: {e}")
                self._file_handle = None

            return self.current_log_file

    def write_log(self, record: Any):
        """写入日志到文件

        Args:
            record: 日志记录（UnifiedLogRecord）
        """
        if not self._file_handle:
            return

        try:
            with self._lock:
                # 格式化日志
                log_line = self._format_log(record)
                self._file_handle.write(log_line)
                self._file_handle.flush()
        except Exception as e:
            logger.exception(f"写入日志到文件失败: {e}")

    def _format_log(self, record: Any) -> str:
        """格式化日志记录

        Args:
            record: 日志记录（UnifiedLogRecord）

        Returns:
            str: 格式化后的日志字符串
        """
        timestamp = record.timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        level_name = logging.getLevelName(record.level)
        logger_name = record.logger_name or "unknown"

        # 构建日志行
        log_line = f"[{level_name}] {timestamp} - {logger_name} - {record.message}"

        # 添加异常信息
        if record.exception:
            log_line += f"\n{record.exception}"

        log_line += "\n"

        return log_line

    def end_startup_log(self, success: bool = True, summary: Optional[str] = None):
        """结束启动日志文件

        Args:
            success: 是否成功
            summary: 摘要信息（可选）
        """
        if not self._file_handle:
            return

        try:
            with self._lock:
                self._file_handle.write("\n" + "=" * 80 + "\n")
                self._file_handle.write(f"流程结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                self._file_handle.write(f"执行结果: {'✅ 成功' if success else '❌ 失败'}\n")
                if summary:
                    self._file_handle.write(f"摘要: {summary}\n")
                self._file_handle.write("=" * 80 + "\n")

                self._file_handle.close()
                self._file_handle = None
        except Exception as e:
            logger.exception(f"结束启动日志文件失败: {e}")

    def get_current_file_path(self) -> Optional[Path]:
        """获取当前日志文件路径

        Returns:
            Path: 当前日志文件路径，如果未创建返回None
        """
        return self.current_log_file


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
        self.ai_log_handler: Optional[StartupAILogHandler] = None
        self._sequence_counter = 0
        self._sequence_lock = threading.Lock()
        self._is_startup_phase = True  # 是否处于启动阶段

    def initialize(self, enable_ordered_queue: bool = True, enable_ai_log: bool = True):
        """初始化日志系统

        Args:
            enable_ordered_queue: 是否启用有序队列（启动阶段建议启用）
            enable_ai_log: 是否启用AI日志文件（启动阶段建议启用）
        """
        if enable_ordered_queue:
            self.ordered_queue = OrderedLogQueue(max_wait_seconds=30)
            # 设置输出回调（输出到Terminal和AI文件）
            self.ordered_queue.set_output_callback(self._output_record)

        if enable_ai_log:
            self.ai_log_handler = StartupAILogHandler()
            # 开始启动日志文件
            metadata = {
                "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "platform": sys.platform,
            }
            log_file = self.ai_log_handler.start_startup_log(metadata)
            # 不在Terminal输出，因为这会干扰环境准备阶段的输出格式
            # 只在AI日志文件中记录
            # self.logger.info(f"启动AI日志文件: {log_file}")

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

        Args:
            record: 日志记录（UnifiedLogRecord）
        """
        # 输出到Terminal（通过标准logger）
        self.logger.info(record.message, extra={"log_type": "STAGE_NODE"})

        # 输出到AI日志文件
        if self.ai_log_handler:
            self.ai_log_handler.write_log(record)

    def close(self, success: bool = True, summary: Optional[str] = None):
        """关闭日志系统

        Args:
            success: 是否成功
            summary: 摘要信息（可选）
        """
        # 关闭有序队列
        if self.ordered_queue:
            self.ordered_queue.close()

        # 结束AI日志文件
        if self.ai_log_handler:
            self.ai_log_handler.end_startup_log(success, summary)

