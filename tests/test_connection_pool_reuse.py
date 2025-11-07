from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional, cast

import pytest

from concurrent.futures import ProcessPoolExecutor

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.infrastructure.data_module_vnpy.load_balancer import ServerPoolManager


@dataclass
class _DummyPool:
    closed: bool = False

    def shutdown(self, wait: bool = True) -> None:  # pragma: no cover - 行为简单
        self.closed = True


@pytest.fixture
def server_pool(monkeypatch, tmp_path: Path) -> Iterator[ServerPoolManager]:
    from backend.infrastructure.data_module_vnpy.core_engine import ConfigManager, DailyCacheManager

    def fake_init_defaults(cls) -> None:
        cls.DEFAULT_IPV4_SERVERS = [
            {"ip": "127.0.0.1", "port": 7709, "name": "local-1"},
            {"ip": "127.0.0.2", "port": 7709, "name": "local-2"},
        ]
        cls.DEFAULT_IPV6_SERVERS = []

    monkeypatch.setattr(
        ServerPoolManager,
        "_init_default_servers",
        classmethod(lambda cls: fake_init_defaults(cls)),
    )

    monkeypatch.setattr(
        DailyCacheManager,
        "load_with_validation",
        staticmethod(lambda path: (None, None, False)),
    )
    monkeypatch.setattr(
        DailyCacheManager,
        "save_with_date",
        staticmethod(lambda data, path: True),
    )

    async def fake_batch(self, servers, max_concurrent: Optional[int] = None, timeout: float = 3.0):
        return {tuple(server): 0.001 * (index + 1) for index, server in enumerate(servers)}

    monkeypatch.setattr(
        "backend.infrastructure.tdx_asyncio.ServerTester.batch_test_servers",
        fake_batch,
        raising=False,
    )

    config_manager = ConfigManager()
    monkeypatch.setattr(config_manager, "get_cache_dir", lambda: tmp_path)

    pool = ServerPoolManager(config_manager)
    yield pool
    pool.close_connection_pool()
    pool._retry_connection_pool = None


def test_test_servers_updates_latency(server_pool: ServerPoolManager) -> None:
    server_pool.test_servers(max_workers=1)
    assert all(server.ping_time > 0 for server in server_pool._ipv4_servers)
    assert all(server.available for server in server_pool._ipv4_servers)


def test_close_connection_pool_idempotent(server_pool: ServerPoolManager) -> None:
    dummy_pool = _DummyPool()
    server_pool._connection_pool = cast("ProcessPoolExecutor", dummy_pool)  # type: ignore[assignment]
    server_pool.close_connection_pool()
    assert dummy_pool.closed is True
    assert server_pool._connection_pool is None
    server_pool.close_connection_pool()  # second call should be a no-op

