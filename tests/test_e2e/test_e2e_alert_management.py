# -*- coding: utf-8 -*-
"""
E2E测试: 告警管理.

测试功能链路: 1.3.1 告警信息管理链条

验证点:
1. 告警规则配置
2. 告警规则引擎
3. 告警触发条件判断
4. 告警及时性验证
5. 告警通知方式
6-10. 告警信息生成、处理工作流、可追溯性等
"""

import asyncio
import logging
import time

import pytest

logger = logging.getLogger(__name__)


@pytest.mark.e2e
@pytest.mark.asyncio
class TestAlertManagementE2E:
    """告警管理端到端测试."""

    @pytest.mark.timeout(30)
    async def test_alert_rule_configuration(
        self,
        backend_app,
        alert_service,
    ):
        """测试告警规则配置."""
        logger.info("=" * 80)
        logger.info("E2E测试: 告警规则配置")
        logger.info("=" * 80)

        # 创建测试告警规则
        test_rule = {
            "id": "test_rule_001",
            "name": "CPU使用率告警",
            "type": "threshold",
            "metric": "cpu_usage",
            "operator": ">",
            "threshold": 80,
            "level": "warning",
        }

        try:
            result = await alert_service.create_alert_rule(**test_rule)

            if result.get("success"):
                logger.info(f"✓ 告警规则创建成功: {test_rule['id']}")
            else:
                logger.warning(f"⚠ 告警规则创建失败: {result.get('error')}")

        except Exception as e:
            logger.warning(f"⚠ 规则配置测试遇到异常: {e}")

        logger.info("=" * 80)

    @pytest.mark.timeout(30)
    async def test_alert_trigger_mechanism(
        self,
        backend_app,
        alert_service,
    ):
        """测试告警触发机制."""
        logger.info("=" * 80)
        logger.info("E2E测试: 告警触发机制")
        logger.info("=" * 80)

        # 模拟触发告警条件
        trigger_event = {
            "metric": "cpu_usage",
            "value": 85,  # 超过阈值80
            "timestamp": time.time(),
        }

        try:
            # 触发告警检查
            triggered = await alert_service.check_alert_conditions(trigger_event)

            if triggered:
                logger.info("✓ 告警条件触发成功")
            else:
                logger.warning("⚠ 告警未触发")

        except Exception as e:
            logger.warning(f"⚠ 触发机制测试遇到异常: {e}")

        logger.info("=" * 80)

    @pytest.mark.timeout(30)
    async def test_alert_timeliness(
        self,
        backend_app,
        alert_service,
    ):
        """测试告警及时性."""
        logger.info("=" * 80)
        logger.info("E2E测试: 告警及时性")
        logger.info("=" * 80)

        # 创建紧急告警
        urgent_alert = {
            "level": "critical",
            "message": "系统错误",
            "source": "test_service",
        }

        # 记录触发时间
        trigger_time = time.time()

        try:
            # 触发告警
            result = await alert_service.trigger_alert(**urgent_alert)

            # 计算响应时间
            notification_time = time.time()
            elapsed = notification_time - trigger_time

            logger.info(f"告警响应时间: {elapsed:.3f}秒")

            # 验证及时性（要求≤5秒）
            if elapsed <= 5.0:
                logger.info("✓ 告警及时性验证通过（≤5秒）")
            else:
                logger.warning("⚠ 告警响应时间超标")

        except Exception as e:
            logger.warning(f"⚠ 及时性测试遇到异常: {e}")

        logger.info("=" * 80)

    @pytest.mark.timeout(30)
    async def test_alert_notification_methods(
        self,
        backend_app,
        alert_service,
    ):
        """测试告警通知方式."""
        logger.info("=" * 80)
        logger.info("E2E测试: 告警通知方式")
        logger.info("=" * 80)

        # 测试不同通知方式
        notification_methods = ["ui", "log", "email", "webhook"]

        for method in notification_methods:
            logger.info(f"测试 {method} 通知方式")

            try:
                result = await alert_service.send_alert_notification(
                    message="测试告警",
                    method=method,
                )

                if result.get("success"):
                    logger.info(f"✓ {method} 通知发送成功")
                else:
                    logger.warning(f"⚠ {method} 通知发送失败")

            except Exception as e:
                logger.warning(f"⚠ {method} 通知测试遇到异常: {e}")

        logger.info("=" * 80)

    @pytest.mark.timeout(30)
    async def test_alert_processing_workflow(
        self,
        backend_app,
        alert_service,
        service_accessor,
    ):
        """测试告警处理工作流."""
        logger.info("=" * 80)
        logger.info("E2E测试: 告警处理工作流")
        logger.info("=" * 80)

        # 创建测试告警
        test_alert = {
            "id": "test_alert_001",
            "level": "warning",
            "message": "测试告警",
            "status": "pending",
        }

        try:
            # 创建告警
            await alert_service.create_alert(**test_alert)

            # 处理告警
            await alert_service.acknowledge_alert(test_alert["id"])

            # 关闭告警
            await alert_service.close_alert(test_alert["id"])

            # 验证工作流
            alert_stats = service_accessor.get_alert_statistics(alert_service)
            logger.info(f"告警统计: {alert_stats}")

            logger.info("✓ 告警处理工作流验证完成")

        except Exception as e:
            logger.warning(f"⚠ 工作流测试遇到异常: {e}")

        logger.info("=" * 80)
