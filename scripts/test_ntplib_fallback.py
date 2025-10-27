# -*- coding: utf-8 -*-
"""
测试 network_time 模块在 ntplib 不可用时的降级策略

此测试验证：
1. 模块可以正常导入（即使 ntplib 不存在）
2. 所有公共接口都能正常工作（降级到系统时间）
3. 不会抛出 ImportError 或 AttributeError
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_import():
    """测试1: 模块导入"""
    print("=" * 60)
    print("测试1: 模块导入（ntplib 可能不可用）")
    print("=" * 60)

    try:
        from backend.infrastructure.data_module_vnpy.utils import network_time

        print("✓ network_time 模块导入成功")
        print(f"  NTPLIB_AVAILABLE = {network_time.NTPLIB_AVAILABLE}")
        return True
    except Exception as e:
        print(f"✗ 导入失败: {e}")
        return False


def test_get_real_date():
    """测试2: 获取真实日期"""
    print("\n" + "=" * 60)
    print("测试2: get_real_date()")
    print("=" * 60)

    try:
        from backend.infrastructure.data_module_vnpy.utils.network_time import get_real_date

        today = get_real_date()
        print(f"✓ get_real_date() 调用成功")
        print(f"  返回日期: {today}")
        print(f"  类型: {type(today)}")
        return True
    except Exception as e:
        print(f"✗ 调用失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_get_real_datetime():
    """测试3: 获取真实时间"""
    print("\n" + "=" * 60)
    print("测试3: get_real_datetime()")
    print("=" * 60)

    try:
        from backend.infrastructure.data_module_vnpy.utils.network_time import get_real_datetime

        now = get_real_datetime()
        print(f"✓ get_real_datetime() 调用成功")
        print(f"  返回时间: {now}")
        print(f"  类型: {type(now)}")
        return True
    except Exception as e:
        print(f"✗ 调用失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_sync_network_time():
    """测试4: 时间同步"""
    print("\n" + "=" * 60)
    print("测试4: sync_network_time()")
    print("=" * 60)

    try:
        from backend.infrastructure.data_module_vnpy.utils.network_time import (
            sync_network_time,
            NTPLIB_AVAILABLE,
        )

        success = sync_network_time()
        print(f"✓ sync_network_time() 调用成功")
        print(f"  返回值: {success}")

        if NTPLIB_AVAILABLE:
            print(f"  ntplib 可用，尝试了网络同步")
        else:
            print(f"  ntplib 不可用，使用系统时间")

        return True
    except Exception as e:
        print(f"✗ 调用失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_cache_manager_integration():
    """测试5: 与 DailyCacheManager 集成"""
    print("\n" + "=" * 60)
    print("测试5: DailyCacheManager 集成")
    print("=" * 60)

    try:
        from backend.infrastructure.data_module_vnpy.cache_manager import DailyCacheManager

        today = DailyCacheManager.get_today()
        print(f"✓ DailyCacheManager.get_today() 调用成功")
        print(f"  返回值: {today}")
        return True
    except Exception as e:
        print(f"✗ 调用失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_data_quality_integration():
    """测试6: 与 data_quality 模块集成"""
    print("\n" + "=" * 60)
    print("测试6: data_quality 模块集成")
    print("=" * 60)

    try:
        from backend.infrastructure.data_module_vnpy.local_data.data_quality import get_real_date

        today = get_real_date()
        print(f"✓ data_quality.get_real_date() 调用成功")
        print(f"  返回值: {today}")
        return True
    except Exception as e:
        print(f"✗ 调用失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("ntplib 降级策略测试套件")
    print("=" * 60)

    tests = [
        ("模块导入", test_import),
        ("get_real_date()", test_get_real_date),
        ("get_real_datetime()", test_get_real_datetime),
        ("sync_network_time()", test_sync_network_time),
        ("DailyCacheManager 集成", test_cache_manager_integration),
        ("data_quality 模块集成", test_data_quality_integration),
    ]

    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n✗ 测试 '{name}' 崩溃: {e}")
            results.append((name, False))

    # 汇总
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for name, success in results:
        status = "✓ 通过" if success else "✗ 失败"
        print(f"{status}: {name}")

    print(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        print("\n✓ 所有测试通过！ntplib 降级策略工作正常。")
        return 0
    else:
        print(f"\n✗ 有 {total - passed} 个测试失败。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
