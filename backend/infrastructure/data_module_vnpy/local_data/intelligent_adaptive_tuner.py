# -*- coding: utf-8 -*-
"""
Intelligent Adaptive Tuner

多维压力评分 + 趋势分析 + 抖动保护 的并发调节器。

说明：
- 保持零依赖，不引入重型ML库；趋势用EMA与P95近似；
- 输入来自监控进程 system 字段的新增四类子系统指标；
- 输出包含并发建议与理由摘要；
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Deque, Dict, Optional


class IntelligentAdaptiveTuner:
    def __init__(
        self,
        base_async_workers: int = 2000,
        base_thread_workers: int = 50,
        base_process_workers: int = 16,
        weights: Optional[Dict[str, float]] = None,
        ema_alpha: float = 0.2,
        adjust_step_max: float = 0.25,  # 单步最大调整比例
        deadband: float = 0.05,  # 死区，避免小抖动
        cooldown_sec: float = 2.0,  # 调整冷却时间
    ) -> None:
        self.base_async_workers = base_async_workers
        self.base_thread_workers = base_thread_workers
        self.base_process_workers = base_process_workers

        self.weights = weights or {
            "cpu": 0.35,
            "memory": 0.25,
            "storage": 0.25,
            "network": 0.15,
        }

        self.ema_alpha = ema_alpha
        self.adjust_step_max = adjust_step_max
        self.deadband = deadband
        self.cooldown_sec = cooldown_sec

        self._pressure_ema: Optional[float] = None
        self._history: Deque[float] = deque(maxlen=60)  # 约一分钟窗口
        self._last_scale: float = 1.0
        self._last_adjust_ts: float = 0.0

    def _norm(self, value: Optional[float], hi: float) -> float:
        if value is None:
            return 0.0
        if hi <= 0:
            return 0.0
        return max(0.0, min(1.0, value / hi))

    def _score_cpu(self, sys_data: Dict[str, Any]) -> float:
        cpu_percent = float(sys_data.get("cpu_percent", 0.0))
        cpu_load = self._norm(cpu_percent, 100.0)

        detailed = sys_data.get("cpu_detailed", {}) or {}
        ctx = detailed.get("context_switches_per_sec")
        intr = detailed.get("interrupts_per_sec")
        # 经验上大于几万/秒说明系统调度压力大，做归一近似
        ctx_load = self._norm(ctx, 50000.0)
        intr_load = self._norm(intr, 20000.0)

        # 加权求和
        return min(1.0, 0.6 * cpu_load + 0.25 * ctx_load + 0.15 * intr_load)

    def _score_memory(self, sys_data: Dict[str, Any]) -> float:
        mem_percent = float(sys_data.get("memory_percent", 0.0))
        mem_load = self._norm(mem_percent, 100.0)
        mem_sub = sys_data.get("memory_subsystem", {}) or {}
        swap_in = mem_sub.get("swap_in_kbps")
        swap_out = mem_sub.get("swap_out_kbps")
        swap_load = max(self._norm(swap_in, 256000.0), self._norm(swap_out, 256000.0))  # 250MB/s
        return min(1.0, 0.8 * mem_load + 0.2 * swap_load)

    def _score_storage(self, sys_data: Dict[str, Any]) -> float:
        st = sys_data.get("storage_subsystem", {}) or {}
        disks = st.get("disks", {}) or {}
        latency_scores = []
        for info in disks.values():
            lat = info.get("average_io_latency_ms")
            if lat is not None:
                latency_scores.append(self._norm(lat, 50.0))  # 50ms 为高风险上限
        return max(latency_scores) if latency_scores else 0.0

    def _score_network(self, sys_data: Dict[str, Any]) -> float:
        net = sys_data.get("network_subsystem", {}) or {}
        loss_in = float(net.get("packet_loss_rate_in", 0.0))
        loss_out = float(net.get("packet_loss_rate_out", 0.0))
        # 1% 丢包即高危
        return max(self._norm(loss_in, 1.0), self._norm(loss_out, 1.0))

    def _calc_pressure(self, sys_data: Dict[str, Any]) -> float:
        cpu = self._score_cpu(sys_data)
        mem = self._score_memory(sys_data)
        sto = self._score_storage(sys_data)
        net = self._score_network(sys_data)

        pressure = (
            cpu * self.weights["cpu"]
            + mem * self.weights["memory"]
            + sto * self.weights["storage"]
            + net * self.weights["network"]
        )

        # EMA 平滑
        self._pressure_ema = (
            pressure
            if self._pressure_ema is None
            else (self.ema_alpha * pressure + (1 - self.ema_alpha) * self._pressure_ema)
        )
        self._history.append(pressure)
        return max(0.0, min(1.0, self._pressure_ema))

    def _suggest_scale(self, pressure: float) -> float:
        # 简单策略曲线：压力低→放大，压力高→缩小
        if pressure < 0.2:
            target = 1.4
        elif pressure < 0.4:
            target = 1.2
        elif pressure < 0.6:
            target = 1.0
        elif pressure < 0.8:
            target = 0.8
        else:
            target = 0.6

        # 死区与最大步长限制
        delta = target - self._last_scale
        if abs(delta) < self.deadband:
            target = self._last_scale
        else:
            step = max(-self.adjust_step_max, min(self.adjust_step_max, delta))
            target = self._last_scale + step

        # 冷却时间限制
        now = time.time()
        if now - self._last_adjust_ts < self.cooldown_sec:
            target = self._last_scale

        return max(0.3, min(1.6, target))

    def suggest(self, system_metrics: Dict[str, Any]) -> Dict[str, Any]:
        pressure = self._calc_pressure(system_metrics or {})
        scale = self._suggest_scale(pressure)

        self._last_adjust_ts = time.time()
        self._last_scale = scale

        return {
            "scale_factor": round(scale, 2),
            "async_workers": max(100, int(self.base_async_workers * scale)),
            "thread_workers": max(5, int(self.base_thread_workers * scale)),
            "process_workers": max(2, int(self.base_process_workers * scale)),
            "pressure_score": round(float(pressure), 3),
        }


__all__ = ["IntelligentAdaptiveTuner"]
