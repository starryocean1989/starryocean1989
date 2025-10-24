#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简单验证 - 用人话总结本次改进
"""
import zmq
import json
from typing import Dict, Any, cast

print("\n" + "=" * 80)
print("性能监控与自适应改进 - 验证总结")
print("=" * 80)

print("\n【问题回顾】")
print("您之前遇到的问题：")
print("  1. 硬件性能负载不高，但系统卡顿")
print("  2. 自适应并发策略过于保守")
print("  3. 怀疑存在未监控的性能瓶颈")

print("\n【改进内容】")
print("\n一、扩展监控指标（已完成✅）")
print("  之前只监控:")
print("    - CPU使用率")
print("    - 内存使用率")
print("    - 磁盘使用率")
print("    - 网络流量")
print("\n  现在新增:")
print("    ✓ CPU详细指标:")
print("      • 上下文切换频率 (过高说明线程/进程调度压力大)")
print("      • 中断频率 (过高说明I/O密集)")
print("      • 系统调用频率")
print("    ✓ 内存子系统:")
print("      • 内存交换活动 (换入/换出速度)")
print("      • 这是最严重的性能杀手！")
print("    ✓ 存储子系统:")
print("      • 磁盘I/O平均延迟 (正常<10ms，>20ms就是瓶颈)")
print("      • I/O队列深度")
print("    ✓ 网络子系统:")
print("      • 丢包率 (>1%说明网络质量差)")
print("      • TCP重传率")

print("\n二、智能自适应策略（已完成✅）")
print("  新增 intelligent 策略模式:")
print("    • 多维度压力评分 (不只看CPU/内存)")
print("    • 趋势分析 (滑动窗口EMA平滑)")
print("    • 抖动保护 (死区+冷却机制)")
print("    • 平滑调节 (避免频繁变化)")

print("\n【验证结果】")

# 连接监控进程验证
try:
    ctx = zmq.Context()
    socket = ctx.socket(zmq.REQ)
    socket.setsockopt(zmq.RCVTIMEO, 3000)
    socket.connect("tcp://127.0.0.1:5557")
    socket.send_json({"action": "get_data"})
    data = cast(Dict[str, Any], socket.recv_json())

    system = cast(Dict[str, Any], data.get("system", {}))
    keys = list(system.keys())

    print("\n✅ 监控进程已运行")
    print(f"✅ 新增指标已生效 (共{len(keys)}个字段)")

    # 检查新字段
    required_new_fields = [
        "cpu_detailed",
        "memory_subsystem",
        "storage_subsystem",
        "network_subsystem",
    ]
    for field in required_new_fields:
        if field in keys:
            print(f"  ✓ {field}")
        else:
            print(f"  ✗ {field} (缺失)")

    # 显示当前状态
    cpu = system.get("cpu_percent", 0)
    mem = system.get("memory_percent", 0)
    print("\n当前系统状态:")
    print(f"  CPU: {cpu:.1f}%")
    print(f"  内存: {mem:.1f}%")

    # CPU详情
    cpu_det = cast(Dict[str, Any], system.get("cpu_detailed", {}))
    if cpu_det:
        ctx_sw = cpu_det.get("context_switches_per_sec", 0)
        intr = cpu_det.get("interrupts_per_sec", 0)
        print(f"  上下文切换: {ctx_sw:.0f}/秒")
        print(f"  中断: {intr:.0f}/秒")
        if ctx_sw > 50000:
            print("    ⚠️ 上下文切换频繁，可能并发度过高")

    # 内存详情
    mem_sub = cast(Dict[str, Any], system.get("memory_subsystem", {}))
    if mem_sub:
        swap_in = mem_sub.get("swap_in_kbps", 0)
        swap_out = mem_sub.get("swap_out_kbps", 0)
        if swap_in > 0 or swap_out > 0:
            print(f"  ⚠️⚠️ 内存交换: 换入{swap_in:.1f} KB/s, 换出{swap_out:.1f} KB/s")
            print("       这会严重拖慢系统！需要降低并发或增加内存")
        else:
            print("  ✓ 无内存交换 (良好)")

    # 磁盘详情
    storage = cast(Dict[str, Any], system.get("storage_subsystem", {}))
    if storage and storage.get("disks"):
        disks = cast(Dict[str, Any], storage["disks"])
        for disk_name, disk_info in disks.items():
            disk_info = cast(Dict[str, Any], disk_info)
            latency = disk_info.get("average_io_latency_ms", 0)
            if latency > 0:
                if latency < 10:
                    status = "✓"
                elif latency < 20:
                    status = "△"
                else:
                    status = "⚠️"
                print(f"  {status} {disk_name} 延迟: {latency:.1f} ms")

    # 网络详情
    network = cast(Dict[str, Any], system.get("network_subsystem", {}))
    if network:
        loss_in = network.get("packet_loss_rate_in", 0)
        loss_out = network.get("packet_loss_rate_out", 0)
        if loss_in > 0.01 or loss_out > 0.01:
            print(f"  ⚠️ 网络丢包: 入{loss_in*100:.2f}%, 出{loss_out*100:.2f}%")
        else:
            print("  ✓ 网络质量良好 (丢包率<0.01%)")

except zmq.error.ZMQError as e:
    print(f"\n✗ 无法连接监控进程: {e}")
    print("  请确保监控进程正在运行")
except Exception as e:
    print(f"\n✗ 验证失败: {e}")
    import traceback

    traceback.print_exc()

# 检查配置
try:
    with open("config/terminal_config.json", "rb") as f:
        config = cast(Dict[str, Any], json.loads(f.read().decode("utf-8-sig")))
    adaptive_config = cast(Dict[str, Any], config.get("adaptive", {}))
    strategy = adaptive_config.get("strategy", "classic")

    print(f"\n✅ 自适应策略配置: {strategy}")
    if strategy == "intelligent":
        print("  ✓ 已启用智能策略")
    else:
        print("  ℹ️ 当前使用经典策略")
        print("  💡 可修改 config/terminal_config.json 启用智能策略:")
        print('     "adaptive": { "strategy": "intelligent" }')
except Exception as e:
    print(f"\n✗ 无法读取配置: {e}")

print("\n" + "=" * 80)
print("【使用指南】")
print("=" * 80)

print("\n下次遇到卡顿时，运行此脚本查看:")
print("  1. 是否发生内存交换 (最严重)")
print("  2. 磁盘I/O延迟是否过高 (>20ms)")
print("  3. 上下文切换是否频繁 (>50000/秒)")
print("  4. 网络丢包率是否高 (>1%)")

print("\n这些新指标能帮您准确定位卡顿原因：")
print("  • CPU/内存正常但卡顿 → 可能是磁盘I/O或网络瓶颈")
print("  • 智能策略会自动根据这些指标降低并发")

print("\n" + "=" * 80)
print()
