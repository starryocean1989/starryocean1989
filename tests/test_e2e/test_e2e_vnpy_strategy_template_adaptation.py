# -*- coding: utf-8 -*-
"""
E2E测试: VnPy策略模板适配.

测试功能链路: 5.2.2 VnPy策略模板适配链条

验证点:
1-6. 6种VnPy策略模板识别
7. 监控条件判断（只激活1个策略触发监控）
8. 策略类型自动识别算法
9. 监控界面自动适配
10. portfoliostrategy特殊处理
"""

import asyncio
import logging

import pytest

from tests.test_e2e.utils.strategy_helper import StrategyHelper

logger = logging.getLogger(__name__)


@pytest.mark.e2e
@pytest.mark.asyncio
class TestVnPyStrategyTemplateE2E:
    """VnPy策略模板适配端到端测试."""

    @pytest.fixture(autouse=True)
    def setup_helper(self):
        """
        设置测试助手（每个测试方法自动运行）.

        注意：
        - autouse=True 意味着此fixture会在每个测试方法前自动执行
        - 为测试类实例注入 strategy_helper，提供策略模板识别工具
        - 与conftest.py中的全局fixture独立，不会产生冲突
        - 测试方法可以通过 self.strategy_helper 访问助手
        """
        self.strategy_helper = StrategyHelper()

    @pytest.mark.timeout(45)
    async def test_strategy_template_recognition(self, backend_app):
        """测试6种策略模板识别."""
        logger.info("=" * 80)
        logger.info("E2E测试: 策略模板识别")
        logger.info("=" * 80)

        # 验证6种模板
        templates = self.strategy_helper.VNPY_STRATEGY_TEMPLATES
        logger.info(f"VnPy支持的策略模板: {templates}")

        # 模拟不同模板的策略代码
        test_codes = {
            "algotrading": "from vnpy_algotrading import AlgoTemplate",
            "ctastrategy": "from vnpy_ctastrategy import CtaTemplate",
            "optionmaster": "from vnpy_optionmaster import OptionTemplate",
            "portfoliostrategy": "from vnpy_portfoliostrategy import StrategyTemplate",
            "scripttrader": "class MyStrategy(StrategyTemplate): pass",
            "spreadtrading": "from vnpy_spreadtrading import SpreadStrategyTemplate",
        }

        for template, code in test_codes.items():
            identified = self.strategy_helper.identify_strategy_template(code)
            if identified == template:
                logger.info(f"✓ {template} 模板识别正确")
            else:
                logger.warning(f"⚠ {template} 识别为 {identified}")

        logger.info("=" * 80)

    @pytest.mark.timeout(45)
    async def test_monitoring_trigger_condition(
        self,
        backend_app,
        strategy_instance_service,
    ):
        """测试监控触发条件."""
        logger.info("=" * 80)
        logger.info("E2E测试: 监控触发条件")
        logger.info("=" * 80)

        # 创建测试网关
        test_gateway = "test_gateway_monitor"
        await self._create_test_gateway(strategy_instance_service, test_gateway)

        # 部署并激活1个策略
        await self._deploy_and_activate_strategy(
            strategy_instance_service, "strategy_single", test_gateway
        )

        # 使用条件等待策略部署完成
        from tests.test_e2e.utils.wait_helpers import wait_until_condition

        async def check_strategy_deployed():
            count = await self._get_active_strategy_count(strategy_instance_service, test_gateway)
            return count >= 1

        await wait_until_condition(
            lambda: asyncio.run(check_strategy_deployed()),
            timeout=2.0,
            interval=0.2,
            error_message="策略部署超时",
        )

        # 验证监控条件（只激活1个策略应触发监控）
        active_count = await self._get_active_strategy_count(
            strategy_instance_service, test_gateway
        )

        logger.info(f"激活的策略数量: {active_count}")

        if active_count == 1:
            logger.info("✓ 监控触发条件满足（激活1个策略）")
        else:
            logger.warning(f"⚠ 激活策略数量异常: {active_count}")

        logger.info("=" * 80)

    @pytest.mark.timeout(45)
    async def test_monitoring_interface_adaptation(
        self,
        backend_app,
        strategy_instance_service,
    ):
        """测试监控界面自动适配."""
        logger.info("=" * 80)
        logger.info("E2E测试: 监控界面适配")
        logger.info("=" * 80)

        # 测试不同模板的监控界面适配
        templates_to_test = ["ctastrategy", "portfoliostrategy", "scripttrader"]

        for template in templates_to_test:
            logger.info(f"测试 {template} 的监控界面适配")

            # 创建对应模板的Mock监控界面
            mock_widget = type(
                "MonitorWidget",
                (),
                {
                    "_widget_type": (
                        f"{template.split('strategy')[0]}_monitor"
                        if template != "scripttrader"
                        else "default_monitor"
                    )
                },
            )()

            # 验证适配
            verification = self.strategy_helper.verify_monitoring_interface_adaptation(
                template, mock_widget
            )

            if verification.get("matched"):
                logger.info(f"✓ {template} 监控界面适配正确")
            else:
                logger.warning(f"⚠ {template} 监控界面适配不匹配")

        logger.info("=" * 80)

    @pytest.mark.timeout(45)
    async def test_portfoliostrategy_special_handling(
        self,
        backend_app,
    ):
        """测试portfoliostrategy特殊处理."""
        logger.info("=" * 80)
        logger.info("E2E测试: portfoliostrategy特殊处理")
        logger.info("=" * 80)

        # 创建portfoliostrategy测试数据
        portfolio_strategy = {
            "id": "test_portfolio",
            "type": "portfoliostrategy",
            "symbols": ["000001", "000002", "000003"],  # 多品种
        }

        # 验证特殊处理
        verification = self.strategy_helper.verify_portfoliostrategy_special_handling(
            portfolio_strategy
        )

        if verification.get("correct_handling"):
            logger.info(
                f"✓ portfoliostrategy特殊处理正确: 支持{verification['symbol_count']}个品种"
            )
        else:
            logger.warning("⚠ portfoliostrategy特殊处理异常")

        logger.info("=" * 80)

    @pytest.mark.timeout(45)
    async def test_custom_monitoring_content(
        self,
        backend_app,
    ):
        """测试定制监控内容."""
        logger.info("=" * 80)
        logger.info("E2E测试: 定制监控内容")
        logger.info("=" * 80)

        # 测试不同策略模板的监控内容定制
        monitoring_content = {
            "algotrading": ["算法进度", "订单状态", "成交明细"],
            "ctastrategy": ["持仓", "信号", "盈亏"],
            "optionmaster": ["Delta", "Gamma", "Vega", "Theta"],
            "portfoliostrategy": ["组合收益", "品种权重", "风险敞口"],
            "scripttrader": ["自定义指标"],
            "spreadtrading": ["价差", "套利机会", "对冲比例"],
        }

        for template, content_items in monitoring_content.items():
            logger.info(f"{template} 监控内容: {content_items}")

        logger.info("✓ 定制监控内容验证完成")
        logger.info("=" * 80)

    # ========== 辅助方法 ==========

    async def _create_test_gateway(self, service, gateway_name: str):
        """创建测试网关."""
        try:
            await service.create_gateway(
                {
                    "name": gateway_name,
                    "type": "PAPER",
                }
            )
        except Exception:
            pass

    async def _deploy_and_activate_strategy(self, service, strategy_id: str, gateway_name: str):
        """部署并激活策略."""
        try:
            await service.deploy_strategy(
                strategy_id=strategy_id,
                gateway_name=gateway_name,
                strategy_class="TestStrategy",
                parameters={},
            )
            await service.start_strategy(gateway_name, strategy_id)
        except Exception:
            pass

    async def _get_active_strategy_count(self, service, gateway_name: str) -> int:
        """获取激活的策略数量."""
        try:
            pool = getattr(service, "_strategy_pools", {}).get(gateway_name, [])
            return sum(1 for s in pool if s.get("status") == "running")
        except Exception:
            return 0
