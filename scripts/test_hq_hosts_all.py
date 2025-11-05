"""
HQ_HOSTS_ALL 服务器连接测试脚本
- 测试 HQ_HOSTS_ALL 中所有服务器的连接性
- 并发测试，显示延迟和连接状态
- 简单直接，无额外复杂逻辑
"""

import sys
import asyncio
import time
from pathlib import Path
from typing import Tuple, Dict
from datetime import datetime

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.tdx_asyncio import AsyncTdxHq_API
from backend.infrastructure.tdx_asyncio.constants import HQ_HOSTS_ALL


async def test_server(name: str, ip: str, port: int, timeout: float = 5.0) -> Tuple[bool, float]:
    """测试单个服务器连接"""
    try:
        api = AsyncTdxHq_API()
        start_time = time.time()

        connected = await asyncio.wait_for(api.connect(ip, port), timeout=timeout)

        if connected:
            latency = (time.time() - start_time) * 1000
            await api.disconnect()
            print(f"  ✅ {name} ({ip}:{port}) - {latency:.0f}ms")
            return True, latency
        else:
            print(f"  ❌ {name} ({ip}:{port}) - 连接失败")
            return False, float('inf')
    except asyncio.TimeoutError:
        print(f"  ⏱️ {name} ({ip}:{port}) - 超时 (>{timeout}s)")
        return False, float('inf')
    except Exception as e:
        print(f"  ❌ {name} ({ip}:{port}) - 异常: {type(e).__name__}")
        return False, float('inf')


async def test_servers_batch(
    servers: list,
    timeout: float = 5.0,
    batch_size: int = 10
) -> Dict[Tuple[str, str, int], Tuple[bool, float]]:
    """批量测试服务器"""
    results = {}
    total = len(servers)

    print(f"\n开始测试 HQ_HOSTS_ALL: 总共 {total} 个服务器，每批 {batch_size} 个")
    print("=" * 60)

    start_time = time.time()

    for i in range(0, total, batch_size):
        batch = servers[i:i + batch_size]
        batch_num = i // batch_size + 1
        total_batches = (total + batch_size - 1) // batch_size

        print(f"\n📦 批次 {batch_num}/{total_batches} (服务器 {i+1}-{min(i+batch_size, total)}/{total})")
        print("-" * 60)

        tasks = [test_server(name, ip, port, timeout) for name, ip, port in batch]
        batch_results = await asyncio.gather(*tasks)

        for server, (passed, latency) in zip(batch, batch_results):
            results[server] = (passed, latency)

        batch_passed = sum(1 for passed, _ in batch_results if passed)
        print(f"\n  批次统计: 通过 {batch_passed}/{len(batch)}")

    elapsed = time.time() - start_time
    return results, elapsed


async def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("HQ_HOSTS_ALL 服务器连接测试")
    print("=" * 60)

    # 显示当前状态
    print(f"\n📊 当前状态:")
    print(f"  - HQ_HOSTS_ALL: {len(HQ_HOSTS_ALL)} 个服务器")

    if not HQ_HOSTS_ALL:
        print("\n❌ HQ_HOSTS_ALL 为空，没有服务器可测试")
        return

    # 执行测试
    print(f"\n⏱️ 预计耗时: {len(HQ_HOSTS_ALL) * 0.5 / 10:.1f} - {len(HQ_HOSTS_ALL) * 1.5 / 10:.1f} 分钟")

    results, elapsed = await test_servers_batch(
        HQ_HOSTS_ALL,
        timeout=5.0,
        batch_size=10
    )

    # 统计结果
    passed_servers = [(s, latency) for s, (passed, latency) in results.items() if passed]
    failed_servers = [s for s, (passed, _) in results.items() if not passed]

    # 按延迟排序通过的服务器
    passed_servers.sort(key=lambda x: x[1])

    # 显示统计
    print(f"\n" + "=" * 60)
    print(f"📊 测试结果统计")
    print("=" * 60)
    print(f"  - 总测试数: {len(results)}")
    print(f"  - ✅ 通过: {len(passed_servers)} ({len(passed_servers)/len(results)*100:.1f}%)")
    print(f"  - ❌ 失败: {len(failed_servers)} ({len(failed_servers)/len(results)*100:.1f}%)")
    print(f"  - 总耗时: {elapsed:.1f}秒 ({elapsed/60:.1f}分钟)")

    # 显示通过的服务器
    if passed_servers:
        print(f"\n✅ 通过的服务器（按延迟排序）:")
        for i, (server, latency) in enumerate(passed_servers, 1):
            name, ip, port = server
            print(f"  {i:2d}. {name:30s} {ip:15s}:{port} - {latency:.0f}ms")
    else:
        print(f"\n❌ 没有服务器通过测试")

    # 显示失败的服务器
    if failed_servers:
        print(f"\n❌ 失败的服务器:")
        for i, server in enumerate(failed_servers, 1):
            name, ip, port = server
            print(f"  {i:2d}. {name:30s} {ip:15s}:{port}")

    print(f"\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断测试")
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
