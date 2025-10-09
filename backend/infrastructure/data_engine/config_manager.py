# -*- coding: utf-8 -*-

"""
数据引擎配置管理器.

本模块负责数据引擎的配置管理,
包括存储配置,缓存配置和备份配置.
"""

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union


@dataclass
class StorageConfig:
    """存储配置类."""

    data_dir: str = "data"
    cache_dir: str = "cache"
    backup_dir: str = "backup"
    max_cache_size_mb: int = 1024
    compression_enabled: bool = True
    auto_cleanup: bool = True
    backup_interval_hours: int = 24
    max_backup_files: int = 30


@dataclass
class DatabaseConfig:
    """数据库配置类."""

    host: str = "localhost"
    port: int = 5432
    database: str = "market_data"
    username: str = "user"
    password: str = "password"
    pool_size: int = 10
    max_overflow: int = 20
    connection_timeout: int = 30


@dataclass
class NetworkConfig:
    """网络配置类."""

    timeout: int = 30
    retry_count: int = 3
    retry_delay: float = 1.0
    user_agent: str = "DataEngine/1.0"
    proxy_url: Optional[str] = None


class DataEngineConfigManager:
    """
    数据引擎配置管理器.

    负责加载,保存和管理数据引擎的所有配置.
    """

    def __init__(self, config_file: str = "data_engine_config.json") -> None:
        """
        初始化配置管理器.

        Args:
            config_file: 配置文件路径
        """
        self.config_file = Path(config_file)
        self.logger = logging.getLogger(__name__)

        # 默认配置
        self.storage_config = StorageConfig()
        self.database_config = DatabaseConfig()
        self.network_config = NetworkConfig()

        # 加载配置
        self.load_config()

    def _load_config_section(
        self, data: Dict[str, Any], section_name: str, config_obj: object
    ) -> None:
        """加载配置的特定部分."""
        if section_name in data:
            section_data = data[section_name]
            for key, value in section_data.items():
                if hasattr(config_obj, key):
                    setattr(config_obj, key, value)

    def load_config(self) -> bool:
        """
        从文件加载配置.

        Returns:
            bool: 加载是否成功
        """
        try:
            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # 加载各个配置部分
                self._load_config_section(data, "storage", self.storage_config)
                self._load_config_section(data, "database", self.database_config)
                self._load_config_section(data, "network", self.network_config)

                self.logger.info("配置已从 %s 加载", self.config_file)
                return True
            else:
                # 配置文件不存在,使用默认配置
                self.logger.info("配置文件不存在,使用默认配置")
                return True
        except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
            self.logger.error("加载配置文件失败: %s", e)
            return False

    def save_config(self) -> bool:
        """
        保存配置到文件.

        Returns:
            bool: 保存是否成功
        """
        try:
            # 确保配置目录存在
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

            config_data = {
                "storage": asdict(self.storage_config),
                "database": asdict(self.database_config),
                "network": asdict(self.network_config),
            }

            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)

            self.logger.info("配置已保存到 %s", self.config_file)
            return True
        except OSError as e:
            self.logger.error("保存配置文件失败: %s", e)
            return False

    def get_storage_config(self) -> StorageConfig:
        """
        获取存储配置.

        Returns:
            StorageConfig: 存储配置对象
        """
        return self.storage_config

    def get_database_config(self) -> DatabaseConfig:
        """
        获取数据库配置.

        Returns:
            DatabaseConfig: 数据库配置对象
        """
        return self.database_config

    def get_network_config(self) -> NetworkConfig:
        """
        获取网络配置.

        Returns:
            NetworkConfig: 网络配置对象
        """
        return self.network_config

    def update_storage_config(self, **kwargs: Union[str, int, float, bool]) -> bool:
        """
        更新存储配置.

        Args:
            **kwargs: 配置参数

        Returns:
            bool: 更新是否成功
        """
        try:
            for key, value in kwargs.items():
                if hasattr(self.storage_config, key):
                    setattr(self.storage_config, key, value)

            return self.save_config()
        except (AttributeError, TypeError) as e:
            self.logger.error("更新存储配置失败: %s", e)
            return False

    def update_database_config(self, **kwargs: Union[str, int, float, bool]) -> bool:
        """
        更新数据库配置.

        Args:
            **kwargs: 配置参数

        Returns:
            bool: 更新是否成功
        """
        try:
            for key, value in kwargs.items():
                if hasattr(self.database_config, key):
                    setattr(self.database_config, key, value)

            return self.save_config()
        except (AttributeError, TypeError) as e:
            self.logger.error("更新数据库配置失败: %s", e)
            return False

    def update_network_config(self, **kwargs: Union[str, int, float, bool, None]) -> bool:
        """
        更新网络配置.

        Args:
            **kwargs: 配置参数

        Returns:
            bool: 更新是否成功
        """
        try:
            for key, value in kwargs.items():
                if hasattr(self.network_config, key):
                    setattr(self.network_config, key, value)

            return self.save_config()
        except (AttributeError, TypeError) as e:
            self.logger.error("更新网络配置失败: %s", e)
            return False

    def get_all_config(
        self,
    ) -> Dict[str, Dict[str, Union[str, int, float, bool, None]]]:
        """
        获取所有配置.

        Returns:
            Dict[str, Dict[str, Union[str, int, float, bool, None]]]: 所有配置数据
        """
        return {
            "storage": asdict(self.storage_config),
            "database": asdict(self.database_config),
            "network": asdict(self.network_config),
        }
