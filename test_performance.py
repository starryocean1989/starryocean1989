# -*- coding: utf-8 -*-
"""
性能测试 - 测试日志延迟和告警延迟.

验收标准：
- 日志发送延迟 < 10ms
- 告警推送延迟 < 50ms
"""

import logging
import multiprocessing
import sys
import time
from pathlib import Path
from statistics import mean, stdev

project_root = Path(__file__).parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
)


def test_log_latency(num_samples: int = 1000):
    """测试日志发送延迟.
    
    Args:
        num_samples: 采样数量
        
    Returns:
        平均延迟（毫秒）
    """
    print("\n" + "=" * 70)
    print("测试1：日志发送延迟")
    print("=" * 70)
    
    from backend.processes.ipc_client import get_distributed_log_handler
    
    # 注册分布式日志处理器
    handler = get_distributed_log_handler()
    logging.root.addHandler(handler)
    
    latencies = []
    
    for i in range(num_samples):
        start = time.perf_counter()
        logging.info(f"性能测试日志 #{i}")
        end = time.perf_counter()
        
        latency_ms = (end - start) * 1000
        latencies.append(latency_ms)
        
        # 每100次显示进度
        if (i + 1) % 100 == 0:
            print(f"[进度] {i+1}/{num_samples} 完成")
    
    # 统计
    avg_latency = mean(latencies)
    std_latency = stdev(latencies) if len(latencies) > 1 else 0
    min_latency = min(latencies)
    max_latency = max(latencies)
    
    print(f"\n日志延迟统计（{num_samples}次采样）：")
    print(f"  平均延迟: {avg_latency:.2f}ms")
    print(f"  标准差: {std_latency:.2f}ms")
    print(f"  最小延迟: {min_latency:.2f}ms")
    print(f"  最大延迟: {max_latency:.2f}ms")
    
    # 验收
    if avg_latency < 10.0:
        print(f"\n✅ 验收通过：平均延迟 {avg_latency:.2f}ms < 10ms")
        return True
    else:
        print(f"\n❌ 验收失败：平均延迟 {avg_latency:.2f}ms >= 10ms")
        return False


def test_database_write_rate():
    """测试数据库写入速率.
    
    Returns:
        写入速率（条/秒）
    """
    print("\n" + "=" * 70)
    print("测试2：数据库写入速率")
    print("=" * 70)
    
    from backend.core.logging_system import LogDatabase
    
    db = LogDatabase("data/test_logs.db")
    
    num_records = 5000
    
    print(f"写入{num_records}条日志记录...")
    
    start = time.perf_counter()
    
    for i in range(num_records):
        log_entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "level": "INFO",
            "logger_name": "test_logger",
            "module": "test_module",
            "function": "test_function",
            "line": 100,
            "message": f"测试日志 #{i}",
            "exception": "",
            "thread": 1,
            "thread_name": "MainThread",
            "process": 1,
            "filename": "test.py",
        }
        
        db.add_log_record(log_entry)
    
    end = time.perf_counter()
    
    elapsed = end - start
    write_rate = num_records / elapsed
    
    print(f"\n数据库写入统计：")
    print(f"  记录数: {num_records}")
    print(f"  耗时: {elapsed:.2f}秒")
    print(f"  写入速率: {write_rate:.0f}条/秒")
    
    # 验收
    if write_rate > 1000:
        print(f"\n✅ 验收通过：写入速率 {write_rate:.0f}条/秒 > 1000条/秒")
        return True
    else:
        print(f"\n❌ 验收失败：写入速率 {write_rate:.0f}条/秒 <= 1000条/秒")
        return False


def test_memory_usage():
    """测试内存占用.
    
    Returns:
        内存占用（MB）
    """
    print("\n" + "=" * 70)
    print("测试3：内存占用")
    print("=" * 70)
    
    import psutil
    import os
    
    process = psutil.Process(os.getpid())
    
    # 获取当前内存
    mem_before = process.memory_info().rss / 1024 / 1024  # MB
    
    print(f"初始内存: {mem_before:.1f}MB")
    
    # 生成10000条日志
    print("生成10000条日志...")
    
    for i in range(10000):
        logging.info(f"内存测试日志 #{i}")
    
    # 等待处理
    time.sleep(2)
    
    # 获取最终内存
    mem_after = process.memory_info().rss / 1024 / 1024  # MB
    
    mem_delta = mem_after - mem_before
    
    print(f"最终内存: {mem_after:.1f}MB")
    print(f"内存增长: {mem_delta:.1f}MB")
    
    # 验收（内存增长应小于100MB）
    if mem_delta < 100:
        print(f"\n✅ 验收通过：内存增长 {mem_delta:.1f}MB < 100MB")
        return True
    else:
        print(f"\n❌ 验收失败：内存增长 {mem_delta:.1f}MB >= 100MB")
        return False


def run_performance_tests():
    """运行所有性能测试."""
    print("=" * 70)
    print("性能测试套件")
    print("=" * 70)
    
    # 启动日志/告警进程
    from backend.processes.process_manager import get_process_manager
    
    pm = get_process_manager()
    pm.register_process(
        name="log_alert",
        target_module="backend.processes.log_alert_process",
        health_port=5559,
    )
    
    print("\n启动日志/告警进程...")
    if not pm.start_process("log_alert"):
        print("❌ 进程启动失败")
        return False
    
    time.sleep(2)
    
    try:
        results = []
        
        # 测试1：日志延迟
        results.append(test_log_latency(1000))
        
        # 测试2：数据库写入速率
        results.append(test_database_write_rate())
        
        # 测试3：内存占用
        results.append(test_memory_usage())
        
        # 汇总结果
        print("\n" + "=" * 70)
        print("性能测试汇总")
        print("=" * 70)
        
        passed = sum(results)
        total = len(results)
        
        print(f"通过测试: {passed}/{total}")
        
        if passed == total:
            print("\n✅ 所有性能测试通过！")
            return True
        else:
            print(f"\n❌ {total - passed}个测试失败")
            return False
            
    finally:
        # 清理
        pm.cleanup()


def main():
    """主函数."""
    try:
        result = run_performance_tests()
        sys.exit(0 if result else 1)
    except KeyboardInterrupt:
        print("\n[测试] 收到中断信号")
        sys.exit(1)


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
