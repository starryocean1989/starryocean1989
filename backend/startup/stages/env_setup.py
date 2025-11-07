# -*- coding: utf-8 -*-
"""
环境准备阶段 - 设置必要的环境变量和Python路径

阶段0：环境准备（< 100ms）
- 设置环境变量
- 设置Python路径
- 不涉及任何业务逻辑
"""

import logging
import os
import sys
import time
from logging.handlers import MemoryHandler
from pathlib import Path

from backend.startup.stages.base import StartupStage, StageResult
from backend.startup.context import StartupContext

logger = logging.getLogger("backend.startup.stages.env_setup")


class EnvSetupStage(StartupStage):
    """环境准备阶段

    职责：
    - 设置必要的环境变量
    - 设置Python路径
    - 不涉及任何业务逻辑
    """

    def __init__(self):
        """初始化环境准备阶段"""
        super().__init__(
            name="env_setup",
            description="环境准备 - 设置必要的环境变量和Python路径",
        )

    async def _execute(self, context: StartupContext) -> StageResult:
        """执行环境准备逻辑

        Args:
            context: 启动上下文

        Returns:
            StageResult: 阶段执行结果
        """
        start_time = time.time()

        try:
            # 统一使用日志输出到终端（简版）
            logger.info("=" * 70, extra={"log_type": "STAGE_NODE"})
            logger.info("【阶段0: 环境准备】 (0-5%)", extra={"log_type": "STAGE_NODE"})
            logger.info("=" * 70, extra={"log_type": "STAGE_NODE"})
            logger.info("📍 阶段0: 环境准备开始", extra={"log_type": "STAGE_NODE"})

            # 禁用Python字节码缓存，确保总是使用最新代码
            os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
            sys.dont_write_bytecode = True
            logger.info("✅ Python字节码缓存已禁用", extra={"log_type": "STAGE_NODE"})
            
# DEBUG日志（只写入事件日志文件）
            logger.debug(
                f"[ENV-SETUP] Python解释器: {sys.executable}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            logger.debug(
                f"[ENV-SETUP] Python版本: {sys.version}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            logger.debug(
                f"[ENV-SETUP] 平台: {sys.platform}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            logger.debug(
                f"[ENV-SETUP] Python路径条目数: {len(sys.path)}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            logger.debug(
                f"[ENV-SETUP] 已禁用字节码缓存: PYTHONDONTWRITEBYTECODE={os.environ.get('PYTHONDONTWRITEBYTECODE')}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            
            # INFO日志（记录关键配置）
            logger.info(
                f"[ENV-SETUP] 环境准备: Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} on {sys.platform}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            # 设置项目路径
            project_root = context.project_root
            path_already_in_sys_path = str(project_root) in sys.path
            if not path_already_in_sys_path:
                sys.path.insert(0, str(project_root))
                logger.debug(
                    f"[ENV-SETUP] 项目路径已添加到sys.path首位: {project_root}",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
            else:
                logger.debug(
                    f"[ENV-SETUP] 项目路径已存在于sys.path: {project_root}",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
            logger.info("✅ 项目路径已添加到sys.path", extra={"log_type": "STAGE_NODE"})
            
# DEBUG日志（只写入事件日志文件）
            logger.debug(
                f"[ENV-SETUP] 项目根目录: {project_root}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            logger.debug(
                f"[ENV-SETUP] sys.path条目数: {len(sys.path)}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            logger.debug(
                f"[ENV-SETUP] sys.path前5项: {sys.path[:5]}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            # 设置Python解释器路径（WebEngine子进程需要）
            python_executable_set = False
            if not os.environ.get("PYTHONEXECUTABLE"):
                os.environ["PYTHONEXECUTABLE"] = sys.executable
                python_executable_set = True
                logger.debug(
                    f"[ENV-SETUP] 设置PYTHONEXECUTABLE: {sys.executable}",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
            else:
                logger.debug(
                    f"[ENV-SETUP] PYTHONEXECUTABLE已存在: {os.environ.get('PYTHONEXECUTABLE')}",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
            
            qt_webengine_set = False
            if not os.environ.get("QT_WEBENGINE_PYTHON_EXECUTABLE"):
                os.environ["QT_WEBENGINE_PYTHON_EXECUTABLE"] = sys.executable
                qt_webengine_set = True
                logger.debug(
                    f"[ENV-SETUP] 设置QT_WEBENGINE_PYTHON_EXECUTABLE: {sys.executable}",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
            else:
                logger.debug(
                    f"[ENV-SETUP] QT_WEBENGINE_PYTHON_EXECUTABLE已存在: {os.environ.get('QT_WEBENGINE_PYTHON_EXECUTABLE')}",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
            
            if python_executable_set or qt_webengine_set:
                logger.info("✅ Python解释器路径已设置", extra={"log_type": "STAGE_NODE"})
                logger.info("✅ Qt WebEngine解释器路径已设置", extra={"log_type": "STAGE_NODE"})

            # 设置Qt环境变量（避免缩放问题）
            os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
            os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
            logger.info("✅ Qt高DPI缩放已配置", extra={"log_type": "STAGE_NODE"})
            
            # DEBUG日志（记录Qt环境变量配置）
            logger.debug(
                f"[ENV-SETUP] Qt环境变量: QT_AUTO_SCREEN_SCALE_FACTOR={os.environ.get('QT_AUTO_SCREEN_SCALE_FACTOR')}, "
                f"QT_ENABLE_HIGHDPI_SCALING={os.environ.get('QT_ENABLE_HIGHDPI_SCALING')}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            # 设置配置文件路径
            config_file = project_root / "config" / "terminal_config.json"
            context.config_file = str(config_file)
            os.environ["CONFIG_FILE"] = str(config_file)
            logger.info("✅ 配置文件路径已设置", extra={"log_type": "STAGE_NODE"})
            
# DEBUG日志（只写入事件日志文件）
            logger.debug(
                f"[ENV-SETUP] 配置文件路径: {config_file}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            config_exists = config_file.exists()
            logger.debug(
                f"[ENV-SETUP] 配置文件存在: {config_exists}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            if config_exists:
                config_size = config_file.stat().st_size
                logger.debug(
                    f"[ENV-SETUP] 配置文件大小: {config_size} bytes",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
            else:
                logger.warning(
                    f"[ENV-SETUP] ⚠️ 配置文件不存在: {config_file}，将使用默认配置",
                    extra={"log_type": "ALERT", "scenario": "application_startup"}
                )

            # 注意：网络时间同步已移至阶段3的8步验证流程（步骤2）中执行
            # 这里不再执行网络时间同步，确保单一事实原则

            # 关键：在环境准备阶段完成后，立即设置MemoryHandler缓冲所有日志
            # 防止在日志系统初始化之前有任何日志输出
            root_logger = logging.getLogger()
            existing_handlers_count = len(root_logger.handlers)
            logger.debug(
                f"[ENV-SETUP] 清理现有handlers: {existing_handlers_count}个",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            
            # 移除已有的handlers（如果有）
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
                if hasattr(handler, 'close'):
                    try:
                        handler.close()
                    except Exception:
                        pass
            
            # 创建MemoryHandler作为临时缓冲（容量10000条）
            # target先设为None，日志系统初始化后再设置
            memory_handler = MemoryHandler(capacity=10000, target=None)
            memory_handler.setLevel(logging.DEBUG)
            root_logger.setLevel(logging.DEBUG)
            root_logger.addHandler(memory_handler)
            
            logger.debug(
                f"[ENV-SETUP] MemoryHandler已创建: 容量={memory_handler.capacity}条, 级别={logging.getLevelName(memory_handler.level)}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            
            # 存储到context中，供日志系统初始化阶段使用
            context._memory_handler = memory_handler

            elapsed_ms = (time.time() - start_time) * 1000

            # 输出完成信息（终端简版阶段日志）
            logger.info(
                f"✅ 环境准备完成 ({elapsed_ms:.0f}ms)",
                extra={"log_type": "STAGE_NODE"},
            )
            
            # INFO日志（记录环境准备完成信息）
            logger.info(
                f"[ENV-SETUP] 环境准备完成: 耗时={elapsed_ms:.0f}ms, 项目路径={project_root}, "
                f"配置文件={'存在' if config_file.exists() else '不存在'}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            return StageResult(
                success=True,
                message="环境准备完成",
                elapsed_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            # 终端简版错误（阶段日志）
            logger.error(
                f"❌ 环境准备失败: {str(e)}",
                extra={"log_type": "STAGE_NODE"},
            )
            
# 错误日志（输出到Terminal和事件日志文件）
            logger.error(
                f"❌ 环境准备失败: {str(e)}",
                extra={"log_type": "ALERT", "scenario": "application_startup"},
                exc_info=True
            )
            
            # 记录关键环境信息用于调试
            logger.debug(
                f"[ENV-SETUP] 错误发生时环境信息: Python={sys.executable}, 平台={sys.platform}, "
                f"项目路径={getattr(context, 'project_root', 'N/A')}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            return StageResult(
                success=False,
                message=f"环境准备失败: {str(e)}",
                elapsed_ms=elapsed_ms,
                error=e,
            )

