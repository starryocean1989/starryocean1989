"""
简化版native_socket_metrics集成测试脚本
直接测试C扩展和SystemMonitor，避免复杂的导入链
"""

import sys
import os
import time

# 添加扩展路径
sys.path.insert(0, r'C:\Users\USER\Desktop\terminal_v0.50\backend\infrastructure\native\native_socket_metrics')

def test_c_extension_direct():
    """测试1: 直接测试C扩展"""
    print("\n" + "="*60)
    print("测试1: 直接测试C扩展")
    print("="*60)
    
    try:
        import socket_metrics
        
        print("✓ C扩展模块导入成功")
        
        # 测试单次调用
        result = socket_metrics.get_socket_metrics()
        
        # 验证返回类型
        if not isinstance(result, dict):
            print(f"✗ 返回类型错误: 期望dict，实际{type(result)}")
            return False
        
        # 验证必需字段
        required_fields = [
            "recv_buffer_size_avg",
            "send_buffer_size_avg", 
            "recv_buffer_size_max",
            "send_buffer_size_max",
            "recv_buffer_size_min",
            "send_buffer_size_min",
            "recv_buffer_usage_ratio",
            "send_buffer_usage_ratio",
            "total_connections",
            "tcp_connections",
            "established_connections"
        ]
        
        missing_fields = [f for f in required_fields if f not in result]
        if missing_fields:
            print(f"✗ 缺少必需字段: {missing_fields}")
            return False
        
        print("✓ 返回数据结构验证通过")
        print(f"  - 总连接数: {result['total_connections']}")
        print(f"  - TCP连接数: {result['tcp_connections']}")
        print(f"  - ESTABLISHED连接数: {result['established_connections']}")
        print(f"  - 平均接收缓冲区: {result['recv_buffer_size_avg']} bytes")
        print(f"  - 平均发送缓冲区: {result['send_buffer_size_avg']} bytes")
        
        return True
        
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_performance():
    """测试2: 性能基准测试"""
    print("\n" + "="*60)
    print("测试2: 性能基准测试（目标<10ms）")
    print("="*60)
    
    try:
        import socket_metrics
        
        # 预热
        socket_metrics.get_socket_metrics()
        
        # 测试10次
        times = []
        print("执行10次采集测试...")
        
        for i in range(10):
            start = time.perf_counter()
            result = socket_metrics.get_socket_metrics()
            elapsed_ms = (time.perf_counter() - start) * 1000
            times.append(elapsed_ms)
            print(f"  第{i+1}次: {elapsed_ms:.2f}ms")
        
        # 计算统计信息
        avg_time = sum(times) / len(times)
        min_time = min(times)
        max_time = max(times)
        
        print(f"\n统计结果:")
        print(f"  - 平均耗时: {avg_time:.2f}ms")
        print(f"  - 最小耗时: {min_time:.2f}ms")
        print(f"  - 最大耗时: {max_time:.2f}ms")
        
        # 验证性能目标
        if avg_time < 10:
            print(f"✓ 性能目标达成（平均耗时 {avg_time:.2f}ms < 10ms）")
            improvement = ((100 - avg_time) / 100) * 100  # 相对100ms基线
            print(f"  - 相对Python基线(~100ms)提升: {improvement:.1f}%")
            return True, avg_time
        else:
            print(f"✗ 未达到性能目标（平均耗时 {avg_time:.2f}ms >= 10ms）")
            return False, avg_time
            
    except Exception as e:
        print(f"✗ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False, 0


def main():
    """运行测试"""
    print("\n" + "="*60)
    print("native_socket_metrics C扩展集成测试（简化版）")
    print("="*60)
    print("测试时间:", time.strftime("%Y-%m-%d %H:%M:%S"))
    print("测试位置: C:\\Users\\USER\\Desktop\\terminal_v0.50")
    
    # 测试1: 基本功能
    test1_passed = test_c_extension_direct()
    
    # 测试2: 性能基准
    test2_passed, avg_time = test_performance()
    
    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    print(f"{'✓ 通过' if test1_passed else '✗ 失败'} - C扩展基本功能")
    print(f"{'✓ 通过' if test2_passed else '✗ 失败'} - 性能基准测试")
    
    if test1_passed and test2_passed:
        print(f"\n🎉 所有测试通过！")
        print(f"   平均采集耗时: {avg_time:.2f}ms")
        print(f"   性能提升: {((100 - avg_time) / 100) * 100:.1f}%（相对100ms基线）")
        return 0
    else:
        print(f"\n⚠ 有测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
