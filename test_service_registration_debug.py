# -*- coding: utf-8 -*-
"""服务注册调试测试脚本"""

import sys


def test_service_registration():
    """测试服务注册状态"""

    print("\n" + "=" * 60)
    print("开始测试服务注册状态")
    print("=" * 60 + "\n")

    # 1. 获取ServiceManager
    print("【测试1】获取ServiceManager...")
    try:
        from backend.core.base import get_service_manager

        service_manager = get_service_manager()

        if service_manager is None:
            print("❌ ServiceManager为None！")
            return False

        print(f"✅ ServiceManager实例: {service_manager}")
        print(f"   services属性: {hasattr(service_manager, 'services')}")

        # 列出所有注册的服务
        if hasattr(service_manager, "services"):
            services = service_manager.services
            print(f"   已注册服务数量: {len(services)}")
            print(f"   已注册服务列表: {list(services.keys())}")

            # 检查system_manager_service是否在列表中
            if "system_manager_service" in services:
                print("   ✅ system_manager_service 已注册")
                service = services["system_manager_service"]
                print(f"      实例: {service}")
                print(f"      log_manager属性: {hasattr(service, 'log_manager')}")
                print(f"      query_logs方法: {hasattr(service, 'query_logs')}")
            else:
                print("   ❌ system_manager_service 未注册！")
                print("   这就是UI日志为空的根本原因！")
                return False
        else:
            print("   ❌ ServiceManager没有services属性！")
            return False

    except Exception as e:
        print(f"❌ 获取ServiceManager失败: {e}")
        import traceback

        traceback.print_exc()
        return False

    # 2. 测试get_service方法
    print("\n【测试2】测试get_service方法...")
    try:
        from backend.core.base import get_service_manager

        service_manager = get_service_manager()

        # 测试silent=True
        service = service_manager.get_service("system_manager_service", silent=True)
        if service:
            print(f"✅ get_service(silent=True)成功获取服务: {service}")
        else:
            print("❌ get_service(silent=True)返回None")
            return False

        # 测试silent=False
        service = service_manager.get_service("system_manager_service", silent=False)
        if service:
            print(f"✅ get_service(silent=False)成功获取服务: {service}")
        else:
            print("❌ get_service(silent=False)返回None")
            return False

    except Exception as e:
        print(f"❌ 测试get_service方法失败: {e}")
        import traceback

        traceback.print_exc()
        return False

    # 3. 测试query_logs调用
    print("\n【测试3】测试query_logs调用...")
    try:
        from backend.core.base import get_service_manager

        service_manager = get_service_manager()

        service = service_manager.get_service("system_manager_service", silent=True)
        if not service:
            print("❌ 无法获取服务")
            return False

        # 调用query_logs
        result = service.query_logs(limit=5)
        print(f"✅ query_logs返回: {result.get('success')}")
        print(f"   logs数量: {len(result.get('logs', []))}")

        if result.get("logs"):
            print(f"   第一条: {result['logs'][0]}")
            return True
        else:
            print("   ⚠️ 查询结果为空")
            return False

    except Exception as e:
        print(f"❌ 测试query_logs调用失败: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_service_registration()

    print("\n" + "=" * 60)
    if success:
        print("✅ 测试完成：服务注册正常")
    else:
        print("❌ 测试完成：发现服务注册问题")
        print("\n问题诊断：")
        print("- ServiceManager已创建，但system_manager_service未注册")
        print("- 这说明SystemManagerService在启动时初始化失败")
        print("- 需要查看启动日志，找出初始化失败的原因")
    print("=" * 60 + "\n")

    sys.exit(0 if success else 1)
