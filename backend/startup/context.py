# -*- coding: utf-8 -*-
"""
启动上下文 - 所有启动依赖的统一管理

提供统一的依赖注入容器，管理启动过程中的所有依赖关系。
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger("backend.startup.context")


class StartupContext:
    """启动上下文 - 所有启动依赖的统一管理

    职责：
    - 统一管理所有启动依赖
    - 提供依赖注入容器
    - 验证依赖完整性
    """

    def __init__(self):
        """初始化启动上下文"""
        # 底层基础设施
        self.event_engine: Optional[Any] = None
        self.main_engine: Optional[Any] = None
        self.china_stock_engine: Optional[Any] = None

        # 后端服务
        self.data_service: Optional[Any] = None
        self.trading_service: Optional[Any] = None
        self.strategy_service: Optional[Any] = None
        self.ai_assistant_service: Optional[Any] = None
        self.portfolio_service: Optional[Any] = None
        self.market_board_service: Optional[Any] = None
        self.system_manager_service: Optional[Any] = None

        # 进程管理
        self.monitor_process: Optional[subprocess.Popen] = None
        self.monitor_process_pid: Optional[int] = None

        # 服务管理器（从backend.core.base导入）
        from backend.core.base import get_service_manager

        self.service_manager = get_service_manager()

        # Qt应用
        self.app: Optional[Any] = None
        self.main_window: Optional[Any] = None

        # 启动配置
        self.project_root: Path = Path(__file__).parent.parent.parent
        self.config_file: Optional[str] = None

        # 启动标志
        self.logging_hub_initialized: bool = False
        self.backend_initialized: bool = False
        self.ui_initialized: bool = False

        # UI预加载
        self.ui_preload_task = None  # asyncio.Task
        self.ui_preloaded: bool = False
        
        # 阶段结果存储（用于日志输出）
        self.stage_results: Dict[str, Any] = {}
        
        # MemoryHandler（环境准备阶段设置，日志系统初始化阶段使用）
        self._memory_handler: Optional[Any] = None

    def validate(self, required_deps: Optional[list] = None) -> bool:
        """验证所有必需的依赖是否已初始化

        Args:
            required_deps: 必需依赖列表，如果为None则使用默认列表

        Returns:
            bool: 所有必需依赖都已初始化返回True，否则返回False
        """
        if required_deps is None:
            required_deps = ["app", "event_engine"]

        for dep in required_deps:
            if getattr(self, dep, None) is None:
                logger.warning(f"必需依赖 {dep} 未初始化")
                return False

        return True

    def get_service(self, service_name: str) -> Optional[Any]:
        """获取已注册的服务

        Args:
            service_name: 服务名称

        Returns:
            服务实例，如果未找到返回None
        """
        return self.service_manager.get_service(service_name)

    def register_service(self, service_name: str, service: Any) -> bool:
        """注册服务到服务管理器

        Args:
            service_name: 服务名称
            service: 服务实例

        Returns:
            bool: 注册成功返回True，否则返回False
        """
        return self.service_manager.register_service(service_name, service)

    def set_engines(self, event_engine: Any, main_engine: Any, china_stock_engine: Any = None):
        """设置VnPy引擎实例

        Args:
            event_engine: EventEngine实例
            main_engine: MainEngine实例
            china_stock_engine: ChinaStockEngine实例（可选）
        """
        self.event_engine = event_engine
        self.main_engine = main_engine
        if china_stock_engine is not None:
            self.china_stock_engine = china_stock_engine

        # 注册到全局访问
        from backend.core.base import set_event_engine, set_main_engine, set_china_stock_engine

        set_event_engine(event_engine)
        set_main_engine(main_engine)
        if china_stock_engine is not None:
            set_china_stock_engine(china_stock_engine)

    def set_monitor_process(self, process: subprocess.Popen):
        """设置监控进程

        Args:
            process: 监控进程Popen对象
        """
        self.monitor_process = process
        self.monitor_process_pid = process.pid

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（用于日志和调试）

        Returns:
            Dict: 包含所有依赖状态的字典
        """
        return {
            "event_engine": self.event_engine is not None,
            "main_engine": self.main_engine is not None,
            "china_stock_engine": self.china_stock_engine is not None,
            "app": self.app is not None,
            "main_window": self.main_window is not None,
            "monitor_process_pid": self.monitor_process_pid,
            "logging_hub_initialized": self.logging_hub_initialized,
            "backend_initialized": self.backend_initialized,
            "ui_initialized": self.ui_initialized,
        }

