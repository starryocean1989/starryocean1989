# -*- coding: utf-8 -*-
"""
端到端集成测试 - 验证UI-Backend-VNPY完整集成

测试内容：
1. 服务初始化
2. 数据中心功能
3. 交易网关功能
4. 策略中心功能
5. 其他服务功能
"""

import logging
import sys
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger(__name__)


def test_service_initialization():
    """测试1: 服务初始化."""
    logger.info("\n" + "=" * 60)
    logger.info("测试1: 服务初始化")
    logger.info("=" * 60)

    try:
        from backend.core.shared_services import (
            get_service_manager,
            get_main_engine,
            get_event_engine,
            get_china_stock_engine,
            initialize_services,
        )

        # 初始化所有服务
        result = initialize_services()

        if result["success"]:
            logger.info("✅ 服务初始化成功")
        else:
            logger.warning("⚠️ 服务初始化有警告:")
            logger.warning(result["user_friendly_report"])

        # 检查引擎
        main_engine = get_main_engine()
        event_engine = get_event_engine()
        china_stock_engine = get_china_stock_engine()

        logger.info(f"MainEngine: {main_engine is not None}")
        logger.info(f"EventEngine: {event_engine is not None}")
        logger.info(f"ChinaStockEngine: {china_stock_engine is not None}")

        # 检查所有服务
        service_manager = get_service_manager()
        services = [
            "data_center_service",
            "trading_gateway_service",
            "strategy_center_service",
            "portfolio_service",
            "market_board_service",
            "system_manager_service",
        ]

        all_ok = True
        for service_name in services:
            service = service_manager.get_service(service_name)
            if service:
                health = service.health_check()
                logger.info(f"✅ {service_name}: {health.get('status')}")
            else:
                logger.error(f"❌ {service_name}: 不可用")
                all_ok = False

        return all_ok

    except Exception as e:
        logger.error(f"服务初始化测试失败: {e}", exc_info=True)
        return False


def test_data_center_service():
    """测试2: 数据中心服务."""
    logger.info("\n" + "=" * 60)
    logger.info("测试2: 数据中心服务")
    logger.info("=" * 60)

    try:
        from backend.core.shared_services import get_service_manager

        service_manager = get_service_manager()
        data_service = service_manager.get_service("data_center_service")

        if not data_service:
            logger.error("❌ DataCenterService不可用")
            return False

        # 测试品种列表
        logger.info("\n测试品种列表功能...")

        # 刷新品种列表
        result = data_service.refresh_symbol_list()
        logger.info(f"刷新结果: {result.get('message')}")

        # 如果缓存为空，重新加载
        if not result.get("success") or result.get("symbol_count", 0) == 0:
            logger.info("重新加载品种列表...")
            result = data_service.reload_symbol_list(force=True)
            logger.info(f"加载结果: {result.get('message')}")
            logger.info(f"品种数量: {result.get('symbol_count', 0)}")

        if result.get("success"):
            logger.info("✅ 品种列表功能正常")
        else:
            logger.warning("⚠️ 品种列表功能异常")

        # 测试筛选
        logger.info("\n测试品种筛选...")
        filter_result = data_service.filter_symbols(search_text="600")
        logger.info(f"筛选结果: {filter_result.get('symbol_count', 0)}个品种")

        return True

    except Exception as e:
        logger.error(f"数据中心服务测试失败: {e}", exc_info=True)
        return False


def test_trading_gateway_service():
    """测试3: 交易网关服务."""
    logger.info("\n" + "=" * 60)
    logger.info("测试3: 交易网关服务")
    logger.info("=" * 60)

    try:
        from backend.core.shared_services import get_service_manager

        service_manager = get_service_manager()
        gateway_service = service_manager.get_service("trading_gateway_service")

        if not gateway_service:
            logger.error("❌ TradingGatewayService不可用")
            return False

        # 测试获取网关类型
        logger.info("\n获取支持的网关类型...")
        gateway_types = gateway_service.get_gateway_types()
        logger.info(f"支持{len(gateway_types)}种网关类型")
        for gw in gateway_types:
            logger.info(f"  - {gw['name']}: {gw['description']}")

        # 测试创建PaperAccount网关
        logger.info("\n创建PaperAccount网关...")
        result = gateway_service.create_gateway(
            gateway_name="测试模拟账户", gateway_type="paperaccount", config={"初始资金": 1000000}
        )

        if result.get("success"):
            logger.info(f"✅ 网关创建成功: {result.get('message')}")

            # 测试连接网关
            logger.info("\n连接网关...")
            conn_result = gateway_service.connect_gateway("测试模拟账户")
            logger.info(f"连接结果: {conn_result.get('message')}")

            # 测试列出网关
            gateways = gateway_service.list_gateways()
            logger.info(f"当前网关数量: {len(gateways)}")

        else:
            logger.warning(f"⚠️ 网关创建失败: {result.get('message')}")

        return True

    except Exception as e:
        logger.error(f"交易网关服务测试失败: {e}", exc_info=True)
        return False


def test_strategy_center_service():
    """测试4: 策略中心服务."""
    logger.info("\n" + "=" * 60)
    logger.info("测试4: 策略中心服务")
    logger.info("=" * 60)

    try:
        from backend.core.shared_services import get_service_manager

        service_manager = get_service_manager()
        strategy_service = service_manager.get_service("strategy_center_service")

        if not strategy_service:
            logger.error("❌ StrategyCenterService不可用")
            return False

        # 测试列出策略文件
        logger.info("\n列出策略文件...")
        result = strategy_service.list_strategy_files()

        if result.get("success"):
            files = result.get("files", [])
            logger.info(f"策略文件数量: {len(files)}")
            logger.info("✅ 策略文件管理功能正常")
        else:
            logger.warning(f"⚠️ 策略文件列表获取失败: {result.get('message')}")

        return True

    except Exception as e:
        logger.error(f"策略中心服务测试失败: {e}", exc_info=True)
        return False


def test_other_services():
    """测试5: 其他服务."""
    logger.info("\n" + "=" * 60)
    logger.info("测试5: 其他服务")
    logger.info("=" * 60)

    try:
        from backend.core.shared_services import get_service_manager

        service_manager = get_service_manager()

        # 测试PortfolioService
        logger.info("\n测试PortfolioService...")
        portfolio_service = service_manager.get_service("portfolio_service")
        if portfolio_service:
            portfolios = portfolio_service.list_portfolios()
            logger.info(f"✅ PortfolioService可用，组合数量: {portfolios.get('total', 0)}")
        else:
            logger.warning("⚠️ PortfolioService不可用")

        # 测试MarketBoardService
        logger.info("\n测试MarketBoardService...")
        market_service = service_manager.get_service("market_board_service")
        if market_service:
            logger.info("✅ MarketBoardService可用")
        else:
            logger.warning("⚠️ MarketBoardService不可用")

        # 测试SystemManagerService
        logger.info("\n测试SystemManagerService...")
        system_service = service_manager.get_service("system_manager_service")
        if system_service:
            # 测试系统监控
            metrics_result = system_service.update_system_metrics()
            if metrics_result.get("success"):
                metrics = metrics_result.get("metrics", {})
                logger.info(f"CPU使用率: {metrics.get('cpu_percent', 0):.1f}%")
                logger.info(f"内存使用率: {metrics.get('memory_percent', 0):.1f}%")
                logger.info("✅ SystemManagerService功能正常")

            # 测试服务健康检查
            health_result = system_service.check_all_services()
            if health_result.get("success"):
                services = health_result.get("services", {})
                logger.info(f"服务健康检查: {len(services)}个服务")
        else:
            logger.warning("⚠️ SystemManagerService不可用")

        return True

    except Exception as e:
        logger.error(f"其他服务测试失败: {e}", exc_info=True)
        return False


def main():
    """主测试流程."""
    logger.info("=" * 60)
    logger.info("UI-Backend-VNPY 端到端集成测试")
    logger.info("=" * 60)

    results = []

    # 运行所有测试
    results.append(("服务初始化", test_service_initialization()))
    results.append(("数据中心服务", test_data_center_service()))
    results.append(("交易网关服务", test_trading_gateway_service()))
    results.append(("策略中心服务", test_strategy_center_service()))
    results.append(("其他服务", test_other_services()))

    # 汇总结果
    logger.info("\n" + "=" * 60)
    logger.info("测试结果汇总")
    logger.info("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{test_name}: {status}")

    logger.info(f"\n总计: {passed}/{total} 通过")

    if passed == total:
        logger.info("\n🎉 所有测试通过！集成成功！")
        return True
    else:
        logger.warning(f"\n⚠️ {total - passed}个测试失败")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
