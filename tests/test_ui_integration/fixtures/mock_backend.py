# -*- coding: utf-8 -*-
"""
后端Mock fixture.

提供后端API和服务的mock实现。
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

logger = logging.getLogger(__name__)


class MockAPIResponse:
    """Mock API响应类."""

    def __init__(self, success: bool = True, data: Any = None, message: str = ""):
        """初始化Mock API响应."""
        self.success = success
        self.data = data or []
        self.message = message

    def json(self):
        """返回JSON格式数据."""
        return {
            "success": self.success,
            "data": self.data,
            "message": self.message,
        }


class MockBackendAPI:
    """Mock后端API类."""

    def __init__(self):
        """初始化Mock后端API."""
        self.logger = logging.getLogger(self.__class__.__name__)
        self._call_history = []

    def record_call(self, method: str, endpoint: str, **kwargs):
        """记录API调用."""
        self._call_history.append(
            {
                "method": method,
                "endpoint": endpoint,
                "kwargs": kwargs,
                "timestamp": datetime.now(),
            }
        )

    def get_call_history(self) -> List[Dict]:
        """获取调用历史."""
        return self._call_history

    # 系统管理API
    def get_system_monitoring(self) -> MockAPIResponse:
        """获取系统监控数据."""
        self.record_call("GET", "/api/system-manager/monitoring/system")
        return MockAPIResponse(
            success=True,
            data={
                "cpu_percent": 45.2,
                "memory_percent": 62.8,
                "disk_percent": 55.0,
                "network_sent": 1024000,
                "network_recv": 2048000,
                "timestamp": datetime.now().isoformat(),
            },
            message="获取系统监控成功",
        )

    def get_performance_metrics(self) -> MockAPIResponse:
        """获取性能指标."""
        self.record_call("GET", "/api/system-manager/monitoring/performance")
        return MockAPIResponse(
            success=True,
            data={
                "data_processing_rate": 1000,
                "strategy_execution_time": 0.05,
                "trade_latency": 0.002,
            },
            message="获取性能指标成功",
        )

    # 数据中心API
    def get_symbols(
        self, exchange: str | None = None, product: str | None = None
    ) -> MockAPIResponse:
        """获取品种列表."""
        self.record_call(
            "GET",
            "/api/data-center/symbols",
            exchange=exchange,
            product=product,
        )

        symbols = [
            {
                "symbol": "000001",
                "exchange": "SSE",
                "name": "平安银行",
                "product": "股票",
            },
            {
                "symbol": "000002",
                "exchange": "SSE",
                "name": "万科A",
                "product": "股票",
            },
            {
                "symbol": "600000",
                "exchange": "SSE",
                "name": "浦发银行",
                "product": "股票",
            },
            {
                "symbol": "600036",
                "exchange": "SSE",
                "name": "招商银行",
                "product": "股票",
            },
        ]

        # 应用过滤
        if exchange:
            symbols = [s for s in symbols if s["exchange"] == exchange]
        if product:
            symbols = [s for s in symbols if s["product"] == product]

        return MockAPIResponse(success=True, data=symbols, message="获取品种列表成功")

    def reload_symbols(self) -> MockAPIResponse:
        """重新加载品种（调用API）."""
        self.record_call("POST", "/api/data-center/symbols/reload")
        return MockAPIResponse(
            success=True,
            data={"count": 4},
            message="重新加载品种成功",
        )

    def refresh_symbols(self) -> MockAPIResponse:
        """刷新品种（从缓存）."""
        self.record_call("POST", "/api/data-center/symbols/refresh")
        return MockAPIResponse(success=True, data={"count": 4}, message="刷新品种成功")

    def start_download(
        self, download_type: str, start_date: str | None = None
    ) -> MockAPIResponse:
        """开始数据下载."""
        self.record_call(
            "POST",
            "/api/data-center/download/start",
            download_type=download_type,
            start_date=start_date,
        )
        return MockAPIResponse(
            success=True,
            data={"task_id": "task_001", "status": "running"},
            message="下载任务已启动",
        )

    def get_download_progress(self, task_id: str) -> MockAPIResponse:
        """获取下载进度."""
        self.record_call("GET", f"/api/data-center/download/progress/{task_id}")
        return MockAPIResponse(
            success=True,
            data={"task_id": task_id, "progress": 45, "status": "running"},
            message="获取进度成功",
        )

    def query_local_data(
        self, symbol: str, start_date: str, end_date: str, interval: str
    ) -> MockAPIResponse:
        """查询本地数据."""
        self.record_call(
            "GET",
            "/api/data-center/local-data/query",
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            interval=interval,
        )

        # 生成模拟OHLCV数据
        data = []
        current_date = datetime.fromisoformat(start_date)
        end_dt = datetime.fromisoformat(end_date)

        while current_date <= end_dt:
            data.append(
                {
                    "datetime": current_date.isoformat(),
                    "open": 10.0,
                    "high": 10.5,
                    "low": 9.8,
                    "close": 10.2,
                    "volume": 1000000,
                }
            )
            current_date += timedelta(days=1)

        return MockAPIResponse(success=True, data=data, message="查询成功")

    # 行情看板API
    def get_kline_data(
        self, symbol: str, interval: str, limit: int = 100
    ) -> MockAPIResponse:
        """获取K线数据."""
        self.record_call(
            "GET",
            "/api/market-board/kline",
            symbol=symbol,
            interval=interval,
            limit=limit,
        )
        return MockAPIResponse(success=True, data=[], message="获取K线数据成功")

    # 策略中心API
    def list_strategies(self) -> MockAPIResponse:
        """列出策略文件."""
        self.record_call("GET", "/api/strategy-center/strategies")
        return MockAPIResponse(
            success=True,
            data=[
                {"name": "strategy1.py", "type": "file"},
                {"name": "strategy2.py", "type": "file"},
            ],
            message="获取策略列表成功",
        )

    def create_strategy(self, name: str, content: str = "") -> MockAPIResponse:
        """创建策略文件."""
        self.record_call(
            "POST",
            "/api/strategy-center/strategies",
            name=name,
            content=content,
        )
        return MockAPIResponse(success=True, data={"name": name}, message="创建成功")

    def run_backtest(self, strategy_name: str, config: Dict) -> MockAPIResponse:
        """运行回测."""
        self.record_call(
            "POST",
            "/api/strategy-center/backtest",
            strategy_name=strategy_name,
            config=config,
        )
        return MockAPIResponse(
            success=True,
            data={"backtest_id": "bt_001", "status": "running"},
            message="回测已启动",
        )

    # 交易网关API
    def create_gateway(self, gateway_type: str, config: Dict) -> MockAPIResponse:
        """创建网关实例."""
        self.record_call(
            "POST",
            "/api/trading-gateway/gateways",
            gateway_type=gateway_type,
            config=config,
        )
        return MockAPIResponse(
            success=True,
            data={"gateway_id": "gw_001", "type": gateway_type},
            message="网关创建成功",
        )

    def connect_gateway(self, gateway_id: str, password: str) -> MockAPIResponse:
        """连接网关."""
        self.record_call(
            "POST",
            f"/api/trading-gateway/gateways/{gateway_id}/connect",
            password=password,
        )
        return MockAPIResponse(
            success=True, data={"status": "connected"}, message="连接成功"
        )

    def deploy_strategy_to_gateway(
        self, gateway_id: str, strategy_name: str
    ) -> MockAPIResponse:
        """部署策略到网关."""
        self.record_call(
            "POST",
            f"/api/trading-gateway/gateways/{gateway_id}/strategies",
            strategy_name=strategy_name,
        )
        return MockAPIResponse(
            success=True,
            data={"strategy_id": "st_001"},
            message="部署成功",
        )

    # 组合投资API
    def get_portfolios(self) -> MockAPIResponse:
        """获取组合列表."""
        self.record_call("GET", "/api/portfolio/portfolios")
        return MockAPIResponse(success=True, data=[], message="获取组合列表成功")

    def create_custom_portfolio(
        self, name: str, gateway_ids: List[str]
    ) -> MockAPIResponse:
        """创建自定义组合."""
        self.record_call(
            "POST", "/api/portfolio/portfolios", name=name, gateway_ids=gateway_ids
        )
        return MockAPIResponse(
            success=True,
            data={"portfolio_id": "pf_001", "name": name},
            message="创建组合成功",
        )


@pytest.fixture(scope="function")
def mock_backend_api():
    """提供Mock后端API实例."""
    api = MockBackendAPI()
    logger.info("Mock后端API创建成功")
    return api


@pytest.fixture(scope="function")
def mock_http_client(mock_backend_api):  # pylint: disable=redefined-outer-name
    """
    Mock HTTP客户端.

    将所有HTTP请求重定向到mock_backend_api。
    """
    with (
        patch("requests.get") as mock_get,
        patch("requests.post") as mock_post,
        patch("requests.put") as mock_put,
        patch("requests.delete") as mock_delete,
    ):
        # 配置mock的返回值
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "success": True,
                "data": [],
                "message": "Success",
            },
        )
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "success": True,
                "data": {},
                "message": "Success",
            },
        )

        yield {
            "get": mock_get,
            "post": mock_post,
            "put": mock_put,
            "delete": mock_delete,
            "api": mock_backend_api,
        }
