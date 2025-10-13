# -*- coding: utf-8 -*-
"""
交易监控与组合投资集成测试

测试内容：
1. 交易网关监控功能
2. 策略类型识别和监控界面适配
3. 组合投资历史业绩分析
4. 数据持久化
"""

import pytest
from datetime import datetime, timedelta


class TestTradingMonitorIntegration:
    """交易监控集成测试."""

    def test_strategy_type_recognition(self):
        """测试策略类型识别功能."""
        from backend.services.trading_gateway_service import TradingGatewayService

        service = TradingGatewayService()

        # 测试CTA策略识别
        strategy_type = service.identify_strategy_type("DoubleMaStrategy")
        assert strategy_type == "ctastrategy"

        # 测试算法交易识别
        strategy_type = service.identify_strategy_type("TwapAlgo")
        assert strategy_type == "algotrading"

        # 测试价差交易识别
        strategy_type = service.identify_strategy_type("SpreadStrategy")
        assert strategy_type == "spreadtrading"

        # 测试组合策略识别
        strategy_type = service.identify_strategy_type("PortfolioStrategy")
        assert strategy_type == "portfoliostrategy"

    def test_monitor_template_selection(self):
        """测试监控模板选择."""
        from backend.services.trading_gateway_service import TradingGatewayService

        service = TradingGatewayService()

        # 测试各种策略类型的监控模板
        assert (
            service.get_monitor_template_for_strategy(strategy_type="ctastrategy") == "cta_monitor"
        )
        assert (
            service.get_monitor_template_for_strategy(strategy_type="algotrading") == "algo_monitor"
        )
        assert (
            service.get_monitor_template_for_strategy(strategy_type="portfoliostrategy")
            == "portfolio_monitor"
        )
        assert (
            service.get_monitor_template_for_strategy(strategy_type="scripttrader")
            == "default_monitor"
        )

    def test_single_strategy_monitoring(self):
        """测试单策略网关监控条件判断."""
        from backend.services.trading_gateway_service import TradingGatewayService

        service = TradingGatewayService()

        # 模拟网关和策略
        gateway_name = "test_gateway"
        service.strategy_instances[gateway_name] = {
            "strategy_1": {
                "name": "strategy_1",
                "engine_name": "CtaStrategy",
                "status": "running",
            }
        }

        # 测试单策略情况
        monitor_info = service.get_active_strategy_for_monitoring(gateway_name)
        assert monitor_info is not None
        assert monitor_info["strategy_type"] == "ctastrategy"
        assert monitor_info["monitor_template"] == "cta_monitor"

        # 测试多策略情况（不应返回监控信息）
        service.strategy_instances[gateway_name]["strategy_2"] = {
            "name": "strategy_2",
            "engine_name": "CtaStrategy",
            "status": "running",
        }
        monitor_info = service.get_active_strategy_for_monitoring(gateway_name)
        assert monitor_info is None


class TestPortfolioPerformanceAnalysis:
    """组合业绩分析集成测试."""

    def test_historical_performance_calculation(self):
        """测试历史业绩计算."""
        from backend.services.portfolio_service import PortfolioService

        service = PortfolioService()

        # 测试历史业绩分析
        result = service.get_historical_performance(
            portfolio_name="test_portfolio",
            start_date=(datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"),
            end_date=datetime.now().strftime("%Y-%m-%d"),
            period="daily",
        )

        assert result["success"] is True
        assert "data" in result
        assert "performance_curve" in result["data"]
        assert "period_statistics" in result["data"]
        assert "drawdown_analysis" in result["data"]

    def test_performance_curve_calculation(self):
        """测试业绩曲线计算."""
        from backend.services.portfolio_service import PortfolioService

        service = PortfolioService()

        # 准备测试交易数据
        trades = [
            {"date": "2024-01-01", "pnl": 1000},
            {"date": "2024-01-02", "pnl": -500},
            {"date": "2024-01-03", "pnl": 1500},
        ]

        curve = service._calculate_performance_curve(trades)

        assert len(curve) == 3
        assert curve[0]["daily_pnl"] == 1000
        assert curve[0]["cumulative_pnl"] == 1000
        assert curve[1]["cumulative_pnl"] == 500  # 1000 - 500
        assert curve[2]["cumulative_pnl"] == 2000  # 500 + 1500

    def test_period_statistics(self):
        """测试周期统计."""
        from backend.services.portfolio_service import PortfolioService

        service = PortfolioService()

        # 准备测试业绩曲线
        performance_curve = [
            {
                "date": "2024-01-01",
                "daily_pnl": 1000,
                "equity": 1001000,
                "cumulative_pnl": 1000,
            },
            {
                "date": "2024-01-02",
                "daily_pnl": -500,
                "equity": 1000500,
                "cumulative_pnl": 500,
            },
            {
                "date": "2024-01-03",
                "daily_pnl": 1500,
                "equity": 1002000,
                "cumulative_pnl": 2000,
            },
        ]

        # 测试日度统计
        stats = service._calculate_period_statistics_data(performance_curve, "daily")
        assert len(stats) == 3
        assert stats[0]["period"] == "2024-01-01"

    def test_drawdown_analysis(self):
        """测试回撤分析."""
        from backend.services.portfolio_service import PortfolioService

        service = PortfolioService()

        # 准备测试业绩曲线
        performance_curve = [
            {"date": "2024-01-01", "equity": 1000000},
            {"date": "2024-01-02", "equity": 1100000},  # 上涨
            {"date": "2024-01-03", "equity": 1050000},  # 回撤
            {"date": "2024-01-04", "equity": 1000000},  # 继续回撤
            {"date": "2024-01-05", "equity": 1200000},  # 恢复
        ]

        analysis = service._analyze_drawdowns(performance_curve)

        assert len(analysis) > 0
        assert "max_drawdown" in analysis[0]
        assert "current_drawdown" in analysis[0]

    def test_trade_history_persistence(self):
        """测试交易历史持久化."""
        from backend.services.portfolio_service import PortfolioService

        service = PortfolioService()

        # 测试保存交易记录
        trade_data = {
            "date": "2024-01-01",
            "time": "09:30:00",
            "symbol": "600000.SSE",
            "direction": "BUY",
            "price": 10.5,
            "volume": 100,
            "pnl": 150,
        }

        result = service.save_trade_to_history(
            portfolio_id="test_portfolio",
            gateway_name="test_gateway",
            strategy_name="test_strategy",
            trade_data=trade_data,
        )

        assert result["success"] is True

    def test_account_snapshot_persistence(self):
        """测试账户快照持久化."""
        from backend.services.portfolio_service import PortfolioService

        service = PortfolioService()

        # 测试保存账户快照
        snapshot_data = {
            "date": "2024-01-01",
            "time": "15:00:00",
            "balance": 1000000,
            "available": 800000,
            "total_pnl": 5000,
            "daily_pnl": 1000,
        }

        result = service.save_account_snapshot(
            portfolio_id="test_portfolio", snapshot_data=snapshot_data
        )

        assert result["success"] is True


class TestDatabaseIntegration:
    """数据库集成测试."""

    def test_database_tables_created(self):
        """测试数据库表是否正确创建."""
        from backend.core.database import get_db_manager

        db = get_db_manager()

        # 验证新表是否存在
        with db.get_connection() as conn:
            cursor = conn.cursor()

            # 检查trade_history表
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='trade_history'"
            )
            assert cursor.fetchone() is not None

            # 检查position_snapshots表
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='position_snapshots'"
            )
            assert cursor.fetchone() is not None

            # 检查account_snapshots表
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='account_snapshots'"
            )
            assert cursor.fetchone() is not None

    def test_trade_history_crud(self):
        """测试交易历史的增删改查."""
        from backend.core.database import get_db_manager

        db = get_db_manager()

        # 插入测试数据
        query = """
            INSERT INTO trade_history (
                portfolio_id, gateway_name, strategy_name,
                trade_date, trade_time, symbol, direction,
                price, volume, pnl
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        params = (
            "test_portfolio",
            "test_gateway",
            "test_strategy",
            "2024-01-01",
            "09:30:00",
            "600000.SSE",
            "BUY",
            10.5,
            100,
            150,
        )

        db.execute_update(query, params)

        # 查询数据
        query = "SELECT * FROM trade_history WHERE portfolio_id = ?"
        results = db.execute_query(query, ("test_portfolio",))

        assert len(results) > 0
        assert results[0]["symbol"] == "600000.SSE"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
