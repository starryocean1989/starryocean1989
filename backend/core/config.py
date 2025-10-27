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
    """日志配置（仅数据库日志和Terminal输出，文件日志已于v0.50移除）."""

    model_config = ConfigDict(env_prefix="LOG_") if ConfigDict else None  # type: ignore

    level: str = Field(default="INFO")
    format: str = Field(default="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


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


class AdaptiveConfig(BaseSettings):
    """自适应并发/监控相关配置."""

    model_config = ConfigDict(env_prefix="ADAPTIVE_") if ConfigDict else None  # type: ignore

    # 策略选择：classic | intelligent
    strategy: str = Field(default="classic")

    # 可选：智能策略调优参数（保留占位，默认None）
    intelligent_tuning: Optional[dict] = Field(default=None)

    # 基准并发配置
    baseline_async_concurrency: int = Field(default=80, description="基准异步并发数")
    baseline_thread_concurrency: int = Field(default=10, description="基准线程并发数")
    baseline_process_concurrency: int = Field(default=2, description="基准进程并发数")


class StartupConfig(BaseSettings):
    """启动流程相关配置."""

    model_config = ConfigDict(env_prefix="STARTUP_") if ConfigDict else None  # type: ignore

    # 启动模式：ui_first | backend_first | server
    mode: str = Field(default="ui_first")

    # 管理员策略：auto | never | ask
    admin_policy: str = Field(default="auto")

    # 监控握手超时（毫秒）
    monitor_handshake_timeout_ms: int = Field(default=3000)

    # 监控重启限流（每分钟最多重启次数）
    monitor_max_restarts_per_minute: int = Field(default=3)

    # UI首屏目标预算（毫秒，用于日志指标与预警）
    ui_target_ms: int = Field(default=2000)


class MonitorConfig(BaseSettings):
    """监控系统集成相关配置."""

    model_config = ConfigDict(env_prefix="MONITOR_") if ConfigDict else None  # type: ignore

    # ZMQ端口
    port_alert_push: int = Field(default=5555)
    port_status_pull: int = Field(default=5556)
    port_query_rep: int = Field(default=5557)

    # 地址
    bind_addr: str = Field(default="127.0.0.1")

    # 端口退避（当默认端口被占用时）
    port_fallback_enabled: bool = Field(default=True)
    port_fallback_base: int = Field(default=5565)
    port_fallback_span: int = Field(default=3)


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
        self.adaptive = AdaptiveConfig()
        self.startup = StartupConfig()
        self.monitor = MonitorConfig()

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
            logger.info("开始加载配置文件: %s", config_file)

            with open(config_file, "r", encoding="utf-8") as f:
                config_data = json.load(f)

            # 统计配置信息
            config_sections = len(config_data)
            total_configs = sum(len(v) for v in config_data.values() if isinstance(v, dict))

            # 更新配置
            for section, values in config_data.items():
                if hasattr(self, section) and isinstance(values, dict):
                    section_obj = getattr(self, section)
                    for key, value in values.items():
                        if hasattr(section_obj, key):
                            setattr(section_obj, key, value)

            logger.info(
                "配置文件加载完成: 文件=%s, 配置节=%d, 配置项=%d",
                config_file,
                config_sections,
                total_configs,
            )

        except FileNotFoundError:
            logger.error("配置文件不存在: %s", config_file)
        except json.JSONDecodeError:
            logger.exception("配置文件JSON格式错误: 文件=%s", config_file)
        except Exception:
            logger.exception("配置文件加载失败: 文件=%s", config_file)

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
                "adaptive": (
                    self.adaptive.model_dump()
                    if hasattr(self.adaptive, "model_dump")
                    else self.adaptive.dict()
                ),
                "startup": (
                    self.startup.model_dump()
                    if hasattr(self.startup, "model_dump")
                    else self.startup.dict()
                ),
                "monitor": (
                    self.monitor.model_dump()
                    if hasattr(self.monitor, "model_dump")
                    else self.monitor.dict()
                ),
            }

            # 确保目录存在
            config_path = Path(config_file)
            config_path.parent.mkdir(parents=True, exist_ok=True)

            # 原子写入：先写临时文件，再重命名
            temp_file = config_path.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)

            # 重命名（原子操作）
            temp_file.replace(config_path)

            # 获取文件大小
            file_size = config_path.stat().st_size

            logger.info("配置保存完成: 文件=%s, 大小=%d字节", config_file, file_size)

        except Exception:
            logger.exception("配置文件保存失败: 文件=%s", config_file)

    def _create_directories(self) -> None:
        """创建必要的目录."""
        directories = [
            Path(self.vnpy.data_storage_path),
            Path(self.database.sqlite_path).parent,
        ]

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
            "adaptive": (
                self.adaptive.model_dump()
                if hasattr(self.adaptive, "model_dump")
                else self.adaptive.dict()
            ),
            "startup": (
                self.startup.model_dump()
                if hasattr(self.startup, "model_dump")
                else self.startup.dict()
            ),
            "monitor": (
                self.monitor.model_dump()
                if hasattr(self.monitor, "model_dump")
                else self.monitor.dict()
            ),
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

    # 阶段感知：启动阶段详细日志（P2优化）
    try:
        from backend.infrastructure.system_vnpy.logging_context import get_logging_context

        ctx = get_logging_context()
        if ctx.routing_engine.current_stage == "startup":
            logger.info("开始初始化全局配置: 文件=%s", config_file)
        else:
            logger.debug("重新初始化全局配置: 文件=%s", config_file)
    except (ImportError, AttributeError):
        # logging_context未初始化，使用默认INFO级别
        logger.info("开始初始化全局配置: 文件=%s", config_file)

    # 强制重新创建配置对象，确保加载最新文件
    _settings = Settings(config_file)

    # 统计配置信息
    config_dict = _settings.to_dict()
    config_sections = len(config_dict)
    total_items = sum(len(v) if isinstance(v, dict) else 1 for v in config_dict.values())

    try:
        from backend.infrastructure.system_vnpy.logging_context import get_logging_context

        ctx = get_logging_context()
        if ctx.routing_engine.current_stage == "startup":
            logger.info(
                "全局配置初始化完成: 文件=%s, 配置节=%d, 配置项=%d",
                config_file,
                config_sections,
                total_items,
            )
        else:
            logger.debug("全局配置重新初始化完成: 文件=%s", config_file)
    except (ImportError, AttributeError):
        logger.info(
            "全局配置初始化完成: 文件=%s, 配置节=%d, 配置项=%d",
            config_file,
            config_sections,
            total_items,
        )

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
    "AdaptiveConfig",
    "StartupConfig",
    "MonitorConfig",
    "Settings",
    "get_settings",
    "init_settings",
    # UI层轻量配置管理器
    "AppConfig",
    "UIConfig",
    "ConfigManager",
]


# =========================
# 运行期能力位（全局注入）
# =========================

_capabilities: Dict[str, Any] = {
    "is_admin": False,
    "hardware_monitoring_enabled": True,
    "smart_enabled": True,
}


def update_capabilities(values: Dict[str, Any]) -> None:
    """更新运行期能力位（线程安全需求较低，使用简单合并）。"""
    try:
        _capabilities.update(values)
        logger.info("运行期能力位已更新: %s", values)
    except Exception as e:
        logger.error("更新能力位失败: %s", e)


def get_capabilities() -> Dict[str, Any]:
    """获取当前运行期能力位副本."""
    return dict(_capabilities)
