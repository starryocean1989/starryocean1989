# -*- coding: utf-8 -*-
"""
日志上下文管理器模块

提供阶段和场景的上下文管理，支持全局切换和局部切换
"""

import logging
from contextlib import contextmanager
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .routing_engine import RoutingRuleEngine


class LoggingContext:
    """日志上下文管理器

    功能：
    - 全局阶段切换（set_stage）
    - 局部阶段切换（stage上下文管理器）
    - 场景标记（scenario上下文管理器）

    使用示例：
        ctx = get_logging_context()

        # 全局阶段切换
        ctx.set_stage("downloading")

        # 局部阶段切换
        with ctx.stage("downloading"):
            logger.info("下载进度: 50%")

        # 场景标记
        with ctx.scenario("bulk_download"):
            logger.info("下载进度: 50%")
    """

    def __init__(self, routing_engine: "RoutingRuleEngine"):
        """初始化上下文管理器

        Args:
            routing_engine: 路由引擎实例
        """
        self.routing_engine = routing_engine
        self.logger = logging.getLogger(__name__)

    def set_stage(self, stage: str):
        """切换阶段（全局）

        适用场景：
        - 系统启动完成后切换到normal阶段
        - 进入下载流程时切换到downloading阶段
        - 开始交易时切换到trading阶段

        Args:
            stage: 阶段名称（startup/downloading/trading等）
        """
        self.routing_engine.set_stage(stage)

    @contextmanager
    def stage(self, stage_name: str):
        """阶段上下文管理器（局部）

        适用场景：
        - 某个函数内临时切换阶段
        - 不希望影响全局阶段状态

        Args:
            stage_name: 阶段名称

        Example:
            with ctx.stage("downloading"):
                logger.info("下载进度: 50%")  # 使用downloading阶段规则
            # 退出后恢复到之前的阶段
        """
        old_stage = self.routing_engine.current_stage
        self.routing_engine.set_stage(stage_name)
        try:
            yield
        finally:
            self.routing_engine.set_stage(old_stage)

    @contextmanager
    def scenario(self, scenario_name: str):
        """场景上下文管理器

        机制：
        - 通过LogRecordFactory注入scenario到record.details
        - 场景规则优先级最高（Layer 4）

        适用场景：
        - 关键业务流程（批量下载、订单执行等）
        - 需要特殊日志策略的场景

        Args:
            scenario_name: 场景名称（不带scenario_前缀）

        Example:
            with ctx.scenario("bulk_download"):
                logger.info("下载进度: 50%")  # 使用scenario_bulk_download规则
        """
        # 保存原始LogRecordFactory
        old_factory = logging.getLogRecordFactory()

        def factory(*args, **kwargs):
            """自定义LogRecordFactory，注入scenario"""
            record = old_factory(*args, **kwargs)
            if not hasattr(record, "details"):
                record.details = {}  # type: ignore[attr-defined]
            record.details["scenario"] = scenario_name  # type: ignore[index]
            return record

        # 设置自定义Factory
        logging.setLogRecordFactory(factory)
        try:
            yield
        finally:
            # 恢复原始Factory
            logging.setLogRecordFactory(old_factory)

    def get_current_stage(self) -> str:
        """获取当前阶段

        Returns:
            当前阶段名称
        """
        return self.routing_engine.current_stage

    def get_run_mode(self) -> str:
        """获取当前运行模式

        Returns:
            当前运行模式（dev/prod/ops）
        """
        return self.routing_engine.run_mode

    def set_run_mode(self, mode: str):
        """切换运行模式

        Args:
            mode: 运行模式（dev/prod/ops）
        """
        self.routing_engine.set_run_mode(mode)


# 全局上下文管理器
_logging_context: Optional[LoggingContext] = None


def get_logging_context() -> LoggingContext:
    """获取全局上下文管理器实例

    Returns:
        LoggingContext实例
    """
    global _logging_context
    if _logging_context is None:
        from backend.infrastructure.system_vnpy.routing_engine import get_routing_engine

        routing_engine = get_routing_engine()
        _logging_context = LoggingContext(routing_engine)
    return _logging_context
