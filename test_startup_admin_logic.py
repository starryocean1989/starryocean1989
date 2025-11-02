#!/usr/bin/env python3
"""
测试启动脚本的管理员权限检查逻辑
"""
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    """主函数"""
    print("🔍 测试启动脚本的管理员权限检查逻辑...")

    try:
        # 模拟启动脚本的逻辑
        from backend.infrastructure.system_vnpy import (
            is_admin,
            run_as_admin,
        )
        from backend.core.config import get_settings

        # 1. 读取启动策略
        print("\n📊 步骤1: 读取启动策略")
        startup_settings = get_settings().startup
        admin_policy = getattr(startup_settings, "admin_policy", "auto")
        print(f"   admin_policy: {admin_policy}")

        # 2. 检查管理员权限
        print("\n📊 步骤2: 检查管理员权限")
        has_admin = is_admin()
        print(f"   has_admin: {has_admin}")

        # 3. 模拟启动脚本的逻辑分支
        print("\n📊 步骤3: 模拟启动脚本的逻辑分支")
        if not has_admin:
            print("   进入分支: not has_admin")
            print("   应该显示: '未能获取管理员权限，部分功能将降级'")

            if admin_policy == "auto":
                print("   admin_policy == 'auto'")
                print("   应该调用: run_as_admin()")
                print("   ⚠️ 注意：run_as_admin()会退出当前进程！")
                # 这里不实际调用，只是模拟
                print("   [模拟] 调用 run_as_admin() - 进程应该退出")
            elif admin_policy == "ask":
                print("   admin_policy == 'ask'")
                print("   应该: 继续执行（不阻塞启动）")
        else:
            print("   进入分支: has_admin")
            print("   应该显示: '已具有管理员权限'")

        # 4. 检查为什么实际启动时显示"已具有管理员权限"
        print("\n📊 步骤4: 分析为什么实际启动时显示'已具有管理员权限'")
        print("   可能的原因:")
        print("   1. 启动脚本确实以管理员权限运行")
        print("   2. run_as_admin()成功启动了管理员进程")
        print("   3. 权限检查逻辑有bug")
        print("   4. 配置文件被修改")

        # 5. 检查当前进程的详细信息
        print("\n📊 步骤5: 检查当前进程的详细信息")
        import ctypes
        try:
            # 获取当前进程的令牌信息
            import ctypes.wintypes

            # 检查是否在管理员组中
            result = ctypes.windll.shell32.IsUserAnAdmin()
            print(f"   IsUserAnAdmin(): {result}")

            # 检查进程完整性级别
            try:
                import win32api
                import win32security
                import win32process

                # 获取当前进程句柄
                process_handle = win32api.GetCurrentProcess()

                # 获取进程令牌
                token_handle = win32security.OpenProcessToken(
                    process_handle,
                    win32security.TOKEN_QUERY
                )

                # 获取令牌信息
                token_info = win32security.GetTokenInformation(
                    token_handle,
                    win32security.TokenIntegrityLevel
                )

                print(f"   进程完整性级别信息可用")

            except ImportError:
                print("   win32api不可用，无法获取详细令牌信息")
            except Exception as e:
                print(f"   获取令牌信息失败: {e}")

        except Exception as e:
            print(f"   检查进程信息失败: {e}")

        print("\n✅ 测试完成")

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
