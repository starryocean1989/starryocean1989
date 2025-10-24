# -*- coding: utf-8 -*-
"""
Debug日志装饰器.

功能：
1. 为Debug模块提供增强的日志输出
2. 支持三种详细级别：brief, normal, detailed
3. 与TerminalOutput集成，实现条件输出
"""
import functools
import logging
import traceback
from typing import Any, Callable, Dict, Optional


class DebugLogger:
    """Debug日志记录器."""

    def __init__(self, module_name: str, logger: Optional[logging.Logger] = None):
        """
        初始化Debug日志记录器.

        Args:
            module_name: 模块名称（如 "monitor", "data"）
            logger: 日志记录器（可选）
        """
        self.module_name = module_name
        self.logger = logger or logging.getLogger(module_name)

    def debug_init_step(self, step_name: str, details: Optional[Dict[str, Any]] = None) -> None:
        """
        记录初始化步骤.

        Args:
            step_name: 步骤名称
            details: 详细信息
        """
        from backend.core.terminal_output import print_debug

        self.logger.info("[DEBUG-INIT] %s: %s", self.module_name, step_name)

        if details:
            self.logger.debug("[DEBUG-INIT] %s details: %s", step_name, details)

        # Terminal输出（条件）
        print_debug(
            f"DEBUG-{self.module_name.upper()}",
            f"初始化步骤: {step_name}",
            details=details,
        )

    def debug_method_call(
        self,
        method_name: str,
        args: Optional[tuple] = None,
        kwargs: Optional[dict] = None,
        result: Any = None,
    ) -> None:
        """
        记录方法调用.

        Args:
            method_name: 方法名称
            args: 位置参数
            kwargs: 关键字参数
            result: 返回结果
        """
        details = {}
        if args:
            details["args"] = str(args)[:200]  # 限制长度
        if kwargs:
            details["kwargs"] = str(kwargs)[:200]
        if result is not None:
            details["result"] = str(result)[:200]

        self.logger.debug("[DEBUG-CALL] %s.%s", self.module_name, method_name)

        from backend.core.terminal_output import print_debug

        print_debug(
            f"DEBUG-{self.module_name.upper()}",
            f"方法调用: {method_name}",
            details=details if details else None,
        )

    def debug_exception(
        self,
        operation: str,
        exception: Exception,
        context: Optional[Dict[str, Any]] = None,
        suppress: bool = False,
    ) -> None:
        """
        记录异常.

        Args:
            operation: 操作名称
            exception: 异常对象
            context: 上下文信息
            suppress: 是否抑制异常传播
        """
        exc_details = {
            "exception_type": type(exception).__name__,
            "exception_message": str(exception),
            "traceback": traceback.format_exc()[:500],  # 限制长度
        }

        if context:
            exc_details.update(context)

        self.logger.error(
            "[DEBUG-ERROR] %s: %s 失败 - %s",
            self.module_name,
            operation,
            exception,
            exc_info=not suppress,  # 如果suppress=True，不打印完整堆栈
        )

        from backend.core.terminal_output import print_debug

        print_debug(
            f"DEBUG-{self.module_name.upper()}",
            f"异常: {operation}",
            details=exc_details,
            force_output=True,  # 异常始终输出
        )

    def debug_metric(self, metric_name: str, value: Any, unit: str = "") -> None:
        """
        记录性能指标.

        Args:
            metric_name: 指标名称
            value: 指标值
            unit: 单位
        """
        unit_str = f" {unit}" if unit else ""
        self.logger.info(
            "[DEBUG-METRIC] %s: %s = %s%s", self.module_name, metric_name, value, unit_str
        )

        from backend.core.terminal_output import print_debug

        print_debug(
            f"DEBUG-{self.module_name.upper()}",
            f"性能指标: {metric_name}",
            details={"value": f"{value}{unit_str}"},
        )


def debug_method(detail_level: str = "normal") -> Callable:
    """
    方法级Debug装饰器.

    Args:
        detail_level: 详细级别 ("brief" | "normal" | "detailed")

    Returns:
        装饰器函数

    Usage:
        @debug_method("normal")
        def my_method(self, arg1, arg2):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 获取self（如果是实例方法）
            if args and hasattr(args[0], "__class__"):
                instance = args[0]
                module_name = instance.__class__.__module__.split(".")[-1]
            else:
                module_name = func.__module__.split(".")[-1]

            debug_logger = DebugLogger(module_name)

            # 根据详细级别决定是否记录参数
            if detail_level in ["normal", "detailed"]:
                debug_logger.debug_method_call(func.__name__, args[1:] if args else None, kwargs)
            else:
                debug_logger.debug_method_call(func.__name__)

            try:
                result = func(*args, **kwargs)

                # 记录结果
                if detail_level == "detailed":
                    debug_logger.debug_method_call(func.__name__, result=result)

                return result

            except Exception as e:
                # 记录异常
                debug_logger.debug_exception(func.__name__, e, suppress=False)
                raise

        return wrapper

    return decorator


def debug_exception_handler(operation: str, suppress: bool = False) -> Callable:
    """
    异常处理装饰器.

    Args:
        operation: 操作名称
        suppress: 是否抑制异常（返回None而不是抛出）

    Returns:
        装饰器函数

    Usage:
        @debug_exception_handler("数据加载", suppress=True)
        def load_data(self):
            ...
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # 获取模块名
            if args and hasattr(args[0], "__class__"):
                instance = args[0]
                module_name = instance.__class__.__module__.split(".")[-1]
            else:
                module_name = func.__module__.split(".")[-1]

            debug_logger = DebugLogger(module_name)

            try:
                return func(*args, **kwargs)
            except Exception as e:
                debug_logger.debug_exception(operation, e, suppress=suppress)
                if not suppress:
                    raise
                return None

        return wrapper

    return decorator


# 便捷函数
def get_debug_logger(module_name: str) -> DebugLogger:
    """
    获取Debug日志记录器.

    Args:
        module_name: 模块名称

    Returns:
        DebugLogger实例
    """
    return DebugLogger(module_name)
