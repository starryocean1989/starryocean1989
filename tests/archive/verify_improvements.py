#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
性能改进验证脚本 - 用人话解释改进效果
"""
import zmq
import json
from typing import Dict, Any, cast


def get_monitoring_data() -> Dict[str, Any]:
    """从监控进程获取数据"""
    ctx = zmq.Context()
    socket = ctx.socket(zmq.REQ)
    socket.setsockopt(zmq.RCVTIMEO, 5000)
    socket.connect("tcp://127.0.0.1:5557")
    socket.send_json({"action": "get_data"})
    return cast(Dict[str, Any], socket.recv_json())


def analyze_bottlenecks(data: Dict[str, Any]) -> None:
    """分析系统瓶颈"""
    system = data.get("system", {})

    print("=" * 60)
    print("【系统瓶颈分析】")
    print("=" * 60)

    # 1. CPU 分析
    cpu_percent = system.get("cpu_percent", 0)
    cpu_detailed = system.get("cpu_detailed", {})
    ctx_switches = cpu_detailed.get("context_switches_per_sec", 0)
    interrupts = cpu_detailed.get("interrupts_per_sec", 0)

    print(f"\n✓ CPU 使用率: {cpu_percent:.1f}%")
    if cpu_percent > 80:
        print("  ⚠️ CPU 负载高")
    if ctx_switches > 50000:
        print(f"  ⚠️ 上下文切换频繁: {ctx_switches:.0f}/秒 (可能线程/进程过多)")
    if interrupts > 30000:
        print(f"  ⚠️ 中断频率高: {interrupts:.0f}/秒 (可能I/O密集)")

    # 2. 内存分析
    memory_percent = system.get("memory_percent", 0)
    memory_subsys = system.get("memory_subsystem", {})
    swap_in = memory_subsys.get("swap_in_kbps", 0)
    swap_out = memory_subsys.get("swap_out_kbps", 0)

    print(f"\n✓ 内存使用率: {memory_percent:.1f}%")
    if memory_percent > 85:
        print("  ⚠️ 内存紧张")
    if swap_in > 0 or swap_out > 0:
        print(f"  ⚠️ 发生内存交换 (换入:{swap_in:.1f} KB/s, 换出:{swap_out:.1f} KB/s)")
        print("     → 这会严重拖慢系统！")

    # 3. 磁盘分析
    storage_subsys = system.get("storage_subsystem", {})
    disks = storage_subsys.get("disks", {})

    print("\n✓ 磁盘状态:")
    has_disk_bottleneck = False
    for disk_name, disk_info in disks.items():
        latency = disk_info.get("average_io_latency_ms", 0)
        if latency > 0:
            print(f"  - {disk_name}: 平均延迟 {latency:.1f} ms")
            if latency > 20:
                print(f"    ⚠️ 延迟偏高 (正常应 < 10ms)")
                has_disk_bottleneck = True

    # 4. 网络分析
    network_subsys = system.get("network_subsystem", {})
    packet_loss_in = network_subsys.get("packet_loss_rate_in", 0)
    packet_loss_out = network_subsys.get("packet_loss_rate_out", 0)

    print("\n✓ 网络状态:")
    print(f"  - 丢包率: 入={packet_loss_in*100:.2f}%, 出={packet_loss_out*100:.2f}%")
    if packet_loss_in > 0.01 or packet_loss_out > 0.01:
        print("  ⚠️ 网络丢包明显 (正常应 < 1%)")

    print("\n" + "=" * 60)
    print("【瓶颈总结】")
    print("=" * 60)

    bottlenecks = []
    if cpu_percent > 80:
        bottlenecks.append("CPU 负载高")
    if ctx_switches > 50000:
        bottlenecks.append("上下文切换过多")
    if memory_percent > 85:
        bottlenecks.append("内存紧张")
    if swap_in > 0 or swap_out > 0:
        bottlenecks.append("内存交换(最严重)")
    if has_disk_bottleneck:
        bottlenecks.append("磁盘 I/O 延迟高")
    if packet_loss_in > 0.01 or packet_loss_out > 0.01:
        bottlenecks.append("网络丢包")

    if bottlenecks:
        print("\n当前发现的性能瓶颈:")
        for i, bottleneck in enumerate(bottlenecks, 1):
            print(f"  {i}. {bottleneck}")
        print("\n💡 建议: 智能自适应策略会根据这些指标自动降低并发数")
    else:
        print("\n✅ 系统状态良好，无明显瓶颈")


def show_adaptive_status(data: Dict[str, Any]) -> None:
    """显示自适应调节状态"""
    print("\n" + "=" * 60)
    print("【自适应并发状态】")
    print("=" * 60)

    # 读取配置
    try:
        with open("config/terminal_config.json", "r", encoding="utf-8") as f:
            config = json.load(f)
            strategy = config.get("adaptive", {}).get("strategy", "classic")
    except:
        strategy = "unknown"

    print(f"\n当前策略: {strategy}")

    if strategy == "intelligent":
        print("✅ 已启用智能策略")
        print("\n智能策略特点:")
        print("  • 监控 4 大子系统 (CPU/内存/磁盘/网络)")
        print("  • 根据多维压力动态调节")
        print("  • 平滑调整 (避免抖动)")
        print("  • 冷却机制 (避免频繁变化)")
    else:
        print("ℹ️ 使用经典策略 (仅看 CPU + 内存)")
        print("\n可切换到智能策略:")
        print("  修改 config/terminal_config.json")
        print('  "adaptive": { "strategy": "intelligent" }')


def main():
    print("\n" + "=" * 60)
    print("性能监控与自适应并发改进验证")
    print("=" * 60)

    try:
        # 1. 获取监控数据
        print("\n正在查询监控数据...")
        data = get_monitoring_data()

        # 2. 分析瓶颈
        analyze_bottlenecks(data)

        # 3. 显示自适应状态
        show_adaptive_status(data)

        print("\n" + "=" * 60)
        print("【改进说明】")
        print("=" * 60)
        print("\n之前的问题:")
        print("  1. 只监控 CPU/内存，磁盘I/O延迟、网络丢包等隐形瓶颈看不到")
        print("  2. 自适应策略太保守，不敢调整并发")

        print("\n现在的改进:")
        print("  1. ✅ 新增 CPU详细指标 (中断/上下文切换)")
        print("  2. ✅ 新增内存子系统 (交换活动)")
        print("  3. ✅ 新增存储子系统 (I/O延迟/队列)")
        print("  4. ✅ 新增网络子系统 (丢包/重传)")
        print("  5. ✅ 智能自适应策略 (多维压力+平滑调节)")

        print("\n下次遇到卡顿时:")
        print("  → 运行此脚本，直接看到是哪个子系统成了瓶颈")
        print("  → 智能策略会自动根据瓶颈降低并发")

    except zmq.error.ZMQError as e:
        print(f"\n❌ 无法连接监控进程: {e}")
        print("请确保监控进程正在运行")
    except Exception as e:
        print(f"\n❌ 验证失败: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
