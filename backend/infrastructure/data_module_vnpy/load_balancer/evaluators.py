# -*- coding: utf-8 -*-
"""
资源压力评估器

基于《系统监控指标.md》的木桶理论模型，评估系统资源压力并计算缩放因子。

评分公式（总分100分）：
- CPU压力：40分满分 = 40 × (1 - cpu_percent/100) × (1 - context_switches/100000)
- 内存压力：30分满分 = 30 × (1 - memory_percent/100) × (1 if swap==0 else 0)
- 磁盘压力：15分满分 = 15 × (1 - io_latency/50)
- 网络压力：15分满分 = 15 × (1 - packet_loss/0.05)

压力等级：
- 85-100分：资源充足，可提高并发（scale_factor 1.0-1.6）
- 70-85分：正常（scale_factor 1.0）
- 50-70分：轻度压力（scale_factor 0.7）
- <50分：严重瓶颈（scale_factor 0.5）
- swap活跃：紧急情况（scale_factor 0.3）
"""

import logging
from typing import Any, Dict


class ResourcePressureEvaluator:
    """资源压力评估器（基于系统监控指标.md的评分模型）

    使用木桶理论模型评估系统资源压力：
    - 系统性能 = min(CPU性能, 内存性能, 磁盘性能, 网络性能)
    - 瓶颈 = 得分最低的维度

    特性：
    - 基于系统监控指标.md的标准评分模型
    - 识别瓶颈维度（cpu/memory/disk/network/balanced）
    - 计算并发缩放因子（0.3-1.6）
    - 检测紧急情况（swap活跃）
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def evaluate(self, metrics: Dict[str, Any]) -> Dict[str, Any]:
        """评估当前资源压力

        Args:
            metrics: 系统监控指标字典（由SystemMetricsMonitor提供）

        Returns:
            评估结果字典：
            {
                "pressure_score": float,      # 0-100，越高越充足
                "bottleneck": str,            # cpu/memory/disk/network/balanced
                "scale_factor": float,        # 并发缩放因子 0.3-1.6
                "cpu_score": float,           # CPU维度得分（40分满分）
                "memory_score": float,        # 内存维度得分（30分满分）
                "disk_score": float,          # 磁盘维度得分（15分满分）
                "network_score": float,       # 网络维度得分（15分满分）
                "swap_active": bool,          # 是否发生swap
                "emergency": bool,            # 是否紧急情况
                "reason": str,                # 评估原因说明
            }
        """
        system = metrics.get("system", {})

        # 提取关键指标
        cpu_percent = system.get("cpu_percent", 0)
        memory_percent = system.get("memory_percent", 0)

        cpu_detailed = system.get("cpu_detailed", {})
        context_switches = cpu_detailed.get("context_switches_per_sec", 0)

        memory_subsystem = system.get("memory_subsystem", {})
        swap_in = memory_subsystem.get("swap_in_kbps", 0)
        swap_out = memory_subsystem.get("swap_out_kbps", 0)

        storage_subsystem = system.get("storage_subsystem", {})
        disks = storage_subsystem.get("disks", {})
        io_latency = 0
        if disks:
            first_disk = list(disks.values())[0]
            io_latency = first_disk.get("average_io_latency_ms", 0)

        network_subsystem = system.get("network_subsystem", {})
        packet_loss = network_subsystem.get("packet_loss_rate_in", 0)

        # 计算各维度评分（按系统监控指标.md的公式）

        # CPU压力 (40分满分)
        # 考虑CPU使用率和上下文切换频率
        cpu_usage_factor = 1 - cpu_percent / 100
        context_switch_factor = 1 - min(context_switches / 100000, 1)
        cpu_score = 40 * cpu_usage_factor * context_switch_factor

        # 内存压力 (30分满分)
        # 发生swap则内存得分为0（最严重瓶颈）
        swap_active = swap_in > 0 or swap_out > 0
        memory_usage_factor = 1 - memory_percent / 100
        swap_penalty = 0 if swap_active else 1
        memory_score = 30 * memory_usage_factor * swap_penalty

        # 磁盘压力 (15分满分)
        # I/O延迟超过50ms则得分为0
        io_latency_factor = 1 - min(io_latency / 50, 1)
        disk_score = 15 * io_latency_factor

        # 网络压力 (15分满分)
        # 丢包率超过5%则得分为0
        packet_loss_factor = 1 - min(packet_loss / 0.05, 1)
        network_score = 15 * packet_loss_factor

        # 总分（木桶理论：取最小值的加权和）
        total_score = cpu_score + memory_score + disk_score + network_score

        # 找出瓶颈维度（得分最低的）
        scores = {
            "cpu": cpu_score,
            "memory": memory_score,
            "disk": disk_score,
            "network": network_score,
        }
        bottleneck = min(scores.keys(), key=lambda k: scores[k])

        # 判断是否均衡（各维度得分差异<5分）
        score_range = max(scores.values()) - min(scores.values())
        if score_range < 5:
            bottleneck = "balanced"

        # 计算缩放因子
        scale_factor, emergency, reason = self._calculate_scale_factor(
            total_score, bottleneck, swap_active
        )

        result = {
            "pressure_score": round(total_score, 2),
            "bottleneck": bottleneck,
            "scale_factor": round(scale_factor, 2),
            "cpu_score": round(cpu_score, 2),
            "memory_score": round(memory_score, 2),
            "disk_score": round(disk_score, 2),
            "network_score": round(network_score, 2),
            "swap_active": swap_active,
            "emergency": emergency,
            "reason": reason,
        }

        self.logger.debug(
            f"资源压力评估: 总分{total_score:.1f}, " f"瓶颈={bottleneck}, 缩放={scale_factor:.2f}"
        )

        return result

    def _calculate_scale_factor(
        self, total_score: float, bottleneck: str, swap_active: bool
    ) -> tuple:
        """计算并发缩放因子

        根据系统压力评分决定并发度调整策略。

        Args:
            total_score: 系统总分（0-100）
            bottleneck: 瓶颈维度
            swap_active: 是否发生swap

        Returns:
            (scale_factor, emergency, reason)
        """
        # 紧急情况：发生swap
        if swap_active:
            return (0.3, True, "🚨 发生内存swap，紧急降低并发至30%")

        # 严重瓶颈：总分<50
        if total_score < 50:
            return (0.5, False, f"⚠️ 系统压力大（{bottleneck}瓶颈），降低并发至50%")

        # 轻度压力：总分50-70
        if total_score < 70:
            return (0.7, False, f"⚠️ 系统有压力（{bottleneck}瓶颈），适度降低并发至70%")

        # 正常：总分70-85
        if total_score < 85:
            return (1.0, False, "✅ 系统正常，使用标准并发（100%）")

        # 资源充足：总分85-100
        # 线性插值：85分=1.0x, 100分=1.6x
        scale_factor = min(1.0 + (total_score - 85) / 15 * 0.6, 1.6)
        return (scale_factor, False, f"🚀 系统资源充足，提高并发至{int(scale_factor*100)}%")
