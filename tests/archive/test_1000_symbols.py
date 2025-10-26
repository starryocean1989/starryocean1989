# -*- coding: utf-8 -*-
"""
1000品种大规模验证测试

测试目标：
1. 验证大规模场景性能（预估24.5秒）
2. 识别新的性能瓶颈
3. 观察动态调整机制
4. 确定最终参数配置
"""

import sys
import time
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from test_loadbalancer_e2e_basic import performance_collector


def test_1000_symbols():
    """测试1000品种扫描性能"""
    print("\n" + "=" * 70)
    print("E2E测试：1000品种大规模验证")
    print("=" * 70)
    
    try:
        from backend.infrastructure.data_module_vnpy.local_data.data_quality import (
            DataSensor,
        )
        from backend.infrastructure.data_module_vnpy.data_acquisition.symbol_management import (
            SymbolLoader,
        )
        from backend.infrastructure.data_module_vnpy.load_balancer import ResourceMonitor
        
        # 初始化
        sensor = DataSensor(event_engine=None)
        symbol_loader = SymbolLoader()
        monitor = ResourceMonitor(event_engine=None)
        
        # 获取1000个品种
        all_symbols = symbol_loader.extract_all_codes()
        test_symbols = all_symbols[:1000]
        
        print(f"测试品种数量: {len(test_symbols)}")
        print("预估耗时: 24-30秒")
        print("请耐心等待...")
        
        # 记录开始时间和资源状态
        initial_pressure = monitor.get_current_pressure()
        print(f"\n初始资源压力: {initial_pressure.score:.1f}% ({initial_pressure.bottleneck}瓶颈)")
        
        # 执行扫描
        start_time = time.time()
        
        overview = sensor.scan_all_data_adaptive(
            reference_symbols=test_symbols,
            intervals=["1d"],
            force_refresh=True,
            progress_callback=None,
        )
        
        duration = time.time() - start_time
        
        # 最终资源状态
        final_pressure = monitor.get_current_pressure()
        
        # 记录结果
        performance_collector.record_test(
            test_name="scan_1000_symbols",
            task_type="data_quality_scan_1000",
            config={
                "symbols_count": len(test_symbols),
                "intervals": ["1d"],
                "adaptive": True,
            },
            duration=duration,
            success=overview.quality_score >= 0,
            resource_info={
                "initial_pressure": initial_pressure.score,
                "initial_bottleneck": initial_pressure.bottleneck,
                "final_pressure": final_pressure.score,
                "final_bottleneck": final_pressure.bottleneck,
            },
        )
        
        # 输出结果
        print(f"\n扫描结果:")
        print(f"  - 耗时: {duration:.2f}秒")
        print(f"  - 总品种: {overview.total_symbols}")
        print(f"  - 缺失品种: {overview.missing_symbols}")
        print(f"  - 错误品种: {overview.error_symbols}")
        print(f"  - 警告品种: {overview.warning_symbols}")
        print(f"  - 资源压力变化: {initial_pressure.score:.1f}% → {final_pressure.score:.1f}%")
        print(f"  - 瓶颈类型变化: {initial_pressure.bottleneck} → {final_pressure.bottleneck}")
        
        # 性能分析
        print(f"\n性能分析:")
        per_symbol_time = duration / len(test_symbols)
        print(f"  - 单品种平均耗时: {per_symbol_time:.4f}秒")
        
        # vs 500品种对比
        expected_per_symbol = 0.0245  # 500品种的单品种耗时
        improvement = (expected_per_symbol - per_symbol_time) / expected_per_symbol * 100
        if per_symbol_time < expected_per_symbol:
            print(f"  ✅ 性能提升: {improvement:.1f}%（vs 500品种）")
        elif per_symbol_time > expected_per_symbol * 1.1:
            print(f"  ⚠️  性能下降: {-improvement:.1f}%（vs 500品种）")
        else:
            print(f"  ✓ 性能持平（vs 500品种）")
        
        # 预估全量
        print(f"\n扩展性预估:")
        print(f"  - 5000品种预估耗时: {per_symbol_time * 5000:.2f}秒 (约{per_symbol_time * 5000 / 60:.1f}分钟)")
        
        # 阶段耗时分析（如果可用）
        print(f"\n压力分析:")
        if initial_pressure.score < 35:
            print(f"  ✅ 初始压力低（{initial_pressure.score:.1f}%），触发积极提速策略")
        elif initial_pressure.score < 70:
            print(f"  ✓ 初始压力中等（{initial_pressure.score:.1f}%），使用标准配置")
        else:
            print(f"  ⚠️  初始压力高（{initial_pressure.score:.1f}%），触发保护性降速")
        
        pressure_change = final_pressure.score - initial_pressure.score
        if abs(pressure_change) > 10:
            print(f"  ⚠️  压力变化较大（{pressure_change:+.1f}%），说明系统负载波动")
        else:
            print(f"  ✅ 压力稳定（{pressure_change:+.1f}%）")
        
        print("\n✅ 1000品种测试通过！")
        return True
        
    except Exception as e:
        print(f"\n❌ 1000品种测试失败: {e}")
        import traceback
        traceback.print_exc()
        
        performance_collector.record_test(
            test_name="scan_1000_symbols",
            task_type="data_quality_scan_1000",
            config={"symbols_count": 1000, "intervals": ["1d"]},
            duration=0,
            success=False,
            resource_info={},
        )
        return False


def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print("LoadBalancer E2E测试 - 1000品种大规模验证")
    print("=" * 70)
    
    result = test_1000_symbols()
    
    if result:
        print("\n🎉 1000品种测试完成！")
        print("\n查看详细性能数据:")
        print("  python tests/e2e/analyze_performance.py")
        return 0
    else:
        print("\n⚠️  测试失败")
        return 1


if __name__ == "__main__":
    exit(main())

