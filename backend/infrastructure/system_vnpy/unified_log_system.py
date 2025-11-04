# -*- coding: utf-8 -*-
"""
统一日志系统 - 整合版本 v5.0

整合了原有的多个日志相关模块：
- unified_logging.py (核心日志Hub)
- routing_engine.py (路由引擎)
- rule_cache.py (规则缓存)
- ai_log_handler.py (AI日志Handler)
- ai_log_context.py (AI日志上下文)
- logging_context.py (阶段上下文)

优化目标：
1. 单文件集中管理，便于调试
2. 消除重复代码
3. 简化路由逻辑
4. 确保所有日志都经过LogHub

作者：系统重构团队
日期：2025-10-28
版本：v5.0 (整合版)

⚠️ 过渡方案说明（v1.0新架构）：
- 新架构设计文档要求移除此文件，改用项目统一日志系统（backend.infrastructure.logging_system）
- 但项目统一日志系统尚未实现，因此暂时保留此文件作为过渡方案
- 待项目统一日志系统实现后，所有引用应迁移到新系统
- 所有导入应保持现有方式，无需修改
"""

import json
import logging
import time
import yaml
import gzip
import os
import asyncio
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from pathlib import Path
from threading import Lock, RLock
from typing import Any, Dict, List, Optional, Callable
from functools import lru_cache

from vnpy.event import Event, EventEngine

# 日志配置
logger = logging.getLogger("backend.infrastructure.system_vnpy.unified_log_system")

# =============================================================================
# Part 1: 数据结构定义
# =============================================================================


class LogType(Enum):
    """日志类型枚举."""

    SYSTEM = "system"
    PROGRESS = "progress"
    NOTIFICATION = "notification"
    ALERT = "alert"
    USER_FEEDBACK = "user_feedback"
    DEBUG = "debug"
    STAGE_NODE = "stage_node"


# 排除字段集合（类级别常量，避免每次重新创建）
_EXCLUDED_FIELDS = frozenset([
    "name", "msg", "args", "created", "filename", "funcName", "levelname",
    "levelno", "lineno", "module", "msecs", "message", "pathname", "process",
    "processName", "relativeCreated", "thread", "threadName", "exc_info",
    "exc_text", "stack_info",
])


@dataclass
class UnifiedLogRecord:
    """统一日志记录."""

    type: LogType
    level: int
    module: str
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime = field(default_factory=datetime.now)
    logger_name: str = ""
    function: str = ""
    line: int = 0
    filename: str = ""
    thread: int = 0
    thread_name: str = ""
    exception: str = ""


# =============================================================================
# Part 2: 事件类型定义
# =============================================================================

EVENT_LOG_SYSTEM = "eLogSystem"
EVENT_LOG_PROGRESS = "eLogProgress"
EVENT_LOG_NOTIFICATION = "eLogNotification"
EVENT_LOG_ALERT = "eLogAlert"
EVENT_UI_STATUSBAR = "eUIStatusBar"
EVENT_UI_DIALOG = "eUIDialog"


# =============================================================================
# Part 3: 规则缓存
# =============================================================================


class RuleCache:
    """规则缓存（LRU+TTL）."""

    def __init__(self, ttl_seconds: int = 60, max_size: int = 5000):
        """初始化缓存.

        Args:
            ttl_seconds: 缓存生存时间（秒），默认60秒（从5秒优化）
            max_size: 最大缓存条目数，默认5000（从1000优化）
        """
        self.ttl = ttl_seconds
        self.max_size = max_size
        self._cache: Dict[tuple, tuple] = {}  # {key: (targets, timestamp)}
        self._lock = Lock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: tuple) -> Optional[List[str]]:
        """获取缓存（检查TTL和LRU）."""
        with self._lock:
            if key not in self._cache:
                self._misses += 1
                return None

            targets, timestamp = self._cache[key]
            # 检查TTL
            if time.time() - timestamp > self.ttl:
                del self._cache[key]
                self._misses += 1
                return None

            self._hits += 1
            # LRU: 移到末尾
            self._cache[key] = self._cache.pop(key)
            return targets

    def set(self, key: tuple, targets: List[str]):
        """设置缓存（带LRU淘汰）."""
        with self._lock:
            # LRU淘汰
            if len(self._cache) >= self.max_size:
                # 删除最旧的
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
                self._evictions += 1

            self._cache[key] = (targets, time.time())

    def clear(self):
        """清空缓存."""
        with self._lock:
            self._cache.clear()

    def get_statistics(self) -> Dict:
        """获取统计信息."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            return {
                "size": len(self._cache),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(hit_rate, 2),
                "evictions": self._evictions,
            }


# =============================================================================
# Part 4: 路由引擎
# =============================================================================


class RoutingRuleEngine:
    """四层路由规则引擎（场景 > 模块 > 阶段 > 全局）."""

    def __init__(self, config_dir: str = "backend/infrastructure/system_vnpy/config"):
        """初始化路由引擎."""
        if not Path(config_dir).is_absolute():
            module_dir = Path(__file__).parent
            project_root = module_dir.parent.parent.parent
            self.config_dir = project_root / config_dir
        else:
            self.config_dir = Path(config_dir)

        self.logger = logging.getLogger("routing_engine")

        # 加载规则
        self.global_rules = self._load_yaml("rules_global.yaml")
        self.stage_rules = self._load_yaml("rules_stage.yaml")
        self.module_rules = self._load_yaml("rules_module.yaml")
        self.scenario_rules = self._load_yaml("rules_scenario.yaml")

        self.current_stage = "startup"
        self.run_mode = "prod"
        self.cache = RuleCache(ttl_seconds=60, max_size=5000)
        self._route_count = 0

        self.logger.info("路由规则引擎初始化完成")
        self.logger.info(f"  - 全局规则: {len(self.global_rules)} 个LogType")
        self.logger.info(f"  - 阶段规则: {len(self.stage_rules)} 个阶段")
        self.logger.info(f"  - 模块规则: {len(self.module_rules)} 个模块")
        self.logger.info(f"  - 场景规则: {len(self.scenario_rules)} 个场景")

    def _load_yaml(self, filename: str) -> Any:
        """加载YAML配置."""
        file_path = self.config_dir / filename
        if not file_path.exists():
            self.logger.warning("配置文件不存在: %s", file_path, extra={"log_type": "SYSTEM"})
            return {}

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            self.logger.error("加载配置文件失败: %s, 错误: %s", filename, e, extra={"log_type": "SYSTEM"})
            return {}

    def route(self, record: UnifiedLogRecord) -> List[str]:
        """执行路由决策（带缓存优化）."""
        self._route_count += 1

        log_type = record.type.value.upper()
        level = logging.getLevelName(record.level)
        module = record.module
        scenario = record.details.get("scenario") if record.details else None

        cache_key = (log_type, level, module, scenario, self.current_stage)
        cached_targets = self.cache.get(cache_key)
        if cached_targets is not None:
            return cached_targets

        targets = self._route_with_layers(log_type, level, module, scenario)
        self.cache.set(cache_key, targets)
        return targets

    def _route_with_layers(
        self, log_type: str, level: str, module: str, scenario: Optional[str]
    ) -> List[str]:
        """四层路由逻辑."""
        # Layer 4: 场景
        if scenario:
            scenario_key = f"scenario_{scenario}"
            targets = self.scenario_rules.get(scenario_key, {}).get(log_type, {}).get(level)
            if targets:
                return targets

        # Layer 3: 模块
        for module_key, module_config in self.module_rules.items():
            source_modules = module_config.get("source_modules", [])
            if any(mod in module for mod in source_modules):
                targets = module_config.get(log_type, {}).get(level)
                if targets:
                    return targets

        # Layer 2: 阶段
        stage_key = f"stage_{self.current_stage}"
        targets = self.stage_rules.get(stage_key, {}).get(log_type, {}).get(level)
        if targets:
            return targets

        # Layer 1: 全局
        return self.global_rules.get(log_type, {}).get(level, ["file"])

    def set_stage(self, stage: str):
        """切换阶段."""
        old_stage = self.current_stage
        self.current_stage = stage
        self.cache.clear()
        # 🎯 阶段切换消息只输出到AI日志，不输出到Terminal
        # 使用DEBUG级别，确保不会出现在Terminal输出中
        self.logger.debug(f"阶段切换: {old_stage} -> {stage}")

    def set_run_mode(self, mode: str):
        """切换运行模式."""
        if mode not in ["dev", "prod", "ops"]:
            return
        old_mode = self.run_mode
        self.run_mode = mode
        # 🎯 运行模式切换消息只输出到AI日志，不输出到Terminal
        self.logger.debug(f"运行模式切换: {old_mode} -> {mode}")

    def reload_rules(self):
        """热更新规则."""
        self.global_rules = self._load_yaml("rules_global.yaml")
        self.stage_rules = self._load_yaml("rules_stage.yaml")
        self.module_rules = self._load_yaml("rules_module.yaml")
        self.scenario_rules = self._load_yaml("rules_scenario.yaml")
        self.cache.clear()
        self.logger.info("路由规则热更新完成")

    def validate_config(self) -> bool:
        """验证配置完整性."""
        required_log_types = [
            "SYSTEM",
            "PROGRESS",
            "NOTIFICATION",
            "ALERT",
            "USER_FEEDBACK",
            "DEBUG",
            "STAGE_NODE",
        ]
        missing_types = [lt for lt in required_log_types if lt not in self.global_rules]

        if missing_types:
            self.logger.error(f"全局规则缺少LogType: {missing_types}", extra={"log_type": "ALERT"})
            return False

        self.logger.info("配置验证通过")
        return True

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息."""
        cache_stats = self.cache.get_statistics()
        return {
            "total_routes": self._route_count,
            "cache_stats": {
                "size": cache_stats["size"],
                "hits": cache_stats["hits"],
                "misses": cache_stats["misses"],
                "hit_rate": f"{cache_stats['hit_rate']}%",
                "evictions": cache_stats["evictions"],
            },
            "current_stage": self.current_stage,
            "run_mode": self.run_mode,
            "rules_loaded": {
                "global": len(self.global_rules),
                "stage": len(self.stage_rules),
                "module": len(self.module_rules),
                "scenario": len(self.scenario_rules),
            },
        }


# =============================================================================
# Part 5: AI日志Handler
# =============================================================================


class AILogFileHandler(logging.Handler):
    """AI助手专用日志文件Handler."""

    def __init__(self, base_dir: str = "logs/ai", encoding: str = "utf-8"):
        """初始化AI日志Handler."""
        super().__init__()
        # ✅ 设置为DEBUG级别，确保接收所有日志
        self.setLevel(logging.DEBUG)

        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.encoding = encoding

        self._current_process: Optional[str] = None
        self._current_file: Optional[Any] = None
        self._current_file_path: Optional[Path] = None
        self._lock = Lock()
        self._process_count = 0
        self._total_logs = 0

        # ✅ 统计各级别日志数量
        self._level_counts = {"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}

        # 日志压缩配置
        self._compression_enabled = True
        self._compression_size_threshold_mb = 10  # 10MB
        self._compression_age_days = 7  # 7天

        # 异步I/O支持
        try:
            from backend.infrastructure.native_iocp.compat import (
                aopen as _compat_aopen,
                is_iocp_available,
            )
            self._use_async_io = is_iocp_available()
            self._compat_aopen = _compat_aopen
        except (ImportError, AttributeError):
            self._use_async_io = False
            self._compat_aopen = None

        # 异步写入队列和协程
        self._async_write_queue: Optional[asyncio.Queue] = None
        self._async_writer_task: Optional[asyncio.Task] = None
        self._async_io_lock = Lock()

        # ✅ 增强格式化器，更清晰地区分日志级别
        self.setFormatter(
            logging.Formatter(
                fmt="[%(asctime)s] [%(levelname)-8s] [%(name)-40s] [%(funcName)s:%(lineno)d]\n    %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

    def start_process(self, process_name: str, metadata: Optional[Dict[str, Any]] = None) -> Path:
        """开始新流程."""
        with self._lock:
            self._close_current_file()

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"{process_name}_{timestamp}.log"
            file_path = self.base_dir / filename

            # 如果支持异步I/O，使用异步队列；否则使用同步文件
            if getattr(self, "_use_async_io", False):
                self._async_write_queue = asyncio.Queue(maxsize=10000)
                self._async_writer_task = asyncio.create_task(self._async_writer_loop(file_path))
                self._current_file = None  # 异步模式下不使用同步文件
            else:
                self._current_file = open(file_path, "w", encoding=self.encoding, buffering=1)

            self._current_file_path = file_path
            self._current_process = process_name
            self._process_count += 1

            # ✅ 重置级别统计
            self._level_counts = {"DEBUG": 0, "INFO": 0, "WARNING": 0, "ERROR": 0, "CRITICAL": 0}

            self._write_file_header(process_name, metadata)
            return file_path

    def _write_file_header(self, process_name: str, metadata: Optional[Dict[str, Any]] = None):
        """写入文件头."""
        header = f"""{'=' * 80}
AI助手专用日志文件 - {process_name}
{'=' * 80}
流程名称: {process_name}
开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
文件路径: {self._current_file_path}
日志级别: DEBUG及以上所有级别
日志用途: AI助手分析、问题诊断、性能分析

说明：
  1. 本文件包含完整的DEBUG/INFO/WARNING/ERROR/CRITICAL日志
  2. Terminal输出经过简化，仅显示关键节点
  3. 本文件提供完整上下文，供AI助手深度分析
  4. 异常时包含完整堆栈信息
  5. 实时写入，确保崩溃时可追溯
"""
        if metadata:
            header += "\n流程元数据:\n"
            for key, value in metadata.items():
                header += f"  - {key}: {value}\n"

        header += f"\n{'=' * 80}\n\n"

        if getattr(self, "_use_async_io", False) and self._async_write_queue:
            # 异步写入
            try:
                self._async_write_queue.put_nowait(header)
            except asyncio.QueueFull:
                # 队列满时降级到同步写入
                self._async_write_sync(header)
        elif self._current_file:
            # 同步写入
            self._current_file.write(header)
            self._current_file.flush()

    def end_process(self, success: bool = True, summary: Optional[str] = None):
        """结束流程."""
        with self._lock:
            if not self._current_file_path:
                return

            footer = f"""
{'=' * 80}
流程结束 - {self._current_process}
{'=' * 80}
结束时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
执行结果: {'成功' if success else '失败'}
"""
            if summary:
                footer += f"\n执行摘要:\n{summary}\n"

            # ✅ 显示各级别日志统计
            footer += f"\n日志统计:\n"
            footer += f"  - 总日志条数: {self._total_logs}\n"
            footer += f"  - DEBUG: {self._level_counts['DEBUG']} 条\n"
            footer += f"  - INFO: {self._level_counts['INFO']} 条\n"
            footer += f"  - WARNING: {self._level_counts['WARNING']} 条\n"
            footer += f"  - ERROR: {self._level_counts['ERROR']} 条\n"
            footer += f"  - CRITICAL: {self._level_counts['CRITICAL']} 条\n"

            footer += f"\n{'=' * 80}\n"

            if getattr(self, "_use_async_io", False) and self._async_write_queue:
                # 🔧 修复：异步写入时，不等待队列清空，直接关闭
                # 原因：end_process可能在非asyncio线程中调用，无法使用run_until_complete
                try:
                    self._async_write_queue.put_nowait(footer)
                    # 不等待队列清空，让异步写入任务自然完成
                    # 关闭文件时会自动处理剩余的队列内容
                except Exception:
                    # 降级到同步写入
                    self._async_write_sync(footer)
            elif self._current_file:
                self._current_file.write(footer)
                self._current_file.flush()

            self._close_current_file()

            # 异步压缩旧日志（不阻塞）
            if self._compression_enabled:
                try:
                    asyncio.create_task(self._compress_old_logs_async())
                except Exception:
                    # 如果无法创建任务（可能不在asyncio环境中），使用同步方式
                    import threading
                    threading.Thread(target=self._compress_old_logs, daemon=True).start()

    def _close_current_file(self):
        """关闭当前文件."""
        # 停止异步写入协程
        if self._async_writer_task:
            try:
                self._async_writer_task.cancel()
                # 等待任务完成
                try:
                    asyncio.get_event_loop().run_until_complete(self._async_writer_task)
                except Exception:
                    pass
            except Exception:
                pass
            finally:
                self._async_writer_task = None
                self._async_write_queue = None

        # 关闭同步文件
        if self._current_file:
            try:
                self._current_file.flush()
                self._current_file.close()
            except Exception:
                pass
            finally:
                self._current_file = None
                self._current_file_path = None
                self._current_process = None

    async def _async_writer_loop(self, file_path: Path):
        """异步写入循环."""
        if not getattr(self, "_compat_aopen", None) or not self._async_write_queue:
            return
        try:
            compat_aopen = getattr(self, "_compat_aopen", None)
            if not compat_aopen:
                return
            # aopen默认使用二进制模式，需要手动编码
            async with await compat_aopen(file_path, "ab") as f:
                while True:
                    try:
                        # 等待日志消息，超时1秒
                        message = await asyncio.wait_for(self._async_write_queue.get(), timeout=1.0)
                        # 将字符串编码为字节
                        message_bytes = message.encode(self.encoding)
                        await f.write(message_bytes)
                        await f.flush()
                        if self._async_write_queue:
                            self._async_write_queue.task_done()
                    except asyncio.TimeoutError:
                        # 超时继续循环，检查是否需要退出
                        continue
                    except asyncio.CancelledError:
                        # 任务被取消，退出循环
                        break
                    except Exception as e:
                        # 写入失败，记录错误但不中断
                        logger.error(f"❌ [AILogFileHandler] 异步写入失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
        except Exception as e:
            logger.critical(f"🔥 [AILogFileHandler] 异步写入循环失败: {e}", exc_info=True, extra={"log_type": "ALERT"})

    def _async_write_sync(self, message: str):
        """异步写入降级到同步写入."""
        if not self._current_file_path:
            return
        try:
            with open(self._current_file_path, "a", encoding=self.encoding) as f:
                f.write(message)
                f.flush()
        except Exception:
            pass

    async def _wait_queue_empty(self):
        """等待队列清空."""
        if self._async_write_queue:
            await self._async_write_queue.join()

    def emit(self, record: logging.LogRecord):
        """处理日志记录."""
        with self._lock:
            if not self._current_file_path:
                return

            try:
                # ✅ 统计日志级别
                level_name = logging.getLevelName(record.levelno)
                if level_name in self._level_counts:
                    self._level_counts[level_name] += 1

                # ✅ 为不同级别添加视觉标识
                level_markers = {
                    logging.DEBUG: "🔍",
                    logging.INFO: "ℹ️",
                    logging.WARNING: "⚠️",
                    logging.ERROR: "❌",
                    logging.CRITICAL: "🔥",
                }
                marker = level_markers.get(record.levelno, "")

                msg = self.format(record)

                # ✅ 为WARNING及以上级别添加分隔线
                if record.levelno >= logging.WARNING:
                    msg = f"\n{'─' * 80}\n{marker} {msg}\n{'─' * 80}"
                else:
                    msg = f"{marker} {msg}"

                # ✅ 异常信息特殊处理
                if record.exc_info:
                    import traceback

                    exc_text = "".join(traceback.format_exception(*record.exc_info))
                    msg += f"\n\n异常堆栈跟踪:\n{exc_text}\n{'═' * 80}"
                elif hasattr(record, "exc_text") and record.exc_text:
                    # 如果有exc_text字段（介 UnifiedLogRecord 传递）
                    msg += f"\n\n异常堆栈跟踪:\n{record.exc_text}\n{'═' * 80}"

                message_with_newline = msg + "\n"

                # 根据模式选择写入方式
                if getattr(self, "_use_async_io", False) and self._async_write_queue:
                    # 异步写入
                    try:
                        self._async_write_queue.put_nowait(message_with_newline)
                    except asyncio.QueueFull:
                        # 队列满时降级到同步写入
                        self._async_write_sync(message_with_newline)
                elif self._current_file:
                    # 同步写入
                    self._current_file.write(message_with_newline)
                    self._current_file.flush()

                self._total_logs += 1
            except Exception as e:
                logger.error(f"❌ [AILogFileHandler] 日志写入失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})

    def get_current_file_path(self) -> Optional[Path]:
        """获取当前日志文件路径."""
        with self._lock:
            return self._current_file_path

    def get_current_process(self) -> Optional[str]:
        """获取当前活动的进程名称."""
        with self._lock:
            return self._current_process

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息."""
        with self._lock:
            return {
                "process_count": self._process_count,
                "total_logs": self._total_logs,
                "level_counts": self._level_counts.copy(),
                "current_process": self._current_process,
                "current_file": str(self._current_file_path) if self._current_file_path else None,
            }

    def _should_compress(self, file_path: Path) -> bool:
        """判断文件是否需要压缩."""
        if not file_path.exists():
            return False

        # 检查文件大小
        file_size_mb = file_path.stat().st_size / (1024 * 1024)
        if file_size_mb >= self._compression_size_threshold_mb:
            return True

        # 检查文件年龄
        file_age = datetime.now() - datetime.fromtimestamp(file_path.stat().st_mtime)
        if file_age.days >= self._compression_age_days:
            return True

        return False

    def _get_old_log_files(self) -> List[Path]:
        """获取需要压缩的日志文件列表."""
        if not self.base_dir.exists():
            return []

        log_files = []
        for file_path in self.base_dir.iterdir():
            # 只处理.log文件，跳过已压缩的.gz文件
            if file_path.suffix == ".log" and self._should_compress(file_path):
                log_files.append(file_path)

        return log_files

    def _compress_old_logs(self):
        """压缩旧的日志文件（同步版本）."""
        try:
            old_files = self._get_old_log_files()
            for file_path in old_files:
                try:
                    # 压缩文件
                    gz_path = file_path.with_suffix(".log.gz")
                    with open(file_path, "rb") as f_in:
                        with gzip.open(gz_path, "wb") as f_out:
                            f_out.writelines(f_in)

                    # 删除原文件
                    file_path.unlink()
                except Exception as e:
                    # 压缩失败不影响主流程，只记录错误
                    logger.warning(f"⚠️ [AILogFileHandler] 压缩日志文件失败 {file_path}: {e}", extra={"log_type": "SYSTEM"})
        except Exception as e:
            logger.warning(f"⚠️ [AILogFileHandler] 压缩旧日志失败: {e}", extra={"log_type": "SYSTEM"})

    async def _compress_old_logs_async(self):
        """压缩旧的日志文件（异步版本）."""
        try:
            old_files = self._get_old_log_files()
            for file_path in old_files:
                try:
                    # 异步压缩文件
                    gz_path = file_path.with_suffix(".log.gz")
                    with open(file_path, "rb") as f_in:
                        with gzip.open(gz_path, "wb") as f_out:
                            f_out.writelines(f_in)

                    # 删除原文件
                    file_path.unlink()
                except Exception as e:
                    # 压缩失败不影响主流程，只记录错误
                    logger.warning(f"⚠️ [AILogFileHandler] 压缩日志文件失败 {file_path}: {e}", extra={"log_type": "SYSTEM"})
        except Exception as e:
            logger.warning(f"⚠️ [AILogFileHandler] 压缩旧日志失败: {e}", extra={"log_type": "SYSTEM"})

    def set_compression_config(self, enabled: bool = True, size_threshold_mb: int = 10, age_days: int = 7):
        """设置日志压缩配置."""
        self._compression_enabled = enabled
        self._compression_size_threshold_mb = size_threshold_mb
        self._compression_age_days = age_days

    def close(self):
        """关闭Handler."""
        with self._lock:
            self._close_current_file()
        super().close()


# =============================================================================
# Part 6: 进度节流器
# =============================================================================


class ProgressThrottler:
    """进度日志节流器（500ms聚合窗口）."""

    def __init__(self, interval_ms: int = 500):
        """初始化节流器."""
        self.interval_ms = interval_ms
        self._last_emit_time = 0
        self._pending_record: Optional[UnifiedLogRecord] = None
        self._pending_count = 0

    def add(self, record: UnifiedLogRecord):
        """添加进度记录."""
        self._pending_record = record
        self._pending_count += 1

    def get_if_ready(self) -> Optional[UnifiedLogRecord]:
        """检查是否可以发送."""
        current_time = time.time() * 1000
        if current_time - self._last_emit_time >= self.interval_ms:
            if self._pending_record:
                result = self._pending_record
                if result.details is None:
                    result.details = {}
                result.details["_throttled_count"] = self._pending_count

                self._pending_record = None
                self._pending_count = 0
                self._last_emit_time = current_time
                return result
        return None

    def has_pending(self) -> bool:
        """是否有待发送记录."""
        return self._pending_record is not None


# =============================================================================
# Part 7: LoggingHub核心类
# =============================================================================


class LoggingHub(logging.Handler):
    """统一日志中心（拦截所有日志并按规则分发）."""

    def __init__(self):
        """初始化LoggingHub."""
        super().__init__()
        self.setLevel(logging.DEBUG)

        # 外部依赖
        self.event_engine: Optional[EventEngine] = None
        self.db_manager: Optional[Any] = None

        # 托管Handler
        self._console_handler: Optional[logging.StreamHandler] = None
        self._file_handler: Optional[logging.FileHandler] = None
        self._ai_log_handler: Optional[AILogFileHandler] = None

        # 控制台输出类型配置
        self._console_enabled_types: set = {
            LogType.STAGE_NODE,
            LogType.NOTIFICATION,
            LogType.ALERT,
        }

        # 节流器
        self._throttler = ProgressThrottler(interval_ms=500)

        # 有序日志队列（启动阶段使用）
        self._ordered_log_queue: Optional[Any] = None
        self._sequence_counter = 0
        self._sequence_lock = RLock()
        self._emit_lock = RLock()

        # 路由引擎
        try:
            self._routing_engine = RoutingRuleEngine()
            if not self._routing_engine.validate_config():
                logger.critical("🔥 [LoggingHub] 路由规则配置验证失败", extra={"log_type": "ALERT"})
        except Exception as e:
            logger.critical(f"🔥 [LoggingHub] 路由引擎初始化失败: {e}", exc_info=True, extra={"log_type": "ALERT"})
            self._routing_engine = None

        # 统计
        self._total_logs = 0
        self._throttled_logs = 0
        self._db_writes = 0
        self._console_writes = 0
        self._file_writes = 0
        self._ai_log_writes = 0

        # 性能监控指标
        self._emit_count = 0
        self._emit_duration_sum = 0.0
        self._max_emit_duration = 0.0
        self._dropped_logs = 0

        # 递归检测
        self._in_emit = False

        # 异步日志支持
        self._async_mode = False
        self._async_log_queue: Optional[asyncio.Queue] = None
        self._async_worker_task: Optional[asyncio.Task] = None

        # 数据库批量写入
        self._db_batch_cache: List[Dict] = []
        self._db_batch_size = 10
        self._db_last_flush = time.time()
        self._db_flush_interval = 5.0

        # 错误日志文件
        self._error_log_file: Optional[logging.FileHandler] = None
        self._error_count = 0
        self._last_error_time: Optional[datetime] = None
        self._init_error_log_file()

    def _init_error_log_file(self):
        """初始化错误日志文件."""
        try:
            error_log_dir = Path("logs/ai")
            error_log_dir.mkdir(parents=True, exist_ok=True)
            error_log_path = error_log_dir / "logging_errors.log"
            self._error_log_file = logging.FileHandler(error_log_path, mode="a", encoding="utf-8")
            self._error_log_file.setLevel(logging.ERROR)
            self._error_log_file.setFormatter(
                logging.Formatter(
                    "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
        except Exception:
            # 错误日志文件初始化失败不影响主功能
            self._error_log_file = None

    def _log_error_to_file(self, error_type: str, error_message: str, exc_info=None):
        """记录错误到错误日志文件."""
        if not self._error_log_file:
            return

        try:
            self._error_count += 1
            self._last_error_time = datetime.now()

            # 创建错误日志记录（避免无限递归，不通过LoggingHub）
            error_record = logging.LogRecord(
                name="LoggingHub.Error",
                level=logging.ERROR,
                pathname="",
                lineno=0,
                msg=f"[{error_type}] {error_message}",
                args=(),
                exc_info=exc_info,
            )
            error_record.created = time.time()
            self._error_log_file.emit(error_record)
            self._error_log_file.flush()
        except Exception:
            # 错误日志记录失败不影响主功能
            pass

    def set_event_engine(self, event_engine: EventEngine):
        """注入EventEngine."""
        self.event_engine = event_engine

    def set_db_manager(self, db_manager: Any):
        """注入数据库管理器."""
        self.db_manager = db_manager

    def set_console_handler(self, handler: logging.StreamHandler):
        """注入控制台Handler."""
        self._console_handler = handler

    def set_file_handler(self, handler: logging.FileHandler):
        """注入文件Handler."""
        self._file_handler = handler

    def set_ai_log_handler(self, handler: AILogFileHandler):
        """注入AI日志Handler."""
        self._ai_log_handler = handler

    def configure_console_output(self, enabled_types: set):
        """配置控制台输出的日志类型."""
        self._console_enabled_types = enabled_types

    def set_ordered_log_queue(self, ordered_queue: Any):
        """设置有序日志队列（启动阶段使用）

        Args:
            ordered_queue: OrderedLogQueue实例
        """
        self._ordered_log_queue = ordered_queue

        # 设置输出回调
        if ordered_queue:
            ordered_queue.set_output_callback(self._output_ordered_log)

    def start_async_worker(self, queue_size: int = 10000):
        """启动异步日志worker."""
        if self._async_worker_task:
            return  # 已经启动

        try:
            self._async_log_queue = asyncio.Queue(maxsize=queue_size)
            self._async_worker_task = asyncio.create_task(self._async_worker_loop())
            self._async_mode = True
        except Exception as e:
            logger.error(f"❌ [LoggingHub] 启动异步worker失败: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
            self._async_mode = False

    def stop_async_worker(self):
        """停止异步日志worker."""
        if self._async_worker_task:
            try:
                self._async_worker_task.cancel()
                try:
                    asyncio.get_event_loop().run_until_complete(self._async_worker_task)
                except Exception:
                    pass
            except Exception:
                pass
            finally:
                self._async_worker_task = None
                self._async_log_queue = None
                self._async_mode = False

    async def async_emit(self, record: logging.LogRecord) -> None:
        """异步日志入口."""
        if not self._async_mode or not self._async_log_queue:
            # 降级到同步emit
            self.emit(record)
            return

        try:
            await self._async_log_queue.put(record)
        except asyncio.QueueFull:
            # 队列满时丢弃日志并记录
            self._dropped_logs += 1

    async def _async_worker_loop(self):
        """异步日志处理循环."""
        if not self._async_log_queue:
            return
        while True:
            try:
                # 等待日志记录，超时1秒
                record = await asyncio.wait_for(self._async_log_queue.get(), timeout=1.0)
                # 同步处理日志（避免重复emit逻辑）
                self._process_log_record_sync(record)
                if self._async_log_queue:
                    self._async_log_queue.task_done()
            except asyncio.TimeoutError:
                # 超时继续循环
                continue
            except asyncio.CancelledError:
                # 任务被取消，退出循环
                break
            except Exception as e:
                # 处理失败，记录错误
                self._log_error_to_file(
                    "AsyncWorkerError",
                    f"异步日志处理失败: {str(e)}",
                    exc_info=(type(e), e, e.__traceback__),
                )

    def _process_log_record_sync(self, record: logging.LogRecord):
        """同步处理日志记录（内部方法，避免递归）."""
        try:
            if hasattr(record, "_unified_hub_processed"):
                return

            setattr(record, "_unified_hub_processed", True)

            if self._should_skip(record):
                return

            self._total_logs += 1
            unified_record = self._convert_to_unified(record)
            targets = self._get_targets(unified_record)
            self._dispatch(targets, unified_record)
            self._check_throttler()
            self._maybe_flush_db_batch()
        except Exception:
            pass

    def _output_ordered_log(self, record: UnifiedLogRecord):
        """输出有序日志（回调函数）

        Args:
            record: UnifiedLogRecord实例
        """
        # 输出到Terminal
        self._to_console_direct(record)

        # 输出到AI日志文件
        if self._ai_log_handler:
            self._to_ai_log_file(record)

    def _to_console_direct(self, record: UnifiedLogRecord):
        """直接输出到控制台（不经过有序队列）

        Args:
            record: UnifiedLogRecord实例
        """
        if not self._console_handler:
            return

        log_record = logging.LogRecord(
            name=record.logger_name,
            level=record.level,
            pathname=record.filename,
            lineno=record.line,
            msg=record.message,
            args=(),
            exc_info=None,
        )
        log_record.created = record.timestamp.timestamp()
        self._console_handler.emit(log_record)
        self._console_writes += 1

    def emit(self, record: logging.LogRecord) -> None:
        """拦截日志输出."""
        # 如果启用了异步模式，尝试异步处理
        if self._async_mode and self._async_log_queue:
            try:
                # 尝试非阻塞放入队列
                self._async_log_queue.put_nowait(record)
                return  # 成功放入队列，异步处理
            except asyncio.QueueFull:
                # 队列满时降级到同步处理
                self._dropped_logs += 1
            except Exception:
                # 其他异常也降级到同步处理
                pass

        # 同步处理模式
        emit_start = time.perf_counter()
        try:
            if self._in_emit:
                return

            if hasattr(record, "_unified_hub_processed"):
                return

            self._in_emit = True
            setattr(record, "_unified_hub_processed", True)

            if self._should_skip(record):
                return

            self._total_logs += 1
            self._emit_count += 1
            unified_record = self._convert_to_unified(record)
            targets = self._get_targets(unified_record)
            self._dispatch(targets, unified_record)
            self._check_throttler()
            self._maybe_flush_db_batch()

            # 记录emit耗时
            emit_duration = time.perf_counter() - emit_start
            self._emit_duration_sum += emit_duration
            if emit_duration > self._max_emit_duration:
                self._max_emit_duration = emit_duration

        except RecursionError as e:
            self._log_error_to_file(
                "RecursionError",
                f"日志处理递归错误: {str(e)}",
                exc_info=(type(e), e, e.__traceback__),
            )
        except Exception as e:
            self._log_error_to_file(
                "EmitError",
                f"日志处理异常: {str(e)}, logger={record.name}, level={record.levelno}",
                exc_info=(type(e), e, e.__traceback__),
            )
        finally:
            self._in_emit = False

    def _should_skip(self, record: logging.LogRecord) -> bool:
        """判断是否应跳过.

        注意：此方法仅用于防止无限递归和过滤系统内部日志，
        不应该在这里过滤业务日志！业务日志的过滤应该由路由规则控制。
        """
        # 防止日志系统自身的日志造成无限递归
        if record.name.startswith("backend.infrastructure.system_vnpy.unified_log_system"):
            return True
        if "log_manager" in record.name.lower():
            return True

        # ✅ 移除DEBUG过滤逻辑 - 让路由规则决定DEBUG日志的去向
        # AI日志需要完整的DEBUG信息，不应该在这里过滤
        # Terminal输出的过滤由_to_console中的console_enabled_types控制

        return False

    def _convert_to_unified(self, record: logging.LogRecord) -> UnifiedLogRecord:
        """转换为UnifiedLogRecord."""
        exception_text = ""
        if record.exc_info:
            import traceback

            exception_text = "".join(traceback.format_exception(*record.exc_info))

        log_type = self._classify_log_type(record)
        details = {}
        if hasattr(record, "__dict__"):
            for key, value in record.__dict__.items():
                if key not in _EXCLUDED_FIELDS:
                    details[key] = value

        return UnifiedLogRecord(
            type=log_type,
            level=record.levelno,
            module=record.module,
            message=record.getMessage(),
            details=details if details else None,
            timestamp=datetime.fromtimestamp(record.created),
            logger_name=record.name,
            function=record.funcName,
            line=record.lineno,
            filename=record.filename,
            thread=record.thread if record.thread is not None else 0,
            thread_name=(
                record.threadName if hasattr(record, "threadName") and record.threadName else ""
            ),
            exception=exception_text,
        )

    @lru_cache(maxsize=1000)
    def _classify_log_type_cached(self, logger_name_lower: str, message_lower: str, levelno: int, log_type_attr_str: Optional[str]) -> LogType:
        """缓存的日志类型分类（辅助方法）."""
        # 优先检查extra参数中的log_type（显式指定）
        if log_type_attr_str:
            try:
                log_type_str = log_type_attr_str.upper()
                if log_type_str == "STAGE_NODE":
                    return LogType.STAGE_NODE
                elif log_type_str == "PROGRESS":
                    return LogType.PROGRESS
                elif log_type_str == "NOTIFICATION":
                    return LogType.NOTIFICATION
                elif log_type_str == "ALERT":
                    return LogType.ALERT
                elif log_type_str == "USER_FEEDBACK":
                    return LogType.USER_FEEDBACK
                elif log_type_str == "DEBUG":
                    return LogType.DEBUG
                elif log_type_str == "SYSTEM":
                    return LogType.SYSTEM
            except Exception:
                pass

        # 流程节点（严格模式）
        if ".stage" in logger_name_lower:
            return LogType.STAGE_NODE

        if levelno == logging.INFO:
            stage_identifiers = ["📍", "阶段", "流程", "步骤", "stage", "phase", "step"]
            status_words = [
                "开始", "完成", "结束", "启动", "进入",
                "start", "complete", "finish", "end",
            ]
            has_stage_id = any(word in message_lower for word in stage_identifiers)
            has_status = any(word in message_lower for word in status_words)
            if has_stage_id and has_status and "%" not in message_lower and "进度" not in message_lower:
                return LogType.STAGE_NODE

        # 告警
        if "alert" in logger_name_lower or "monitor" in logger_name_lower:
            if levelno >= logging.WARNING:
                return LogType.ALERT

        # 进度
        if "download" in logger_name_lower or "progress" in logger_name_lower:
            if "进度" in message_lower or "%" in message_lower or "progress" in message_lower:
                return LogType.PROGRESS

        if "quality" in logger_name_lower or "scan" in logger_name_lower:
            if "扫描" in message_lower or "%" in message_lower:
                return LogType.PROGRESS

        # 通知（严格）
        if levelno == logging.INFO:
            notification_markers = [
                "✅ 任务完成", "✅ 下载完成", "✅ 扫描完成", "✅ 验证完成",
                "download completed", "scan completed", "task completed",
            ]
            is_notification_logger = "notification" in logger_name_lower or "notifier" in logger_name_lower
            import re
            task_completion_pattern = re.compile(
                r"(完成|已完成|finished|completed)\s*\d+\s*(个|项|条|次)", re.IGNORECASE
            )
            has_completion_report = task_completion_pattern.search(message_lower) is not None

            if (
                is_notification_logger
                or has_completion_report
                or any(marker in message_lower for marker in notification_markers)
            ):
                return LogType.NOTIFICATION

        # DEBUG
        if levelno == logging.DEBUG:
            return LogType.DEBUG

        return LogType.SYSTEM

    def _classify_log_type(self, record: logging.LogRecord) -> LogType:
        """根据logger名称和消息判断日志类型."""
        # 优先检查extra参数中的log_type（显式指定）
        log_type_attr = getattr(record, "log_type", None)
        log_type_attr_str = None
        if log_type_attr is not None:
            # 先尝试直接转换（LogType枚举）
            if isinstance(log_type_attr, LogType):
                return log_type_attr
            elif isinstance(log_type_attr, str):
                log_type_attr_str = log_type_attr

        logger_name = record.name.lower()
        message = record.getMessage().lower()

        # 使用缓存的分类方法
        return self._classify_log_type_cached(logger_name, message, record.levelno, log_type_attr_str)

    def _get_targets(self, record: UnifiedLogRecord) -> List[str]:
        """获取路由目标."""
        if self._routing_engine:
            try:
                return self._routing_engine.route(record)
            except Exception:
                pass

        # 回退：简单规则
        if record.level >= logging.WARNING:
            return ["file", "console", "database"]
        else:
            return ["file"]

    def _dispatch(self, targets: List[str], record: UnifiedLogRecord):
        """分发日志."""
        for target in targets:
            try:
                if target == "console":
                    self._to_console(record)
                elif target in ("file", "logger_file"):
                    self._to_logger_file(record)
                elif target == "ai_file":
                    self._to_ai_log_file(record)
                elif target == "database":
                    self._to_database_batched(record)
                elif target == "event":
                    self._to_event(record)
                elif target == "event_throttled":
                    self._to_event_throttled(record)
                elif target == "ui_statusbar":
                    self._to_ui_statusbar(record)
                elif target == "ui_dialog":
                    self._to_ui_dialog(record)
            except Exception:
                pass

    def _to_console(self, record: UnifiedLogRecord):
        """输出到控制台（Terminal）

        输出规则：
        1. 特定类型的日志（STAGE_NODE, NOTIFICATION, ALERT）
        2. WARNING及以上级别的日志（WARNING, ERROR, CRITICAL）

        # 优化原因：统一Terminal日志输出规则，减少刷屏
        # 问题：原先只输出特定类型，导致WARNING/ERROR不显示在Terminal，用户无法及时发现问题
        # 解决：添加日志级别判断，WARNING及以上级别自动输出到Terminal
        # 效果：
        #   - Terminal保持简洁：只显示流程关键节点 + 警告错误
        #   - AI日志文件保持详细：包含所有INFO及以上日志
        #   - 用户体验改善：重要问题能立即在Terminal看到

        # 🆕 启动阶段增强：如果启用了有序日志队列，则通过队列输出（确保顺序）
        """
        if not self._console_handler:
            return

        # 检查是否应该输出到console
        # 优化原因：双重过滤机制 - 既按类型过滤，也按级别过滤
        should_output = (
            record.type in self._console_enabled_types  # 特定类型（流程节点、通知、告警）
            or record.level >= logging.WARNING  # WARNING及以上级别（警告、错误、严重）
        )

        if not should_output:
            return

        # 🆕 如果启用了有序日志队列（启动阶段），则通过队列输出
        if self._ordered_log_queue and self._is_startup_phase():
            # 获取序列号
            with self._sequence_lock:
                sequence = self._sequence_counter
                self._sequence_counter += 1

            # 添加到有序队列
            self._ordered_log_queue.add_log(record, sequence)
        else:
            # 直接输出（非启动阶段或不使用有序队列）
            self._to_console_direct(record)

    def _is_startup_phase(self) -> bool:
        """判断是否处于启动阶段

        Returns:
            bool: 是否处于启动阶段
        """
        if not self._routing_engine:
            return False

        current_stage = getattr(self._routing_engine, "current_stage", None)
        startup_stages = ["startup", "logging_init", "qt_init", "backend_init", "ui_init", "vnpy_core", "cache_validation_step1", "cache_validation_step2", "cache_validation_step3", "cache_validation_step4", "cache_validation_step5", "cache_validation_step6", "cache_validation_step7", "cache_validation_step8"]
        return current_stage in startup_stages

    def _to_logger_file(self, record: UnifiedLogRecord):
        """输出到文件."""
        if not self._file_handler:
            return

        # ✅ 构造完整的LogRecord，包括异常信息
        exc_info = None
        if record.exception:
            # 如果有异常文本，设置 exc_text 字段
            exc_info = None  # 保持None，但设置 exc_text

        log_record = logging.LogRecord(
            name=record.logger_name,
            level=record.level,
            pathname=record.filename,
            lineno=record.line,
            msg=record.message,
            args=(),
            exc_info=exc_info,
        )
        log_record.created = record.timestamp.timestamp()
        log_record.funcName = record.function

        # ✅ 添加异常信息
        if record.exception:
            log_record.exc_text = record.exception

        self._file_handler.emit(log_record)
        self._file_writes += 1

    def _to_ai_log_file(self, record: UnifiedLogRecord):
        """输出到AI日志."""
        # 排除自动延迟测试的日志（每10秒一次，不需要生成AI日志文件）
        # 1. 检查日志消息中是否包含自动测试标记
        if "[LATENCY-AUTO]" in record.message:
            return

        # 2. 排除自动测试循环相关的函数日志
        if record.function in ("_test_single_latency", "_auto_test_loop", "start_auto_test"):
            if "monitor_system" in record.logger_name or "monitor_process" in record.logger_name:
                return

        # 3. 排除初始化服务器时的日志（启动时一次性测试，不需要AI日志）
        if (
            "[LATENCY-INIT]" in record.message
            or "[LATENCY-CACHE]" in record.message
            or "[LATENCY-FALLBACK]" in record.message
        ):
            return

        # 4. 排除自动测试中调用网络测速产生的日志
        # 手动测试会使用ai_log_process上下文管理器，会创建独立的AI日志文件
        # 自动测试不会使用ai_log_process，所以网络测速的日志如果是自动测试产生的，
        # 应该被排除。我们通过检查AILogFileHandler是否有活动的process来判断
        # 注意：NetworkSpeedTester已集成到monitor_system.py，日志名称可能包含SPEEDTEST标记
        if "speedtest_native" in record.logger_name or "SPEEDTEST" in record.message:
            # 检查当前是否有活动的AI日志进程（手动测试会在ai_log_process中）
            if self._ai_log_handler:
                current_process = self._ai_log_handler.get_current_process()
                # 如果没有活动的process，说明不在ai_log_process上下文中，可能是自动测试
                # 排除这些日志（手动测试会设置process_name）
                if not current_process:
                    return

        if not self._ai_log_handler:
            return

        # ✅ 构造完整的LogRecord，包括异常信息
        exc_info = None
        if record.exception:
            # 如果有异常文本，设置 exc_text 字段
            exc_info = None  # 保持None，但设置 exc_text

        log_record = logging.LogRecord(
            name=record.logger_name,
            level=record.level,
            pathname=record.filename,
            lineno=record.line,
            msg=record.message,
            args=(),
            exc_info=exc_info,
        )
        log_record.created = record.timestamp.timestamp()
        log_record.funcName = record.function

        # ✅ 添加异常信息
        if record.exception:
            log_record.exc_text = record.exception

        self._ai_log_handler.emit(log_record)
        self._ai_log_writes += 1

    def _to_database_batched(self, record: UnifiedLogRecord):
        """写入数据库（批量）."""
        if record.level < logging.WARNING or not self.db_manager:
            return

        self._db_batch_cache.append(
            {
                "timestamp": record.timestamp.isoformat(),
                "level": logging.getLevelName(record.level),
                "module": record.module,
                "message": record.message,
                "extra": (
                    json.dumps(
                        {
                            "logger_name": record.logger_name,
                            "function": record.function,
                            "line": record.line,
                            "exception": record.exception,
                            "details": record.details,
                        },
                        ensure_ascii=False,
                    )
                    if record.exception or record.details
                    else None
                ),
            }
        )

        if len(self._db_batch_cache) >= self._db_batch_size:
            self._flush_db_batch()

    def _flush_db_batch(self):
        """刷新数据库批量缓存."""
        if not self._db_batch_cache or not self.db_manager:
            self._db_batch_cache.clear()
            return

        try:
            for log_data in self._db_batch_cache:
                self.db_manager.execute_update(
                    "INSERT INTO system_logs (timestamp, level, module, message, extra) VALUES (?, ?, ?, ?, ?)",
                    (
                        log_data["timestamp"],
                        log_data["level"],
                        log_data["module"],
                        log_data["message"],
                        log_data["extra"],
                    ),
                )
            self._db_writes += len(self._db_batch_cache)
            self._db_batch_cache.clear()
            self._db_last_flush = time.time()
        except Exception:
            self._db_batch_cache.clear()

    def _maybe_flush_db_batch(self):
        """定期刷新."""
        if time.time() - self._db_last_flush >= self._db_flush_interval:
            self._flush_db_batch()

    def _to_event(self, record: UnifiedLogRecord):
        """发送到EventEngine."""
        if not self.event_engine:
            return

        event_type_map = {
            LogType.SYSTEM: EVENT_LOG_SYSTEM,
            LogType.PROGRESS: EVENT_LOG_PROGRESS,
            LogType.NOTIFICATION: EVENT_LOG_NOTIFICATION,
            LogType.ALERT: EVENT_LOG_ALERT,
        }
        event_type = event_type_map.get(record.type, EVENT_LOG_SYSTEM)
        event_data = {
            "type": record.type.value,
            "level": logging.getLevelName(record.level),
            "module": record.module,
            "message": record.message,
            "details": record.details,
            "timestamp": record.timestamp.isoformat(),
        }
        event = Event(event_type, event_data)
        self.event_engine.put(event)

    def _to_event_throttled(self, record: UnifiedLogRecord):
        """节流发送."""
        self._throttler.add(record)
        self._throttled_logs += 1

    def _check_throttler(self):
        """检查节流器."""
        pending = self._throttler.get_if_ready()
        if pending:
            self._to_event(pending)

    def _to_ui_statusbar(self, record: UnifiedLogRecord):
        """发送到状态栏."""
        if self.event_engine:
            event_data = {
                "message": record.message,
                "level": logging.getLevelName(record.level),
                "timestamp": record.timestamp.isoformat(),
                "type": record.type.value,
            }
            event = Event(EVENT_UI_STATUSBAR, event_data)
            self.event_engine.put(event)

    def _to_ui_dialog(self, record: UnifiedLogRecord):
        """发送到UI弹窗."""
        if self.event_engine:
            event_data = {
                "title": logging.getLevelName(record.level),
                "message": record.message,
                "details": record.details,
                "timestamp": record.timestamp.isoformat(),
                "exception": record.exception,
            }
            event = Event(EVENT_UI_DIALOG, event_data)
            self.event_engine.put(event)

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息."""
        # 计算平均emit耗时
        avg_emit_duration = (
            self._emit_duration_sum / self._emit_count if self._emit_count > 0 else 0.0
        )

        # 获取队列大小（如果启用了异步日志）
        queue_size = 0
        if hasattr(self, "_async_log_queue") and self._async_log_queue:
            try:
                queue_size = self._async_log_queue.qsize()
            except Exception:
                pass

        stats: Dict[str, Any] = {
            "total_logs": self._total_logs,
            "throttled_logs": self._throttled_logs,
            "console_writes": self._console_writes,
            "file_writes": self._file_writes,
            "ai_log_writes": self._ai_log_writes,
            "db_writes": self._db_writes,
            "db_batch_pending": len(self._db_batch_cache),
            # 性能监控指标
            "performance": {
                "emit_count": self._emit_count,
                "emit_duration_sum_ms": round(self._emit_duration_sum * 1000, 2),
                "max_emit_duration_ms": round(self._max_emit_duration * 1000, 2),
                "avg_emit_duration_ms": round(avg_emit_duration * 1000, 2),
                "queue_size": queue_size,
                "dropped_logs": self._dropped_logs,
            },
            # 错误统计
            "errors": {
                "error_count": self._error_count,
                "last_error_time": self._last_error_time.isoformat() if self._last_error_time else None,
            },
        }

        if self._routing_engine:
            stats["routing_engine"] = self._routing_engine.get_statistics()

        return stats

    def get_current_stage(self) -> str:
        """获取当前阶段."""
        if self._routing_engine:
            return self._routing_engine.current_stage
        return "startup"

    def set_stage(self, stage: str):
        """切换日志阶段."""
        if self._routing_engine:
            self._routing_engine.set_stage(stage)

    def set_run_mode(self, mode: str):
        """切换运行模式."""
        if self._routing_engine:
            self._routing_engine.set_run_mode(mode)

    def reload_routing_rules(self):
        """热更新路由规则."""
        if self._routing_engine:
            self._routing_engine.reload_rules()

    def close(self):
        """关闭LoggingHub."""
        # 停止异步worker
        self.stop_async_worker()

        self._flush_db_batch()
        if self._error_log_file:
            self._error_log_file.close()
        super().close()


# =============================================================================
# Part 8: AI日志上下文管理
# =============================================================================


def start_ai_process(process_name: str, metadata: Optional[Dict[str, Any]] = None) -> Path:
    """开始AI日志流程."""
    handler = get_ai_log_handler()
    file_path = handler.start_process(process_name, metadata)

    logger = logging.getLogger(f"ai.process.{process_name}")
    logger.info(f"🚀 流程开始: {process_name}")
    if metadata:
        logger.info(f"流程元数据: {metadata}")

    return file_path


def end_ai_process(success: bool = True, summary: Optional[str] = None):
    """结束AI日志流程."""
    handler = get_ai_log_handler()

    current_process = handler._current_process
    if current_process:
        logger = logging.getLogger(f"ai.process.{current_process}")
        status = "✅ 成功" if success else "❌ 失败"
        logger.info(f"流程结束: {status}")
        if summary:
            logger.info(f"摘要: {summary}")

    handler.end_process(success, summary)


def get_current_ai_log_file() -> Optional[Path]:
    """获取当前AI日志文件路径."""
    handler = get_ai_log_handler()
    return handler.get_current_file_path()


@contextmanager
def ai_log_process(
    process_name: str, metadata: Optional[Dict[str, Any]] = None, auto_summary: bool = True
):
    """AI日志流程上下文管理器."""
    file_path = start_ai_process(process_name, metadata)

    success = False
    exception_info = None

    try:
        yield file_path
        success = True
    except Exception as e:
        exception_info = e
        raise
    finally:
        summary = None
        if auto_summary:
            if success:
                summary = "流程正常完成"
            elif exception_info:
                summary = f"流程异常终止: {exception_info}"
            else:
                summary = "流程未正常完成"

        end_ai_process(success, summary)


def ai_log_process_decorator(
    process_name: Optional[str] = None,
    metadata_func: Optional[Callable[..., Dict[str, Any]]] = None,
):
    """AI日志流程装饰器."""

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            name = process_name or func.__name__

            metadata = None
            if metadata_func:
                try:
                    metadata = metadata_func(*args, **kwargs)
                except Exception:
                    pass

            with ai_log_process(name, metadata):
                return func(*args, **kwargs)

        return wrapper

    return decorator


class AILogProcess:
    """AI日志流程类（面向对象风格）."""

    def __init__(self, process_name: str):
        """初始化流程."""
        self.process_name = process_name
        self.file_path: Optional[Path] = None
        self._started = False

    def start(self, metadata: Optional[Dict[str, Any]] = None) -> Path:
        """开始流程."""
        if self._started:
            raise RuntimeError(f"流程 {self.process_name} 已经启动")

        self.file_path = start_ai_process(self.process_name, metadata)
        self._started = True
        return self.file_path

    def end(self, success: bool = True, summary: Optional[str] = None):
        """结束流程."""
        if not self._started:
            raise RuntimeError(f"流程 {self.process_name} 尚未启动")

        end_ai_process(success, summary)
        self._started = False

    def __enter__(self):
        """上下文管理器入口."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口."""
        success = exc_type is None
        summary = None if success else f"异常: {exc_val}"
        self.end(success, summary)
        return False


class ProcessNames:
    """预定义的流程名称常量."""

    STARTUP = "startup"
    SHUTDOWN = "shutdown"

    SYMBOL_REFRESH = "symbol_refresh"
    SYMBOL_LOAD = "symbol_load"
    DOWNLOAD_KLINE = "download_kline"
    DOWNLOAD_TICK = "download_tick"
    QUALITY_SCAN = "quality_scan"
    QUALITY_REPAIR = "quality_repair"

    STRATEGY_BACKTEST = "strategy_backtest"
    STRATEGY_OPTIMIZE = "strategy_optimize"
    STRATEGY_DEPLOY = "strategy_deploy"

    TRADING_START = "trading_start"
    TRADING_STOP = "trading_stop"
    ORDER_EXECUTION = "order_execution"

    CONFIG_UPDATE = "config_update"
    DATABASE_BACKUP = "database_backup"
    LOG_CLEANUP = "log_cleanup"

    NETWORK_SPEEDTEST_PING = "network_speedtest_ping"
    NETWORK_SPEEDTEST_BANDWIDTH = "network_speedtest_bandwidth"


# =============================================================================
# Part 9: 全局单例和便捷API
# =============================================================================

_hub_instance: Optional[LoggingHub] = None
_ai_handler_instance: Optional[AILogFileHandler] = None


def get_logging_hub() -> LoggingHub:
    """获取LoggingHub全局单例."""
    global _hub_instance
    if _hub_instance is None:
        _hub_instance = LoggingHub()
    return _hub_instance


def get_ai_log_handler() -> AILogFileHandler:
    """获取AI日志Handler全局单例."""
    global _ai_handler_instance
    if _ai_handler_instance is None:
        _ai_handler_instance = AILogFileHandler()
    return _ai_handler_instance


def get_routing_engine() -> Optional[RoutingRuleEngine]:
    """获取路由引擎实例."""
    hub = get_logging_hub()
    return hub._routing_engine


def log_progress(module: str, message: str, progress: float, **details):
    """记录进度日志（自动节流）."""
    details["progress"] = progress
    logger = logging.getLogger(f"backend.{module}")
    logger.info(message, extra=details)


def notify_complete(module: str, message: str, **details):
    """任务完成通知."""
    logger = logging.getLogger(f"backend.{module}")
    logger.info(message, extra=details)


def alert(severity: str, module: str, message: str, **details):
    """发送告警."""
    logger = logging.getLogger(f"backend.{module}")
    level = getattr(logging, severity.upper(), logging.WARNING)
    logger.log(level, message, extra=details)


def log_system(level: str, module: str, message: str, **details):
    """记录系统日志."""
    logger = logging.getLogger(f"backend.{module}")
    log_level = getattr(logging, level.upper(), logging.INFO)
    logger.log(log_level, message, extra=details)


# =============================================================================
# 导出
# =============================================================================

__all__ = [
    # 数据结构
    "LogType",
    "UnifiedLogRecord",
    # 核心类
    "LoggingHub",
    "RoutingRuleEngine",
    "RuleCache",
    "AILogFileHandler",
    "ProgressThrottler",
    # AI日志流程
    "AILogProcess",
    "ProcessNames",
    # 上下文管理器
    "ai_log_process",
    "ai_log_process_decorator",
    # 流程控制函数
    "start_ai_process",
    "end_ai_process",
    "get_current_ai_log_file",
    # 全局单例
    "get_logging_hub",
    "get_ai_log_handler",
    "get_routing_engine",
    # 事件类型
    "EVENT_LOG_SYSTEM",
    "EVENT_LOG_PROGRESS",
    "EVENT_LOG_NOTIFICATION",
    "EVENT_LOG_ALERT",
    "EVENT_UI_STATUSBAR",
    "EVENT_UI_DIALOG",
    # 便捷API
    "log_progress",
    "notify_complete",
    "alert",
    "log_system",
]
