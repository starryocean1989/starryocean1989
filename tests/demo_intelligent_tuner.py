#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
智能自适应调节器演示 - 直观展示新功能
"""
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from backend.infrastructure.data_module_vnpy.local_data.intelligent_adaptive_tuner import IntelligentAdaptiveTuner

def demo():
    print("\n" + "=" * 80)
    print("智能自适应并发调节器 - 功能演示")
    print("=" * 80)

    print("\n这是本次改进的核心功能：")
    print("  • 不只看 CPU/内存")
    print("  • 全面监控：CPU详情 + 内存交换 + 磁盘延迟 + 网络丢包")
    print("  • 智能决策：多维压力评分 + 趋势分析 + 平滑调节")
    print()

    # 创建调节器
    tuner = IntelligentAdaptiveTuner(
        base_async_workers=8,
        base_thread_workers=4,
        base_process_workers=2
    )

    # 场景测试
    scenarios = [
        {
            "name": "场景1: 系统健康 (应该提升并发)",
            "metrics": {
                "cpu_percent": 25.0,
                "memory_percent": 35.0,
                "cpu_detailed": {
                    "context_switches_per_sec": 12000,
                    "interrupts_per_sec": 8000
                },
                "memory_subsystem": {"swap_in_kbps": 0, "swap_out_kbps": 0},
                "storage_subsystem": {"disks": {"PhysicalDrive0": {"average_io_latency_ms": 3.0}}},
                "network_subsystem": {"packet_loss_rate_in": 0.0001, "packet_loss_rate_out": 0.0001}
            },
            "expected": "缩放因子 > 1.0"
        },
        {
            "name": "场景2: 磁盘I/O延迟高 (应该降低并发)",
            "metrics": {
                "cpu_percent": 30.0,  # CPU不高
                "memory_percent": 45.0,  # 内存正常
                "cpu_detailed": {
                    "context_switches_per_sec": 18000,
                    "interrupts_per_sec": 15000
                },
                "memory_subsystem": {"swap_in_kbps": 0, "swap_out_kbps": 0},
                "storage_subsystem": {"disks": {"PhysicalDrive0": {"average_io_latency_ms": 48.0}}},  # 延迟高！
                "network_subsystem": {"packet_loss_rate_in": 0.0002, "packet_loss_rate_out": 0.0001}
            },
            "expected": "缩放因子 < 1.0（因为磁盘成瓶颈）"
        },
        {
            "name": "场景3: 内存交换严重 (应该大幅降低并发)",
            "metrics": {
                "cpu_percent": 35.0,
                "memory_percent": 88.0,
                "cpu_detailed": {
                    "context_switches_per_sec": 28000,
                    "interrupts_per_sec": 14000
                },
                "memory_subsystem": {"swap_in_kbps": 8000, "swap_out_kbps": 6000},  # 交换严重！
                "storage_subsystem": {"disks": {}},
                "network_subsystem": {"packet_loss_rate_in": 0.0001, "packet_loss_rate_out": 0.0001}
            },
            "expected": "缩放因子明显 < 1.0"
        },
        {
            "name": "场景4: 网络丢包 (应该降低并发)",
            "metrics": {
                "cpu_percent": 32.0,
                "memory_percent": 48.0,
                "cpu_detailed": {
                    "context_switches_per_sec": 19000,
                    "interrupts_per_sec": 16000
                },
                "memory_subsystem": {"swap_in_kbps": 0, "swap_out_kbps": 0},
                "storage_subsystem": {"disks": {}},
                "network_subsystem": {"packet_loss_rate_in": 0.025, "packet_loss_rate_out": 0.018}  # 丢包 2-3%！
            },
            "expected": "缩放因子 < 1.0（因为网络质量差）"
        }
    ]

    import time

    for i, scenario in enumerate(scenarios):
        print("\n" + "-" * 80)
        print(f"【{scenario['name']}】")
        print("-" * 80)

        metrics = scenario['metrics']

        # 显示关键指标
        print(f"\n关键指标:")
        print(f"  CPU: {metrics['cpu_percent']:.1f}%")
        print(f"  内存: {metrics['memory_percent']:.1f}%")

        # CPU详情
        cpu_det = metrics.get('cpu_detailed', {})
        ctx = cpu_det.get('context_switches_per_sec', 0)
        intr = cpu_det.get('interrupts_per_sec', 0)
        if ctx > 0 or intr > 0:
            print(f"  上下文切换: {ctx:.0f}/秒")
            print(f"  中断: {intr:.0f}/秒")

        # 内存详情
        mem_sub = metrics.get('memory_subsystem', {})
        swap_in = mem_sub.get('swap_in_kbps', 0)
        swap_out = mem_sub.get('swap_out_kbps', 0)
        if swap_in > 0 or swap_out > 0:
            print(f"  ⚠️ 内存交换: 换入{swap_in:.0f} KB/s, 换出{swap_out:.0f} KB/s")

        # 磁盘详情
        storage = metrics.get('storage_subsystem', {}).get('disks', {})
        for disk_name, disk_info in storage.items():
            latency = disk_info.get('average_io_latency_ms', 0)
            if latency > 0:
                status = "⚠️" if latency > 20 else "✓"
                print(f"  {status} 磁盘延迟: {latency:.1f} ms")

        # 网络详情
        network = metrics.get('network_subsystem', {})
        loss_in = network.get('packet_loss_rate_in', 0)
        loss_out = network.get('packet_loss_rate_out', 0)
        if loss_in > 0.001 or loss_out > 0.001:
            status = "⚠️" if (loss_in > 0.01 or loss_out > 0.01) else "✓"
            print(f"  {status} 网络丢包: 入{loss_in*100:.2f}%, 出{loss_out*100:.2f}%")

        # 调用intelligent tuner
        result = tuner.suggest(metrics)

        print(f"\n智能调节结果:")
        print(f"  系统压力评分: {result['pressure_score']:.3f} (0=空闲, 1=满载)")
        print(f"  缩放因子: {result['scale_factor']:.2f}")
        print(f"  并发配置:")
        print(f"    - async_workers: {result['async_workers']}")
        print(f"    - thread_workers: {result['thread_workers']}")
        print(f"    - process_workers: {result['process_workers']}")
        print(f"\n预期: {scenario['expected']}")

        # 判断结果
        scale = result['scale_factor']
        pressure = result['pressure_score']
        if pressure < 0.3 and scale > 1.0:
            print(f"✅ 判断: 压力低，提升并发")
        elif pressure > 0.5 and scale < 1.0:
            print(f"✅ 判断: 压力高，降低并发")
        elif 0.3 <= pressure <= 0.5:
            print(f"✅ 判断: 压力适中，维持并发")

        # 模拟时间流逝，避免冷却机制
        time.sleep(0.1)

    print("\n" + "=" * 80)
    print("总结")
    print("=" * 80)
    print("\n✅ 智能调节器的优势:")
    print("  1. 即使 CPU/内存正常，也能发现磁盘I/O或网络瓶颈")
    print("  2. 根据多个维度的压力综合决策（不会只看一个指标）")
    print("  3. 平滑调节（避免频繁抖动）")
    print("\n💡 实际应用:")
    print("  • 已集成到系统中，通过 config/terminal_config.json 启用")
    print("  • 下次卡顿时，智能调节器会自动识别瓶颈并降低并发")
    print("  • 运行 tests/verify_improvements.py 可查看实时监控数据")
    print()

if __name__ == "__main__":
    demo()

