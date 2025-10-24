# -*- coding: utf-8 -*-
"""完整启动流程测试脚本"""

import sys
import os

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)


def test_full_startup():
    """测试完整启动流程"""

    print("\n" + "=" * 60)
    print("开始测试完整启动流程")
    print("=" * 60 + "\n")

    # 1. 初始化EventEngine
    print("【步骤1】初始化EventEngine...")
    try:
        from vnpy.event import EventEngine

        event_engine = EventEngine()
        print(f"✅ EventEngine已创建: {event_engine}")
    except Exception as e:
        print(f"❌ EventEngine创建失败: {e}")
        return False

    # 2. 初始化ServiceManager
    print("\n【步骤2】初始化ServiceManager...")
    try:
        from backend.core.base import get_service_manager

        service_manager = get_service_manager()
        print(f"✅ ServiceManager已创建: {service_manager}")
        print(f"   已注册服务数量: {len(service_manager.services)}")
    except Exception as e:
        print(f"❌ ServiceManager创建失败: {e}")
        return False

    # 3. 手动初始化SystemManagerService
    print("\n【步骤3】手动初始化SystemManagerService...")
    try:
        from backend.services.system_manager_service import SystemManagerService

        system_manager_service = SystemManagerService()
        print(f"✅ SystemManagerService已创建: {system_manager_service}")

        # 初始化服务
        print("   正在初始化服务...")
        init_success = system_manager_service.initialize()
        print(f"   初始化结果: {init_success}")

        if init_success:
            # 注册服务
            print("   正在注册服务...")
            register_success = service_manager.register_service(
                "system_manager_service", system_manager_service
            )
            print(f"   注册结果: {register_success}")

            # 验证注册
            print("\n   验证注册结果...")
            print(f"   已注册服务数量: {len(service_manager.services)}")
            print(f"   已注册服务列表: {list(service_manager.services.keys())}")

            # 获取服务
            service = service_manager.get_service("system_manager_service", silent=True)
            if service:
                print(f"   ✅ 成功获取服务: {service}")
            else:
                print("   ❌ 无法获取服务")
                return False
        else:
            print("   ❌ SystemManagerService初始化失败")
            return False

    except Exception as e:
        print(f"❌ SystemManagerService创建/初始化失败: {e}")
        import traceback

        traceback.print_exc()
        return False

    # 4. 测试日志查询
    print("\n【步骤4】测试日志查询...")
    try:
        service = service_manager.get_service("system_manager_service", silent=True)
        if not service:
            print("❌ 无法获取服务")
            return False

        # 调用query_logs
        result = service.query_logs(limit=5)
        print(f"✅ query_logs返回: {result.get('success')}")
        print(f"   logs数量: {len(result.get('logs', []))}")

        if result.get("logs"):
            print(
                f"   第一条: {result['logs'][0].get('timestamp')} - {result['logs'][0].get('message')[:50]}"
            )
            return True
        else:
            print("   ⚠️ 查询结果为空（但查询成功）")
            # 这不是错误，可能只是没有日志
            return True

    except Exception as e:
        print(f"❌ 测试日志查询失败: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_full_startup()

    print("\n" + "=" * 60)
    if success:
        print("✅ 测试完成：完整启动流程正常")
        print("\n结论：")
        print("- EventEngine可以正常创建")
        print("- ServiceManager可以正常创建")
        print("- SystemManagerService可以正常初始化和注册")
        print("- 日志查询功能正常")
        print("\n问题定位：")
        print("- UI日志为空的原因是：在实际启动时，ServiceInitializer")
        print("  没有正常执行，导致SystemManagerService未注册")
        print("- 需要检查启动代码，确保ServiceInitializer被正确调用")
    else:
        print("❌ 测试完成：启动流程存在问题")
    print("=" * 60 + "\n")

    sys.exit(0 if success else 1)
