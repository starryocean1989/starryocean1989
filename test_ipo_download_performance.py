#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
IPO日期下载性能测试脚本

测试不同品种数量下的下载耗时，分析每增加一个品种的平均耗时。
"""

import time
import sys
import os
from pathlib import Path
from typing import List, Dict

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 导入必要的模块
try:
    from backend.infrastructure.data_module_vnpy.data_acquisition import download_ipo_dates
    from backend.infrastructure.data_module_vnpy.data_acquisition import download_ipo_dates, SymbolLoader
    from backend.core.base import get_event_engine, set_event_engine
    from vnpy.event import EventEngine
except ImportError as e:
    print(f"❌ 导入模块失败: {e}")
    print("请确保在项目根目录运行此脚本")
    sys.exit(1)

# 初始化EventEngine
event_engine = EventEngine()
set_event_engine(event_engine)


def get_test_symbols(total_count: int) -> List[str]:
    """获取测试用的品种列表
    
    Args:
        total_count: 需要的品种总数
        
    Returns:
        品种代码列表
    """
    # 尝试从SymbolLoader获取真实品种列表
    try:
        event_engine = get_event_engine()
        if event_engine is None:
            print("⚠️ EventEngine未初始化，使用模拟品种列表")
            # 使用模拟品种列表
            return [f"{i:06d}" for i in range(1, total_count + 1)]
        
        symbol_loader = SymbolLoader(event_engine)
        
        # 重新加载品种列表
        classified_symbols = symbol_loader.reload_and_classify(force_reload=False)
        
        # 提取所有品种代码
        all_symbols = []
        for category, symbols in classified_symbols.items():
            for symbol in symbols:
                code = symbol.get("code") or symbol.get("symbol")
                if code:
                    all_symbols.append(str(code).zfill(6))
        
        # 去重
        unique_symbols = list(set(all_symbols))
        
        if len(unique_symbols) >= total_count:
            return unique_symbols[:total_count]
        else:
            print(f"⚠️ 可用品种数({len(unique_symbols)})少于请求数({total_count})，使用全部可用品种")
            return unique_symbols
            
    except Exception as e:
        print(f"⚠️ 获取品种列表失败: {e}，使用模拟品种列表")
        # 使用模拟品种列表
        return [f"{i:06d}" for i in range(1, total_count + 1)]


def test_ipo_download_performance(
    start_count: int = 1,
    end_count: int = 100,
    step: int = 10,
    repeat: int = 1,
) -> List[Dict]:
    """测试IPO下载性能
    
    Args:
        start_count: 起始品种数量
        end_count: 结束品种数量
        step: 每次增加的品种数量
        repeat: 每个数量重复测试的次数（取平均值）
        
    Returns:
        测试结果列表，每个元素包含 {count, total_time, avg_time_per_symbol, success_count, failed_count}
    """
    results = []
    print(f"DEBUG: results list initialized: {results}")
    
    print("=" * 80)
    print("IPO日期下载性能测试")
    print("=" * 80)
    print(f"测试范围: {start_count} - {end_count} 个品种，步长: {step}")
    print(f"每个数量重复测试: {repeat} 次")
    print("=" * 80)
    print()
    
    # 获取足够多的品种用于测试
    max_symbols = get_test_symbols(end_count + 100)  # 多获取一些备用
    
    test_counts = list(range(start_count, end_count + 1, step))
    if test_counts[-1] != end_count:
        test_counts.append(end_count)
    
    for count in test_counts:
        print(f"\n📊 测试 {count} 个品种...")
        
        # 选择测试品种
        test_symbols = max_symbols[:count]
        
        # 重复测试
        total_times = []
        success_counts = []
        failed_counts = []
        
        for r in range(repeat):
            print(f"  第 {r+1}/{repeat} 次测试...", end=" ", flush=True)
            
            try:
                # 清除缓存（确保每次都是真实下载）
                from backend.infrastructure.data_module_vnpy.core_engine import DailyCacheManager
                cache_dir = Path("data/cache")
                cache_file = cache_dir / "ipo_dates.json"
                if cache_file.exists():
                    # 备份缓存（可选）
                    # cache_file.rename(cache_file.with_suffix('.json.backup'))
                    pass
                
                # 记录开始时间
                start_time = time.time()
                
                # 执行下载
                ipo_dates = download_ipo_dates(
                    symbols=test_symbols,
                    progress_callback=None,
                    use_multiprocess=False,  # 使用单进程模式，更准确
                    max_workers=1,
                )
                
                # 记录结束时间
                elapsed_time = time.time() - start_time
                
                # 统计结果
                success_count = sum(1 for v in ipo_dates.values() if v is not None)
                failed_count = count - success_count
                
                total_times.append(elapsed_time)
                success_counts.append(success_count)
                failed_counts.append(failed_count)
                
                print(f"✅ {elapsed_time:.2f}s (成功={success_count}, 失败={failed_count})")
                
            except Exception as e:
                print(f"❌ 失败: {e}")
                import traceback
                traceback.print_exc()
                continue
        
        # 计算平均值
        if total_times:
            avg_time = sum(total_times) / len(total_times)
            avg_success = sum(success_counts) / len(success_counts)
            avg_failed = sum(failed_counts) / len(failed_counts)
            avg_time_per_symbol = avg_time / count if count > 0 else 0
            
            result = {
                "count": count,
                "total_time": avg_time,
                "avg_time_per_symbol": avg_time_per_symbol,
                "success_count": int(avg_success),
                "failed_count": int(avg_failed),
                "min_time": min(total_times),
                "max_time": max(total_times),
            }
            print(f"DEBUG: Appending result: {result}")
            results.append(result)
            
            print(f"  📈 平均耗时: {avg_time:.2f}s，每品种平均: {avg_time_per_symbol*1000:.2f}ms")
        else:
            print(f"  ⚠️ 所有测试都失败了")
    
    return results


def print_results_table(results: List[Dict]):
    """打印结果表格"""
    if not results:
        print("\n❌ 没有测试结果")
        return
    
    print("\n" + "=" * 100)
    print("测试结果汇总")
    print("=" * 100)
    print(f"{'品种数':<10} {'总耗时(s)':<12} {'每品种耗时(ms)':<16} {'成功数':<10} {'失败数':<10} {'最小耗时(s)':<14} {'最大耗时(s)':<14}")
    print("-" * 100)
    
    for r in results:
        print(
            f"{r['count']:<10} "
            f"{r['total_time']:<12.2f} "
            f"{r['avg_time_per_symbol']*1000:<16.2f} "
            f"{r['success_count']:<10} "
            f"{r['failed_count']:<10} "
            f"{r['min_time']:<14.2f} "
            f"{r['max_time']:<14.2f}"
        )
    
    print("=" * 100)
    
    # 分析每增加一个品种的耗时
    if len(results) > 1:
        print("\n📊 每增加一个品种的平均耗时分析:")
        print("-" * 60)
        
        increments = []
        for i in range(1, len(results)):
            prev_count = results[i-1]['count']
            curr_count = results[i]['count']
            prev_time = results[i-1]['total_time']
            curr_time = results[i]['total_time']
            
            count_diff = curr_count - prev_count
            time_diff = curr_time - prev_time
            
            if count_diff > 0:
                time_per_symbol = time_diff / count_diff
                increments.append(time_per_symbol)
                print(
                    f"{prev_count} → {curr_count} (+{count_diff}): "
                    f"增加耗时 {time_diff:.2f}s, 每品种 {time_per_symbol*1000:.2f}ms"
                )
        
        if increments:
            avg_increment = sum(increments) / len(increments)
            print("-" * 60)
            print(f"平均每增加一个品种耗时: {avg_increment*1000:.2f}ms")
            print(f"范围: {min(increments)*1000:.2f}ms - {max(increments)*1000:.2f}ms")


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="IPO日期下载性能测试")
    parser.add_argument("--start", type=int, default=1, help="起始品种数量（默认: 1）")
    parser.add_argument("--end", type=int, default=100, help="结束品种数量（默认: 100）")
    parser.add_argument("--step", type=int, default=10, help="每次增加的品种数量（默认: 10）")
    parser.add_argument("--repeat", type=int, default=1, help="每个数量重复测试次数（默认: 1）")
    parser.add_argument("--output", type=str, help="结果保存路径（CSV格式）")
    
    args = parser.parse_args()
    
    # 执行测试
    results = test_ipo_download_performance(
        start_count=args.start,
        end_count=args.end,
        step=args.step,
        repeat=args.repeat,
    )
    
    # 打印结果
    print_results_table(results)
    
    # 保存结果（如果指定了输出文件）
    print(f"DEBUG: Results before CSV write: {results}")
    if not args.output:
        output_path = Path("ipo_performance_results.csv")
    else:
        output_path = Path(args.output)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    
    print(f"\n✅ 结果已保存到: {output_path}")


if __name__ == "__main__":
    main()
