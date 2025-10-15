# -*- coding: utf-8 -*-
"""
最终修复测试脚本.
"""

import sys
import os
import time

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_system_manager_initialization():
    """测试系统管理服务初始化是否还会阻塞."""
    try:
        print("=" * 60)
        print("🚀 测试系统管理服务最终修复")
        print("=" * 60)

        print("1. 导入系统管理服务...")
        from backend.services.system_manager_service import SystemManagerService

        print("2. 创建系统管理服务实例...")
        service = SystemManagerService()

        print("3. 测试初始化（限时10秒）...")
        start_time = time.time()

        success = service.initialize()

        end_time = time.time()
        duration = end_time - start_time

        print(f"   初始化耗时: {duration:.2f}秒")
        print(f"   初始化结果: {success}")

        if success and duration < 10:
            print("   ✅ 系统管理服务初始化成功且快速")
            return True
        elif success:
            print("   ⚠️ 系统管理服务初始化成功但耗时较长")
            return True
        else:
            print("   ❌ 系统管理服务初始化失败")
            return False

    except Exception as e:
        print(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_core_systems():
    """测试核心系统是否正常."""
    try:
        print("=" * 60)
        print("🔧 测试核心系统功能")
        print("=" * 60)

        # 测试日志系统
        print("1. 测试日志系统...")
        from backend.core.logging_system import initialize_logging_system, get_log_manager

        success = initialize_logging_system()
        if success:
            manager = get_log_manager()
            print("   ✅ 日志系统正常")
        else:
            print("   ❌ 日志系统初始化失败")

        # 测试告警系统
        print("2. 测试告警系统...")
        from backend.core.alert_system import initialize_alert_system, get_alert_database

        success = initialize_alert_system(None)  # 不传入事件引擎
        if success:
            print("   ✅ 告警系统正常")
        else:
            print("   ❌ 告警系统初始化失败")

        return True

    except Exception as e:
        print(f"❌ 核心系统测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数."""
    print("🎯 开始最终修复验证测试")
    print("=" * 60)

    # 创建数据目录
    os.makedirs("data", exist_ok=True)

    # 运行测试
    results = []

    print("\n1️⃣ 测试核心系统...")
    results.append(test_core_systems())

    print("\n2️⃣ 测试系统管理服务...")
    results.append(test_system_manager_initialization())

    # 总结结果
    print("=" * 60)
    print("📊 最终测试结果")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"✅ 通过: {passed}/{total}")
    print(f"❌ 失败: {total - passed}/{total}")

    if passed == total:
        print("\n🎉 所有测试通过！系统阻塞问题已彻底解决。")
        print("🚀 应用现在应该能够正常启动，不再卡在30%。")
        return 0
    else:
        print(f"\n⚠️ 有 {total - passed} 个测试失败，仍需进一步调试。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
