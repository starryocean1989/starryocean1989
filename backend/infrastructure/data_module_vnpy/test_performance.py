"""性能基准测试"""
import sys
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.data_module_vnpy.load_balancer import (
    LoadBalancer,
    TaskCategory,
    TaskConfig,
    QueueMetrics,
    QueuePressureMonitor,
    ResourceMonitor,
)

print("=" * 80)
print("性能基准测试")
print("=" * 80)

# 测试1: LoadBalancer 配置生成性能
print("\n[基准1] LoadBalancer 配置生成性能...")
lb = LoadBalancer()
task = TaskConfig(
    name="perf_test",
    category=TaskCategory.LOCAL_READ,
    total_count=5000,
    is_io_intensive=True,
)

iterations = 1000
start_time = time.perf_counter()
for _ in range(iterations):
    config = lb.get_optimal_config(task=task)
end_time = time.perf_counter()

elapsed = end_time - start_time
avg_time = elapsed / iterations
throughput = iterations / elapsed

print(f"✅ 总耗时: {elapsed:.3f}秒")
print(f"✅ 平均耗时: {avg_time*1000:.3f}毫秒/次")
print(f"✅ 吞吐量: {throughput:.0f}次/秒")

# 测试2: 队列压力评估性能
print("\n[基准2] 队列压力评估性能...")
monitor = QueuePressureMonitor()
metrics = QueueMetrics(
    queue_name="test_queue",
    current_size=500,
    max_size=1000,
    fill_rate=0.5,
)

iterations = 10000
start_time = time.perf_counter()
for _ in range(iterations):
    monitor.record_metrics(metrics)
    pressure = monitor.get_pressure_level()
    factor = monitor.get_adjustment_factor()
end_time = time.perf_counter()

elapsed = end_time - start_time
avg_time = elapsed / iterations
throughput = iterations / elapsed

print(f"✅ 总耗时: {elapsed:.3f}秒")
print(f"✅ 平均耗时: {avg_time*1000:.3f}毫秒/次")
print(f"✅ 吞吐量: {throughput:.0f}次/秒")

# 测试3: 资源监控性能
print("\n[基准3] 资源监控性能...")
resource_monitor = ResourceMonitor()

iterations = 100
start_time = time.perf_counter()
for _ in range(iterations):
    metrics = resource_monitor.get_metrics()
end_time = time.perf_counter()

elapsed = end_time - start_time
avg_time = elapsed / iterations
throughput = iterations / elapsed

print(f"✅ 总耗时: {elapsed:.3f}秒")
print(f"✅ 平均耗时: {avg_time*1000:.3f}毫秒/次")
print(f"✅ 吞吐量: {throughput:.0f}次/秒")
print(f"✅ 当前CPU: {metrics.cpu_percent:.1f}%")
print(f"✅ 当前内存: {metrics.memory_percent:.1f}%")

print("\n" + "=" * 80)
print("性能基准测试完成")
print("=" * 80)

# 性能评估
print("\n性能评估:")
print("─" * 80)
print("| 测试项目             | 平均耗时      | 吞吐量        | 性能等级 |")
print("│" + "─" * 78 + "│")

# 配置生成性能评估
config_avg = avg_time * 1000  # 转换为毫秒
if config_avg < 0.1:
    config_level = "优秀"
elif config_avg < 1.0:
    config_level = "良好"
elif config_avg < 10.0:
    config_level = "一般"
else:
    config_level = "需优化"

print(f"│ LoadBalancer配置生成 | {config_avg:.3f}毫秒    | {iterations/elapsed:.0f}次/秒   | {config_level:^8} │")

print("└" + "─" * 78 + "┘")
print("\n✅ 所有性能基准测试完成！")
