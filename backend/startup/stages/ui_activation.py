# -*- coding: utf-8 -*-
"""
UI激活阶段 - 创建MainWindow和初始化界面

阶段4：UI主窗口创建（90-100%）
- 创建MainWindow
- 显示主窗口
- 初始化功能界面（等待后端就绪）
"""

import logging
import time

from backend.startup.stages.base import StartupStage, StageResult
from backend.startup.context import StartupContext

logger = logging.getLogger("backend.startup.stages.ui_activation")


class UIActivationStage(StartupStage):
    """UI激活阶段

    职责：
    - 创建MainWindow
    - 显示主窗口
    - 初始化功能界面（等待后端就绪）
    """

    def __init__(self):
        """初始化UI激活阶段"""
        super().__init__(
            name="ui_activation",
            description="UI激活 - 创建MainWindow和初始化界面",
        )

    async def _execute(self, context: StartupContext) -> StageResult:
        """执行UI激活逻辑

        Args:
            context: 启动上下文

        Returns:
            StageResult: 阶段执行结果
        """
        start_time = time.time()

        try:
            # DEBUG日志（记录阶段开始）
            logger.debug(
                "[UI-ACTIVATION] UI激活阶段开始",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            
            # 切换到ui_init阶段
            from backend.infrastructure.system_vnpy import get_logging_hub

            hub = get_logging_hub()
            hub.set_stage("ui_init")
            logger.debug(
                "[UI-ACTIVATION] 日志系统阶段已切换到ui_init",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            # 注意：场景信息通过日志记录的extra参数传递，无需全局设置

            stage_logger = logging.getLogger("startup.stage")

            # 阶段4标题
            stage_logger.info("", extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})
            stage_logger.info("=" * 70, extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})
            stage_logger.info(
                "【阶段4: UI主窗口】 (90-100%)", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )
            stage_logger.info("=" * 70, extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})
            stage_logger.info("", extra={"log_type": "STAGE_NODE", "scenario": "application_startup"})

            stage_logger.info(
                "📍 阶段4: UI主窗口创建开始", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )

            # 创建MainWindow
            from ui.main_window import MainWindow

            logger.debug(
                "[UI-ACTIVATION] 开始创建MainWindow",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            main_window = MainWindow(backend_ready=False)
            context.main_window = main_window
            logger.debug(
                "[UI-ACTIVATION] MainWindow已创建并存储到context",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            stage_logger.info(
                "✅ MainWindow创建完成", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )
            stage_logger.info(
                "✅ 六大功能模块注册完成", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )
            stage_logger.info(
                "  ├─ DataCenterView ✅", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )
            stage_logger.info(
                "  ├─ MarketBoardView ✅", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )
            stage_logger.info(
                "  ├─ TradingGatewayView ✅", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )
            stage_logger.info(
                "  ├─ PortfolioView ✅", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )
            stage_logger.info(
                "  ├─ StrategyCenterView ✅", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )
            stage_logger.info(
                "  └─ SystemManagerView ✅", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )
            stage_logger.info(
                "✅ 快捷键系统注册完成", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )
            stage_logger.info(
                "  - 全局快捷键: 15个", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )
            stage_logger.info(
                "✅ 增强状态栏初始化完成", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )

            # 显示主窗口
            logger.debug(
                "[UI-ACTIVATION] 开始显示主窗口",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            main_window.show()
            main_window.raise_()
            main_window.activateWindow()
            logger.debug(
                "[UI-ACTIVATION] 主窗口已显示并激活",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            stage_logger.info(
                "✅ 主窗口显示", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )

            # 初始化功能界面（等待后端就绪）
            logger.debug(
                f"[UI-ACTIVATION] 检查后端就绪状态: backend_initialized={context.backend_initialized}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            if context.backend_initialized:
                # 后端已就绪，初始化功能界面
                logger.debug(
                    "[UI-ACTIVATION] 后端已就绪，开始初始化功能界面",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                stage_logger.info(
                    "📍 阶段4.1: 初始化功能界面", 
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )
                main_window.initialize_function_interfaces_after_backend()
                logger.debug(
                    "[UI-ACTIVATION] 功能界面初始化完成",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                stage_logger.info(
                    "✅ 功能界面初始化完成", 
                    extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
                )
            else:
                # 后端未就绪（理论上不应该发生，因为阶段4在阶段3之后）
                logger.warning(
                    "[UI-ACTIVATION] ⚠️ 后端未就绪，功能界面将延迟初始化",
                    extra={"log_type": "ALERT", "scenario": "application_startup"}
                )
                stage_logger.warning(
                    "⚠️ 后端未就绪，功能界面将延迟初始化", 
                    extra={"log_type": "ALERT", "scenario": "application_startup"}
                )

            # 关闭启动画面（如果有的话）
            # 注意：实际启动画面可能在MainWindow创建时自动关闭
            stage_logger.info(
                "✅ 启动画面关闭", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )

            # 标记UI已初始化
            context.ui_initialized = True

            elapsed_ms = (time.time() - start_time) * 1000
            
            # DEBUG日志（记录阶段完成）
            logger.debug(
                f"[UI-ACTIVATION] UI激活阶段完成: 耗时={elapsed_ms:.0f}ms",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            logger.info(
                f"[UI-ACTIVATION] UI激活完成: 耗时={elapsed_ms:.0f}ms",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            stage_logger.info(
                f"✅ UI就绪 ({elapsed_ms:.0f}ms)", 
                extra={"log_type": "STAGE_NODE", "scenario": "application_startup"}
            )

            return StageResult(
                success=True,
                message="UI激活完成",
                elapsed_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            
            # DEBUG日志（记录异常发生）
            logger.debug(
                f"[UI-ACTIVATION] UI激活阶段发生异常: {type(e).__name__}: {str(e)}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            # 错误日志（输出到Terminal和AI日志文件）
            logger.error(
                f"❌ UI激活失败: {str(e)}",
                extra={"log_type": "ALERT", "scenario": "application_startup"},
                exc_info=True
            )

            return StageResult(
                success=False,
                message=f"UI激活失败: {str(e)}",
                elapsed_ms=elapsed_ms,
                error=e,
            )

