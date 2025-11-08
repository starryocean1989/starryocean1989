"""
Logging utilities for the application.

This module provides utility functions and classes for consistent logging across the application.
"""

import functools
import logging
import time
from typing import Any, Callable, Dict, Optional, TypeVar, cast

from .logging_system import (
    UnifiedLogRecord,
    log_system,
    log_progress,
    notify_complete,
    alert,
    debug_log,
    stage_node,
)

# Type variable for generic function type
F = TypeVar('F', bound=Callable[..., Any])

def log_execution_time(level: str = 'INFO', log_args: bool = False):
    """Decorator to log the execution time of a function.
    
    Args:
        level: Log level ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
        log_args: Whether to log function arguments
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            module_name = func.__module__.split('.')[-1]
            func_name = func.__name__
            
            # Log function start
            start_time = time.time()
            
            # Log arguments if requested
            if log_args and (args or kwargs):
                arg_str = ', '.join([str(a) for a in args] + [f'{k}={v}' for k, v in kwargs.items()])
                log_system(
                    level, 
                    module_name, 
                    f"{func_name} called with args: {arg_str}",
                    func=func_name,
                    log_type="DEBUG"
                )
            
            try:
                # Call the original function
                result = func(*args, **kwargs)
                
                # Calculate duration
                duration_ms = (time.time() - start_time) * 1000
                
                # Log successful completion
                log_system(
                    level,
                    module_name,
                    f"{func_name} completed in {duration_ms:.2f}ms",
                    func=func_name,
                    duration_ms=duration_ms,
                    log_type="PERFORMANCE"
                )
                
                return result
                
            except Exception as e:
                # Log error with duration
                duration_ms = (time.time() - start_time) * 1000
                alert(
                    "ERROR",
                    module_name,
                    f"{func_name} failed after {duration_ms:.2f}ms: {str(e)}",
                    func=func_name,
                    error_type=type(e).__name__,
                    duration_ms=duration_ms,
                    exc_info=True
                )
                raise
                
        return cast(F, wrapper)
    return decorator


def log_operation(operation: str, level: str = 'INFO'):
    """Decorator to log the start and end of an operation.
    
    Args:
        operation: Name of the operation being performed
        level: Log level ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            module_name = func.__module__.split('.')[-1]
            
            # Log operation start
            log_system(
                level,
                module_name,
                f"Starting {operation}",
                operation=operation,
                status="started"
            )
            
            start_time = time.time()
            
            try:
                # Call the original function
                result = func(*args, **kwargs)
                
                # Calculate duration
                duration_ms = (time.time() - start_time) * 1000
                
                # Log successful completion
                log_system(
                    level,
                    module_name,
                    f"Completed {operation} in {duration_ms:.2f}ms",
                    operation=operation,
                    status="completed",
                    duration_ms=duration_ms
                )
                
                return result
                
            except Exception as e:
                # Log error with duration
                duration_ms = (time.time() - start_time) * 1000
                alert(
                    "ERROR",
                    module_name,
                    f"{operation} failed after {duration_ms:.2f}ms: {str(e)}",
                    operation=operation,
                    status="failed",
                    error_type=type(e).__name__,
                    duration_ms=duration_ms,
                    exc_info=True
                )
                raise
                
        return cast(F, wrapper)
    return decorator


def with_logging_context(**context):
    """Add context to all log messages within the decorated function.
    
    Example:
        @with_logging_context(user_id=123, request_id="abc123")
        def process_request():
            log_system("INFO", "my_module", "Processing request")  # Will include user_id and request_id
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            # Get the logger for the module
            logger = logging.getLogger(func.__module__)
            
            # Create a filter to add context
            class ContextFilter(logging.Filter):
                def filter(self, record):
                    for key, value in context.items():
                        setattr(record, key, value)
                    return True
            
            # Add the filter to the logger
            context_filter = ContextFilter()
            logger.addFilter(context_filter)
            
            try:
                return func(*args, **kwargs)
            finally:
                # Remove the filter when done
                logger.removeFilter(context_filter)
                
        return cast(F, wrapper)
    return decorator


def log_exceptions(level: str = 'ERROR'):
    """Decorator to log exceptions with the application's logging system.
    
    Args:
        level: Log level to use for exceptions
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            module_name = func.__module__.split('.')[-1]
            func_name = func.__name__
            
            try:
                return func(*args, **kwargs)
            except Exception as e:
                alert(
                    level,
                    module_name,
                    f"Unhandled exception in {func_name}: {str(e)}",
                    func=func_name,
                    error_type=type(e).__name__,
                    exc_info=True
                )
                raise
                
        return cast(F, wrapper)
    return decorator


class LoggingContext:
    """Context manager for managing logging context.
    
    Example:
        with LoggingContext(user_id=123, request_id="abc123"):
            log_system("INFO", "my_module", "Processing request")  # Will include user_id and request_id
    """
    
    def __init__(self, **context):
        self.context = context
        self.logger = logging.getLogger()
        self.filters = {}
    
    def __enter__(self):
        # Add context to all log records
        class ContextFilter(logging.Filter):
            def __init__(self, context):
                super().__init__()
                self.context = context
            
            def filter(self, record):
                for key, value in self.context.items():
                    setattr(record, key, value)
                return True
        
        # Create and add filter
        self.filter = ContextFilter(self.context)
        self.logger.addFilter(self.filter)
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # Remove filter
        self.logger.removeFilter(self.filter)
        
        # Log any exception that occurred
        if exc_type is not None:
            alert(
                "ERROR",
                "logging_context",
                f"Exception in logging context: {str(exc_val)}",
                error_type=exc_type.__name__,
                exc_info=(exc_type, exc_val, exc_tb)
            )
        
        return False  # Don't suppress exceptions
