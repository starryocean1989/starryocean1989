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
            # 在日志系统初始化前，使用print直接输出到终端
            # 确保输出格式与设计文档一致
            print()
            print("=" * 70)
            print("【阶段0: 环境准备】 (0-5%)")
            print("=" * 70)
            print()
            print("📍 阶段0: 环境准备开始")

            # 禁用Python字节码缓存，确保总是使用最新代码
            os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
            sys.dont_write_bytecode = True
            print("✅ Python字节码缓存已禁用")

            # 设置项目路径
            project_root = context.project_root
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))
            print("✅ 项目路径已添加到sys.path")

            # 设置Python解释器路径（WebEngine子进程需要）
            if not os.environ.get("PYTHONEXECUTABLE"):
                os.environ["PYTHONEXECUTABLE"] = sys.executable
            if not os.environ.get("QT_WEBENGINE_PYTHON_EXECUTABLE"):
                os.environ["QT_WEBENGINE_PYTHON_EXECUTABLE"] = sys.executable
            print("✅ Python解释器路径已设置")
            print("✅ Qt WebEngine解释器路径已设置")

            # 设置Qt环境变量（避免缩放问题）
            os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
            os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
            print("✅ Qt高DPI缩放已配置")

            # 设置配置文件路径
            config_file = project_root / "config" / "terminal_config.json"
            context.config_file = str(config_file)
            os.environ["CONFIG_FILE"] = str(config_file)
            print("✅ 配置文件路径已设置")

            # 注意：网络时间同步已移至阶段3的8步验证流程（步骤2）中执行
            # 这里不再执行网络时间同步，确保单一事实原则

            # 关键：在环境准备阶段完成后，立即设置MemoryHandler缓冲所有日志
            # 防止在日志系统初始化之前有任何日志输出
            root_logger = logging.getLogger()
            # 移除已有的handlers（如果有）
            for handler in root_logger.handlers[:]:
                root_logger.removeHandler(handler)
                if hasattr(handler, 'close'):
                    handler.close()
            
            # 创建MemoryHandler作为临时缓冲（容量10000条）
            # target先设为None，日志系统初始化后再设置
            memory_handler = MemoryHandler(capacity=10000, target=None)
            memory_handler.setLevel(logging.DEBUG)
            root_logger.setLevel(logging.DEBUG)
            root_logger.addHandler(memory_handler)
            
            # 存储到context中，供日志系统初始化阶段使用
            context._memory_handler = memory_handler

            elapsed_ms = (time.time() - start_time) * 1000

            # 输出完成信息
            print(f"✅ 环境准备完成 ({elapsed_ms:.0f}ms)")

            return StageResult(
                success=True,
                message="环境准备完成",
                elapsed_ms=elapsed_ms,
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000

            print(f"❌ 环境准备失败: {str(e)}")

            return StageResult(
                success=False,
                message=f"环境准备失败: {str(e)}",
                elapsed_ms=elapsed_ms,
                error=e,
            )

