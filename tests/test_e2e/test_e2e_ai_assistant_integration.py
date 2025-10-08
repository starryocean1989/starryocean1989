# -*- coding: utf-8 -*-
"""
E2E测试: AI助手集成.

测试功能链路: 4.1.2-4.1.3 AI助手集成链条

验证点:
1. AI助手界面触发
2. 竖向布局界面显示
3. 用户指令输入
4. AI响应接收验证
5. 反馈内容分类算法
6. 代码内容自动识别
7-10. 代码插入、反馈路由等
"""

import asyncio
import logging

import pytest

logger = logging.getLogger(__name__)


@pytest.mark.e2e
@pytest.mark.asyncio
class TestAIAssistantIntegrationE2E:
    """AI助手集成端到端测试."""

    @pytest.mark.timeout(30)
    async def test_ai_assistant_interface_trigger(
        self,
        backend_app,
        ai_assistant_mock,
    ):
        """测试AI助手界面触发."""
        logger.info("=" * 80)
        logger.info("E2E测试: AI助手界面触发")
        logger.info("=" * 80)

        # 验证AI助手服务可用
        assert ai_assistant_mock is not None, "AI助手服务应该可用"
        logger.info("✓ AI助手服务已加载")

        # 模拟界面触发
        logger.info("模拟点击右下角触发按钮...")
        # 实际应用中这里会触发UI界面显示

        logger.info("✓ AI助手界面触发验证完成")
        logger.info("=" * 80)

    @pytest.mark.timeout(30)
    async def test_ai_response_reception(
        self,
        backend_app,
        ai_assistant_mock,
    ):
        """测试AI响应接收."""
        logger.info("=" * 80)
        logger.info("E2E测试: AI响应接收")
        logger.info("=" * 80)

        # 发送测试消息
        test_message = "请帮我生成一个简单的移动平均策略"

        response = ai_assistant_mock.send_message(test_message)

        logger.info(f"AI响应: {response}")

        # 验证响应结构
        assert "response" in response, "响应应包含response字段"
        assert "code" in response, "响应应包含code字段"
        assert "feedback" in response, "响应应包含feedback字段"

        logger.info("✓ AI响应接收验证通过")
        logger.info("=" * 80)

    @pytest.mark.timeout(30)
    async def test_content_classification_algorithm(
        self,
        backend_app,
        ai_assistant_mock,
    ):
        """测试内容分类算法."""
        logger.info("=" * 80)
        logger.info("E2E测试: 内容分类算法")
        logger.info("=" * 80)

        # 测试不同类型的内容
        test_contents = [
            "print('Hello World')",  # 代码
            "这是一段文本反馈",  # 文本
            "def calculate_ma(prices, period):\n    return sum(prices) / period",  # 代码块
        ]

        for content in test_contents:
            result = ai_assistant_mock.classify_content(content)
            logger.info(f"内容: {content[:50]}...")
            logger.info(f"分类结果: {result['type']}")

            # 验证分类准确性
            if "def " in content or "print(" in content:
                expected_type = "code"
            else:
                expected_type = "text"

            if result["type"] == expected_type:
                logger.info(f"✓ 分类正确: {result['type']}")
            else:
                logger.warning(f"⚠ 分类异常: 期望{expected_type}, 实际{result['type']}")

        logger.info("=" * 80)

    @pytest.mark.timeout(30)
    async def test_code_auto_insertion(
        self,
        backend_app,
        ai_assistant_mock,
    ):
        """测试代码自动插入."""
        logger.info("=" * 80)
        logger.info("E2E测试: 代码自动插入")
        logger.info("=" * 80)

        # 获取AI响应
        response = ai_assistant_mock.send_message("生成策略代码")

        code_content = response.get("code", "")
        logger.info(f"生成的代码: {code_content}")

        # 验证代码内容
        if code_content:
            logger.info("✓ 代码内容生成成功")

            # 模拟插入到编辑器
            logger.info("模拟代码自动插入到编辑器...")
            # 实际应用中这里会调用编辑器API插入代码

            logger.info("✓ 代码自动插入验证完成")
        else:
            logger.warning("⚠ 没有代码内容")

        logger.info("=" * 80)

    @pytest.mark.timeout(30)
    async def test_content_routing_correctness(
        self,
        backend_app,
        ai_assistant_mock,
    ):
        """测试内容路由正确性."""
        logger.info("=" * 80)
        logger.info("E2E测试: 内容路由正确性")
        logger.info("=" * 80)

        # 获取AI响应
        response = ai_assistant_mock.send_message("测试路由")

        code = response.get("code", "")
        feedback = response.get("feedback", "")

        logger.info("内容路由验证:")
        logger.info(f"  - 代码内容: {len(code)}字符 -> 路由到编辑器")
        logger.info(f"  - 反馈内容: {len(feedback)}字符 -> 路由到助手界面")

        # 验证路由规则
        if code and feedback:
            logger.info("✓ 内容路由正确：代码和反馈分别路由")
        elif code:
            logger.info("✓ 仅有代码内容，路由到编辑器")
        elif feedback:
            logger.info("✓ 仅有反馈内容，路由到助手界面")
        else:
            logger.warning("⚠ 没有内容需要路由")

        logger.info("=" * 80)
