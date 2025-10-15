# -*- coding: utf-8 -*-
"""
系统阻塞问题修复测试.
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
        print("🧪 测试系统管理服务初始化")
        print("=" * 60)

        print("1. 导入系统管理服务...")
        from backend.services.system_manager_service import SystemManagerService

        print("2. 创建系统管理服务实例...")
        service = SystemManagerService()

        print("3. 测试初始化（可能需要一些时间）...")
        start_time = time.time()

        success = service.initialize()

        end_time = time.time()
        duration = end_time - start_time

        print(f"   初始化耗时: {duration:.2f}秒")
        print(f"   初始化结果: {success}")

        if success:
            print("   ✅ 系统管理服务初始化成功")
            return True
        else:
            print("   ❌ 系统管理服务初始化失败")
            return False

    except Exception as e:
        print(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_system_monitor():
    """测试系统监控功能是否正常."""
    try:
        print("=" * 60)
        print("🔍 测试系统监控功能")
        print("=" * 60)

        print("1. 导入系统监控...")
        from backend.infrastructure.system_vnpy.system_monitor import SystemMonitor

        print("2. 创建系统监控实例...")
        monitor = SystemMonitor()

        print("3. 测试获取资源使用情况...")
        start_time = time.time()

        resource_usage = monitor.get_resource_usage()

        end_time = time.time()
        duration = end_time - start_time

        print(f"   获取耗时: {duration:.3f}秒")
        print(f"   CPU使用率: {resource_usage.cpu_percent}%")
        print(f"   内存使用率: {resource_usage.memory_percent}%")
        print(f"   磁盘使用率: {resource_usage.disk_percent}%")

        if duration < 5:  # 如果耗时少于5秒，认为正常
            print("   ✅ 系统监控功能正常")
            return True
        else:
            print(f"   ❌ 系统监控耗时过长: {duration:.3f}秒")
            return False

    except Exception as e:
        print(f"❌ 系统监控测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数."""
    print("🚀 开始系统阻塞问题修复测试")
    print("=" * 60)

    # 创建数据目录
    os.makedirs("data", exist_ok=True)

    # 运行测试
    results = []

    print("\n1️⃣ 测试系统监控功能...")
    results.append(test_system_monitor())

    print("\n2️⃣ 测试系统管理服务初始化...")
    results.append(test_system_manager_initialization())

    # 总结结果
    print("=" * 60)
    print("📊 测试结果总结")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"✅ 通过: {passed}/{total}")
    print(f"❌ 失败: {total - passed}/{total}")

    if passed == total:
        print("\n🎉 所有测试通过！系统阻塞问题已修复。")
        return 0
    else:
        print(f"\n⚠️ 有 {total - passed} 个测试失败，系统仍可能存在阻塞问题。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
