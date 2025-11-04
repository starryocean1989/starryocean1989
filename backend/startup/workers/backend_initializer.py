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

            # 2. 初始化ChinaStockEngine
            # 注意：阶段3.1的日志输出由BackendInitStage统一管理，这里只负责初始化
            china_stock_engine = None
            init_success = False

            try:
                self.logger.debug(
                    "[BACKEND-INIT-WORKER] 开始初始化ChinaStockEngine...",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                from backend.infrastructure.data_module_vnpy import ChinaStockEngine
                from backend.core.base import set_china_stock_engine

                self.logger.debug(
                    "[BACKEND-INIT-WORKER] ChinaStockEngine类已导入，开始实例化",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                china_stock_engine = ChinaStockEngine(main_engine, event_engine)
                self.logger.debug(
                    "[BACKEND-INIT-WORKER] ChinaStockEngine实例已创建，开始调用initialize()",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                init_success = china_stock_engine.initialize()

                if init_success:
                    self.logger.debug(
                        "[BACKEND-INIT-WORKER] ✅ ChinaStockEngine.initialize()返回成功",
                        extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                    )
                    set_china_stock_engine(china_stock_engine)
                    context.china_stock_engine = china_stock_engine
                    self.logger.info(
                        "[BACKEND-INIT-WORKER] ✅ ChinaStockEngine已注册到全局和context",
                        extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                    )
                else:
                    self.logger.warning(
                        "[BACKEND-INIT-WORKER] ⚠️ ChinaStockEngine.initialize()返回False",
                        extra={"log_type": "ALERT", "scenario": "application_startup"}
                    )
            except ImportError as e:
                self.logger.error(
                    f"[BACKEND-INIT-WORKER] ❌ ChinaStockEngine导入失败: {e}",
                    exc_info=True,
                    extra={"log_type": "ALERT", "scenario": "application_startup"}
                )
                init_success = False
            except Exception as e:
                self.logger.error(
                    f"[BACKEND-INIT-WORKER] ❌ ChinaStockEngine初始化异常: {e}",
                    exc_info=True,
                    extra={"log_type": "ALERT", "scenario": "application_startup"}
                )
                init_success = False

            # 3. 初始化DataCenterService
            # 注意：DataCenterService的日志输出由其自身管理，这里只负责初始化
            data_service = None
            data_init_success = False

            try:
                self.logger.debug(
                    "[BACKEND-INIT-WORKER] 开始初始化DataCenterService...",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                from backend.services.data_center_service import DataCenterService

                self.logger.debug(
                    "[BACKEND-INIT-WORKER] DataCenterService类已导入，开始实例化",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                data_service = DataCenterService()
                self.logger.debug(
                    "[BACKEND-INIT-WORKER] DataCenterService实例已创建，开始调用initialize()",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                data_init_success = data_service.initialize()

                if data_init_success:
                    self.logger.debug(
                        "[BACKEND-INIT-WORKER] ✅ DataCenterService.initialize()返回成功",
                        extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                    )
                    context.service_manager.register_service("data_center_service", data_service)
                    context.data_service = data_service
                    self.logger.info(
                        "[BACKEND-INIT-WORKER] ✅ DataCenterService已注册到ServiceManager和context",
                        extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                    )
                else:
                    self.logger.warning(
                        "[BACKEND-INIT-WORKER] ⚠️ DataCenterService.initialize()返回False",
                        extra={"log_type": "ALERT", "scenario": "application_startup"}
                    )
            except ImportError as e:
                self.logger.error(
                    f"[BACKEND-INIT-WORKER] ❌ DataCenterService导入失败: {e}",
                    exc_info=True,
                    extra={"log_type": "ALERT", "scenario": "application_startup"}
                )
                data_init_success = False
            except Exception as e:
                self.logger.error(
                    f"[BACKEND-INIT-WORKER] ❌ DataCenterService初始化异常: {e}",
                    exc_info=True,
                    extra={"log_type": "ALERT", "scenario": "application_startup"}
                )
                data_init_success = False

            # 4. 返回结果
            success = init_success and data_init_success
            elapsed_ms = (time.time() - start_time) * 1000

            if success:
                self.logger.debug(
                    f"[BACKEND-INIT-WORKER] ✅ 后端数据服务初始化成功 ({elapsed_ms:.0f}ms)",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
                self.logger.info(
                    f"[BACKEND-INIT-WORKER] ✅ 后端数据服务初始化完成: "
                    f"ChinaStockEngine={'成功' if init_success else '失败'}, "
                    f"DataCenterService={'成功' if data_init_success else '失败'}",
                    extra={"log_type": "SYSTEM", "scenario": "application_startup"}
                )
            else:
                self.logger.warning(
                    f"[BACKEND-INIT-WORKER] ⚠️ 后端数据服务初始化部分失败 ({elapsed_ms:.0f}ms): "
                    f"ChinaStockEngine={'成功' if init_success else '失败'}, "
                    f"DataCenterService={'成功' if data_init_success else '失败'}",
                    extra={"log_type": "ALERT", "scenario": "application_startup"}
                )

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

