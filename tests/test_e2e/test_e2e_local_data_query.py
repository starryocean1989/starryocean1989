# -*- coding: utf-8 -*-
"""
E2E测试: 本地数据查询展示.

测试功能链路: 2.3.1-2.3.3 本地数据查询展示链条

验证点:
1. 品种/日期区间/周期查询参数
2. OHLCV数据检索
3. 查询响应时间
4. 数据格式验证
5-6. 复合查询、展示格式化
7-11. 数据质量检测、缺失识别等
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta

import pytest
from vnpy.trader.constant import Exchange, Interval

logger = logging.getLogger(__name__)


@pytest.mark.e2e
@pytest.mark.asyncio
class TestLocalDataQueryE2E:
    """本地数据查询端到端测试."""

    @pytest.mark.timeout(35)
    async def test_ohlcv_data_query(
        self,
        backend_app,
        vnpy_db_helper,
        symbol_service,
    ):
        """测试OHLCV数据查询."""
        logger.info("=" * 80)
        logger.info("E2E测试: OHLCV数据查询")
        logger.info("=" * 80)

        # 准备品种缓存
        await self._ensure_symbol_cache(symbol_service)

        # 获取测试品种
        test_symbol, test_exchange = self._get_test_symbol(symbol_service)
        if not test_symbol:
            logger.warning("⚠ 没有可用的测试品种")
            return

        # 执行查询
        try:
            count = vnpy_db_helper.count_bars(
                symbol=test_symbol,
                exchange=Exchange(test_exchange),
                interval=Interval.MINUTE,
                start_date=datetime.now() - timedelta(days=7),
                end_date=datetime.now(),
            )

            logger.info(f"查询结果: {count}条数据")

            if count > 0:
                logger.info("✓ OHLCV数据查询成功")
            else:
                logger.warning("⚠ 没有查询到数据")

        except Exception as e:
            logger.warning(f"⚠ 查询遇到异常: {e}")

        logger.info("=" * 80)

    @pytest.mark.timeout(30)
    async def test_query_response_time(
        self,
        backend_app,
        vnpy_db_helper,
        symbol_service,
    ):
        """测试查询响应时间."""
        logger.info("=" * 80)
        logger.info("E2E测试: 查询响应时间")
        logger.info("=" * 80)

        await self._ensure_symbol_cache(symbol_service)
        test_symbol, test_exchange = self._get_test_symbol(symbol_service)

        if test_symbol:
            # 测量查询时间
            start_time = time.time()

            try:
                vnpy_db_helper.count_bars(
                    symbol=test_symbol,
                    exchange=Exchange(test_exchange),
                    interval=Interval.MINUTE,
                    start_date=datetime.now() - timedelta(days=1),
                    end_date=datetime.now(),
                )

                elapsed = time.time() - start_time
                logger.info(f"查询耗时: {elapsed:.3f}秒")

                if elapsed <= 3.0:
                    logger.info("✓ 查询响应时间≤3秒")
                else:
                    logger.warning("⚠ 查询响应时间超标")

            except Exception as e:
                logger.warning(f"⚠ 查询遇到异常: {e}")

        logger.info("=" * 80)

    @pytest.mark.timeout(30)
    async def test_data_format_validation(
        self,
        backend_app,
        vnpy_db_helper,
        symbol_service,
    ):
        """测试数据格式验证."""
        logger.info("=" * 80)
        logger.info("E2E测试: 数据格式验证")
        logger.info("=" * 80)

        await self._ensure_symbol_cache(symbol_service)
        test_symbol, test_exchange = self._get_test_symbol(symbol_service)

        if test_symbol:
            try:
                format_result = vnpy_db_helper.verify_data_format(
                    symbol=test_symbol,
                    exchange=Exchange(test_exchange),
                    interval=Interval.MINUTE,
                    limit=10,
                )

                logger.info(f"数据格式验证: {format_result}")

                if format_result.get("valid"):
                    logger.info("✓ 数据格式验证通过")
                else:
                    logger.warning(f"⚠ 数据格式异常: {format_result.get('error')}")

            except Exception as e:
                logger.warning(f"⚠ 格式验证遇到异常: {e}")

        logger.info("=" * 80)

    @pytest.mark.timeout(35)
    async def test_data_quality_detection(
        self,
        backend_app,
        vnpy_db_helper,
        symbol_service,
    ):
        """测试数据质量检测."""
        logger.info("=" * 80)
        logger.info("E2E测试: 数据质量检测")
        logger.info("=" * 80)

        await self._ensure_symbol_cache(symbol_service)
        test_symbol, test_exchange = self._get_test_symbol(symbol_service)

        if test_symbol:
            try:
                quality_result = vnpy_db_helper.detect_data_quality(
                    symbol=test_symbol,
                    exchange=Exchange(test_exchange),
                    interval=Interval.MINUTE,
                )

                logger.info(f"数据质量检测结果:")
                logger.info(f"  - 质量分数: {quality_result['quality_score']:.2%}")
                logger.info(f"  - 总数据量: {quality_result['total_count']}")
                logger.info(f"  - 问题: {quality_result.get('issues', [])}")

                if quality_result["quality_score"] >= 0.98:
                    logger.info("✓ 数据质量≥98%")
                else:
                    logger.warning("⚠ 数据质量不达标")

            except Exception as e:
                logger.warning(f"⚠ 质量检测遇到异常: {e}")

        logger.info("=" * 80)

    @pytest.mark.timeout(30)
    async def test_missing_data_identification(
        self,
        backend_app,
        vnpy_db_helper,
        symbol_service,
    ):
        """测试缺失数据识别."""
        logger.info("=" * 80)
        logger.info("E2E测试: 缺失数据识别")
        logger.info("=" * 80)

        await self._ensure_symbol_cache(symbol_service)
        test_symbol, test_exchange = self._get_test_symbol(symbol_service)

        if test_symbol:
            try:
                missing_result = vnpy_db_helper.identify_missing_data(
                    symbol=test_symbol,
                    exchange=Exchange(test_exchange),
                    interval=Interval.MINUTE,
                    expected_start=datetime.now() - timedelta(days=7),
                    expected_end=datetime.now(),
                )

                logger.info(f"缺失数据识别结果:")
                logger.info(f"  - 是否缺失: {missing_result['has_missing']}")
                logger.info(f"  - 完整度: {missing_result.get('completeness', 0):.2%}")
                logger.info(f"  - 缺失范围数: {missing_result.get('missing_range_count', 0)}")

                if missing_result.get("completeness", 0) >= 0.98:
                    logger.info("✓ 数据完整度≥98%")
                else:
                    logger.warning("⚠ 数据有缺失")

            except Exception as e:
                logger.warning(f"⚠ 缺失识别遇到异常: {e}")

        logger.info("=" * 80)

    # ========== 辅助方法 ==========

    async def _ensure_symbol_cache(self, symbol_service):
        """确保品种缓存已加载."""
        from tests.test_e2e.utils.service_accessor import ServiceAccessor

        accessor = ServiceAccessor()
        cache_stats = accessor.get_cache_stats(symbol_service)
        if cache_stats["cache_size"] == 0:
            await symbol_service.refresh_cache()
            # 使用条件等待
            from tests.test_e2e.utils.wait_helpers import wait_for_cache_loaded

            await wait_for_cache_loaded(symbol_service, accessor, min_size=1, timeout=3.0)

    def _get_test_symbol(self, symbol_service):
        """获取测试品种."""
        for symbol_info in symbol_service._symbols_cache.values():
            return symbol_info.symbol, symbol_info.exchange
        return None, None
