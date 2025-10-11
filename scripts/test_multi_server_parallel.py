# -*- coding: utf-8 -*-
"""
测试多服务器并行下载的可行性
"""

import sys
import time
import threading
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from mootdx.quotes import Quotes


def download_from_server(server_id, server_config, symbols, results):
    """从指定服务器下载数据"""
    try:
        quotes = Quotes.factory(**server_config)

        print(f"[服务器{server_id}] 开始下载 {len(symbols)} 个品种...")
        start_time = time.time()

        success_count = 0
        for symbol in symbols:
            try:
                data = quotes.client.get_security_bars(9, 1, symbol, 0, 10)
                if data and len(data) > 0:
                    success_count += 1
            except Exception as e:
                print(f"[服务器{server_id}] {symbol} 失败: {str(e)[:30]}")

        elapsed = time.time() - start_time

        results[server_id] = {
            "success": success_count,
            "total": len(symbols),
            "elapsed": elapsed,
            "qps": success_count / elapsed if elapsed > 0 else 0,
        }

        print(
            f"[服务器{server_id}] 完成! 成功:{success_count}/{len(symbols)}, "
            f"耗时:{elapsed:.1f}秒, QPS:{success_count/elapsed:.1f}"
        )

    except Exception as e:
        print(f"[服务器{server_id}] 异常: {e}")
        results[server_id] = {"error": str(e)}


def test_parallel_download():
    """测试并行下载"""
    print("=" * 80)
    print("测试多服务器并行下载")
    print("=" * 80)

    # 准备测试品种（20个品种，分2组）
    test_symbols = [
        [
            "600000",
            "600004",
            "600009",
            "600010",
            "600015",
            "600016",
            "600019",
            "600022",
            "600023",
            "600025",
        ],  # 组1: 10个
        [
            "600028",
            "600029",
            "600030",
            "600031",
            "600032",
            "600036",
            "600038",
            "600048",
            "600050",
            "600052",
        ],  # 组2: 10个
    ]

    # 方案1: 单服务器串行（基准）
    print("\n【方案1】单服务器串行下载（基准）")
    print("-" * 80)

    all_symbols = test_symbols[0] + test_symbols[1]
    quotes = Quotes.factory()

    start_time = time.time()
    success = 0
    for symbol in all_symbols:
        try:
            data = quotes.client.get_security_bars(9, 1, symbol, 0, 10)
            if data and len(data) > 0:
                success += 1
        except:
            pass

    baseline_time = time.time() - start_time
    baseline_qps = success / baseline_time if baseline_time > 0 else 0

    print(f"[OK] 完成: {success}/{len(all_symbols)} 品种")
    print(f"[OK] 耗时: {baseline_time:.2f}秒")
    print(f"[OK] QPS: {baseline_qps:.1f}")

    # 方案2: 双服务器并行（使用默认服务器的两个实例）
    print("\n【方案2】双服务器并行下载（两个独立连接）")
    print("-" * 80)

    results = {}
    threads = []

    # 创建两个独立的下载线程
    for i in range(2):
        t = threading.Thread(
            target=download_from_server, args=(i + 1, {}, test_symbols[i], results)
        )
        threads.append(t)

    # 同时启动
    start_time = time.time()
    for t in threads:
        t.start()

    # 等待完成
    for t in threads:
        t.join()

    total_time = time.time() - start_time

    # 统计结果
    print("\n" + "=" * 80)
    print("性能对比")
    print("=" * 80)

    total_success = sum(r.get("success", 0) for r in results.values())
    total_requests = sum(r.get("total", 0) for r in results.values())
    parallel_qps = total_success / total_time if total_time > 0 else 0

    print(f"\n单服务器串行:")
    print(f"  ├─ 耗时: {baseline_time:.2f}秒")
    print(f"  ├─ 成功: {success}/{len(all_symbols)}")
    print(f"  └─ QPS: {baseline_qps:.1f}")

    print(f"\n双服务器并行:")
    print(f"  ├─ 耗时: {total_time:.2f}秒")
    print(f"  ├─ 成功: {total_success}/{total_requests}")
    print(f"  └─ QPS: {parallel_qps:.1f}")

    if total_time < baseline_time:
        speedup = baseline_time / total_time
        time_saved = baseline_time - total_time
        print(f"\n>> 并行提速:")
        print(f"  - 速度提升: {speedup:.2f}x")
        print(f"  - 节省时间: {time_saved:.2f}秒")
        print(f"  - 提速比例: {(speedup-1)*100:.1f}%")

        # 推算全量下载
        full_download_symbols = 19017  # 6339品种 × 3周期
        original_time = full_download_symbols * (baseline_time / len(all_symbols)) / 60
        optimized_time = full_download_symbols * (total_time / len(all_symbols)) / 60

        print(f"\n>> 全量下载预估 (19,017个请求):")
        print(f"  - 单服务器: {original_time:.1f}分钟")
        print(f"  - 双服务器: {optimized_time:.1f}分钟")
        print(f"  - 节省: {original_time - optimized_time:.1f}分钟")

        print(f"\n[SUCCESS] 方案可行！建议实施多服务器并行下载")
    else:
        print(f"\n[WARNING] 并行无明显提速，可能原因:")
        print(f"  - 测试品种太少，线程开销影响")
        print(f"  - 网络波动")
        print(f"  - 需要使用不同的物理服务器")


if __name__ == "__main__":
    test_parallel_download()
