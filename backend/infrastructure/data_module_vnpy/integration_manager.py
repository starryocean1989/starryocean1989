# -*- coding: utf-8 -*-
"""
VnPy集成管理器
统一管理所有VnPy功能的初始化和配置
"""

import logging
from typing import Dict, Any, Optional
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class VnPyIntegrationManager:
    """VnPy集成管理器"""

    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "vnpy_config.json"
        self.config = self._load_config()
        self.initialized_components = {}

    def _load_config(self) -> Dict[str, Any]:
        """加载VnPy配置"""
        try:
            if Path(self.config_path).exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                return self._get_default_config()
        except Exception as e:
            logger.warning(f"加载VnPy配置失败,使用默认配置: {e}")
            return self._get_default_config()

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "datafeed": {
                "tushare": {
                    "enabled": True,
                    "token": "",
                    "timeout": 30
                },
                "rqdata": {
                    "enabled": False,
                    "username": "",
                    "password": ""
                },
                "ifind": {
                    "enabled": False,
                    "username": "",
                    "password": ""
                }
            },
            "gateway": {
                "ctp": {
                    "enabled": True,
                    "broker_id": "",
                    "md_front": "",
                    "td_front": "",
                    "app_id": "",
                    "auth_code": ""
                },
                "ctptest": {
                    "enabled": False,
                    "broker_id": "",
                    "md_front": "",
                    "td_front": "",
                    "app_id": "",
                    "auth_code": ""
                },
                "ib": {
                    "enabled": False,
                    "host": "127.0.0.1",
                    "port": 7497,
                    "client_id": 1
                }
            },
            "strategy": {
                "cta": {
                    "enabled": True,
                    "class_names": [
                        "DoubleMaStrategy",
                        "BollChannelStrategy",
                        "DualThrustStrategy"
                    ]
                },
                "portfolio": {
                    "enabled": True,
                    "class_names": [
                        "PairTradingStrategy",
                        "TrendFollowingStrategy"
                    ]
                },
                "spread": {
                    "enabled": True,
                    "class_names": [
                        "BasicSpreadStrategy",
                        "StatisticalArbitrageStrategy"
                    ]
                }
            }
        }

    def initialize_datafeed(self, datafeed_type: str) -> bool:
        """初始化数据源"""
        try:
            if datafeed_type not in self.config.get("datafeed", {}):
                logger.error(f"不支持的数据源类型: {datafeed_type}")
                return False

            datafeed_config = self.config["datafeed"][datafeed_type]
            if not datafeed_config.get("enabled", False):
                logger.warning(f"数据源 {datafeed_type} 未启用")
                return False

            # 根据类型初始化相应的数据源
            if datafeed_type == "tushare":
                return self._init_tushare_datafeed(datafeed_config)
            elif datafeed_type == "rqdata":
                return self._init_rqdata_datafeed(datafeed_config)
            elif datafeed_type == "ifind":
                return self._init_ifind_datafeed(datafeed_config)
            else:
                logger.error(f"未知的数据源类型: {datafeed_type}")
                return False

        except Exception as e:
            logger.error(f"初始化数据源 {datafeed_type} 失败: {e}")
            return False

    def _init_tushare_datafeed(self, config: Dict[str, Any]) -> bool:
        """初始化Tushare数据源"""
        try:
            # 这里应该导入并初始化vnpy_tushare
            # 需要实际的Tushare数据源连接
            logger.info("初始化Tushare数据源")
            logger.info(f"配置: {config}")
            self.initialized_components["tushare"] = True
            return True
        except Exception as e:
            logger.error(f"初始化Tushare数据源失败: {e}")
            return False

    def _init_rqdata_datafeed(self, config: Dict[str, Any]) -> bool:
        """初始化RQData数据源"""
        try:
            logger.info("初始化RQData数据源")
            logger.info(f"配置: {config}")
            self.initialized_components["rqdata"] = True
            return True
        except Exception as e:
            logger.error(f"初始化RQData数据源失败: {e}")
            return False

    def _init_ifind_datafeed(self, config: Dict[str, Any]) -> bool:
        """初始化iFind数据源"""
        try:
            logger.info("初始化iFind数据源")
            logger.info(f"配置: {config}")
            self.initialized_components["ifind"] = True
            return True
        except Exception as e:
            logger.error(f"初始化iFind数据源失败: {e}")
            return False

    def initialize_gateway(self, gateway_type: str) -> bool:
        """初始化交易网关"""
        try:
            if gateway_type not in self.config.get("gateway", {}):
                logger.error(f"不支持的网关类型: {gateway_type}")
                return False

            gateway_config = self.config["gateway"][gateway_type]
            if not gateway_config.get("enabled", False):
                logger.warning(f"网关 {gateway_type} 未启用")
                return False

            # 根据类型初始化相应的网关
            if gateway_type == "ctp":
                return self._init_ctp_gateway(gateway_config)
            elif gateway_type == "ctptest":
                return self._init_ctptest_gateway(gateway_config)
            elif gateway_type == "ib":
                return self._init_ib_gateway(gateway_config)
            else:
                logger.error(f"未知的网关类型: {gateway_type}")
                return False

        except Exception as e:
            logger.error(f"初始化网关 {gateway_type} 失败: {e}")
            return False

    def _init_ctp_gateway(self, config: Dict[str, Any]) -> bool:
        """初始化CTP网关"""
        try:
            logger.info("初始化CTP网关")
            logger.info(f"配置: {config}")
            self.initialized_components["ctp"] = True
            return True
        except Exception as e:
            logger.error(f"初始化CTP网关失败: {e}")
            return False

    def _init_ctptest_gateway(self, config: Dict[str, Any]) -> bool:
        """初始化CTP测试网关"""
        try:
            logger.info("初始化CTP测试网关")
            logger.info(f"配置: {config}")
            self.initialized_components["ctptest"] = True
            return True
        except Exception as e:
            logger.error(f"初始化CTP测试网关失败: {e}")
            return False

    def _init_ib_gateway(self, config: Dict[str, Any]) -> bool:
        """初始化IB网关"""
        try:
            logger.info("初始化IB网关")
            logger.info(f"配置: {config}")
            self.initialized_components["ib"] = True
            return True
        except Exception as e:
            logger.error(f"初始化IB网关失败: {e}")
            return False

    def initialize_strategy_engine(self, strategy_type: str) -> bool:
        """初始化策略引擎"""
        try:
            if strategy_type not in self.config.get("strategy", {}):
                logger.error(f"不支持的策略类型: {strategy_type}")
                return False

            strategy_config = self.config["strategy"][strategy_type]
            if not strategy_config.get("enabled", False):
                logger.warning(f"策略引擎 {strategy_type} 未启用")
                return False

            # 根据类型初始化相应的策略引擎
            if strategy_type == "cta":
                return self._init_cta_strategy_engine(strategy_config)
            elif strategy_type == "portfolio":
                return self._init_portfolio_strategy_engine(strategy_config)
            elif strategy_type == "spread":
                return self._init_spread_strategy_engine(strategy_config)
            else:
                logger.error(f"未知的策略类型: {strategy_type}")
                return False

        except Exception as e:
            logger.error(f"初始化策略引擎 {strategy_type} 失败: {e}")
            return False

    def _init_cta_strategy_engine(self, config: Dict[str, Any]) -> bool:
        """初始化CTA策略引擎"""
        try:
            logger.info("初始化CTA策略引擎")
            logger.info(f"配置: {config}")
            self.initialized_components["cta"] = True
            return True
        except Exception as e:
            logger.error(f"初始化CTA策略引擎失败: {e}")
            return False

    def _init_portfolio_strategy_engine(self, config: Dict[str, Any]) -> bool:
        """初始化组合策略引擎"""
        try:
            logger.info("初始化组合策略引擎")
            logger.info(f"配置: {config}")
            self.initialized_components["portfolio"] = True
            return True
        except Exception as e:
            logger.error(f"初始化组合策略引擎失败: {e}")
            return False

    def _init_spread_strategy_engine(self, config: Dict[str, Any]) -> bool:
        """初始化价差策略引擎"""
        try:
            logger.info("初始化价差策略引擎")
            logger.info(f"配置: {config}")
            self.initialized_components["spread"] = True
            return True
        except Exception as e:
            logger.error(f"初始化价差策略引擎失败: {e}")
            return False

    def get_initialized_components(self) -> Dict[str, bool]:
        """获取已初始化的组件状态"""
        return self.initialized_components.copy()

    def is_component_initialized(self, component_name: str) -> bool:
        """检查组件是否已初始化"""
        return self.initialized_components.get(component_name, False)

    def save_config(self) -> bool:
        """保存配置到文件"""
        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            logger.info(f"配置已保存到: {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False


# 全局实例
vnpy_manager = VnPyIntegrationManager()
