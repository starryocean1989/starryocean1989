# -*- coding: utf-8 -*-
"""
统一配置管理模块.

提供应用配置的统一管理，支持环境变量、配置文件等多种配置源。
"""

import os
import json
import logging
from typing import Any, Dict, Optional
from pathlib import Path
from pydantic import BaseSettings, Field

logger = logging.getLogger(__name__)


class DatabaseConfig(BaseSettings):
    """数据库配置."""

    # SQLite配置
    sqlite_path: str = Field(default="data/terminal.db", env="SQLITE_PATH")
    sqlite_timeout: int = Field(default=30, env="SQLITE_TIMEOUT")

    # PostgreSQL配置（可选）
    postgres_host: Optional[str] = Field(default=None, env="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, env="POSTGRES_PORT")
    postgres_db: Optional[str] = Field(default=None, env="POSTGRES_DB")
    postgres_user: Optional[str] = Field(default=None, env="POSTGRES_USER")
    postgres_password: Optional[str] = Field(default=None, env="POSTGRES_PASSWORD")

    class Config:
        """配置类."""

        env_prefix = "DB_"


class VnPyConfig(BaseSettings):
    """VnPy配置."""

    # VnPy引擎配置
    event_engine_timer_interval: float = Field(
        default=1.0, env="VNPY_EVENT_TIMER_INTERVAL"
    )
    event_engine_timer_interval_ms: int = Field(
        default=1000, env="VNPY_EVENT_TIMER_INTERVAL_MS"
    )

    # 数据存储配置
    data_storage_path: str = Field(default="data", env="VNPY_DATA_STORAGE_PATH")

    # 日志配置
    log_level: str = Field(default="INFO", env="VNPY_LOG_LEVEL")
    log_file: Optional[str] = Field(default=None, env="VNPY_LOG_FILE")

    class Config:
        """配置类."""

        env_prefix = "VNPY_"


class WebSocketConfig(BaseSettings):
    """WebSocket配置."""

    # 连接配置
    max_connections: int = Field(default=1000, env="WS_MAX_CONNECTIONS")
    connection_timeout: float = Field(default=300.0, env="WS_CONNECTION_TIMEOUT")

    # 消息配置
    max_message_size: int = Field(default=1024 * 1024, env="WS_MAX_MESSAGE_SIZE")  # 1MB
    ping_interval: float = Field(default=30.0, env="WS_PING_INTERVAL")
    ping_timeout: float = Field(default=10.0, env="WS_PING_TIMEOUT")

    # 清理配置
    cleanup_interval: float = Field(default=60.0, env="WS_CLEANUP_INTERVAL")

    class Config:
        """配置类."""

        env_prefix = "WS_"


class APIConfig(BaseSettings):
    """API配置."""

    # 服务器配置
    host: str = Field(default="0.0.0.0", env="API_HOST")
    port: int = Field(default=8000, env="API_PORT")
    debug: bool = Field(default=False, env="API_DEBUG")

    # 安全配置
    secret_key: str = Field(default="your-secret-key-here", env="API_SECRET_KEY")
    access_token_expire_minutes: int = Field(
        default=30, env="API_ACCESS_TOKEN_EXPIRE_MINUTES"
    )

    # CORS配置
    cors_origins: list = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ],
        env="API_CORS_ORIGINS",
    )

    # 限流配置
    rate_limit_per_minute: int = Field(default=100, env="API_RATE_LIMIT_PER_MINUTE")

    class Config:
        """配置类."""

        env_prefix = "API_"


class LoggingConfig(BaseSettings):
    """日志配置."""

    level: str = Field(default="INFO", env="LOG_LEVEL")
    format: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s", env="LOG_FORMAT"
    )
    file_path: Optional[str] = Field(default="logs/backend.log", env="LOG_FILE_PATH")
    max_file_size: int = Field(
        default=10 * 1024 * 1024, env="LOG_MAX_FILE_SIZE"
    )  # 10MB
    backup_count: int = Field(default=5, env="LOG_BACKUP_COUNT")

    class Config:
        """配置类."""

        env_prefix = "LOG_"


class Settings:
    """统一配置管理类."""

    def __init__(self, config_file: Optional[str] = None):
        """初始化配置."""
        self.config_file = config_file

        # 加载配置
        self.database = DatabaseConfig()
        self.vnpy = VnPyConfig()
        self.websocket = WebSocketConfig()
        self.api = APIConfig()
        self.logging = LoggingConfig()

        # 加载配置文件
        if config_file and Path(config_file).exists():
            self.load_from_file(config_file)

        # 创建必要的目录
        self._create_directories()

    def load_from_file(self, config_file: str) -> None:
        """从配置文件加载配置."""
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config_data = json.load(f)

            # 更新配置
            for section, values in config_data.items():
                if hasattr(self, section) and isinstance(values, dict):
                    section_obj = getattr(self, section)
                    for key, value in values.items():
                        if hasattr(section_obj, key):
                            setattr(section_obj, key, value)

            logger.info("配置文件加载完成: %s", config_file)

        except Exception as e:
            logger.error("配置文件加载失败: %s", e)

    def save_to_file(self, config_file: str) -> None:
        """保存配置到文件."""
        try:
            config_data = {
                "database": self.database.dict(),
                "vnpy": self.vnpy.dict(),
                "websocket": self.websocket.dict(),
                "api": self.api.dict(),
                "logging": self.logging.dict(),
            }

            # 确保目录存在
            Path(config_file).parent.mkdir(parents=True, exist_ok=True)

            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)

            logger.info("配置文件保存完成: %s", config_file)

        except Exception as e:
            logger.error("配置文件保存失败: %s", e)

    def _create_directories(self) -> None:
        """创建必要的目录."""
        directories = [
            Path(self.vnpy.data_storage_path),
            Path(self.database.sqlite_path).parent,
        ]

        if self.logging.file_path:
            directories.append(Path(self.logging.file_path).parent)

        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)

    def get_database_url(self) -> str:
        """获取数据库连接URL."""
        if self.database.postgres_host:
            return (
                f"postgresql://{self.database.postgres_user}:"
                f"{self.database.postgres_password}@"
                f"{self.database.postgres_host}:"
                f"{self.database.postgres_port}/"
                f"{self.database.postgres_db}"
            )
        else:
            return f"sqlite:///{self.database.sqlite_path}"

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式."""
        return {
            "database": self.database.dict(),
            "vnpy": self.vnpy.dict(),
            "websocket": self.websocket.dict(),
            "api": self.api.dict(),
            "logging": self.logging.dict(),
        }


# 全局配置实例
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """获取全局配置实例."""
    global _settings
    if _settings is None:
        # 尝试从环境变量获取配置文件路径
        config_file = os.getenv("CONFIG_FILE")
        _settings = Settings(config_file)
    return _settings


def init_settings(config_file: Optional[str] = None) -> Settings:
    """初始化全局配置."""
    global _settings
    _settings = Settings(config_file)
    return _settings


# 导出公共接口
__all__ = [
    "DatabaseConfig",
    "VnPyConfig",
    "WebSocketConfig",
    "APIConfig",
    "LoggingConfig",
    "Settings",
    "get_settings",
    "init_settings",
]
