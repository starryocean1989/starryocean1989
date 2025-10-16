# -*- coding: utf-8 -*-
"""
生命周期管理器模块

封装延迟初始化、组件关闭等生命周期管理逻辑，从core.py迁移
"""

import logging
from typing import Any, Dict, Optional

from .config import config_manager


logger = logging.getLogger(__name__)


class LifecycleManager:
    """生命周期管理器 - 管理组件的初始化和关闭"""

    @staticmethod
    def lazy_init(data_sensor, preload_service) -> None:
        """
        延迟初始化（从core.py迁移）

        首次调用时初始化：
        1. 文件监控器
        2. 数据感知器
        3. 预加载服务

        Args:
            data_sensor: DataSensor实例
            preload_service: PreloadService实例（可选）
        """
        logger.info("[LAZY-INIT] 开始延迟初始化...")

        try:
            # 1. 启动文件监控（如果配置启用）
            if config_manager.is_watcher_enabled():
                logger.info("[LAZY-INIT] 启动文件监控...")
                try:
                    # 文件监控现在由data_sensor处理，无需单独启动
                    logger.info("[LAZY-INIT] ✅ 文件监控由data_sensor管理")
                except Exception as e:
                    logger.warning("[LAZY-INIT] ⚠️ 文件监控启动失败: %s", e)
            else:
                logger.info("[LAZY-INIT] 文件监控未启用，跳过")

            # 2. 启动数据感知器（异步扫描）
            logger.info("[LAZY-INIT] 启动数据感知器...")
            try:
                # 数据感知器的启动逻辑已经移到DataSensor中
                logger.info("[LAZY-INIT] ✅ 数据感知器准备就绪（按需启动）")
            except Exception as e:
                logger.warning("[LAZY-INIT] ⚠️ 数据感知器启动失败: %s", e)

            # 3. 启动预加载服务（如果配置启用且自动启动）
            if preload_service and config_manager.is_preload_auto_start():
                logger.info("[LAZY-INIT] 启动预加载服务...")
                try:
                    preload_service.start(prime=True)
                    logger.info("[LAZY-INIT] ✅ 预加载服务启动成功")
                except Exception as e:
                    logger.warning("[LAZY-INIT] ⚠️ 预加载服务启动失败: %s", e)
            else:
                logger.info("[LAZY-INIT] 预加载服务未启用或不自动启动，跳过")

            logger.info("[LAZY-INIT] ✅ 延迟初始化完成")

        except Exception as e:
            logger.error("[LAZY-INIT] ❌ 延迟初始化发生异常: %s", e, exc_info=True)

    @staticmethod
    def close_all(components: Dict[str, Any]) -> None:
        """
        关闭所有组件（从core.py迁移）

        Args:
            components: 组件字典，包含所有需要关闭的组件
        """
        try:
            # 停止数据感知
            data_sensor = components.get("data_sensor")
            if data_sensor and hasattr(data_sensor, "stop_sensing"):
                try:
                    data_sensor.stop_sensing()
                except Exception as e:
                    logger.error("停止数据感知失败: %s", e)

            # 停止预加载服务
            preload = components.get("preload")
            if preload and hasattr(preload, "stop"):
                try:
                    preload.stop()
                except Exception as e:
                    logger.error("停止预加载服务失败: %s", e)

            # 关闭轮询网关
            polling = components.get("polling")
            if polling and hasattr(polling, "close"):
                try:
                    polling.close()
                except Exception as e:
                    logger.error("关闭轮询网关失败: %s", e)

            # 关闭虚拟网关
            virtual = components.get("virtual")
            if virtual and hasattr(virtual, "close"):
                try:
                    virtual.close()
                except Exception as e:
                    logger.error("关闭虚拟网关失败: %s", e)

            logger.info("所有组件已关闭")

        except Exception as e:
            logger.error("关闭组件失败: %s", e)

