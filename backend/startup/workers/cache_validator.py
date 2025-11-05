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
        scenario = "application_startup"

        try:
            # 获取ChinaStockEngine
            if not context.china_stock_engine:
                logger.debug(
                    "[CACHE-VALIDATOR] ChinaStockEngine未初始化",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                logger.error(
                    "[CACHE-VALIDATOR] ❌ ChinaStockEngine未初始化",
                    extra={"log_type": "ALERT", "scenario": scenario}
                )
                raise RuntimeError("ChinaStockEngine未初始化")

            engine = context.china_stock_engine
            stage_logger = logging.getLogger("startup.stage")

            logger.debug(
                "[CACHE-VALIDATOR] 开始执行8步缓存验证流程",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.info(
                "[CACHE-VALIDATOR] ℹ️ 开始执行8步缓存验证流程",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

            # 注意：分支B标题和ChinaStockEngine初始化信息已在BackendInitStage中输出
            # 这里只输出8步验证的开始标记
            stage_logger.info(
                "📍 开始缓存验证与感知流程（8步）",
                extra={"log_type": "STAGE_NODE", "scenario": scenario}
            )

            # 创建进度回调函数
            def progress_callback(description: str, percent: int):
                """进度回调函数"""
                logger.debug(
                    f"[CACHE-VALIDATOR] [进度 {percent}%] {description}",
                    extra={"log_type": "PROGRESS", "scenario": scenario}
                )
                self._report_progress(description, percent)

            # 创建步骤完成回调函数（输出简洁的阶段成果日志）
            def step_callback(step_num: int, step_name: str, step_result: dict):
                """步骤完成回调函数 - 输出阶段成果到Terminal"""
                elapsed = step_result.get("elapsed", 0)
                progress = step_result.get("progress", 0)
                logger.debug(
                    f"[CACHE-VALIDATOR] 步骤{step_num}完成: {step_name}, 耗时={elapsed:.0f}ms, 进度={progress}%",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                stage_logger.info(
                    f"✅ 步骤{step_num}完成: {step_name} ({elapsed:.0f}ms) [进度: {progress}%]",
                    extra={"log_type": "STAGE_NODE", "scenario": scenario},
                )

            # 执行8步验证流程
            # 注意：_smart_cache_validation_and_sensing是同步方法，需要在后台线程执行
            import asyncio

            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                engine._smart_cache_validation_and_sensing,
                progress_callback,
                step_callback,  # 传递step_callback，输出阶段成果日志
            )

            elapsed_ms = (time.time() - start_time) * 1000

            # 检查是否进入离线模式（如果有）
            # 注意：离线模式信息已在_smart_cache_validation_and_sensing中输出
            if result.get("offline_mode"):
                offline_reason = result.get("offline_reason", "未知原因")
                logger.debug(
                    f"[CACHE-VALIDATOR] 检测到离线模式: {offline_reason}",
                    extra={"log_type": "SYSTEM", "scenario": scenario}
                )
                logger.warning(
                    f"[CACHE-VALIDATOR] ⚠️ 触发离线降级: {offline_reason}",
                    extra={"log_type": "ALERT", "scenario": scenario}
                )
                stage_logger.warning(
                    f"🔴 触发离线降级: {offline_reason}",
                    extra={"log_type": "STAGE_NODE", "scenario": scenario},
                )

            # 注意："✅ 数据引擎完全就绪"已在_smart_cache_validation_and_sensing中输出，
            # 这里不需要重复输出
            logger.debug(
                f"[CACHE-VALIDATOR] 8步缓存验证流程完成: 成功={result.get('success', False)}, "
                f"耗时={elapsed_ms:.0f}ms, 完成步骤数={result.get('steps_completed', 0)}",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.info(
                f"[CACHE-VALIDATOR] ✅ 8步缓存验证流程完成: 耗时={elapsed_ms:.0f}ms",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )

            return WorkerResult(
                success=result.get("success", False),
                message="缓存验证完成" if result.get("success", False) else "缓存验证失败",
                elapsed_ms=elapsed_ms,
                data={"validation_result": result},
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000
            scenario = "application_startup"

            logger.debug(
                f"[CACHE-VALIDATOR] 缓存验证Worker异常详情: {type(e).__name__}: {str(e)}, 耗时={elapsed_ms:.0f}ms",
                extra={"log_type": "SYSTEM", "scenario": scenario}
            )
            logger.error(
                f"[CACHE-VALIDATOR] ❌ 缓存验证Worker异常: {e}",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": scenario}
            )

            return WorkerResult(
                success=False,
                message=f"缓存验证Worker异常: {str(e)}",
                elapsed_ms=elapsed_ms,
                error=e,
            )

    def cancel(self):
        """取消验证"""
        self._cancelled = True
        scenario = "application_startup"
        logger.debug(
            "[CACHE-VALIDATOR] 缓存验证被取消",
            extra={"log_type": "SYSTEM", "scenario": scenario}
        )
        logger.warning(
            "[CACHE-VALIDATOR] ⚠️ 缓存验证被取消",
            extra={"log_type": "ALERT", "scenario": scenario}
        )

