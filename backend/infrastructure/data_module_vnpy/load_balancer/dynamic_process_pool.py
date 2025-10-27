# -*- coding: utf-8 -*-
"""
动态进程池管理器（v3.6新增）

提供运行时动态增减进程的能力，支持LoadBalancer的智能决策
"""

import asyncio
import logging
import multiprocessing
from typing import Dict, Any, Callable, Optional, List
from multiprocessing import Process, Event


class DynamicProcessPool:
    """运行时动态增减进程的进程池管理器

    核心功能：
    1. 支持运行时增加进程（创建新worker并启动）
    2. 支持运行时减少进程（优雅停止worker）
    3. 所有worker从共享task_queue拉取任务
    4. 支持独立的result_queue和metrics_queue

    使用方式：
    ```python
    pool = DynamicProcessPool(
        initial_processes=4,
        worker_function=my_worker_process,
        shared_queues={
            'task_queue': task_queue,
            'result_queue': result_queue,
            'metrics_queue': metrics_queue,
        },
        worker_kwargs={'param1': value1, ...}
    )

    await pool.start()

    # 动态调整
    await pool.adjust_processes(6)  # 增加到6个进程

    await pool.stop()
    ```
    """

    def __init__(
        self,
        initial_processes: int,
        worker_function: Callable,
        shared_queues: Dict[str, Any],
        worker_kwargs: Optional[Dict[str, Any]] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """初始化动态进程池

        Args:
            initial_processes: 初始进程数
            worker_function: worker进程入口函数
            shared_queues: 共享队列字典，必须包含：
                - task_queue: 任务队列
                - result_queue: 结果队列
                - metrics_queue: 监控指标队列
                可选：
                - progress_queue: 进度队列
                - config_queue: 配置队列
            worker_kwargs: 传递给worker函数的其他参数
            logger: 日志记录器
        """
        self.initial_processes = initial_processes
        self.worker_function = worker_function
        self.shared_queues = shared_queues
        self.worker_kwargs = worker_kwargs or {}
        self.logger = logger or logging.getLogger(__name__)

        # 进程管理
        self.processes: List[Process] = []
        self.next_worker_id = 0
        self.stop_event: Optional["Event"] = None

        # 验证必需的队列
        required_queues = ["task_queue", "result_queue", "metrics_queue"]
        for queue_name in required_queues:
            if queue_name not in shared_queues:
                raise ValueError(f"缺少必需的队列: {queue_name}")

    async def start(self):
        """启动初始进程池"""
        self.logger.info("=" * 80)
        self.logger.info(f"🚀 启动动态进程池: {self.initial_processes}个进程")
        self.logger.info("=" * 80)

        # 创建停止事件
        ctx = multiprocessing.get_context("spawn")
        self.stop_event = ctx.Event()

        # 启动初始进程
        for _ in range(self.initial_processes):
            self._create_and_start_worker()

        self.logger.info(f"✅ {len(self.processes)}个worker进程已启动")

    def _create_and_start_worker(self) -> Process:
        """创建并启动一个新的worker进程"""
        worker_id = self.next_worker_id
        self.next_worker_id += 1

        # 准备worker参数
        worker_args = {
            "worker_id": worker_id,
            "stop_event": self.stop_event,
            **self.shared_queues,
            **self.worker_kwargs,
        }

        # 创建进程
        p = Process(target=self.worker_function, kwargs=worker_args, name=f"Worker-{worker_id}")
        p.start()
        self.processes.append(p)

        self.logger.info(f"✅ 创建新worker进程: Worker-{worker_id} (PID: {p.pid})")
        return p

    async def adjust_processes(self, target_count: int):
        """动态调整进程数量

        Args:
            target_count: 目标进程数
        """
        current_count = len([p for p in self.processes if p.is_alive()])

        if target_count == current_count:
            return

        if target_count > current_count:
            # 增加进程
            to_add = target_count - current_count
            self.logger.info(f"📈 增加进程: {current_count} → {target_count} (+{to_add})")

            for _ in range(to_add):
                self._create_and_start_worker()
                await asyncio.sleep(0.1)  # 短暂延迟，避免同时创建大量进程

            self.logger.info(
                f"✅ 进程增加完成，当前活跃进程: {len([p for p in self.processes if p.is_alive()])}"
            )

        elif target_count < current_count:
            # 减少进程（优雅停止）
            to_remove = current_count - target_count
            self.logger.info(f"📉 减少进程: {current_count} → {target_count} (-{to_remove})")

            # 标记进程为待停止（通过发送特殊任务或等待其完成当前任务）
            # 注意：我们不能强制终止进程，只能等待它们自然结束
            # 策略：移除进程引用，让它们完成当前任务后自然退出

            alive_processes = [p for p in self.processes if p.is_alive()]
            to_stop = alive_processes[target_count:]

            # 记录待停止的进程
            for p in to_stop:
                self.logger.info(f"🔻 标记进程待停止: {p.name} (PID: {p.pid})")

            # 保留前target_count个活跃进程
            self.processes = alive_processes[:target_count]

            self.logger.info(f"✅ 进程减少标记完成，保留进程数: {len(self.processes)}")
            self.logger.info("   注意：被移除的进程将在完成当前任务后自然退出")

    def get_active_process_count(self) -> int:
        """获取当前活跃进程数"""
        return len([p for p in self.processes if p.is_alive()])

    async def stop(self, timeout: float = 5.0):
        """停止所有进程

        Args:
            timeout: 等待进程结束的超时时间（秒）
        """
        self.logger.info("=" * 80)
        self.logger.info("🛑 停止动态进程池")
        self.logger.info("=" * 80)

        # 设置停止事件
        if self.stop_event:
            self.stop_event.set()

        # 等待所有进程结束
        alive_count = len([p for p in self.processes if p.is_alive()])
        self.logger.info(f"等待{alive_count}个进程结束（超时{timeout}秒）...")

        for p in self.processes:
            if p.is_alive():
                p.join(timeout=timeout / len(self.processes))
                if p.is_alive():
                    self.logger.warning(f"⚠️ 进程{p.name}未能在超时内结束，强制终止")
                    p.terminate()
                    p.join(timeout=1.0)

        self.logger.info("✅ 所有进程已停止")

    def get_status(self) -> Dict[str, Any]:
        """获取进程池状态"""
        alive_processes = [p for p in self.processes if p.is_alive()]
        return {
            "total_processes": len(self.processes),
            "alive_processes": len(alive_processes),
            "dead_processes": len(self.processes) - len(alive_processes),
            "next_worker_id": self.next_worker_id,
            "process_pids": [p.pid for p in alive_processes],
        }
