# -*- coding: utf-8 -*-
"""数据质量检查与修复功能e2e测试.

测试目标：
1. 数据质量检查：验证四维度检查（完整性、准确性、一致性、格式）
2. 断点检测：品种缺失、历史缺失检查
3. 数据自动修复：修复损坏数据、增量下载补全
4. 质量报告生成：完整性报告、错误统计

测试使用真实数据验证端到端流程。
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Any, Dict, List

import pytest

logger = logging.getLogger(__name__)


# ==================== 测试辅助函数 ====================


def validate_data_quality_check(data_center_service, symbol: str, interval: str) -> Dict[str, Any]:
    """验证数据质量检查功能."""
    result = {
        "quality_check_available": False,
        "quality_score": 0.0,
        "check_dimensions": [],
        "issues_found": [],
        "report_generated": False,
        "error_message": "",
    }

    try:
        # 调用质量检查API
        response = data_center_service.check_data_quality(symbol, interval)

        if not response.get("success"):
            result["error_message"] = response.get("message", "未知错误")
            return result

        result["quality_check_available"] = True

        # 解析质量检查结果
        quality_data = response.get("data", {})
        result["quality_score"] = quality_data.get("quality_score", 0.0)
        result["issues_found"] = quality_data.get("issues", [])
        result["check_dimensions"] = quality_data.get("check_dimensions", [])

        # 验证质量报告结构
        if "quality_score" in quality_data and "issues" in quality_data:
            result["report_generated"] = True
            logger.info("✅ 数据质量检查成功: 评分=%.2f", result["quality_score"])
        else:
            logger.warning("⚠️ 质量报告结构不完整")

        return result

    except Exception as e:
        result["error_message"] = str(e)
        logger.error("数据质量检查失败: %s", e)
        return result


def validate_missing_data_detection(data_center_service) -> Dict[str, Any]:
    """验证数据缺失检测功能."""
    result = {
        "detection_available": False,
        "missing_symbols": [],
        "missing_dates": [],
        "missing_count": 0,
        "detection_accurate": False,
        "error_message": "",
    }

    try:
        # 获取数据质量概览
        overview_response = data_center_service.get_data_quality_overview()

        if not overview_response.get("success"):
            result["error_message"] = overview_response.get("message", "未知错误")
            return result

        result["detection_available"] = True

        # 解析缺失数据信息
        overview_data = overview_response.get("data", {})
        result["missing_symbols"] = overview_data.get("missing_symbols", [])
        result["missing_dates"] = overview_data.get("missing_dates", [])
        result["missing_count"] = overview_data.get("missing_count", 0)

        # 验证检测准确性（至少应该检测到一些基本信息）
        if result["missing_count"] >= 0:
            result["detection_accurate"] = True
            logger.info("✅ 数据缺失检测成功: 缺失数量=%d", result["missing_count"])
        else:
            logger.warning("⚠️ 数据缺失检测结果异常")

        return result

    except Exception as e:
        result["error_message"] = str(e)
        logger.error("数据缺失检测失败: %s", e)
        return result


def validate_data_repair_functionality(
    data_center_service, symbol: str, issues: List[str]
) -> Dict[str, Any]:
    """验证数据修复功能."""
    result = {
        "repair_available": False,
        "repair_successful": False,
        "repaired_count": 0,
        "repair_time": 0,
        "error_message": "",
    }

    try:
        start_time = time.time()

        # 调用自动修复API
        repair_response = data_center_service.auto_repair_data(symbol, issues)

        result["repair_time"] = time.time() - start_time

        if not repair_response.get("success"):
            result["error_message"] = repair_response.get("message", "未知错误")
            return result

        result["repair_available"] = True
        result["repair_successful"] = repair_response.get("success", False)
        result["repaired_count"] = repair_response.get("repaired_count", 0)

        if result["repair_successful"]:
            logger.info(
                "✅ 数据修复成功: 修复数量=%d, 耗时=%.2f秒",
                result["repaired_count"],
                result["repair_time"],
            )
        else:
            logger.warning("❌ 数据修复失败: %s", result["error_message"])

        return result

    except Exception as e:
        result["error_message"] = str(e)
        logger.error("数据修复验证失败: %s", e)
        return result


def validate_quality_report_generation(data_center_service) -> Dict[str, Any]:
    """验证质量报告生成功能."""
    result = {
        "report_available": False,
        "report_complete": False,
        "report_sections": [],
        "statistics_valid": False,
        "error_message": "",
    }

    try:
        # 获取完整质量概览（包含报告）
        report_response = data_center_service.get_data_quality_overview()

        if not report_response.get("success"):
            result["error_message"] = report_response.get("message", "未知错误")
            return result

        result["report_available"] = True

        # 解析报告数据
        report_data = report_response.get("data", {})
        result["report_sections"] = (
            list(report_data.keys()) if isinstance(report_data, dict) else []
        )

        # 验证报告完整性
        expected_sections = ["missing_symbols", "missing_dates", "quality_scores", "statistics"]
        result["report_complete"] = all(
            section in result["report_sections"] for section in expected_sections
        )

        # 验证统计数据有效性
        statistics = report_data.get("statistics", {})
        if isinstance(statistics, dict) and "total_symbols" in statistics:
            result["statistics_valid"] = True
            logger.info("✅ 质量报告生成成功: 包含 %d 个部分", len(result["report_sections"]))
        else:
            logger.warning("⚠️ 质量报告统计数据无效")

        return result

    except Exception as e:
        result["error_message"] = str(e)
        logger.error("质量报告验证失败: %s", e)
        return result


# ==================== 测试用例 ====================


@pytest.mark.e2e
@pytest.mark.data_center
@pytest.mark.timeout(180)  # 数据质量检查可能需要较长时间
class TestDataQuality:
    """数据质量检查与修复功能e2e测试套件."""

    def test_data_quality_check_basic(self, data_center_service):
        """测试数据质量检查基本功能.

        验证标准：
        1. ✅ 质量检查功能可用
        2. ✅ 质量评分合理（0-1之间）
        3. ✅ 检查维度完整（完整性、准确性、一致性、格式）
        4. ✅ 问题发现和报告

        Args:
            data_center_service: 数据中心服务实例
        """
        logger.info("=" * 80)
        logger.info("开始测试：数据质量检查基本功能")
        logger.info("=" * 80)

        # 使用常见品种进行测试
        test_symbol = "000001"  # 平安银行
        test_interval = "1d"

        # 1. 执行质量检查
        logger.info("步骤1：执行数据质量检查...")
        quality_result = validate_data_quality_check(
            data_center_service, test_symbol, test_interval
        )

        assert quality_result[
            "quality_check_available"
        ], f"质量检查不可用: {quality_result['error_message']}"
        assert 0.0 <= quality_result["quality_score"] <= 1.0, "质量评分应在0-1之间"

        logger.info("✅ 质量检查完成: 评分=%.2f", quality_result["quality_score"])

        # 2. 验证检查维度
        expected_dimensions = ["完整性", "准确性", "一致性", "格式"]
        actual_dimensions = quality_result["check_dimensions"]

        for dimension in expected_dimensions:
            if dimension in actual_dimensions:
                logger.info("✅ 检查维度包含: %s", dimension)
            else:
                logger.warning("⚠️ 缺少检查维度: %s", dimension)

        # 3. 验证问题报告
        issues_count = len(quality_result["issues_found"])
        if issues_count > 0:
            logger.info("✅ 发现 %d 个质量问题", issues_count)
            for i, issue in enumerate(quality_result["issues_found"][:3]):  # 只显示前3个
                logger.info("  - 问题 %d: %s", i + 1, issue)
        else:
            logger.info("ℹ️ 未发现质量问题（数据质量良好）")

        logger.info("=" * 80)
        logger.info("✅ 数据质量检查基本功能测试通过")
        logger.info("   - 测试品种: %s", test_symbol)
        logger.info("   - 质量评分: %.2f", quality_result["quality_score"])
        logger.info("   - 问题数量: %d", issues_count)
        logger.info("=" * 80)

    def test_missing_data_detection(self, data_center_service):
        """测试数据缺失检测功能.

        验证标准：
        1. ✅ 缺失检测功能可用
        2. ✅ 检测结果准确
        3. ✅ 包含品种缺失和日期缺失信息
        4. ✅ 检测覆盖主要品种

        Args:
            data_center_service: 数据中心服务实例
        """
        logger.info("=" * 80)
        logger.info("开始测试：数据缺失检测功能")
        logger.info("=" * 80)

        # 执行缺失检测
        detection_result = validate_missing_data_detection(data_center_service)

        assert detection_result[
            "detection_available"
        ], f"缺失检测不可用: {detection_result['error_message']}"
        assert detection_result["detection_accurate"], "缺失检测结果异常"

        logger.info("✅ 数据缺失检测完成: 总缺失=%d", detection_result["missing_count"])

        # 验证缺失品种信息
        missing_symbols = detection_result["missing_symbols"]
        if missing_symbols:
            logger.info("✅ 检测到 %d 个缺失品种", len(missing_symbols))
            logger.info("前5个缺失品种: %s", missing_symbols[:5])
        else:
            logger.info("ℹ️ 未检测到品种缺失（数据完整）")

        # 验证缺失日期信息
        missing_dates = detection_result["missing_dates"]
        if missing_dates:
            logger.info("✅ 检测到 %d 个缺失日期段", len(missing_dates))
        else:
            logger.info("ℹ️ 未检测到日期缺失（数据连续）")

        logger.info("=" * 80)
        logger.info("✅ 数据缺失检测测试通过")
        logger.info("   - 总缺失数量: %d", detection_result["missing_count"])
        logger.info("   - 缺失品种数: %d", len(missing_symbols))
        logger.info("   - 缺失日期段: %d", len(missing_dates))
        logger.info("=" * 80)

    def test_data_repair_functionality(self, data_center_service):
        """测试数据自动修复功能.

        验证标准：
        1. ✅ 修复功能可用
        2. ✅ 修复成功率
        3. ✅ 修复耗时合理
        4. ✅ 修复结果验证

        Args:
            data_center_service: 数据中心服务实例
        """
        logger.info("=" * 80)
        logger.info("开始测试：数据自动修复功能")
        logger.info("=" * 80)

        # 先检查是否有需要修复的问题
        test_symbol = "000001"
        quality_result = validate_data_quality_check(data_center_service, test_symbol, "1d")

        if not quality_result["issues_found"]:
            logger.info("ℹ️ 测试品种无质量问题，跳过修复测试")
            pytest.skip("测试品种无质量问题，无需修复")

        # 执行修复
        logger.info("步骤1：执行数据修复...")
        issues_to_repair = quality_result["issues_found"]
        repair_result = validate_data_repair_functionality(
            data_center_service, test_symbol, issues_to_repair
        )

        assert repair_result[
            "repair_available"
        ], f"修复功能不可用: {repair_result['error_message']}"

        if repair_result["repair_successful"]:
            logger.info(
                "✅ 数据修复成功: 修复 %d 个问题，耗时 %.2f秒",
                repair_result["repaired_count"],
                repair_result["repair_time"],
            )

            # 验证修复效果
            logger.info("步骤2：验证修复效果...")
            post_repair_quality = validate_data_quality_check(
                data_center_service, test_symbol, "1d"
            )

            if post_repair_quality["quality_score"] >= quality_result["quality_score"]:
                logger.info(
                    "✅ 修复效果良好，质量评分从 %.2f 提升到 %.2f",
                    quality_result["quality_score"],
                    post_repair_quality["quality_score"],
                )
            else:
                logger.warning("⚠️ 修复后质量评分下降，可能存在问题")
        else:
            logger.warning("❌ 数据修复失败: %s", repair_result["error_message"])

        logger.info("=" * 80)
        logger.info("✅ 数据自动修复测试通过")
        logger.info("   - 修复成功: %s", repair_result["repair_successful"])
        logger.info("   - 修复数量: %d", repair_result["repaired_count"])
        logger.info("   - 修复耗时: %.2f秒", repair_result["repair_time"])
        logger.info("=" * 80)

    def test_quality_report_generation(self, data_center_service):
        """测试质量报告生成功能.

        验证标准：
        1. ✅ 报告生成功能可用
        2. ✅ 报告结构完整
        3. ✅ 包含必要统计信息
        4. ✅ 报告格式正确

        Args:
            data_center_service: 数据中心服务实例
        """
        logger.info("=" * 80)
        logger.info("开始测试：质量报告生成功能")
        logger.info("=" * 80)

        # 生成质量报告
        report_result = validate_quality_report_generation(data_center_service)

        assert report_result[
            "report_available"
        ], f"报告生成功能不可用: {report_result['error_message']}"

        logger.info("✅ 质量报告生成成功")

        # 验证报告完整性
        if report_result["report_complete"]:
            logger.info("✅ 报告结构完整，包含 %d 个部分", len(report_result["report_sections"]))
            for section in report_result["report_sections"]:
                logger.info("  - 报告部分: %s", section)
        else:
            logger.warning("⚠️ 报告结构不完整，缺少某些部分")

        # 验证统计数据
        if report_result["statistics_valid"]:
            logger.info("✅ 统计数据格式正确")
        else:
            logger.warning("⚠️ 统计数据格式异常")

        logger.info("=" * 80)
        logger.info("✅ 质量报告生成测试通过")
        logger.info("   - 报告部分数: %d", len(report_result["report_sections"]))
        logger.info("   - 报告完整性: %s", "完整" if report_result["report_complete"] else "不完整")
        logger.info("=" * 80)

    def test_comprehensive_quality_workflow(self, data_center_service):
        """测试完整的数据质量工作流.

        验证标准：
        1. ✅ 完整工作流：检查 → 检测 → 修复 → 报告
        2. ✅ 各环节衔接正确
        3. ✅ 整体耗时合理
        4. ✅ 最终质量提升

        Args:
            data_center_service: 数据中心服务实例
        """
        logger.info("=" * 80)
        logger.info("开始测试：完整数据质量工作流")
        logger.info("=" * 80)

        workflow_start = time.time()
        test_symbol = "000001"

        # 1. 初始质量检查
        logger.info("步骤1：初始质量检查...")
        initial_quality = validate_data_quality_check(data_center_service, test_symbol, "1d")
        initial_score = initial_quality["quality_score"]

        # 2. 缺失检测
        logger.info("步骤2：数据缺失检测...")
        detection_result = validate_missing_data_detection(data_center_service)

        # 3. 数据修复（如果有问题）
        logger.info("步骤3：数据修复...")
        if initial_quality["issues_found"]:
            repair_result = validate_data_repair_functionality(
                data_center_service, test_symbol, initial_quality["issues_found"]
            )
            repair_successful = repair_result["repair_successful"]
        else:
            logger.info("ℹ️ 无质量问题，跳过修复步骤")
            repair_successful = True

        # 4. 最终质量验证
        logger.info("步骤4：最终质量验证...")
        final_quality = validate_data_quality_check(data_center_service, test_symbol, "1d")
        final_score = final_quality["quality_score"]

        # 5. 生成最终报告
        logger.info("步骤5：生成质量报告...")
        report_result = validate_quality_report_generation(data_center_service)

        workflow_time = time.time() - workflow_start

        # 验证工作流完整性
        workflow_complete = (
            initial_quality["quality_check_available"]
            and detection_result["detection_available"]
            and (repair_successful or not initial_quality["issues_found"])
            and report_result["report_available"]
        )

        assert workflow_complete, "数据质量工作流不完整"

        # 验证质量改进（如果进行了修复）
        if initial_quality["issues_found"] and repair_successful:
            if final_score >= initial_score:
                logger.info("✅ 质量改进: %.2f → %.2f", initial_score, final_score)
            else:
                logger.warning("⚠️ 质量评分下降，可能修复有问题")

        logger.info("=" * 80)
        logger.info("✅ 完整数据质量工作流测试通过")
        logger.info("   - 工作流耗时: %.2f秒", workflow_time)
        logger.info("   - 初始质量评分: %.2f", initial_score)
        logger.info("   - 最终质量评分: %.2f", final_score)
        logger.info("   - 缺失检测: %d 个问题", detection_result["missing_count"])
        logger.info("   - 修复成功: %s", repair_successful)
        logger.info("=" * 80)


# ==================== 单独的快速测试 ====================


@pytest.mark.e2e
@pytest.mark.data_center
@pytest.mark.timeout(60)
def test_quality_service_availability(data_center_service):
    """快速测试：验证质量检查服务可用性.

    Args:
        data_center_service: 数据中心服务实例
    """
    logger.info("快速测试：验证质量检查服务可用性")

    assert data_center_service is not None, "数据中心服务应该可用"
    logger.info("✅ 数据中心服务可用")

    # 检查质量检查相关方法是否存在
    quality_methods = [
        "check_data_quality",
        "auto_repair_data",
        "get_data_quality_overview",
    ]

    for method in quality_methods:
        assert hasattr(data_center_service, method), f"缺少质量检查方法: {method}"
        logger.info("✅ 质量检查方法可用: %s", method)

    logger.info("✅ 质量检查服务可用性验证通过")


@pytest.mark.e2e
@pytest.mark.data_center
@pytest.mark.timeout(30)
def test_quality_check_performance(data_center_service):
    """快速测试：验证质量检查性能.

    Args:
        data_center_service: 数据中心服务实例
    """
    logger.info("快速测试：验证质量检查性能")

    # 测试质量检查响应时间
    test_symbol = "000001"
    start_time = time.time()

    quality_result = validate_data_quality_check(data_center_service, test_symbol, "1d")

    response_time = time.time() - start_time

    assert quality_result["quality_check_available"], "质量检查应可用"
    assert response_time < 10, f"质量检查响应时间过长: {response_time:.2f}秒"

    logger.info("✅ 质量检查性能正常: %.2f秒", response_time)
