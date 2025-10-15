#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试日志和告警系统集成.

验证日志收集、告警触发、前端推送等功能是否正常工作。
"""

import logging
import sys
import time
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_logging_system():
    """测试日志系统."""
    print("=" * 60)
    print("🧪 测试日志系统")
    print("=" * 60)

    try:
        # 导入日志系统
        from backend.core.logging_system import initialize_logging_system, get_log_manager

        # 初始化日志系统（模拟事件引擎）
        class MockEventEngine:
            def put(self, event):
                print(f"📨 收到日志事件: {event.type_}")

        mock_engine = MockEventEngine()
        success = initialize_logging_system(mock_engine, {
            "db_path": "data/logs.db",
            "retention_days": 30,
        })

        if not success:
            print("❌ 日志系统初始化失败")
            return False

        # 获取日志管理器
        log_manager = get_log_manager()

        # 测试日志记录和查询
        print("📝 测试日志记录...")

        # 模拟一些日志记录
        logger = logging.getLogger("test.module")
        logger.info("这是一条测试信息日志")
        logger.warning("这是一条测试警告日志")
        logger.error("这是一条测试错误日志")

        # 等待日志处理
        time.sleep(1)

        # 查询日志
        logs = log_manager.query_logs(limit=10)
        print(f"✅ 查询到 {len(logs)} 条日志记录")

        for log in logs[:3]:  # 只显示前3条
            print(f"  - [{log['level']}] {log['module']}: {log['message']}")

        # 测试日志统计
        stats = log_manager.get_log_stats()
        print(f"✅ 日志统计: {stats.get('total_count', 0)} 条总记录")

        print("✅ 日志系统测试完成")
        return True

    except Exception as e:
        print(f"❌ 日志系统测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_alert_system():
    """测试告警系统."""
    print("=" * 60)
    print("🚨 测试告警系统")
    print("=" * 60)

    try:
        # 导入告警系统
        from backend.core.alert_system import initialize_alert_system, get_alert_database
        from backend.core.utils import AlertEngine

        # 初始化告警系统（模拟事件引擎）
        class MockEventEngine:
            def put(self, event):
                print(f"📨 收到告警事件: {event.type_}")

        mock_engine = MockEventEngine()
        success = initialize_alert_system(mock_engine, {
            "db_path": "data/alerts.db",
            "suppression_window": 300,
        })

        if not success:
            print("❌ 告警系统初始化失败")
            return False

        # 获取告警数据库
        alert_db = get_alert_database()

        # 获取告警引擎（单例）
        alert_engine = AlertEngine()

        print(f"✅ 告警引擎加载了 {len(alert_engine.get_all_rules())} 个规则")

        # 测试告警规则评估
        print("📝 测试告警规则评估...")

        # 模拟错误日志上下文
        error_context = {
            "level": "ERROR",
            "module": "test.module",
            "message": "数据库连接失败，请检查配置",
        }

        # 评估规则
        triggered_alerts = alert_engine.evaluate_rules(error_context)
        print(f"✅ 触发了 {len(triggered_alerts)} 个告警")

        for alert in triggered_alerts:
            print(f"  - [{alert.severity.value}] {alert.message}")

        # 查询告警记录
        alerts = alert_db.get_alerts(limit=10)
        print(f"✅ 数据库中保存了 {len(alerts)} 个告警记录")

        for alert in alerts[:3]:  # 只显示前3条
            print(f"  - [{alert.status.value}] {alert.severity.value}: {alert.message}")

        print("✅ 告警系统测试完成")
        return True

    except Exception as e:
        print(f"❌ 告警系统测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_frontend_components():
    """测试前端组件导入."""
    print("=" * 60)
    print("🖥️ 测试前端组件导入")
    print("=" * 60)

    try:
        # 测试日志管理组件导入
        from ui.components.system_manager.log_manager_widget import LogManagerWidget
        print("✅ 日志管理组件导入成功")

        # 测试告警管理组件导入
        from ui.components.system_manager.alert_manager_widget import AlertManagerWidget
        print("✅ 告警管理组件导入成功")

        # 测试告警滚动条组件导入
        from ui.widgets.alert_ticker import AlertTicker
        print("✅ 告警滚动条组件导入成功")

        print("✅ 前端组件测试完成")
        return True

    except Exception as e:
        print(f"❌ 前端组件测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数."""
    print("🚀 开始日志和告警系统集成测试")
    print("=" * 60)

    # 创建数据目录
    Path("data").mkdir(exist_ok=True)

    # 运行测试
    results = []

    print("\n1️⃣ 测试日志系统...")
    results.append(test_logging_system())

    print("\n2️⃣ 测试告警系统...")
    results.append(test_alert_system())

    print("\n3️⃣ 测试前端组件...")
    results.append(test_frontend_components())

    # 总结结果
    print("=" * 60)
    print("📊 测试结果总结")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"✅ 通过: {passed}/{total}")
    print(f"❌ 失败: {total - passed}/{total}")

    if passed == total:
        print("\n🎉 所有测试通过！日志和告警系统集成成功。")
        return 0
    else:
        print(f"\n⚠️ 有 {total - passed} 个测试失败，请检查上述错误信息。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
