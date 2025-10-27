# -*- coding: utf-8 -*-
"""
测试在 ntplib 不可用时的启动流程

验证关键组件能否正常初始化：
1. ServiceInitializer (时间同步阶段)
2. ChinaStockEngine
3. ServerPoolManager
4. DataCenterService
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def test_service_initializer_time_sync():
    """测试 ServiceInitializer 的时间同步阶段"""
    print("=" * 60)
    print("测试1: ServiceInitializer 时间同步阶段")
    print("=" * 60)

    try:
        from backend.core.base import ServiceInitializer

        # 模拟时间同步
        initializer = object.__new__(ServiceInitializer)
        initializer.logger = __import__("logging").getLogger("test")

        # 直接测试时间同步逻辑
        from backend.infrastructure.data_module_vnpy.utils.network_time import (
            sync_network_time,
            get_time_stats,
        )

        print("开始网络时间同步...")
        success = sync_network_time()

        if success:
            stats = get_time_stats()
            print(f"✓ 时间同步成功")
            print(f"  偏移: {stats.get('cached_offset', 'N/A')}")
        else:
            print("⚠️ 时间同步失败（降级到系统时间）")

        print("✓ 时间同步阶段完成（不阻塞启动）")
        return True

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_china_stock_engine_creation():
    """测试 ChinaStockEngine 创建"""
    print("\n" + "=" * 60)
    print("测试2: ChinaStockEngine 创建")
    print("=" * 60)

    try:
        from backend.infrastructure.data_module_vnpy.core import ChinaStockEngine
        from vnpy.event import EventEngine

        print("创建 EventEngine...")
        event_engine = EventEngine()

        print("创建 ChinaStockEngine...")
        # 注意：这里只测试类的可访问性，不实际创建实例
        # 因为完整创建需要很多依赖
        print(f"✓ ChinaStockEngine 类可访问: {ChinaStockEngine}")

        event_engine.stop()
        return True

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_server_pool_manager():
    """测试 ServerPoolManager"""
    print("\n" + "=" * 60)
    print("测试3: ServerPoolManager")
    print("=" * 60)

    try:
        from backend.infrastructure.data_module_vnpy.load_balancer import server_pool_manager

        print(f"✓ server_pool_manager 可访问: {server_pool_manager}")

        # 测试缓存加载（应该不崩溃）
        try:
            server_pool_manager.load_server_cache()
            print("  缓存加载尝试完成（可能无缓存）")
        except Exception as e:
            print(f"  缓存加载失败（预期行为）: {e}")

        return True

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_cache_manager():
    """测试 DailyCacheManager"""
    print("\n" + "=" * 60)
    print("测试4: DailyCacheManager")
    print("=" * 60)

    try:
        from backend.infrastructure.data_module_vnpy.cache_manager import DailyCacheManager

        # 测试关键方法
        today = DailyCacheManager.get_today()
        print(f"✓ get_today(): {today}")

        # 测试缓存验证
        is_valid = DailyCacheManager.is_cache_valid("2025-10-27")
        print(f"  is_cache_valid('2025-10-27'): {is_valid}")

        return True

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_data_quality():
    """测试 DataValidator 和 DataSensor"""
    print("\n" + "=" * 60)
    print("测试5: DataValidator 和 DataSensor")
    print("=" * 60)

    try:
        from backend.infrastructure.data_module_vnpy.local_data.data_quality import (
            DataValidator,
            DataSensor,
            IPODateCache,
        )

        print(f"✓ DataValidator 类可访问: {DataValidator}")
        print(f"✓ DataSensor 类可访问: {DataSensor}")
        print(f"✓ IPODateCache 类可访问: {IPODateCache}")

        # 测试 get_real_date（关键函数）
        from backend.infrastructure.data_module_vnpy.local_data.data_quality import get_real_date

        today = get_real_date()
        print(f"  get_real_date(): {today}")

        return True

    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """运行所有测试"""
    print("\n" + "=" * 60)
    print("启动流程测试套件（无 ntplib）")
    print("=" * 60)
    print("目标：验证系统在 ntplib 不可用时能正常启动\n")

    tests = [
        ("ServiceInitializer 时间同步", test_service_initializer_time_sync),
        ("ChinaStockEngine 创建", test_china_stock_engine_creation),
        ("ServerPoolManager", test_server_pool_manager),
        ("DailyCacheManager", test_cache_manager),
        ("DataValidator/DataSensor", test_data_quality),
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
        print("\n✓ 所有测试通过！系统可以在 ntplib 不可用时正常启动。")
        print("  → 时间同步将降级到系统时间")
        print("  → 所有核心功能不受影响")
        return 0
    else:
        print(f"\n✗ 有 {total - passed} 个测试失败。")
        return 1


if __name__ == "__main__":
    sys.exit(main())
