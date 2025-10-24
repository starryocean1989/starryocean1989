# -*- coding: utf-8 -*-
"""
Terminal输出管理器.

功能：
1. 统一管理启动项和Debug信息的Terminal输出
2. 压缩启动输出（保留标题和状态）
3. 条件输出Debug信息
"""
import os
from typing import Any, Dict, Optional


class TerminalOutput:
    """Terminal输出管理器（静态类）."""

    # Debug模块控制（从环境变量或配置文件读取）
    _debug_enabled_modules: set = set()
    _debug_level: str = "normal"  # brief | normal | detailed
    _terminal_debug_output: bool = True

    @classmethod
    def configure(
        cls,
        enabled_modules: Optional[list] = None,
        debug_level: str = "normal",
        terminal_output: bool = True,
    ) -> None:
        """
        配置Debug输出.

        Args:
            enabled_modules: 启用Debug的模块列表
            debug_level: Debug级别 (brief | normal | detailed)
            terminal_output: 是否输出到Terminal
        """
        if enabled_modules:
            cls._debug_enabled_modules = set(enabled_modules)
        else:
            # 从环境变量读取
            env_modules = os.getenv("DEBUG_MODULES", "")
            if env_modules:
                cls._debug_enabled_modules = set(m.strip() for m in env_modules.split(","))

        cls._debug_level = os.getenv("DEBUG_LEVEL", debug_level)
        cls._terminal_debug_output = terminal_output

    @staticmethod
    def print_stage(tag: str, message: str, success: bool = True, error_detail: str = "") -> None:
        """
        打印阶段信息（压缩格式）.

        Args:
            tag: 阶段标签（如 "QT-INIT"）
            message: 简短描述
            success: 是否成功
            error_detail: 错误详情（仅success=False时使用）
        """
        status_icon = "✅" if success else "❌"

        if success:
            # ✅ 状态：单行输出
            print(f"[{tag}] {status_icon} {message}")
        else:
            # ❌ 状态：输出错误原因
            print(f"[{tag}] {status_icon} {message}")
            if error_detail:
                # 缩进输出详细信息
                for line in error_detail.split("\n"):
                    if line.strip():
                        print(f"         {line}")

    @staticmethod
    def print_error(tag: str, error: str, context: Optional[Dict[str, Any]] = None) -> None:
        """
        打印错误信息（详细格式）.

        Args:
            tag: 错误标签
            error: 错误描述
            context: 错误上下文（可选）
        """
        print(f"[{tag}] ❌ {error}")
        if context:
            for key, value in context.items():
                print(f"         {key}: {value}")

    @classmethod
    def print_debug(
        cls,
        tag: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        force_output: bool = False,
    ) -> None:
        """
        打印Debug信息（条件输出）.

        Args:
            tag: Debug标签（如 "DEBUG-MONITOR"）
            message: Debug消息
            details: 详细信息（根据debug_level决定是否输出）
            force_output: 强制输出（忽略模块过滤）
        """
        if not cls._terminal_debug_output and not force_output:
            return

        # 检查模块是否启用Debug
        module_name = tag.replace("DEBUG-", "").lower()
        if not force_output and module_name not in cls._debug_enabled_modules:
            return

        # 根据Debug级别输出
        if cls._debug_level == "brief":
            # brief: 单行输出
            print(f"[{tag}] {message}")

        elif cls._debug_level == "normal":
            # normal: 消息 + 简要详情
            print(f"[{tag}] {message}")
            if details:
                for key, value in details.items():
                    # 限制值的长度
                    value_str = str(value)
                    if len(value_str) > 100:
                        value_str = value_str[:100] + "..."
                    print(f"         {key}: {value_str}")

        elif cls._debug_level == "detailed":
            # detailed: 消息 + 完整详情（JSON格式）
            print(f"[{tag}] {message}")
            if details:
                import json

                try:
                    json_str = json.dumps(details, indent=2, ensure_ascii=False)
                    for line in json_str.split("\n"):
                        print(f"         {line}")
                except Exception:
                    # JSON序列化失败，使用普通格式
                    for key, value in details.items():
                        print(f"         {key}: {value}")

    @classmethod
    def is_debug_enabled(cls, module_name: str) -> bool:
        """
        检查模块是否启用Debug.

        Args:
            module_name: 模块名称

        Returns:
            是否启用
        """
        return module_name.lower() in cls._debug_enabled_modules

    @classmethod
    def get_debug_level(cls) -> str:
        """
        获取当前Debug级别.

        Returns:
            Debug级别
        """
        return cls._debug_level


# 便捷函数
def print_stage(tag: str, message: str, success: bool = True, error_detail: str = "") -> None:
    """打印阶段信息（便捷函数）."""
    TerminalOutput.print_stage(tag, message, success, error_detail)


def print_error(tag: str, error: str, context: Optional[Dict[str, Any]] = None) -> None:
    """打印错误信息（便捷函数）."""
    TerminalOutput.print_error(tag, error, context)


def print_debug(
    tag: str,
    message: str,
    details: Optional[Dict[str, Any]] = None,
    force_output: bool = False,
) -> None:
    """打印Debug信息（便捷函数）."""
    TerminalOutput.print_debug(tag, message, details, force_output)


def configure_debug(
    enabled_modules: Optional[list] = None,
    debug_level: str = "normal",
    terminal_output: bool = True,
) -> None:
    """配置Debug输出（便捷函数）."""
    TerminalOutput.configure(enabled_modules, debug_level, terminal_output)
