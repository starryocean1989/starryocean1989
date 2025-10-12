# -*- coding: utf-8 -*-
"""
配置管理模块

负责管理data_module_vnpy的所有配置项，包括：
- 品种列表缓存路径
- K线数据存储路径
- 通达信软件根目录
- 数据感知基日
- 其他运行时配置
"""

from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import date, datetime

from vnpy.trader.setting import SETTINGS, SETTING_FILENAME
from vnpy.trader.utility import load_json, save_json


class ConfigManager:
    """配置管理器"""

    # 默认配置项
    DEFAULT_CONFIG = {
        "chinastock.cache_dir": "./data/cache",
        "chinastock.data_dir": "./data/kline",
        "chinastock.tdx_dir": "",
        "chinastock.base_date": "2020-01-01",
        "chinastock.max_workers": 10,
        "chinastock.timeout": 30,
        "chinastock.retry_times": 3,
        "chinastock.enable_watcher": True,
        "chinastock.watcher_interval": 5,
        # 多服务器并行下载配置
        "chinastock.server_pool_size": 5,  # 并行服务器数量（默认5个，可设置1-30）
        # 轮询数据源转换器配置
        "chinastock.polling_gateway.enabled": False,
        "chinastock.polling_gateway.interval": 60,  # 轮询间隔（秒）
        # 品种列表默认从本地缓存加载，不再提供默认配置
        # 虚拟推送数据网关配置
        "chinastock.virtual_gateway.enabled": False,
        "chinastock.virtual_gateway.start_datetime": "",  # 虚拟推送起始时间（格式：YYYY-MM-DD HH:MM:SS）
        "chinastock.virtual_gateway.speed": 1.0,  # 推送速度倍数（1.0=实时，2.0=2倍速）
        # 品种列表默认从本地缓存加载，不再提供默认配置
        # 数据标准化读取工具配置
        "chinastock.data_readers.tdx_root_dir": "C:/new_tdx",  # 通达信软件根目录
    }

    def __init__(self):
        """初始化配置管理器"""
        self._config: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self) -> None:
        """加载配置"""
        # 从默认配置开始
        self._config.update(self.DEFAULT_CONFIG)

        # 从vnpy全局设置加载
        for key, value in SETTINGS.items():
            if key.startswith("chinastock."):
                self._config[key] = value

        # 从vt_setting.json加载
        try:
            setting_data = load_json(SETTING_FILENAME)
            for key, value in setting_data.items():
                if key.startswith("chinastock."):
                    self._config[key] = value
        except Exception:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置配置值"""
        self._config[key] = value
        self._save_to_file()

    def get_cache_dir(self) -> Path:
        """获取品种列表缓存目录"""
        cache_dir = Path(self.get("chinastock.cache_dir", "./data/cache"))
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def get_data_dir(self) -> Path:
        """获取K线数据存储目录"""
        data_dir = Path(self.get("chinastock.data_dir", "./data/kline"))
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    def get_tdx_dir(self) -> Optional[Path]:
        """获取通达信软件根目录"""
        tdx_dir = self.get("chinastock.tdx_dir", "")
        if tdx_dir and Path(tdx_dir).exists():
            return Path(tdx_dir)
        return None

    def get_base_date(self) -> date:
        """获取数据感知基日"""
        base_date_str = self.get("chinastock.base_date", "2020-01-01")
        try:
            return datetime.strptime(base_date_str, "%Y-%m-%d").date()
        except ValueError:
            return date(2020, 1, 1)

    def get_max_workers(self) -> int:
        """获取最大工作线程数"""
        return int(self.get("chinastock.max_workers", 10))

    def get_timeout(self) -> int:
        """获取请求超时时间（秒）"""
        return int(self.get("chinastock.timeout", 30))

    def get_retry_times(self) -> int:
        """获取重试次数"""
        return int(self.get("chinastock.retry_times", 3))

    def is_watcher_enabled(self) -> bool:
        """是否启用文件监控"""
        return bool(self.get("chinastock.enable_watcher", True))

    def get_watcher_interval(self) -> int:
        """获取文件监控间隔（秒）"""
        return int(self.get("chinastock.watcher_interval", 5))

    def is_polling_gateway_enabled(self) -> bool:
        """是否启用轮询数据源转换器"""
        return bool(self.get("chinastock.polling_gateway.enabled", False))

    def get_polling_interval(self) -> int:
        """获取轮询间隔（秒）"""
        return int(self.get("chinastock.polling_gateway.interval", 60))

    def is_virtual_gateway_enabled(self) -> bool:
        """是否启用虚拟推送数据网关"""
        return bool(self.get("chinastock.virtual_gateway.enabled", False))

    def get_virtual_gateway_start_datetime(self) -> str:
        """获取虚拟网关起始时间"""
        return str(self.get("chinastock.virtual_gateway.start_datetime", ""))

    def get_virtual_gateway_speed(self) -> float:
        """获取虚拟网关推送速度倍数"""
        return float(self.get("chinastock.virtual_gateway.speed", 1.0))

    def get_tdx_reader_root_dir(self) -> Optional[Path]:
        """获取通达信数据读取器根目录"""
        tdx_root = self.get("chinastock.data_readers.tdx_root_dir", "C:/new_tdx")
        if tdx_root and Path(tdx_root).exists():
            return Path(tdx_root)
        return None

    def _save_to_file(self) -> None:
        """保存配置到文件"""
        try:
            # 读取现有配置
            setting_data = {}
            with suppress(Exception):
                setting_data = load_json(SETTING_FILENAME)

            # 更新chinastock相关配置
            for key, value in self._config.items():
                if key.startswith("chinastock."):
                    setting_data[key] = value

            # 保存到文件
            save_json(SETTING_FILENAME, setting_data)
        except Exception as e:
            print(f"保存配置失败: {e}")

    def update_config(self, config_dict: Dict[str, Any]) -> None:
        """批量更新配置"""
        for key, value in config_dict.items():
            if key.startswith("chinastock."):
                self._config[key] = value
        self._save_to_file()

    def get_all_config(self) -> Dict[str, Any]:
        """获取所有配置"""
        return self._config.copy()


# 全局配置管理器实例
config_manager = ConfigManager()
