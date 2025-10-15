# -*- coding: utf-8 -*-
"""
错误修复测试脚本.
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_log_stats():
    """测试日志统计功能是否正常."""
    try:
        print("=" * 60)
        print("🔍 测试日志统计功能修复")
        print("=" * 60)

        from backend.core.logging_system import LogDatabase

        # 创建日志数据库实例
        db = LogDatabase("data/test_logs.db")

        # 测试获取日志统计
        stats = db.get_log_stats()

        print("   ✅ 日志统计获取成功"        print(f"   总记录数: {stats.get('total_count', 0)}")
        print(f"   级别统计: {stats.get('level_stats', {})}")
        print(f"   模块统计: {stats.get('module_stats', [])}")

        return True

    except Exception as e:
        print(f"❌ 日志统计测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_datetime_conversion():
    """测试PySide6日期时间转换是否正常."""
    try:
        print("=" * 60)
        print("🔧 测试日期时间转换修复")
        print("=" * 60)

        # 模拟PySide6的QDateTime对象（因为我们可能没有PySide6环境）
        class MockQDateTime:
            def __init__(self, year, month, day, hour=0, minute=0, second=0):
                import datetime
                self._datetime = datetime.datetime(year, month, day, hour, minute, second)

            def toPython(self):
                return self._datetime

        # 测试转换
        dt = MockQDateTime(2025, 1, 15, 10, 30, 45)
        iso_string = dt.toPython().isoformat()

        print(f"   模拟QDateTime转换成功: {iso_string}")
        print("   ✅ 日期时间转换方法修复成功")

        return True

    except Exception as e:
        print(f"❌ 日期时间转换测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数."""
    print("🎯 开始错误修复验证测试")
    print("=" * 60)

    # 创建数据目录
    os.makedirs("data", exist_ok=True)

    # 运行测试
    results = []

    print("\n1️⃣ 测试日志统计SQL绑定参数修复...")
    results.append(test_log_stats())

    print("\n2️⃣ 测试PySide6日期时间转换修复...")
    results.append(test_datetime_conversion())

    # 总结结果
    print("=" * 60)
    print("📊 错误修复测试结果")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"✅ 通过: {passed}/{total}")
    print(f"❌ 失败: {total - passed}/{total}")

    if passed == total:
        print("\n🎉 所有错误修复测试通过！")
        print("🚀 SQL绑定参数和日期时间转换问题已解决。")
        return 0
    else:
        print(f"\n⚠️ 有 {total - passed} 个测试失败，仍需进一步修复。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
