# -*- coding: utf-8 -*-
"""网络请求E2E测试夹具.

提供：
- 独立测试缓存目录
- Mock服务（服务器池、IPO下载、K线下载）
- 缓存场景生成器（不存在、失效、有效、损坏）
"""

import json
import shutil
import tempfile
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Generator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture(scope="function")
def isolated_cache_dir(monkeypatch) -> Generator[Path, None, None]:
    """提供独立的测试缓存目录.

    使用pytest的monkeypatch修改DailyCacheManager._get_cache_dir()，
    使其指向临时测试目录。测试后自动清理。

    Yields:
        Path: 独立的测试缓存目录
    """
    # 创建临时目录
    temp_dir = tempfile.mkdtemp(prefix="network_test_cache_")
    cache_path = Path(temp_dir)

    # 修改DailyCacheManager._get_cache_dir()的返回值
    def mock_get_cache_dir():
        return cache_path

    monkeypatch.setattr(
        "backend.infrastructure.data_module_vnpy.cache_manager.DailyCacheManager._get_cache_dir",
        classmethod(lambda cls: cache_path),
    )

    yield cache_path

    # 清理临时目录
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def setup_cache_scenario(isolated_cache_dir):
    """缓存场景生成器工厂.

    返回一个函数，用于按指定场景准备缓存文件。

    Returns:
        callable: 场景生成函数 setup_scenario(cache_file, scenario, data)
    """

    def setup_scenario(cache_file: str, scenario: str, data: Any = None):
        """按场景准备缓存文件.

        Args:
            cache_file: 缓存文件名（如 "trading_calendar.json"）
            scenario: 场景类型（"missing", "expired", "valid", "corrupted"）
            data: 缓存数据（如果为None，使用默认数据）
        """
        cache_path = isolated_cache_dir / cache_file

        if scenario == "missing":
            # 场景1：缓存不存在
            if cache_path.exists():
                cache_path.unlink()

        elif scenario == "expired":
            # 场景2：缓存失效（昨天的日期）
            yesterday = (date.today() - timedelta(days=1)).isoformat()
            cache_obj = {"cache_date": yesterday, "data": data or _get_default_data(cache_file)}
            cache_path.write_text(json.dumps(cache_obj, ensure_ascii=False, indent=2), encoding="utf-8")

        elif scenario == "valid":
            # 场景3：缓存有效（今天的日期）
            today = date.today().isoformat()
            cache_obj = {"cache_date": today, "data": data or _get_default_data(cache_file)}
            cache_path.write_text(json.dumps(cache_obj, ensure_ascii=False, indent=2), encoding="utf-8")

        elif scenario == "corrupted":
            # 场景4：缓存损坏（无效的JSON）
            cache_path.write_text("{invalid json content", encoding="utf-8")

        else:
            raise ValueError(f"未知场景类型: {scenario}")

    def _get_default_data(cache_file: str) -> Any:
        """获取各类缓存文件的默认数据."""
        if cache_file == "trading_calendar.json":
            # 交易日历：约250个交易日
            return [
                (date.today() - timedelta(days=i)).isoformat() for i in range(250) if i % 7 not in [5, 6]
            ]

        elif cache_file == "server_pool_cache.json":
            # 服务器池：10个可用服务器
            return [["119.147.212.81", 7709], ["124.74.236.94", 7709], ["114.80.63.12", 7709]] * 3 + [
                ["119.147.212.81", 7709]
            ]

        elif cache_file == "stock_list_classified.json":
            # 品种列表：模拟分类数据
            return {
                "classified": {
                    "stock": [{"code": f"00000{i}", "name": f"测试股票{i}", "market": 0} for i in range(100)],
                    "etf": [{"code": f"51000{i}", "name": f"测试ETF{i}", "market": 1} for i in range(20)],
                },
                "total_count": 120,
            }

        else:
            # 默认空数据
            return {}

    return setup_scenario


@pytest.fixture(scope="function")
def mock_server_pool_manager():
    """Mock服务器池管理器.

    避免实际执行30-60秒的服务器测速。

    Yields:
        MagicMock: Mock的ServerPoolManager
    """
    mock_manager = MagicMock()
    mock_manager._running = False
    mock_manager._cache_date = None

    def mock_start():
        """Mock的start方法."""
        mock_manager._running = True
        mock_manager._cache_date = date.today().isoformat()
        # 模拟加载缓存或测速成功
        return True

    def mock_get_stats():
        """Mock的get_stats方法."""
        return {"total": 150, "available": 120, "unavailable": 30}

    mock_manager.start = mock_start
    mock_manager.get_stats = mock_get_stats

    with patch(
        "backend.infrastructure.data_module_vnpy.load_balancer.load_balancer.ServerPoolManager", mock_manager
    ):
        with patch("backend.infrastructure.data_module_vnpy.load_balancer.server_pool_manager", mock_manager):
            yield mock_manager


@pytest.fixture(scope="function")
def mock_ipo_downloader():
    """Mock IPO日期下载器.

    避免实际执行30-60秒的IPO日期批量下载。

    Yields:
        AsyncMock: Mock的IPO下载函数
    """

    async def mock_download_ipo_dates(*args, **kwargs):
        """Mock的download_ipo_dates函数."""
        # 模拟返回下载成功的结果
        return {"success": True, "downloaded": 100, "failed": 0, "elapsed": 1.5}

    with patch(
        "backend.infrastructure.data_module_vnpy.data_acquisition.data_acquisition.download_ipo_dates",
        side_effect=mock_download_ipo_dates,
    ):
        yield mock_download_ipo_dates


@pytest.fixture(scope="function")
def mock_kline_downloader():
    """Mock K线下载器.

    避免实际执行耗时的K线数据下载。

    Yields:
        AsyncMock: Mock的K线下载函数
    """

    async def mock_start_incremental_download(*args, **kwargs):
        """Mock的start_incremental_download_async函数."""
        # 模拟返回下载成功的结果
        return {"success": True, "total": 50, "downloaded": 50, "failed": 0, "elapsed": 2.0}

    mock_fetcher = MagicMock()
    mock_fetcher.start_incremental_download_async = AsyncMock(side_effect=mock_start_incremental_download)

    yield mock_fetcher


@pytest.fixture(scope="function")
def cache_scenario_manager(isolated_cache_dir, setup_cache_scenario):
    """缓存场景管理器.

    提供便捷的缓存场景管理接口。

    Returns:
        CacheScenarioManager: 场景管理器实例
    """

    class CacheScenarioManager:
        """缓存场景管理器类."""

        def __init__(self, cache_dir: Path, scenario_setup):
            self.cache_dir = cache_dir
            self.setup_scenario = scenario_setup

        def prepare_all_missing(self):
            """准备所有缓存不存在的场景."""
            self.setup_scenario("trading_calendar.json", "missing")
            self.setup_scenario("server_pool_cache.json", "missing")
            self.setup_scenario("stock_list_classified.json", "missing")

        def prepare_all_valid(self):
            """准备所有缓存有效的场景."""
            self.setup_scenario("trading_calendar.json", "valid")
            self.setup_scenario("server_pool_cache.json", "valid")
            self.setup_scenario("stock_list_classified.json", "valid")

        def prepare_all_expired(self):
            """准备所有缓存失效的场景."""
            self.setup_scenario("trading_calendar.json", "expired")
            self.setup_scenario("server_pool_cache.json", "expired")
            self.setup_scenario("stock_list_classified.json", "expired")

        def prepare_mixed_scenario(self, scenarios: Dict[str, str]):
            """准备混合场景.

            Args:
                scenarios: 字典，key为缓存文件名，value为场景类型
                    例如: {
                        "trading_calendar.json": "valid",
                        "server_pool_cache.json": "expired",
                        "stock_list_classified.json": "missing"
                    }
            """
            for cache_file, scenario in scenarios.items():
                self.setup_scenario(cache_file, scenario)

        def verify_cache_exists(self, cache_file: str) -> bool:
            """验证缓存文件是否存在."""
            return (self.cache_dir / cache_file).exists()

        def get_cache_content(self, cache_file: str) -> Dict[str, Any]:
            """读取缓存文件内容."""
            cache_path = self.cache_dir / cache_file
            if not cache_path.exists():
                return {}
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}

    return CacheScenarioManager(isolated_cache_dir, setup_cache_scenario)


@pytest.fixture(scope="function")
def network_test_env(isolated_cache_dir, cache_scenario_manager, mock_server_pool_manager):
    """网络测试环境（综合fixture）.

    组合多个fixture，提供完整的测试环境。

    Returns:
        dict: 测试环境字典，包含：
            - cache_dir: 独立缓存目录
            - scenario_manager: 缓存场景管理器
            - mock_server_pool: Mock的服务器池管理器
    """
    return {
        "cache_dir": isolated_cache_dir,
        "scenario_manager": cache_scenario_manager,
        "mock_server_pool": mock_server_pool_manager,
    }

