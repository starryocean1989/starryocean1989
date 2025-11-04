# -*- coding: utf-8 -*-
"""
启动初始化器模块

提供服务初始化的核心功能。
"""

from .service_initializer import (
    InitializationPhase,
    ServiceInitializer,
    initialize_services,
    initialize_real_services,
    shutdown_services,
    shutdown_real_services,
)

__all__ = [
    "InitializationPhase",
    "ServiceInitializer",
    "initialize_services",
    "initialize_real_services",
    "shutdown_services",
    "shutdown_real_services",
]

