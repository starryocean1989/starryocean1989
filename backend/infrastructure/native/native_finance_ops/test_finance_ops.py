# -*- coding: utf-8 -*-
"""
测试native_finance_ops扩展功能
"""

import sys
import os

# 添加项目根目录到Python路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../..'))
sys.path.insert(0, project_root)

import time
from typing import List, Tuple


def test_aggregate_daily_pnl():
    """测试日频盈亏聚合"""
    print("\n" + "="*60)
    print("测试1: 日频盈亏聚合 (aggregate_daily_pnl)")
    print("="*60)

    # 准备测试数据
    dates = [20240101, 20240102, 20240102, 20240103, 20240103, 20240103]
    pnl = [100.0, 50.0, -30.0, 200.0, -100.0, 50.0]

    try:
        from backend.infrastructure.native.native_finance_ops import aggregate_daily_pnl

        start = time.perf_counter()
        result = aggregate_daily_pnl(dates, pnl)
        elapsed = (time.perf_counter() - start) * 1000

        print(f"✅ 原生扩展执行成功，耗时: {elapsed:.3f}ms")
        print(f"   聚合后天数: {len(result['dates'])}")
        print(f"   日期: {result['dates']}")
        print(f"   每日收益: {result['daily_returns']}")
        print(f"   累计净值: {result['cumulative_equity']}")

        # 验证结果
        assert len(result['dates']) == 3, "应该有3个不同日期"
        assert abs(result['daily_returns'][0] - 100.0) < 0.01, "第一天收益应为100"
        assert abs(result['daily_returns'][1] - 20.0) < 0.01, "第二天收益应为20 (50-30)"
        assert abs(result['daily_returns'][2] - 150.0) < 0.01, "第三天收益应为150 (200-100+50)"

        print("✅ 结果验证通过")
        return True

    except ImportError as e:
        print(f"❌ 无法导入native_finance_ops: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_compute_return_metrics():
    """测试绩效指标计算"""
    print("\n" + "="*60)
    print("测试2: 绩效指标计算 (compute_return_metrics)")
    print("="*60)

    # 准备测试数据：模拟100天的交易
    import random
    random.seed(42)

    pnl_series = [random.uniform(-500, 1000) for _ in range(100)]
    equity_series = [1000000]  # 初始资金100万

    for pnl in pnl_series:
        equity_series.append(equity_series[-1] + pnl)

    equity_series = equity_series[1:]  # 移除初始值

    try:
        from backend.infrastructure.native.native_finance_ops import compute_return_metrics

        start = time.perf_counter()
        result = compute_return_metrics(pnl_series, equity_series, trading_days_per_year=252)
        elapsed = (time.perf_counter() - start) * 1000

        print(f"✅ 原生扩展执行成功，耗时: {elapsed:.3f}ms")
        print(f"   总收益率: {result['total_return']*100:.2f}%")
        print(f"   年化收益率: {result['annualized_return']*100:.2f}%")
        print(f"   波动率: {result['volatility']*100:.2f}%")
        print(f"   夏普比率: {result['sharpe_ratio']:.2f}")
        print(f"   最大回撤: {result['max_drawdown']*100:.2f}%")
        print(f"   回撤持续天数: {result['drawdown_days']}天")
        print(f"   卡玛比率: {result['calmar_ratio']:.2f}")

        # 基本验证
        assert 'total_return' in result
        assert 'volatility' in result
        assert 'sharpe_ratio' in result
        assert 'max_drawdown' in result

        print("✅ 结果验证通过")
        return True

    except ImportError as e:
        print(f"❌ 无法导入native_finance_ops: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_bucketize_period():
    """测试周期分组"""
    print("\n" + "="*60)
    print("测试3: 周期分组 (bucketize_period)")
    print("="*60)

    # 准备测试数据：3个月的数据
    dates = [
        20240101, 20240115, 20240130,
        20240201, 20240215, 20240228,
        20240301, 20240315, 20240330,
    ]
    equity = [1000000, 1010000, 1020000, 1015000, 1025000, 1030000, 1028000, 1035000, 1040000]

    try:
        from backend.infrastructure.native.native_finance_ops import bucketize_period

        start = time.perf_counter()
        result = bucketize_period(equity, dates, "monthly")
        elapsed = (time.perf_counter() - start) * 1000

        print(f"✅ 原生扩展执行成功，耗时: {elapsed:.3f}ms")
        print(f"   周期数量: {len(result['period_labels'])}")
        print(f"   周期标签: {result['period_labels']}")
        print(f"   周期收益: {[f'{r*100:.2f}%' for r in result['period_returns']]}")

        # 验证
        assert len(result['period_labels']) == 3, "应该有3个月"

        print("✅ 结果验证通过")
        return True

    except ImportError as e:
        print(f"❌ 无法导入native_finance_ops: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_compute_period_statistics():
    """测试周期统计接口"""
    print("\n" + "="*60)
    print("测试4: 周期统计 (compute_period_statistics)")
    print("="*60)

    dates = [
        "2024-01-01",
        "2024-01-02",
        "2024-01-03",
        "2024-01-08",
        "2024-01-09",
    ]
    pnl = [1000.0, -500.0, 300.0, 800.0, -200.0]

    try:
        from backend.infrastructure.native.native_finance_ops import compute_period_statistics

        start = time.perf_counter()
        result = compute_period_statistics(dates, pnl, initial_equity=1_000_000)
        elapsed = (time.perf_counter() - start) * 1000

        print(f"✅ 原生扩展执行成功，耗时: {elapsed:.3f}ms")
        print(f"   日度条目: {len(result['daily'])}")
        print(f"   周度条目: {len(result['weekly'])}")
        print(f"   月度条目: {len(result['monthly'])}")
        print(f"   总收益: {result['summary']['total_pnl']}")
        print(f"   夏普比率: {result['summary']['sharpe_ratio']:.4f}")

        assert result["success"] is True
        assert len(result["daily"]) == len(dates)
        assert "equity_curve" in result
        assert abs(result["summary"]["total_pnl"] - sum(pnl)) < 1e-6

        print("✅ 结果验证通过")
        return True

    except ImportError as e:
        print(f"❌ 无法导入native_finance_ops: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_compute_risk_profile():
    """测试风险画像接口"""
    print("\n" + "="*60)
    print("测试5: 风险画像 (compute_risk_profile)")
    print("="*60)

    returns = [0.01, -0.005, 0.007, -0.012, 0.004, 0.009, -0.003]

    try:
        from backend.infrastructure.native.native_finance_ops import compute_risk_profile

        start = time.perf_counter()
        result = compute_risk_profile(returns, scale=1_500_000, confidence_levels=[0.95])
        elapsed = (time.perf_counter() - start) * 1000

        print(f"✅ 原生扩展执行成功，耗时: {elapsed:.3f}ms")
        print(f"   夏普比率: {result['sharpe_ratio']:.4f}")
        print(f"   最大回撤: {result['max_drawdown']:.4f}")
        print(f"   VaR95: {result['var']['0.95']['var_value']:.4f}")
        print(f"   CVaR95: {result['var']['0.95']['cvar_value']:.4f}")

        assert "var" in result and "0.95" in result["var"]
        assert "max_drawdown" in result
        assert "equity_curve" in result
        assert len(result["equity_curve"]) == len(returns) + 1

        print("✅ 结果验证通过")
        return True

    except ImportError as e:
        print(f"❌ 无法导入native_finance_ops: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_performance_benchmark():
    """性能基准测试"""
    print("\n" + "="*60)
    print("性能基准测试")
    print("="*60)

    import random
    random.seed(42)

    # 生成大规模数据：10万条记录
    size = 100000
    dates = [20240101 + i//400 for i in range(size)]  # 模拟约250个交易日
    pnl = [random.uniform(-1000, 2000) for _ in range(size)]

    print(f"\n数据规模: {size:,} 条记录")

    try:
        from backend.infrastructure.native.native_finance_ops import (
            aggregate_daily_pnl,
            FINANCE_OPS_AVAILABLE
        )

        if not FINANCE_OPS_AVAILABLE:
            print("❌ native_finance_ops 不可用")
            return False

        # 预热
        _ = aggregate_daily_pnl(dates[:100], pnl[:100])

        # 测试原生扩展
        start = time.perf_counter()
        result = aggregate_daily_pnl(dates, pnl)
        native_time = (time.perf_counter() - start) * 1000

        print(f"✅ 原生扩展耗时: {native_time:.2f}ms")
        print(f"   聚合后天数: {len(result['dates'])}")

        # Python实现对比
        print("\n对比Python实现...")
        from collections import defaultdict

        start = time.perf_counter()
        daily_dict = defaultdict(float)
        for d, p in zip(dates, pnl):
            daily_dict[d] += p
        sorted_dates = sorted(daily_dict.keys())
        python_time = (time.perf_counter() - start) * 1000

        print(f"✅ Python实现耗时: {python_time:.2f}ms")
        print(f"   聚合后天数: {len(sorted_dates)}")

        # 性能对比
        speedup = python_time / native_time
        print(f"\n🚀 性能提升: {speedup:.2f}x")
        print(f"   CPU时间节省: {python_time - native_time:.2f}ms ({(1-native_time/python_time)*100:.1f}%)")

        return True

    except Exception as e:
        print(f"❌ 性能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "="*60)
    print("native_finance_ops 扩展测试套件")
    print("="*60)

    # 检查扩展是否可用
    try:
        from backend.infrastructure.native.native_finance_ops import FINANCE_OPS_AVAILABLE
        if FINANCE_OPS_AVAILABLE:
            print("✅ native_finance_ops 扩展已成功加载")
        else:
            print("❌ native_finance_ops 扩展不可用")
            exit(1)
    except ImportError as e:
        print(f"❌ 无法导入扩展: {e}")
        exit(1)

    # 运行测试
    results = []
    results.append(("日频盈亏聚合", test_aggregate_daily_pnl()))
    results.append(("绩效指标计算", test_compute_return_metrics()))
    results.append(("周期分组", test_bucketize_period()))
    results.append(("周期统计", test_compute_period_statistics()))
    results.append(("风险画像", test_compute_risk_profile()))
    results.append(("性能基准测试", run_performance_benchmark()))

    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} - {name}")

    print(f"\n总计: {passed}/{total} 测试通过")

    if passed == total:
        print("\n🎉 所有测试通过！")
        exit(0)
    else:
        print(f"\n⚠️ {total - passed} 个测试失败")
        exit(1)
