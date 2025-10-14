# -*- coding: utf-8 -*-
"""
配置管理模块

负责管理data_module_vnpy的所有配置项，包括：
- 品种列表缓存路径
- K线数据存储路径
- 通达信软件根目录和配置文件
- 数据感知基日
- 其他运行时配置

合并来源：config.py + config_file_parser.py
"""

import logging
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import date, datetime
import re

from vnpy.trader.setting import SETTINGS, SETTING_FILENAME
from vnpy.trader.utility import load_json, save_json

logger = logging.getLogger(__name__)


class TdxConfigFileParser:
    """通达信配置文件解析器

    合并自 config_file_parser.py
    """

    def __init__(self, tdx_dir: Optional[Path] = None):
        """
        初始化配置文件解析器

        Args:
            tdx_dir: 通达信软件根目录，如果为None则自动查找
        """
        self.tdx_dir = tdx_dir
        self.tdxstat2_path: Optional[Path] = None
        self.addedcode_bj_path: Optional[Path] = None
        self._find_config_files()

    def _find_config_files(self) -> None:
        """查找配置文件（递归搜索）"""
        if self.tdx_dir and self.tdx_dir.exists():
            # 在指定目录下递归搜索
            self._search_config_files_in_dir(self.tdx_dir)
            if self.tdxstat2_path and self.addedcode_bj_path:
                return

        # 如果未指定路径或搜索失败，尝试常见根目录并递归搜索
        common_root_dirs = [
            Path("C:/new_tdx"),
            Path("C:/通达信金融终端V7"),
            Path("C:/Program Files/通达信金融终端V7"),
            Path("D:/通达信金融终端V7"),
            Path("C:/tdx"),
            Path("D:/tdx"),
        ]

        for root_dir in common_root_dirs:
            if root_dir.exists() and self._search_config_files_in_dir(root_dir):
                break

    def _search_config_files_in_dir(self, directory: Path) -> bool:
        """
        在指定目录下递归搜索配置文件

        Args:
            directory: 要搜索的目录

        Returns:
            是否找到所有配置文件
        """
        try:
            logger.info("正在递归搜索 %s 目录下的配置文件...", directory)

            # 搜索 tdxstat2.cfg
            if not self.tdxstat2_path:
                for file in directory.rglob("tdxstat2.cfg"):
                    if file.is_file():
                        self.tdxstat2_path = file
                        logger.info("✓ 找到 tdxstat2.cfg: %s", file)
                        break

            # 搜索 addedcode_bj.cfg
            if not self.addedcode_bj_path:
                for file in directory.rglob("addedcode_bj.cfg"):
                    if file.is_file():
                        self.addedcode_bj_path = file
                        logger.info("✓ 找到 addedcode_bj.cfg: %s", file)
                        break

            # 如果都找到了，返回True
            if self.tdxstat2_path and self.addedcode_bj_path:
                return True

            if not self.tdxstat2_path:
                logger.warning("在 %s 目录下未找到 tdxstat2.cfg 文件", directory)
            if not self.addedcode_bj_path:
                logger.warning("在 %s 目录下未找到 addedcode_bj.cfg 文件", directory)

            return False

        except OSError as e:
            logger.warning("搜索 %s 时发生错误: %s", directory, e)
            return False

    def parse_tdxstat2(self) -> Dict[int, List[str]]:
        """
        解析tdxstat2.cfg文件，获取可转债代码

        实际文件为管道分隔：如 market|code|date|...
        - 取第二列为6位代码
        - 代码以11开头 -> 市场1；以12开头 -> 市场0
        """
        if not self.tdxstat2_path or not self.tdxstat2_path.exists():
            logger.warning("tdxstat2.cfg 文件不存在，返回空字典")
            return {0: [], 1: []}

        result: Dict[int, List[str]] = {0: [], 1: []}
        total_lines = 0
        parsed = 0

        try:
            # 使用GBK读取
            with open(self.tdxstat2_path, "r", encoding="gbk", errors="ignore") as f:
                for raw in f:
                    total_lines += 1
                    line = raw.strip()
                    if not line:
                        continue
                    parts = line.split("|")
                    if len(parts) >= 2:
                        code = parts[1].strip()
                        if code.isdigit() and len(code) == 6:
                            if code.startswith("11"):
                                result[1].append(code)
                                parsed += 1
                            elif code.startswith("12"):
                                result[0].append(code)
                                parsed += 1

            logger.info(
                "成功解析 tdxstat2.cfg: market0=%d, market1=%d, 总行=%d, 命中=%d",
                len(result[0]),
                len(result[1]),
                total_lines,
                parsed,
            )
            return result

        except Exception as e:
            logger.error("解析 tdxstat2.cfg 失败: %s", e, exc_info=True)
            return {0: [], 1: []}

    def parse_addedcode_bj(self) -> List[Dict[str, str]]:
        """
        解析addedcode_bj.cfg（GBK）：实际格式多为
        44|原代码|北证代码|名称|日期
        - 取第3列为 920xxx（6位），第4列为名称（去除尾部括号注）
        - 若该格式不匹配，再回退到简单 "code|name" 或空白分隔的两列格式（9/8/4开头）
        """
        if not self.addedcode_bj_path or not self.addedcode_bj_path.exists():
            logger.warning("addedcode_bj.cfg 文件不存在，返回空列表")
            return []

        result = []
        used_new_format = 0

        try:
            with open(self.addedcode_bj_path, "r", encoding="gbk", errors="ignore") as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if not line:
                        continue
                    parts = [p.strip() for p in line.split("|")]

                    # 优先解析 5 段及以上：44|orig|bj(920xxx)|name|date
                    if len(parts) >= 4 and parts[2].isdigit() and len(parts[2]) == 6:
                        bj_code = parts[2]
                        name = parts[3]
                        # 仅收集 920xxx（北证股票）
                        if bj_code.startswith("920"):
                            # 去除名称中的尾部括号注释
                            name_clean = re.sub(r"\(.*?\)$", "", name).strip()
                            result.append({"code": bj_code, "name": name_clean})
                            used_new_format += 1
                        continue

                    # 回退：两段或空白分隔（兼容旧历史数据）
                    if "|" not in line:
                        parts = [p.strip() for p in re.split(r"\s+", line) if p.strip()]
                    if len(parts) >= 2:
                        code = parts[0]
                        name = parts[1]
                        if code.isdigit() and len(code) == 6 and code.startswith(("9", "8", "4")):
                            name_clean = re.sub(r"\(.*?\)$", "", name).strip()
                            result.append({"code": code, "name": name_clean})

            logger.info(
                "成功解析 addedcode_bj.cfg: %d 个北交所股票（新格式匹配 %d 条）",
                len(result),
                used_new_format,
            )
            return result

        except Exception as e:
            logger.error("解析 addedcode_bj.cfg 失败: %s", e, exc_info=True)
            return []

    def is_available(self) -> bool:
        """
        检查配置文件是否可用

        Returns:
            是否可用
        """
        return (self.tdxstat2_path is not None and self.tdxstat2_path.exists()) or (
            self.addedcode_bj_path is not None and self.addedcode_bj_path.exists()
        )

    def get_file_info(self) -> Dict[str, Dict[str, str]]:
        """
        获取配置文件信息

        Returns:
            文件信息字典
        """
        info = {}

        if self.tdxstat2_path and self.tdxstat2_path.exists():
            info["tdxstat2.cfg"] = {
                "status": "可用",
                "path": str(self.tdxstat2_path),
                "size": f"{self.tdxstat2_path.stat().st_size / 1024:.2f} KB",
            }
        else:
            info["tdxstat2.cfg"] = {"status": "不可用", "path": ""}

        if self.addedcode_bj_path and self.addedcode_bj_path.exists():
            info["addedcode_bj.cfg"] = {
                "status": "可用",
                "path": str(self.addedcode_bj_path),
                "size": f"{self.addedcode_bj_path.stat().st_size / 1024:.2f} KB",
            }
        else:
            info["addedcode_bj.cfg"] = {"status": "不可用", "path": ""}

        return info


class ConfigManager:
    """配置管理器

    合并自 config.py
    """

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

    # 新增：便捷访问配置文件解析器
    def get_config_parser(self) -> Optional[TdxConfigFileParser]:
        """
        获取通达信配置文件解析器实例

        Returns:
            TdxConfigFileParser实例，如果通达信目录存在
        """
        tdx_dir = self.get_tdx_dir()
        if tdx_dir:
            return TdxConfigFileParser(tdx_dir)
        return None


# 全局配置管理器实例
config_manager = ConfigManager()
