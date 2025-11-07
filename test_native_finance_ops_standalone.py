# -*- coding: utf-8 -*-
"""
独立测试native_finance_ops扩展功能（不依赖其他模块）
"""

import time
import sys
import os

# 直接导入编译好的扩展
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend/infrastructure/native/native_finance_ops'))

def test_native_extension():
    """测试原生扩展"""
    print("\n" + "="*60)
    print("测试native_finance_ops扩展")
    print("="*60)
    
    try:
        import native_finance_ops
        print(f"✅ 扩展版本: {native_finance_ops.VERSION}")
        print(f"✅ 扩展可用: {native_finance_ops.FINANCE_OPS_AVAILABLE}")
        
        # 测试1: aggregate_daily_pnl
        print("\n测试1: aggregate_daily_pnl")
        dates = [20240101, 20240102, 20240102, 20240103]
        pnl = [100.0, 50.0, -30.0, 200.0]
        
        result = native_finance_ops.aggregate_daily_pnl(dates, pnl)
        print(f"  输入: dates={dates}, pnl={pnl}")
        print(f"  输出日期: {result['dates']}")
        print(f"  输出收益: {result['daily_returns']}")
        print(f"  累计净值: {result['cumulative_equity']}")
        
        # 测试2: compute_return_metrics  
        print("\n测试2: compute_return_metrics")
        pnl_series = [100, -50, 200, -30, 150]
        equity_series = [1000000, 1000100, 1000050, 1000250, 1000220, 1000370]
        
        metrics = native_finance_ops.compute_return_metrics(
            pnl_series, equity_series, trading_days_per_year=252
        )
        print(f"  总收益率: {metrics['total_return']*100:.2f}%")
        print(f"  年化收益率: {metrics['annualized_return']*100:.2f}%")
        print(f"  夏普比率: {metrics['sharpe_ratio']:.2f}")
        print(f"  最大回撤: {metrics['max_drawdown']*100:.2f}%")
        
        # 测试3: bucketize_period
        print("\n测试3: bucketize_period")
        equity = [1000000, 1010000, 1020000]
        dates_period = [20240101, 20240201, 20240301]
        
        buckets = native_finance_ops.bucketize_period(equity, dates_period, "monthly")
        print(f"  周期数: {len(buckets['period_labels'])}")
        print(f"  标签: {buckets['period_labels']}")
        print(f"  收益: {buckets['period_returns']}")
        
        # 性能测试
        print("\n" + "="*60)
        print("性能测试 (10万条数据)")
        print("="*60)
        
        import random
        random.seed(42)
        size = 100000
        test_dates = [20240101 + i//400 for i in range(size)]
        test_pnl = [random.uniform(-1000, 2000) for _ in range(size)]
        
        start = time.perf_counter()
        result = native_finance_ops.aggregate_daily_pnl(test_dates, test_pnl)
        elapsed = (time.perf_counter() - start) * 1000
        
        print(f"✅ 原生扩展处理{size:,}条记录")
        print(f"   耗时: {elapsed:.2f}ms")
        print(f"   聚合后: {len(result['dates'])} 个交易日")
        print(f"   吞吐量: {size/elapsed*1000:.0f} 条/秒")
        
        print("\n🎉 所有测试通过！")
        return True
        
    except ImportError as e:
        print(f"❌ 无法导入扩展: {e}")
        print("\n提示: 请先编译扩展:")
        print("  cd backend/infrastructure/native/native_finance_ops")
        print("  python setup.py build_ext --inplace")
        return False
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_native_extension()
    sys.exit(0 if success else 1)
