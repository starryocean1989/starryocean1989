# -*- coding: utf-8 -*-
"""
测试data_fetcher.py的多进程下载功能
"""
import sys
from pathlib import Path
from datetime import date, timedelta
import time

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.data_module_vnpy.data_fetcher import MultiProcessStockFetcher


def test_multiprocess_download():
    """测试多进程下载功能"""
    print("\n" + "="*60)
    print("测试多进程下载功能")
    print("="*60)

    # 创建多进程下载器
    fetcher = MultiProcessStockFetcher()

    # 测试品种列表（包含不同市场）
    test_symbols = [
        "600000",  # 上海
        "000001",  # 深圳
        "600519",  # 上海
        "000002",  # 深圳
        "920418",  # 北交所
    ]

    # 测试周期
    intervals = ["1d", "5m", "1m"]

    # 开始日期：最近5天
    start_date = (date.today() - timedelta(days=5)).strftime("%Y-%m-%d")

    print(f"\n测试参数:")
    print(f"  品种数量: {len(test_symbols)}")
    print(f"  品种列表: {test_symbols}")
    print(f"  时间周期: {intervals}")
    print(f"  开始日期: {start_date}")
    print(f"  预期任务数: {len(test_symbols) * len(intervals)} = {len(test_symbols)} × {len(intervals)}")

    # 开始计时
    start_time = time.time()

    print(f"\n" + "="*60)
    print("开始多进程下载...")
    print("="*60)

    try:
        # 调用多进程下载
        results = fetcher.download_incremental_kline(
            symbols=test_symbols,
            start_date=start_date,
            intervals=intervals,
            progress_callback=None  # 不使用进度回调，避免输出过多
        )

        elapsed = time.time() - start_time

        print(f"\n" + "="*60)
        print("下载完成")
        print("="*60)

        # 分析结果
        print(f"\n下载统计:")
        print(f"  总耗时: {elapsed:.2f} 秒")
        print(f"  返回结果数: {len(results)}")

        # 分类统计
        valid_count = 0
        empty_count = 0
        none_count = 0

        for key, data in results.items():
            if data is None:
                none_count += 1
            elif data.empty:
                empty_count += 1
            else:
                valid_count += 1

        print(f"\n结果分类:")
        print(f"  有效数据: {valid_count}")
        print(f"  空数据: {empty_count}")
        print(f"  None数据: {none_count}")

        # 显示有效数据的详情
        if valid_count > 0:
            print(f"\n有效数据详情:")
            count = 0
            for key, data in results.items():
                if data is not None and not data.empty:
                    count += 1
                    if count <= 5:  # 只显示前5个
                        symbol, interval = key.split("_", 1)
                        print(f"  {key}: {len(data)} 条数据")
                        if 'datetime' in data.columns and len(data) > 0:
                            print(f"    范围: {data['datetime'].iloc[0]} ~ {data['datetime'].iloc[-1]}")

        # 检查是否所有预期任务都有结果
        expected_tasks = len(test_symbols) * len(intervals)
        if len(results) == expected_tasks:
            print(f"\n✅ 任务完整性: 所有{expected_tasks}个任务都返回了结果")
        else:
            print(f"\n⚠️  任务完整性: 预期{expected_tasks}个，实际{len(results)}个")

            # 找出缺失的任务
            missing = []
            for symbol in test_symbols:
                for interval in intervals:
                    key = f"{symbol}_{interval}"
                    if key not in results:
                        missing.append(key)

            if missing:
                print(f"  缺失的任务: {missing}")

        # 检查数据质量
        print(f"\n数据质量检查:")
        quality_issues = []
        for key, data in results.items():
            if data is not None and not data.empty:
                # 检查必要列
                required_cols = ['datetime', 'open', 'close', 'high', 'low', 'volume']
                missing_cols = [col for col in required_cols if col not in data.columns]
                if missing_cols:
                    quality_issues.append(f"{key}: 缺少列 {missing_cols}")

                # 检查datetime类型
                if 'datetime' in data.columns:
                    import pandas as pd
                    if not pd.api.types.is_datetime64_any_dtype(data['datetime']):
                        quality_issues.append(f"{key}: datetime不是datetime类型")

        if quality_issues:
            print(f"  ⚠️  发现质量问题:")
            for issue in quality_issues:
                print(f"    - {issue}")
        else:
            print(f"  ✅ 所有有效数据的列和类型都正确")

        # 总体评价
        print(f"\n" + "="*60)
        print("总体评价:")
        print("="*60)

        success_rate = (valid_count / expected_tasks * 100) if expected_tasks > 0 else 0

        if valid_count == expected_tasks and len(quality_issues) == 0:
            print(f"  ✅ 完美! 多进程下载功能完全正常")
            print(f"     - 所有任务都成功返回有效数据")
            print(f"     - 数据质量检查全部通过")
            print(f"     - 平均速度: {expected_tasks/elapsed:.2f} 任务/秒")
        elif valid_count > 0:
            print(f"  ⚠️  部分成功")
            print(f"     - 成功率: {success_rate:.1f}%")
            print(f"     - 有效数据: {valid_count}/{expected_tasks}")
            if quality_issues:
                print(f"     - 存在{len(quality_issues)}个质量问题")
        else:
            print(f"  ❌ 失败: 没有获取到有效数据")

        return results

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n❌ 多进程下载异常 (耗时 {elapsed:.2f}秒):")
        print(f"  {str(e)}")
        import traceback
        traceback.print_exc()
        return None


def test_single_symbol_download():
    """测试单个品种下载（快速测试）"""
    print("\n" + "="*60)
    print("快速测试：单个品种下载")
    print("="*60)

    fetcher = MultiProcessStockFetcher()

    # 单个品种
    test_symbol = ["600000"]
    intervals = ["1d"]
    start_date = (date.today() - timedelta(days=3)).strftime("%Y-%m-%d")

    print(f"\n测试: {test_symbol[0]} - 日线 - 最近3天")

    start_time = time.time()

    try:
        results = fetcher.download_incremental_kline(
            symbols=test_symbol,
            start_date=start_date,
            intervals=intervals,
            progress_callback=None
        )

        elapsed = time.time() - start_time

        if results and len(results) > 0:
            key = list(results.keys())[0]
            data = results[key]

            if data is not None and not data.empty:
                print(f"\n✅ 成功!")
                print(f"  耗时: {elapsed:.2f} 秒")
                print(f"  数据条数: {len(data)}")
                print(f"  列: {list(data.columns)}")
                if 'datetime' in data.columns:
                    print(f"  时间范围: {data['datetime'].iloc[0]} ~ {data['datetime'].iloc[-1]}")
                return True
            else:
                print(f"\n⚠️  返回空数据")
                return False
        else:
            print(f"\n❌ 未返回结果")
            return False

    except Exception as e:
        elapsed = time.time() - start_time
        print(f"\n❌ 失败 (耗时 {elapsed:.2f}秒): {str(e)}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "="*60)
    print("测试 data_fetcher.py 多进程下载功能")
    print("="*60)

    # 测试1: 快速测试单个品种
    print("\n【测试1】快速单品种测试")
    quick_result = test_single_symbol_download()

    if quick_result:
        # 测试2: 完整的多进程下载测试
        print("\n\n【测试2】完整多进程测试")
        full_result = test_multiprocess_download()
    else:
        print("\n⚠️  快速测试失败，跳过完整测试")

    print("\n" + "="*60)
    print("测试完成")
    print("="*60)

