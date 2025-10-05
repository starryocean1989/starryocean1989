# -*- coding: utf-8 -*-
"""
工厂模式实现模块.

提供统一的网关、策略、数据源创建和管理.
"""
import logging
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING, Type

from .imports import (
    AlgoEngine,
    CtaEngine,
    CtpGateway,
    IbGateway,
    MiniGateway,
    ModuleAvailability,
    PortfolioEngine,
    RqdataDatafeed,
    TushareDatafeed
)

if TYPE_CHECKING:
    from .vnpy_integration import TerminalEngine


class GatewayType(Enum):
    """网关类型枚举."""

    CTP = "ctp"           # 国内期货CTP
    MINI = "mini"         # 期货迷你版
    IB = "ib"             # 国际市场IB
    PAPER = "paper"       # 模拟交易
    TDX = "tdx"           # 通达信股票
    TTS = "tts"           # 期货仿真


class StrategyType(Enum):
    """策略类型枚举."""

    CTA = "cta"           # CTA策略
    ALGO = "algo"         # 算法交易
    PORTFOLIO = "portfolio"  # 组合策略
    SPREAD = "spread"     # 价差交易
    SCRIPT = "script"     # 脚本交易
    OPTION = "option"     # 期权策略


class DatafeedType(Enum):
    """数据源类型枚举."""

    TUSHARE = "tushare"   # 聚宽数据
    RQDATA = "rqdata"     # 米筐数据
    VNPY_RECORDER = "vnpy_recorder"  # VNPY录制器
    LOCAL_DB = "local_db"  # 本地数据库


class GatewayFactory:
    """网关工厂."""

    def __init__(self, terminal_engine: "TerminalEngine") -> None:
        """初始化网关工厂."""
        self.terminal_engine = terminal_engine
        self.logger = logging.getLogger(__name__)
        self._gateway_configs: Dict[str, Dict[str, Any]] = {}
        self._gateway_instances: Dict[str, Any] = {}

    def register_gateway_type(self, gateway_type: GatewayType,
                              gateway_class: Type,
                              default_config: Dict[str, Any] = None) -> None:
        """注册网关类型."""
        self._gateway_configs[gateway_type.value] = {
            "class": gateway_class,
            "config": default_config or {}
        }
        self.logger.info("注册网关类型: %s", gateway_type.value)

    def create_gateway(self, gateway_name: str, gateway_type: GatewayType,
                       config: Dict[str, Any] = None) -> Optional[Any]:
        """创建网关实例."""
        if gateway_type.value not in self._gateway_configs:
            self.logger.error("未注册的网关类型: %s", gateway_type.value)
            return None

        try:
            gateway_config = self._gateway_configs[gateway_type.value]
            gateway_class = gateway_config["class"]

            # 合并配置
            final_config = gateway_config["config"].copy()
            if config:
                final_config.update(config)

            # 创建网关实例
            gateway = self.terminal_engine.add_gateway(
                gateway_name, gateway_class, **final_config)

            if gateway:
                self._gateway_instances[gateway_name] = {
                    "type": gateway_type,
                    "instance": gateway,
                    "config": final_config
                }
                self.logger.info("网关创建成功: %s (%s)",
                                 gateway_name, gateway_type.value)

            return gateway

        except (ImportError, AttributeError, TypeError, OSError) as e:
            self.logger.error("创建网关失败 %s: %s", gateway_name, e)
            return None

    def connect_gateway(self, gateway_name: str,
                        connection_config: Dict[str, Any]) -> bool:
        """连接网关."""
        if gateway_name not in self._gateway_instances:
            self.logger.error("网关未找到: %s", gateway_name)
            return False

        return self.terminal_engine.connect_gateway(
            gateway_name, **connection_config)

    def disconnect_gateway(self, gateway_name: str) -> bool:
        """断开网关连接."""
        if gateway_name not in self._gateway_instances:
            self.logger.error("网关未找到: %s", gateway_name)
            return False

        try:
            gateway = self._gateway_instances[gateway_name]["instance"]
            if hasattr(gateway, 'close'):
                gateway.close()
                self.logger.info("网关断开成功: %s", gateway_name)
                return True
        except (ImportError, AttributeError, TypeError, OSError) as e:
            self.logger.error("断开网关失败 %s: %s", gateway_name, e)

        return False

    def get_gateway(self, gateway_name: str) -> Optional[Any]:
        """获取网关实例."""
        if gateway_name in self._gateway_instances:
            return self._gateway_instances[gateway_name]["instance"]
        return None

    def list_gateways(self) -> List[Dict[str, Any]]:
        """列出所有网关."""
        return [
            {
                "name": name,
                "type": info["type"].value,
                "connected": getattr(info["instance"], 'connected', False),
                "trading": getattr(info["instance"], 'trading', False)
            }
            for name, info in self._gateway_instances.items()
        ]

    def remove_gateway(self, gateway_name: str) -> bool:
        """移除网关."""
        if gateway_name in self._gateway_instances:
            try:
                # 先断开连接
                self.disconnect_gateway(gateway_name)

                # 移除实例
                del self._gateway_instances[gateway_name]
                self.logger.info("网关移除成功: %s", gateway_name)
                return True
            except (ImportError, AttributeError, TypeError, OSError) as e:
                self.logger.error("移除网关失败 %s: %s", gateway_name, e)

        return False


class StrategyFactory:
    """策略工厂."""

    def __init__(self, terminal_engine: "TerminalEngine") -> None:
        """初始化策略工厂."""
        self.terminal_engine = terminal_engine
        self.logger = logging.getLogger(__name__)
        self._strategy_configs: Dict[str, Dict[str, Any]] = {}
        self._strategy_instances: Dict[str, Any] = {}

    def register_strategy_type(self, strategy_type: StrategyType,
                               engine_name: str,
                               default_config: Dict[str, Any] = None) -> None:
        """注册策略类型."""
        self._strategy_configs[strategy_type.value] = {
            "engine": engine_name,
            "config": default_config or {}
        }
        self.logger.info("注册策略类型: %s -> %s", strategy_type.value, engine_name)

    def create_strategy(self, strategy_name: str, strategy_type: StrategyType,
                        strategy_class: Type,
                        config: Dict[str, Any] = None) -> Optional[Any]:
        """创建策略实例."""
        if strategy_type.value not in self._strategy_configs:
            self.logger.error("未注册的策略类型: %s", strategy_type.value)
            return None

        try:
            engine_name = self._strategy_configs[strategy_type.value]["engine"]

            if engine_name not in self.terminal_engine.strategy_engines:
                self.logger.error("策略引擎未找到: %s", engine_name)
                return None

            # 合并配置
            final_config = self._strategy_configs[strategy_type.value][
                "config"].copy()
            if config:
                final_config.update(config)

            # 创建策略实例
            strategy = self.terminal_engine.start_strategy(
                strategy_name, strategy_class, **final_config)

            if strategy:
                self._strategy_instances[strategy_name] = {
                    "type": strategy_type,
                    "class": strategy_class,
                    "instance": strategy,
                    "engine": engine_name,
                    "config": final_config
                }
                self.logger.info("策略创建成功: %s (%s)",
                                 strategy_name, strategy_type.value)

            return strategy

        except (ImportError, AttributeError, TypeError, OSError) as e:
            self.logger.error("创建策略失败 %s: %s", strategy_name, e)
            return None

    def start_strategy(self, strategy_name: str) -> bool:
        """启动策略."""
        if strategy_name not in self._strategy_instances:
            self.logger.error("策略未找到: %s", strategy_name)
            return False

        try:
            strategy_info = self._strategy_instances[strategy_name]
            engine = self.terminal_engine.strategy_engines[
                strategy_info["engine"]]

            # 这里需要根据具体引擎的API来启动策略
            # 不同引擎的启动方式可能不同
            if hasattr(engine, 'start_strategy'):
                engine.start_strategy(strategy_name)
                self.logger.info("策略启动成功: %s", strategy_name)
                return True

        except (ImportError, AttributeError, TypeError, OSError) as e:
            self.logger.error("启动策略失败 %s: %s", strategy_name, e)

        return False

    def stop_strategy(self, strategy_name: str) -> bool:
        """停止策略."""
        if strategy_name not in self._strategy_instances:
            self.logger.error("策略未找到: %s", strategy_name)
            return False

        try:
            strategy_info = self._strategy_instances[strategy_name]
            engine = self.terminal_engine.strategy_engines[
                strategy_info["engine"]]

            # 这里需要根据具体引擎的API来停止策略
            if hasattr(engine, 'stop_strategy'):
                engine.stop_strategy(strategy_name)
                self.logger.info("策略停止成功: %s", strategy_name)
                return True

        except (ImportError, AttributeError, TypeError, OSError) as e:
            self.logger.error("停止策略失败 %s: %s", strategy_name, e)

        return False

    def list_strategies(self) -> List[Dict[str, Any]]:
        """列出所有策略."""
        strategies = []

        for engine_name, engine in \
                self.terminal_engine.strategy_engines.items():
            if hasattr(engine, 'strategies'):
                for strategy_name, strategy in engine.strategies.items():
                    strategies.append({
                        "name": strategy_name,
                        "engine": engine_name,
                        "active": getattr(strategy, 'active', False),
                        "trading": getattr(strategy, 'trading', False)
                    })

        return strategies

    def remove_strategy(self, strategy_name: str) -> bool:
        """移除策略."""
        if strategy_name in self._strategy_instances:
            try:
                # 先停止策略
                self.stop_strategy(strategy_name)

                # 移除实例
                del self._strategy_instances[strategy_name]
                self.logger.info("策略移除成功: %s", strategy_name)
                return True
            except (ImportError, AttributeError, TypeError, OSError) as e:
                self.logger.error("移除策略失败 %s: %s", strategy_name, e)

        return False


class DatafeedFactory:
    """数据源工厂."""

    def __init__(self, terminal_engine: "TerminalEngine") -> None:
        """初始化数据源工厂."""
        self.terminal_engine = terminal_engine
        self.logger = logging.getLogger(__name__)
        self._datafeed_configs: Dict[str, Dict[str, Any]] = {}
        self._datafeed_instances: Dict[str, Any] = {}

    def register_datafeed_type(self, datafeed_type: DatafeedType,
                               datafeed_class: Type,
                               default_config: Dict[str, Any] = None) -> None:
        """注册数据源类型."""
        self._datafeed_configs[datafeed_type.value] = {
            "class": datafeed_class,
            "config": default_config or {}
        }
        self.logger.info("注册数据源类型: %s", datafeed_type.value)

    def create_datafeed(self, datafeed_name: str, datafeed_type: DatafeedType,
                        config: Dict[str, Any] = None) -> Optional[Any]:
        """创建数据源实例."""
        if datafeed_type.value not in self._datafeed_configs:
            self.logger.error("未注册的数据源类型: %s", datafeed_type.value)
            return None

        try:
            datafeed_config = self._datafeed_configs[datafeed_type.value]
            datafeed_class = datafeed_config["class"]

            # 合并配置
            final_config = datafeed_config["config"].copy()
            if config:
                final_config.update(config)

            # 创建数据源实例
            datafeed = self.terminal_engine.add_datafeed(
                datafeed_name, datafeed_class, **final_config)

            if datafeed:
                self._datafeed_instances[datafeed_name] = {
                    "type": datafeed_type,
                    "instance": datafeed,
                    "config": final_config
                }
                self.logger.info("数据源创建成功: %s (%s)",
                                 datafeed_name, datafeed_type.value)

            return datafeed

        except (ImportError, AttributeError, TypeError, OSError) as e:
            self.logger.error("创建数据源失败 %s: %s", datafeed_name, e)
            return None

    def subscribe_symbol(self, datafeed_name: str, symbol: str,
                         exchange: str = "") -> bool:
        """订阅行情数据."""
        if datafeed_name not in self._datafeed_instances:
            self.logger.error("数据源未找到: %s", datafeed_name)
            return False

        try:
            datafeed = self._datafeed_instances[datafeed_name]["instance"]
            if hasattr(datafeed, 'subscribe'):
                datafeed.subscribe(symbol, exchange)
                self.logger.info("订阅成功: %s -> %s", datafeed_name, symbol)
                return True
        except (ImportError, AttributeError, TypeError, OSError) as e:
            self.logger.error("订阅失败 %s -> %s: %s", datafeed_name, symbol, e)

        return False

    def unsubscribe_symbol(self, datafeed_name: str, symbol: str,
                           exchange: str = "") -> bool:
        """取消订阅行情数据."""
        if datafeed_name not in self._datafeed_instances:
            self.logger.error("数据源未找到: %s", datafeed_name)
            return False

        try:
            datafeed = self._datafeed_instances[datafeed_name]["instance"]
            if hasattr(datafeed, 'unsubscribe'):
                datafeed.unsubscribe(symbol, exchange)
                self.logger.info("取消订阅成功: %s -> %s", datafeed_name, symbol)
                return True
        except (ImportError, AttributeError, TypeError, OSError) as e:
            self.logger.error("取消订阅失败 %s -> %s: %s", datafeed_name, symbol, e)

        return False

    def list_datafeeds(self) -> List[Dict[str, Any]]:
        """列出所有数据源."""
        return [
            {
                "name": name,
                "type": info["type"].value,
                "connected": getattr(info["instance"], 'connected', False),
                "symbols": getattr(info["instance"], 'subscribed_symbols', [])
            }
            for name, info in self._datafeed_instances.items()
        ]

    def remove_datafeed(self, datafeed_name: str) -> bool:
        """移除数据源."""
        if datafeed_name in self._datafeed_instances:
            try:
                # 先取消所有订阅
                datafeed = self._datafeed_instances[datafeed_name]["instance"]
                if hasattr(datafeed, 'subscribed_symbols'):
                    for symbol in datafeed.subscribed_symbols:
                        if hasattr(datafeed, 'unsubscribe'):
                            datafeed.unsubscribe(symbol)

                # 移除实例
                del self._datafeed_instances[datafeed_name]
                self.logger.info("数据源移除成功: %s", datafeed_name)
                return True
            except (ImportError, AttributeError, TypeError, OSError) as e:
                self.logger.error("移除数据源失败 %s: %s", datafeed_name, e)

        return False


class UnifiedFactory:
    """统一工厂，整合所有工厂."""

    def __init__(self, terminal_engine: "TerminalEngine") -> None:
        """初始化统一工厂."""
        self.terminal_engine = terminal_engine
        self.logger = logging.getLogger(__name__)

        # 初始化子工厂
        self.gateway_factory = GatewayFactory(terminal_engine)
        self.strategy_factory = StrategyFactory(terminal_engine)
        self.datafeed_factory = DatafeedFactory(terminal_engine)

        # 自动注册可用类型
        self._auto_register_types()

    def _auto_register_types(self) -> None:
        """自动注册可用类型."""
        # 注册网关类型
        if (ModuleAvailability.CTP_GATEWAY and CtpGateway):
            self.gateway_factory.register_gateway_type(
                GatewayType.CTP, CtpGateway,
                {"setting": {"用户名": "", "密码": "", "经纪商代码": "",
                             "交易服务器": "", "行情服务器": ""}}
            )

        if (ModuleAvailability.MINI_GATEWAY and MiniGateway):
            self.gateway_factory.register_gateway_type(
                GatewayType.MINI, MiniGateway,
                {"setting": {"用户名": "", "密码": "", "经纪商代码": "",
                             "地址": "", "端口": 0}}
            )

        if ModuleAvailability.IB_GATEWAY and IbGateway:
            self.gateway_factory.register_gateway_type(
                GatewayType.IB, IbGateway,
                {"setting": {"TWS地址": "127.0.0.1", "TWS端口": 7497, "客户端ID": 1}}
            )

        # 注册策略类型
        if ModuleAvailability.CTA_ENGINE and CtaEngine:
            self.strategy_factory.register_strategy_type(
                StrategyType.CTA, "cta",
                {"class_params": {}, "strategy_params": {}}
            )

        if ModuleAvailability.ALGO_ENGINE and AlgoEngine:
            self.strategy_factory.register_strategy_type(
                StrategyType.ALGO, "algo",
                {"class_params": {}, "strategy_params": {}}
            )

        if ModuleAvailability.PORTFOLIO_ENGINE and PortfolioEngine:
            self.strategy_factory.register_strategy_type(
                StrategyType.PORTFOLIO, "portfolio",
                {"class_params": {}, "strategy_params": {}}
            )

        # 注册数据源类型
        if ModuleAvailability.TUSHARE_DATAFEED and TushareDatafeed:
            self.datafeed_factory.register_datafeed_type(
                DatafeedType.TUSHARE, TushareDatafeed,
                {"token": "", "symbols": []}
            )

        if ModuleAvailability.RQDATA_DATAFEED and RqdataDatafeed:
            self.datafeed_factory.register_datafeed_type(
                DatafeedType.RQDATA, RqdataDatafeed,
                {"username": "", "password": "", "symbols": []}
            )

        self.logger.info("类型注册完成")

    def get_status(self) -> Dict[str, Any]:
        """获取工厂状态."""
        return {
            "gateway_count": len(self.gateway_factory.list_gateways()),
            "strategy_count": len(self.strategy_factory.list_strategies()),
            "datafeed_count": len(self.datafeed_factory.list_datafeeds()),
            "gateways": self.gateway_factory.list_gateways(),
            "strategies": self.strategy_factory.list_strategies(),
            "datafeeds": self.datafeed_factory.list_datafeeds()
        }

    def get_gateway_factory(self) -> GatewayFactory:
        """获取网关工厂."""
        return self.gateway_factory

    def get_strategy_factory(self) -> StrategyFactory:
        """获取策略工厂."""
        return self.strategy_factory

    def get_datafeed_factory(self) -> DatafeedFactory:
        """获取数据源工厂."""
        return self.datafeed_factory


# 导出公共接口
__all__ = [
    # 枚举类型
    'GatewayType', 'StrategyType', 'DatafeedType',

    # 工厂类
    'GatewayFactory', 'StrategyFactory', 'DatafeedFactory', 'UnifiedFactory'
]
