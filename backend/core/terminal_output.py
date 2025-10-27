# -*- coding: utf-8 -*-
"""
终端输出工具模块 - 用于启动阶段的格式化输出.

提供启动阶段的状态打印和调试配置功能。
"""

import logging
from typing import List, Literal

# 全局配置
_debug_config = {
    "enabled_modules": [],
    "debug_level": "normal",
    "terminal_output": True,
}


def print_stage(
    stage_name: str,
    message: str,
    success: bool = True,
    error_detail: str = "",
) -> None:
    """打印启动阶段状态信息.

    Args:
        stage_name: 阶段名称（如 "ENV-SETUP", "QT-INIT" 等）
        message: 状态消息
        success: 是否成功
        error_detail: 错误详情（失败时使用）
    """
    # 状态图标
    icon = "✅" if success else "❌"

    # 格式化输出
    status_line = f"[{stage_name}] {icon} {message}"

    # 打印到终端
    print(status_line)

    # 如果有错误详情，打印额外信息
    if not success and error_detail:
        print(f"    └─ {error_detail}")

    # 同时记录到日志系统
    logger = logging.getLogger("startup")
    if success:
        logger.info("[%s] %s", stage_name, message)
    else:
        error_msg = f"{message}"
        if error_detail:
            error_msg += f" - {error_detail}"
        logger.error("[%s] %s", stage_name, error_msg)


def configure_debug(
    enabled_modules: List[str],
    debug_level: Literal["brief", "normal", "detailed"] = "normal",
    terminal_output: bool = True,
) -> None:
    """配置调试输出.

    Args:
        enabled_modules: 启用调试的模块列表
        debug_level: 调试级别 (brief/normal/detailed)
        terminal_output: 是否输出到终端
    """
    global _debug_config

    _debug_config = {
        "enabled_modules": enabled_modules,
        "debug_level": debug_level,
        "terminal_output": terminal_output,
    }

    # 配置对应模块的日志级别
    for module_name in enabled_modules:
        logger = logging.getLogger(module_name)

        # 根据debug_level设置日志级别
        if debug_level == "detailed":
            logger.setLevel(logging.DEBUG)
        elif debug_level == "normal":
            logger.setLevel(logging.INFO)
        else:  # brief
            logger.setLevel(logging.WARNING)

    # 记录配置信息
    logger = logging.getLogger("startup")
    logger.info(
        "Debug配置: 模块=%s, 级别=%s, 终端输出=%s",
        ", ".join(enabled_modules),
        debug_level,
        terminal_output,
    )


def get_debug_config() -> dict:
    """获取当前调试配置.

    Returns:
        当前的调试配置字典
    """
    return _debug_config.copy()
