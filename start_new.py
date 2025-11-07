# -*- coding: utf-8 -*-
"""
新的启动入口 - 使用StartupOrchestrator统一管理启动流程

这是重构后的启动入口，使用新的启动架构：
- StartupOrchestrator: 统一管理所有启动阶段
- StartupContext: 统一管理所有启动依赖
- Stages: 分阶段初始化（环境准备、日志系统、Qt框架、后端服务、UI激活）
- Workers: 后台工作线程（后端初始化、监控进程、缓存验证）

特点：
- 单一入口管理所有启动逻辑
- 清晰的阶段划分和依赖关系
- 统一的错误处理和降级机制
- 简洁的Terminal输出和详细的事件日志文件
"""

import asyncio
import atexit
import logging
import signal
import sys
from pathlib import Path

# 在环境准备阶段之前禁用所有日志输出，确保环境准备阶段的输出是第一个输出
# 环境准备阶段会使用print直接输出，不使用logger
logging.basicConfig(level=logging.CRITICAL, force=True)

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 导入启动架构
from backend.startup import (
    StartupOrchestrator,
    EnvSetupStage,
    LoggingInitStage,
    QtFrameworkStage,
    BackendInitStage,
    UIActivationStage,
)


def setup_process_cleanup():
    """设置进程清理（signal处理和atexit）

    支持以下场景的进程清理：
    - Terminal关闭（SIGINT/SIGTERM）
    - 正常退出（atexit）
    - 窗口关闭（Qt事件）
    - 异常退出（finally块）
    """
    try:
        from backend.startup.workers.monitor_launcher import cleanup_all_processes as cleanup_monitor
        from backend.startup.workers.monitor_launcher import _cleanup_signal_file as cleanup_monitor_signal
    except ImportError:  # pragma: no cover
        cleanup_monitor = None
        cleanup_monitor_signal = None

    try:
        from backend.startup.workers.data_launcher import cleanup_all_processes as cleanup_data
        from backend.startup.workers.data_launcher import _cleanup_signal_file as cleanup_data_signal
    except ImportError:  # pragma: no cover
        cleanup_data = None
        cleanup_data_signal = None

    def _run_cleanup(label: str = "清理流程"):
        errors = []

        if cleanup_monitor:
            try:
                cleanup_monitor()
            except Exception as exc:  # pragma: no cover
                errors.append(f"监控进程: {exc}")
        if cleanup_data:
            try:
                cleanup_data()
            except Exception as exc:  # pragma: no cover
                errors.append(f"数据进程: {exc}")

        for signal_cleanup in (cleanup_monitor_signal, cleanup_data_signal):
            if signal_cleanup:
                try:
                    signal_cleanup()
                except Exception:
                    pass

        if errors:
            print(f"❌ {label}失败: {'; '.join(errors)}")

    def signal_handler(signum, frame):
        """信号处理器"""
        print(f"\n⚠️ 收到信号 {signum}，正在清理进程...")
        _run_cleanup(label="进程清理")
        sys.exit(1)

    # 注册信号处理器（Windows上只支持SIGINT和SIGTERM）
    if sys.platform != "win32":
        # Unix系统支持更多信号
        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)
    else:
        # Windows系统
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    # 注册atexit清理（作为后备）
    def cleanup_on_exit():
        _run_cleanup()

    atexit.register(cleanup_on_exit)


async def main():
    """主入口函数"""
    # 🔧 新增：设置进程清理
    setup_process_cleanup()

    # 创建启动编排器
    orchestrator = StartupOrchestrator()

    # 添加所有启动阶段（按顺序）
    orchestrator.add_stage(EnvSetupStage())
    orchestrator.add_stage(LoggingInitStage())
    orchestrator.add_stage(QtFrameworkStage())
    orchestrator.add_stage(BackendInitStage())
    orchestrator.add_stage(UIActivationStage())

    # 执行启动流程
    # 注意：ai_log_process已在LoggingInitStage中启动，这里不需要再次包裹
    result = await orchestrator.startup()

    # 检查启动结果
    if not result.success:
        print(f"❌ 启动失败: {result.message}", file=sys.stderr)
        if result.error:
            import traceback
            traceback.print_exception(type(result.error), result.error, result.error.__traceback__)
        return 1

    # 启动成功，运行Qt应用
    context = orchestrator.get_context()
    if context.app:
        print(f"✅ 启动成功（总耗时: {result.elapsed_ms:.0f}ms）")
        return context.app.exec()

    return 0


if __name__ == "__main__":
    # 运行异步主函数
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️ 启动被用户中断", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"❌ 启动异常: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

