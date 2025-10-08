# -*- coding: utf-8 -*-
"""
系统管理处理器.

处理系统管理界面的所有业务逻辑。
"""

import logging
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


class SystemManagerHandlers:
    """系统管理处理器类."""

    def __init__(self, parent_widget=None):
        """
        初始化处理器.

        Args:
            parent_widget: 父窗口组件
        """
        self.parent_widget = parent_widget
        self.logger = logging.getLogger(self.__class__.__name__)
        self._config_cache: Dict[str, Any] = {}

    def load_data_module_config(self) -> Dict[str, Any]:
        """
        加载data_module_vnpy的配置.

        Returns:
            配置字典
        """
        try:
            from backend.infrastructure.data_module_vnpy.config import config_manager

            config = {
                "通达信软件根目录": {
                    "key": "chinastock.tdx_dir",
                    "value": config_manager.get("chinastock.tdx_dir", ""),
                    "type": "path",
                    "description": "通达信金融终端安装路径（用于解析spblock.dat获取特殊品种）",
                },
                "品种列表缓存目录": {
                    "key": "chinastock.cache_dir",
                    "value": config_manager.get("chinastock.cache_dir", "./data/cache"),
                    "type": "path",
                    "description": "品种列表Parquet文件存储目录",
                },
                "K线数据存储目录": {
                    "key": "chinastock.data_dir",
                    "value": config_manager.get("chinastock.data_dir", "./data/kline"),
                    "type": "path",
                    "description": "K线数据Parquet文件存储目录",
                },
                "数据感知基日": {
                    "key": "chinastock.base_date",
                    "value": config_manager.get("chinastock.base_date", "2020-01-01"),
                    "type": "date",
                    "description": "数据完整性检查的起始日期（格式：YYYY-MM-DD）",
                },
                "最大工作线程数": {
                    "key": "chinastock.max_workers",
                    "value": config_manager.get("chinastock.max_workers", 10),
                    "type": "int",
                    "description": "数据下载的最大并发线程数（1-50）",
                },
                "请求超时时间": {
                    "key": "chinastock.timeout",
                    "value": config_manager.get("chinastock.timeout", 30),
                    "type": "int",
                    "description": "数据请求超时时间（秒，10-300）",
                },
                "请求重试次数": {
                    "key": "chinastock.retry_times",
                    "value": config_manager.get("chinastock.retry_times", 3),
                    "type": "int",
                    "description": "数据请求失败后的重试次数（0-10）",
                },
                "启用文件监控": {
                    "key": "chinastock.enable_watcher",
                    "value": config_manager.get("chinastock.enable_watcher", True),
                    "type": "bool",
                    "description": "是否启用数据文件变化实时监控",
                },
                "文件监控间隔": {
                    "key": "chinastock.watcher_interval",
                    "value": config_manager.get("chinastock.watcher_interval", 5),
                    "type": "int",
                    "description": "文件监控检查间隔（秒，1-60）",
                },
            }

            self._config_cache = config
            self.logger.info("成功加载data_module_vnpy配置: %d 项", len(config))
            return config

        except Exception as e:
            self.logger.error("加载data_module_vnpy配置失败: %s", e)
            return {}

    def save_data_module_config(self, config_updates: Dict[str, Any]) -> bool:
        """
        保存data_module_vnpy的配置.

        Args:
            config_updates: 配置更新字典，键为配置键，值为新值

        Returns:
            是否保存成功
        """
        try:
            from backend.infrastructure.data_module_vnpy.config import config_manager

            # 更新配置
            for key, value in config_updates.items():
                if key.startswith("chinastock."):
                    config_manager.set(key, value)
                    self.logger.info("配置已更新: %s = %s", key, value)

            self.logger.info("data_module_vnpy配置保存成功")
            return True

        except Exception as e:
            self.logger.error("保存data_module_vnpy配置失败: %s", e)
            return False

    def validate_tdx_path(self, tdx_path: str) -> tuple[bool, str]:
        """
        验证通达信路径是否有效.

        Args:
            tdx_path: 通达信软件根目录路径

        Returns:
            (是否有效, 验证消息)
        """
        if not tdx_path:
            return True, "路径为空，将不使用spblock.dat解析特殊品种"

        path = Path(tdx_path)

        # 检查路径是否存在
        if not path.exists():
            return False, "路径不存在: " + tdx_path

        if not path.is_dir():
            return False, "路径不是目录: " + tdx_path

        # 递归搜索spblock.dat文件
        spblock_file = self._search_spblock_file(path)
        if not spblock_file:
            return (
                False,
                "未找到spblock.dat文件（已在 " + str(path) + " 目录下递归搜索）",
            )

        return True, "✓ 有效的通达信路径，找到spblock.dat在: " + str(spblock_file.relative_to(path))

    def _search_spblock_file(self, root_path: Path) -> Path | None:
        """
        在指定目录下递归搜索spblock.dat文件.

        Args:
            root_path: 根目录路径

        Returns:
            找到的spblock.dat文件路径，未找到则返回None
        """
        try:
            # 使用rglob递归搜索
            for spblock_file in root_path.rglob("spblock.dat"):
                if spblock_file.is_file():
                    self.logger.info("找到spblock.dat: %s", spblock_file)
                    return spblock_file
            return None
        except Exception as e:
            self.logger.error("搜索spblock.dat失败: %s", e)
            return None

    def get_config_statistics(self) -> Dict[str, Any]:
        """
        获取配置统计信息.

        Returns:
            配置统计字典
        """
        try:
            from backend.infrastructure.data_module_vnpy.config import config_manager

            cache_dir = config_manager.get_cache_dir()
            data_dir = config_manager.get_data_dir()

            # 统计缓存文件
            cache_files = list(cache_dir.glob("*.parquet"))

            # 统计数据文件
            data_symbols = list(data_dir.iterdir()) if data_dir.exists() else []
            data_symbols_count = len([d for d in data_symbols if d.is_dir()])

            return {
                "cache_dir": str(cache_dir),
                "data_dir": str(data_dir),
                "cache_files_count": len(cache_files),
                "data_symbols_count": data_symbols_count,
                "tdx_configured": bool(config_manager.get_tdx_dir()),
            }

        except Exception as e:
            self.logger.error("获取配置统计失败: %s", e)
            return {}

    def reset_to_defaults(self) -> bool:
        """
        重置配置为默认值.

        Returns:
            是否重置成功
        """
        try:
            from backend.infrastructure.data_module_vnpy.config import config_manager

            # 恢复默认配置
            default_config = {
                "chinastock.cache_dir": "./data/cache",
                "chinastock.data_dir": "./data/kline",
                "chinastock.tdx_dir": "",
                "chinastock.base_date": "2020-01-01",
                "chinastock.max_workers": 10,
                "chinastock.timeout": 30,
                "chinastock.retry_times": 3,
                "chinastock.enable_watcher": True,
                "chinastock.watcher_interval": 5,
            }

            for key, value in default_config.items():
                config_manager.set(key, value)

            self.logger.info("配置已重置为默认值")
            return True

        except Exception as e:
            self.logger.error("重置配置失败: %s", e)
            return False


# 导出公共接口
__all__ = ["SystemManagerHandlers"]
