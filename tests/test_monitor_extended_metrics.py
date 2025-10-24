# -*- coding: utf-8 -*-
"""扩展监控指标字段存在性与容错测试（轻量单元测试）。"""

from backend.infrastructure.system_vnpy.monitors import SystemMonitor


def test_extended_metrics_shape():
    monitor = SystemMonitor()

    cpu_det = monitor.get_cpu_os_detailed()
    mem_sub = monitor.get_memory_subsystem_metrics()
    sto_sub = monitor.get_storage_subsystem_metrics()
    net_sub = monitor.get_network_subsystem_metrics()

    # 只验证key存在与类型合理，不强制要求有值（跨平台可能返回空/None）
    assert isinstance(cpu_det, dict)
    assert isinstance(mem_sub, dict)
    assert isinstance(sto_sub, dict)
    assert isinstance(net_sub, dict)

    # 关键字段存在
    for k in [
        "interrupts_per_sec",
        "context_switches_per_sec",
        "syscalls_per_sec",
        "soft_interrupts_per_sec",
        "steal_time_percent",
    ]:
        assert k in cpu_det

    for k in [
        "page_faults_per_sec",
        "swap_in_kbps",
        "swap_out_kbps",
        "cache_hit_ratio",
        "memory_bandwidth_kbps",
    ]:
        assert k in mem_sub

    assert "disks" in sto_sub

    for k in [
        "packet_loss_rate_in",
        "packet_loss_rate_out",
        "tcp_retransmissions_per_sec",
        "rtt_ms",
    ]:
        assert k in net_sub


