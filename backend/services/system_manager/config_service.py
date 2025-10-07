# -*- coding: utf-8 -*-
"""
配置管理服务.

提供系统配置管理、验证、备份恢复功能。
"""

import logging
import json
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class ConfigService:
    """配置管理服务."""

    def __init__(self, config_dir: str = "config"):
        """初始化配置服务."""
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.configs: Dict[str, Any] = {}
        logger.info("配置管理服务初始化完成: config_dir=%s", self.config_dir)

    def get_config(self, config_type: str) -> Dict[str, Any]:
        """获取配置."""
        try:
            if config_type in self.configs:
                return self.configs[config_type]

            # 从文件加载
            config_file = self.config_dir / f"{config_type}.json"
            if config_file.exists():
                with open(config_file, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                    self.configs[config_type] = config_data
                    return config_data

            return {}

        except Exception as e:
            logger.error("获取配置失败: type=%s, error=%s", config_type, e)
            raise

    def update_config(self, config_type: str, config_data: Dict[str, Any]) -> bool:
        """更新配置."""
        try:
            # TODO: 使用pydantic验证配置

            # 保存到内存
            self.configs[config_type] = config_data

            # 保存到文件
            config_file = self.config_dir / f"{config_type}.json"
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)

            logger.info("配置更新成功: type=%s", config_type)
            return True

        except Exception as e:
            logger.error("更新配置失败: %s", e)
            raise

    def backup_config(self) -> str:
        """备份配置."""
        try:
            backup_id = f"backup_{int(datetime.now().timestamp())}"
            backup_dir = self.config_dir / "backups" / backup_id
            backup_dir.mkdir(parents=True, exist_ok=True)

            # 备份所有配置文件
            for config_file in self.config_dir.glob("*.json"):
                backup_file = backup_dir / config_file.name
                backup_file.write_text(
                    config_file.read_text(encoding="utf-8"), encoding="utf-8"
                )

            logger.info("配置备份成功: backup_id=%s", backup_id)
            return backup_id

        except Exception as e:
            logger.error("备份配置失败: %s", e)
            raise


__all__ = ["ConfigService"]
