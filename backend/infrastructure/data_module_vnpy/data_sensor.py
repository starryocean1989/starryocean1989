# -*- coding: utf-8 -*-
"""数据传感器模块.

监控数据变化并触发相应的事件处理
"""
import asyncio
import logging
from typing import Any, Callable, Dict, List


logger = logging.getLogger(__name__)


class DataSensor:
    """数据传感器类."""

    def __init__(self) -> None:
        """初始化数据传感器."""
        self.logger = logging.getLogger(__name__)
        self.callbacks: Dict[str, List[Callable[[Any], None]]] = {}
        self.monitoring = False

    def register_callback(self, event_type: str,
                          callback: Callable[[Any], None]) -> None:
        """
        注册事件回调函数.

        Args:
            event_type: 事件类型
            callback: 回调函数
        """
        if event_type not in self.callbacks:
            self.callbacks[event_type] = []

        self.callbacks[event_type].append(callback)
        self.logger.info("注册回调函数: %s", event_type)

    def unregister_callback(self, event_type: str,
                            callback: Callable[[Any], None]) -> None:
        """
        注销事件回调函数.

        Args:
            event_type: 事件类型
            callback: 回调函数
        """
        if event_type in self.callbacks:
            try:
                self.callbacks[event_type].remove(callback)
                self.logger.info("注销回调函数: %s", event_type)
            except ValueError:
                self.logger.warning("回调函数未找到: %s", event_type)

    async def start_monitoring(self) -> None:
        """启动数据监控."""
        self.monitoring = True
        self.logger.info("启动数据监控")

        while self.monitoring:
            try:
                # 这里应该实现实际的数据监控逻辑
                await asyncio.sleep(1)  # 每秒检查一次

            except OSError as e:
                self.logger.error("数据监控出错: %s", e)
                await asyncio.sleep(5)  # 出错后等待5秒再试

    def stop_monitoring(self) -> None:
        """停止数据监控."""
        self.monitoring = False
        self.logger.info("停止数据监控")

    def trigger_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """
        触发事件.

        Args:
            event_type: 事件类型
            data: 事件数据
        """
        if event_type in self.callbacks:
            for callback in self.callbacks[event_type]:
                try:
                    callback(data)
                except (TypeError, ValueError, RuntimeError) as e:
                    self.logger.error("执行回调函数出错: %s", e)
