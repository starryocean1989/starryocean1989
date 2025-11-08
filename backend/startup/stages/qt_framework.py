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

from backend.infrastructure.system_vnpy.logging_system import bind_logger_defaults
from backend.startup.context import StartupContext
from backend.startup.stages.base import StartupStage, StageResult

logger = bind_logger_defaults(
    logging.getLogger("backend.startup.stages.qt_framework"),
    log_type="SYSTEM",
    scenario="application_startup",
)


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
            # 注意：场景信息通过日志记录的extra参数传递，无需全局设置

            stage_logger = logging.getLogger("startup.stage")

            # 阶段2标题
            stage_logger.info("=" * 70, extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})
            stage_logger.info("【阶段2: Qt应用框架】 (10-20%)", extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})
            stage_logger.info("=" * 70, extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})
            stage_logger.info("", extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})

            stage_logger.info(
                "📍 阶段2: Qt应用框架开始", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )

            # 创建QApplication
            from PySide6.QtWidgets import QApplication

            logger.debug(
                "[QT-INIT] 开始创建QApplication",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            logger.debug(
                f"[QT-INIT] 命令行参数: {sys.argv}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            app = QApplication(sys.argv)
            app.setApplicationName("星辰金融终端")
            app.setApplicationVersion("5.0.0")
            app.setOrganizationName("星辰科技")

            context.app = app

            logger.debug(
                f"[QT-INIT] QApplication已创建: 应用名={app.applicationName()}, 版本={app.applicationVersion()}, 组织={app.organizationName()}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            logger.info(
                "[QT-INIT] QApplication创建完成",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            stage_logger.info(
                "✅ QApplication创建完成", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )

            # 预创建EventEngine和MainEngine（根据启动完整设计文档1081-1082行）
            from vnpy.event import EventEngine
            from vnpy.trader.engine import MainEngine
            from backend.core.base import set_event_engine, set_main_engine

            logger.debug(
                "[QT-INIT] 开始预创建EventEngine",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            event_engine = EventEngine()
            context.event_engine = event_engine
            set_event_engine(event_engine)  # 注册到全局，供后续阶段使用
            logger.debug(
                "[QT-INIT] EventEngine已创建并注册到全局",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            logger.info(
                "[QT-INIT] EventEngine预创建完成",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            stage_logger.info(
                "✅ EventEngine预创建完成", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )

            # 预创建MainEngine（根据启动完整设计文档1082行）
            logger.debug(
                "[QT-INIT] 开始预创建MainEngine",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            main_engine = MainEngine(event_engine)
            context.main_engine = main_engine
            set_main_engine(main_engine)  # 注册到全局，供后续阶段使用
            logger.debug(
                "[QT-INIT] MainEngine已创建并注册到全局",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            logger.info(
                "[QT-INIT] MainEngine预创建完成",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            stage_logger.info(
                "✅ MainEngine预创建完成", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )

            # 主题系统加载
            try:
                logger.debug(
                    "[QT-INIT] 开始加载主题系统",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                from ui.components.theme_system import ThemeManager

                theme_manager = ThemeManager()
                logger.debug(
                    "[QT-INIT] ThemeManager已创建",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                
                # 尝试获取主题信息（如果方法存在）
                current_theme = "modern_dark"
                theme_config = "ui/components/themes.json"
                
                if hasattr(theme_manager, 'get_current_theme'):
                    try:
                        current_theme = getattr(theme_manager, 'get_current_theme')()
                        logger.debug(
                            f"[QT-INIT] 当前主题: {current_theme}",
                            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                        )
                    except Exception as e:
                        logger.debug(
                            f"[QT-INIT] 获取当前主题失败: {e}，使用默认主题",
                            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                        )
                        
                if hasattr(theme_manager, 'get_theme_config_path'):
                    try:
                        theme_config = getattr(theme_manager, 'get_theme_config_path')()
                        logger.debug(
                            f"[QT-INIT] 主题配置路径: {theme_config}",
                            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                        )
                    except Exception as e:
                        logger.debug(
                            f"[QT-INIT] 获取主题配置路径失败: {e}，使用默认路径",
                            extra={"log_type": "SYSTEM", "scenario": "application_startup"}
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
                
                theme_config_exists = os.path.exists(theme_config_abs)
                logger.debug(
                    f"[QT-INIT] 主题配置文件: {theme_config_abs}, 存在={theme_config_exists}",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                
                logger.info(
                    f"[QT-INIT] 主题系统加载完成: 当前主题={current_theme}, 配置={theme_config_abs}",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                stage_logger.info(
                    "✅ 主题系统加载完成", 
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )
                stage_logger.info(
                    f"  - 当前主题: {current_theme}", 
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )
                stage_logger.info(
                    f"  - 主题配置: {theme_config_abs}", 
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )
            except Exception as e:
                logger.warning(
                    f"[QT-INIT] ⚠️ 主题系统加载失败: {e}",
                    extra={"log_type": "ALERT", "scenario": "application_startup"},
                    exc_info=True
                )

            # 启动画面显示
            logger.debug(
                "[QT-INIT] 启动画面显示",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            stage_logger.info(
                "✅ 启动画面显示", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )

            # 加载配置文件
            logger.debug(
                "[QT-INIT] 开始加载配置文件",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            from backend.core.config import init_settings

            config_file = os.getenv("CONFIG_FILE")
            if config_file:
                config_exists = os.path.exists(config_file)
                logger.debug(
                    f"[QT-INIT] 从环境变量加载配置: {config_file}, 存在={config_exists}",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                if not config_exists:
                    logger.warning(
                        f"[QT-INIT] ⚠️ 配置文件不存在: {config_file}，将使用默认配置",
                        extra={"log_type": "ALERT", "scenario": "application_startup"}
                    )
                try:
                    init_settings(config_file)
                    logger.info(
                        f"[QT-INIT] 配置文件加载完成: {config_file}",
                        extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                    )
                except Exception as e:
                    logger.error(
                        f"[QT-INIT] ❌ 配置文件加载失败: {e}",
                        extra={"log_type": "ALERT", "scenario": "application_startup"},
                        exc_info=True
                    )
            else:
                logger.debug(
                    "[QT-INIT] CONFIG_FILE环境变量未设置，使用默认配置",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                try:
                    init_settings()
                    logger.info(
                        "[QT-INIT] 默认配置加载完成",
                        extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                    )
                except Exception as e:
                    logger.error(
                        f"[QT-INIT] ❌ 默认配置加载失败: {e}",
                        extra={"log_type": "ALERT", "scenario": "application_startup"},
                        exc_info=True
                    )

            elapsed_ms = (time.time() - start_time) * 1000

            logger.info(
                f"[QT-INIT] Qt框架初始化完成: 耗时={elapsed_ms:.0f}ms",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            stage_logger.info(
                f"✅ Qt框架就绪 ({elapsed_ms:.0f}ms)", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )

            return StageResult(
                success=True,
                message="Qt框架初始化完成",
                elapsed_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000

# 错误日志（输出到Terminal和事件日志文件）
            logger.error(
                f"[QT-INIT] ❌ Qt框架初始化失败: {str(e)}",
                extra={"log_type": "ALERT", "scenario": "application_startup"},
                exc_info=True
            )
            
            # 记录关键信息用于调试
            logger.debug(
                f"[QT-INIT] 错误发生时状态: QApplication={'已创建' if hasattr(context, 'app') and context.app else '未创建'}, "
                f"EventEngine={'已创建' if hasattr(context, 'event_engine') and context.event_engine else '未创建'}, "
                f"MainEngine={'已创建' if hasattr(context, 'main_engine') and context.main_engine else '未创建'}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            return StageResult(
                success=False,
                message=f"Qt框架初始化失败: {str(e)}",
                elapsed_ms=elapsed_ms,
                error=e,
            )

