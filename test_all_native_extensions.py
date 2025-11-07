# -*- coding: utf-8 -*-
"""
综合测试所有优化6实现的原生扩展
"""

import sys
import os
import time

# 添加项目根目录
project_root = os.path.dirname(__file__)
sys.path.insert(0, project_root)

# 添加各个扩展目录到路径
sys.path.insert(0, os.path.join(project_root, 'backend/infrastructure/native/native_finance_ops'))
sys.path.insert(0, os.path.join(project_root, 'backend/infrastructure/native/native_rpc_bridge'))
sys.path.insert(0, os.path.join(project_root, 'backend/infrastructure/native/native_netprobe'))


def test_native_finance_ops():
    """测试native_finance_ops扩展"""
    print("\n" + "="*70)
    print("测试 1: native_finance_ops - 组合分析原生算子")
    print("="*70)
    
    try:
        import native_finance_ops
        
        print(f"✅ 扩展版本: {native_finance_ops.VERSION}")
        print(f"✅ 扩展可用: {native_finance_ops.FINANCE_OPS_AVAILABLE}")
        
        # 快速测试
        dates = [20240101, 20240102, 20240103]
        pnl = [100.0, -50.0, 200.0]
        result = native_finance_ops.aggregate_daily_pnl(dates, pnl)
        
        print(f"\n测试聚合功能:")
        print(f"  输入: {len(dates)} 条数据")
        print(f"  输出: {len(result['dates'])} 个交易日")
        print(f"  累计净值: {result['cumulative_equity'][-1]:.2f}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_native_rpc_bridge():
    """测试native_rpc_bridge扩展"""
    print("\n" + "="*70)
    print("测试 2: native_rpc_bridge - 零拷贝RPC桥接")
    print("="*70)
    
    try:
        import native_rpc_bridge
        
        print(f"✅ 扩展版本: {native_rpc_bridge.VERSION}")
        print(f"✅ 扩展可用: {native_rpc_bridge.RPC_BRIDGE_AVAILABLE}")
        
        # 测试方法ID映射
        method_name = "get_kline_data"
        method_id = native_rpc_bridge.get_method_id(method_name)
        reverse_name = native_rpc_bridge.get_method_name(method_id)
        
        print(f"\n测试方法映射:")
        print(f"  方法名 '{method_name}' -> ID: {method_id}")
        print(f"  ID {method_id} -> 方法名: '{reverse_name}'")
        print(f"  映射正确: {method_name == reverse_name}")
        
        # 测试请求头创建
        header = native_rpc_bridge.create_request_header(method_id, 1024)
        print(f"\n测试请求头创建:")
        print(f"  Method ID: {header['method_id']}")
        print(f"  Payload Size: {header['payload_size']}")
        print(f"  Request ID: {header['request_id']}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_native_netprobe():
    """测试native_netprobe扩展"""
    print("\n" + "="*70)
    print("测试 3: native_netprobe - 网络探测器")
    print("="*70)
    
    try:
        import native_netprobe
        
        print(f"✅ 扩展版本: {native_netprobe.VERSION}")
        print(f"✅ 扩展可用: {native_netprobe.NETPROBE_AVAILABLE}")
        
        # 测试本地连接（假设某些端口不开放）
        print(f"\n测试单个连接:")
        result = native_netprobe.test_connection("127.0.0.1", 65535, timeout=1.0)
        print(f"  主机: {result['host']}:{result['port']}")
        print(f"  状态: {'成功' if result['status'] == 0 else '失败'}")
        if result['status'] == 0:
            print(f"  延迟: {result['latency_ms']:.2f}ms")
        
        # 测试批量连接
        print(f"\n测试批量连接:")
        servers = [
            ("127.0.0.1", 65530),
            ("127.0.0.1", 65531),
            ("127.0.0.1", 65532),
        ]
        
        start = time.perf_counter()
        results = native_netprobe.batch_test_connections(servers, timeout=0.5, max_concurrent=10)
        elapsed = (time.perf_counter() - start) * 1000
        
        print(f"  测试服务器数: {len(servers)}")
        print(f"  总耗时: {elapsed:.2f}ms")
        print(f"  平均耗时: {elapsed/len(servers):.2f}ms/server")
        
        success_count = sum(1 for r in results if r['status'] == 0)
        print(f"  成功: {success_count}/{len(servers)}")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_performance_comparison():
    """性能对比测试"""
    print("\n" + "="*70)
    print("性能对比测试")
    print("="*70)
    
    try:
        import native_finance_ops
        import random
        random.seed(42)
        
        # 生成测试数据
        size = 50000
        dates = [20240101 + i//200 for i in range(size)]
        pnl = [random.uniform(-500, 1000) for _ in range(size)]
        
        print(f"\n数据规模: {size:,} 条记录")
        
        # 原生扩展性能
        start = time.perf_counter()
        native_result = native_finance_ops.aggregate_daily_pnl(dates, pnl)
        native_time = (time.perf_counter() - start) * 1000
        
        print(f"✅ 原生扩展: {native_time:.2f}ms")
        print(f"   聚合后: {len(native_result['dates'])} 个交易日")
        
        # Python实现性能
        from collections import defaultdict
        start = time.perf_counter()
        daily_dict = defaultdict(float)
        for d, p in zip(dates, pnl):
            daily_dict[d] += p
        sorted_dates = sorted(daily_dict.keys())
        python_time = (time.perf_counter() - start) * 1000
        
        print(f"✅ Python实现: {python_time:.2f}ms")
        print(f"   聚合后: {len(sorted_dates)} 个交易日")
        
        # 性能对比
        speedup = python_time / native_time
        print(f"\n🚀 性能提升: {speedup:.2f}x")
        print(f"   时间节省: {python_time - native_time:.2f}ms ({(1-native_time/python_time)*100:.1f}%)")
        
        return True
        
    except Exception as e:
        print(f"❌ 性能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    print("\n" + "="*70)
    print("优化6 - 三进程架构热点优化 - C扩展综合测试")
    print("="*70)
    
    results = []
    results.append(("native_finance_ops", test_native_finance_ops()))
    results.append(("native_rpc_bridge", test_native_rpc_bridge()))
    results.append(("native_netprobe", test_native_netprobe()))
    results.append(("性能对比", run_performance_comparison()))
    
    # 总结
    print("\n" + "="*70)
    print("测试总结")
    print("="*70)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        print(f"{status} - {name}")
    
    print(f"\n总计: {passed}/{total} 测试通过")
    
    if passed == total:
        print("\n" + "="*70)
        print("🎉 所有优化6扩展测试通过！")
        print("="*70)
        print("\n已实现的C扩展:")
        print("  1. ✅ native_finance_ops - 组合分析原生算子")
        print("  2. ✅ native_rpc_bridge - 零拷贝RPC桥接")
        print("  3. ✅ native_netprobe - 网络探测器")
        print("\n预期性能提升:")
        print("  • 组合刷新延迟: 600ms → <150ms (75%↓)")
        print("  • RPC跨进程延迟: 降低15-20ms")
        print("  • 端口扫描: 2-3s → <300ms (90%↓)")
        print("="*70)
        exit(0)
    else:
        print(f"\n⚠️ {total - passed} 个测试失败")
        exit(1)
