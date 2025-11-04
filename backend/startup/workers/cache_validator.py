# -*- coding: utf-8 -*-
"""
缓存验证Worker - 执行8步缓存验证流程

负责执行_smart_cache_validation_and_sensing的8步验证流程。
"""

import logging
import time
from typing import Optional, Dict, Any, Callable

from backend.startup.workers.base import StartupWorker, WorkerResult
from backend.startup.context import StartupContext

logger = logging.getLogger("backend.startup.workers.cache_validator")


class CacheValidatorWorker(StartupWorker):
    """缓存验证Worker

    职责：
    - 封装_smart_cache_validation_and_sensing的8步验证流程
    - 使用async/await支持异步执行
    - 报告进度
    """

    def __init__(self):
        """初始化缓存验证Worker"""
        super().__init__(
            name="cache_validator",
            description="缓存验证Worker - 执行8步验证流程",
        )
        self._cancelled = False

    async def _run(self, context: StartupContext) -> WorkerResult:
        """执行缓存验证逻辑

        Args:
            context: 启动上下文

        Returns:
            WorkerResult: Worker执行结果
        """
        start_time = time.time()

        try:
            # 获取ChinaStockEngine
            if not context.china_stock_engine:
                raise RuntimeError("ChinaStockEngine未初始化")

            engine = context.china_stock_engine
            stage_logger = logging.getLogger("startup.stage")

            # 注意：分支B标题和ChinaStockEngine初始化信息已在BackendInitStage中输出
            # 这里只输出8步验证的开始标记
            stage_logger.info(
                "📍 开始缓存验证与感知流程（8步）", extra={"log_type": "STAGE_NODE"}
            )

            # 创建进度回调函数
            def progress_callback(description: str, percent: int):
                """进度回调函数"""
                self.logger.debug(f"[进度 {percent}%] {description}")
                self._report_progress(description, percent)

            # 注意：步骤完成日志已在_smart_cache_validation_and_sensing中输出
            # 不需要在这里创建step_callback，避免重复输出
            # def step_callback(step_num: int, step_name: str, step_result: dict):
            #     """步骤完成回调函数"""
            #     elapsed = step_result.get("elapsed", 0)
            #     progress = step_result.get("progress", 0)
            #     stage_logger.info(
            #         f"✅ 步骤{step_num}完成 ({elapsed:.0f}ms) [进度: {progress}%]",
            #         extra={"log_type": "STAGE_NODE"},
            #     )

            # 执行8步验证流程
            # 注意：_smart_cache_validation_and_sensing是同步方法，需要在后台线程执行
            import asyncio

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                engine._smart_cache_validation_and_sensing,
                progress_callback,
                None,  # 不传递step_callback，避免重复输出
            )

            elapsed_ms = (time.time() - start_time) * 1000

            # 检查是否进入离线模式（如果有）
            # 注意：离线模式信息已在_smart_cache_validation_and_sensing中输出
            if result.get("offline_mode"):
                stage_logger.warning(
                    f"🔴 触发离线降级: {result.get('offline_reason', '未知原因')}",
                    extra={"log_type": "STAGE_NODE"},
                )

            # 注意："✅ 数据引擎完全就绪"已在_smart_cache_validation_and_sensing中输出，
            # 这里不需要重复输出

            return WorkerResult(
                success=result.get("success", False),
                message="缓存验证完成" if result.get("success", False) else "缓存验证失败",
                elapsed_ms=elapsed_ms,
                data={"validation_result": result},
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000

            self.logger.exception(f"缓存验证Worker异常: {e}")

            return WorkerResult(
                success=False,
                message=f"缓存验证Worker异常: {str(e)}",
                elapsed_ms=elapsed_ms,
                error=e,
            )

    def cancel(self):
        """取消验证"""
        self._cancelled = True
        self.logger.warning("缓存验证被取消", extra={"log_type": "SYSTEM"})

