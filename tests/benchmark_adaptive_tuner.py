# -*- coding: utf-8 -*-
"""A/B 基准对比：classic vs intelligent 自适应调节器决策对比.

该脚本不做真实负载，仅在相同合成指标序列下，对比两个策略的缩放决策曲线，
用于快速人工验证调节的灵敏度/稳定性（抖动）。
"""

from backend.infrastructure.data_module_vnpy.local_data.intelligent_adaptive_tuner import (
    IntelligentAdaptiveTuner,
)


def classic_scale(cpu_percent: float, mem_percent: float) -> float:
    # 复制 classic 策略缩放逻辑（简化版，与 adaptive_concurrency.py 对齐）
    if cpu_percent < 30:
        cpu_scale = 1.5
    elif cpu_percent < 60:
        cpu_scale = 1.2
    elif cpu_percent < 80:
        cpu_scale = 1.0
    else:
        cpu_scale = 0.6

    if mem_percent > 85:
        memory_scale = 0.5
    elif mem_percent > 75:
        memory_scale = 0.7
    elif mem_percent > 60:
        memory_scale = 0.9
    else:
        memory_scale = 1.0

    scale = cpu_scale * memory_scale
    return max(0.3, min(1.5, scale))


def synth_seq(n=60):
    """构造一段包含三个阶段的合成指标序列：
    1. 低压（前20）
    2. I/O延迟上升（中间20）
    3. 丢包上升（后20）
    """
    data = []
    for i in range(n):
        cpu = 25.0 if i < 20 else (50.0 if i < 40 else 55.0)
        mem = 55.0 if i < 20 else (60.0 if i < 40 else 65.0)
        storage_latency = 2.0 if i < 20 else (15.0 if i < 40 else 4.0)
        loss = 0.0 if i < 20 else (0.1 if i < 40 else 0.8)
        sys_metrics = {
            "cpu_percent": cpu,
            "memory_percent": mem,
            "storage_subsystem": {
                "disks": {"d0": {"average_io_latency_ms": storage_latency}},
            },
            "network_subsystem": {
                "packet_loss_rate_in": loss,
                "packet_loss_rate_out": loss,
            },
        }
        data.append((cpu, mem, sys_metrics))
    return data


def main():
    tuner = IntelligentAdaptiveTuner()
    seq = synth_seq()
    classic_curve = []
    intel_curve = []

    for cpu, mem, sys_metrics in seq:
        classic_curve.append(classic_scale(cpu, mem))
        intel_curve.append(tuner.suggest(sys_metrics)["scale_factor"])

    # 输出结果概览
    print("classic:", [round(x, 2) for x in classic_curve])
    print("intellg:", [round(x, 2) for x in intel_curve])


if __name__ == "__main__":
    main()


