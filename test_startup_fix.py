# -*- coding: utf-8 -*-
"""验证启动修复效果.

检查项：
1. 监控握手是否被移除（start_async_fixed.py中不应有握手代码）
2. SystemManagerService是否条件启动定时器
3. initialize_optional_services是否有服务去重逻辑
"""

import re
from pathlib import Path


def check_monitor_handshake_removed():
    """检查监控握手是否已从主流程移除"""
    print("=" * 60)
    print("检查1：监控握手是否已移除")
    print("=" * 60)

    file_path = Path("start_async_fixed.py")
    content = file_path.read_text(encoding="utf-8")

    # 检查是否还有握手相关代码
    handshake_patterns = [
        r"try_handshake_with_progressive_retry",
        r"handshake_ok\s*=",
        r"HANDSHAKE.*失败",
    ]

    found_issues = []
    for pattern in handshake_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        if matches:
            found_issues.append(f"  ❌ 找到握手代码: {pattern}")

    # 检查是否有新的注释说明握手延迟
    if "握手延迟到SystemManagerService" in content:
        print("  ✅ 发现握手延迟说明")
    else:
        found_issues.append("  ⚠️ 未找到握手延迟说明")

    # 检查是否设置环境变量
    if "MONITOR_PROCESS_PID" in content:
        print("  ✅ 设置监控进程PID环境变量")
    else:
        found_issues.append("  ❌ 未设置MONITOR_PROCESS_PID环境变量")

    if found_issues:
        print("\n问题:")
        for issue in found_issues:
            print(issue)
        return False
    else:
        print("  ✅ 监控握手已成功移除")
        return True


def check_system_manager_conditional_timer():
    """检查SystemManagerService是否条件启动定时器"""
    print("\n" + "=" * 60)
    print("检查2：SystemManagerService条件启动定时器")
    print("=" * 60)

    file_path = Path("backend/services/system_manager_service.py")
    content = file_path.read_text(encoding="utf-8")

    # 检查是否有_test_zmq_connection方法
    if "def _test_zmq_connection" in content:
        print("  ✅ 找到_test_zmq_connection方法")
    else:
        print("  ❌ 未找到_test_zmq_connection方法")
        return False

    # 检查是否有条件启动逻辑
    if "if zmq_connection_ok:" in content:
        print("  ✅ 找到条件启动定时器逻辑")
    else:
        print("  ❌ 未找到条件启动定时器逻辑")
        return False

    # 检查是否有降级提示
    if "状态推送定时器未启动（降级模式）" in content:
        print("  ✅ 找到降级模式提示")
    else:
        print("  ⚠️ 未找到降级模式提示")

    return True


def check_optional_services_deduplication():
    """检查可选服务加载是否有去重逻辑"""
    print("\n" + "=" * 60)
    print("检查3：可选服务加载去重")
    print("=" * 60)

    file_path = Path("backend/core/base.py")
    content = file_path.read_text(encoding="utf-8")

    # 检查ServiceManager是否有has_service方法
    if "def has_service" in content:
        print("  ✅ ServiceManager有has_service方法")
    else:
        print("  ❌ ServiceManager缺少has_service方法")
        return False

    # 检查initialize_optional_services是否使用has_service
    if "self.service_manager.has_service(service_name)" in content:
        print("  ✅ initialize_optional_services使用has_service检查")
    else:
        print("  ❌ initialize_optional_services未使用has_service检查")
        return False

    # 检查是否有跳过重复初始化的逻辑
    if "跳过重复初始化" in content:
        print("  ✅ 找到跳过重复初始化逻辑")
    else:
        print("  ⚠️ 未找到跳过重复初始化提示")

    return True


def main():
    """主函数"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "启动修复验证脚本" + " " * 15 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    results = []

    results.append(("监控握手移除", check_monitor_handshake_removed()))
    results.append(("SystemManagerService条件定时器", check_system_manager_conditional_timer()))
    results.append(("可选服务去重", check_optional_services_deduplication()))

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
        print("\n🎉 所有修复已正确实施！")
        return 0
    else:
        print("\n⚠️ 部分修复未完成，请检查")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())


