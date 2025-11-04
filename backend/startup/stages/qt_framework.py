# -*- coding: utf-8 -*-
"""
Qt框架初始化阶段 - 创建QApplication和EventEngine

阶段2：Qt框架初始化（10-20%）
- 创建QApplication
- 预创建EventEngine
- 加载主题系统
- 加载配置文件
"""

import logging
import os
import sys
import time

from backend.startup.stages.base import StartupStage, StageResult
from backend.startup.context import StartupContext

logger = logging.getLogger("backend.startup.stages.qt_framework")


class QtFrameworkStage(StartupStage):
    """Qt框架初始化阶段

    职责：
    - 创建QApplication
    - 预创建EventEngine
    - 预创建MainEngine（根据启动完整设计文档1082行）
    - 加载主题系统
    - 加载配置文件
    """

    def __init__(self):
        """初始化Qt框架阶段"""
        super().__init__(
            name="qt_framework",
            description="Qt框架初始化 - 创建QApplication和EventEngine",
        )

    async def _execute(self, context: StartupContext) -> StageResult:
        """执行Qt框架初始化逻辑

        Args:
            context: 启动上下文

        Returns:
            StageResult: 阶段执行结果
        """
        start_time = time.time()

        try:
            # 切换到qt_init阶段
            from backend.infrastructure.system_vnpy import get_logging_hub

            hub = get_logging_hub()
            hub.set_stage("qt_init")

            stage_logger = logging.getLogger("startup.stage")

            # 阶段2标题
            stage_logger.info("=" * 70, extra={"log_type": "STAGE_NODE", "scenario": "backend_init"})
            stage_logger.info("【阶段2: Qt应用框架】 (10-20%)", extra={"log_type": "STAGE_NODE", "scenario": "backend_init"})
            stage_logger.info("=" * 70, extra={"log_type": "STAGE_NODE", "scenario": "backend_init"})
            stage_logger.info("", extra={"log_type": "STAGE_NODE", "scenario": "backend_init"})

            stage_logger.info(
                "📍 阶段2: Qt应用框架开始", 
                extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
            )

            # 创建QApplication
            from PySide6.QtWidgets import QApplication

            app = QApplication(sys.argv)
            app.setApplicationName("星辰金融终端")
            app.setApplicationVersion("5.0.0")
            app.setOrganizationName("星辰科技")

            context.app = app

            stage_logger.info(
                "✅ QApplication创建完成", 
                extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
            )

            # 预创建EventEngine和MainEngine（根据启动完整设计文档1081-1082行）
            from vnpy.event import EventEngine
            from vnpy.trader.engine import MainEngine
            from backend.core.base import set_event_engine, set_main_engine

            event_engine = EventEngine()
            context.event_engine = event_engine
            set_event_engine(event_engine)  # 注册到全局，供后续阶段使用
            
            stage_logger.info(
                "✅ EventEngine预创建完成", 
                extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
            )

            # 预创建MainEngine（根据启动完整设计文档1082行）
            main_engine = MainEngine(event_engine)
            context.main_engine = main_engine
            set_main_engine(main_engine)  # 注册到全局，供后续阶段使用

            stage_logger.info(
                "✅ MainEngine预创建完成", 
                extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
            )

            # 主题系统加载
            try:
                from ui.components.theme_system import ThemeManager

                theme_manager = ThemeManager()
                # 尝试获取主题信息（如果方法存在）
                current_theme = "modern_dark"
                theme_config = "ui/components/themes.json"
                
                if hasattr(theme_manager, 'get_current_theme'):
                    try:
                        current_theme = getattr(theme_manager, 'get_current_theme')()
                    except Exception:
                        pass
                        
                if hasattr(theme_manager, 'get_theme_config_path'):
                    try:
                        theme_config = getattr(theme_manager, 'get_theme_config_path')()
                    except Exception:
                        pass

                stage_logger.info(
                    "✅ 主题系统加载完成", 
                    extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
                )
                stage_logger.info(
                    f"  - 当前主题: {current_theme}", 
                    extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
                )
                # 将主题配置路径转换为绝对路径
                if theme_config:
                    if not os.path.isabs(theme_config):
                        theme_config_abs = os.path.abspath(theme_config)
                    else:
                        theme_config_abs = theme_config
                else:
                    # 使用默认路径
                    theme_config_abs = os.path.abspath("ui/components/themes.json")
                stage_logger.info(
                    f"  - 主题配置: {theme_config_abs}", 
                    extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
                )
            except Exception as e:
                self.logger.warning(f"主题系统加载失败: {e}")

            # 启动画面显示
            stage_logger.info(
                "✅ 启动画面显示", 
                extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
            )

            # 加载配置文件
            from backend.core.config import init_settings

            config_file = os.getenv("CONFIG_FILE")
            if config_file:
                self.logger.debug(f"[QT-INIT] 从环境变量加载配置: {config_file}")
                init_settings(config_file)
            else:
                self.logger.debug("[QT-INIT] 使用默认配置")
                init_settings()

            elapsed_ms = (time.time() - start_time) * 1000

            stage_logger.info(
                f"✅ Qt框架就绪 ({elapsed_ms:.0f}ms)", 
                extra={"log_type": "STAGE_NODE", "scenario": "backend_init"}
            )

            return StageResult(
                success=True,
                message="Qt框架初始化完成",
                elapsed_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000

            return StageResult(
                success=False,
                message=f"Qt框架初始化失败: {str(e)}",
                elapsed_ms=elapsed_ms,
                error=e,
            )

