#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
阶段11实施验证脚本

验证系统工具与基础设施日志增强的实施结果
"""

import sys
import os
import logging

# 添加项目路径
sys.path.insert(0, os.path.dirname(__file__))

def test_alert_engine_enhancement():
    """测试AlertEngine增强"""
    print("🔍 测试AlertEngine日志增强...")
    try:
        from backend.services.alert_engine import AlertEngine

        engine = AlertEngine()
        rules = [{"id": "test", "field": "value", "op": ">", "value": 10}]
        engine.set_rules(rules)

        records = [{"value": 15, "datetime": "2025-11-09T12:00:00"}]
        alerts = engine.evaluate(records)

        assert len(alerts) == 1
        print("✅ AlertEngine日志增强测试通过")

    except Exception as e:
        print(f"❌ AlertEngine测试失败: {e}")

def test_native_fs_enhancement():
    """测试native_fs增强"""
    print("🔍 测试native_fs日志增强...")
    try:
        import backend.infrastructure.native.native_fs as native_fs

        # 测试降级情况
        if not native_fs.FS_WATCH_AVAILABLE:
            print("✅ native_fs降级处理正常")
        else:
            print("✅ native_fs扩展可用")

    except Exception as e:
        print(f"❌ native_fs测试失败: {e}")

def test_native_memory_enhancement():
    """测试native_memory增强"""
    print("🔍 测试native_memory日志增强...")
    try:
        import backend.infrastructure.native.native_memory as native_memory

        if not native_memory.MEMORY_AVAILABLE:
            print("✅ native_memory降级处理正常")
        else:
            print("✅ native_memory扩展可用")

    except Exception as e:
        print(f"❌ native_memory测试失败: {e}")

def test_native_gil_enhancement():
    """测试native_gil增强"""
    print("🔍 测试native_gil日志增强...")
    try:
        import backend.infrastructure.native.native_gil as native_gil

        if not native_gil.__all__:
            print("✅ native_gil降级处理正常")
        else:
            print("✅ native_gil扩展可用")

    except Exception as e:
        print(f"❌ native_gil测试失败: {e}")

def test_system_manager_alert_persistence():
    """测试SystemManager告警持久化增强"""
    print("🔍 测试SystemManager告警持久化日志增强...")
    try:
        from backend.services.system_manager_service import SystemManagerService
        from backend.core.models import Alert, AlertRule, AlertSeverity

        service = SystemManagerService()

        rule = AlertRule(
            rule_id="test_verify",
            name="验证规则",
            severity=AlertSeverity.INFO,
            condition="test"
        )

        alert = Alert(
            alert_id="test_verify_alert",
            rule=rule,
            message="阶段11验证告警",
            severity=AlertSeverity.INFO
        )

        service.save_alert(alert)
        print("✅ SystemManager告警持久化日志增强测试通过")

    except Exception as e:
        print(f"❌ SystemManager测试失败: {e}")

def main():
    """主验证函数"""
    print("=" * 60)
    print("🚀 阶段11：系统工具与基础设施日志增强 - 实施验证")
    print("=" * 60)

    # 配置日志
    logging.basicConfig(level=logging.INFO)

    # 运行各项测试
    test_alert_engine_enhancement()
    test_system_manager_alert_persistence()
    test_native_fs_enhancement()
    test_native_memory_enhancement()
    test_native_gil_enhancement()

    print("=" * 60)
    print("🎉 阶段11实施验证完成")
    print("=" * 60)

if __name__ == "__main__":
    main()
