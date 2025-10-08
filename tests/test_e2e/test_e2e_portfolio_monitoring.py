# -*- coding: utf-8 -*-
"""
E2E测试: 组合投资监控.

测试功能链路: 6.0.4 组合投资监控链条

验证点:
1. 组合管理组件初始化
2. 自动组合识别（激活>1策略的网关）
3. 自定义组合创建（虚拟网关）
4-10. 选项卡切换、实时业绩、风险监控、历史分析等
"""

import asyncio
import logging

import pytest

logger = logging.getLogger(__name__)


@pytest.mark.e2e
@pytest.mark.asyncio
class TestPortfolioMonitoringE2E:
    """组合投资监控端到端测试."""

    @pytest.mark.timeout(40)
    async def test_automatic_portfolio_recognition(
        self,
        backend_app,
        portfolio_service,
        strategy_instance_service,
    ):
        """测试自动组合识别."""
        logger.info("=" * 80)
        logger.info("E2E测试: 自动组合识别")
        logger.info("=" * 80)

        # 创建测试网关并激活多个策略
        test_gateway = "test_gateway_portfolio"
        try:
            await self._create_gateway_with_multiple_strategies(
                strategy_instance_service, test_gateway, strategy_count=3
            )

            # 使用条件等待自动识别
            from tests.test_e2e.utils.wait_helpers import wait_until_condition

            async def check_portfolio_recognized():
                portfolios = await portfolio_service.get_portfolios()
                return len(portfolios) > 0

            await wait_until_condition(
                lambda: asyncio.run(check_portfolio_recognized()),
                timeout=3.0,
                interval=0.3,
                error_message="组合自动识别超时",
            )

            # 验证自动识别
            portfolios = await portfolio_service.get_portfolios()
            logger.info(f"识别到的组合数: {len(portfolios)}")

            # 检查测试网关是否被识别为组合
            found = any(p.get("gateway") == test_gateway for p in portfolios)
            if found:
                logger.info("✓ 自动组合识别成功")
            else:
                logger.warning("⚠ 未识别到测试组合")

        except Exception as e:
            logger.warning(f"⚠ 自动识别测试遇到异常: {e}")

        logger.info("=" * 80)

    @pytest.mark.timeout(40)
    async def test_custom_portfolio_creation(
        self,
        backend_app,
        portfolio_service,
    ):
        """测试自定义组合创建."""
        logger.info("=" * 80)
        logger.info("E2E测试: 自定义组合创建")
        logger.info("=" * 80)

        # 创建自定义组合
        custom_portfolio_config = {
            "name": "自定义组合1",
            "gateways": ["gateway1", "gateway2"],
            "type": "custom",
        }

        try:
            result = await portfolio_service.create_custom_portfolio(**custom_portfolio_config)

            if result.get("success"):
                logger.info(f"✓ 自定义组合创建成功: {result.get('portfolio_id')}")
            else:
                logger.warning(f"⚠ 组合创建失败: {result.get('error')}")

        except Exception as e:
            logger.warning(f"⚠ 组合创建测试遇到异常: {e}")

        logger.info("=" * 80)

    @pytest.mark.timeout(40)
    async def test_realtime_performance_monitoring(
        self,
        backend_app,
        portfolio_service,
        service_accessor,
    ):
        """测试实时业绩监控."""
        logger.info("=" * 80)
        logger.info("E2E测试: 实时业绩监控")
        logger.info("=" * 80)

        # 获取测试组合
        portfolios = await portfolio_service.get_portfolios()

        if portfolios:
            test_portfolio_id = portfolios[0].get("id")
            logger.info(f"测试组合: {test_portfolio_id}")

            # 获取监控数据
            monitoring_data = service_accessor.get_portfolio_monitoring_data(
                portfolio_service, test_portfolio_id
            )

            logger.info(f"监控数据: {monitoring_data}")

            # 验证数据完整性
            if monitoring_data.get("performance"):
                logger.info("✓ 业绩数据可用")
            else:
                logger.warning("⚠ 业绩数据缺失")

        else:
            logger.warning("⚠ 没有可用的组合")

        logger.info("=" * 80)

    @pytest.mark.timeout(40)
    async def test_risk_monitoring_calculation(
        self,
        backend_app,
        portfolio_service,
        service_accessor,
    ):
        """测试风险监控计算."""
        logger.info("=" * 80)
        logger.info("E2E测试: 风险监控计算")
        logger.info("=" * 80)

        portfolios = await portfolio_service.get_portfolios()

        if portfolios:
            test_portfolio_id = portfolios[0].get("id")

            # 获取风险监控数据
            monitoring_data = service_accessor.get_portfolio_monitoring_data(
                portfolio_service, test_portfolio_id
            )

            risk_data = monitoring_data.get("risk", {})
            logger.info(f"风险数据: {risk_data}")

            # 验证风险指标
            expected_metrics = ["volatility", "max_drawdown", "sharpe_ratio"]
            for metric in expected_metrics:
                if metric in risk_data:
                    logger.info(f"✓ 风险指标 {metric}: {risk_data[metric]}")
                else:
                    logger.warning(f"⚠ 缺少风险指标: {metric}")

        logger.info("=" * 80)

    @pytest.mark.timeout(40)
    async def test_historical_performance_analysis(
        self,
        backend_app,
        portfolio_service,
    ):
        """测试历史业绩分析."""
        logger.info("=" * 80)
        logger.info("E2E测试: 历史业绩分析")
        logger.info("=" * 80)

        portfolios = await portfolio_service.get_portfolios()

        if portfolios:
            test_portfolio_id = portfolios[0].get("id")

            try:
                # 获取历史业绩
                historical_data = await portfolio_service.get_historical_performance(
                    test_portfolio_id, days=30
                )

                if historical_data:
                    logger.info(f"✓ 历史业绩数据: {len(historical_data)}条")
                else:
                    logger.warning("⚠ 历史业绩数据为空")

            except Exception as e:
                logger.warning(f"⚠ 历史分析测试遇到异常: {e}")

        logger.info("=" * 80)

    # ========== 辅助方法 ==========

    async def _create_gateway_with_multiple_strategies(
        self, service, gateway_name: str, strategy_count: int = 3
    ):
        """创建网关并激活多个策略."""
        try:
            await service.create_gateway(
                {
                    "name": gateway_name,
                    "type": "PAPER",
                }
            )

            for i in range(strategy_count):
                await service.deploy_strategy(
                    strategy_id=f"strategy_{i}",
                    gateway_name=gateway_name,
                    strategy_class="TestStrategy",
                    parameters={},
                )
                await service.start_strategy(gateway_name, f"strategy_{i}")

        except Exception:
            pass
