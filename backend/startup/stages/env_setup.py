# -*- coding: utf-8 -*-
"""
环境准备阶段 - 设置必要的环境变量和Python路径

阶段0：环境准备（< 100ms）
- 设置环境变量
- 设置Python路径
- 不涉及任何业务逻辑
"""

import importlib
import logging
import os
import sys
import time
from logging.handlers import MemoryHandler
from pathlib import Path
from typing import Dict

from backend.infrastructure.system_vnpy.logging_system import bind_logger_defaults
from backend.startup.stages.base import StartupStage, StageResult
from backend.startup.context import StartupContext

logger = bind_logger_defaults(
    logging.getLogger("backend.startup.stages.env_setup"),
    log_type="SYSTEM",
    scenario="application_startup",
)


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
            scenario = "application_startup"
            stage_logger = logging.getLogger("startup.stage")

            # 确保早期阶段日志不会被提升的root级别吞掉（start_new.py启动时将root设为CRITICAL）
            root_logger = logging.getLogger()
            if root_logger.level > logging.DEBUG:
                root_logger.setLevel(logging.DEBUG)

            # 在记录任何阶段日志前，移除默认控制台handler并启用MemoryHandler缓冲
            if getattr(context, "_memory_handler", None) is None:
                existing_handlers = root_logger.handlers[:]
                for handler in existing_handlers:
                    root_logger.removeHandler(handler)
                    if hasattr(handler, "close"):
                        try:
                            handler.close()
                        except Exception:
                            pass

                memory_handler = MemoryHandler(capacity=10000, target=None)
                memory_handler.setLevel(logging.DEBUG)
                root_logger.addHandler(memory_handler)
                root_logger.setLevel(logging.DEBUG)
                context._memory_handler = memory_handler
            else:
                memory_handler = context._memory_handler

            stage_logger.setLevel(logging.INFO)

            # 阶段标题（严格按照标准输出格式）
            stage_logger.info("=" * 70, extra={"log_type": "STAGE_NODE", "scenario": scenario})
            stage_logger.info("【阶段0: 环境准备】 (0-5%)", extra={"log_type": "STAGE_NODE", "scenario": scenario})
            stage_logger.info("=" * 70, extra={"log_type": "STAGE_NODE", "scenario": scenario})
            stage_logger.info("", extra={"log_type": "STAGE_NODE", "scenario": scenario})
            stage_logger.info("📍 阶段0: 环境准备开始", extra={"log_type": "STAGE_NODE", "scenario": scenario})

            # 禁用Python字节码缓存，确保总是使用最新代码
            os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
            sys.dont_write_bytecode = True
            logger.info(
                "Python字节码缓存已禁用",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

# DEBUG日志（只写入事件日志文件）
            logger.debug(
                f"[ENV-SETUP] Python解释器: {sys.executable}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.debug(
                f"[ENV-SETUP] Python版本: {sys.version}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.debug(
                f"[ENV-SETUP] 平台: {sys.platform}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.debug(
                f"[ENV-SETUP] Python路径条目数: {len(sys.path)}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.debug(
                f"[ENV-SETUP] 已禁用字节码缓存: PYTHONDONTWRITEBYTECODE={os.environ.get('PYTHONDONTWRITEBYTECODE')}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            
            # INFO日志（记录关键配置）
            logger.info(
                f"[ENV-SETUP] 环境准备: Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro} on {sys.platform}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

            # 设置项目路径
            project_root = context.project_root
            path_already_in_sys_path = str(project_root) in sys.path
            if not path_already_in_sys_path:
                sys.path.insert(0, str(project_root))
                logger.debug(
                    f"[ENV-SETUP] 项目路径已添加到sys.path首位: {project_root}",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
            else:
                logger.debug(
                    f"[ENV-SETUP] 项目路径已存在于sys.path: {project_root}",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
            logger.info(
                "项目路径已添加到sys.path",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

# 新增原生扩展目录到 sys.path，确保顶层 native_* 包可导入
            native_extensions_path = project_root / "backend" / "infrastructure" / "native"
            native_path_str = str(native_extensions_path)
            if native_extensions_path.exists():
                if native_path_str not in sys.path:
                    sys.path.insert(1, native_path_str)
                    importlib.invalidate_caches()
                    logger.debug(
                        f"[ENV-SETUP] 原生扩展目录已添加到sys.path: {native_extensions_path}",
                        extra={"log_type": "SYSTEM", "scenario": scenario}
                    )
                else:
                    logger.debug(
                        f"[ENV-SETUP] 原生扩展目录已存在于sys.path: {native_extensions_path}",
                        extra={"log_type": "SYSTEM", "scenario": scenario}
                    )
                logger.info(
                    "原生扩展目录已加入 sys.path",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
            else:
                logger.warning(
                    f"[ENV-SETUP] ⚠️ 原生扩展目录不存在: {native_extensions_path}",
                    extra={"log_type": "ALERT", "scenario": scenario}
                )

# 原生扩展可用性自检
            native_checks = {
                "native_log_pipeline": "native_log_pipeline",
                "native_ipc": "backend.infrastructure.native.native_ipc",
                "native_serialization": "backend.infrastructure.native.native_serialization",
            }
            native_status: Dict[str, bool] = {}
            for name, module_path in native_checks.items():
                try:
                    importlib.import_module(module_path)
                    native_status[name] = True
                    logger.debug(
                        f"[ENV-SETUP] 原生扩展检测成功: {module_path}",
                        extra={"log_type": "SYSTEM", "scenario": scenario}
                    )
                except Exception as native_exc:
                    native_status[name] = False
                    logger.warning(
                        f"[ENV-SETUP] ⚠️ 原生扩展检测失败: {module_path} - {native_exc}",
                        extra={"log_type": "ALERT", "scenario": scenario},
                    )

            context.native_extension_status.update(native_status)
            context.native_log_pipeline_enabled = native_status.get("native_log_pipeline", False)

            status_summary = "，".join(
                f"{name}={'可用' if available else '不可用'}"
                for name, available in native_status.items()
            )
            logger.info(
                f"[ENV-SETUP] 原生扩展检测结果: {status_summary}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

# DEBUG日志（只写入事件日志文件）
            logger.debug(
                f"[ENV-SETUP] 项目根目录: {project_root}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.debug(
                f"[ENV-SETUP] sys.path条目数: {len(sys.path)}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.debug(
                f"[ENV-SETUP] sys.path前5项: {sys.path[:5]}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

            # 设置Python解释器路径（WebEngine子进程需要）
            python_executable_set = False
            if not os.environ.get("PYTHONEXECUTABLE"):
                os.environ["PYTHONEXECUTABLE"] = sys.executable
                python_executable_set = True
                logger.debug(
                    f"[ENV-SETUP] 设置PYTHONEXECUTABLE: {sys.executable}",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
            else:
                logger.debug(
                    f"[ENV-SETUP] PYTHONEXECUTABLE已存在: {os.environ.get('PYTHONEXECUTABLE')}",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
            
            qt_webengine_set = False
            if not os.environ.get("QT_WEBENGINE_PYTHON_EXECUTABLE"):
                os.environ["QT_WEBENGINE_PYTHON_EXECUTABLE"] = sys.executable
                qt_webengine_set = True
                logger.debug(
                    f"[ENV-SETUP] 设置QT_WEBENGINE_PYTHON_EXECUTABLE: {sys.executable}",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
            else:
                logger.debug(
                    f"[ENV-SETUP] QT_WEBENGINE_PYTHON_EXECUTABLE已存在: {os.environ.get('QT_WEBENGINE_PYTHON_EXECUTABLE')}",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )

            # 设置Qt环境变量（避免缩放问题）
            os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
            os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
            logger.info(
                "Qt高DPI缩放已配置",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            
            # DEBUG日志（记录Qt环境变量配置）
            logger.debug(
                f"[ENV-SETUP] Qt环境变量: QT_AUTO_SCREEN_SCALE_FACTOR={os.environ.get('QT_AUTO_SCREEN_SCALE_FACTOR')}, "
                f"QT_ENABLE_HIGHDPI_SCALING={os.environ.get('QT_ENABLE_HIGHDPI_SCALING')}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

            # 设置配置文件路径
            config_file = project_root / "config" / "terminal_config.json"
            context.config_file = str(config_file)
            os.environ["CONFIG_FILE"] = str(config_file)
            logger.info(
                "配置文件路径已设置",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            
# DEBUG日志（只写入事件日志文件）
            logger.debug(
                f"[ENV-SETUP] 配置文件路径: {config_file}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            config_exists = config_file.exists()
            logger.debug(
                f"[ENV-SETUP] 配置文件存在: {config_exists}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            if config_exists:
                config_size = config_file.stat().st_size
                logger.debug(
                    f"[ENV-SETUP] 配置文件大小: {config_size} bytes",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
            else:
                logger.warning(
                    f"[ENV-SETUP] ⚠️ 配置文件不存在: {config_file}，将使用默认配置",
                    extra={"log_type": "ALERT", "scenario": scenario}
                )

            # 注意：网络时间同步已移至阶段3的8步验证流程（步骤2）中执行
            # 这里不再执行网络时间同步，确保单一事实原则

            # 环境参数设置完成（对应标准输出）
            stage_logger.info(
                "✅ 环境参数设置完成（DPI/路径/解释器/配置）",
                extra={"log_type": "STAGE_NODE", "scenario": scenario}
            )

            elapsed_ms = (time.time() - start_time) * 1000

            # 输出完成信息（终端简版阶段日志）
            stage_logger.info(
                f"✅ 环境准备完成 ({int(elapsed_ms)}ms)",
                extra={"log_type": "STAGE_NODE", "scenario": scenario},
            )
            
            # INFO日志（记录环境准备完成信息）
            logger.info(
                f"[ENV-SETUP] 环境准备完成: 耗时={elapsed_ms:.0f}ms, 项目路径={project_root}, "
                f"配置文件={'存在' if config_file.exists() else '不存在'}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
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

