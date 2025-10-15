# -*- coding: utf-8 -*-
"""
统一日志管理系统.

提供完整的日志收集、存储、查询和管理功能，支持实时推送和历史查询。
"""

import json
import logging
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.core.utils import EVENT_LOG_RECORD


class LogRecordHandler(logging.Handler):
    """自定义日志记录处理器.

    拦截所有日志记录，结构化存储并推送到事件引擎。
    """

    def __init__(self, log_manager: "LogManager"):
        """初始化日志记录处理器.

        Args:
            log_manager: 日志管理器实例
        """
        super().__init__()
        self.log_manager = log_manager
        self.setLevel(logging.DEBUG)

        # 设置格式化器
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        self.setFormatter(formatter)

    def emit(self, record: logging.LogRecord) -> None:
        """处理日志记录.

        Args:
            record: 日志记录
        """
        try:
            # 跳过日志系统本身的记录，避免递归
            if record.name.startswith('backend.core.logging_system'):
                return

            # 增强递归检测：检查是否在日志处理过程中
            if hasattr(record, '_in_log_handler'):
                print(f"[DEBUG] 检测到递归日志记录，跳过: {record.name}")
                return

            # 标记当前记录正在被日志处理器处理
            record._in_log_handler = True

            # 提取异常信息
            exception_text = ""
            if record.exc_info:
                exception_text = self.formatException(record.exc_info)

            # 构建日志数据
            log_data = {
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

            # 只在非日志系统模块时才推送，避免递归
            if not record.name.startswith('backend.core.logging_system'):
                try:
                    # 推送到事件引擎（实时推送）
                    self.log_manager.publish_log_record(log_data)
                except Exception as e:
                    # 推送失败时静默处理，避免递归
                    # 但在调试模式下输出警告
                    if record.levelno >= logging.ERROR:
                        print(f"[DEBUG] 日志事件推送失败: {e}")

            # 存储到数据库（批量插入）
            try:
                self.log_manager.add_log_record(log_data)
            except Exception as e:
                # 存储失败时静默处理，避免递归
                # 但在调试模式下输出警告
                if record.levelno >= logging.ERROR:
                    print(f"[DEBUG] 日志数据库存储失败: {e}")

        except Exception as e:
            # 避免任何形式的递归记录错误
            try:
                # 只在控制台输出，不使用日志系统
                if not str(e).startswith('日志处理器错误'):
                    print(f"日志处理器错误: {e}")
            except:
                pass
        finally:
            # 清理标记
            if hasattr(record, '_in_log_handler'):
                delattr(record, '_in_log_handler')


class LogDatabase:
    """日志数据库管理器.

    提供日志记录的SQLite存储和查询功能。
    """

    def __init__(self, db_path: str = "data/logs.db"):
        """初始化日志数据库.

        Args:
            db_path: 数据库文件路径
        """
        self.db_path = db_path
        self._lock = threading.Lock()

        # 确保数据库目录存在
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

        # 初始化数据库
        self._init_database()

    def _init_database(self) -> None:
        """初始化数据库表结构."""
        import time
        db_init_start = time.time()

        print(f"[DEBUG] 初始化日志数据库: {self.db_path}")

        try:
            # 使用更长的超时时间防止阻塞
            print(f"[DEBUG] 连接数据库，timeout=30.0s...")
            conn_start = time.time()
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                conn_end = time.time()
                print(f"[DEBUG] 数据库连接成功，耗时: {conn_end - conn_start:.3f}s")

                print(f"[DEBUG] 创建日志表结构...")
                table_start = time.time()
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        level TEXT NOT NULL,
                        logger_name TEXT,
                        module TEXT,
                        function_name TEXT,
                        line_number INTEGER,
                        message TEXT NOT NULL,
                        exception TEXT,
                        thread INTEGER,
                        thread_name TEXT,
                        process INTEGER,
                        filename TEXT,
                        created_at REAL NOT NULL
                    )
                """)
                table_end = time.time()
                print(f"[DEBUG] 日志表创建完成，耗时: {table_end - table_start:.3f}s")

                # 创建索引
                print(f"[DEBUG] 创建索引...")
                index_start = time.time()
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON logs(timestamp)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_level ON logs(level)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_module ON logs(module)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_logger_name ON logs(logger_name)")
                index_end = time.time()
                print(f"[DEBUG] 索引创建完成，耗时: {index_end - index_start:.3f}s")

                print(f"[DEBUG] 提交事务...")
                commit_start = time.time()
                conn.commit()
                commit_end = time.time()
                print(f"[DEBUG] 事务提交完成，耗时: {commit_end - commit_start:.3f}s")

            db_init_end = time.time()
            total_time = db_init_end - db_init_start
            print(f"[DEBUG] ✅ 日志数据库初始化完成，总耗时: {total_time:.3f}s")

        except Exception as e:
            db_init_end = time.time()
            total_time = db_init_end - db_init_start
            print(f"[DEBUG] ❌ 日志数据库初始化失败，耗时: {total_time:.3f}s，错误: {e}")
            raise

    def add_log_record(self, log_data: Dict[str, Any]) -> None:
        """添加日志记录（批量插入优化）.

        Args:
            log_data: 日志数据字典
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                    conn.execute("""
                        INSERT OR IGNORE INTO logs
                        (timestamp, level, logger_name, module, function_name, line_number,
                         message, exception, thread, thread_name, process, filename, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        log_data["timestamp"],
                        log_data["level"],
                        log_data["logger_name"],
                        log_data["module"],
                        log_data["function"],
                        log_data["line"],
                        log_data["message"],
                        log_data["exception"],
                        log_data["thread"],
                        log_data["thread_name"],
                        log_data["process"],
                        log_data["filename"],
                        time.time(),
                    ))
                    conn.commit()

        except Exception as e:
            print(f"日志数据库插入失败: {e}")

    def query_logs(
        self,
        level: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        module: Optional[str] = None,
        logger_name: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """查询日志记录.

        Args:
            level: 日志级别筛选
            start_time: 开始时间 (ISO格式)
            end_time: 结束时间 (ISO格式)
            module: 模块名筛选
            logger_name: 日志记录器名筛选
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            日志记录列表
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                conn.row_factory = sqlite3.Row

                # 构建查询条件
                conditions = []
                params = []

                if level:
                    conditions.append("level = ?")
                    params.append(level)

                if start_time:
                    conditions.append("timestamp >= ?")
                    params.append(start_time)

                if end_time:
                    conditions.append("timestamp <= ?")
                    params.append(end_time)

                if module:
                    conditions.append("module LIKE ?")
                    params.append(f"%{module}%")

                if logger_name:
                    conditions.append("logger_name LIKE ?")
                    params.append(f"%{logger_name}%")

                where_clause = " AND ".join(conditions) if conditions else "1=1"

                # 执行查询
                cursor = conn.execute(f"""
                    SELECT * FROM logs
                    WHERE {where_clause}
                    ORDER BY timestamp DESC
                    LIMIT ? OFFSET ?
                """, params + [limit, offset])

                # 转换结果
                results = []
                for row in cursor.fetchall():
                    results.append({
                        "id": row["id"],
                        "timestamp": row["timestamp"],
                        "level": row["level"],
                        "logger_name": row["logger_name"],
                        "module": row["module"],
                        "function_name": row["function_name"],
                        "line_number": row["line_number"],
                        "message": row["message"],
                        "exception": row["exception"],
                        "thread": row["thread"],
                        "thread_name": row["thread_name"],
                        "process": row["process"],
                        "filename": row["filename"],
                    })

                return results

        except Exception as e:
            print(f"日志查询失败: {e}")
            return []

    def get_log_stats(self) -> Dict[str, Any]:
        """获取日志统计信息.

        Returns:
            统计信息字典
        """
        try:
            with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                # 按级别统计
                cursor = conn.execute("""
                    SELECT level, COUNT(*) as count
                    FROM logs
                    WHERE timestamp >= ?
                    GROUP BY level
                """, ((datetime.now() - timedelta(days=7)).isoformat(),))

                level_stats = {row["level"]: row["count"] for row in cursor.fetchall()}

                # 按模块统计
                cursor = conn.execute("""
                    SELECT module, COUNT(*) as count
                    FROM logs
                    WHERE timestamp >= ? AND module IS NOT NULL
                    GROUP BY module
                    ORDER BY count DESC
                    LIMIT 10
                """, ((datetime.now() - timedelta(days=7)).isoformat(),))

                module_stats = [
                    {"module": row["module"], "count": row["count"]}
                    for row in cursor.fetchall()
                ]

                # 总记录数
                cursor = conn.execute("SELECT COUNT(*) as total FROM logs")
                row = cursor.fetchone()
                total_count = row[0] if isinstance(row, (tuple, list)) else row["total"]

                return {
                    "total_count": total_count,
                    "level_stats": level_stats,
                    "module_stats": module_stats,
                    "recent_days": 7,
                }

        except Exception as e:
            print(f"获取日志统计失败: {e}")
            return {}

    def cleanup_old_logs(self, retention_days: int = 30) -> int:
        """清理旧日志记录.

        Args:
            retention_days: 保留天数

        Returns:
            删除的记录数量
        """
        try:
            cutoff_time = (datetime.now() - timedelta(days=retention_days)).isoformat()

            with self._lock:
                with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                    cursor = conn.execute(
                        "DELETE FROM logs WHERE timestamp < ?",
                        (cutoff_time,)
                    )
                    deleted_count = cursor.rowcount
                    conn.commit()

                    return deleted_count

        except Exception as e:
            print(f"清理旧日志失败: {e}")
            return 0


class LogManager:
    """日志系统管理器.

    统一管理日志收集、存储和查询功能。
    """

    def __init__(
        self,
        db_path: str = "data/logs.db",
        event_engine=None,
        retention_days: int = 30,
    ):
        """初始化日志管理器.

        Args:
            db_path: 日志数据库路径
            event_engine: VnPy事件引擎实例
            retention_days: 日志保留天数
        """
        self.db_path = db_path
        self.event_engine = event_engine
        self.retention_days = retention_days

        # 日志记录器（必须先初始化）
        self.logger = logging.getLogger(__name__)

        # 初始化数据库
        self.database = LogDatabase(db_path)

        # 批量插入缓冲区
        self._batch_buffer: List[Dict[str, Any]] = []
        self._batch_lock = threading.Lock()
        self._batch_timer: Optional[threading.Timer] = None

        # 延迟启动清理定时器，避免启动时阻塞
        # self._start_cleanup_timer()

    def initialize(self) -> bool:
        """初始化日志管理系统.

        Returns:
            是否初始化成功
        """
        try:
            import time
            init_start = time.time()

            print(f"[DEBUG] LogManager.initialize() 开始执行...")

            # 创建自定义日志处理器
            print(f"[DEBUG] 创建 LogRecordHandler...")
            handler_start = time.time()
            log_handler = LogRecordHandler(self)
            handler_end = time.time()
            print(f"[DEBUG] LogRecordHandler 创建完成，耗时: {handler_end - handler_start:.3f}s")

            # 添加到根日志记录器
            print(f"[DEBUG] 获取根日志记录器并添加处理器...")
            logger_start = time.time()
            root_logger = logging.getLogger()
            root_logger.addHandler(log_handler)
            logger_end = time.time()
            print(f"[DEBUG] 日志处理器添加完成，耗时: {logger_end - logger_start:.3f}s")

            # 设置日志级别
            print(f"[DEBUG] 设置日志级别为 DEBUG...")
            root_logger.setLevel(logging.DEBUG)

            init_end = time.time()
            total_time = init_end - init_start
            print(f"[DEBUG] ✅ 日志管理系统初始化完成，总耗时: {total_time:.3f}s")

            # 初始化完成后，暂时不启动清理定时器（避免阻塞）
            print(f"[DEBUG] 日志清理定时器已禁用（避免启动阻塞）")

            # 使用 print 而不是 logger，避免递归日志记录
            print(f"[DEBUG] 日志管理系统初始化完成")
            return True

        except Exception as e:
            print(f"[DEBUG] 💥 日志管理系统初始化异常: {e}")
            self.logger.error("日志管理系统初始化失败: %s", e)
            return False

    def shutdown(self) -> None:
        """关闭日志管理系统."""
        try:
            print(f"[DEBUG] 关闭日志管理系统...")

            # 刷新剩余的批量缓冲区
            self._flush_batch_buffer()

            # 取消所有定时器
            print(f"[DEBUG] 取消日志定时器...")
            if self._batch_timer:
                self._batch_timer.cancel()
                print(f"[DEBUG] 批量缓冲定时器已取消")

            # 注意：清理定时器不需要显式取消，它会在下次执行时自动停止

            # 移除日志处理器
            print(f"[DEBUG] 移除日志处理器...")
            root_logger = logging.getLogger()
            for handler in root_logger.handlers[:]:
                if isinstance(handler, LogRecordHandler):
                    root_logger.removeHandler(handler)

            print(f"[DEBUG] ✅ 日志管理系统已关闭")
            self.logger.info("日志管理系统已关闭")

        except Exception as e:
            print(f"[DEBUG] 关闭日志管理系统失败: {e}")
            self.logger.error("关闭日志管理系统失败: %s", e)

    def add_log_record(self, log_data: Dict[str, Any]) -> None:
        """添加日志记录到缓冲区.

        Args:
            log_data: 日志数据
        """
        with self._batch_lock:
            self._batch_buffer.append(log_data)

            # 如果缓冲区达到阈值，立即刷新
            if len(self._batch_buffer) >= 10:
                self._flush_batch_buffer()

                # 重新启动批量定时器
                if self._batch_timer:
                    self._batch_timer.cancel()

                self._batch_timer = threading.Timer(1.0, self._flush_batch_buffer)
                self._batch_timer.daemon = True
                self._batch_timer.start()

    def publish_log_record(self, log_data: Dict[str, Any]) -> None:
        """发布日志记录到事件引擎.

        Args:
            log_data: 日志数据
        """
        if not self.event_engine:
            return

        try:
            # 检查事件引擎是否活跃（避免阻塞）
            if hasattr(self.event_engine, 'is_active') and not self.event_engine.is_active():
                print(f"[DEBUG] 事件引擎非活跃，跳过日志事件发布")
                return

            # 导入事件类型常量（避免循环导入）
            from backend.core.utils import EVENT_LOG_RECORD
            from vnpy.event import Event

            # 创建事件
            event = Event(EVENT_LOG_RECORD, log_data)

            # 发布事件（非阻塞方式）
            try:
                self.event_engine.put(event)
            except Exception as e:
                # 如果事件引擎put操作可能阻塞，这里应该处理
                print(f"[DEBUG] 事件引擎put操作异常: {e}")
                # 不抛出异常，避免递归日志

        except Exception as e:
            # 避免在错误处理中再次触发日志，导致递归
            print(f"[DEBUG] 发布日志事件失败: {e}")

    def _flush_batch_buffer(self) -> None:
        """刷新批量缓冲区到数据库."""
        if not self._batch_buffer:
            return

        try:
            with self._batch_lock:
                # 获取当前缓冲区内容
                buffer_to_flush = self._batch_buffer.copy()
                self._batch_buffer.clear()

            # 批量插入到数据库
            for log_data in buffer_to_flush:
                try:
                    self.database.add_log_record(log_data)
                except Exception as e:
                    print(f"[DEBUG] 批量插入日志记录失败: {e}")

            # 注意：不要在这里重新启动定时器，避免递归
            # 定时器会在下次有新日志时重新启动

        except Exception as e:
            print(f"[DEBUG] 刷新批量缓冲区失败: {e}")

    def _start_cleanup_timer(self) -> None:
        """启动定期清理定时器."""
        try:
            # 暂时禁用定时器，避免启动时阻塞
            # delay = 24 * 60 * 60  # 24小时 = 86400秒
            print(f"[DEBUG] 日志清理定时器已禁用（避免启动阻塞）")

            # 如果需要启用，请取消下面这行的注释：
            # delay = 3600  # 1小时测试用，生产环境应该用 24 * 60 * 60

            # print(f"[DEBUG] 启动日志清理定时器，间隔: {delay}s")
            # cleanup_timer = threading.Timer(delay, self._schedule_next_cleanup)
            # cleanup_timer.daemon = True
            # cleanup_timer.start()
            # next_cleanup_time = datetime.now() + timedelta(seconds=delay)
            # self.logger.info("日志清理定时器已启动，下次清理: %s", next_cleanup_time)

        except Exception as e:
            # 避免定时器启动失败导致的错误
            print(f"[DEBUG] 启动日志清理定时器失败: {e}")

    def _schedule_next_cleanup(self) -> None:
        """调度下次清理任务（避免递归调用）."""
        try:
            print(f"[DEBUG] 调度下次日志清理...")
            # 执行清理任务
            self._cleanup_task()
            # 注意：定时器已在启动时设置，不需要重新启动
        except Exception as e:
            print(f"[DEBUG] 调度下次清理失败: {e}")

    def _cleanup_task(self) -> None:
        """执行清理任务."""
        try:
            print(f"[DEBUG] 执行日志清理任务...")
            deleted_count = self.database.cleanup_old_logs(self.retention_days)
            self.logger.info("日志清理完成，删除 %d 条记录", deleted_count)
            print(f"[DEBUG] 日志清理完成，删除 {deleted_count} 条记录")

        except Exception as e:
            print(f"[DEBUG] 日志清理任务失败: {e}")
            self.logger.error("日志清理任务失败: %s", e)

    def query_logs(
        self,
        level: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        module: Optional[str] = None,
        logger_name: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """查询日志记录.

        Args:
            level: 日志级别筛选
            start_time: 开始时间
            end_time: 结束时间
            module: 模块名筛选
            logger_name: 日志记录器名筛选
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            日志记录列表
        """
        return self.database.query_logs(
            level=level,
            start_time=start_time,
            end_time=end_time,
            module=module,
            logger_name=logger_name,
            limit=limit,
            offset=offset,
        )

    def get_log_stats(self) -> Dict[str, Any]:
        """获取日志统计信息.

        Returns:
            统计信息字典
        """
        return self.database.get_log_stats()

    def export_logs(
        self,
        file_path: str,
        level: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        module: Optional[str] = None,
    ) -> bool:
        """导出日志到文件.

        Args:
            file_path: 导出文件路径
            level: 日志级别筛选
            start_time: 开始时间
            end_time: 结束时间
            module: 模块名筛选

        Returns:
            是否导出成功
        """
        try:
            # 查询日志记录
            logs = self.query_logs(
                level=level,
                start_time=start_time,
                end_time=end_time,
                module=module,
                limit=10000,  # 导出限制
            )

            # 写入文件
            with open(file_path, "w", encoding="utf-8") as f:
                for log in logs:
                    f.write(f"[{log['timestamp']}] {log['level']} {log['module']}.{log['function_name']}:{log['line_number']} - {log['message']}\n")
                    if log['exception']:
                        f.write(f"Exception: {log['exception']}\n")

            self.logger.info("日志已导出到: %s，共 %d 条记录", file_path, len(logs))
            return True

        except Exception as e:
            self.logger.error("导出日志失败: %s", e)
            return False


# 全局日志管理器实例
_log_manager: Optional[LogManager] = None
_log_manager_lock = threading.Lock()


def get_log_manager() -> LogManager:
    """获取全局日志管理器实例.

    Returns:
        日志管理器实例
    """
    global _log_manager
    if _log_manager is None:
        with _log_manager_lock:
            if _log_manager is None:
                _log_manager = LogManager()
    return _log_manager


def initialize_logging_system(event_engine=None, config: Optional[Dict[str, Any]] = None) -> bool:
    """初始化日志系统.

    Args:
        event_engine: VnPy事件引擎实例
        config: 配置字典

    Returns:
        是否初始化成功
    """
    try:
        import time
        start_time = time.time()

        print(f"[DEBUG] 开始初始化日志系统... (事件引擎: {event_engine is not None})")

        # 获取配置
        if config is None:
            config = {
                "db_path": "data/logs.db",
                "retention_days": 30,
            }

        print(f"[DEBUG] 日志系统配置: {config}")

        # 创建全局日志管理器
        global _log_manager
        with _log_manager_lock:
            print(f"[DEBUG] 创建 LogManager 实例...")
            _log_manager = LogManager(
                db_path=config.get("db_path", "data/logs.db"),
                event_engine=event_engine,
                retention_days=config.get("retention_days", 30),
            )

        # 初始化日志系统
        print(f"[DEBUG] 开始 LogManager.initialize()...")
        init_start = time.time()
        success = _log_manager.initialize()
        init_end = time.time()

        print(f"[DEBUG] LogManager.initialize() 完成，耗时: {init_end - init_start:.3f}s")

        if success:
            total_time = time.time() - start_time
            print(f"[DEBUG] ✅ 日志系统初始化成功，总耗时: {total_time:.3f}s")
            logging.info("日志系统初始化完成")
        else:
            total_time = time.time() - start_time
            print(f"[DEBUG] ❌ 日志系统初始化失败，总耗时: {total_time:.3f}s")
            logging.error("日志系统初始化失败")

        return success

    except Exception as e:
        print(f"[DEBUG] 💥 初始化日志系统异常: {e}")
        logging.error("初始化日志系统失败: %s", e)
        return False


def shutdown_logging_system() -> None:
    """关闭日志系统."""
    global _log_manager
    if _log_manager:
        _log_manager.shutdown()
        _log_manager = None
        logging.info("日志系统已关闭")
