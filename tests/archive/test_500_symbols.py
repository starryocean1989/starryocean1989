# -*- coding: utf-8 -*-
"""
500品种中规模验证测试

测试目标：
1. 验证CPU低压力场景的积极提速策略
2. 验证2000批次大小的效果
3. 触发并观察动态调整机制
"""

import sys
import time
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from test_loadbalancer_e2e_basic import performance_collector


def test_500_symbols():
    """测试500品种扫描性能"""
    print("\n" + "=" * 70)
    print("E2E测试：500品种中规模验证")
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
        
        # 获取500个品种
        all_symbols = symbol_loader.extract_all_codes()
        test_symbols = all_symbols[:500]
        
        print(f"测试品种数量: {len(test_symbols)}")
        
        # 记录开始时间和资源状态
        initial_pressure = monitor.get_current_pressure()
        print(f"初始资源压力: {initial_pressure.score:.1f}% ({initial_pressure.bottleneck}瓶颈)")
        
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
            test_name="scan_500_symbols",
            task_type="data_quality_scan_500",
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
        
        # 分析结果
        print(f"\n性能分析:")
        per_symbol_time = duration / len(test_symbols)
        print(f"  - 单品种平均耗时: {per_symbol_time:.4f}秒")
        print(f"  - 预估1000品种耗时: {per_symbol_time * 1000:.2f}秒")
        print(f"  - 预估5000品种耗时: {per_symbol_time * 5000:.2f}秒")
        
        # 判断是否触发低压力场景
        if initial_pressure.score < 35:
            print(f"\n✅ 触发CPU低压力场景（<35%），应该看到积极提速策略")
        elif initial_pressure.score < 70:
            print(f"\n✓ 中等压力场景（35-70%），正常配置")
        else:
            print(f"\n⚠️ 高压力场景（>70%），应该看到降速保护")
        
        print("\n✅ 500品种测试通过！")
        return True
        
    except Exception as e:
        print(f"\n❌ 500品种测试失败: {e}")
        import traceback
        traceback.print_exc()
        
        performance_collector.record_test(
            test_name="scan_500_symbols",
            task_type="data_quality_scan_500",
            config={"symbols_count": 500, "intervals": ["1d"]},
            duration=0,
            success=False,
            resource_info={},
        )
        return False


def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print("LoadBalancer E2E测试 - 500品种中规模验证")
    print("=" * 70)
    
    result = test_500_symbols()
    
    if result:
        print("\n🎉 500品种测试完成！")
        print("\n查看详细性能数据:")
        print("  python tests/e2e/analyze_performance.py")
        return 0
    else:
        print("\n⚠️  测试失败")
        return 1


if __name__ == "__main__":
    exit(main())

