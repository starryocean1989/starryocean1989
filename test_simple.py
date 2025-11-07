import sys
import os

# 只添加必要的路径
sys.path.insert(0, r"C:\Users\USER\Desktop\terminal_v0.50")

# 直接导入需要的模块
import time

print("=" * 70)
print("简化集成测试: 直接测试SystemMonitor.get_socket_buffer_info()")
print("=" * 70)

# 方法1: 直接使用C扩展
print("\n方法1: 直接使用C扩展")
try:
    sys.path.insert(0, r"C:\Users\USER\Desktop\terminal_v0.50\backend\infrastructure\native\native_socket_metrics")
    import socket_metrics
    
    print(" socket_metrics导入成功")
    times = []
    for i in range(10):
        start = time.perf_counter()
        result = socket_metrics.get_socket_metrics()
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    
    avg_time = sum(times[1:]) / len(times[1:])
    print(f" 平均耗时: {avg_time:.2f}ms")
    print(f" TCP连接数: {result['tcp_connections']}")
    print(f" ESTABLISHED: {result['established_connections']}")
    
except Exception as e:
    print(f" 失败: {e}")

print("\n" + "=" * 70)
print("测试完成")
print("=" * 70)
