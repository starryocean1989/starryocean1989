# -*- coding: utf-8 -*-
"""
E2E测试等待助手工具.

提供条件等待、状态轮询等工具，避免硬编码sleep。
"""

import asyncio
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


async def wait_until_condition(
    condition_func: Callable[[], bool],
    timeout: float = 3.0,
    interval: float = 0.1,
    error_message: str = "条件等待超时",
) -> bool:
    """
    等待直到条件满足或超时.

    Args:
        condition_func: 条件检查函数，返回True表示条件满足
        timeout: 超时时间（秒）
        interval: 检查间隔（秒）
        error_message: 超时错误消息

    Returns:
        是否在超时前满足条件
    """
    elapsed = 0.0
    while elapsed < timeout:
        try:
            if condition_func():
                logger.debug(f"条件满足，耗时: {elapsed:.3f}秒")
                return True
        except Exception as e:
            logger.debug(f"条件检查异常: {e}")

        await asyncio.sleep(interval)
        elapsed += interval

    logger.warning(f"{error_message}（等待{elapsed:.3f}秒）")
    return False


async def wait_for_service_state(
    service,
    state_getter: Callable[[Any], Any],
    expected_value: Any,
    timeout: float = 3.0,
    interval: float = 0.2,
    field_name: str = "状态",
) -> bool:
    """
    等待服务状态达到预期值.

    Args:
        service: 服务实例
        state_getter: 获取状态的函数
        expected_value: 期望的状态值
        timeout: 超时时间（秒）
        interval: 检查间隔（秒）
        field_name: 状态字段名称（用于日志）

    Returns:
        是否在超时前达到预期状态
    """
    elapsed = 0.0
    while elapsed < timeout:
        try:
            current_value = state_getter(service)
            if current_value == expected_value:
                logger.debug(f"{field_name}达到预期值: {expected_value}，耗时: {elapsed:.3f}秒")
                return True
        except Exception as e:
            logger.debug(f"获取{field_name}失败: {e}")

        await asyncio.sleep(interval)
        elapsed += interval

    logger.warning(f"{field_name}等待超时（期望: {expected_value}，等待{elapsed:.3f}秒）")
    return False


async def wait_for_cache_loaded(
    symbol_service,
    service_accessor,
    min_size: int = 1,
    timeout: float = 3.0,
    interval: float = 0.2,
) -> bool:
    """
    等待品种缓存加载完成.

    Args:
        symbol_service: SymbolService实例
        service_accessor: ServiceAccessor实例
        min_size: 最小缓存大小
        timeout: 超时时间（秒）
        interval: 检查间隔（秒）

    Returns:
        是否成功加载
    """

    def check_cache():
        stats = service_accessor.get_cache_stats(symbol_service)
        return stats.get("cache_size", 0) >= min_size and stats.get("cache_updated", False)

    return await wait_until_condition(
        condition_func=check_cache,
        timeout=timeout,
        interval=interval,
        error_message=f"品种缓存加载超时（期望≥{min_size}个品种）",
    )


async def wait_for_task_completion(
    download_service,
    service_accessor,
    task_id: str,
    expected_statuses: list = None,
    timeout: float = 30.0,
    interval: float = 0.5,
) -> Optional[dict]:
    """
    等待下载任务完成.

    Args:
        download_service: DownloadService实例
        service_accessor: ServiceAccessor实例
        task_id: 任务ID
        expected_statuses: 期望的完成状态列表
        timeout: 超时时间（秒）
        interval: 检查间隔（秒）

    Returns:
        任务最终状态，超时返回None
    """
    if expected_statuses is None:
        expected_statuses = ["completed", "failed", "cancelled"]

    elapsed = 0.0
    while elapsed < timeout:
        task_status = service_accessor.get_task_status(download_service, task_id)

        if task_status and task_status["status"] in expected_statuses:
            logger.debug(
                f"任务{task_id[:8]}完成，状态: {task_status['status']}，耗时: {elapsed:.3f}秒"
            )
            return task_status

        await asyncio.sleep(interval)
        elapsed += interval

    logger.warning(f"任务{task_id[:8]}等待超时（{elapsed:.3f}秒）")
    return None


async def wait_for_ui_update(
    widget,
    check_func: Callable[[Any], bool],
    timeout: float = 1.0,
    interval: float = 0.1,
    description: str = "UI更新",
) -> bool:
    """
    等待UI组件更新完成.

    Args:
        widget: UI组件
        check_func: 检查UI状态的函数
        timeout: 超时时间（秒）
        interval: 检查间隔（秒）
        description: 描述（用于日志）

    Returns:
        是否在超时前完成更新
    """
    elapsed = 0.0
    while elapsed < timeout:
        try:
            if check_func(widget):
                logger.debug(f"{description}完成，耗时: {elapsed:.3f}秒")
                return True
        except Exception as e:
            logger.debug(f"{description}检查异常: {e}")

        await asyncio.sleep(interval)
        elapsed += interval

    logger.warning(f"{description}等待超时（{elapsed:.3f}秒）")
    return False


async def wait_for_connection_state(
    datasource_service,
    service_accessor,
    expected_source: Optional[str] = None,
    expected_state: Optional[str] = None,
    expected_pushing: Optional[bool] = None,
    timeout: float = 3.0,
    interval: float = 0.2,
) -> bool:
    """
    等待数据源连接状态.

    Args:
        datasource_service: DataSourceService实例
        service_accessor: ServiceAccessor实例
        expected_source: 期望连接的数据源
        expected_state: 期望的连接状态
        expected_pushing: 期望的推送状态
        timeout: 超时时间（秒）
        interval: 检查间隔（秒）

    Returns:
        是否达到预期状态
    """

    def check_state():
        state = service_accessor.get_datasource_connection_state(datasource_service)

        if expected_source is not None and state.get("connected_source") != expected_source:
            return False
        if expected_state is not None and state.get("connection_state") != expected_state:
            return False
        if expected_pushing is not None and state.get("is_pushing") != expected_pushing:
            return False

        return True

    return await wait_until_condition(
        condition_func=check_state,
        timeout=timeout,
        interval=interval,
        error_message=f"数据源状态等待超时（source={expected_source}, state={expected_state}, pushing={expected_pushing}）",
    )


async def wait_for_widget_enabled(widget, timeout: float = 5.0, interval: float = 0.1) -> bool:
    """
    等待Qt组件可用（异步版本）.

    Args:
        widget: Qt组件
        timeout: 超时时间（秒）
        interval: 检查间隔（秒）

    Returns:
        组件是否可用
    """

    async def check_enabled():
        return widget is not None and hasattr(widget, "isEnabled") and widget.isEnabled()

    return await wait_until_condition(
        check_enabled,
        timeout=timeout,
        interval=interval,
        error_message="等待组件可用超时",
    )


async def wait_for_data_loaded(
    widget, min_items: int = 1, timeout: float = 10.0, interval: float = 0.2
) -> bool:
    """
    等待Qt组件数据加载（异步版本）.

    Args:
        widget: Qt组件（表格、列表等）
        min_items: 最小项目数
        timeout: 超时时间（秒）
        interval: 检查间隔（秒）

    Returns:
        数据是否加载
    """

    async def check_data():
        if widget is None:
            return False

        # 检查不同类型的组件
        if hasattr(widget, "rowCount"):
            return widget.rowCount() >= min_items
        elif hasattr(widget, "count"):
            return widget.count() >= min_items
        elif hasattr(widget, "topLevelItemCount"):
            return widget.topLevelItemCount() >= min_items

        return False

    return await wait_until_condition(
        check_data,
        timeout=timeout,
        interval=interval,
        error_message=f"等待数据加载(最小{min_items}项)超时",
    )


async def wait_with_progress(total_time: float, interval: float = 0.1):
    """
    带进度的等待（异步版本）.

    Args:
        total_time: 总等待时间（秒）
        interval: 检查间隔（秒）
    """
    elapsed = 0.0
    while elapsed < total_time:
        await asyncio.sleep(interval)
        elapsed += interval
        progress = int((elapsed / total_time) * 100)
        logger.debug(f"等待进度: {progress}%")


# 导出公共接口
__all__ = [
    "wait_until_condition",
    "wait_for_service_state",
    "wait_for_cache_loaded",
    "wait_for_task_completion",
    "wait_for_ui_update",
    "wait_for_connection_state",
    "wait_for_widget_enabled",
    "wait_for_data_loaded",
    "wait_with_progress",
]
