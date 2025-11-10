# -*- coding: utf-8 -*-
"""健康监控框架测试."""

import asyncio
import logging
import time
from datetime import datetime

from backend.startup.health import (
    HealthStatus,
    HealthCheckResult,
    get_health_checker_registry,
    get_health_event_bus,
    get_recovery_orchestrator,
    initialize_health_monitoring,
    get_system_health_status,
    get_health_dashboard_data
)
from backend.startup.health.checker import ProcessHealthChecker, SystemHealthChecker
from backend.startup.context import StartupContext


async def test_health_checker():
    """测试健康检查器."""
    print("=" * 60)
    print("测试健康检查器")
    print("=" * 60)

    # 创建模拟的PID获取器
    def mock_pid_getter():
        return 1234  # 模拟PID

    def mock_status_provider():
        return {
            "pid": 1234,
            "state": "ready",
            "status": "healthy",
            "metadata": {"source": "unit-test"},
            "levels": {"level0": {"timestamp": time.time()}},
        }

    # 创建进程健康检查器
    process_checker = ProcessHealthChecker(
        process_name="test_process",
        pid_getter=mock_pid_getter,
        status_provider=mock_status_provider,
        heartbeat_timeout=30.0,
        check_interval=5.0
    )

    # 创建系统健康检查器
    system_checker = SystemHealthChecker(check_interval=10.0)

    # 注册检查器
    registry = get_health_checker_registry()
    registry.register(process_checker)
    registry.register(system_checker)

    print(f"已注册检查器: {registry.list_checkers()}")

    # 执行健康检查
    results = await registry.check_all()

    for name, result in results.items():
        print(f"\n检查器: {name}")
        print(f"状态: {result.status.value}")
        print(f"消息: {result.message}")
        print(f"指标: {result.metrics}")

    # 清理
    await registry.stop_all()
    registry.unregister("test_process")
    registry.unregister("system")


async def test_event_bus():
    """测试事件总线."""
    print("\n" + "=" * 60)
    print("测试事件总线")
    print("=" * 60)

    event_bus = get_health_event_bus()

    # 创建事件处理器
    events_received = []

    async def event_handler(event):
        events_received.append(event)
        print(f"收到事件: {event.event_type.value} from {event.source} - {event.message}")

    # 订阅事件
    from backend.startup.health.events import HealthEventType
    await event_bus.subscribe(
        HealthEventType.PROCESS_HEALTH_CHECK,
        event_handler
    )

    # 发布测试事件
    from backend.startup.health.events import HealthEvent, HealthEventType

    test_event = HealthEvent(
        event_type=HealthEventType.PROCESS_HEALTH_CHECK,
        source="test_process",
        severity="info",
        message="测试事件"
    )

    await event_bus.publish(test_event)

    # 等待事件处理
    await asyncio.sleep(0.1)

    print(f"总共收到 {len(events_received)} 个事件")

    # 获取事件统计
    stats = await event_bus.get_event_statistics()
    print(f"事件统计: {stats}")


async def test_recovery_orchestrator():
    """测试恢复协调器."""
    print("\n" + "=" * 60)
    print("测试恢复协调器")
    print("=" * 60)

    orchestrator = get_recovery_orchestrator()

    # 创建模拟的健康检查结果
    unhealthy_result = HealthCheckResult(
        status=HealthStatus.UNHEALTHY,
        source="test_process",
        message="进程不健康",
        recovery_suggestions=["restart_process"]
    )

    print(f"恢复策略数量: {len(orchestrator.strategies)}")
    for strategy in orchestrator.strategies:
        print(f"- {strategy.name} (优先级: {strategy.priority})")

    # 测试策略是否能处理
    for strategy in orchestrator.strategies:
        can_handle = await strategy.can_handle(unhealthy_result)
        print(f"策略 {strategy.name} 能处理问题: {can_handle}")


async def test_integration():
    """测试完整集成."""
    print("\n" + "=" * 60)
    print("测试完整集成")
    print("=" * 60)

    # 创建模拟的启动上下文
    context = StartupContext()

    try:
        # 初始化健康监控
        await initialize_health_monitoring(context)
        print("健康监控系统初始化成功")

        # 等待一段时间让检查器运行
        print("等待健康检查...")
        await asyncio.sleep(2)

        # 获取系统健康状态
        health_status = await get_system_health_status()
        print(f"\n系统健康状态:")
        print(f"- 总检查器: {health_status.get('total_checkers', 0)}")
        print(f"- 健康数量: {health_status.get('healthy_count', 0)}")
        print(f"- 警告数量: {health_status.get('warning_count', 0)}")
        print(f"- 不健康数量: {health_status.get('unhealthy_count', 0)}")
        print(f"- 严重数量: {health_status.get('critical_count', 0)}")
        print(f"- 健康百分比: {health_status.get('health_percentage', 0):.1f}%")

        # 获取详细报告
        dashboard_data = await get_health_dashboard_data(time_window_minutes=5)
        print(f"\n仪表板数据:")
        print(f"- 时间窗口: {dashboard_data.get('time_window_minutes', 0)} 分钟")
        print(f"- 事件统计: {dashboard_data.get('event_statistics', {})}")
        print(f"- 恢复统计: {dashboard_data.get('recovery_statistics', {})}")

        from backend.startup.health.integration import get_health_integration

        integration = get_health_integration()
        if integration.is_initialized:
            process_overview = integration.get_process_overview()
            print(f"- 进程快照: {process_overview}")

    except Exception as e:
        print(f"集成测试失败: {e}")
        import traceback
        traceback.print_exc()

    finally:
        # 清理
        from backend.startup.health import shutdown_health_monitoring
        await shutdown_health_monitoring()
        print("健康监控系统已关闭")


async def main():
    """主测试函数."""
    print("开始健康监控框架测试")
    print(f"测试时间: {datetime.now()}")

    # 设置日志级别
    logging.basicConfig(level=logging.INFO)

    try:
        # 运行各项测试
        await test_health_checker()
        await test_event_bus()
        await test_recovery_orchestrator()
        await test_integration()

        print("\n" + "=" * 60)
        print("所有测试完成")
        print("=" * 60)

    except Exception as e:
        print(f"测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
