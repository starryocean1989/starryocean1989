# -*- coding: utf-8 -*-
"""
日志混入类 - 提供标准化的日志记录功能.

为所有服务和组件提供统一的日志记录接口和最佳实践。
"""

import logging
from typing import Any, Dict, Optional


class LoggerMixin:
    """日志记录器混入类.
    
    为类提供标准化的日志记录功能，包括：
    - 自动创建命名日志记录器
    - 标准化的日志输出方法
    - 上下文信息传递
    - 性能日志记录
    
    使用方法:
        class MyService(LoggerMixin):
            def __init__(self):
                super().__init__()
                self.logger.info("服务已创建")
    """
    
    def __init__(self):
        """初始化日志记录器混入."""
        # 创建以类名命名的日志记录器
        self._logger = logging.getLogger(self.__class__.__name__)
    
    @property
    def logger(self) -> logging.Logger:
        """获取日志记录器.
        
        Returns:
            日志记录器实例
        """
        return self._logger
    
    def log_with_context(
        self,
        level: int,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
        exc_info: bool = False
    ) -> None:
        """记录带上下文信息的日志.
        
        Args:
            level: 日志级别（logging.DEBUG, INFO, WARNING, ERROR, CRITICAL）
            message: 日志消息
            extra: 额外的上下文信息
            exc_info: 是否包含异常信息
        """
        log_extra = extra or {}
        self._logger.log(level, message, extra=log_extra, exc_info=exc_info)
    
    def log_performance(
        self,
        operation: str,
        duration_ms: float,
        success: bool = True,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """记录性能日志.
        
        Args:
            operation: 操作名称
            duration_ms: 操作耗时（毫秒）
            success: 操作是否成功
            extra: 额外的上下文信息
        """
        log_extra = extra or {}
        log_extra.update({
            "operation": operation,
            "duration_ms": duration_ms,
            "success": success,
        })
        
        if success:
            message = f"[性能] {operation} 完成，耗时: {duration_ms:.2f}ms"
            self._logger.debug(message, extra=log_extra)
        else:
            message = f"[性能] {operation} 失败，耗时: {duration_ms:.2f}ms"
            self._logger.warning(message, extra=log_extra)
    
    def log_operation_start(self, operation: str, **kwargs) -> None:
        """记录操作开始日志.
        
        Args:
            operation: 操作名称
            **kwargs: 操作参数
        """
        params_str = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
        message = f"[开始] {operation}"
        if params_str:
            message += f" ({params_str})"
        self._logger.info(message)
    
    def log_operation_success(self, operation: str, **kwargs) -> None:
        """记录操作成功日志.
        
        Args:
            operation: 操作名称
            **kwargs: 结果信息
        """
        result_str = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
        message = f"[成功] {operation}"
        if result_str:
            message += f" ({result_str})"
        self._logger.info(message)
    
    def log_operation_failure(
        self,
        operation: str,
        error: Exception,
        **kwargs
    ) -> None:
        """记录操作失败日志.
        
        Args:
            operation: 操作名称
            error: 错误异常
            **kwargs: 错误上下文
        """
        context_str = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
        message = f"[失败] {operation}: {str(error)}"
        if context_str:
            message += f" ({context_str})"
        self._logger.error(message, exc_info=True)
