"""
Logging configuration for the application.

This module provides a centralized way to configure logging for the application.
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

from .logging_system import (
    LoggingHub,
    EventLogFileHandler,
    get_logging_hub,
    get_event_log_handler,
    get_ordered_log_queue,
    MultiProcessLogCollector,
    setup_logging_system,
)
from .logging_utils import LoggingContext

# Default log format
DEFAULT_LOG_FORMAT = (
    "[%(asctime)s] [%(levelname)-8s] [%(name)-40s] [%(funcName)s:%(lineno)d]\n    %(message)s"
)

# Default date format
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Default log levels for different loggers
DEFAULT_LOG_LEVELS = {
    # Framework loggers
    "backend": logging.INFO,
    "vnpy": logging.WARNING,
    "asyncio": logging.WARNING,
    "aiohttp": logging.WARNING,
    "urllib3": logging.WARNING,
    "requests": logging.WARNING,
    "matplotlib": logging.WARNING,
    "PIL": logging.WARNING,
    "numpy": logging.WARNING,
    "pandas": logging.WARNING,
    # Application loggers
    "data_module": logging.INFO,
    "trading": logging.INFO,
    "strategy": logging.INFO,
    "market_data": logging.INFO,
    "risk_management": logging.INFO,
    "portfolio": logging.INFO,
    "execution": logging.INFO,
    "backtest": logging.INFO,
    "performance": logging.INFO,
    "alert": logging.WARNING,
    "notification": logging.INFO,
    "system": logging.INFO,
    "security": logging.INFO,
}


def configure_logging(
    log_level: Union[str, int] = logging.INFO,
    log_file: Optional[Union[str, Path]] = None,
    log_format: str = DEFAULT_LOG_FORMAT,
    date_format: str = DEFAULT_DATE_FORMAT,
    log_levels: Optional[Dict[str, Union[str, int]]] = None,
    enable_console: bool = True,
    enable_file: bool = True,
    enable_database: bool = False,
    enable_event_engine: bool = True,
    enable_ordered_queue: bool = True,
    enable_multi_process: bool = True,
    event_engine: Optional[Any] = None,
    db_manager: Optional[Any] = None,
) -> LoggingHub:
    """Configure the logging system.

    Args:
        log_level: Default log level
        log_file: Path to the log file
        log_format: Log format string
        date_format: Date format string
        log_levels: Dictionary of logger names to log levels
        enable_console: Whether to enable console logging
        enable_file: Whether to enable file logging
        enable_database: Whether to enable database logging
        enable_event_engine: Whether to enable event engine logging
        enable_ordered_queue: Whether to enable ordered log queue
        enable_multi_process: Whether to enable multi-process logging
        event_engine: Event engine instance
        db_manager: Database manager instance

    Returns:
        Configured LoggingHub instance
    """
    # Convert log level if it's a string
    if isinstance(log_level, str):
        log_level = getattr(logging, log_level.upper())

    # Set default log levels
    effective_log_levels = DEFAULT_LOG_LEVELS.copy()
    if log_levels:
        # Convert string level names to int values
        converted_levels = {}
        for logger_name, level in log_levels.items():
            if isinstance(level, str):
                converted_levels[logger_name] = getattr(logging, level.upper())
            else:
                converted_levels[logger_name] = level
        effective_log_levels.update(converted_levels)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove all existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Setup console handler if enabled
    if enable_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            logging.Formatter(fmt=log_format, datefmt=date_format)
        )
        console_handler.setLevel(log_level)
        root_logger.addHandler(console_handler)

    # Setup file handler if enabled and log_file is provided
    if enable_file and log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(
            filename=log_file,
            mode='a',
            encoding='utf-8',
        )
        file_handler.setFormatter(
            logging.Formatter(fmt=log_format, datefmt=date_format)
        )
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)

    # Set log levels for specific loggers
    for logger_name, level in effective_log_levels.items():
        if isinstance(level, str):
            level = getattr(logging, level.upper())
        logging.getLogger(logger_name).setLevel(level)

    # Setup LoggingHub
    hub = setup_logging_system(
        event_engine=event_engine,
        db_manager=db_manager if enable_database else None,
        enable_ordered_queue=enable_ordered_queue,
        enable_multi_process=enable_multi_process,
    )

    # Set log levels for LoggingHub
    hub.setLevel(log_level)

    # Configure event log handler if needed
    if enable_file:
        event_log_handler = get_event_log_handler()
        if event_log_handler:
            event_log_handler.setLevel(log_level)

    # Log configuration
    logging.info("Logging system configured", extra={
        "log_level": logging.getLevelName(log_level),
        "console_enabled": enable_console,
        "file_enabled": enable_file,
        "log_file": str(log_file) if log_file else None,
        "database_enabled": enable_database,
        "event_engine_enabled": enable_event_engine,
        "ordered_queue_enabled": enable_ordered_queue,
        "multi_process_enabled": enable_multi_process,
    })

    return hub


def get_logger(name: str, **context) -> logging.Logger:
    """Get a logger with the given name and context.

    Args:
        name: Logger name
        **context: Additional context to include in log records

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Add context to log records if provided
    # Note: Standard logging handlers don't support custom context attributes
    # Context should be added at the logging call site instead
    if context:
        logger.debug(f"Logger context provided but not applied to handlers: {context}")

    return logger


def setup_application_logging(
    app_name: str,
    log_dir: Union[str, Path] = "logs",
    log_level: Union[str, int] = logging.INFO,
    **kwargs
) -> LoggingHub:
    """Setup logging for an application.

    Args:
        app_name: Application name (used for log file naming)
        log_dir: Directory to store log files
        log_level: Default log level
        **kwargs: Additional arguments to pass to configure_logging

    Returns:
        Configured LoggingHub instance
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Create log file path
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"{app_name}_{timestamp}.log"

    # Configure logging
    hub = configure_logging(
        log_level=log_level,
        log_file=log_file,
        **kwargs
    )

    return hub


# Context manager for logging configuration
class LoggingConfiguration:
    """Context manager for temporary logging configuration.

    Example:
        with LoggingConfiguration(log_level=logging.DEBUG):
            # Logging with DEBUG level here
            logger.debug("Debug message")
    """

    def __init__(self, **config):
        self.config = config
        self.original_handlers = None
        self.original_levels = {}

    def __enter__(self):
        # Save original configuration
        root_logger = logging.getLogger()
        self.original_handlers = root_logger.handlers[:]

        # Save original log levels
        for logger_name in self.config.get('log_levels', {}):
            logger = logging.getLogger(logger_name)
            self.original_levels[logger_name] = logger.level

        # Apply new configuration
        configure_logging(**self.config)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        # Restore original configuration
        root_logger = logging.getLogger()

        # Remove all current handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # Restore original handlers
        if self.original_handlers:
            for handler in self.original_handlers:
                root_logger.addHandler(handler)

        # Restore original log levels
        for logger_name, level in self.original_levels.items():
            logging.getLogger(logger_name).setLevel(level)

        return False  # Don't suppress exceptions
