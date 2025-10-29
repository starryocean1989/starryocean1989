# -*- coding: utf-8 -*-
"""管理员权限检查和自动提权工具."""

import sys
import ctypes
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def is_admin() -> bool:
    """
    检查当前进程是否具有管理员权限.

    Returns:
        bool: 如果具有管理员权限返回True
    """
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception as e:
        logger.error("检查管理员权限失败: %s", e)
        return False


def run_as_admin(_wait: bool = True) -> Optional[int]:
    """
    以管理员权限重新启动当前脚本.

    Args:
        _wait: 是否等待新进程结束（默认True）[预留参数，暂未实现]

    Returns:
        Optional[int]: 如果wait=True，返回新进程的退出码；否则返回None

    Note:
        此函数会终止当前进程！
    """
    if is_admin():
        logger.info("当前已具有管理员权限")
        return None

    logger.info("正在请求管理员权限...")

    try:
        # 获取当前脚本路径和参数
        script = sys.argv[0]
        params = " ".join([f'"{arg}"' for arg in sys.argv[1:]])

        # 使用ShellExecute以管理员身份运行
        # 参数说明：
        # - lpVerb: "runas" 表示以管理员身份运行
        # - lpFile: Python解释器路径
        # - lpParameters: 脚本路径和参数
        # - nShowCmd: 1 表示正常显示窗口
        ret = ctypes.windll.shell32.ShellExecuteW(
            None,  # hwnd
            "runas",  # lpVerb: 以管理员身份运行
            sys.executable,  # lpFile: Python解释器
            f'"{script}" {params}',  # lpParameters: 脚本和参数
            None,  # lpDirectory
            1,  # nShowCmd: SW_NORMAL
        )

        # ShellExecuteW返回值：
        # > 32: 成功
        # <= 32: 错误码
        if ret <= 32:
            logger.error("以管理员身份启动失败，错误码: %s", ret)
            return None

        logger.info("✅ 已请求管理员权限，新进程已启动")

        # 退出当前进程
        sys.exit(0)

    except Exception as e:
        logger.error("请求管理员权限失败: %s", e, exc_info=True)
        return None


def ensure_admin(auto_elevate: bool = True, message: Optional[str] = None) -> bool:
    """
    确保当前进程具有管理员权限.

    Args:
        auto_elevate: 如果没有权限，是否自动提权（默认True）
        message: 自定义提示消息

    Returns:
        bool: 如果具有管理员权限返回True

    Note:
        如果auto_elevate=True且没有权限，此函数会重启进程并退出当前进程！
    """
    if is_admin():
        return True

    if message:
        logger.warning(message)
    else:
        logger.warning("=" * 80)
        logger.warning("⚠️  此应用需要管理员权限才能访问硬件传感器")
        logger.warning("=" * 80)

    if not auto_elevate:
        logger.warning("\n请以管理员身份运行此程序。")
        return False

    logger.warning("\n正在请求管理员权限...")
    logger.warning("（如果出现UAC提示，请点击'是'）")

    run_as_admin()

    # 如果run_as_admin失败（没有退出进程），返回False
    return False


def check_admin_for_hardware_monitoring() -> bool:
    """
    检查硬件监控所需的管理员权限.

    专门用于硬件监控场景，提供友好的提示信息。

    Returns:
        bool: 如果具有管理员权限返回True
    """
    if is_admin():
        logger.info("✅ 已具有管理员权限（硬件监控）")
        return True

    logger.warning("❌ 缺少管理员权限（硬件监控功能可能受限）")
    logger.warning("提示：某些硬件传感器（如AMD Ryzen温度）需要管理员权限")
    return False


__all__ = [
    "is_admin",
    "run_as_admin",
    "ensure_admin",
    "check_admin_for_hardware_monitoring",
]
