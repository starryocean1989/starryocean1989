# -*- coding: utf-8 -*-
"""
基础集成测试 - 验证架构重构是否正常工作
"""

import logging
import sys

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def test_architecture_changes():
    """测试架构更改."""
    logger.info("=" * 60)
    logger.info("开始测试架构更改")
    logger.info("=" * 60)

    try:
        # 1. 测试shared_services模块
        logger.info("\n1. 测试shared_services模块")
        from backend.core.shared_services import (
            get_service_manager,
            get_main_engine,
            get_event_engine,
            get_china_stock_engine,
        )

        service_manager = get_service_manager()
        logger.info("✅ ServiceManager 获取成功")

        main_engine = get_main_engine()
        event_engine = get_event_engine()
        china_stock_engine = get_china_stock_engine()

        logger.info(f"MainEngine: {main_engine}")
        logger.info(f"EventEngine: {event_engine}")
        logger.info(f"ChinaStockEngine: {china_stock_engine}")

        # 2. 测试服务初始化
        logger.info("\n2. 测试服务初始化")
        from backend.core.shared_services import initialize_services

        result = initialize_services()
        logger.info(f"初始化结果: {result['success']}")

        if not result["success"]:
            logger.warning("初始化有警告:")
            logger.warning(result["user_friendly_report"])

        # 3. 测试引擎是否初始化
        logger.info("\n3. 检查引擎状态")
        main_engine = get_main_engine()
        event_engine = get_event_engine()
        china_stock_engine = get_china_stock_engine()

        logger.info(f"MainEngine 可用: {main_engine is not None}")
        logger.info(f"EventEngine 可用: {event_engine is not None}")
        logger.info(f"ChinaStockEngine 可用: {china_stock_engine is not None}")

        # 4. 测试服务获取
        logger.info("\n4. 测试服务获取")
        services = [
            "data_center_service",
            "trading_gateway_service",
            "strategy_center_service",
            "portfolio_service",
            "market_board_service",
            "system_manager_service",
        ]

        for service_name in services:
            service = service_manager.get_service(service_name)
            if service:
                logger.info(f"✅ {service_name}: 可用")
                # 测试健康检查
                try:
                    health = service.health_check()
                    logger.info(f"   状态: {health.get('status')}")
                    logger.info(f"   Main Engine: {service.main_engine is not None}")
                    logger.info(f"   Event Engine: {service.event_engine is not None}")
                except Exception as e:
                    logger.warning(f"   健康检查失败: {e}")
            else:
                logger.warning(f"⚠️ {service_name}: 不可用")

        # 5. 测试DataCenterService的基本功能
        logger.info("\n5. 测试DataCenterService基本功能")
        data_center_service = service_manager.get_service("data_center_service")

        if data_center_service and data_center_service.china_stock_engine:
            logger.info("测试品种列表加载...")
            try:
                # 测试刷新品种列表（不调用API）
                result = data_center_service.refresh_symbol_list()
                logger.info(f"刷新结果: {result.get('message')}")

                # 如果缓存为空，尝试重新加载
                if not result.get("success") or result.get("symbol_count", 0) == 0:
                    logger.info("尝试重新加载品种列表...")
                    result = data_center_service.reload_symbol_list(force=True)
                    logger.info(f"加载结果: {result.get('message')}")
                    logger.info(f"品种数量: {result.get('symbol_count', 0)}")

            except Exception as e:
                logger.error(f"品种列表测试失败: {e}", exc_info=True)
        else:
            logger.warning("DataCenterService 或 ChinaStockEngine 不可用，跳过功能测试")

        logger.info("\n" + "=" * 60)
        logger.info("测试完成")
        logger.info("=" * 60)

        return True

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = test_architecture_changes()
    sys.exit(0 if success else 1)
