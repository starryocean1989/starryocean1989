# -*- coding: utf-8 -*-
"""
网络时间同步功能测试脚本

测试内容：
1. NTP时间同步功能
2. 时间偏移量计算
3. 缓存机制
4. 降级策略
5. 与系统时间对比

使用方法：
    python scripts/test_network_time_sync.py
"""

import sys
import time
from pathlib import Path
from datetime import datetime, date

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def print_section(title: str):
    """打印分隔线"""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def test_network_time_sync():
    """测试网络时间同步功能"""

    print_section("网络时间同步功能测试")

    try:
        from backend.infrastructure.data_module_vnpy.utils.network_time import (
            NetworkTimeSync,
            get_real_date,
            get_real_datetime,
            sync_network_time,
            get_time_stats,
        )

        print("✓ 模块导入成功")

        # 测试1: 基本时间同步
        print_section("测试1: 基本时间同步")
        print("正在同步网络时间...")
        success = sync_network_time()

        if success:
            print("✓ 时间同步成功")

            # 显示统计信息
            stats = get_time_stats()
            print(f"\n同步统计:")
            print(f"  - 同步次数: {stats['sync_count']}")
            print(f"  - 失败次数: {stats['sync_failures']}")
            print(f"  - 最后同步时间: {stats['last_sync_time']}")
            print(f"  - 成功服务器: {stats['last_successful_server']}")
            print(f"  - 时间偏移: {stats['cached_offset']:.3f}秒")
            print(f"  - 缓存年龄: {stats['cache_age']:.1f}秒")
            print(f"  - 已同步: {stats['is_synced']}")
        else:
            print("⚠️ 时间同步失败")
            print("这可能是由于网络问题或防火墙阻止了NTP请求")

        # 测试2: 获取真实时间
        print_section("测试2: 获取真实时间")

        # 获取系统时间
        system_datetime = datetime.now()
        system_date = date.today()

        # 获取网络时间
        real_datetime = get_real_datetime()
        real_date = get_real_date()

        print(f"系统时间: {system_datetime}")
        print(f"网络时间: {real_datetime}")
        print(f"时间差: {(real_datetime - system_datetime).total_seconds():.3f}秒")
        print()
        print(f"系统日期: {system_date}")
        print(f"网络日期: {real_date}")

        if system_date != real_date:
            print(f"⚠️ 警告: 系统日期与网络日期不一致！")
        else:
            print(f"✓ 系统日期与网络日期一致")

        # 测试3: 缓存机制
        print_section("测试3: 缓存机制")

        print("测试缓存性能（连续10次查询）...")
        start = time.time()
        for i in range(10):
            _ = get_real_datetime()
        elapsed = time.time() - start

        print(f"✓ 10次查询耗时: {elapsed*1000:.2f}毫秒")
        print(f"✓ 平均每次查询: {elapsed*100:.2f}毫秒")
        print("（使用缓存后查询速度应该非常快）")

        # 测试4: 单例模式
        print_section("测试4: 单例模式")

        sync1 = NetworkTimeSync.get_instance()
        sync2 = NetworkTimeSync.get_instance()

        if sync1 is sync2:
            print("✓ 单例模式工作正常（两次获取的是同一个实例）")
        else:
            print("✗ 单例模式失败（获取了不同的实例）")

        # 测试5: 强制重新同步
        print_section("测试5: 强制重新同步")

        old_stats = get_time_stats()
        old_count = old_stats["sync_count"]

        print("执行强制重新同步...")
        sync_obj = NetworkTimeSync.get_instance()
        force_success = sync_obj.force_sync()

        new_stats = get_time_stats()
        new_count = new_stats["sync_count"]

        if force_success:
            print(f"✓ 强制同步成功")
            print(f"  同步次数从 {old_count} 增加到 {new_count}")
        else:
            print("⚠️ 强制同步失败")

        # 测试6: 数据新鲜度场景模拟
        print_section("测试6: 数据新鲜度场景模拟")

        print("模拟数据新鲜度计算场景:")

        # 模拟本地数据的最新日期
        local_data_date = date(2025, 10, 26)  # 假设本地数据是昨天的

        # 获取真实的当前日期
        current_date = get_real_date()

        # 计算差距
        gap = (current_date - local_data_date).days

        print(f"  本地数据最新日期: {local_data_date}")
        print(f"  真实当前日期: {current_date}")
        print(f"  数据滞后: {gap} 天")

        if gap == 0:
            print("  ✓ 数据是最新的")
        elif gap == 1:
            print("  ⚠️ 数据滞后1天")
        else:
            print(f"  ⚠️ 数据滞后{gap}天，需要更新")

        # 测试7: 缓存管理器集成测试
        print_section("测试7: 缓存管理器集成测试")

        try:
            from backend.infrastructure.data_module_vnpy.cache_manager import (
                DailyCacheManager,
            )

            # 测试get_today
            today_str = DailyCacheManager.get_today()
            print(f"DailyCacheManager.get_today(): {today_str}")

            # 测试is_cache_valid
            test_dates = [
                (today_str, True, "今天的缓存"),
                ("2025-10-26", False, "昨天的缓存"),
                ("2025-10-28", True, "明天的缓存（应该有效）"),
                (None, False, "空缓存日期"),
            ]

            print("\n缓存验证测试:")
            for test_date, expected, desc in test_dates:
                result = DailyCacheManager.is_cache_valid(test_date)
                status = "✓" if result == expected else "✗"
                print(f"  {status} {desc}: {test_date} -> {result} (期望: {expected})")

            print("✓ 缓存管理器集成测试完成")

        except Exception as e:
            print(f"✗ 缓存管理器测试失败: {e}")

        # 总结
        print_section("测试总结")

        final_stats = get_time_stats()

        print("网络时间同步功能测试完成！")
        print()
        print("统计信息:")
        print(f"  - 总同步次数: {final_stats['sync_count']}")
        print(f"  - 失败次数: {final_stats['sync_failures']}")
        print(
            f"  - 当前偏移量: {final_stats['cached_offset']:.3f}秒"
            if final_stats["cached_offset"] is not None
            else "  - 当前偏移量: 未同步"
        )
        print(f"  - 同步状态: {'已同步' if final_stats['is_synced'] else '未同步'}")

        if final_stats["is_synced"]:
            print()
            print("✓ 网络时间同步功能正常")
            print("✓ 可以用于数据新鲜度计算")
            return True
        else:
            print()
            print("⚠️ 网络时间同步未成功")
            print("⚠️ 将降级使用系统时间")
            return False

    except ImportError as e:
        print(f"✗ 模块导入失败: {e}")
        print("请确保已安装 ntplib: pip install ntplib")
        return False

    except Exception as e:
        print(f"✗ 测试过程中发生错误: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("=" * 80)
    print("  网络时间同步功能测试")
    print("  Terminal v0.50")
    print("=" * 80)

    success = test_network_time_sync()

    sys.exit(0 if success else 1)
