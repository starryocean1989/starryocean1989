#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试启动修复.

验证日志系统是否能正常初始化而不卡住。
"""

import logging
import sys
import time
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

def test_logging_system_init():
    """测试日志系统初始化."""
    print("=" * 60)
    print("🧪 测试日志系统初始化")
    print("=" * 60)

    try:
        print("1. 导入日志系统模块...")
        from backend.core.logging_system import initialize_logging_system, LogManager

        print("2. 创建日志管理器实例...")
        manager = LogManager()

        print("3. 测试初始化...")
        success = manager.initialize()

        if success:
            print("✅ 日志系统初始化成功")
            return True
        else:
            print("❌ 日志系统初始化失败")
            return False

    except Exception as e:
        print(f"❌ 日志系统初始化测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_system_manager_service():
    """测试系统管理服务初始化."""
    print("=" * 60)
    print("🔧 测试系统管理服务初始化")
    print("=" * 60)

    try:
        print("1. 导入系统管理服务...")
        from backend.services.system_manager_service import SystemManagerService

        print("2. 创建系统管理服务实例...")
        service = SystemManagerService()

        print("3. 测试初始化...")
        success = service.initialize()

        if success:
            print("✅ 系统管理服务初始化成功")
            return True
        else:
            print("❌ 系统管理服务初始化失败")
            return False

    except Exception as e:
        print(f"❌ 系统管理服务初始化测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数."""
    print("🚀 开始启动修复测试")
    print("=" * 60)

    # 创建数据目录
    Path("data").mkdir(exist_ok=True)

    # 运行测试
    results = []

    print("\n1️⃣ 测试日志系统初始化...")
    results.append(test_logging_system_init())

    print("\n2️⃣ 测试系统管理服务初始化...")
    results.append(test_system_manager_service())

    # 总结结果
    print("=" * 60)
    print("📊 测试结果总结")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"✅ 通过: {passed}/{total}")
    print(f"❌ 失败: {total - passed}/{total}")

    if passed == total:
        print("\n🎉 所有测试通过！启动问题已修复。")
        return 0
    else:
        print(f"\n⚠️ 有 {total - passed} 个测试失败，启动仍可能卡住。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
