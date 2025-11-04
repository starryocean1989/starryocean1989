#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""IPO日期下载性能测试脚本"""

import time
import sys
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.data_module_vnpy.data_acquisition import download_ipo_dates


def get_test_symbols(count):
    """获取测试品种列表（使用真实品种代码）"""
    try:
        from backend.infrastructure.data_module_vnpy.data_acquisition import SymbolLoader
        from backend.core.base import get_event_engine
        
        event_engine = get_event_engine()
        if event_engine:
            symbol_loader = SymbolLoader(event_engine)
            classified_symbols = symbol_loader.reload_and_classify(force_reload=False)
            
            all_symbols = []
            for category, symbols in classified_symbols.items():
                for symbol in symbols:
                    code = symbol.get("code") or symbol.get("symbol")
                    if code:
                        all_symbols.append(str(code).zfill(6))
            
            unique_symbols = list(set(all_symbols))
            if len(unique_symbols) >= count:
                return unique_symbols[:count]
    except Exception as e:
        print(f"⚠️ 获取真实品种失败: {e}，使用常用品种代码")
    
    # 回退到常用真实品种代码（上证和深证的主要股票）
    # 这些是真实存在的股票代码
    common_symbols = [
        "000001", "000002", "000858", "000876", "002001", "002007", 
        "002142", "002415", "002594", "002673", "300015", "300059",
        "600000", "600036", "600519", "600887", "600893", "601318",
        "601398", "601601", "601668", "601766", "601857", "601888"
    ]
    
    if len(common_symbols) >= count:
        return common_symbols[:count]
    else:
        # 如果还不够，循环使用
        return (common_symbols * ((count // len(common_symbols)) + 1))[:count]


def test_marginal_time(start=1, end_count=20, repeat=1, clear_cache=True):
    """测试边际耗时（每增加一个品种的额外耗时）
    
    Args:
        start: 起始品种数量
        end_count: 结束品种数量
        repeat: 每个数量重复测试次数（取平均值）
        clear_cache: 是否在测试开始前清除缓存
    """
    results = []
    print(f"📊 边际耗时测试：从 {start} 到 {end_count} 个品种，每次增加1个")
    if clear_cache:
        print("⚠️ 测试开始前将清除缓存，确保测试真实下载性能")
    print("=" * 80)
    
    # 清除缓存（如果启用）
    if clear_cache:
        try:
            cache_file = Path("data/cache/ipo_dates.json")
            if cache_file.exists():
                cache_file.unlink()
                print("✅ 缓存已清除\n")
        except Exception as e:
            print(f"⚠️ 清除缓存失败: {e}\n")
    
    # 获取足够多的品种
    all_test_symbols = get_test_symbols(end_count + 100)
    
    # 测试每个品种数量
    for count in range(start, end_count + 1):
        symbols = all_test_symbols[:count]
        print(f"📊 测试 {count} 个品种...", end=" ", flush=True)
        
        times = []
        success_counts = []
        
        for r in range(repeat):
            # 清除缓存（如果启用）
            if clear_cache and r == 0:  # 只在第一次测试前清除
                try:
                    cache_file = Path("data/cache/ipo_dates.json")
                    if cache_file.exists():
                        cache_file.unlink()
                        print(f"[已清除缓存] ", end="", flush=True)
                except Exception as e:
                    pass
            
            start_time = time.time()
            try:
                # 下载IPO日期
                ipo_dates = download_ipo_dates(
                    symbols, 
                    use_multiprocess=False, 
                    max_workers=1
                )
                elapsed = time.time() - start_time
                times.append(elapsed)
                success = sum(1 for v in ipo_dates.values() if v is not None)
                success_counts.append(success)
                print(f"✅ {elapsed:.2f}s (成功={success})", end=" " if r < repeat-1 else "\n")
            except Exception as e:
                print(f"❌ 失败: {e}")
                import traceback
                traceback.print_exc()
        
        if times:
            avg_time = sum(times) / len(times)
            avg_success = sum(success_counts) / len(success_counts)
            per_symbol = avg_time / count * 1000 if count > 0 else 0
            results.append({
                "count": count,
                "total_time": avg_time,
                "per_symbol_ms": per_symbol,
                "success": int(avg_success)
            })
            print(f"  📈 平均耗时: {avg_time:.2f}s, 每品种: {per_symbol:.2f}ms")
    
    # 打印结果汇总
    print("\n" + "=" * 60)
    print("结果汇总:")
    print(f"{'品种数':<10} {'总耗时(s)':<12} {'每品种(ms)':<12} {'成功数':<10}")
    print("-" * 60)
    for r in results:
        print(
            f"{r['count']:<10} "
            f"{r['total_time']:<12.2f} "
            f"{r['per_symbol_ms']:<12.2f} "
            f"{r['success']:<10}"
        )
    
    # 计算增量
    if len(results) > 1:
        print("\n" + "=" * 60)
        print("每增加一个品种的耗时分析:")
        print("-" * 60)
        
        increments = []
        positive_increments = []  # 只计算正的增量（排除并发效率提升）
        
        for i in range(1, len(results)):
            prev = results[i-1]
            curr = results[i]
            count_diff = curr['count'] - prev['count']
            time_diff = curr['total_time'] - prev['total_time']
            per_symbol = time_diff / count_diff * 1000 if count_diff > 0 else 0
            increments.append(per_symbol)
            
            if per_symbol > 0:
                positive_increments.append(per_symbol)
            
            status = "✅" if per_symbol > 0 else "⚠️ (并发效率提升)"
            print(
                f"{prev['count']} → {curr['count']} (+{count_diff}): "
                f"增加耗时 {time_diff:.2f}s, 每品种 {per_symbol:.2f}ms {status}"
            )
        
        if increments:
            avg_inc = sum(increments) / len(increments)
            min_inc = min(increments)
            max_inc = max(increments)
            print("-" * 60)
            print(f"📊 统计信息:")
            print(f"  所有增量平均: {avg_inc:.2f}ms")
            print(f"  范围: {min_inc:.2f}ms - {max_inc:.2f}ms")
            
            if positive_increments:
                avg_positive = sum(positive_increments) / len(positive_increments)
                print(f"  ⚠️ 仅正增量平均（排除并发效率）: {avg_positive:.2f}ms")
            
            # 计算总趋势：最后N个点的平均增量
            if len(results) >= 3:
                last_three = results[-3:]
                total_count_diff = last_three[-1]['count'] - last_three[0]['count']
                total_time_diff = last_three[-1]['total_time'] - last_three[0]['total_time']
                trend_per_symbol = total_time_diff / total_count_diff * 1000 if total_count_diff > 0 else 0
                print(f"  📈 趋势分析（最后3个点）: 每品种 {trend_per_symbol:.2f}ms")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="IPO日期下载性能测试")
    parser.add_argument("--start", type=int, default=1, help="起始品种数量")
    parser.add_argument("--end", type=int, default=20, help="结束品种数量")
    parser.add_argument("--step", type=int, default=5, help="步长")
    parser.add_argument("--repeat", type=int, default=1, help="重复次数")
    parser.add_argument("--no-clear-cache", action="store_true", help="不清除缓存（测试增量性能）")
    
    args = parser.parse_args()
    
    test_performance(
        start=args.start,
        end_count=args.end,
        step=args.step,
        repeat=args.repeat,
        clear_cache=not args.no_clear_cache
    )
