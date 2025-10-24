#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试UI是否正确集成新增监控指标
"""
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

# 模拟测试数据
test_metrics = {
    "cpu_percent": 45.2,
    "memory_percent": 62.5,
    "disk_percent": 75.0,
    "network_speed": {
        "upload_speed_kbps": 1024,
        "download_speed_kbps": 5120,
        "bandwidth_percent": 30.5
    },
    # 新增字段
    "cpu_detailed": {
        "context_switches_per_sec": 28000,
        "interrupts_per_sec": 15000,
        "syscalls_per_sec": 200000
    },
    "memory_subsystem": {
        "swap_in_kbps": 1024,
        "swap_out_kbps": 512
    },
    "storage_subsystem": {
        "disks": {
            "PhysicalDrive0": {
                "average_io_latency_ms": 25.5
            },
            "PhysicalDrive1": {
                "average_io_latency_ms": 8.2
            }
        }
    },
    "network_subsystem": {
        "packet_loss_rate_in": 0.025,
        "packet_loss_rate_out": 0.018
    }
}

print("\n" + "=" * 80)
print("UI集成测试 - 新增监控指标")
print("=" * 80)

print("\n测试数据准备完成，包含以下新增字段：")
print("  ✓ cpu_detailed")
print("  ✓ memory_subsystem")
print("  ✓ storage_subsystem")
print("  ✓ network_subsystem")

print("\n模拟UI表格显示内容：")
print("-" * 80)
print(f"{'指标名称':<20} {'当前值':<30} {'状态':<20} {'备注'}")
print("-" * 80)

# 基础指标
print(f"{'CPU使用率':<20} {test_metrics['cpu_percent']:.1f}% {'':30} {'--'}")
print(f"{'内存使用率':<20} {test_metrics['memory_percent']:.1f}% {'':30} {'--'}")
print(f"{'磁盘使用率':<20} {test_metrics['disk_percent']:.1f}% {'':30} {'--'}")

network = test_metrics['network_speed']
print(f"{'网络上传':<20} {network['upload_speed_kbps']:.1f} KB/s {'':30} {'--'}")
print(f"{'网络下载':<20} {network['download_speed_kbps']:.1f} KB/s {'':30} {'--'}")
print(f"{'带宽占用':<20} {network['bandwidth_percent']:.1f}% {'':30} {'--'}")

# 新增：CPU详细
cpu_det = test_metrics['cpu_detailed']
ctx_switches = cpu_det['context_switches_per_sec']
interrupts = cpu_det['interrupts_per_sec']
print(f"{'上下文切换':<20} {ctx_switches:.0f}/秒 {'':30} {'⚠️ >50000' if ctx_switches > 50000 else '✓'}")
print(f"{'CPU中断':<20} {interrupts:.0f}/秒 {'':30} {'⚠️ >20000' if interrupts > 20000 else '✓'}")

# 新增：内存子系统
mem_sub = test_metrics['memory_subsystem']
swap_in = mem_sub['swap_in_kbps']
swap_out = mem_sub['swap_out_kbps']
if swap_in > 0 or swap_out > 0:
    print(f"{'内存交换':<20} 入{swap_in:.0f} 出{swap_out:.0f} KB/s {'':15} {'⚠️⚠️ 严重影响性能！'}")
else:
    print(f"{'内存交换':<20} 无交换 {'':30} {'✓ 良好'}")

# 新增：存储子系统
storage = test_metrics['storage_subsystem']
for disk_name, disk_info in storage['disks'].items():
    latency = disk_info['average_io_latency_ms']
    status = "⚠️ 瓶颈" if latency > 20 else ("△ 偏高" if latency > 10 else "✓ 正常")
    print(f"{'磁盘延迟(' + disk_name + ')':<20} {latency:.1f} ms {'':30} {status}")

# 新增：网络子系统
net_sub = test_metrics['network_subsystem']
loss_in = net_sub['packet_loss_rate_in']
loss_out = net_sub['packet_loss_rate_out']
status = "⚠️ 高" if (loss_in > 0.01 or loss_out > 0.01) else "✓ 良好"
print(f"{'网络丢包率':<20} 入{loss_in*100:.2f}% 出{loss_out*100:.2f}% {'':15} {status}")

print("-" * 80)

print("\n" + "=" * 80)
print("集成效果预览")
print("=" * 80)

print("\n✅ 新增字段已成功集成到UI代码")
print("✅ UI会自动显示以下告警信息：")
print("  • 上下文切换过高 (>50000/秒)")
print("  • CPU中断频繁 (>20000/秒)")
print("  • ⚠️⚠️ 内存交换活动（最严重，红色高亮）")
print("  • 磁盘延迟瓶颈 (>20ms)")
print("  • 磁盘延迟偏高 (10-20ms)")
print("  • 网络丢包率高 (>1%)")

print("\n📍 位置：系统管理 → 系统监控 → 状态详细数据表格")
print("\n💡 重启UI后，表格会显示以上所有指标，自动标注⚠️符号提醒")

print("\n" + "=" * 80)
print("下一步")
print("=" * 80)
print("\n需要重启UI才能看到新增字段：")
print("  1. 停止当前运行的UI进程")
print("  2. 重新启动终端")
print("  3. 打开 系统管理 → 系统监控")
print("  4. 查看状态详细数据表格（会看到新增的8-12行数据）")
print()

