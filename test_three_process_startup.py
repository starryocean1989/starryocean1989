# -*- coding: utf-8 -*-
"""
测试三进程架构启动流程

测试内容：
1. 环境准备阶段
2. 日志系统初始化（MultiProcessLogCollector）
3. 后端初始化阶段（并行启动数据进程、监控进程）
4. 验证进程状态
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 设置基本日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)


async def test_startup():
    """测试启动流程"""
    try:
        print("=" * 70)
        print("测试三进程架构启动流程")
        print("=" * 70)

        from backend.startup import (
            StartupOrchestrator,
            EnvSetupStage,
            LoggingInitStage,
            BackendInitStage,
        )

        # 创建启动编排器
        orchestrator = StartupOrchestrator()

        # 添加启动阶段（只到后端初始化，不启动UI）
        orchestrator.add_stage(EnvSetupStage())
        orchestrator.add_stage(LoggingInitStage())
        orchestrator.add_stage(BackendInitStage())

        print("\n📍 开始执行启动流程...")
        start_time = time.time()

        # 执行启动流程（设置超时，避免无限等待）
        try:
            result = await asyncio.wait_for(orchestrator.startup(), timeout=120.0)  # 2分钟超时
        except asyncio.TimeoutError:
            print("\n⚠️ 启动流程超时（120秒）")
            return False

        # 如果验证失败是因为没有app（测试未启动UI），手动设置占位符
        if not result.success and "启动上下文验证失败" in result.message:
            context = orchestrator.get_context()
            if context.event_engine and not context.app:
                # 设置占位符app，让验证通过
                class PlaceholderApp:
                    def exec(self):
                        return 0

                context.app = PlaceholderApp()
                # 重新验证
                if context.validate():
                    result.success = True
                    result.message = "启动成功（测试模式，未启动UI）"

        elapsed = (time.time() - start_time) * 1000

        print("\n" + "=" * 70)
        print("启动结果:", "✅ 成功" if result.success else "❌ 失败")
        print("总耗时:", f"{elapsed:.0f}ms")
        print("=" * 70)

        if result.success:
            context = orchestrator.get_context()
            print("\n✅ 启动成功！")
            print(f"  - 监控进程PID: {context.monitor_process_pid}")
            print(f"  - 数据进程PID: {context.data_process_pid}")
            print(f"  - 日志系统已初始化: {context.logging_hub_initialized}")

            # 检查进程是否运行
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

            # 检查就绪信号文件（使用绝对路径）
            project_root = Path(__file__).parent
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

        else:
            print(f"\n❌ 启动失败: {result.message}")
            if result.error:
                import traceback

                traceback.print_exception(
                    type(result.error), result.error, result.error.__traceback__
                )

        return result.success

    except Exception as e:
        print(f"\n❌ 启动测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    try:
        success = asyncio.run(test_startup())
        print("\n" + "=" * 70)
        print("测试结果:", "✅ 通过" if success else "❌ 失败")
        print("=" * 70)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n⚠️ 测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
