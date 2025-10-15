# -*- coding: utf-8 -*-
"""
测试日志系统修复.
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_logging_system():
    """测试日志系统是否正常工作."""
    try:
        print("=" * 60)
        print("🧪 测试日志系统修复")
        print("=" * 60)

        print("1. 测试日志系统初始化...")
        from backend.core.logging_system import initialize_logging_system

        success = initialize_logging_system()
        print(f"   初始化结果: {success}")

        if success:
            print("   ✅ 日志系统初始化成功")

            # 测试日志记录
            print("2. 测试日志记录...")
            import logging
            logger = logging.getLogger('test_logging_fix')
            logger.info("这是一条测试日志")
            print("   ✅ 测试日志记录成功")

            # 测试获取日志管理器
            print("3. 测试日志管理器...")
            from backend.core.logging_system import get_log_manager
            manager = get_log_manager()
            if manager:
                print("   ✅ 日志管理器获取成功")
                print(f"   日志管理器类型: {type(manager)}")
            else:
                print("   ❌ 日志管理器获取失败")

            return True
        else:
            print("   ❌ 日志系统初始化失败")
            return False

    except Exception as e:
        print(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_logging_system()

    print("=" * 60)
    if success:
        print("🎉 日志系统修复成功！")
    else:
        print("💥 日志系统仍有问题")
    print("=" * 60)
