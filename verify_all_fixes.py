# -*- coding: utf-8 -*-
"""验证所有架构修复效果.

检查项：
1. ServiceManager.get_service() 支持silent参数
2. ServiceManager.register_service() 重复注册降级为DEBUG
3. DataSensor直接使用LoadBalancer（移除AdaptiveQualityConfig警告）
4. market_board_view使用silent模式查询服务
"""

import re
from pathlib import Path


def check_servicemanager_silent():
    """检查ServiceManager.get_service是否支持silent参数"""
    print("=" * 60)
    print("检查1: ServiceManager.get_service() silent参数")
    print("=" * 60)

    file_path = Path("backend/core/base.py")
    content = file_path.read_text(encoding="utf-8")

    # 检查get_service方法签名
    if "def get_service(self, name: str, silent: bool = False)" in content:
        print("  ✅ get_service方法已添加silent参数")
    else:
        print("  ❌ get_service方法缺少silent参数")
        return False

    # 检查silent逻辑
    if "if not silent:" in content and "ErrorSeverity.DEBUG" in content:
        print("  ✅ silent逻辑已实现，SERVICE_NOT_FOUND降级为DEBUG")
    else:
        print("  ⚠️ silent逻辑可能未完全实现")

    return True


def check_register_service_debug():
    """检查register_service重复注册是否降级为DEBUG"""
    print("\n" + "=" * 60)
    print("检查2: register_service() 重复注册降级")
    print("=" * 60)

    file_path = Path("backend/core/base.py")
    content = file_path.read_text(encoding="utf-8")

    # 查找DUPLICATE_REGISTRATION
    if "DUPLICATE_REGISTRATION" in content:
        # 检查是否降级为DEBUG
        pattern = r"DUPLICATE_REGISTRATION.*?severity=ErrorSeverity\.DEBUG"
        if re.search(pattern, content, re.DOTALL):
            print("  ✅ DUPLICATE_REGISTRATION已降级为DEBUG")
            return True
        else:
            print("  ❌ DUPLICATE_REGISTRATION仍为WARNING或ERROR")
            return False
    else:
        print("  ⚠️ 未找到DUPLICATE_REGISTRATION")
        return False


def check_datasensor_loadbalancer():
    """检查DataSensor是否直接使用LoadBalancer"""
    print("\n" + "=" * 60)
    print("检查3: DataSensor使用LoadBalancer")
    print("=" * 60)

    file_path = Path("backend/infrastructure/data_module_vnpy/local_data/data_quality.py")
    content = file_path.read_text(encoding="utf-8")

    # 检查是否直接导入LoadBalancer
    if (
        "from backend.infrastructure.data_module_vnpy.load_balancer.core import LoadBalancer"
        in content
    ):
        print("  ✅ 已直接导入LoadBalancer")
    else:
        print("  ❌ 未直接导入LoadBalancer")
        return False

    # 检查trigger_scan_with_symbols方法
    # 查找trigger_scan_with_symbols开始的位置
    method_start = content.find("def trigger_scan_with_symbols")
    if method_start == -1:
        print("  ❌ 未找到trigger_scan_with_symbols方法")
        return False

    # 检查方法内是否使用LoadBalancer
    method_content = content[method_start : method_start + 5000]

    if "LoadBalancer(event_engine=None)" in method_content:
        print("  ✅ trigger_scan_with_symbols直接使用LoadBalancer")
    else:
        print("  ❌ trigger_scan_with_symbols仍使用AdaptiveQualityConfig")
        return False

    # 检查是否移除了AdaptiveQualityConfig.calculate_optimal_config调用
    if "AdaptiveQualityConfig.calculate_optimal_config(" in method_content:
        print("  ⚠️ 仍调用AdaptiveQualityConfig.calculate_optimal_config")
        return False
    else:
        print("  ✅ 已移除AdaptiveQualityConfig.calculate_optimal_config调用")

    return True


def check_market_board_silent():
    """检查market_board_view是否使用silent模式"""
    print("\n" + "=" * 60)
    print("检查4: market_board_view使用silent模式")
    print("=" * 60)

    file_path = Path("ui/modules/market_board_view.py")
    content = file_path.read_text(encoding="utf-8")

    # 检查_initialize_service方法
    if 'get_service("market_board_service", silent=True)' in content:
        print("  ✅ market_board_view使用silent模式查询服务")
        return True
    else:
        print("  ❌ market_board_view未使用silent模式")
        return False


def main():
    """主函数"""
    print("\n")
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "架构修复验证脚本" + " " * 15 + "║")
    print("╚" + "=" * 58 + "╝")
    print()

    results = []

    results.append(("ServiceManager.get_service() silent参数", check_servicemanager_silent()))
    results.append(("register_service() 降级为DEBUG", check_register_service_debug()))
    results.append(("DataSensor使用LoadBalancer", check_datasensor_loadbalancer()))
    results.append(("market_board_view使用silent模式", check_market_board_silent()))

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
        print("\n🎉 所有架构修复已正确实施！")
        print("\n下一步：请重启terminal验证效果")
        print("=" * 60)
        print("预期结果：")
        print("  ❌ 不再出现: SERVICE_NOT_FOUND ERROR")
        print("  ❌ 不再出现: DUPLICATE_REGISTRATION WARNING")
        print("  ❌ 不再出现: AdaptiveQualityConfig已弃用 WARNING")
        print("  ✅ 日志清爽，无负面信息")
        print("=" * 60)
        return 0
    else:
        print("\n⚠️ 部分修复未完成，请检查")
        return 1


if __name__ == "__main__":
    import sys

    sys.exit(main())
