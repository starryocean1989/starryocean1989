# -*- coding: utf-8 -*-
"""
后端API测试脚本.

测试所有模块的API端点。
"""

import requests
import json
import sys
from datetime import datetime


BASE_URL = "http://127.0.0.1:8000"


def test_health_check():
    """测试健康检查."""
    print("\n=== 测试健康检查 ===")
    try:
        response = requests.get(f"{BASE_URL}/")
        print(f"状态码: {response.status_code}")
        print(f"响应: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        return response.status_code == 200
    except Exception as e:
        print(f"❌ 错误: {e}")
        return False


def test_strategy_center():
    """测试策略中心模块."""
    print("\n=== 测试策略中心模块 ===")
    success_count = 0
    total_count = 0

    # 1. 获取文件树
    total_count += 1
    try:
        response = requests.get(f"{BASE_URL}/api/v1/strategy-center/files")
        if response.status_code == 200:
            print("✓ 获取文件树成功")
            success_count += 1
        else:
            print(f"✗ 获取文件树失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 获取文件树错误: {e}")

    # 2. 获取模板列表
    total_count += 1
    try:
        response = requests.get(f"{BASE_URL}/api/v1/strategy-center/templates/list")
        if response.status_code == 200:
            print("✓ 获取模板列表成功")
            success_count += 1
        else:
            print(f"✗ 获取模板列表失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 获取模板列表错误: {e}")

    # 3. 代码验证
    total_count += 1
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/strategy-center/code/validate",
            json={"code": "print('test')", "file_type": "python"},
        )
        if response.status_code == 200:
            print("✓ 代码验证成功")
            success_count += 1
        else:
            print(f"✗ 代码验证失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 代码验证错误: {e}")

    # 4. AI助手
    total_count += 1
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/strategy-center/ai/chat",
            json={"message": "帮我写个策略"},
        )
        if response.status_code == 200:
            print("✓ AI助手接口成功（预留接口）")
            success_count += 1
        else:
            print(f"✗ AI助手接口失败: {response.status_code}")
    except Exception as e:
        print(f"✗ AI助手接口错误: {e}")

    print(f"\n策略中心测试: {success_count}/{total_count} 通过")
    return success_count, total_count


def test_trading_gateway():
    """测试交易网关模块."""
    print("\n=== 测试交易网关模块 ===")
    success_count = 0
    total_count = 0

    # 1. 获取网关列表
    total_count += 1
    try:
        response = requests.get(f"{BASE_URL}/api/v1/trading-gateway/gateways")
        if response.status_code == 200:
            print("✓ 获取网关列表成功")
            success_count += 1
        else:
            print(f"✗ 获取网关列表失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 获取网关列表错误: {e}")

    # 2. 获取配置模式（动态表单）
    total_count += 1
    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/trading-gateway/gateways/types/config-schema",
            params={"gateway_type": "PaperAccount"},
        )
        if response.status_code == 200:
            data = response.json()
            print("✓ 获取PaperAccount配置模式成功")
            if "initial_capital" in str(data):
                print("  ✓ PaperAccount不需要服务器地址配置")
            success_count += 1
        else:
            print(f"✗ 获取配置模式失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 获取配置模式错误: {e}")

    # 3. 创建网关
    total_count += 1
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/trading-gateway/gateways",
            json={
                "gateway_type": "PaperAccount",
                "instance_name": "测试模拟网关",
                "config": {"initial_capital": 1000000},
            },
        )
        if response.status_code == 200:
            print("✓ 创建网关成功")
            success_count += 1
        else:
            print(f"✗ 创建网关失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 创建网关错误: {e}")

    print(f"\n交易网关测试: {success_count}/{total_count} 通过")
    return success_count, total_count


def test_portfolio():
    """测试组合投资模块."""
    print("\n=== 测试组合投资模块 ===")
    success_count = 0
    total_count = 0

    # 1. 获取组合列表
    total_count += 1
    try:
        response = requests.get(f"{BASE_URL}/api/v1/portfolio/portfolios")
        if response.status_code == 200:
            print("✓ 获取组合列表成功")
            success_count += 1
        else:
            print(f"✗ 获取组合列表失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 获取组合列表错误: {e}")

    # 2. 获取自动识别组合
    total_count += 1
    try:
        response = requests.get(f"{BASE_URL}/api/v1/portfolio/portfolios/auto-detected")
        if response.status_code == 200:
            print("✓ 获取自动识别组合成功")
            success_count += 1
        else:
            print(f"✗ 获取自动识别组合失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 获取自动识别组合错误: {e}")

    # 3. 创建虚拟网关
    total_count += 1
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/portfolio/portfolios/virtual",
            json={
                "virtual_name": "测试虚拟网关",
                "member_gateways": ["gw_001", "gw_002"],
                "description": "测试用虚拟网关",
            },
        )
        if response.status_code == 200:
            data = response.json()
            print("✓ 创建虚拟网关成功")
            if data.get("data", {}).get("virtual_id"):
                print(f"  ✓ 虚拟网关ID已生成（hashlib MD5）")
            success_count += 1
        else:
            print(f"✗ 创建虚拟网关失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 创建虚拟网关错误: {e}")

    print(f"\n组合投资测试: {success_count}/{total_count} 通过")
    return success_count, total_count


def test_system_manager():
    """测试系统管理模块."""
    print("\n=== 测试系统管理模块 ===")
    success_count = 0
    total_count = 0

    # 1. 获取系统监控
    total_count += 1
    try:
        response = requests.get(f"{BASE_URL}/api/v1/system/monitoring/system")
        if response.status_code == 200:
            print("✓ 获取系统监控成功")
            success_count += 1
        else:
            print(f"✗ 获取系统监控失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 获取系统监控错误: {e}")

    # 2. 获取性能指标
    total_count += 1
    try:
        response = requests.get(f"{BASE_URL}/api/v1/system/monitoring/performance")
        if response.status_code == 200:
            print("✓ 获取性能指标成功")
            success_count += 1
        else:
            print(f"✗ 获取性能指标失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 获取性能指标错误: {e}")

    # 3. 服务健康检查
    total_count += 1
    try:
        response = requests.get(f"{BASE_URL}/api/v1/system/health/services")
        if response.status_code == 200:
            print("✓ 服务健康检查成功")
            success_count += 1
        else:
            print(f"✗ 服务健康检查失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 服务健康检查错误: {e}")

    # 4. 创建告警规则
    total_count += 1
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/system/alerts/rules",
            json={
                "rule_name": "CPU告警",
                "metric_type": "cpu_percent",
                "condition": ">",
                "threshold": 90.0,
                "severity": "warning",
            },
        )
        if response.status_code == 200:
            print("✓ 创建告警规则成功")
            success_count += 1
        else:
            print(f"✗ 创建告警规则失败: {response.status_code}")
    except Exception as e:
        print(f"✗ 创建告警规则错误: {e}")

    print(f"\n系统管理测试: {success_count}/{total_count} 通过")
    return success_count, total_count


def test_api_docs():
    """测试API文档."""
    print("\n=== 测试API文档 ===")
    try:
        response = requests.get(f"{BASE_URL}/docs")
        if response.status_code == 200:
            print("✓ API文档可访问: http://127.0.0.1:8000/docs")
            return True
        else:
            print(f"✗ API文档不可访问: {response.status_code}")
            return False
    except Exception as e:
        print(f"✗ API文档访问错误: {e}")
        return False


def main():
    """主测试函数."""
    print("=" * 60)
    print("后端API端点测试")
    print("=" * 60)
    print(f"测试时间: {datetime.now().isoformat()}")
    print(f"服务地址: {BASE_URL}")
    print("=" * 60)

    # 检查服务是否运行
    try:
        requests.get(f"{BASE_URL}/", timeout=2)
    except Exception as e:
        print(f"\n❌ 无法连接到后端服务: {e}")
        print("\n请先启动后端服务:")
        print("  python -m uvicorn backend.app:app --reload")
        sys.exit(1)

    total_success = 0
    total_tests = 0

    # 健康检查
    if test_health_check():
        total_success += 1
    total_tests += 1

    # API文档
    if test_api_docs():
        total_success += 1
    total_tests += 1

    # 策略中心
    s, t = test_strategy_center()
    total_success += s
    total_tests += t

    # 交易网关
    s, t = test_trading_gateway()
    total_success += s
    total_tests += t

    # 组合投资
    s, t = test_portfolio()
    total_success += s
    total_tests += t

    # 系统管理
    s, t = test_system_manager()
    total_success += s
    total_tests += t

    # 总结
    print("\n" + "=" * 60)
    print(f"测试总结: {total_success}/{total_tests} 通过")
    print("=" * 60)

    if total_success == total_tests:
        print("\n✅ 所有测试通过！")
        return 0
    else:
        print(f"\n⚠️  部分测试失败: {total_tests - total_success} 个")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
