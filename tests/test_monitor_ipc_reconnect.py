import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from backend.infrastructure.system_vnpy.monitor_system import MonitoringProcessV2


class _StubQueryPipe:
    def __init__(self):
        self.wait_calls = 0
        self.read_calls = 0
        self.write_payloads = []
        self.write_event = asyncio.Event()

    async def wait_for_client(self, timeout=None):
        self.wait_calls += 1
        if self.wait_calls == 1:
            raise asyncio.TimeoutError()

    async def read(self, size=65536):
        self.read_calls += 1
        if self.read_calls == 1:
            return json.dumps({"action": "get_data"}).encode("utf-8")
        raise ValueError("Pipe not opened")

    async def write(self, data: bytes):
        self.write_payloads.append(json.loads(data.decode("utf-8")))
        self.write_event.set()
        return len(data)


class _StubStatusPipe:
    def __init__(self):
        self.wait_calls = 0
        self.read_calls = 0
        self.read_event = asyncio.Event()

    async def wait_for_client(self, timeout=None):
        self.wait_calls += 1
        if self.wait_calls == 1:
            raise asyncio.TimeoutError()

    async def read(self, size=65536):
        self.read_calls += 1
        if self.read_calls == 1:
            payload = json.dumps({"status": "ok"}).encode("utf-8")
            self.read_event.set()
            return payload
        raise ValueError("Pipe not opened")


@pytest.mark.asyncio
async def test_query_pipe_retries_after_initial_timeout_and_processes_request():
    monitor = MonitoringProcessV2.__new__(MonitoringProcessV2)  # type: ignore
    monitor.running = True
    monitor.query_pipe = _StubQueryPipe()
    monitor.status_pipe = None
    monitor.alerts_pipe = None
    monitor.monitoring_data = {
        "system": {"cpu_percent": 12.3},
        "process": {"processes": []},
        "service": {},
        "hardware": {},
        "smart": {},
        "analysis": {},
    }
    monitor.adaptive_threshold = None
    monitor.business_metrics_collector = SimpleNamespace(
        get_concurrent_tasks=lambda: {"download": 0, "backtest": 0, "trading": 0, "total": 0}
    )
    monitor.system_monitor = SimpleNamespace(
        bandwidth_monitor=SimpleNamespace(test_bandwidth_full_async=lambda: asyncio.sleep(0)),
        get_bandwidth_info=lambda: {"sent": 0, "recv": 0},
    )
    monitor._background_bandwidth_task = None
    monitor.smart_trigger_event = None

    task = asyncio.create_task(monitor._handle_query_pipe())

    await asyncio.wait_for(monitor.query_pipe.write_event.wait(), timeout=2.0)

    monitor.running = False
    await asyncio.wait_for(task, timeout=1.0)

    assert monitor.query_pipe.wait_calls >= 2
    assert len(monitor.query_pipe.write_payloads) == 1
    response = monitor.query_pipe.write_payloads[0]
    assert response["system"]["cpu_percent"] == 12.3


@pytest.mark.asyncio
async def test_status_pipe_retries_and_updates_service_state():
    monitor = MonitoringProcessV2.__new__(MonitoringProcessV2)  # type: ignore
    monitor.running = True
    monitor.query_pipe = None
    monitor.status_pipe = _StubStatusPipe()
    monitor.monitoring_data = {
        "system": {},
        "process": {},
        "service": {},
        "hardware": {},
        "smart": {},
        "analysis": {},
    }

    task = asyncio.create_task(monitor._handle_status_pipe())

    await asyncio.wait_for(monitor.status_pipe.read_event.wait(), timeout=2.0)

    monitor.running = False
    await asyncio.wait_for(task, timeout=1.0)

    assert monitor.status_pipe.wait_calls >= 2
    assert monitor.monitoring_data["service"]["status"] == "ok"

