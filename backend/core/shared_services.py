# -*- coding: utf-8 -*-
"""
共享服务层模块
提供统一的配置、日志、监控等服务
"""

import json
import logging
import logging.handlers
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
from datetime import datetime, timedelta
import threading
import time

# 导入核心模块
from .vnpy_integration import TerminalEngine, VNPY_AVAILABLE

# 导入统一导入
from .imports import psutil


class ConfigService:
    """统一配置管理服务"""

    def __init__(self, config_file: str = "config/terminal_config.json"):
        self.config_file = Path(config_file)
        self.logger = logging.getLogger(__name__)
        self._config: Dict[str, Any] = {}
        self._listeners: List[Callable] = []
        self._lock = threading.Lock()

        # 确保配置目录存在
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        # 加载配置
        self.load_config()

    def load_config(self) -> bool:
        """加载配置文件"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    self._config = json.load(f)
                self.logger.info("配置加载成功: %s", self.config_file)
                return True

            # 创建默认配置
            self._create_default_config()
            return self.save_config()

        except Exception as e:
            self.logger.error("加载配置失败: %s", e)
            self._create_default_config()
            return False

    def save_config(self) -> bool:
        """保存配置文件"""
        try:
            with self._lock:
                # 备份原文件
                backup_file = None
                if self.config_file.exists():
                    backup_file = self.config_file.with_suffix('.json.bak')
                    self.config_file.rename(backup_file)

                # 保存新配置
                with open(self.config_file, 'w', encoding='utf-8') as f:
                    json.dump(self._config, f, indent=2, ensure_ascii=False)

                # 恢复备份文件（如果存在）
                if backup_file and backup_file.exists():
                    backup_file.rename(
                        self.config_file.with_suffix('.json.bak'                    )
                )

                self.logger.info("配置保存成功: %s", self.config_file)
                return True

        except Exception as e:
            self.logger.error("保存配置失败: %s", e)
            return False

    def _create_default_config(self):
        """创建默认配置"""
        self._config = {
            "app": {
                "name": "星辰金融终端",
                "version": "5.0.0",
                "author": "星辰科技",
                "description": "专业的金融交易终端系统"
            },

            "ui": {
                "theme": "dark",
                "language": "zh_CN",
                "window_width": 1200,
                "window_height": 800,
                "min_width": 800,
                "min_height": 600,
                "font_size": 10,
                "refresh_interval": 1000
            },

            "vnpy": {
                "data_path": "data/vnpy",
                "log_path": "logs/vnpy",
                "cache_size": 1000,
                "timeout": 30
            },

            "gateways": {
                "ctp": {
                    "enabled": True,
                    "setting": {
                        "用户名": "",
                        "密码": "",
                        "经纪商代码": "",
                        "交易服务器": "",
                        "行情服务器": "",
                        "产品名称": "",
                        "授权编码": ""
                    }
                },
                "mini": {
                    "enabled": False,
                    "setting": {
                        "用户名": "",
                        "密码": "",
                        "经纪商代码": "",
                        "地址": "",
                        "端口": 0
                    }
                },
                "ib": {
                    "enabled": False,
                    "setting": {
                        "TWS地址": "127.0.0.1",
                        "TWS端口": 7497,
                        "客户端ID": 1
                    }
                }
            },

            "datafeeds": {
                "tushare": {
                    "enabled": True,
                    "token": "",
                    "timeout": 30
                },
                "rqdata": {
                    "enabled": False,
                    "username": "",
                    "password": "",
                    "timeout": 30
                }
            },

            "strategies": {
                "default_engine": "cta",
                "auto_start": False,
                "max_running": 10,
                "log_level": "INFO"
            },

            "system": {
                "log_level": "INFO",
                "log_max_size": 10485760,  # 10MB
                "log_backup_count": 5,
                "performance_monitor": True,
                "memory_warning_threshold": 80,
                "cpu_warning_threshold": 80
            }
        }

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值"""
        keys = key.split('.')
        value = self._config

        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default

        return value

    def set(self, key: str, value: Any) -> bool:
        """设置配置值"""
        try:
            keys = key.split('.')
            config = self._config

            # 导航到父级字典
            for k in keys[:-1]:
                if k not in config or not isinstance(config[k], dict):
                    config[k] = {}
                config = config[k]

            # 设置值
            config[keys[-1]] = value

            # 通知监听器
            self._notify_listeners(key, value)

            return True

        except Exception as e:
            self.logger.error("设置配置失败 %s: %s", key, e)
            return False

    def update(self, updates: Dict[str, Any]) -> bool:
        """批量更新配置"""
        try:
            with self._lock:
                def deep_update(d, u):
                    for k, v in u.items():
                        if (isinstance(v, dict) and k in d and
                                isinstance(d[k], dict)):
                            deep_update(d[k], v)
                        else:
                            d[k] = v

                deep_update(self._config, updates)

                # 通知监听器
                for key, value in updates.items():
                    self._notify_listeners(key, value)

                return True

        except Exception as e:
            self.logger.error("批量更新配置失败: %s", e)
            return False

    def add_listener(self, listener: Callable[[str, Any], None]):
        """添加配置变更监听器"""
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[str, Any], None]):
        """移除配置变更监听器"""
        try:
            self._listeners.remove(listener)
        except ValueError:
            pass

    def _notify_listeners(self, key: str, value: Any):
        """通知监听器配置变更"""
        for listener in self._listeners:
            try:
                listener(key, value)
            except Exception as e:
                self.logger.error("配置监听器执行失败: %s", e)

    def reload_config(self) -> bool:
        """重新加载配置"""
        return self.load_config()

    def export_config(self, export_file: str) -> bool:
        """导出配置到文件"""
        try:
            export_path = Path(export_file)
            export_path.parent.mkdir(parents=True, exist_ok=True)

            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(self._config, f, indent=2, ensure_ascii=False)

            self.logger.info("配置导出成功: %s", export_path)
            return True

        except Exception as e:
            self.logger.error("导出配置失败: %s", e)
            return False

    def import_config(self, import_file: str) -> bool:
        """从文件导入配置"""
        try:
            import_path = Path(import_file)
            if not import_path.exists():
                self.logger.error("导入配置文件不存在: %s", import_path)
                return False

            with open(import_path, 'r', encoding='utf-8') as f:
                imported_config = json.load(f)

            # 备份当前配置
            backup_config = self._config.copy()

            # 尝试导入
            self._config = imported_config

            # 验证导入的配置
            if self._validate_config():
                self.save_config()
                self.logger.info("配置导入成功: %s", import_path)
                return True

            # 恢复备份
            self._config = backup_config
            self.logger.error("导入配置验证失败，已恢复原配置")
            return False

        except Exception as e:
            self.logger.error("导入配置失败: %s", e)
            return False

    def _validate_config(self) -> bool:
        """验证配置有效性"""
        try:
            # 检查必需的顶级配置项
            required_keys = [
                "app", "ui", "vnpy", "gateways",
                "datafeeds", "strategies", "system"
            ]
            for key in required_keys:
                if key not in self._config:
                    self.logger.error("配置缺少必需项: %s", key)
                    return False

            # 检查UI配置
            ui_config = self._config["ui"]
            if not isinstance(ui_config.get("window_width"), int):
                self.logger.error("UI配置中window_width必须为整数")
                return False

            return True

        except Exception as e:
            self.logger.error("配置验证失败: %s", e)
            return False


class LoggingService:
    """统一日志管理服务"""

    def __init__(self, config_service: ConfigService):
        self.config_service = config_service
        self.logger = logging.getLogger(__name__)
        self._handlers: Dict[str, logging.Handler] = {}
        self._formatters: Dict[str, logging.Formatter] = {}
        self._lock = threading.Lock()

        # 初始化日志格式器
        self._init_formatters()

        # 初始化日志处理器
        self._init_handlers()

        # 配置根日志器
        self._configure_root_logger()

    def _init_formatters(self):
        """初始化日志格式器"""
        self._formatters = {
            "console": logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            ),
            "file": logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:'
                '%(lineno)d - %(message)s'
            ),
            "detailed": logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(funcName)s() - '
                '%(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
        }

    def _init_handlers(self):
        """初始化日志处理器"""
        config = self.config_service.get("system", {})

        # 控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(self._formatters["console"])
        console_handler.setLevel(
            getattr(logging, config.get("log_level", "INFO").upper())
        )
        self._handlers["console"] = console_handler

        # 文件处理器
        log_file = config.get("log_file", "logs/terminal.log")
        try:
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=config.get("log_max_size", 10485760),
                backupCount=config.get("log_backup_count", 5),
                encoding='utf-8'
            )
            file_handler.setFormatter(self._formatters["file"])
            file_handler.setLevel(logging.DEBUG)
            self._handlers["file"] = file_handler

        except Exception as e:
            self.logger.error("创建文件日志处理器失败: %s", e)

    def _configure_root_logger(self):
        """配置根日志器"""
        root_logger = logging.getLogger()

        # 清空现有处理器
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)

        # 添加新处理器
        for handler in self._handlers.values():
            root_logger.addHandler(handler)

        # 设置日志级别
        config = self.config_service.get("system", {})
        level = getattr(logging, config.get("log_level", "INFO").upper())
        root_logger.setLevel(level)

    def get_logger(self, name: str) -> logging.Logger:
        """获取指定名称的日志器"""
        return logging.getLogger(name)

    def set_level(self, level: str):
        """设置日志级别"""
        try:
            config = self.config_service.get("system", {})
            config["log_level"] = level
            self.config_service.set("system.log_level", level)

            # 更新所有处理器级别
            level_enum = getattr(logging, level.upper())
            for handler in self._handlers.values():
                handler.setLevel(level_enum)

            self.logger.info("日志级别已设置为: %s", level)

        except Exception as e:
            self.logger.error("设置日志级别失败: %s", e)

    def add_file_handler(self, name: str, file_path: str, level: str = "INFO"):
        """添加文件处理器"""
        try:
            log_path = Path(file_path)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            handler = logging.FileHandler(file_path, encoding='utf-8')
            handler.setFormatter(self._formatters["file"])
            handler.setLevel(getattr(logging, level.upper()))

            self._handlers[name] = handler

            # 添加到根日志器
            root_logger = logging.getLogger()
            root_logger.addHandler(handler)

            self.logger.info("文件日志处理器添加成功: %s", name)

        except Exception as e:
            self.logger.error("添加文件日志处理器失败 %s: %s", name, e)

    def remove_handler(self, name: str):
        """移除日志处理器"""
        if name in self._handlers:
            try:
                handler = self._handlers[name]

                # 从根日志器移除
                root_logger = logging.getLogger()
                root_logger.removeHandler(handler)

                # 关闭处理器
                handler.close()

                del self._handlers[name]
                self.logger.info("日志处理器移除成功: %s", name)

            except Exception as e:
                self.logger.error("移除日志处理器失败 %s: %s", name, e)


class MonitoringService:
    """统一监控服务"""

    def __init__(self, config_service: ConfigService,
                 terminal_engine: TerminalEngine):
        self.config_service = config_service
        self.terminal_engine = terminal_engine
        self.logger = logging.getLogger(__name__)

        self._monitoring_data: Dict[str, Any] = {}
        self._alerts: List[Dict[str, Any]] = []
        self._performance_history: List[Dict[str, Any]] = []

        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        # 启动监控
        self.start_monitoring()

    def start_monitoring(self):
        """启动监控"""
        if self._monitor_thread and self._monitor_thread.is_alive():
            return

        self._stop_event.clear()
        self._monitor_thread = threading.Thread(
            target=self._monitoring_loop, daemon=True
        )
        self._monitor_thread.start()
        self.logger.info("监控服务已启动")

    def stop_monitoring(self):
        """停止监控"""
        self._stop_event.set()

        if self._monitor_thread:
            self._monitor_thread.join(timeout=5)

        self.logger.info("监控服务已停止")

    def _monitoring_loop(self):
        """监控循环"""
        interval = 5  # 监控间隔（秒）

        while not self._stop_event.is_set():
            try:
                # 收集系统性能数据
                self._collect_system_metrics()

                # 收集VNPY状态数据
                self._collect_vnpy_metrics()

                # 检查告警条件
                self._check_alerts()

                # 保存历史数据
                self._save_performance_history()

                # 等待下次监控
                self._stop_event.wait(interval)

            except Exception as e:
                self.logger.error("监控循环异常: %s", e)
                time.sleep(interval)

    def _collect_system_metrics(self):
        """收集系统性能指标"""
        try:
            if not psutil:
                return

            timestamp = datetime.now()

            # CPU使用率
            cpu_percent = psutil.cpu_percent(interval=1)

            # 内存使用情况
            memory = psutil.virtual_memory()

            # 磁盘使用情况
            disk = psutil.disk_usage('/')

            # 网络状态
            network = psutil.net_if_stats()

            metrics = {
                "timestamp": timestamp,
                "cpu_percent": cpu_percent,
                "memory_percent": memory.percent,
                "memory_used": memory.used,
                "memory_available": memory.available,
                "disk_percent": disk.percent,
                "disk_used": disk.used,
                "disk_free": disk.free,
                "network_interfaces": len(network),
                "active_connections": len(psutil.net_connections())
            }

            with self._lock:
                self._monitoring_data["system"] = metrics

        except Exception as e:
            self.logger.error("收集系统指标失败: %s", e)

    def _collect_vnpy_metrics(self):
        """收集VNPY指标"""
        try:
            if not VNPY_AVAILABLE:
                return

            timestamp = datetime.now()
            status = self.terminal_engine.get_status()

            metrics = {
                "timestamp": timestamp,
                "vnpy_available": status.get("vnpy_available", False),
                "connected_gateways": status.get("connected_gateways", 0),
                "subscribed_symbols": status.get("subscribed_symbols", 0),
                "active_strategies": 0,
                "gateway_count": len(status.get("gateways", {})),
                "datafeed_count": len(status.get("datafeeds", {}))
            }

            # 计算活跃策略数量
            for engine_info in status.get(
                    "strategy_engines", {}).values():
                metrics["active_strategies"] += engine_info.get(
                    "strategies", 0)

            with self._lock:
                self._monitoring_data["vnpy"] = metrics

        except Exception as e:
            self.logger.error("收集VNPY指标失败: %s", e)

    def _check_alerts(self):
        """检查告警条件"""
        try:
            config = self.config_service.get("system", {})
            cpu_threshold = config.get("cpu_warning_threshold", 80)
            memory_threshold = config.get("memory_warning_threshold", 80)

            current_metrics = self._monitoring_data.get("system", {})

            if not current_metrics:
                return

            alerts_to_add = []

            # CPU告警
            if current_metrics.get("cpu_percent", 0) > cpu_threshold:
                alert = {
                    "timestamp": datetime.now(),
                    "type": "cpu_warning",
                    "level": "warning",
                    "message": f"CPU使用率过高: "
                               f"{current_metrics['cpu_percent']:.1f}%",
                    "metric": "cpu_percent",
                    "value": current_metrics["cpu_percent"],
                    "threshold": cpu_threshold
                }
                alerts_to_add.append(alert)

            # 内存告警
            if (current_metrics.get("memory_percent", 0) >
                    memory_threshold):
                alert = {
                    "timestamp": datetime.now(),
                    "type": "memory_warning",
                    "level": "warning",
                    "message": f"内存使用率过高: "
                               f"{current_metrics['memory_percent']:.1f}%",
                    "metric": "memory_percent",
                    "value": current_metrics["memory_percent"],
                    "threshold": memory_threshold
                }
                alerts_to_add.append(alert)

            # 添加新告警
            if alerts_to_add:
                with self._lock:
                    self._alerts.extend(alerts_to_add)

                    # 限制告警数量
                    if len(self._alerts) > 1000:
                        self._alerts = self._alerts[-500:]

                # 记录告警日志
                for alert in alerts_to_add:
                    self.logger.warning("监控告警: %s", alert['message'])

        except Exception as e:
            self.logger.error("检查告警失败: %s", e)

    def _save_performance_history(self):
        """保存性能历史数据"""
        try:
            if not self._monitoring_data:
                return

            history_entry = {
                "timestamp": datetime.now(),
                "system": self._monitoring_data.get("system", {}),
                "vnpy": self._monitoring_data.get("vnpy", {})
            }

            with self._lock:
                self._performance_history.append(
                    history_entry
                )

                # 限制历史数据数量
                max_history = 3600  # 保存1小时的历史数据（每5秒一个点）
                if len(self._performance_history) > max_history:
                    self._performance_history = self._performance_history[
                        -max_history:]

        except Exception as e:
            self.logger.error("保存性能历史失败: %s", e)

    def get_current_metrics(self) -> Dict[str, Any]:
        """获取当前监控指标"""
        with self._lock:
            return self._monitoring_data.copy()

    def get_performance_history(self, hours: int = 1) -> List[Dict[str, Any]]:
        """获取性能历史数据"""
        with self._lock:
            cutoff_time = datetime.now() - timedelta(hours=hours)
            return [
                entry for entry in self._performance_history
                if entry["timestamp"] >= cutoff_time
            ]

    def get_alerts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取告警列表"""
        with self._lock:
            return self._alerts[-limit:] if self._alerts else []

    def clear_alerts(self):
        """清空告警"""
        with self._lock:
            self._alerts.clear()
        self.logger.info("告警已清空")

    def get_system_health_score(self) -> float:
        """获取系统健康评分"""
        try:
            metrics = self._monitoring_data.get("system", {})

            if not metrics:
                return 0.0

            score = 100.0

            # CPU评分
            cpu_score = max(0, 100 - metrics.get("cpu_percent", 0))
            score = min(score, cpu_score)

            # 内存评分
            memory_score = max(0, 100 - metrics.get("memory_percent", 0))
            score = min(score, memory_score)

            # 磁盘评分
            disk_score = max(0, 100 - metrics.get("disk_percent", 0))
            score = min(score, disk_score)

            return round(score, 1)

        except Exception as e:
            self.logger.error("计算健康评分失败: %s", e)
            return 0.0

    def __del__(self):
        """析构函数，确保监控线程被停止"""
        self.stop_monitoring()


# 导出公共接口
__all__ = [
    'ConfigService', 'LoggingService', 'MonitoringService'
]
