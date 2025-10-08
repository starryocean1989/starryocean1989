# -*- coding: utf-8 -*-
"""
服务初始化器 - 按依赖顺序初始化所有服务

负责整个系统的服务初始化流程，包括：
- VNPY框架初始化（MainEngine + EventEngine）
- ChinaStockEngine初始化
- 各业务服务初始化
- 依赖关系管理
- 错误处理和降级
"""

import logging
from typing import Any, Dict, List
from enum import Enum

logger = logging.getLogger(__name__)


class InitializationPhase(Enum):
    """初始化阶段."""

    VNPY_CORE = "vnpy_core"  # VNPY核心框架
    DATA_ENGINES = "data_engines"  # 数据引擎（ChinaStockEngine等）
    DATA_SERVICES = "data_services"  # 数据服务
    TRADING_SERVICES = "trading_services"  # 交易服务
    STRATEGY_SERVICES = "strategy_services"  # 策略服务
    AUXILIARY_SERVICES = "auxiliary_services"  # 辅助服务


class ServiceInitializer:
    """服务初始化器.

    按照依赖顺序初始化所有服务：
    1. VNPY核心框架 (MainEngine + EventEngine)
    2. 数据引擎 (ChinaStockEngine)
    3. 数据服务 (DataCenterService)
    4. 交易服务 (TradingGatewayService)
    5. 策略服务 (StrategyCenterService)
    6. 辅助服务 (Portfolio, Market, System)
    """

    def __init__(self, service_manager):
        """初始化服务初始化器.

        Args:
            service_manager: 服务管理器实例
        """
        self.service_manager = service_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        self.initialized_services: Dict[str, Any] = {}
        self.failed_services: List[str] = []

        # VNPY引擎实例
        self.main_engine = None
        self.event_engine = None
        self.china_stock_engine = None

    def initialize_all_services(self) -> bool:
        """初始化所有服务.

        Returns:
            bool: 是否成功初始化（允许部分失败）
        """
        try:
            self.logger.info("=" * 60)
            self.logger.info("开始初始化服务...")
            self.logger.info("=" * 60)

            # 阶段1: 初始化VNPY核心框架
            phase1_success = self._initialize_vnpy_core()

            # 阶段2: 初始化数据引擎
            phase2_success = self._initialize_data_engines()

            # 阶段3: 初始化数据服务
            phase3_success = self._initialize_data_services()

            # 阶段4: 初始化交易服务
            _phase4_success = self._initialize_trading_services()

            # 阶段5: 初始化策略服务
            _phase5_success = self._initialize_strategy_services()

            # 阶段6: 初始化辅助服务
            _phase6_success = self._initialize_auxiliary_services()

            # 生成初始化报告
            self._generate_initialization_report()

            # 如果核心服务初始化成功，即使部分服务失败也返回True
            core_services_ok = phase1_success or phase2_success or phase3_success

            if core_services_ok:
                self.logger.info("✅ 核心服务初始化成功，系统可以启动")
                return True
            else:
                self.logger.error("❌ 核心服务初始化失败，系统无法正常启动")
                return False

        except Exception as e:
            self.logger.error("服务初始化过程发生严重异常: %s", e, exc_info=True)
            self.service_manager.record_error(
                "ServiceInitializer",
                "CRITICAL_INITIALIZATION_ERROR",
                f"初始化过程异常: {str(e)}",
                exception=e,
            )
            return False

    def _initialize_vnpy_core(self) -> bool:
        """阶段1: 初始化VNPY核心框架.

        Returns:
            bool: 是否成功
        """
        self.logger.info("\n" + "=" * 60)
        self.logger.info("阶段1: 初始化VNPY核心框架")
        self.logger.info("=" * 60)

        try:
            # 导入VNPY核心类
            try:
                from vnpy.event import EventEngine
                from vnpy.trader.engine import MainEngine

                self.logger.info("✅ VNPY核心模块导入成功")
            except ImportError as e:
                self.logger.error("❌ VNPY核心模块导入失败: %s", e)
                self.failed_services.append("vnpy_core")
                return False

            # 创建事件引擎
            try:
                self.event_engine = EventEngine()
                self.logger.info("✅ EventEngine 创建成功")
            except Exception as e:
                self.logger.error("❌ EventEngine 创建失败: %s", e, exc_info=True)
                self.failed_services.append("event_engine")
                return False

            # 创建主引擎
            try:
                self.main_engine = MainEngine(self.event_engine)
                self.logger.info("✅ MainEngine 创建成功")
            except Exception as e:
                self.logger.error("❌ MainEngine 创建失败: %s", e, exc_info=True)
                self.failed_services.append("main_engine")
                return False

            # 注册到全局
            from backend.core.shared_services import set_main_engine, set_event_engine

            set_main_engine(self.main_engine)
            set_event_engine(self.event_engine)

            self.logger.info("✅ VNPY核心框架初始化完成")
            return True

        except Exception as e:
            self.logger.error("❌ VNPY核心框架初始化失败: %s", e, exc_info=True)
            self.failed_services.append("vnpy_core")
            return False

    def _initialize_data_engines(self) -> bool:
        """阶段2: 初始化数据引擎.

        Returns:
            bool: 是否成功
        """
        self.logger.info("\n" + "=" * 60)
        self.logger.info("阶段2: 初始化数据引擎")
        self.logger.info("=" * 60)

        if not self.main_engine or not self.event_engine:
            self.logger.warning("⚠️ VNPY引擎未初始化，跳过数据引擎初始化")
            return False

        try:
            # 初始化ChinaStockEngine
            try:
                from backend.infrastructure.data_module_vnpy.engine import ChinaStockEngine

                self.china_stock_engine = ChinaStockEngine(self.main_engine, self.event_engine)
                self.logger.info("✅ ChinaStockEngine 创建成功")

                # 注册到全局
                from backend.core.shared_services import set_china_stock_engine

                set_china_stock_engine(self.china_stock_engine)

            except ImportError as e:
                self.logger.warning("⚠️ ChinaStockEngine 不可用: %s", e)
                self.failed_services.append("china_stock_engine")
            except Exception as e:
                self.logger.error("❌ ChinaStockEngine 初始化失败: %s", e, exc_info=True)
                self.failed_services.append("china_stock_engine")

            # 集成data_engine作为vnpy datafeed
            try:
                from backend.infrastructure.data_engine.vnpy_datafeed import DataEngineGateway

                # 添加DataEngine网关到MainEngine
                self.main_engine.add_gateway(DataEngineGateway)
                self.logger.info("✅ DataEngine网关已注册")

            except ImportError as e:
                self.logger.warning("⚠️ DataEngine网关不可用: %s", e)
            except Exception as e:
                self.logger.error("❌ DataEngine网关注册失败: %s", e, exc_info=True)

            self.logger.info("✅ 数据引擎初始化完成")
            return True

        except Exception as e:
            self.logger.error("❌ 数据引擎初始化失败: %s", e, exc_info=True)
            return False

    def _initialize_data_services(self) -> bool:
        """阶段3: 初始化数据服务.

        Returns:
            bool: 是否成功
        """
        self.logger.info("\n" + "=" * 60)
        self.logger.info("阶段3: 初始化数据服务")
        self.logger.info("=" * 60)

        success_count = 0

        # 初始化DataCenterService
        try:
            from backend.services.data_center_service import DataCenterService

            data_center_service = DataCenterService()
            init_success = data_center_service.initialize()

            if init_success:
                self.service_manager.register_service("data_center_service", data_center_service)
                self.initialized_services["data_center_service"] = data_center_service
                self.logger.info("✅ DataCenterService 初始化成功")
                success_count += 1
            else:
                self.logger.warning("⚠️ DataCenterService 初始化失败")
                self.failed_services.append("data_center_service")

        except Exception as e:
            self.logger.error("❌ DataCenterService 初始化异常: %s", e, exc_info=True)
            self.failed_services.append("data_center_service")

        return success_count > 0

    def _initialize_trading_services(self) -> bool:
        """阶段4: 初始化交易服务.

        Returns:
            bool: 是否成功
        """
        self.logger.info("\n" + "=" * 60)
        self.logger.info("阶段4: 初始化交易服务")
        self.logger.info("=" * 60)

        success_count = 0

        # 初始化TradingGatewayService
        try:
            from backend.services.trading_gateway_service import TradingGatewayService

            trading_gateway_service = TradingGatewayService()
            init_success = trading_gateway_service.initialize()

            if init_success:
                self.service_manager.register_service(
                    "trading_gateway_service", trading_gateway_service
                )
                self.initialized_services["trading_gateway_service"] = trading_gateway_service
                self.logger.info("✅ TradingGatewayService 初始化成功")
                success_count += 1
            else:
                self.logger.warning("⚠️ TradingGatewayService 初始化失败")
                self.failed_services.append("trading_gateway_service")

        except Exception as e:
            self.logger.error("❌ TradingGatewayService 初始化异常: %s", e, exc_info=True)
            self.failed_services.append("trading_gateway_service")

        return success_count > 0

    def _initialize_strategy_services(self) -> bool:
        """阶段5: 初始化策略服务.

        Returns:
            bool: 是否成功
        """
        self.logger.info("\n" + "=" * 60)
        self.logger.info("阶段5: 初始化策略服务")
        self.logger.info("=" * 60)

        success_count = 0

        # 初始化StrategyCenterService
        try:
            from backend.services.strategy_center_service import StrategyCenterService

            strategy_center_service = StrategyCenterService()
            init_success = strategy_center_service.initialize()

            if init_success:
                self.service_manager.register_service(
                    "strategy_center_service", strategy_center_service
                )
                self.initialized_services["strategy_center_service"] = strategy_center_service
                self.logger.info("✅ StrategyCenterService 初始化成功")
                success_count += 1
            else:
                self.logger.warning("⚠️ StrategyCenterService 初始化失败")
                self.failed_services.append("strategy_center_service")

        except Exception as e:
            self.logger.error("❌ StrategyCenterService 初始化异常: %s", e, exc_info=True)
            self.failed_services.append("strategy_center_service")

        return success_count > 0

    def _initialize_auxiliary_services(self) -> bool:
        """阶段6: 初始化辅助服务.

        Returns:
            bool: 是否成功
        """
        self.logger.info("\n" + "=" * 60)
        self.logger.info("阶段6: 初始化辅助服务")
        self.logger.info("=" * 60)

        success_count = 0

        # 初始化PortfolioService
        try:
            from backend.services.portfolio_service import PortfolioService

            portfolio_service = PortfolioService()
            init_success = portfolio_service.initialize()

            if init_success:
                self.service_manager.register_service("portfolio_service", portfolio_service)
                self.initialized_services["portfolio_service"] = portfolio_service
                self.logger.info("✅ PortfolioService 初始化成功")
                success_count += 1
            else:
                self.logger.warning("⚠️ PortfolioService 初始化失败")
                self.failed_services.append("portfolio_service")

        except Exception as e:
            self.logger.error("❌ PortfolioService 初始化异常: %s", e, exc_info=True)
            self.failed_services.append("portfolio_service")

        # 初始化MarketBoardService
        try:
            from backend.services.market_board_service import MarketBoardService

            market_board_service = MarketBoardService()
            init_success = market_board_service.initialize()

            if init_success:
                self.service_manager.register_service("market_board_service", market_board_service)
                self.initialized_services["market_board_service"] = market_board_service
                self.logger.info("✅ MarketBoardService 初始化成功")
                success_count += 1
            else:
                self.logger.warning("⚠️ MarketBoardService 初始化失败")
                self.failed_services.append("market_board_service")

        except Exception as e:
            self.logger.error("❌ MarketBoardService 初始化异常: %s", e, exc_info=True)
            self.failed_services.append("market_board_service")

        # 初始化SystemManagerService
        try:
            from backend.services.system_manager_service import SystemManagerService

            system_manager_service = SystemManagerService()
            init_success = system_manager_service.initialize()

            if init_success:
                self.service_manager.register_service(
                    "system_manager_service", system_manager_service
                )
                self.initialized_services["system_manager_service"] = system_manager_service
                self.logger.info("✅ SystemManagerService 初始化成功")
                success_count += 1
            else:
                self.logger.warning("⚠️ SystemManagerService 初始化失败")
                self.failed_services.append("system_manager_service")

        except Exception as e:
            self.logger.error("❌ SystemManagerService 初始化异常: %s", e, exc_info=True)
            self.failed_services.append("system_manager_service")

        return success_count > 0

    def _generate_initialization_report(self):
        """生成初始化报告."""
        self.logger.info("\n" + "=" * 60)
        self.logger.info("初始化报告")
        self.logger.info("=" * 60)

        total_services = len(self.initialized_services) + len(self.failed_services)
        success_count = len(self.initialized_services)
        failed_count = len(self.failed_services)

        self.logger.info("总服务数: %d", total_services)
        self.logger.info("成功初始化: %d", success_count)
        self.logger.info("初始化失败: %d", failed_count)

        if self.initialized_services:
            self.logger.info("\n✅ 成功的服务:")
            for name in self.initialized_services:
                self.logger.info("  - %s", name)

        if self.failed_services:
            self.logger.info("\n❌ 失败的服务:")
            for name in self.failed_services:
                self.logger.info("  - %s", name)

        self.logger.info("=" * 60)


def initialize_real_services() -> bool:
    """初始化所有服务的入口函数.

    Returns:
        bool: 是否初始化成功
    """
    from backend.core.shared_services import get_service_manager

    service_manager = get_service_manager()
    initializer = ServiceInitializer(service_manager)
    return initializer.initialize_all_services()


def shutdown_real_services() -> None:
    """关闭所有服务."""
    from backend.core.shared_services import get_service_manager, get_main_engine

    service_manager = get_service_manager()
    logger.info("开始关闭所有服务...")

    # 关闭所有业务服务
    for service_name, service in list(service_manager.services.items()):
        if service and hasattr(service, "shutdown"):
            try:
                service.shutdown()
                logger.info("✅ %s 已关闭", service_name)
            except Exception as e:
                logger.error("❌ 关闭 %s 失败: %s", service_name, e)

    # 关闭VNPY主引擎
    main_engine = get_main_engine()
    if main_engine:
        try:
            main_engine.close()
            logger.info("✅ MainEngine 已关闭")
        except Exception as e:
            logger.error("❌ 关闭 MainEngine 失败: %s", e)

    logger.info("所有服务已关闭")
