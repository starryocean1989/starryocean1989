#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
自适应策略对比测试 - 直观展示新旧策略的区别
"""
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from backend.infrastructure.system_vnpy.monitors import SystemMonitor
from backend.infrastructure.data_module_vnpy.local_data.adaptive_concurrency import AdaptiveConcurrencyTuner

def simulate_scenarios():
    """模拟不同的性能场景"""
    scenarios = [
        {
            "name": "场景1: CPU高负载",
            "metrics": {
                "cpu_percent": 85.0,
                "memory_percent": 40.0,
                "cpu_detailed": {
                    "context_switches_per_sec": 30000,
                    "interrupts_per_sec": 15000
                },
                "memory_subsystem": {"swap_in_kbps": 0, "swap_out_kbps": 0},
                "storage_subsystem": {"disks": {}},
                "network_subsystem": {"packet_loss_rate_in": 0, "packet_loss_rate_out": 0}
            }
        },
        {
            "name": "场景2: 磁盘I/O延迟高",
            "metrics": {
                "cpu_percent": 30.0,
                "memory_percent": 50.0,
                "cpu_detailed": {
                    "context_switches_per_sec": 20000,
                    "interrupts_per_sec": 18000
                },
                "memory_subsystem": {"swap_in_kbps": 0, "swap_out_kbps": 0},
                "storage_subsystem": {
                    "disks": {
                        "PhysicalDrive0": {"average_io_latency_ms": 45.0}
                    }
                },
                "network_subsystem": {"packet_loss_rate_in": 0, "packet_loss_rate_out": 0}
            }
        },
        {
            "name": "场景3: 内存交换(最严重)",
            "metrics": {
                "cpu_percent": 40.0,
                "memory_percent": 88.0,
                "cpu_detailed": {
                    "context_switches_per_sec": 25000,
                    "interrupts_per_sec": 12000
                },
                "memory_subsystem": {"swap_in_kbps": 5000, "swap_out_kbps": 3000},
                "storage_subsystem": {"disks": {}},
                "network_subsystem": {"packet_loss_rate_in": 0, "packet_loss_rate_out": 0}
            }
        },
        {
            "name": "场景4: 网络丢包",
            "metrics": {
                "cpu_percent": 35.0,
                "memory_percent": 45.0,
                "cpu_detailed": {
                    "context_switches_per_sec": 22000,
                    "interrupts_per_sec": 16000
                },
                "memory_subsystem": {"swap_in_kbps": 0, "swap_out_kbps": 0},
                "storage_subsystem": {"disks": {}},
                "network_subsystem": {"packet_loss_rate_in": 0.02, "packet_loss_rate_out": 0.015}
            }
        },
        {
            "name": "场景5: 系统健康",
            "metrics": {
                "cpu_percent": 25.0,
                "memory_percent": 35.0,
                "cpu_detailed": {
                    "context_switches_per_sec": 15000,
                    "interrupts_per_sec": 10000
                },
                "memory_subsystem": {"swap_in_kbps": 0, "swap_out_kbps": 0},
                "storage_subsystem": {"disks": {}},
                "network_subsystem": {"packet_loss_rate_in": 0, "packet_loss_rate_out": 0}
            }
        }
    ]
    return scenarios

def mock_system_monitor(metrics):
    """创建模拟的SystemMonitor"""
    class ResourceUsage:
        def __init__(self, cpu, memory, disk=0):
            self.cpu_percent = cpu
            self.memory_percent = memory
            self.disk_percent = disk

    class MockMonitor:
        def get_resource_usage_with_extended_metrics(self):
            return metrics

        def get_resource_usage(self):
            return ResourceUsage(
                metrics.get("cpu_percent", 0),
                metrics.get("memory_percent", 0),
                0
            )

        def get_cpu_os_detailed(self):
            return metrics.get("cpu_detailed", {})

        def get_memory_subsystem_metrics(self):
            return metrics.get("memory_subsystem", {})

        def get_storage_subsystem_metrics(self):
            return metrics.get("storage_subsystem", {})

        def get_network_subsystem_metrics(self):
            return metrics.get("network_subsystem", {})

    return MockMonitor()

def main():
    print("\n" + "=" * 80)
    print("自适应并发策略对比测试")
    print("=" * 80)

    print("\n说明:")
    print("  • classic 策略: 只看 CPU + 内存")
    print("  • intelligent 策略: 看 CPU + 内存 + 磁盘I/O + 网络 (更全面)")
    print()

    # 基础并发配置
    base_async = 8
    base_thread = 4
    base_process = 2

    scenarios = simulate_scenarios()

    for scenario in scenarios:
        print("\n" + "-" * 80)
        print(f"【{scenario['name']}】")
        print("-" * 80)

        metrics = scenario['metrics']

        # 显示场景特征
        print(f"\n系统状态:")
        print(f"  CPU: {metrics['cpu_percent']:.1f}%")
        print(f"  内存: {metrics['memory_percent']:.1f}%")

        cpu_det = metrics.get('cpu_detailed', {})
        if cpu_det.get('context_switches_per_sec', 0) > 25000:
            print(f"  上下文切换: {cpu_det['context_switches_per_sec']:.0f}/秒 ⚠️")

        mem_sub = metrics.get('memory_subsystem', {})
        if mem_sub.get('swap_in_kbps', 0) > 0 or mem_sub.get('swap_out_kbps', 0) > 0:
            print(f"  内存交换: 换入{mem_sub['swap_in_kbps']:.0f} KB/s, 换出{mem_sub['swap_out_kbps']:.0f} KB/s ⚠️⚠️")

        storage = metrics.get('storage_subsystem', {}).get('disks', {})
        for disk_name, disk_info in storage.items():
            latency = disk_info.get('average_io_latency_ms', 0)
            if latency > 20:
                print(f"  磁盘延迟: {latency:.1f} ms ⚠️")

        network = metrics.get('network_subsystem', {})
        loss_in = network.get('packet_loss_rate_in', 0)
        loss_out = network.get('packet_loss_rate_out', 0)
        if loss_in > 0.01 or loss_out > 0.01:
            print(f"  网络丢包: 入{loss_in*100:.1f}%, 出{loss_out*100:.1f}% ⚠️")

        # 测试两种策略
        mock_monitor = mock_system_monitor(metrics)

        # Classic 策略 - 临时修改配置文件
        import json
        import shutil
        config_path = 'config/terminal_config.json'
        backup_path = 'config/terminal_config.json.bak'

        # 备份配置
        shutil.copy(config_path, backup_path)

        try:
            # 测试 classic
            with open(config_path, 'rb') as f:
                config = json.loads(f.read().decode('utf-8-sig'))
            config['adaptive']['strategy'] = 'classic'
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)

            classic_tuner = AdaptiveConcurrencyTuner(
                mock_monitor,
                base_async_workers=base_async,
                base_thread_workers=base_thread,
                base_process_workers=base_process
            )
            classic_result = classic_tuner.adjust_concurrency()

            # 测试 intelligent
            config['adaptive']['strategy'] = 'intelligent'
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4, ensure_ascii=False)

            intelligent_tuner = AdaptiveConcurrencyTuner(
                mock_monitor,
                base_async_workers=base_async,
                base_thread_workers=base_thread,
                base_process_workers=base_process
            )
            intelligent_result = intelligent_tuner.adjust_concurrency()

        finally:
            # 恢复配置
            shutil.copy(backup_path, config_path)
            os.remove(backup_path)

        # 显示对比结果
        print(f"\n并发调整对比:")
        print(f"  {'策略':<12} {'缩放因子':<10} {'async':<8} {'thread':<8} {'process':<8} {'建议'}")
        print(f"  {'-'*12} {'-'*10} {'-'*8} {'-'*8} {'-'*8} {'-'*30}")

        classic_scale = classic_result.get('scale_factor', 1.0)
        classic_async = int(base_async * classic_scale)
        classic_thread = int(base_thread * classic_scale)
        classic_process = int(base_process * classic_scale)
        classic_reason = classic_result.get('reason', '')

        print(f"  {'classic':<12} {classic_scale:<10.2f} {classic_async:<8} {classic_thread:<8} {classic_process:<8} {classic_reason}")

        intel_scale = intelligent_result.get('scale_factor', 1.0)
        intel_async = int(base_async * intel_scale)
        intel_thread = int(base_thread * intel_scale)
        intel_process = int(base_process * intel_scale)
        intel_reason = intelligent_result.get('reason', '')

        print(f"  {'intelligent':<12} {intel_scale:<10.2f} {intel_async:<8} {intel_thread:<8} {intel_process:<8} {intel_reason}")

        # 分析差异
        if abs(classic_scale - intel_scale) > 0.05:
            if intel_scale < classic_scale:
                print(f"\n  💡 intelligent 更保守: 发现了 classic 忽略的瓶颈")
            else:
                print(f"\n  💡 intelligent 更激进: 硬件还有余力可用")

    print("\n" + "=" * 80)
    print("总结")
    print("=" * 80)
    print("\n关键区别:")
    print("  1. classic 只关注 CPU/内存，容易漏掉磁盘I/O、网络等瓶颈")
    print("  2. intelligent 全面监控，在隐性瓶颈出现时会主动降低并发")
    print("  3. 当磁盘延迟高或出现内存交换时，intelligent 会及时降低并发避免卡顿")
    print("\n推荐:")
    print("  ✓ 已在 config/terminal_config.json 启用 intelligent 策略")
    print("  ✓ 下次卡顿时运行 tests/verify_improvements.py 查看瓶颈")
    print()

if __name__ == "__main__":
    main()

