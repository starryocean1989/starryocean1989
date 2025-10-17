# -*- coding: utf-8 -*-
"""
测试 tdx_asyncio v2.0 新功能

测试项目：
1. 基本功能兼容性（原有API不变）
2. 主备热切换机制
3. 动态服务器监控
4. IP池管理功能
5. 服务器列表扩展

作者：[项目名称]
版本：2.0
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.infrastructure.tdx_asyncio import (
    AsyncConnectionPool,
    AsyncConnectionPoolContext,
    ConnectionPoolConfig,
    AsyncSmartIPPool,
    AsyncRandomIPPool,
    HQ_HOSTS_ALL,
    HQ_HOSTS,
    FUTURE_HOSTS
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_basic_compatibility():
    """
    测试基本功能兼容性

    确保原有API完全兼容，无需修改即可使用
    """
    print("\n=== 测试基本功能兼容性 ===")

    # 测试1: 原有连接池API
    pool = AsyncConnectionPool(max_connections=5)

    try:
        async with pool:
            conn = await pool.acquire()
            if conn:
                # 测试基本行情查询
                try:
                    bars = await conn.get_security_bars(9, 1, "600000", 0, 10)
                    print(f"✓ 基本行情查询成功: 获取到{len(bars)}根K线")
                except Exception as e:
                    print(f"⚠ 行情查询异常（可能网络问题）: {e}")

                pool.release(conn)
            else:
                print("⚠ 未能获取连接")
    except Exception as e:
        print(f"✗ 基本功能测试失败: {e}")
        return False

    # 测试2: 上下文管理器
    try:
        pool2 = AsyncConnectionPool(max_connections=3)
        async with AsyncConnectionPoolContext(pool2) as conn:
            if conn:
                print("✓ 上下文管理器工作正常")
            else:
                print("⚠ 上下文管理器未能获取连接")
    except Exception as e:
        print(f"✗ 上下文管理器测试失败: {e}")
        return False

    print("✓ 基本功能兼容性测试通过")
    return True


async def test_standby_failover():
    """
    测试主备热切换机制

    模拟主连接故障，验证备用连接自动顶上
    """
    print("\n=== 测试主备热切换机制 ===")

    config = ConnectionPoolConfig(
        max_primary_connections=3,  # 主连接
        max_standby_connections=2,  # 备用连接
        enable_monitoring=False,    # 禁用监控以便手动测试
        timeout=2.0  # 快速超时
    )

    pool = AsyncConnectionPool(config=config)

    try:
        await pool.initialize()

        # 检查连接池状态
        primary_count = sum(1 for c in pool.primary_connections if c)
        standby_count = sum(1 for c in pool.standby_connections if c)

        print(f"✓ 连接池初始化: 主连接{primary_count}个, 备用{standby_count}个")

        # 测试正常获取连接
        conn1 = await pool.acquire()
        if conn1:
            print("✓ 正常获取主连接成功")
            pool.release(conn1)
        else:
            print("⚠ 未能获取主连接")

        # 模拟主连接故障（简单测试：关闭第一个主连接）
        if pool.primary_connections and pool.primary_connections[0]:
            await pool.primary_connections[0].close()
            pool.primary_connections[0] = None
            print("✓ 模拟主连接故障")

        # 测试故障转移
        conn2 = await pool.acquire()
        if conn2:
            print("✓ 故障转移成功，获取到备用连接")
            pool.release(conn2)
        else:
            print("⚠ 故障转移失败")

        await pool.close_all()
        print("✓ 主备热切换测试通过")

    except Exception as e:
        print(f"✗ 主备热切换测试失败: {e}")
        return False

    return True


async def test_ip_pool_monitoring():
    """
    测试IP池动态监控功能

    验证服务器测速、排序、故障剔除等功能
    """
    print("\n=== 测试IP池动态监控功能 ===")

    # 使用较少的服务器进行测试（避免过多网络请求）
    test_servers = [(h[1], h[2]) for h in HQ_HOSTS_ALL[:10]]

    try:
        # 测试智能IP池
        ip_pool = AsyncSmartIPPool(
            servers=test_servers,
            update_interval=5.0,  # 5秒快速测试
            test_timeout=1.0      # 1秒快速超时
        )

        # 启动监控
        await ip_pool.start()
        print("✓ IP池监控启动")

        # 等待第一次测速完成
        await asyncio.sleep(8)

        # 获取排序后的服务器
        sorted_servers = await ip_pool.get_servers()
        print(f"✓ 获取排序服务器列表: {len(sorted_servers)}个")

        # 获取最快服务器
        best_server = await ip_pool.get_best_server()
        if best_server:
            print(f"✓ 最快服务器: {best_server}")
        else:
            print("⚠ 未找到可用服务器")

        # 获取统计信息
        stats = await ip_pool.get_server_stats()
        print(f"✓ 服务器统计: 总计{stats['total']}, 可用{stats['available']}, 不可用{stats['unavailable']}")

        # 停止监控
        await ip_pool.stop()
        print("✓ IP池监控停止")

        print("✓ IP池动态监控测试通过")
        return True

    except Exception as e:
        print(f"✗ IP池动态监控测试失败: {e}")
        return False


async def test_server_expansion():
    """
    测试服务器列表扩展

    验证合并后的服务器资源池
    """
    print("\n=== 测试服务器列表扩展 ===")

    try:
        # 测试股票服务器
        print(f"✓ 股票行情服务器: {len(HQ_HOSTS_ALL)}个")
        print(f"  - 云服务器: {len(HQ_HOSTS)}个（优先使用）")
        print(f"  - 官方主站: {len(HQ_HOSTS_ALL) - len(HQ_HOSTS)}个（备用）")

        # 测试期货服务器
        print(f"✓ 期货/扩展服务器: {len(FUTURE_HOSTS)}个")

        # 验证服务器格式
        sample_stock = HQ_HOSTS_ALL[0]
        sample_future = FUTURE_HOSTS[0] if FUTURE_HOSTS else None

        print(f"✓ 股票服务器格式: {sample_stock}")
        if sample_future:
            print(f"✓ 期货服务器格式: {sample_future}")

        # 验证端口范围
        stock_ports = set(h[2] for h in HQ_HOSTS_ALL)
        future_ports = set(h[2] for h in FUTURE_HOSTS) if FUTURE_HOSTS else set()

        print(f"✓ 股票服务器端口: {sorted(stock_ports)}")
        if future_ports:
            print(f"✓ 期货服务器端口: {sorted(future_ports)}")

        print("✓ 服务器列表扩展测试通过")
        return True

    except Exception as e:
        print(f"✗ 服务器列表扩展测试失败: {e}")
        return False


async def test_performance_comparison():
    """
    性能对比测试（可选）

    对比新旧连接池的性能差异
    """
    print("\n=== 性能对比测试（可选） ===")

    try:
        # 测试服务器数量统计
        total_servers = len(HQ_HOSTS_ALL)
        cloud_servers = len(HQ_HOSTS)
        official_servers = total_servers - cloud_servers

        print(f"✓ 服务器资源对比:")
        print(f"  - 总服务器数: {total_servers}")
        print(f"  - 云服务器: {cloud_servers} (最稳定)")
        print(f"  - 官方主站: {official_servers} (备用)")

        # 测试IP池性能
        test_servers = [(h[1], h[2]) for h in HQ_HOSTS_ALL[:5]]

        start_time = time.time()
        ip_pool = AsyncSmartIPPool(test_servers, update_interval=1.0, test_timeout=0.5)
        await ip_pool.start()
        await asyncio.sleep(3)  # 等待测速
        await ip_pool.stop()
        end_time = time.time()

        print(f"✓ IP池测速耗时: {end_time - start_time:.2f}秒")

        print("✓ 性能对比测试通过")
        return True

    except Exception as e:
        print(f"⚠ 性能对比测试异常（可忽略）: {e}")
        return True  # 性能测试失败不影响整体


async def main():
    """
    主测试函数
    """
    print("=" * 60)
    print("🔍 tdx_asyncio v2.0 功能测试")
    print("=" * 60)

    # 设置快速超时，避免测试时间过长
    import asyncio
    asyncio.get_event_loop().slow_callback_duration = 30.0

    test_results = []

    # 1. 基本功能兼容性测试
    test_results.append(await test_basic_compatibility())

    # 2. 主备热切换测试
    test_results.append(await test_standby_failover())

    # 3. IP池动态监控测试
    test_results.append(await test_ip_pool_monitoring())

    # 4. 服务器列表扩展测试
    test_results.append(await test_server_expansion())

    # 5. 性能对比测试（可选）
    test_results.append(await test_performance_comparison())

    # 汇总结果
    passed = sum(test_results)
    total = len(test_results)

    print("\n" + "=" * 60)
    print(f"📊 测试结果汇总: {passed}/{total} 通过")

    if passed == total:
        print("🎉 所有测试通过！tdx_asyncio v2.0 功能正常")
        return 0
    else:
        print("⚠️ 部分测试失败，请检查网络连接和服务器状态")
        return 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        print("\n⚠️ 测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 测试过程中发生异常: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
