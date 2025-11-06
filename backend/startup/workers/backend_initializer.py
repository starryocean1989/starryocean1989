# -*- coding: utf-8 -*-
"""
后端初始化Worker - 执行后端服务初始化逻辑

负责调用ServiceInitializer初始化所有后端服务。
"""

import logging
import time

from backend.startup.workers.base import StartupWorker, WorkerResult
from backend.startup.context import StartupContext

logger = logging.getLogger("backend.startup.workers.backend_initializer")


class BackendInitializerWorker(StartupWorker):
    """后端初始化Worker

    职责：
    - 调用ServiceInitializer初始化所有后端服务
    - 报告初始化进度
    - 处理初始化错误
    """

    def __init__(self):
        """初始化后端初始化Worker"""
        super().__init__(
            name="backend_initializer",
            description="后端初始化Worker - 调用ServiceInitializer初始化所有服务",
        )

    async def _run(self, context: StartupContext) -> WorkerResult:
        """执行后端初始化逻辑 - 只初始化数据服务

        Args:
            context: 启动上下文

        Returns:
            WorkerResult: Worker执行结果
        """
        start_time = time.time()

        try:
            # 注意：日志输出统一由BackendInitStage管理，这里记录详细的DEBUG级别日志
            self.logger.debug(
                "=" * 70,
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            self.logger.debug(
                "[BACKEND-INIT-WORKER] 🔧 后端初始化Worker开始执行",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            self.logger.debug(
                "=" * 70,
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            # 1. 从context获取已初始化的引擎（阶段3已经初始化）
            event_engine = context.event_engine
            main_engine = context.main_engine

            self.logger.debug(
                f"[BACKEND-INIT-WORKER] 检查引擎状态: event_engine={'存在' if event_engine else '不存在'}, "
                f"main_engine={'存在' if main_engine else '不存在'}",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            if not event_engine or not main_engine:
                self.logger.error(
                    "[BACKEND-INIT-WORKER] ❌ EventEngine或MainEngine未初始化",
                    extra={"log_type": "ALERT", "scenario": "application_startup"}
                )
                return WorkerResult(
                    success=False,
                    message="EventEngine或MainEngine未初始化",
                    elapsed_ms=(time.time() - start_time) * 1000,
                )

            # 2. 根据三进程架构迁移方案步骤5，ChinaStockEngine和DataCenterService
            # 已迁移到数据进程中，主进程不再初始化这些服务
            self.logger.info(
                "[BACKEND-INIT-WORKER] ℹ️ ChinaStockEngine和DataCenterService已迁移到数据进程，主进程不再初始化",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            # 3. 返回结果 - 成功（因为没有需要初始化的数据服务）
            success = True
            elapsed_ms = (time.time() - start_time) * 1000

            self.logger.debug(
                f"[BACKEND-INIT-WORKER] ✅ 后端服务初始化成功 ({elapsed_ms:.0f}ms)",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )
            self.logger.info(
                "[BACKEND-INIT-WORKER] ✅ 后端服务初始化完成（三进程架构）",
                extra={"log_type": "SYSTEM", "scenario": "application_startup"}
            )

            return WorkerResult(
                success=success,
                message="后端服务初始化完成（三进程架构）",
                elapsed_ms=elapsed_ms,
                data={
                    "architecture": "three_process",
                    "data_services_migrated": True,
                },
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000

            self.logger.critical(
                f"[BACKEND-INIT-WORKER] 🔥 后端初始化Worker发生严重异常: {e}",
                exc_info=True,
                extra={"log_type": "ALERT", "scenario": "application_startup"}
            )

            return WorkerResult(
                success=False,
                message=f"后端初始化Worker异常: {str(e)}",
                elapsed_ms=elapsed_ms,
                error=e,
            )

