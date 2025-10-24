# -*- coding: utf-8 -*-
"""日志查询调试测试脚本"""

import sys
import json
from typing import Dict, Any


def test_log_query_flow():
    """测试日志查询完整流程"""

    print("\n" + "=" * 60)
    print("开始测试日志查询流程")
    print("=" * 60 + "\n")

    # 1. 测试数据库直接查询
    print("【测试1】直接查询数据库...")
    try:
        import sqlite3

        conn = sqlite3.connect("data/terminal.db")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM system_logs")
        count = cursor.fetchone()[0]
        print(f"✅ 数据库中有 {count} 条日志记录")

        # 查询最近5条
        cursor.execute(
            "SELECT id, timestamp, level, module, message FROM system_logs ORDER BY timestamp DESC LIMIT 5"
        )
        rows = cursor.fetchall()
        print(f"✅ 查询到最近5条日志：")
        for row in rows:
            print(f"   - [{row[1]}] {row[2]} {row[3]}: {row[4][:50]}...")
        conn.close()
    except Exception as e:
        print(f"❌ 数据库查询失败: {e}")
        return False

    # 2. 测试LogDatabase查询
    print("\n【测试2】LogDatabase查询...")
    try:
        from backend.services.system_manager_service import LogDatabase

        log_db = LogDatabase()
        logs = log_db.query_logs(limit=5)
        print(f"✅ LogDatabase查询到 {len(logs)} 条日志")
        if logs:
            print(f"   第一条: {logs[0]}")
        else:
            print("   ⚠️ 查询结果为空")
    except Exception as e:
        print(f"❌ LogDatabase查询失败: {e}")
        import traceback

        traceback.print_exc()
        return False

    # 3. 测试LogManager查询
    print("\n【测试3】LogManager查询...")
    try:
        from backend.services.system_manager_service import get_log_manager

        log_manager = get_log_manager()
        print(f"   LogManager实例: {log_manager}")
        print(f"   database属性: {hasattr(log_manager, 'database')}")
        print(f"   query_logs方法: {hasattr(log_manager, 'query_logs')}")

        logs = log_manager.query_logs(limit=5)
        print(f"✅ LogManager查询到 {len(logs)} 条日志")
        if logs:
            print(f"   第一条: {logs[0]}")
        else:
            print("   ⚠️ 查询结果为空")
    except Exception as e:
        print(f"❌ LogManager查询失败: {e}")
        import traceback

        traceback.print_exc()
        return False

    # 4. 测试SystemManagerService查询
    print("\n【测试4】SystemManagerService查询...")
    try:
        from backend.core.base import get_service_manager

        service_manager = get_service_manager()

        if service_manager is None:
            print("   ⚠️ ServiceManager未初始化，尝试手动创建SystemManagerService")
            from backend.services.system_manager_service import SystemManagerService

            system_service = SystemManagerService()
            # 不执行initialize()，因为需要event_engine
            print(f"   SystemManagerService实例: {system_service}")
            print(f"   log_manager属性: {hasattr(system_service, 'log_manager')}")

            # 直接调用query_logs
            result = system_service.query_logs(limit=5)
            print(f"✅ SystemManagerService查询返回: {result.get('success')}")
            print(f"   logs数量: {len(result.get('logs', []))}")
            if result.get("logs"):
                print(f"   第一条: {result['logs'][0]}")
            else:
                print("   ⚠️ 查询结果为空")
        else:
            system_service = service_manager.get_service("system_manager_service", silent=True)
            if system_service:
                print(f"✅ 从ServiceManager获取到SystemManagerService")
                result = system_service.query_logs(limit=5)
                print(f"✅ SystemManagerService查询返回: {result.get('success')}")
                print(f"   logs数量: {len(result.get('logs', []))}")
            else:
                print("❌ 从ServiceManager获取SystemManagerService失败")
                return False
    except Exception as e:
        print(f"❌ SystemManagerService查询失败: {e}")
        import traceback

        traceback.print_exc()
        return False

    # 5. 测试UI调用流程
    print("\n【测试5】模拟UI调用流程...")
    try:
        from backend.core.base import get_service_manager

        service_manager = get_service_manager()

        if service_manager is None:
            print("   ⚠️ ServiceManager未初始化，无法测试UI调用流程")
            print("   这可能是UI日志为空的原因！")
            return False

        system_service = service_manager.get_service("system_manager_service", silent=True)
        if not system_service:
            print("   ❌ 无法获取SystemManagerService")
            print("   这就是UI日志为空的根本原因！")
            return False

        # 模拟UI的查询
        result = system_service.query_logs(limit=1000)
        if result.get("success"):
            logs = result.get("logs", [])
            print(f"✅ 模拟UI查询成功，获取到 {len(logs)} 条日志")
            return True
        else:
            print(f"❌ 模拟UI查询失败: {result.get('message')}")
            return False
    except Exception as e:
        print(f"❌ 模拟UI调用流程失败: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_log_query_flow()

    print("\n" + "=" * 60)
    if success:
        print("✅ 测试完成：所有流程正常")
    else:
        print("❌ 测试完成：发现问题")
    print("=" * 60 + "\n")

    sys.exit(0 if success else 1)
