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
            # 注意：日志输出统一由BackendInitStage管理，这里只记录DEBUG级别日志
            self.logger.debug("=" * 70)
            self.logger.debug("[BACKEND-INIT] 🔧 后端初始化Worker开始执行")
            self.logger.debug("=" * 70)

            # 1. 从context获取已初始化的引擎（阶段3已经初始化）
            event_engine = context.event_engine
            main_engine = context.main_engine

            if not event_engine or not main_engine:
                return WorkerResult(
                    success=False,
                    message="EventEngine或MainEngine未初始化",
                    elapsed_ms=(time.time() - start_time) * 1000,
                )

            # 2. 初始化ChinaStockEngine
            # 注意：阶段3.1的日志输出由BackendInitStage统一管理，这里只负责初始化
            china_stock_engine = None
            init_success = False

            try:
                self.logger.debug("[BACKEND-INIT] 初始化ChinaStockEngine...")
                from backend.infrastructure.data_module_vnpy import ChinaStockEngine
                from backend.core.base import set_china_stock_engine

                china_stock_engine = ChinaStockEngine(main_engine, event_engine)
                init_success = china_stock_engine.initialize()

                if init_success:
                    self.logger.debug("[BACKEND-INIT] ✅ ChinaStockEngine 初始化成功")
                    set_china_stock_engine(china_stock_engine)
                    context.china_stock_engine = china_stock_engine
                else:
                    self.logger.warning("[BACKEND-INIT] ⚠️ ChinaStockEngine 初始化失败", extra={"log_type": "SYSTEM"})
            except Exception as e:
                self.logger.error(f"[BACKEND-INIT] ❌ ChinaStockEngine 初始化异常: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
                init_success = False

            # 3. 初始化DataCenterService
            # 注意：DataCenterService的日志输出由其自身管理，这里只负责初始化
            data_service = None
            data_init_success = False

            try:
                self.logger.debug("[BACKEND-INIT] 初始化DataCenterService...")
                from backend.services.data_center_service import DataCenterService

                data_service = DataCenterService()
                data_init_success = data_service.initialize()

                if data_init_success:
                    self.logger.debug("[BACKEND-INIT] ✅ DataCenterService 初始化成功")
                    context.service_manager.register_service("data_center_service", data_service)
                    context.data_service = data_service
                else:
                    self.logger.warning("[BACKEND-INIT] ⚠️ DataCenterService 初始化失败", extra={"log_type": "SYSTEM"})
            except Exception as e:
                self.logger.error(f"[BACKEND-INIT] ❌ DataCenterService 初始化异常: {e}", exc_info=True, extra={"log_type": "SYSTEM"})
                data_init_success = False

            # 4. 返回结果
            success = init_success and data_init_success
            elapsed_ms = (time.time() - start_time) * 1000

            if success:
                self.logger.debug(f"[BACKEND-INIT] ✅ 后端数据服务初始化成功 ({elapsed_ms:.0f}ms)")
            else:
                self.logger.warning(f"[BACKEND-INIT] ⚠️ 后端数据服务初始化部分失败 ({elapsed_ms:.0f}ms)", extra={"log_type": "SYSTEM"})

            return WorkerResult(
                success=success,
                message="后端数据服务初始化完成" if success else "后端数据服务初始化失败",
                elapsed_ms=elapsed_ms,
                data={
                    "china_stock_engine": china_stock_engine,
                    "data_service": data_service,
                    "china_stock_success": init_success,
                    "data_service_success": data_init_success,
                },
            )

        except Exception as e:
            elapsed_ms = (time.time() - start_time) * 1000

            self.logger.exception(f"[BACKEND-INIT] 后端初始化Worker异常: {e}")

            return WorkerResult(
                success=False,
                message=f"后端初始化Worker异常: {str(e)}",
                elapsed_ms=elapsed_ms,
                error=e,
            )

