# -*- coding: utf-8 -*-
"""
统一配置管理模块.

提供应用配置的统一管理，支持环境变量、配置文件等多种配置源。
"""

import os
import json
import logging
from typing import Any, Dict, Optional, TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    # For type checkers, always assume pydantic_settings is available
    from pydantic_settings import BaseSettings
    from pydantic import Field, ConfigDict
else:
    # For runtime, handle both pydantic v1 and v2
    try:
        from pydantic_settings import BaseSettings
        from pydantic import Field, ConfigDict
    except ImportError:
        from pydantic import BaseSettings, Field

        # For Pydantic v1 compatibility
        class ConfigDict:  # type: ignore[no-redef]
            """Fallback ConfigDict for Pydantic v1."""

            def __init__(self, **kwargs: Any) -> None:
                _ = kwargs  # Acknowledge unused parameter


logger = logging.getLogger(__name__)


class DatabaseConfig(BaseSettings):
    """数据库配置."""

    model_config = ConfigDict(env_prefix="DB_") if ConfigDict else None  # type: ignore

    # SQLite配置
    sqlite_path: str = Field(default="data/terminal.db")
    sqlite_timeout: int = Field(default=30)

    # PostgreSQL配置（可选）
    postgres_host: Optional[str] = Field(default=None)
    postgres_port: int = Field(default=5432)
    postgres_db: Optional[str] = Field(default=None)
    postgres_user: Optional[str] = Field(default=None)
    postgres_password: Optional[str] = Field(default=None)


class VnPyConfig(BaseSettings):
    """VnPy配置."""

    model_config = ConfigDict(env_prefix="VNPY_") if ConfigDict else None  # type: ignore

    # VnPy引擎配置
    event_engine_timer_interval: float = Field(default=1.0)
    event_engine_timer_interval_ms: int = Field(default=1000)

    # 数据存储配置
    data_storage_path: str = Field(default="data")

    # 实时数据录制配置（对应需求：保存位置可配置更改）
    recording_data_path: str = Field(default="data/recordings")

    # 日志配置
    log_level: str = Field(default="INFO")
    log_file: Optional[str] = Field(default=None)


class APIConfig(BaseSettings):
    """API配置."""

    model_config = ConfigDict(env_prefix="API_") if ConfigDict else None  # type: ignore

    # 服务器配置
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000)
    debug: bool = Field(default=False)

    # 安全配置
    secret_key: str = Field(default="your-secret-key-here")
    access_token_expire_minutes: int = Field(default=30)

    # CORS配置
    cors_origins: list = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5173",
        ]
    )

    # 限流配置
    rate_limit_per_minute: int = Field(default=100)


class LoggingConfig(BaseSettings):
    """日志配置."""

    model_config = ConfigDict(env_prefix="LOG_") if ConfigDict else None  # type: ignore

    level: str = Field(default="INFO")
    format: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    file_path: Optional[str] = Field(default="logs/backend.log")
    max_file_size: int = Field(default=10 * 1024 * 1024)  # 10MB
    backup_count: int = Field(default=5)


class AIConfig(BaseSettings):
    """AI助手配置."""

    model_config = ConfigDict(env_prefix="AI_") if ConfigDict else None  # type: ignore

    # DeepSeek API配置
    provider: str = Field(default="deepseek")
    api_key: Optional[str] = Field(default=None)
    api_url: str = Field(default="https://api.deepseek.com/v1/chat/completions")
    model: str = Field(default="deepseek-chat")

    # 请求配置
    max_tokens: int = Field(default=2000)
    temperature: float = Field(default=0.7)
    timeout: int = Field(default=30)

    # 对话配置
    max_history: int = Field(default=10)
    system_prompt: str = Field(default="你是一个专业的量化交易策略编写助手，擅长Python和VnPy框架。")

    # 工具调用配置（MCP功能）
    enable_tools: bool = Field(default=False)  # 默认禁用，避免兼容性问题


class Settings:
    """统一配置管理类."""

    def __init__(self, config_file: Optional[str] = None):
        """初始化配置."""
        self.config_file = config_file

        # 加载配置
        self.database = DatabaseConfig()
        self.vnpy = VnPyConfig()
        self.api = APIConfig()
        self.logging = LoggingConfig()
        self.ai = AIConfig()

        # 加载配置文件（如果提供了路径就尝试加载）
        if config_file:
            config_path = Path(config_file)
            if config_path.exists():
                self.load_from_file(config_file)
            else:
                # 配置文件不存在，创建默认配置
                logger.info("配置文件不存在，将创建默认配置: %s", config_file)
                config_path.parent.mkdir(parents=True, exist_ok=True)
                self.save_to_file(config_file)

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
                "database": (
                    self.database.model_dump()
                    if hasattr(self.database, "model_dump")
                    else self.database.dict()
                ),
                "vnpy": (
                    self.vnpy.model_dump() if hasattr(self.vnpy, "model_dump") else self.vnpy.dict()
                ),
                "api": (
                    self.api.model_dump() if hasattr(self.api, "model_dump") else self.api.dict()
                ),
                "logging": (
                    self.logging.model_dump()
                    if hasattr(self.logging, "model_dump")
                    else self.logging.dict()
                ),
                "ai": self.ai.model_dump() if hasattr(self.ai, "model_dump") else self.ai.dict(),
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
            "database": (
                self.database.model_dump()
                if hasattr(self.database, "model_dump")
                else self.database.dict()
            ),
            "vnpy": (
                self.vnpy.model_dump() if hasattr(self.vnpy, "model_dump") else self.vnpy.dict()
            ),
            "api": self.api.model_dump() if hasattr(self.api, "model_dump") else self.api.dict(),
            "logging": (
                self.logging.model_dump()
                if hasattr(self.logging, "model_dump")
                else self.logging.dict()
            ),
            "ai": self.ai.model_dump() if hasattr(self.ai, "model_dump") else self.ai.dict(),
        }


# 全局配置实例
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """获取全局配置实例."""
    global _settings
    if _settings is None:
        # 尝试从环境变量获取配置文件路径
        config_file = os.getenv("CONFIG_FILE")
        if not config_file:
            # 如果环境变量未设置，使用默认路径
            config_file = "config/terminal_config.json"
        _settings = Settings(config_file)
    return _settings


def init_settings(config_file: Optional[str] = None) -> Settings:
    """初始化全局配置."""
    global _settings
    if config_file is None:
        # 🔧 修复点2：优先从环境变量获取配置文件路径
        config_file = os.getenv("CONFIG_FILE") or "config/terminal_config.json"

    # 强制重新创建配置对象，确保加载最新文件
    _settings = Settings(config_file)

    logger.info("全局配置已初始化: %s", config_file)
    return _settings


# 轻量UI/应用配置（供前端UI使用）
class AppConfig(BaseSettings):
    """应用基础配置（供UI展示用）."""

    model_config = ConfigDict(env_prefix="APP_") if ConfigDict else None  # type: ignore

    name: str = Field(default="星辰金融终端")
    version: str = Field(default="5.0.0")


class UIConfig(BaseSettings):
    """UI界面配置（供主窗口使用）."""

    model_config = ConfigDict(env_prefix="UI_") if ConfigDict else None  # type: ignore

    window_width: int = Field(default=1200)
    window_height: int = Field(default=800)
    min_width: int = Field(default=960)
    min_height: int = Field(default=640)
    theme: str = Field(default="dark")


class ConfigManager:
    """UI层期望的配置管理器（轻量实现）。"""

    def __init__(self, config_file: Optional[str] = None):
        """初始化配置管理器."""
        # 轻量从环境/默认值加载
        self.app_config = AppConfig()
        self.ui_config = UIConfig()
        # 兼容保存到文件（可选）
        self._config_file = config_file or os.getenv("UI_CONFIG_FILE")

        # 若提供文件路径，尝试加载
        if self._config_file and Path(self._config_file).exists():
            try:
                with open(self._config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                app = data.get("app", {})
                ui = data.get("ui", {})
                for k, v in app.items():
                    if hasattr(self.app_config, k):
                        setattr(self.app_config, k, v)
                for k, v in ui.items():
                    if hasattr(self.ui_config, k):
                        setattr(self.ui_config, k, v)
                logger.info("UI配置文件加载完成: %s", self._config_file)
            except Exception as e:
                logger.error("UI配置文件加载失败: %s", e)

    def save_config(self) -> None:
        """保存当前配置到文件（如提供路径）。"""
        if not self._config_file:
            # 无文件路径时不写盘，仅日志提示
            logger.debug("未提供UI配置文件路径，跳过保存")
            return
        try:
            Path(self._config_file).parent.mkdir(parents=True, exist_ok=True)
            with open(self._config_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "app": {
                            "name": self.app_config.name,
                            "version": self.app_config.version,
                        },
                        "ui": {
                            "window_width": self.ui_config.window_width,
                            "window_height": self.ui_config.window_height,
                            "min_width": self.ui_config.min_width,
                            "min_height": self.ui_config.min_height,
                            "theme": self.ui_config.theme,
                        },
                    },
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
            logger.info("UI配置保存完成: %s", self._config_file)
        except Exception as e:
            logger.error("UI配置保存失败: %s", e)


# 导出公共接口
__all__ = [
    "DatabaseConfig",
    "VnPyConfig",
    "APIConfig",
    "LoggingConfig",
    "AIConfig",
    "Settings",
    "get_settings",
    "init_settings",
    # UI层轻量配置管理器
    "AppConfig",
    "UIConfig",
    "ConfigManager",
]
