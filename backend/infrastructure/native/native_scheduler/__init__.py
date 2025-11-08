# -*- coding: utf-8 -*-
"""原子化调度控制组件."""

from __future__ import annotations

import heapq
import logging
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional, Tuple


try:
    from ._native_scheduler import (  # type: ignore[attr-defined]
        NativeScheduler,
        SCHEDULER_AVAILABLE,
        __version__,
    )
except ImportError:  # pragma: no cover
    __version__ = "0.0.0"
    SCHEDULER_AVAILABLE = False

    class NativeScheduler:  # type: ignore[override]
        def __init__(self, *args, **kwargs):
            raise RuntimeError("native_scheduler extension is not available")


LOGGER = logging.getLogger(__name__)


@dataclass
class _ScheduledJob:
    job_id: str
    func: Callable[..., Any]
    trigger: str
    args: Tuple[Any, ...]
    kwargs: Dict[str, Any]
    interval: Optional[float]
    cron_fields: Optional[Dict[str, int]]
    next_run: float
    name: Optional[str] = None


class NativeCronScheduler:
    """轻量级原生调度器包装，支持 cron / interval / date 任务."""

    def __init__(
        self,
        *,
        max_workers: int = 2,
        queue_capacity: int = 64,
        poll_interval: float = 0.25,
        category: str = "default",
    ) -> None:
        if not SCHEDULER_AVAILABLE:
            raise RuntimeError("native_scheduler extension is not available")

        self._native = NativeScheduler()
        self._category = category
        self._native.register_category(category, queue_capacity=queue_capacity, max_workers=max_workers)

        self._jobs: Dict[str, _ScheduledJob] = {}
        self._queue: list[Tuple[float, int, str]] = []
        self._sequence = 0
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._stopped = False
        self._poll_interval = max(0.05, float(poll_interval))

        self._worker_thread = threading.Thread(
            target=self._run_loop,
            name="native-cron-scheduler",
            daemon=True,
        )
        self._worker_thread.start()

    def add_job(self, func: Callable[..., Any], trigger: str, *_, **options: Any) -> str:
        if not callable(func):
            raise TypeError("func must be callable")

        trigger = trigger.lower().strip()
        job_id = options.pop("id", None) or f"native-{uuid.uuid4().hex}"
        replace_existing = bool(options.pop("replace_existing", False))
        name = options.pop("name", None)

        args = options.pop("args", ()) or ()
        if isinstance(args, list):
            args = tuple(args)
        elif not isinstance(args, tuple):
            args = (args,) if args else ()

        call_kwargs = options.pop("kwargs", {}) or {}
        if not isinstance(call_kwargs, dict):
            raise TypeError("kwargs must be a dict")

        now = time.time()
        interval: Optional[float] = None
        cron_fields: Optional[Dict[str, int]] = None

        if trigger == "interval":
            interval = self._extract_interval_seconds(options)
            next_run = now + interval
        elif trigger == "cron":
            cron_fields = self._extract_cron_fields(options)
            next_run = self._compute_next_cron(cron_fields, now=now)
        elif trigger in {"date", "once"}:
            next_run = self._parse_run_date(options)
        else:
            raise ValueError(f"unsupported trigger: {trigger}")

        job = _ScheduledJob(
            job_id=job_id,
            func=func,
            trigger=trigger,
            args=args,
            kwargs=call_kwargs,
            interval=interval,
            cron_fields=cron_fields,
            next_run=next_run,
            name=name,
        )

        with self._lock:
            if replace_existing and job_id in self._jobs:
                self._jobs.pop(job_id, None)
            elif not replace_existing and job_id in self._jobs:
                raise ValueError(f"job {job_id} already exists")

            self._jobs[job_id] = job
            heapq.heappush(self._queue, (job.next_run, self._sequence, job_id))
            self._sequence += 1
            self._wake.set()

        return job_id

    def remove_job(self, job_id: str) -> bool:
        with self._lock:
            removed = self._jobs.pop(job_id, None) is not None
            if removed:
                self._wake.set()
            return removed

    def shutdown(self, *, wait: bool = True) -> None:
        with self._lock:
            if self._stopped:
                return
            self._stopped = True
            self._wake.set()

        if wait and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=2.0)

        try:
            self._native.shutdown(wait=wait)
        except Exception:  # noqa: BLE001
            LOGGER.debug("native scheduler shutdown encountered error", exc_info=True)

    def __del__(self) -> None:  # pragma: no cover
        try:
            self.shutdown(wait=False)
        except Exception:
            pass

    def _extract_interval_seconds(self, options: Dict[str, Any]) -> float:
        seconds = float(options.pop("seconds", 0) or 0)
        minutes = float(options.pop("minutes", 0) or 0)
        hours = float(options.pop("hours", 0) or 0)
        total = seconds + minutes * 60 + hours * 3600
        if total <= 0:
            raise ValueError("interval must be positive")
        return total

    def _extract_cron_fields(self, options: Dict[str, Any]) -> Dict[str, int]:
        hour = int(options.pop("hour", 0) or 0)
        minute = int(options.pop("minute", 0) or 0)
        second = int(options.pop("second", 0) or 0)
        if not (0 <= hour <= 23 and 0 <= minute <= 59 and 0 <= second <= 59):
            raise ValueError("invalid cron time components")
        return {"hour": hour, "minute": minute, "second": second}

    def _parse_run_date(self, options: Dict[str, Any]) -> float:
        run_date = options.pop("run_date", None)
        if run_date is None:
            raise ValueError("run_date is required for date trigger")
        if isinstance(run_date, datetime):
            return run_date.timestamp()
        if isinstance(run_date, (int, float)):
            return float(run_date)
        if isinstance(run_date, str):
            try:
                return datetime.fromisoformat(run_date).timestamp()
            except ValueError as exc:
                raise ValueError("invalid run_date string format") from exc
        raise TypeError("run_date must be datetime, timestamp, or ISO string")

    def _compute_next_cron(self, fields: Dict[str, int], *, now: Optional[float] = None) -> float:
        current = datetime.fromtimestamp(now or time.time())
        target = current.replace(
            hour=fields.get("hour", 0),
            minute=fields.get("minute", 0),
            second=fields.get("second", 0),
            microsecond=0,
        )
        if target <= current:
            target += timedelta(days=1)
        return target.timestamp()

    def _run_loop(self) -> None:
        while True:
            with self._lock:
                if self._stopped:
                    return
                if not self._queue:
                    timeout = self._poll_interval
                else:
                    next_run, _, _ = self._queue[0]
                    timeout = max(0.0, next_run - time.time())

            signaled = self._wake.wait(timeout)
            if signaled:
                self._wake.clear()
                continue

            with self._lock:
                if self._stopped or not self._queue:
                    continue
                next_run, _, job_id = heapq.heappop(self._queue)
                job = self._jobs.get(job_id)
                if job is None:
                    continue
                now = time.time()
                if job.next_run - now > 0.002:
                    heapq.heappush(self._queue, (job.next_run, self._sequence, job.job_id))
                    self._sequence += 1
                    continue

            self._submit_job(job)

    def _submit_job(self, job: _ScheduledJob) -> None:
        should_reschedule = False
        next_run = None
        now = time.time()

        if job.trigger == "interval" and job.interval:
            next_run = now + job.interval
            should_reschedule = True
        elif job.trigger == "cron" and job.cron_fields:
            next_run = self._compute_next_cron(job.cron_fields, now=now)
            should_reschedule = True

        if should_reschedule and next_run:
            job.next_run = next_run
            with self._lock:
                if not self._stopped and job.job_id in self._jobs:
                    heapq.heappush(self._queue, (job.next_run, self._sequence, job.job_id))
                    self._sequence += 1
        else:
            with self._lock:
                self._jobs.pop(job.job_id, None)

        try:
            self._native.submit(self._category, job.func, job.args, job.kwargs)
        except Exception:  # noqa: BLE001
            LOGGER.exception("native scheduler job submission failed")


__all__ = [
    "NativeScheduler",
    "NativeCronScheduler",
    "SCHEDULER_AVAILABLE",
    "__version__",
]

