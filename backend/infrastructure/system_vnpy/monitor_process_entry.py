# -*- coding: utf-8 -*-
"""
独立监控进程启动入口.

v0.50重构后，MonitoringProcess类已合并到monitors.py中。
本文件作为独立进程的启动入口，保证路径导入正确。
"""

import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# 配置日志（仅Terminal输出，文件日志已移除）
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("MonitorProcess")


def main():
    """监控进程入口函数."""
    logger.info("=" * 60)
    logger.info("独立监控进程启动（V2 - 混合并发架构）")
    logger.info("=" * 60)

    try:
        # 强制导入monitor_core中的MonitoringProcessV2
        import asyncio
        import platform

        # Windows需要使用SelectorEventLoop以支持ZMQ asyncio
        if platform.system() == "Windows":
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
            logger.info("✅ 已设置Windows SelectorEventLoop策略")

        logger.info("正在导入MonitoringProcessV2...")
        from backend.infrastructure.system_vnpy.monitor_core import MonitoringProcessV2

        logger.info("✅ MonitoringProcessV2导入成功")

        # 创建并启动监控进程V2
        logger.info("正在创建MonitoringProcessV2实例...")

        # 获取父进程PID（主应用的PID）
        import os

        parent_pid = os.getppid()
        logger.info(
            f"[PARENT-PID] 父进程PID（主应用）: {parent_pid}, 当前进程PID（监控进程）: {os.getpid()}"
        )

        monitor = MonitoringProcessV2(parent_pid=parent_pid)
        logger.info("✅ MonitoringProcessV2实例创建成功")

        logger.info("正在启动监控进程主循环...")
        # 创建新的事件循环并使用当前策略
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(monitor.start())
        finally:
            loop.close()

    except ImportError as e:
        logger.error("❌ 导入MonitoringProcessV2失败: %s", e, exc_info=True)
        logger.error("monitor_core.py可能有语法错误或依赖缺失")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("收到中断信号")
    except Exception as e:
        logger.error("❌ 监控进程启动失败: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
