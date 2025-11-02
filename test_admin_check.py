#!/usr/bin/env python3
"""
测试不同的管理员权限检查方法
"""
import sys
import os
import logging

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """主函数"""
    print("🔍 测试管理员权限检查...")

    # 1. 直接使用ctypes检查
    print("\n📊 方法1: 直接使用ctypes.windll.shell32.IsUserAnAdmin()")
    try:
        import ctypes
        result1 = ctypes.windll.shell32.IsUserAnAdmin()
        print(f"   结果: {result1} ({'管理员' if result1 else '普通用户'})")
    except Exception as e:
        print(f"   错误: {e}")
        result1 = False

    # 2. 使用system_toolkit.is_admin()
    print("\n📊 方法2: 使用system_toolkit.is_admin()")
    try:
        from backend.infrastructure.system_vnpy import is_admin
        result2 = is_admin()
        print(f"   结果: {result2} ({'管理员' if result2 else '普通用户'})")
    except Exception as e:
        print(f"   错误: {e}")
        result2 = False

    # 3. 使用SystemManagerService._check_admin_privileges()
    print("\n📊 方法3: 使用SystemManagerService._check_admin_privileges()")
    try:
        from backend.services.system_manager_service import SystemManagerService
        service = SystemManagerService()
        result3 = service._check_admin_privileges()
        print(f"   结果: {result3} ({'管理员' if result3 else '普通用户'})")
    except Exception as e:
        print(f"   错误: {e}")
        result3 = False

    # 4. 检查进程信息
    print("\n📊 方法4: 检查进程信息")
    try:
        import os
        print(f"   当前进程PID: {os.getpid()}")
        print(f"   当前用户: {os.getenv('USERNAME', 'Unknown')}")
        print(f"   当前工作目录: {os.getcwd()}")
    except Exception as e:
        print(f"   错误: {e}")

    # 5. 尝试创建需要管理员权限的操作
    print("\n📊 方法5: 尝试创建Named Pipe（需要管理员权限）")
    try:
        from backend.infrastructure.native_ipc import AsyncIPCPipe
        print("   Native IPC模块可用")
        # 这里不实际创建，只是检查模块是否可用
    except Exception as e:
        print(f"   Native IPC模块不可用: {e}")

    # 总结
    print(f"\n📊 总结:")
    print(f"   方法1 (ctypes直接): {result1}")
    print(f"   方法2 (system_toolkit): {result2}")
    print(f"   方法3 (SystemManagerService): {result3}")

    if result1 == result2 == result3:
        print("   ✅ 所有方法结果一致")
    else:
        print("   ❌ 方法结果不一致！")

    # 6. 检查当前是否能连接到监控进程的Named Pipe
    print("\n📊 方法6: 尝试连接监控进程Named Pipe")
    try:
        import asyncio
        from backend.infrastructure.native_ipc import AsyncIPCPipe

        async def test_pipe():
            try:
                pipe = await AsyncIPCPipe.client("monitor_query")
                print("   ✅ 成功连接到monitor_query管道")
                await pipe.close()
                return True
            except Exception as e:
                print(f"   ❌ 连接monitor_query管道失败: {e}")
                return False

        # 运行异步测试
        result = asyncio.run(test_pipe())
        print(f"   管道连接结果: {result}")

    except Exception as e:
        print(f"   管道连接测试失败: {e}")

if __name__ == "__main__":
    main()
