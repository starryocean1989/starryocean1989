# -*- coding: utf-8 -*-
"""验证SERVICE_NOT_FOUND和DUPLICATE_REGISTRATION修复效果.

检查项：
1. system_manager_view.py中所有get_service调用都使用silent=True
2. 移除了手动服务创建逻辑
3. 添加了on_service_ready回调方法
4. main_window.py转发服务就绪通知
"""

import re
from pathlib import Path


def check_silent_mode():
    """检查所有get_service调用是否使用silent=True"""
    print("=" * 60)
    print("检查1: system_manager_view.py使用silent模式查询服务")
    print("=" * 60)

    file_path = Path("ui/modules/system_manager_view.py")
    content = file_path.read_text(encoding="utf-8")

    # 查找所有get_service("system_manager_service")调用
    pattern = r'get_service\([\'"]system_manager_service[\'"](?:,\s*silent\s*=\s*True)?\)'
    matches = re.findall(pattern, content)

    # 查找不带silent=True的调用
    bad_pattern = r'get_service\([\'"]system_manager_service[\'"](?!,\s*silent\s*=\s*True)\)'
    bad_matches = re.findall(bad_pattern, content)

    print(f"  总调用数: {len(matches)}")
    print(f"  未使用silent=True: {len(bad_matches)}")

    if len(bad_matches) == 0:
        print("  ✅ 所有调用都使用了silent=True")
        return True
    else:
        print(f"  ❌ 发现{len(bad_matches)}处未使用silent=True的调用")
        return False


def check_no_manual_creation():
    """检查是否移除了手动服务创建逻辑"""
    print("\n" + "=" * 60)
    print("检查2: 移除手动服务创建逻辑")
    print("=" * 60)

    file_path = Path("ui/modules/system_manager_view.py")
    content = file_path.read_text(encoding="utf-8")

    # 检查是否存在SystemManagerService()调用
    if "SystemManagerService()" in content:
        print("  ❌ 仍存在手动创建SystemManagerService的代码")
        return False
    else:
        print("  ✅ 已移除手动服务创建逻辑")

    # 检查是否存在手动register_service调用
    pattern = r'register_service\([\'"]system_manager_service[\'"]'
    if re.search(pattern, content):
        print("  ⚠️ 仍存在手动register_service调用")
        return False
    else:
        print("  ✅ 已移除手动register_service调用")

    return True


def check_service_ready_callback():
    """检查是否添加了on_service_ready回调"""
    print("\n" + "=" * 60)
    print("检查3: on_service_ready回调方法")
    print("=" * 60)

    file_path = Path("ui/modules/system_manager_view.py")
    content = file_path.read_text(encoding="utf-8")

    # 检查是否定义了on_service_ready方法
    if "def on_service_ready(self, service_name: str, success: bool):" in content:
        print("  ✅ 已添加on_service_ready回调方法")
    else:
        print("  ❌ 未找到on_service_ready回调方法")
        return False

    # 检查是否处理system_manager_service就绪
    if 'service_name == "system_manager_service"' in content:
        print("  ✅ 处理system_manager_service就绪事件")
    else:
        print("  ⚠️ 未处理system_manager_service就绪事件")

    return True


def check_main_window_forwarding():
    """检查MainWindow是否转发服务就绪通知"""
    print("\n" + "=" * 60)
    print("检查4: MainWindow转发服务就绪通知")
    print("=" * 60)

    file_path = Path("ui/main_window.py")
    content = file_path.read_text(encoding="utf-8")

    # 检查on_service_ready方法是否转发到SystemManagerView
    if "system_manager_view.on_service_ready" in content:
        print("  ✅ MainWindow转发服务就绪通知到SystemManagerView")
        return True
    else:
        print("  ❌ MainWindow未转发服务就绪通知")
        return False


def check_error_severity_debug():
    """检查ErrorSeverity是否添加了DEBUG级别"""
    print("\n" + "=" * 60)
    print("检查5: ErrorSeverity添加DEBUG级别")
    print("=" * 60)

    file_path = Path("backend/core/base.py")
    content = file_path.read_text(encoding="utf-8")

    # 检查ErrorSeverity枚举
    if 'DEBUG = "debug"' in content:
        print("  ✅ ErrorSeverity已添加DEBUG级别")
        return True
    else:
        print("  ❌ ErrorSeverity缺少DEBUG级别")
        return False


def main():
    """主函数"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "服务修复验证脚本" + " " * 15 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    results = []

    results.append(("所有get_service调用使用silent=True", check_silent_mode()))
    results.append(("移除手动服务创建逻辑", check_no_manual_creation()))
    results.append(("添加on_service_ready回调", check_service_ready_callback()))
    results.append(("MainWindow转发服务就绪通知", check_main_window_forwarding()))
    results.append(("ErrorSeverity添加DEBUG级别", check_error_severity_debug()))

    print("\n" + "=" * 60)
    print("总结")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{name}: {status}")

    print()
    print(f"总计: {passed}/{total} 项通过")

    if passed == total:
        print("\n🎉 所有服务修复已正确实施！")
        print("\n下一步：请重启terminal验证效果")
        print("=" * 60)
        print("预期结果：")
        print("  ❌ 不再出现: SERVICE_NOT_FOUND DEBUG日志")
        print("  ❌ 不再出现: DUPLICATE_REGISTRATION DEBUG日志")
        print("  ❌ 不再出现: SERVICE_ACCESS_EXCEPTION ERROR日志")
        print("  ❌ 不再出现: REGISTRATION_EXCEPTION ERROR日志")
        print("  ✅ 日志清爽，UI功能正常")
        print("=" * 60)
        return 0
    else:
        print("\n⚠️ 部分修复未完成，请检查")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
