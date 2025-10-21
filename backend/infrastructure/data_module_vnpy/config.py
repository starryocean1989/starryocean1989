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


def get_project_root() -> Path:
    """获取项目根目录

    从当前文件向上查找，直到找到真正的项目根目录标记文件
    优先查找 pyproject.toml 和 venv310 目录（项目特有），避免被子模块的 requirements.txt 误导
    """
    current = Path(__file__).resolve().parent

    # 向上查找，最多10层
    for _ in range(10):
        # 优先级1：pyproject.toml 或 venv310 目录（最可靠）
        if (current / "pyproject.toml").exists() or (current / "venv310").exists():
            return current

        # 优先级2：检查是否同时有 requirements.txt 和 ui 目录（避免子模块干扰）
        if (current / "requirements.txt").exists() and (current / "ui").exists():
            return current

        parent = current.parent
        if parent == current:  # 到达根目录
            break
        current = parent

    # 如果没找到，返回当前工作目录
    return Path.cwd()


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
        # 服务器池管理器配置
        "chinastock.server_pool.server_count": 132,  # 测速服务器数量（默认132个，使用所有可用服务器）
        "chinastock.server_pool.use_multiprocess": True,  # 是否使用多进程测速（默认True）
        "chinastock.server_pool.max_coroutines_per_process": 50,  # 每进程最多协程数（默认50）
        "chinastock.server_pool.update_interval": 600.0,  # 服务器池更新间隔（秒，默认10分钟）
        "chinastock.server_pool.test_timeout": 2.0,  # 单个服务器测试超时（秒）
        "chinastock.server_pool.max_fail_time": 10.0,  # 服务器失败阈值（秒，超过则视为不可用）
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
        # 统一数据管理器与预加载配置
        "chinastock.unified_manager.enabled": True,
        "chinastock.unified_manager.auto_download": False,  # 禁用自动下载，需要用户手动触发
        "chinastock.preload.enabled": True,
        "chinastock.preload.auto_start": False,  # 禁用自动启动预加载
        "chinastock.preload.max_cache_symbols": 64,
        "chinastock.preload.intervals": ["1d", "5m"],
        "chinastock.preload.frequently_used_symbols": [
            "000001",
            "000002",
            "600000",
            "600036",
            "600519",
        ],
        # 🆕 数据质量感知配置
        "chinastock.quality_scan.enable_adaptive": True,  # 启用自适应配置
        "chinastock.quality_scan.enable_detailed_scan": True,  # 启用详细扫描（错误/警告）
        "chinastock.quality_scan.enable_incremental_push": True,  # 启用增量推送
        "chinastock.quality_scan.min_push_interval_ms": 500,  # 最小推送间隔（避免UI刷新过快）
        # 🆕 混合异步架构配置
        "chinastock.quality_scan.enable_hybrid_async": True,  # 启用混合异步架构
        "chinastock.quality_scan.max_async_workers": 1000,  # 协程层最大并发数
        "chinastock.quality_scan.max_thread_workers": 20,  # 线程层最大并发数
        "chinastock.quality_scan.max_process_workers": 8,  # 进程层最大并发数
        "chinastock.quality_scan.enable_dynamic_tuning": True,  # 启用动态并发调节
        "chinastock.quality_scan.file_size_threshold_small_kb": 1024,  # <1MB用协程
        "chinastock.quality_scan.file_size_threshold_large_kb": 10240,  # >10MB用进程
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

        # 🔧 新增：初始化时主动转换相对路径为绝对路径
        self._normalize_paths_on_init()

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        return self._config.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """设置配置值"""
        self._config[key] = value
        self._save_to_file()

    def _normalize_paths_on_init(self) -> None:
        """初始化时主动转换相对路径为绝对路径

        检查 cache_dir 和 data_dir 配置，如果是相对路径则转换为绝对路径并持久化
        """
        try:
            project_root = get_project_root()
            path_updated = False

            # 1. 检查并转换 cache_dir
            cache_dir_str = self._config.get("chinastock.cache_dir", "./data/cache")
            if cache_dir_str:
                cache_path = Path(cache_dir_str)
                if not cache_path.is_absolute():
                    abs_cache_path = project_root / cache_path
                    abs_cache_str = str(abs_cache_path.resolve())
                    self._config["chinastock.cache_dir"] = abs_cache_str
                    path_updated = True
                    print("\n🔧 初始化配置转换: 品种缓存目录")
                    print(f"   原配置: {cache_dir_str} (相对路径)")
                    print(f"   新配置: {abs_cache_str} (绝对路径)")

            # 2. 检查并转换 data_dir
            data_dir_str = self._config.get("chinastock.data_dir", "./data/kline")
            if data_dir_str:
                data_path = Path(data_dir_str)
                if not data_path.is_absolute():
                    abs_data_path = project_root / data_path
                    abs_data_str = str(abs_data_path.resolve())
                    self._config["chinastock.data_dir"] = abs_data_str
                    path_updated = True
                    print("🔧 初始化配置转换: K线数据目录")
                    print(f"   原配置: {data_dir_str} (相对路径)")
                    print(f"   新配置: {abs_data_str} (绝对路径)")

            # 3. 检查并转换 db_file
            db_file_str = self._config.get("chinastock.db_file", "./data/terminal.db")
            if db_file_str:
                db_path = Path(db_file_str)
                if not db_path.is_absolute():
                    abs_db_path = project_root / db_path
                    abs_db_str = str(abs_db_path.resolve())
                    self._config["chinastock.db_file"] = abs_db_str
                    path_updated = True
                    print("🔧 初始化配置转换: 数据库文件")
                    print(f"   原配置: {db_file_str} (相对路径)")
                    print(f"   新配置: {abs_db_str} (绝对路径)")

            # 4. 检查并转换 config_file
            config_file_str = self._config.get(
                "chinastock.config_file", "./config/terminal_config.json"
            )
            if config_file_str:
                config_path = Path(config_file_str)
                if not config_path.is_absolute():
                    abs_config_path = project_root / config_path
                    abs_config_str = str(abs_config_path.resolve())
                    self._config["chinastock.config_file"] = abs_config_str
                    path_updated = True
                    print("🔧 初始化配置转换: 终端配置文件")
                    print(f"   原配置: {config_file_str} (相对路径)")
                    print(f"   新配置: {abs_config_str} (绝对路径)")

            # 5. 检查并转换 logs_dir
            logs_dir_str = self._config.get("chinastock.logs_dir", "./logs")
            if logs_dir_str:
                logs_path = Path(logs_dir_str)
                if not logs_path.is_absolute():
                    abs_logs_path = project_root / logs_path
                    abs_logs_str = str(abs_logs_path.resolve())
                    self._config["chinastock.logs_dir"] = abs_logs_str
                    path_updated = True
                    print("🔧 初始化配置转换: 日志目录")
                    print(f"   原配置: {logs_dir_str} (相对路径)")
                    print(f"   新配置: {abs_logs_str} (绝对路径)")

            # 6. 如果有路径更新，保存到配置文件
            if path_updated:
                print(f"   项目根目录: {project_root}")
                print("✅ 配置已自动转换并持久化\n")
                self._save_to_file()
                logger.info("路径配置已在初始化时转换为绝对路径并持久化")

        except Exception as e:
            logger.warning("初始化路径转换失败: %s", e)

    def get_cache_dir(self) -> Path:
        """获取品种列表缓存目录

        注意：相对路径已在初始化时转换，此方法作为双重保险
        """
        cache_dir_str = self.get("chinastock.cache_dir", "./data/cache")
        cache_dir = Path(cache_dir_str)

        # 🔧 双重保险：如果仍是相对路径（用户手动修改配置后），再次转换
        if not cache_dir.is_absolute():
            project_root = get_project_root()
            cache_dir = project_root / cache_dir
            abs_path_str = str(cache_dir.resolve())
            self._config["chinastock.cache_dir"] = abs_path_str
            self._save_to_file()
            logger.warning("检测到相对路径配置，已转换: %s -> %s", cache_dir_str, abs_path_str)

        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir

    def get_data_dir(self) -> Path:
        """获取K线数据存储目录

        注意：相对路径已在初始化时转换，此方法作为双重保险
        """
        data_dir_str = self.get("chinastock.data_dir", "./data/kline")
        data_dir = Path(data_dir_str)

        # 🔧 双重保险：如果仍是相对路径（用户手动修改配置后），再次转换
        if not data_dir.is_absolute():
            project_root = get_project_root()
            data_dir = project_root / data_dir
            abs_path_str = str(data_dir.resolve())
            self._config["chinastock.data_dir"] = abs_path_str
            self._save_to_file()
            logger.warning("检测到相对路径配置，已转换: %s -> %s", data_dir_str, abs_path_str)

        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    def get_db_file(self) -> Path:
        """获取数据库文件路径

        注意：相对路径已在初始化时转换，此方法作为双重保险
        """
        db_file_str = self.get("chinastock.db_file", "./data/terminal.db")
        db_file = Path(db_file_str)

        # 🔧 双重保险：如果仍是相对路径（用户手动修改配置后），再次转换
        if not db_file.is_absolute():
            project_root = get_project_root()
            db_file = project_root / db_file
            abs_path_str = str(db_file.resolve())
            self._config["chinastock.db_file"] = abs_path_str
            self._save_to_file()
            logger.warning("检测到相对路径配置，已转换: %s -> %s", db_file_str, abs_path_str)

        db_file.parent.mkdir(parents=True, exist_ok=True)
        return db_file

    def get_config_file(self) -> Path:
        """获取终端配置文件路径

        注意：相对路径已在初始化时转换，此方法作为双重保险
        """
        config_file_str = self.get("chinastock.config_file", "./config/terminal_config.json")
        config_file = Path(config_file_str)

        # 🔧 双重保险：如果仍是相对路径（用户手动修改配置后），再次转换
        if not config_file.is_absolute():
            project_root = get_project_root()
            config_file = project_root / config_file
            abs_path_str = str(config_file.resolve())
            self._config["chinastock.config_file"] = abs_path_str
            self._save_to_file()
            logger.warning("检测到相对路径配置，已转换: %s -> %s", config_file_str, abs_path_str)

        config_file.parent.mkdir(parents=True, exist_ok=True)
        return config_file

    def get_logs_dir(self) -> Path:
        """获取日志目录

        注意：相对路径已在初始化时转换，此方法作为双重保险
        """
        logs_dir_str = self.get("chinastock.logs_dir", "./logs")
        logs_dir = Path(logs_dir_str)

        # 🔧 双重保险：如果仍是相对路径（用户手动修改配置后），再次转换
        if not logs_dir.is_absolute():
            project_root = get_project_root()
            logs_dir = project_root / logs_dir
            abs_path_str = str(logs_dir.resolve())
            self._config["chinastock.logs_dir"] = abs_path_str
            self._save_to_file()
            logger.warning("检测到相对路径配置，已转换: %s -> %s", logs_dir_str, abs_path_str)

        logs_dir.mkdir(parents=True, exist_ok=True)
        return logs_dir

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

    def is_unified_manager_enabled(self) -> bool:
        """是否启用统一数据管理器"""
        return bool(self.get("chinastock.unified_manager.enabled", True))

    def is_unified_manager_auto_download_enabled(self) -> bool:
        """统一数据管理器是否允许自动补全下载"""
        return bool(self.get("chinastock.unified_manager.auto_download", True))

    def is_preload_enabled(self) -> bool:
        """是否启用预加载服务"""
        return bool(self.get("chinastock.preload.enabled", True))

    def is_preload_auto_start(self) -> bool:
        """预加载服务是否自动启动"""
        return bool(self.get("chinastock.preload.auto_start", True))

    def get_preload_max_cache_symbols(self) -> int:
        """获取预加载缓存的最大品种数量"""
        return int(self.get("chinastock.preload.max_cache_symbols", 64))

    def get_preload_intervals(self) -> List[str]:
        """获取预加载的默认周期列表"""
        intervals = self.get("chinastock.preload.intervals", ["1d", "5m"])
        if isinstance(intervals, str):
            return [item.strip() for item in intervals.split(",") if item.strip()]
        if isinstance(intervals, list):
            return [str(item).strip() for item in intervals if str(item).strip()]
        return ["1d", "5m"]

    def get_preload_frequently_used_symbols(self) -> List[str]:
        """获取常用品种列表"""
        symbols = self.get("chinastock.preload.frequently_used_symbols", [])
        if isinstance(symbols, str):
            return [item.strip() for item in symbols.split(",") if item.strip()]
        if isinstance(symbols, list):
            return [str(item).strip() for item in symbols if str(item).strip()]
        return []

    # 🆕 数据质量感知配置访问方法

    def is_quality_scan_adaptive_enabled(self) -> bool:
        """是否启用自适应质量扫描"""
        return bool(self.get("chinastock.quality_scan.enable_adaptive", True))

    def is_quality_scan_detailed_enabled(self) -> bool:
        """是否启用详细质量扫描（错误/警告检查）"""
        return bool(self.get("chinastock.quality_scan.enable_detailed_scan", True))

    def is_quality_scan_incremental_push_enabled(self) -> bool:
        """是否启用增量推送"""
        return bool(self.get("chinastock.quality_scan.enable_incremental_push", True))

    def get_quality_scan_min_push_interval(self) -> int:
        """获取最小推送间隔（毫秒）"""
        return int(self.get("chinastock.quality_scan.min_push_interval_ms", 500))

    # 🆕 混合异步架构配置访问方法

    def is_quality_scan_hybrid_async_enabled(self) -> bool:
        """是否启用混合异步架构"""
        return bool(self.get("chinastock.quality_scan.enable_hybrid_async", True))

    def get_quality_scan_max_async_workers(self) -> int:
        """获取协程层最大并发数"""
        return int(self.get("chinastock.quality_scan.max_async_workers", 1000))

    def get_quality_scan_max_thread_workers(self) -> int:
        """获取线程层最大并发数"""
        return int(self.get("chinastock.quality_scan.max_thread_workers", 20))

    def get_quality_scan_max_process_workers(self) -> int:
        """获取进程层最大并发数"""
        return int(self.get("chinastock.quality_scan.max_process_workers", 8))

    def is_quality_scan_dynamic_tuning_enabled(self) -> bool:
        """是否启用动态并发调节"""
        return bool(self.get("chinastock.quality_scan.enable_dynamic_tuning", True))

    def get_quality_scan_file_size_threshold_small(self) -> int:
        """获取小文件大小阈值（字节）"""
        kb = int(self.get("chinastock.quality_scan.file_size_threshold_small_kb", 1024))
        return kb * 1024

    def get_quality_scan_file_size_threshold_large(self) -> int:
        """获取大文件大小阈值（字节）"""
        kb = int(self.get("chinastock.quality_scan.file_size_threshold_large_kb", 10240))
        return kb * 1024

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
