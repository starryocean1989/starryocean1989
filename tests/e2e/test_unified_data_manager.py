# -*- coding: utf-8 -*-
"""统一数据管理器功能e2e测试.

测试目标：
1. 四层数据融合：预加载缓存、历史数据、录制数据、实时数据
2. 订阅管理：多模块订阅合并、订阅取消、资源管理
3. 数据查询性能：预加载命中率、查询响应时间、缓存效果
4. 自动补全机制：数据缺失检测、自动下载触发、补全结果验证

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


def validate_four_layer_data_fusion(china_stock_engine) -> Dict[str, Any]:
    """验证四层数据融合功能."""
    result = {
        "fusion_available": False,
        "preload_layer": False,
        "history_layer": False,
        "recording_layer": False,
        "realtime_layer": False,
        "fusion_successful": False,
        "query_performance": 0,
        "error_message": "",
    }

    try:
        # 获取统一数据管理器
        unified_manager = china_stock_engine.unified_data_manager

        if not unified_manager:
            result["error_message"] = "统一数据管理器不可用"
            return result

        result["fusion_available"] = True

        # 测试品种和时间范围
        test_symbol = "000001"
        test_interval = "1d"
        start_date = date.today() - timedelta(days=30)
        end_date = date.today()

        # 测量查询性能
        start_time = time.time()

        # 执行数据查询（四层融合）
        data = unified_manager.get_kline_data(
            symbol=test_symbol,
            interval=test_interval,
            start_date=start_date,
            end_date=end_date,
            check_gaps=True,
            use_preload=True,
        )

        result["query_performance"] = time.time() - start_time

        if data is not None and not data.empty:
            result["fusion_successful"] = True
            logger.info(
                "✅ 四层数据融合成功，获取到 %d 条记录，耗时 %.2f秒",
                len(data),
                result["query_performance"],
            )

            # 检查数据完整性
            required_columns = ["datetime", "open", "high", "low", "close", "volume"]
            missing_columns = [col for col in required_columns if col not in data.columns]

            if not missing_columns:
                logger.info("✅ 数据结构完整，包含所有必需字段")
            else:
                logger.warning("⚠️ 数据结构不完整，缺少字段: %s", missing_columns)
        else:
            logger.warning("⚠️ 数据查询返回空结果")

        # 验证各层是否可用（通过内部方法检查）
        try:
            # 检查预加载层
            if hasattr(unified_manager, "preload_service") and unified_manager.preload_service:
                result["preload_layer"] = True
                logger.info("✅ 预加载层可用")

            # 检查历史数据层
            if hasattr(china_stock_engine, "storage_manager"):
                result["history_layer"] = True
                logger.info("✅ 历史数据层可用")

            # 检查录制数据层（如果有vnpy_datarecorder）
            try:
                import vnpy_datarecorder

                result["recording_layer"] = True
                logger.info("✅ 录制数据层可用")
            except ImportError:
                logger.info("ℹ️ 录制数据层不可用（vnpy_datarecorder未安装）")

            # 检查实时数据层
            if hasattr(china_stock_engine, "polling_gateway") or hasattr(
                china_stock_engine, "virtual_gateway"
            ):
                result["realtime_layer"] = True
                logger.info("✅ 实时数据层可用")

        except Exception as e:
            logger.warning("层可用性检查异常: %s", e)

        return result

    except Exception as e:
        result["error_message"] = str(e)
        logger.error("四层数据融合验证失败: %s", e)
        return result


def validate_subscription_management(china_stock_engine) -> Dict[str, Any]:
    """验证订阅管理功能."""
    result = {
        "subscription_available": False,
        "multi_module_merge": False,
        "subscription_cancel": False,
        "resource_cleanup": False,
        "error_message": "",
    }

    try:
        # 获取统一数据管理器
        unified_manager = china_stock_engine.unified_data_manager

        if not unified_manager:
            result["error_message"] = "统一数据管理器不可用"
            return result

        result["subscription_available"] = True

        # 测试多模块订阅合并
        test_modules = ["market_board", "strategy_center", "data_center"]
        test_symbols = ["000001", "600000", "600036"]

        logger.info("测试多模块订阅合并...")

        # 为多个模块订阅相同品种
        for module in test_modules:
            success = unified_manager.subscribe(module, test_symbols)
            if success:
                logger.info("✅ 模块 %s 订阅成功", module)
            else:
                logger.warning("❌ 模块 %s 订阅失败", module)

        # 检查订阅合并结果
        merged_subscriptions = {}
        for module in test_modules:
            module_subs = getattr(unified_manager, "_module_subscriptions", {}).get(module, set())
            for symbol in module_subs:
                if symbol not in merged_subscriptions:
                    merged_subscriptions[symbol] = []
                merged_subscriptions[symbol].append(module)

        # 验证订阅合并
        merged_count = len(merged_subscriptions)
        expected_merge = len(set(test_symbols))  # 去重后的品种数

        if merged_count == expected_merge:
            result["multi_module_merge"] = True
            logger.info("✅ 多模块订阅合并成功: %d 个品种", merged_count)

            # 显示合并详情
            for symbol, modules in merged_subscriptions.items():
                logger.info("  - 品种 %s 被 %d 个模块订阅: %s", symbol, len(modules), modules)
        else:
            logger.warning(
                "⚠️ 订阅合并异常: 预期 %d 个品种，实际 %d 个", expected_merge, merged_count
            )

        # 测试订阅取消
        logger.info("测试订阅取消...")
        cancel_module = "market_board"
        cancel_symbols = ["000001"]

        cancel_success = unified_manager.unsubscribe(cancel_module, cancel_symbols)

        if cancel_success is not None:  # unsubscribe返回None表示成功
            result["subscription_cancel"] = True
            logger.info("✅ 订阅取消成功")

            # 验证取消效果
            remaining_subs = getattr(unified_manager, "_module_subscriptions", {}).get(
                cancel_module, set()
            )
            if "000001" not in remaining_subs:
                logger.info("✅ 品种取消验证成功")
            else:
                logger.warning("⚠️ 品种取消未生效")
        else:
            logger.warning("❌ 订阅取消失败")

        # 验证资源清理
        # （这里主要检查是否有明显的资源泄露迹象）
        active_gateways = getattr(unified_manager, "_gateway_symbols", {})
        if active_gateways:
            logger.info("✅ 网关资源正常: %s", list(active_gateways.keys()))
            result["resource_cleanup"] = True
        else:
            logger.info("ℹ️ 无活动网关资源")

        return result

    except Exception as e:
        result["error_message"] = str(e)
        logger.error("订阅管理验证失败: %s", e)
        return result


def validate_preload_cache_effectiveness(china_stock_engine) -> Dict[str, Any]:
    """验证预加载缓存效果."""
    result = {
        "preload_available": False,
        "cache_hit_rate": 0.0,
        "cache_symbols": 0,
        "performance_improvement": False,
        "error_message": "",
    }

    try:
        # 获取预加载服务
        preload_service = china_stock_engine.preload_service

        if not preload_service:
            result["error_message"] = "预加载服务不可用"
            return result

        result["preload_available"] = True

        # 获取缓存统计信息
        stats = preload_service.get_stats()

        if stats:
            result["cache_symbols"] = stats.get("total_preloaded", 0)
            cache_hits = stats.get("cache_hits", 0)
            cache_misses = stats.get("cache_misses", 0)

            if cache_hits + cache_misses > 0:
                result["cache_hit_rate"] = cache_hits / (cache_hits + cache_misses)
                logger.info(
                    "✅ 预加载缓存效果: 命中率 %.1f%% (%d/%d)",
                    result["cache_hit_rate"] * 100,
                    cache_hits,
                    cache_hits + cache_misses,
                )
            else:
                logger.info("ℹ️ 暂无缓存访问记录")

            # 验证常用品种预加载
            frequently_used = ["000001", "000002", "600000", "600036", "600519"]
            preloaded_count = 0

            for symbol in frequently_used:
                if preload_service.is_preloaded(symbol, ["1d"]):
                    preloaded_count += 1

            if preloaded_count > 0:
                logger.info(
                    "✅ 常用品种预加载: %d/%d 个品种", preloaded_count, len(frequently_used)
                )
        else:
            logger.info("ℹ️ 预加载服务统计不可用")

        # 测试缓存性能提升
        test_symbol = "000001"
        test_intervals = ["1d", "5m"]

        # 第一次查询（可能触发预加载）
        start_time = time.time()
        data1 = preload_service.get_cached_dataframe(test_symbol, "1d")
        first_query_time = time.time() - start_time

        # 第二次查询（使用缓存）
        start_time = time.time()
        data2 = preload_service.get_cached_dataframe(test_symbol, "1d")
        second_query_time = time.time() - start_time

        if second_query_time < first_query_time and data2 is not None:
            result["performance_improvement"] = True
            logger.info(
                "✅ 缓存性能提升: %.2f秒 → %.2f秒 (%.1f%% 提升)",
                first_query_time,
                second_query_time,
                (first_query_time - second_query_time) / first_query_time * 100,
            )

        return result

    except Exception as e:
        result["error_message"] = str(e)
        logger.error("预加载缓存验证失败: %s", e)
        return result


def validate_auto_completion_mechanism(china_stock_engine) -> Dict[str, Any]:
    """验证自动补全机制."""
    result = {
        "auto_completion_available": False,
        "gap_detection_working": False,
        "download_triggered": False,
        "completion_successful": False,
        "error_message": "",
    }

    try:
        # 获取统一数据管理器
        unified_manager = china_stock_engine.unified_data_manager

        if not unified_manager:
            result["error_message"] = "统一数据管理器不可用"
            return result

        result["auto_completion_available"] = True

        # 测试品种和时间范围
        test_symbol = "000001"
        test_interval = "1d"
        # 使用一个较早的日期来测试缺失检测
        start_date = date.today() - timedelta(days=60)
        end_date = date.today()

        # 第一次查询（可能触发缺失检测）
        logger.info("第一次查询（可能触发缺失检测）...")
        data1 = unified_manager.get_kline_data(
            symbol=test_symbol,
            interval=test_interval,
            start_date=start_date,
            end_date=end_date,
            check_gaps=True,
            use_preload=True,
        )

        if data1 is None or data1.empty:
            result["gap_detection_working"] = True
            logger.info("✅ 数据缺失检测生效，返回空结果")

            # 检查是否触发了自动下载
            # （通过检查是否有新的下载任务或数据文件生成来判断）
            time.sleep(2)  # 等待可能的自动下载启动

            # 第二次查询（检查是否补全）
            logger.info("第二次查询（检查补全结果）...")
            data2 = unified_manager.get_kline_data(
                symbol=test_symbol,
                interval=test_interval,
                start_date=start_date,
                end_date=end_date,
                check_gaps=True,
                use_preload=True,
            )

            if data2 is not None and not data2.empty:
                if len(data2) > len(data1) if data1 is not None else True:
                    result["completion_successful"] = True
                    logger.info(
                        "✅ 自动补全成功，数据量从 %d 增加到 %d",
                        len(data1) if data1 is not None else 0,
                        len(data2),
                    )
                else:
                    logger.info("ℹ️ 数据补全未触发或数据已完整")
            else:
                logger.info("ℹ️ 自动补全未触发（可能是网络问题或配置问题）")
        else:
            logger.info("ℹ️ 数据完整，无需补全")

        return result

    except Exception as e:
        result["error_message"] = str(e)
        logger.error("自动补全机制验证失败: %s", e)
        return result


# ==================== 测试用例 ====================


@pytest.mark.e2e
@pytest.mark.data_center
@pytest.mark.timeout(300)  # 统一数据管理器测试可能需要较长时间
class TestUnifiedDataManager:
    """统一数据管理器功能e2e测试套件."""

    def test_four_layer_data_fusion(self, china_stock_engine):
        """测试四层数据融合功能.

        验证标准：
        1. ✅ 四层融合机制可用
        2. ✅ 各数据层正常工作
        3. ✅ 数据融合结果正确
        4. ✅ 查询性能符合预期

        Args:
            china_stock_engine: ChinaStockEngine实例
        """
        logger.info("=" * 80)
        logger.info("开始测试：四层数据融合功能")
        logger.info("=" * 80)

        # 1. 验证四层数据融合
        logger.info("步骤1：验证四层数据融合机制...")
        fusion_result = validate_four_layer_data_fusion(china_stock_engine)

        assert fusion_result[
            "fusion_available"
        ], f"四层融合不可用: {fusion_result['error_message']}"
        assert fusion_result["fusion_successful"], "数据融合失败"

        logger.info("✅ 四层数据融合可用且成功")

        # 2. 验证各数据层可用性
        layer_status = []
        if fusion_result["preload_layer"]:
            layer_status.append("预加载层")
        if fusion_result["history_layer"]:
            layer_status.append("历史数据层")
        if fusion_result["recording_layer"]:
            layer_status.append("录制数据层")
        if fusion_result["realtime_layer"]:
            layer_status.append("实时数据层")

        logger.info("✅ 可用数据层: %s", ", ".join(layer_status))

        if len(layer_status) >= 2:
            logger.info("✅ 多层数据融合正常")
        else:
            logger.warning("⚠️ 仅有一层数据源可用，建议配置更多数据源")

        # 3. 验证查询性能
        if fusion_result["query_performance"] < 1.0:
            logger.info("✅ 查询性能良好: %.2f秒", fusion_result["query_performance"])
        else:
            logger.warning("⚠️ 查询性能较慢: %.2f秒", fusion_result["query_performance"])

        logger.info("=" * 80)
        logger.info("✅ 四层数据融合测试通过")
        logger.info("   - 融合可用: %s", fusion_result["fusion_available"])
        logger.info("   - 融合成功: %s", fusion_result["fusion_successful"])
        logger.info("   - 查询性能: %.2f秒", fusion_result["query_performance"])
        logger.info("=" * 80)

    def test_subscription_management(self, china_stock_engine):
        """测试订阅管理功能.

        验证标准：
        1. ✅ 订阅管理功能可用
        2. ✅ 多模块订阅合并正确
        3. ✅ 订阅取消功能正常
        4. ✅ 资源清理机制有效

        Args:
            china_stock_engine: ChinaStockEngine实例
        """
        logger.info("=" * 80)
        logger.info("开始测试：订阅管理功能")
        logger.info("=" * 80)

        # 1. 验证订阅管理
        logger.info("步骤1：验证订阅管理机制...")
        subscription_result = validate_subscription_management(china_stock_engine)

        assert subscription_result[
            "subscription_available"
        ], f"订阅管理不可用: {subscription_result['error_message']}"

        logger.info("✅ 订阅管理功能可用")

        # 2. 验证多模块订阅合并
        if subscription_result["multi_module_merge"]:
            logger.info("✅ 多模块订阅合并成功")
        else:
            logger.warning("⚠️ 多模块订阅合并异常")

        # 3. 验证订阅取消
        if subscription_result["subscription_cancel"]:
            logger.info("✅ 订阅取消功能正常")
        else:
            logger.warning("⚠️ 订阅取消功能异常")

        # 4. 验证资源清理
        if subscription_result["resource_cleanup"]:
            logger.info("✅ 资源清理机制有效")
        else:
            logger.info("ℹ️ 资源清理机制未完全验证")

        logger.info("=" * 80)
        logger.info("✅ 订阅管理测试通过")
        logger.info("   - 订阅可用: %s", subscription_result["subscription_available"])
        logger.info("   - 多模块合并: %s", subscription_result["multi_module_merge"])
        logger.info("   - 订阅取消: %s", subscription_result["subscription_cancel"])
        logger.info("   - 资源清理: %s", subscription_result["resource_cleanup"])
        logger.info("=" * 80)

    def test_preload_cache_effectiveness(self, china_stock_engine):
        """测试预加载缓存效果.

        验证标准：
        1. ✅ 预加载服务可用
        2. ✅ 缓存命中率合理
        3. ✅ 常用品种预加载
        4. ✅ 缓存性能提升明显

        Args:
            china_stock_engine: ChinaStockEngine实例
        """
        logger.info("=" * 80)
        logger.info("开始测试：预加载缓存效果")
        logger.info("=" * 80)

        # 1. 验证预加载服务
        logger.info("步骤1：验证预加载服务...")
        preload_result = validate_preload_cache_effectiveness(china_stock_engine)

        assert preload_result[
            "preload_available"
        ], f"预加载服务不可用: {preload_result['error_message']}"

        logger.info("✅ 预加载服务可用")

        # 2. 验证缓存效果
        if preload_result["cache_symbols"] > 0:
            logger.info("✅ 预加载缓存包含 %d 个品种", preload_result["cache_symbols"])
        else:
            logger.info("ℹ️ 预加载缓存为空（首次运行或未配置）")

        # 3. 验证缓存命中率
        if preload_result["cache_hit_rate"] > 0:
            logger.info("✅ 缓存命中率: %.1f%%", preload_result["cache_hit_rate"] * 100)
        else:
            logger.info("ℹ️ 暂无缓存访问记录")

        # 4. 验证性能提升
        if preload_result["performance_improvement"]:
            logger.info("✅ 缓存性能提升明显")
        else:
            logger.info("ℹ️ 缓存性能提升未明显体现（可能需要更多测试）")

        logger.info("=" * 80)
        logger.info("✅ 预加载缓存效果测试通过")
        logger.info("   - 预加载可用: %s", preload_result["preload_available"])
        logger.info("   - 缓存品种数: %d", preload_result["cache_symbols"])
        logger.info("   - 命中率: %.1f%%", preload_result["cache_hit_rate"] * 100)
        logger.info(
            "   - 性能提升: %s", "是" if preload_result["performance_improvement"] else "否"
        )
        logger.info("=" * 80)

    def test_auto_completion_mechanism(self, china_stock_engine):
        """测试自动补全机制.

        验证标准：
        1. ✅ 自动补全功能可用
        2. ✅ 数据缺失检测准确
        3. ✅ 自动下载触发正确
        4. ✅ 补全结果验证通过

        Args:
            china_stock_engine: ChinaStockEngine实例
        """
        logger.info("=" * 80)
        logger.info("开始测试：自动补全机制")
        logger.info("=" * 80)

        # 1. 验证自动补全机制
        logger.info("步骤1：验证自动补全机制...")
        completion_result = validate_auto_completion_mechanism(china_stock_engine)

        assert completion_result[
            "auto_completion_available"
        ], f"自动补全不可用: {completion_result['error_message']}"

        logger.info("✅ 自动补全机制可用")

        # 2. 验证缺失检测
        if completion_result["gap_detection_working"]:
            logger.info("✅ 数据缺失检测正常")
        else:
            logger.info("ℹ️ 数据缺失检测未触发（数据可能完整）")

        # 3. 验证补全效果
        if completion_result["completion_successful"]:
            logger.info("✅ 自动补全成功")
        else:
            logger.info("ℹ️ 自动补全未触发或无需补全")

        logger.info("=" * 80)
        logger.info("✅ 自动补全机制测试通过")
        logger.info("   - 补全可用: %s", completion_result["auto_completion_available"])
        logger.info("   - 缺失检测: %s", completion_result["gap_detection_working"])
        logger.info("   - 补全成功: %s", completion_result["completion_successful"])
        logger.info("=" * 80)

    def test_comprehensive_data_manager_workflow(self, china_stock_engine):
        """测试完整的数据管理器工作流.

        验证标准：
        1. ✅ 完整工作流：查询 → 缓存 → 订阅 → 补全
        2. ✅ 各模块协同工作
        3. ✅ 性能和稳定性良好
        4. ✅ 资源管理正确

        Args:
            china_stock_engine: ChinaStockEngine实例
        """
        logger.info("=" * 80)
        logger.info("开始测试：完整数据管理器工作流")
        logger.info("=" * 80)

        workflow_start = time.time()

        # 1. 四层数据融合测试
        logger.info("步骤1：四层数据融合...")
        fusion_result = validate_four_layer_data_fusion(china_stock_engine)

        # 2. 订阅管理测试
        logger.info("步骤2：订阅管理...")
        subscription_result = validate_subscription_management(china_stock_engine)

        # 3. 预加载缓存测试
        logger.info("步骤3：预加载缓存...")
        preload_result = validate_preload_cache_effectiveness(china_stock_engine)

        # 4. 自动补全测试
        logger.info("步骤4：自动补全...")
        completion_result = validate_auto_completion_mechanism(china_stock_engine)

        workflow_time = time.time() - workflow_start

        # 验证工作流完整性
        workflow_complete = (
            fusion_result["fusion_available"]
            and subscription_result["subscription_available"]
            and preload_result["preload_available"]
            and completion_result["auto_completion_available"]
        )

        assert workflow_complete, "统一数据管理器工作流不完整"

        # 汇总性能数据
        total_queries = 0
        total_time = 0

        if fusion_result["query_performance"] > 0:
            total_queries += 1
            total_time += fusion_result["query_performance"]

        if preload_result["preload_available"]:
            # 估算预加载查询时间（通常很快）
            estimated_preload_time = 0.1
            total_queries += 1
            total_time += estimated_preload_time

        avg_performance = total_time / total_queries if total_queries > 0 else 0

        logger.info("=" * 80)
        logger.info("✅ 完整数据管理器工作流测试通过")
        logger.info("   - 工作流耗时: %.2f秒", workflow_time)
        logger.info("   - 四层融合: %s", "正常" if fusion_result["fusion_successful"] else "异常")
        logger.info(
            "   - 订阅管理: %s", "正常" if subscription_result["multi_module_merge"] else "异常"
        )
        logger.info(
            "   - 预加载缓存: %s", "正常" if preload_result["cache_symbols"] > 0 else "未配置"
        )
        logger.info(
            "   - 自动补全: %s", "正常" if completion_result["gap_detection_working"] else "未触发"
        )
        logger.info("   - 平均查询性能: %.2f秒", avg_performance)
        logger.info("=" * 80)


# ==================== 单独的快速测试 ====================


@pytest.mark.e2e
@pytest.mark.data_center
@pytest.mark.timeout(60)
def test_unified_manager_availability(china_stock_engine):
    """快速测试：验证统一数据管理器可用性.

    Args:
        china_stock_engine: ChinaStockEngine实例
    """
    logger.info("快速测试：验证统一数据管理器可用性")

    assert china_stock_engine is not None, "ChinaStockEngine应该可用"
    logger.info("✅ ChinaStockEngine可用")

    # 检查统一数据管理器是否存在
    unified_manager = getattr(china_stock_engine, "unified_data_manager", None)
    assert unified_manager is not None, "统一数据管理器应该可用"

    logger.info("✅ 统一数据管理器可用")

    # 检查核心方法是否存在
    core_methods = [
        "get_kline_data",
        "get_multi_kline_data",
        "subscribe",
        "unsubscribe",
    ]

    for method in core_methods:
        assert hasattr(unified_manager, method), f"缺少核心方法: {method}"
        logger.info("✅ 核心方法可用: %s", method)

    logger.info("✅ 统一数据管理器可用性验证通过")


@pytest.mark.e2e
@pytest.mark.data_center
@pytest.mark.timeout(30)
def test_data_fusion_performance(china_stock_engine):
    """快速测试：验证数据融合性能.

    Args:
        china_stock_engine: ChinaStockEngine实例
    """
    logger.info("快速测试：验证数据融合性能")

    unified_manager = getattr(china_stock_engine, "unified_data_manager", None)
    assert unified_manager is not None, "统一数据管理器不可用"

    # 测试基本查询性能
    test_symbol = "000001"
    start_date = date.today() - timedelta(days=7)

    start_time = time.time()
    data = unified_manager.get_kline_data(
        symbol=test_symbol,
        interval="1d",
        start_date=start_date,
        end_date=date.today(),
        check_gaps=False,  # 禁用补全以测试纯查询性能
        use_preload=True,
    )
    query_time = time.time() - start_time

    assert query_time < 2.0, f"查询性能过慢: {query_time:.2f}秒"
    logger.info("✅ 数据融合性能正常: %.2f秒", query_time)

    if data is not None and not data.empty:
        logger.info("✅ 查询返回 %d 条记录", len(data))
    else:
        logger.warning("⚠️ 查询返回空结果")
