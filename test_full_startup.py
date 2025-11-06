# -*- coding: utf-8 -*-
"""
测试完整的UI启动流程（不实际启动UI窗口）
"""

import asyncio
import sys
import time
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from backend.startup import (
    StartupOrchestrator,
    EnvSetupStage,
    LoggingInitStage,
    QtFrameworkStage,
    BackendInitStage,
    UIActivationStage,
)


async def test_full_startup():
    """测试完整的启动流程"""
    print("=" * 60)
    print("测试完整的UI启动流程")
    print("=" * 60)

    try:
        # 设置进程清理
        from start_new import setup_process_cleanup

        setup_process_cleanup()

        # 创建启动编排器
        orchestrator = StartupOrchestrator()

        # 添加所有启动阶段
        orchestrator.add_stage(EnvSetupStage())
        orchestrator.add_stage(LoggingInitStage())
        orchestrator.add_stage(QtFrameworkStage())
        orchestrator.add_stage(BackendInitStage())
        orchestrator.add_stage(UIActivationStage())

        print("\n📍 开始执行完整启动流程...")
        start_time = time.time()

        # 执行启动流程（设置超时，避免无限等待）
        try:
            result = await asyncio.wait_for(orchestrator.startup(), timeout=180.0)  # 3分钟超时
        except asyncio.TimeoutError:
            print("\n⚠️ 启动流程超时（180秒）")
            return False

        elapsed = time.time() - start_time

        print("\n" + "=" * 60)
        print(f"启动结果: {'✅ 成功' if result.success else '❌ 失败'}")
        print(f"总耗时: {elapsed:.0f}ms")
        print("=" * 60)

        if result.success:
            context = orchestrator.get_context()

            print("\n✅ 启动成功！")
            print(f"  - 监控进程PID: {context.monitor_process_pid}")
            print(f"  - 数据进程PID: {context.data_process_pid}")
            print(f"  - 日志系统已初始化: {context.log_queue is not None}")
            print(f"  - EventEngine已初始化: {context.event_engine is not None}")
            print(f"  - MainEngine已初始化: {context.main_engine is not None}")
            print(f"  - Qt应用已初始化: {context.app is not None}")

            # 检查进程状态
            try:
                import psutil

                if context.monitor_process_pid:
                    try:
                        proc = psutil.Process(context.monitor_process_pid)
                        print(f"  - 监控进程状态: ✅ 运行中 ({proc.status()})")
                    except psutil.NoSuchProcess:
                        print("  - 监控进程状态: ❌ 已退出")

                if context.data_process_pid:
                    try:
                        proc = psutil.Process(context.data_process_pid)
                        print(f"  - 数据进程状态: ✅ 运行中 ({proc.status()})")
                    except psutil.NoSuchProcess:
                        print("  - 数据进程状态: ❌ 已退出")
            except ImportError:
                print("  - ⚠️ psutil不可用，无法检查进程状态")

            # 检查就绪信号文件
            signal_files = {
                "监控进程": project_root / "logs" / "monitor_ready.signal",
                "数据进程": project_root / "logs" / "data_process_ready.signal",
            }

            print("\n📋 就绪信号文件检查:")
            for name, signal_file in signal_files.items():
                if signal_file.exists():
                    try:
                        import json

                        with open(signal_file, "r", encoding="utf-8") as f:
                            signal_data = json.load(f)
                        pid = signal_data.get("pid", "未知")
                        level = signal_data.get("level", "未知")
                        print(f"  - {name}: ✅ 已就绪 (PID={pid}, Level={level})")
                    except Exception as e:
                        print(f"  - {name}: ✅ 已就绪 (读取失败: {e})")
                else:
                    print(f"  - {name}: ❌ 未就绪")

            print("\n" + "=" * 60)
            print("测试结果: ✅ 通过")
            print("=" * 60)

            return True
        else:
            print(f"\n❌ 启动失败: {result.message}")
            if result.error:
                import traceback

                traceback.print_exception(
                    type(result.error), result.error, result.error.__traceback__
                )

            print("\n" + "=" * 60)
            print("测试结果: ❌ 失败")
            print("=" * 60)

            return False

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(test_full_startup())
    sys.exit(0 if success else 1)

