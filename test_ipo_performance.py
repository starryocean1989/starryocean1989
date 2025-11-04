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
            start_time = time.time()
            try:
                # 下载IPO日期（使用增量下载，已有缓存的不重复下载）
                # 注意：由于有缓存机制，边际耗时可能为负（说明新增品种已缓存）
                ipo_dates = download_ipo_dates(
                    symbols, 
                    use_multiprocess=False, 
                    max_workers=1
                )
                elapsed = time.time() - start_time
                times.append(elapsed)
                success = sum(1 for v in ipo_dates.values() if v is not None)
                success_counts.append(success)
                
                # 显示新增品种数量（帮助理解边际耗时）
                if len(results) > 0:
                    prev_count = results[-1]['count']
                    new_symbols = count - prev_count
                    print(f"✅ {elapsed:.2f}s (新增{new_symbols}个)", end=" " if r < repeat-1 else "")
                else:
                    print(f"✅ {elapsed:.2f}s", end=" " if r < repeat-1 else "")
            except Exception as e:
                print(f"❌ 失败: {e}")
                import traceback
                traceback.print_exc()
        
        if times:
            avg_time = sum(times) / len(times)
            avg_success = sum(success_counts) / len(success_counts)
            results.append({
                "count": count,
                "total_time": avg_time,
                "success": int(avg_success)
            })
            
            # 计算边际耗时
            marginal_time = None
            if len(results) > 1:
                prev_time = results[-2]['total_time']
                marginal_time = (avg_time - prev_time) * 1000  # 转换为毫秒
                print(f" → 边际耗时: {marginal_time:.2f}ms")
            else:
                print(f" → 总耗时: {avg_time:.2f}s")
    
    # 打印结果汇总和边际耗时分析
    print("\n" + "=" * 80)
    print("边际耗时结果汇总")
    print("=" * 80)
    print(f"{'品种数':<10} {'累计耗时(s)':<15} {'边际耗时(ms)':<18} {'成功数':<10}")
    print("-" * 80)
    
    marginal_times = []
    for i, r in enumerate(results):
        if i == 0:
            marginal_ms = "N/A"
        else:
            prev_time = results[i-1]['total_time']
            marginal_ms = (r['total_time'] - prev_time) * 1000
            marginal_times.append(marginal_ms)
            marginal_ms = f"{marginal_ms:.2f}"
        
        print(
            f"{r['count']:<10} "
            f"{r['total_time']:<15.2f} "
            f"{marginal_ms:<18} "
            f"{r['success']:<10}"
        )
    
    # 边际耗时统计
    if marginal_times:
        print("=" * 80)
        print("📊 边际耗时统计:")
        print("-" * 80)
        avg_marginal = sum(marginal_times) / len(marginal_times)
        min_marginal = min(marginal_times)
        max_marginal = max(marginal_times)
        
        # 只统计正的边际耗时（排除缓存命中等情况）
        positive_marginal = [t for t in marginal_times if t > 0]
        
        print(f"  平均边际耗时: {avg_marginal:.2f}ms")
        print(f"  范围: {min_marginal:.2f}ms - {max_marginal:.2f}ms")
        
        if positive_marginal:
            avg_positive = sum(positive_marginal) / len(positive_marginal)
            print(f"  ✅ 仅正边际耗时平均: {avg_positive:.2f}ms ({len(positive_marginal)}/{len(marginal_times)}个)")
        
        # 趋势分析：最近N个点的边际耗时
        if len(marginal_times) >= 5:
            recent_marginal = marginal_times[-5:]
            recent_avg = sum(recent_marginal) / len(recent_marginal)
            print(f"  📈 最近5个品种边际耗时平均: {recent_avg:.2f}ms")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="IPO日期下载边际耗时测试")
    parser.add_argument("--start", type=int, default=1, help="起始品种数量（默认: 1）")
    parser.add_argument("--end", type=int, default=20, help="结束品种数量（默认: 20）")
    parser.add_argument("--repeat", type=int, default=1, help="每个数量重复测试次数（默认: 1）")
    parser.add_argument("--no-clear-cache", action="store_true", help="不清除缓存（测试增量性能）")
    
    args = parser.parse_args()
    
    test_marginal_time(
        start=args.start,
        end_count=args.end,
        repeat=args.repeat,
        clear_cache=not args.no_clear_cache
    )
