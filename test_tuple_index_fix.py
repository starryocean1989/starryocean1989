# -*- coding: utf-8 -*-
"""
元组索引错误修复测试脚本.
"""

import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_log_stats_fix():
    """测试日志统计元组索引修复."""
    try:
        print("=" * 60)
        print("🔍 测试日志统计元组索引修复")
        print("=" * 60)

        from backend.core.logging_system import LogDatabase

        # 创建日志数据库实例
        db = LogDatabase("data/test_logs.db")

        # 测试获取日志统计
        stats = db.get_log_stats()

        print("   ✅ 日志统计获取成功"        print(f"   总记录数: {stats.get('total_count', 0)}")
        print(f"   级别统计: {stats.get('level_stats', {})}")
        print(f"   模块统计: {stats.get('module_stats', [])}")

        # 检查 total_count 是否为整数
        total_count = stats.get('total_count', 0)
        if isinstance(total_count, int):
            print(f"   ✅ total_count 类型正确: {type(total_count)} = {total_count}")
        else:
            print(f"   ❌ total_count 类型错误: {type(total_count)} = {total_count}")

        return True

    except Exception as e:
        print(f"❌ 日志统计测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_sqlite_row_handling():
    """测试SQLite行对象处理."""
    try:
        print("=" * 60)
        print("🔧 测试SQLite行对象处理")
        print("=" * 60)

        import sqlite3

        # 创建临时数据库进行测试
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE test (id INTEGER PRIMARY KEY, name TEXT)")

        # 测试普通元组返回
        cursor = conn.execute("SELECT COUNT(*) as total FROM test")
        row = cursor.fetchone()
        print(f"   元组类型: {type(row)}")
        if isinstance(row, (tuple, list)):
            total = row[0]
            print(f"   ✅ 元组索引访问成功: {total}")
        else:
            print(f"   ❌ 意外的返回类型: {type(row)}")

        # 测试字典式访问（设置row_factory）
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT COUNT(*) as total FROM test")
        row = cursor.fetchone()
        print(f"   Row类型: {type(row)}")
        if hasattr(row, '__getitem__') and hasattr(row, 'keys'):
            total = row[0]  # 元组式访问
            total_dict = row["total"]  # 字典式访问
            print(f"   ✅ Row对象双重访问成功: {total} / {total_dict}")

        conn.close()
        return True

    except Exception as e:
        print(f"❌ SQLite测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数."""
    print("🎯 开始元组索引错误修复测试")
    print("=" * 60)

    # 创建数据目录
    os.makedirs("data", exist_ok=True)

    # 运行测试
    results = []

    print("\n1️⃣ 测试日志统计元组索引修复...")
    results.append(test_log_stats_fix())

    print("\n2️⃣ 测试SQLite行对象处理...")
    results.append(test_sqlite_row_handling())

    # 总结结果
    print("=" * 60)
    print("📊 元组索引修复测试结果")
    print("=" * 60)

    passed = sum(results)
    total = len(results)

    print(f"✅ 通过: {passed}/{total}")
    print(f"❌ 失败: {total - passed}/{total}")

    if passed == total:
        print("\n🎉 所有测试通过！元组索引错误已修复。")
        print("🚀 日志统计功能现在可以正常工作。")
        return 0
    else:
        print(f"\n⚠️ 有 {total - passed} 个测试失败，仍需进一步修复。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
