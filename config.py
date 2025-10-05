# -*- coding: utf-8 -*-
"""
配置管理模块
提供应用程序配置管理功能
"""

import json
import os
from pathlib import Path
from typing import Dict, Any


class AppConfig:
    """应用配置"""

    def __init__(self):
        self.name = "星辰金融终端"
        self.version = "5.0.0"
        self.author = "星辰科技"
        self.description = "专业的金融交易终端系统"


class UIConfig:
    """UI配置"""

    def __init__(self):
        self.theme = "dark"
        self.language = "zh_CN"
        self.window_width = 1200
        self.window_height = 800
        self.min_width = 800
        self.min_height = 600
        self.font_size = 10
        self.refresh_interval = 1000


class ConfigManager:
    """配置管理器"""

    def __init__(self):
        import logging
        self._logger = logging.getLogger(self.__class__.__name__)
        self.app_config = AppConfig()
        self.ui_config = UIConfig()

        # 配置文件路径
        self.config_file = Path("config") / "terminal_config.json"

        # 确保配置目录存在
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        # 加载配置
        self.load_config()

    @property
    def logger(self):
        """获取日志器"""
        return self._logger

    def load_config(self):
        """加载配置"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                # 更新配置
                if 'app' in data:
                    for key, value in data['app'].items():
                        if hasattr(self.app_config, key):
                            setattr(self.app_config, key, value)

                if 'ui' in data:
                    for key, value in data['ui'].items():
                        if hasattr(self.ui_config, key):
                            setattr(self.ui_config, key, value)

        except Exception as e:
            print(f"加载配置失败: {e}")

    def save_config(self):
        """保存配置"""
        try:
            data = {
                'app': {
                    'name': self.app_config.name,
                    'version': self.app_config.version,
                    'author': self.app_config.author,
                    'description': self.app_config.description
                },
                'ui': {
                    'theme': self.ui_config.theme,
                    'language': self.ui_config.language,
                    'window_width': self.ui_config.window_width,
                    'window_height': self.ui_config.window_height,
                    'min_width': self.ui_config.min_width,
                    'min_height': self.ui_config.min_height,
                    'font_size': self.ui_config.font_size,
                    'refresh_interval': self.ui_config.refresh_interval
                }
            }

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"保存配置失败: {e}")


# 全局配置实例
config_manager = ConfigManager()
