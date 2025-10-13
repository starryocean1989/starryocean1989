# -*- coding: utf-8 -*-
"""
交易网关服务.

提供完整的交易网关管理功能，包括：
- 7种网关的注册和管理（CTP, CTP mini, Sopt, TTS, IB, PaperAccount, TradeX Gateway）
- 策略实例管理（策略池、部署、控制）
- 交易监控（6种策略模板适配、交易数据、风险监控）
"""

import contextlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum

from backend.services.base_and_utils import BaseService


class GatewayType(Enum):
    """网关类型枚举."""

    CTP = "ctp"  # 国内期货、期权
    CTP_MINI = "ctp_mini"  # 国内期货、期权（迷你版）
    SOPT = "sopt"  # 国内ETF期权
    TTS = "tts"  # 国内期货仿真交易
    IB = "ib"  # 海外证券、期货、期权、贵金属
    PAPER_ACCOUNT = "paperaccount"  # 纯本地模拟交易
    TRADEX_GATEWAY = "tdx"  # 国内股票交易（TradeX标准接口）


class StrategyEngineType(Enum):
    """策略引擎类型枚举."""

    ALGO_TRADING = "algotrading"  # 算法交易
    CTA_STRATEGY = "ctastrategy"  # CTA策略
    OPTION_MASTER = "optionmaster"  # 期权策略
    PORTFOLIO_STRATEGY = "portfoliostrategy"  # 组合策略
    SCRIPT_TRADER = "scripttrader"  # 脚本交易
    SPREAD_TRADING = "spreadtrading"  # 价差交易


class TradingGatewayService(BaseService):
    """交易网关服务.

    管理所有交易网关和策略实例，提供：
    1. 网关管理 - 创建、连接、断开、删除7种网关
    2. 策略池管理 - 策略部署、启动、停止、删除
    3. 交易监控 - 订单、成交、持仓、资金、日志监控
    4. 风险管理 - 风险指标、预警、限额管理
    """

    # 策略引擎名称映射（小写格式 -> VnPy引擎名称）
    ENGINE_NAME_MAP = {
        "ctastrategy": "CtaStrategy",
        "algotrading": "AlgoTrading",
        "optionmaster": "OptionMaster",
        "portfoliostrategy": "PortfolioStrategy",
        "scripttrader": "ScriptTrader",
        "spreadtrading": "SpreadTrading",
    }

    # 策略应用类映射（引擎名称 -> (模块名, 类名)）
    APP_CLASS_MAP = {
        "CtaStrategy": ("vnpy_ctastrategy", "CtaStrategyApp"),
        "AlgoTrading": ("vnpy_algotrading", "AlgoTradingApp"),
        "OptionMaster": ("vnpy_optionmaster", "OptionMasterApp"),
        "PortfolioStrategy": ("vnpy_portfoliostrategy", "PortfolioStrategyApp"),
        "ScriptTrader": ("vnpy_scripttrader", "ScriptTraderApp"),
        "SpreadTrading": ("vnpy_spreadtrading", "SpreadTradingApp"),
    }

    # 友好的策略类型名称
    ENGINE_DISPLAY_NAMES = {
        "CtaStrategy": "CTA策略",
        "AlgoTrading": "算法交易",
        "OptionMaster": "期权分析",
        "PortfolioStrategy": "组合策略",
        "ScriptTrader": "脚本交易",
        "SpreadTrading": "价差交易",
    }

    # 支持策略池部署的引擎（其他引擎有不同的使用方式）
    STRATEGY_POOL_SUPPORTED_ENGINES = {
        "CtaStrategy",  # ✅ CTA策略 - 支持add_strategy
        "PortfolioStrategy",  # ✅ 组合策略 - 支持add_strategy
        "SpreadTrading",  # ✅ 价差交易 - 支持add_strategy
    }

    @staticmethod
    def _check_package_installed(module_name: str) -> bool:
        """动态检测包是否已安装.

        Args:
            module_name: 模块名称

        Returns:
            bool: 是否已安装
        """
        try:
            import importlib.util

            spec = importlib.util.find_spec(module_name)
            return spec is not None
        except (ImportError, ValueError, AttributeError):
            return False

    def __init__(self):
        """初始化交易网关服务."""
        super().__init__()

        # 记录已加载的策略应用
        self.loaded_apps = set()

        # 网关实例管理
        self.gateway_instances: Dict[str, Dict[str, Any]] = {}

        # 策略实例管理（按网关组织）
        self.strategy_instances: Dict[str, Dict[str, Any]] = {}

        # 网关配置模板
        self.gateway_config_templates = self._init_gateway_templates()

        # 网关类字典（在 _do_initialize 中填充）
        self.gateway_classes: Dict[str, Any] = {}

        # 风险管理引擎
        self.risk_engine = None

        # 配置文件路径
        self.config_file = Path("config/terminal_config.json")

        self.logger.info("交易网关服务已创建")

    def _do_initialize(self) -> bool:
        """初始化交易网关服务."""
        try:
            self.logger.info("初始化交易网关服务...")

            # 检查main_engine是否可用
            if self.main_engine is None:
                self.logger.warning("MainEngine不可用，部分功能受限")
                return True  # 仍然允许服务启动

            # 初始化网关类
            self._init_gateway_classes()

            # 初始化风险管理引擎
            self._init_risk_manager()

            # 加载已保存的网关配置
            self._load_gateway_configs()

            return True

        except Exception as e:
            self._log_error("初始化", e)
            return False

    def _do_shutdown(self) -> bool:
        """关闭交易网关服务."""
        try:
            self.logger.info("关闭交易网关服务...")

            # 停止所有策略
            self._stop_all_strategies()

            # 断开所有网关
            self._disconnect_all_gateways()

            return True
        except Exception as e:
            self._log_error("关闭", e)
            return False

    def _do_health_check(self) -> Dict[str, Any]:
        """健康检查."""
        return {
            "main_engine_available": self.main_engine is not None,
            "gateway_count": len(self.gateway_instances),
            "connected_gateways": sum(
                1 for g in self.gateway_instances.values() if g.get("connected", False)
            ),
            "total_strategies": sum(
                len(strategies) for strategies in self.strategy_instances.values()
            ),
            "active_strategies": sum(
                1
                for strategies in self.strategy_instances.values()
                for s in strategies.values()
                if s.get("status") == "running"
            ),
        }

    def _init_gateway_templates(self) -> Dict[str, Dict[str, Any]]:
        """初始化网关配置模板.

        Returns:
            Dict: 网关类型 -> 配置模板
        """
        return {
            GatewayType.CTP.value: {
                "name": "CTP",
                "description": "国内期货、期权",
                "requires_address": True,
                "config_fields": [
                    "服务器地址",
                    "用户名",
                    "密码",
                    "经纪商代码",
                    "产品名称",
                    "授权编码",
                ],
            },
            GatewayType.CTP_MINI.value: {
                "name": "CTP Mini",
                "description": "国内期货、期权（迷你版）",
                "requires_address": True,
                "config_fields": ["服务器地址", "用户名", "密码", "经纪商代码"],
            },
            GatewayType.SOPT.value: {
                "name": "Sopt",
                "description": "国内ETF期权",
                "requires_address": True,
                "config_fields": ["服务器地址", "用户名", "密码", "授权码"],
            },
            GatewayType.TTS.value: {
                "name": "TTS",
                "description": "国内期货仿真交易",
                "requires_address": True,
                "config_fields": ["服务器地址", "用户名", "密码"],
            },
            GatewayType.IB.value: {
                "name": "IB",
                "description": "海外证券、期货、期权、贵金属",
                "requires_address": True,
                "config_fields": ["服务器地址", "客户号", "账户ID"],
            },
            GatewayType.PAPER_ACCOUNT.value: {
                "name": "PaperAccount",
                "description": "纯本地模拟交易",
                "requires_address": False,  # 不需要地址
                "config_fields": ["初始资金"],
            },
            GatewayType.TRADEX_GATEWAY.value: {
                "name": "TradeX",
                "description": "国内股票交易（TradeX标准接口）",
                "requires_address": True,
                "config_fields": [
                    "服务器IP",
                    "服务器端口",
                    "客户端版本",
                    "营业部ID",
                    "登录账号",
                    "交易账号",
                    "交易密码",
                    "通讯密码",
                ],
            },
        }

    def _init_gateway_classes(self):
        """初始化网关类（尝试导入）."""
        try:
            # 尝试导入各种网关类
            self.gateway_classes = {}

            # CTP
            try:
                from vnpy_ctp import CtpGateway

                self.gateway_classes[GatewayType.CTP.value] = CtpGateway
                self.logger.info("✅ CTP网关类可用")
            except ImportError:
                self.logger.warning("⚠️ CTP网关类不可用")

            # PaperAccount（使用适配器集成）
            try:
                from backend.infrastructure.gateway_adapters import PaperAccountGateway

                self.gateway_classes[GatewayType.PAPER_ACCOUNT.value] = PaperAccountGateway
                self.logger.info("✅ PaperAccount网关类可用")
            except ImportError:
                self.logger.warning("⚠️ PaperAccount网关类不可用")

            # CTP Mini
            try:
                from vnpy_mini import MiniGateway

                self.gateway_classes[GatewayType.CTP_MINI.value] = MiniGateway
                self.logger.info("✅ CTP Mini网关类可用")
            except ImportError:
                self.logger.warning("⚠️ CTP Mini网关类不可用")

            # Sopt
            try:
                from vnpy_sopt import SoptGateway

                self.gateway_classes[GatewayType.SOPT.value] = SoptGateway
                self.logger.info("✅ Sopt网关类可用")
            except ImportError:
                self.logger.warning("⚠️ Sopt网关类不可用")

            # TTS
            try:
                from vnpy_tts import TtsGateway

                self.gateway_classes[GatewayType.TTS.value] = TtsGateway
                self.logger.info("✅ TTS网关类可用")
            except ImportError:
                self.logger.warning("⚠️ TTS网关类不可用")

            # IB (Interactive Brokers)
            try:
                from vnpy_ib import IbGateway

                self.gateway_classes[GatewayType.IB.value] = IbGateway
                self.logger.info("✅ IB网关类可用")
            except ImportError:
                # IB网关是可选功能，降低日志级别
                self.logger.debug("⚠️ IB网关类不可用")

            # TradeX Gateway（国内股票交易）
            try:
                from backend.infrastructure.gateway_adapters import TradeXGateway

                self.gateway_classes[GatewayType.TRADEX_GATEWAY.value] = TradeXGateway
                self.logger.info("✅ TradeX网关类可用")
            except ImportError:
                self.logger.warning("⚠️ TradeX网关类不可用")

        except Exception as e:
            self.logger.error("初始化网关类失败: %s", e, exc_info=True)

    def _init_risk_manager(self):
        """初始化风险管理引擎."""
        try:
            if not self.main_engine:
                self.logger.warning("MainEngine不可用，无法初始化风险管理")
                return

            # 尝试导入vnpy_riskmanager
            try:
                from vnpy_riskmanager import RiskManagerApp

                # 添加风险管理应用到MainEngine
                self.risk_engine = self.main_engine.add_app(RiskManagerApp)

                if self.risk_engine:
                    self.logger.info("✅ 风险管理引擎初始化成功")

                    # 设置默认风控参数
                    self._set_default_risk_parameters()
                else:
                    self.logger.warning("⚠️ 风险管理引擎获取失败")

            except ImportError:
                self.logger.warning("⚠️ vnpy_riskmanager未安装")

        except Exception as e:
            self.logger.error("风险管理引擎初始化失败: %s", e, exc_info=True)

    def _set_default_risk_parameters(self):
        """设置默认风控参数."""
        if not self.risk_engine:
            return

        try:
            # 设置默认风控参数
            default_params = {
                "order_flow_limit": 50,  # 单位时间内委托流量限制
                "order_flow_clear": 1,  # 委托流量清空时间（秒）
                "order_size_limit": 1000,  # 单笔委托数量限制
                "order_cancel_limit": 100,  # 单位时间内撤单次数限制
                "trade_limit": 100,  # 单位时间内成交限制
                "active_order_limit": 50,  # 活动委托数量限制
            }

            if hasattr(self.risk_engine, "update_setting"):
                self.risk_engine.update_setting(default_params)
                self.logger.info("风控参数已设置")

        except Exception as e:
            # 风控参数设置失败是常见情况，降低日志级别
            self.logger.debug("设置风控参数失败: %s", e)

    def _load_gateway_configs(self):
        """从配置文件加载网关配置."""
        try:
            if not self.config_file.exists():
                self.logger.info("配置文件不存在，跳过网关配置加载")
                return

            with open(self.config_file, "r", encoding="utf-8") as f:
                config = json.load(f)

            gateways = config.get("gateways", [])
            if not gateways:
                self.logger.info("没有保存的网关配置")
                return

            self.logger.info(f"开始加载 {len(gateways)} 个网关配置")

            for gateway_config in gateways:
                gateway_name = gateway_config.get("name")
                gateway_type = gateway_config.get("type")
                config_data = gateway_config.get("config", {})

                if not gateway_name or not gateway_type:
                    self.logger.warning(f"无效的网关配置: {gateway_config}")
                    continue

                # 创建网关实例
                result = self.create_gateway(gateway_name, gateway_type, config_data)

                if result.get("success"):
                    self.logger.info(f"✓ 网关 '{gateway_name}' 加载成功")
                else:
                    self.logger.warning(
                        f"✗ 网关 '{gateway_name}' 加载失败: {result.get('message')}"
                    )

            self.logger.info("网关配置加载完成")

        except Exception as e:
            self.logger.error(f"加载网关配置失败: {e}", exc_info=True)

    def _save_gateway_configs(self):
        """保存网关配置到配置文件."""
        try:
            # 读取现有配置
            if self.config_file.exists():
                with open(self.config_file, "r", encoding="utf-8") as f:
                    config = json.load(f)
            else:
                config = {}

            # 构建网关配置列表
            gateways = []
            for name, info in self.gateway_instances.items():
                gateway_config = {
                    "name": name,
                    "type": info["type"],
                    "config": info["config"],
                }
                gateways.append(gateway_config)

            # 更新配置
            config["gateways"] = gateways

            # 保存到文件
            with open(self.config_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            self.logger.info(f"网关配置已保存，共 {len(gateways)} 个网关")

        except Exception as e:
            self.logger.error(f"保存网关配置失败: {e}", exc_info=True)

    # ==================== 网关管理 ====================

    def get_gateway_types(self) -> List[Dict[str, Any]]:
        """获取支持的网关类型列表.

        Returns:
            List[Dict]: 网关类型信息列表
        """
        gateway_types = []
        for gw_type, template in self.gateway_config_templates.items():
            gateway_types.append(
                {
                    "type": gw_type,
                    "name": template["name"],
                    "description": template["description"],
                    "requires_address": template["requires_address"],
                    "config_fields": template["config_fields"],
                }
            )
        return gateway_types

    def create_gateway(
        self, gateway_name: str, gateway_type: str, config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """创建网关实例.

        Args:
            gateway_name: 网关实例名称（用户自定义）
            gateway_type: 网关类型（GatewayType枚举值）
            config: 网关配置（根据类型不同而不同）

        Returns:
            Dict: 创建结果
        """
        try:
            self._log_operation("创建网关", name=gateway_name, type=gateway_type)

            # 检查网关名称是否已存在
            if gateway_name in self.gateway_instances:
                return {
                    "success": False,
                    "message": f"网关名称 '{gateway_name}' 已存在",
                }

            # 检查网关类型是否支持
            if gateway_type not in self.gateway_config_templates:
                return {
                    "success": False,
                    "message": f"不支持的网关类型: {gateway_type}",
                }

            # 检查main_engine
            if self.main_engine is None:
                return {
                    "success": False,
                    "message": "MainEngine不可用",
                }

            # 获取网关类
            gateway_class = self.gateway_classes.get(gateway_type)
            if gateway_class is None:
                return {
                    "success": False,
                    "message": f"网关类 '{gateway_type}' 未安装或不可用",
                }

            # 添加网关类到MainEngine（如果尚未添加）
            self.main_engine.add_gateway(gateway_class)
            self.logger.info("网关类 %s 已注册到MainEngine", gateway_type)

            # 保存网关实例信息（实际的网关实例在connect时创建）
            self.gateway_instances[gateway_name] = {
                "name": gateway_name,
                "type": gateway_type,
                "gateway_class": gateway_class,
                "config": config,
                "connected": False,
                "create_time": datetime.now(),
            }

            # 初始化该网关的策略池
            self.strategy_instances[gateway_name] = {}

            self.logger.info("网关 '%s' (类型: %s) 创建成功", gateway_name, gateway_type)

            # 保存网关配置到文件
            self._save_gateway_configs()

            return {
                "success": True,
                "message": f"网关 '{gateway_name}' 创建成功",
                "gateway_name": gateway_name,
                "gateway_type": gateway_type,
            }

        except Exception as e:
            self._log_error("创建网关", e, name=gateway_name, type=gateway_type)
            return {
                "success": False,
                "message": f"创建失败: {str(e)}",
            }

    def connect_gateway(self, gateway_name: str, password: Optional[str] = None) -> Dict[str, Any]:
        """连接网关.

        Args:
            gateway_name: 网关名称
            password: 密码（部分网关需要）

        Returns:
            Dict: 连接结果
        """
        try:
            self._log_operation("连接网关", name=gateway_name)

            if gateway_name not in self.gateway_instances:
                return {
                    "success": False,
                    "message": f"网关 '{gateway_name}' 不存在",
                }

            gateway_info = self.gateway_instances[gateway_name]
            gateway_type = gateway_info["type"]

            # 准备连接配置
            connect_setting = gateway_info["config"].copy()
            if password:
                connect_setting["密码"] = password

            # 检查main_engine是否可用
            if self.main_engine is None:
                return {
                    "success": False,
                    "message": "MainEngine不可用",
                }

            # 调用main_engine连接
            # gateway_name作为vnpy中的gateway_name参数
            self.main_engine.connect(connect_setting, gateway_type)

            # 更新状态
            gateway_info["connected"] = True

            self.logger.info("网关 '%s' 连接请求已发送", gateway_name)

            # ✨ 发送网关状态变化事件
            self._emit_gateway_status_event(gateway_name, "connected", gateway_type)

            return {
                "success": True,
                "message": f"网关 '{gateway_name}' 连接请求已发送",
                "gateway_name": gateway_name,
            }

        except Exception as e:
            self._log_error("连接网关", e, name=gateway_name)
            return {
                "success": False,
                "message": f"连接失败: {str(e)}",
            }

    def disconnect_gateway(self, gateway_name: str) -> Dict[str, Any]:
        """断开网关.

        Args:
            gateway_name: 网关名称

        Returns:
            Dict: 操作结果
        """
        try:
            if gateway_name not in self.gateway_instances:
                return {
                    "success": False,
                    "message": f"网关 '{gateway_name}' 不存在",
                }

            gateway_info = self.gateway_instances[gateway_name]

            # 先停止该网关的所有策略
            self._stop_gateway_strategies(gateway_name)

            # 断开网关
            if self.main_engine:
                self.main_engine.close()  # 关闭所有网关连接
                # 注意：VNPY的close()会关闭所有网关，如果需要单独关闭，需要其他方法

            gateway_info["connected"] = False

            self.logger.info("网关 '%s' 已断开", gateway_name)

            # ✨ 发送网关状态变化事件
            gateway_type = gateway_info.get("type", "")
            self._emit_gateway_status_event(gateway_name, "disconnected", gateway_type)

            return {
                "success": True,
                "message": f"网关 '{gateway_name}' 已断开",
                "gateway_name": gateway_name,
            }

        except Exception as e:
            self._log_error("断开网关", e, name=gateway_name)
            return {
                "success": False,
                "message": f"断开失败: {str(e)}",
            }

    def delete_gateway(self, gateway_name: str) -> Dict[str, Any]:
        """删除网关.

        Args:
            gateway_name: 网关名称

        Returns:
            Dict: 操作结果
        """
        try:
            if gateway_name not in self.gateway_instances:
                return {
                    "success": False,
                    "message": f"网关 '{gateway_name}' 不存在",
                }

            # 先断开
            self.disconnect_gateway(gateway_name)

            # 删除网关实例信息
            del self.gateway_instances[gateway_name]
            if gateway_name in self.strategy_instances:
                del self.strategy_instances[gateway_name]

            # 保存网关配置到文件
            self._save_gateway_configs()

            return {
                "success": True,
                "message": f"网关 '{gateway_name}' 已删除",
            }

        except Exception as e:
            self._log_error("删除网关", e, name=gateway_name)
            return {
                "success": False,
                "message": f"删除失败: {str(e)}",
            }

    def list_gateways(self) -> List[Dict[str, Any]]:
        """列出所有网关.

        Returns:
            List[Dict]: 网关列表
        """
        gateways = []
        for name, info in self.gateway_instances.items():
            gateways.append(
                {
                    "name": name,
                    "type": info["type"],
                    "connected": info["connected"],
                    "strategy_count": len(self.strategy_instances.get(name, {})),
                    "create_time": info["create_time"].isoformat(),
                }
            )
        return gateways

    def _disconnect_all_gateways(self):
        """断开所有网关."""
        for gateway_name in list(self.gateway_instances.keys()):
            self.disconnect_gateway(gateway_name)

    # ==================== 策略实例管理 ====================

    def get_available_strategies(self, engine_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取可用的策略列表（从策略中心）.

        Args:
            engine_type: 策略引擎类型（如"ctastrategy", "algotrading"等），None表示全部

        Returns:
            List[Dict]: 策略列表
        """
        try:
            # 从服务管理器获取策略中心服务
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()
            strategy_service = service_manager.get_service("strategy_center_service")

            if not strategy_service:
                self.logger.warning("策略中心服务不可用")
                return []

            # 调用策略中心的get_available_strategies方法
            result = strategy_service.get_available_strategies(engine_type=engine_type)

            if result.get("success"):
                return result.get("strategies", [])
            else:
                self.logger.error(f"获取策略列表失败: {result.get('message')}")
                return []

        except Exception as e:
            self._log_error("获取可用策略列表", e)
            return []

    def identify_strategy_type_from_file(self, file_path: str) -> Optional[str]:
        """从策略文件识别策略类型.

        Args:
            file_path: 策略文件路径（相对于策略根目录）

        Returns:
            str: 策略引擎类型，如果无法识别则返回None
        """
        try:
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()
            strategy_service = service_manager.get_service("strategy_center_service")

            if not strategy_service:
                self.logger.warning("策略中心服务不可用")
                return None

            return strategy_service.identify_strategy_type(file_path)

        except Exception as e:
            self._log_error("识别策略类型", e)
            return None

    def load_strategy_from_file(
        self,
        gateway_name: str,
        strategy_name: str,
        file_path: str,
        strategy_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """从策略文件加载并部署策略.

        Args:
            gateway_name: 网关名称
            strategy_name: 策略名称
            file_path: 策略文件路径（相对于策略根目录）
            strategy_params: 策略参数

        Returns:
            Dict: 部署结果
        """
        try:
            self._log_operation(
                "从文件加载策略", gateway=gateway_name, strategy=strategy_name, file=file_path
            )

            # 从策略中心加载策略模块信息
            from backend.core.base import get_service_manager

            service_manager = get_service_manager()
            strategy_service = service_manager.get_service("strategy_center_service")

            if not strategy_service:
                return {
                    "success": False,
                    "message": "策略中心服务不可用",
                }

            # 加载策略模块信息
            module_info = strategy_service.load_strategy_module_info(file_path)

            if not module_info:
                return {
                    "success": False,
                    "message": f"无法加载策略文件: {file_path}",
                }

            # 使用解析出的策略类名和引擎类型
            strategy_class = module_info["class_name"]
            engine_type = module_info["engine_type"]

            # 设置策略参数中的engine_type
            strategy_params = strategy_params.copy()
            strategy_params["engine_type"] = engine_type
            strategy_params["file_path"] = file_path  # 记录原文件路径

            # 调用原有的部署方法
            return self.deploy_strategy(
                gateway_name=gateway_name,
                strategy_name=strategy_name,
                strategy_class=strategy_class,
                strategy_params=strategy_params,
            )

        except Exception as e:
            self._log_error("从文件加载策略", e)
            return {
                "success": False,
                "message": f"加载失败: {str(e)}",
            }

    def deploy_strategy(
        self,
        gateway_name: str,
        strategy_name: str,
        strategy_class: str,
        strategy_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """部署策略到指定网关.

        Args:
            gateway_name: 网关名称
            strategy_name: 策略名称
            strategy_class: 策略类名
            strategy_params: 策略参数

        Returns:
            Dict: 部署结果
        """
        try:
            self._log_operation(
                "部署策略", gateway=gateway_name, strategy=strategy_name, class_name=strategy_class
            )

            if gateway_name not in self.gateway_instances:
                return {
                    "success": False,
                    "message": f"网关 '{gateway_name}' 不存在",
                }

            if gateway_name not in self.strategy_instances:
                self.strategy_instances[gateway_name] = {}

            # 检查策略名称是否已存在
            if strategy_name in self.strategy_instances[gateway_name]:
                return {
                    "success": False,
                    "message": f"策略 '{strategy_name}' 已存在于网关 '{gateway_name}'",
                }

            # 确定策略引擎类型（默认CTA）
            engine_type_param = strategy_params.get("engine_type", "ctastrategy")
            # 将小写格式转换为vnpy的引擎名称格式
            engine_name = self.ENGINE_NAME_MAP.get(
                engine_type_param.lower() if isinstance(engine_type_param, str) else "ctastrategy",
                "CtaStrategy",
            )

            # 检查main_engine是否可用
            if self.main_engine is None:
                return {
                    "success": False,
                    "message": "MainEngine不可用",
                }

            # 按需加载策略应用
            if not self._ensure_app_loaded(engine_name):
                # 获取友好的错误提示
                display_name = self.ENGINE_DISPLAY_NAMES.get(engine_name, engine_name)
                module_name = self.APP_CLASS_MAP.get(engine_name, ("未知", ""))[0]

                error_msg = (
                    f"{display_name}引擎不可用。\n\n"
                    f"原因：扩展包 {module_name} 未安装或加载失败。\n\n"
                    f"当前已安装的策略引擎：\n"
                )

                # 列出可用的引擎（动态检测）
                available = []
                for name, (mod, cls) in self.APP_CLASS_MAP.items():
                    if self._check_package_installed(mod):
                        available.append(self.ENGINE_DISPLAY_NAMES.get(name, name))

                if available:
                    error_msg += "  • " + "\n  • ".join(available)
                else:
                    error_msg += "  (无)"

                error_msg += f"\n\n如需使用{display_name}，请确保扩展包 {module_name} 已正确安装。"

                return {
                    "success": False,
                    "message": error_msg,
                }

            # 获取策略引擎
            try:
                strategy_engine = self.main_engine.get_engine(engine_name)
                if not strategy_engine:
                    return {
                        "success": False,
                        "message": f"策略引擎 '{engine_name}' 不可用",
                    }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"获取策略引擎失败: {str(e)}",
                }

            # 根据引擎类型准备不同的参数和调用不同的API
            try:
                deploy_result = self._deploy_to_engine(
                    strategy_engine=strategy_engine,
                    engine_name=engine_name,
                    strategy_class=strategy_class,
                    strategy_name=strategy_name,
                    strategy_params=strategy_params,
                )

                if not deploy_result["success"]:
                    return deploy_result

                # 获取部署信息
                deployed_info = deploy_result["info"]

            except Exception as e:
                self.logger.error("添加策略失败: %s", e, exc_info=True)
                return {
                    "success": False,
                    "message": f"添加策略失败: {str(e)}",
                }

            # 保存策略信息
            self.strategy_instances[gateway_name][strategy_name] = {
                "name": strategy_name,
                "class": strategy_class,
                "params": strategy_params,
                "engine_name": engine_name,
                "deployed_info": deployed_info,  # 引擎特定的部署信息
                "status": "stopped",
                "deploy_time": datetime.now(),
            }

            return {
                "success": True,
                "message": f"策略 '{strategy_name}' 部署成功",
                "strategy_name": strategy_name,
                "engine_name": engine_name,
            }

        except Exception as e:
            self._log_error("部署策略", e, gateway=gateway_name, strategy=strategy_name)
            return {
                "success": False,
                "message": f"部署失败: {str(e)}",
            }

    def start_strategy(self, gateway_name: str, strategy_name: str) -> Dict[str, Any]:
        """启动策略.

        Args:
            gateway_name: 网关名称
            strategy_name: 策略名称

        Returns:
            Dict: 操作结果
        """
        try:
            if gateway_name not in self.strategy_instances:
                return {
                    "success": False,
                    "message": f"网关 '{gateway_name}' 没有部署的策略",
                }

            if strategy_name not in self.strategy_instances[gateway_name]:
                return {
                    "success": False,
                    "message": f"策略 '{strategy_name}' 未部署",
                }

            strategy_info = self.strategy_instances[gateway_name][strategy_name]
            # 获取引擎名称，确保使用正确的格式
            engine_name_stored = strategy_info.get("engine_name", "CtaStrategy")
            engine_name = self.ENGINE_NAME_MAP.get(
                (
                    engine_name_stored.lower()
                    if isinstance(engine_name_stored, str)
                    else "ctastrategy"
                ),
                engine_name_stored,
            )

            # 检查main_engine是否可用
            if self.main_engine is None:
                return {
                    "success": False,
                    "message": "MainEngine不可用",
                }

            # 获取策略引擎
            try:
                strategy_engine = self.main_engine.get_engine(engine_name)
                if not strategy_engine:
                    return {
                        "success": False,
                        "message": f"策略引擎 '{engine_name}' 不可用",
                    }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"获取策略引擎失败: {str(e)}",
                }

            # 检查启动前置条件
            precondition_check = self._check_strategy_start_preconditions(
                gateway_name, strategy_info, engine_name
            )
            if not precondition_check["success"]:
                return precondition_check

            # 初始化并启动策略
            try:
                # 先初始化策略
                self.logger.info("正在初始化策略 '%s'...", strategy_name)
                strategy_engine.init_strategy(strategy_name)
                self.logger.info("✅ 策略 '%s' 初始化完成", strategy_name)

                # 等待初始化完成（init_strategy可能是异步的）
                import time

                time.sleep(0.5)

                # 启动策略
                self.logger.info("正在启动策略 '%s'...", strategy_name)
                strategy_engine.start_strategy(strategy_name)
                self.logger.info("✅ 策略 '%s' 已启动", strategy_name)

            except Exception as e:
                self.logger.error("启动策略失败: %s", e, exc_info=True)
                return {
                    "success": False,
                    "message": f"启动策略失败: {str(e)}",
                }

            # 更新状态
            strategy_info["status"] = "running"

            # ✨ 发送策略状态变化事件（支持跨模块集成）
            self._emit_strategy_status_event(gateway_name, strategy_name, "running", engine_name)

            return {
                "success": True,
                "message": f"策略 '{strategy_name}' 已启动",
                "strategy_name": strategy_name,
            }

        except Exception as e:
            self._log_error("启动策略", e, gateway=gateway_name, strategy=strategy_name)
            return {
                "success": False,
                "message": f"启动失败: {str(e)}",
            }

    def stop_strategy(self, gateway_name: str, strategy_name: str) -> Dict[str, Any]:
        """停止策略.

        Args:
            gateway_name: 网关名称
            strategy_name: 策略名称

        Returns:
            Dict: 操作结果
        """
        try:
            if gateway_name not in self.strategy_instances:
                return {
                    "success": False,
                    "message": f"网关 '{gateway_name}' 没有部署的策略",
                }

            if strategy_name not in self.strategy_instances[gateway_name]:
                return {
                    "success": False,
                    "message": f"策略 '{strategy_name}' 未部署",
                }

            strategy_info = self.strategy_instances[gateway_name][strategy_name]
            # 获取引擎名称，确保使用正确的格式
            engine_name_stored = strategy_info.get("engine_name", "CtaStrategy")
            engine_name = self.ENGINE_NAME_MAP.get(
                (
                    engine_name_stored.lower()
                    if isinstance(engine_name_stored, str)
                    else "ctastrategy"
                ),
                engine_name_stored,
            )

            # 检查main_engine是否可用
            if self.main_engine is None:
                return {
                    "success": False,
                    "message": "MainEngine不可用",
                }

            # 获取策略引擎
            try:
                strategy_engine = self.main_engine.get_engine(engine_name)
                if not strategy_engine:
                    return {
                        "success": False,
                        "message": f"策略引擎 '{engine_name}' 不可用",
                    }
            except Exception as e:
                return {
                    "success": False,
                    "message": f"获取策略引擎失败: {str(e)}",
                }

            # 停止策略
            try:
                strategy_engine.stop_strategy(strategy_name)
                self.logger.info("策略 '%s' 已停止", strategy_name)

            except Exception as e:
                self.logger.error("停止策略失败: %s", e, exc_info=True)
                return {
                    "success": False,
                    "message": f"停止策略失败: {str(e)}",
                }

            # 更新状态
            strategy_info["status"] = "stopped"

            # ✨ 发送策略状态变化事件（支持跨模块集成）
            self._emit_strategy_status_event(gateway_name, strategy_name, "stopped", engine_name)

            return {
                "success": True,
                "message": f"策略 '{strategy_name}' 已停止",
                "strategy_name": strategy_name,
            }

        except Exception as e:
            self._log_error("停止策略", e, gateway=gateway_name, strategy=strategy_name)
            return {
                "success": False,
                "message": f"停止失败: {str(e)}",
            }

    def remove_strategy(self, gateway_name: str, strategy_name: str) -> Dict[str, Any]:
        """移除策略.

        Args:
            gateway_name: 网关名称
            strategy_name: 策略名称

        Returns:
            Dict: 操作结果
        """
        try:
            if gateway_name not in self.strategy_instances:
                return {
                    "success": False,
                    "message": f"网关 '{gateway_name}' 没有部署的策略",
                }

            if strategy_name not in self.strategy_instances[gateway_name]:
                return {
                    "success": False,
                    "message": f"策略 '{strategy_name}' 未部署",
                }

            # 先停止策略
            self.stop_strategy(gateway_name, strategy_name)

            # 删除策略
            del self.strategy_instances[gateway_name][strategy_name]

            return {
                "success": True,
                "message": f"策略 '{strategy_name}' 已移除",
            }

        except Exception as e:
            self._log_error("移除策略", e, gateway=gateway_name, strategy=strategy_name)
            return {
                "success": False,
                "message": f"移除失败: {str(e)}",
            }

    def start_all_strategies(self, gateway_name: str) -> Dict[str, Any]:
        """启动指定网关的所有策略.

        Args:
            gateway_name: 网关名称

        Returns:
            Dict: 操作结果
        """
        try:
            if gateway_name not in self.strategy_instances:
                return {
                    "success": False,
                    "message": f"网关 '{gateway_name}' 没有部署的策略",
                }

            started_count = 0
            for strategy_name in self.strategy_instances[gateway_name].keys():
                result = self.start_strategy(gateway_name, strategy_name)
                if result["success"]:
                    started_count += 1

            return {
                "success": True,
                "message": f"已启动 {started_count} 个策略",
                "started_count": started_count,
            }

        except Exception as e:
            self._log_error("启动所有策略", e, gateway=gateway_name)
            return {
                "success": False,
                "message": f"启动失败: {str(e)}",
            }

    def stop_all_strategies(self, gateway_name: str) -> Dict[str, Any]:
        """停止指定网关的所有策略.

        Args:
            gateway_name: 网关名称

        Returns:
            Dict: 操作结果
        """
        try:
            if gateway_name not in self.strategy_instances:
                return {
                    "success": False,
                    "message": f"网关 '{gateway_name}' 没有部署的策略",
                }

            stopped_count = 0
            for strategy_name in self.strategy_instances[gateway_name].keys():
                result = self.stop_strategy(gateway_name, strategy_name)
                if result["success"]:
                    stopped_count += 1

            return {
                "success": True,
                "message": f"已停止 {stopped_count} 个策略",
                "stopped_count": stopped_count,
            }

        except Exception as e:
            self._log_error("停止所有策略", e, gateway=gateway_name)
            return {
                "success": False,
                "message": f"停止失败: {str(e)}",
            }

    def list_strategies(self, gateway_name: str) -> List[Dict[str, Any]]:
        """列出指定网关的所有策略.

        Args:
            gateway_name: 网关名称

        Returns:
            List[Dict]: 策略列表
        """
        if gateway_name not in self.strategy_instances:
            return []

        strategies = []
        for name, info in self.strategy_instances[gateway_name].items():
            strategies.append(
                {
                    "name": name,
                    "class": info["class"],
                    "status": info["status"],
                    "deploy_time": info["deploy_time"].isoformat(),
                }
            )
        return strategies

    def _stop_gateway_strategies(self, gateway_name: str):
        """停止指定网关的所有策略."""
        if gateway_name in self.strategy_instances:
            for strategy_name in list(self.strategy_instances[gateway_name].keys()):
                self.stop_strategy(gateway_name, strategy_name)

    def _stop_all_strategies(self):
        """停止所有策略."""
        for gateway_name in self.strategy_instances:
            self._stop_gateway_strategies(gateway_name)

    def _deploy_to_engine(
        self,
        strategy_engine: Any,
        engine_name: str,
        strategy_class: str,
        strategy_name: str,
        strategy_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """根据引擎类型部署策略.

        不同的策略引擎有不同的API：
        - CTA策略: add_strategy(class_name, strategy_name, vt_symbol, setting)
        - 组合策略: add_strategy(class_name, strategy_name, vt_symbols, setting)
        - 价差交易: add_strategy(class_name, strategy_name, spread_name, setting)
        - 算法交易: start_algo(algo_template, setting) - 不同的模式

        Args:
            strategy_engine: 策略引擎实例
            engine_name: 引擎名称
            strategy_class: 策略类名
            strategy_name: 策略名称
            strategy_params: 策略参数

        Returns:
            Dict: 部署结果
        """
        # 排除引擎类型参数
        setting = {k: v for k, v in strategy_params.items() if k not in ["engine_type"]}

        try:
            if engine_name == "CtaStrategy":
                # CTA策略: 单合约
                vt_symbol = self._get_vt_symbol(strategy_params)
                if not vt_symbol:
                    return {
                        "success": False,
                        "message": "CTA策略需要vt_symbol参数（合约代码）",
                    }

                # 移除vt_symbol和vt_symbols，放入setting中的其他参数
                setting = {k: v for k, v in setting.items() if k not in ["vt_symbol", "vt_symbols"]}

                strategy_engine.add_strategy(
                    class_name=strategy_class,
                    strategy_name=strategy_name,
                    vt_symbol=vt_symbol,
                    setting=setting,
                )

                self.logger.info("✅ CTA策略 '%s' 已部署，合约: %s", strategy_name, vt_symbol)
                return {
                    "success": True,
                    "info": {"vt_symbol": vt_symbol, "type": "cta"},
                }

            elif engine_name == "PortfolioStrategy":
                # 组合策略: 多合约
                vt_symbols = strategy_params.get("vt_symbols", [])
                if not vt_symbols:
                    # 兼容单合约
                    vt_symbol = strategy_params.get("vt_symbol", "")
                    if vt_symbol:
                        vt_symbols = [vt_symbol]

                if not vt_symbols:
                    return {
                        "success": False,
                        "message": "组合策略需要vt_symbols参数（合约列表）",
                    }

                # 移除vt_symbols，放入setting中的其他参数
                setting = {k: v for k, v in setting.items() if k not in ["vt_symbol", "vt_symbols"]}

                strategy_engine.add_strategy(
                    class_name=strategy_class,
                    strategy_name=strategy_name,
                    vt_symbols=vt_symbols,
                    setting=setting,
                )

                self.logger.info("✅ 组合策略 '%s' 已部署，合约: %s", strategy_name, vt_symbols)
                return {
                    "success": True,
                    "info": {"vt_symbols": vt_symbols, "type": "portfolio"},
                }

            elif engine_name == "SpreadTrading":
                # 价差交易: 使用价差名称
                spread_name = strategy_params.get("spread_name", "")
                if not spread_name:
                    return {
                        "success": False,
                        "message": "价差交易策略需要spread_name参数（价差组合名称）",
                    }

                # 移除spread_name，放入setting中的其他参数
                setting = {k: v for k, v in setting.items() if k != "spread_name"}

                strategy_engine.add_strategy(
                    class_name=strategy_class,
                    strategy_name=strategy_name,
                    spread_name=spread_name,
                    setting=setting,
                )

                self.logger.info(
                    "✅ 价差交易策略 '%s' 已部署，价差: %s", strategy_name, spread_name
                )
                return {
                    "success": True,
                    "info": {"spread_name": spread_name, "type": "spread"},
                }

            elif engine_name == "OptionMaster":
                # 期权引擎: 不是用来部署策略的，而是期权分析工具
                return {
                    "success": False,
                    "message": (
                        "期权分析引擎不支持通过策略池部署。\n\n"
                        "期权引擎（OptionMaster）是专业的期权分析和对冲工具，提供：\n"
                        "  • 期权T型报价展示\n"
                        "  • 希腊字母计算和监控\n"
                        "  • 期权定价算法\n"
                        "  • 期权对冲算法\n"
                        "  • 隐含波动率分析\n\n"
                        "它不是传统的策略引擎，无法通过策略池部署。\n"
                        "如需进行期权交易策略，建议使用CTA策略引擎，\n"
                        "在策略代码中调用期权相关的交易逻辑。"
                    ),
                }

            elif engine_name == "AlgoTrading":
                # 算法交易: 使用start_algo而不是add_strategy
                return {
                    "success": False,
                    "message": (
                        "算法交易引擎不支持通过策略池部署。\n\n"
                        "算法交易（AlgoTrading）是一次性执行的智能订单算法，包括：\n"
                        "  • TWAP（时间加权平均）\n"
                        "  • VWAP（成交量加权平均）\n"
                        "  • 冰山算法\n"
                        "  • 狙击手算法\n\n"
                        "使用方式：在下单时选择算法类型，而不是预先部署到策略池。"
                    ),
                }

            elif engine_name == "ScriptTrader":
                # 脚本交易: 特殊的执行模式
                return {
                    "success": False,
                    "message": (
                        "脚本交易引擎不支持通过策略池部署。\n\n"
                        "脚本交易（ScriptTrader）是灵活的Python脚本执行环境，\n"
                        "用于快速验证交易想法或执行临时交易任务。\n\n"
                        "使用方式：直接在脚本交易界面编写和执行Python脚本。"
                    ),
                }

            else:
                # 未知引擎，尝试通用方法
                vt_symbol = self._get_vt_symbol(strategy_params)
                if not vt_symbol:
                    return {
                        "success": False,
                        "message": f"未知的引擎类型: {engine_name}",
                    }

                setting = {k: v for k, v in setting.items() if k not in ["vt_symbol", "vt_symbols"]}

                strategy_engine.add_strategy(
                    class_name=strategy_class,
                    strategy_name=strategy_name,
                    vt_symbol=vt_symbol,
                    setting=setting,
                )

                self.logger.info("✅ 策略 '%s' 已部署到 %s", strategy_name, engine_name)
                return {
                    "success": True,
                    "info": {"vt_symbol": vt_symbol, "type": "generic"},
                }

        except Exception as e:
            self.logger.error("部署策略到引擎失败: %s", e, exc_info=True)
            return {
                "success": False,
                "message": f"部署失败: {str(e)}",
            }

    def _get_vt_symbol(self, strategy_params: Dict[str, Any]) -> str:
        """从参数中获取vt_symbol（兼容多种格式）.

        Args:
            strategy_params: 策略参数

        Returns:
            str: 合约代码
        """
        # 优先使用vt_symbol
        vt_symbol = strategy_params.get("vt_symbol", "")

        if not vt_symbol:
            # 兼容vt_symbols列表（取第一个）
            vt_symbols = strategy_params.get("vt_symbols", [])
            if vt_symbols:
                vt_symbol = vt_symbols[0] if isinstance(vt_symbols, list) else str(vt_symbols)

        return vt_symbol

    def _check_strategy_start_preconditions(
        self, gateway_name: str, strategy_info: Dict[str, Any], engine_name: str
    ) -> Dict[str, Any]:
        """检查策略启动的前置条件.

        策略启动需要满足：
        1. 网关已连接
        2. 合约数据可用（可以订阅行情）
        3. 策略类已注册到引擎

        Args:
            gateway_name: 网关名称
            strategy_info: 策略信息
            engine_name: 引擎名称

        Returns:
            Dict: 检查结果
        """
        issues = []

        # 1. 检查网关连接状态
        if gateway_name in self.gateway_instances:
            gateway_info = self.gateway_instances[gateway_name]
            if not gateway_info.get("connected", False):
                issues.append("网关未连接")
                self.logger.warning("⚠️ 网关 '%s' 未连接", gateway_name)

        # 2. 检查合约数据
        if self.main_engine:
            # 获取合约信息
            deployed_info = strategy_info.get("deployed_info", {})
            vt_symbol = deployed_info.get("vt_symbol")
            vt_symbols = deployed_info.get("vt_symbols", [])

            symbols_to_check = []
            if vt_symbol:
                symbols_to_check.append(vt_symbol)
            if vt_symbols:
                symbols_to_check.extend(vt_symbols)

            if symbols_to_check:
                missing_contracts = []
                for symbol in symbols_to_check:
                    contract = self.main_engine.get_contract(symbol)
                    if not contract:
                        missing_contracts.append(symbol)

                if missing_contracts:
                    issues.append(f"找不到合约: {', '.join(missing_contracts)}")
                    self.logger.warning(
                        "⚠️ 找不到合约数据: %s (网关可能未连接或未订阅该合约)", missing_contracts
                    )

        # 如果有问题，返回友好提示
        if issues:
            error_msg = "策略启动前置条件不满足：\n\n"
            for i, issue in enumerate(issues, 1):
                error_msg += f"{i}. {issue}\n"

            error_msg += "\n💡 解决方案：\n"
            if "网关未连接" in str(issues):
                error_msg += "  • 请先连接网关\n"
            if "找不到合约" in str(issues):
                error_msg += "  • 确保网关已连接\n"
                error_msg += "  • 确保合约代码格式正确（如：600000.SSE）\n"
                error_msg += "  • 网关连接后会自动获取可用合约\n"

            return {
                "success": False,
                "message": error_msg.strip(),
            }

        return {"success": True}

    def _ensure_app_loaded(self, engine_name: str) -> bool:
        """确保策略应用已加载.

        Args:
            engine_name: 引擎名称（如"CtaStrategy"）

        Returns:
            bool: 是否成功加载
        """
        # 如果已加载，直接返回
        if engine_name in self.loaded_apps:
            return True

        # 检查main_engine
        if not self.main_engine:
            self.logger.error("MainEngine不可用，无法加载策略应用")
            return False

        # 获取应用类信息
        if engine_name not in self.APP_CLASS_MAP:
            self.logger.error("未知的策略引擎: %s", engine_name)
            return False

        module_name, class_name = self.APP_CLASS_MAP[engine_name]
        display_name = self.ENGINE_DISPLAY_NAMES.get(engine_name, engine_name)

        # 动态检测包是否已安装
        is_installed = self._check_package_installed(module_name)

        if not is_installed:
            self.logger.error("❌ %s引擎不可用：扩展包 %s 未安装", display_name, module_name)
            return False

        try:
            # 动态导入模块
            import importlib

            module = importlib.import_module(module_name)
            app_class = getattr(module, class_name)

            # 添加到MainEngine
            self.main_engine.add_app(app_class)
            self.loaded_apps.add(engine_name)

            self.logger.info("✅ 策略应用 %s 已按需加载", display_name)
            return True

        except ImportError as e:
            self.logger.error("❌ 策略包 %s 导入失败: %s", module_name, e)
            return False
        except AttributeError as e:
            self.logger.error("❌ 策略应用类 %s 不存在: %s", class_name, e)
            return False
        except Exception as e:
            self.logger.error("❌ 加载策略应用 %s 失败: %s", engine_name, e, exc_info=True)
            return False

    def get_available_engine_types(self) -> List[Dict[str, Any]]:
        """获取可用的策略引擎类型列表.

        只返回支持策略池部署的引擎类型。

        Returns:
            List[Dict]: 引擎类型列表，包含名称、显示名称、是否可用
        """
        available_engines = []
        for engine_name, (module_name, class_name) in self.APP_CLASS_MAP.items():
            # 只返回支持策略池的引擎
            if engine_name not in self.STRATEGY_POOL_SUPPORTED_ENGINES:
                continue

            display_name = self.ENGINE_DISPLAY_NAMES.get(engine_name, engine_name)
            # 动态检测包是否已安装
            is_installed = self._check_package_installed(module_name)
            available_engines.append(
                {
                    "engine_name": engine_name,
                    "display_name": display_name,
                    "module_name": module_name,
                    "is_installed": is_installed,
                    "is_available": is_installed,  # 兼容旧字段名
                    "supports_strategy_pool": True,
                }
            )
        return available_engines

    # ==================== 交易监控 ====================

    def get_monitoring_data(self, gateway_name: str) -> Dict[str, Any]:
        """获取指定网关的交易监控数据.

        Args:
            gateway_name: 网关名称

        Returns:
            Dict: 监控数据
        """
        try:
            if gateway_name not in self.gateway_instances:
                return {
                    "success": False,
                    "message": f"网关 '{gateway_name}' 不存在",
                }

            # 从main_engine获取实际的监控数据
            if not self.main_engine:
                return {
                    "success": False,
                    "message": "MainEngine不可用",
                }

            gateway_info = self.gateway_instances[gateway_name]
            gateway_type = gateway_info["type"]

            # 获取订单
            orders = []
            all_orders = self.main_engine.get_all_orders()
            for order in all_orders:
                if order.gateway_name == gateway_type:
                    orders.append(
                        {
                            "orderid": order.orderid,
                            "symbol": order.symbol,
                            "direction": order.direction.value,
                            "offset": order.offset.value,
                            "price": order.price,
                            "volume": order.volume,
                            "traded": order.traded,
                            "status": order.status.value,
                            "time": order.time,
                        }
                    )

            # 获取成交
            trades = []
            all_trades = self.main_engine.get_all_trades()
            for trade in all_trades:
                if trade.gateway_name == gateway_type:
                    trades.append(
                        {
                            "tradeid": trade.tradeid,
                            "orderid": trade.orderid,
                            "symbol": trade.symbol,
                            "direction": trade.direction.value,
                            "offset": trade.offset.value,
                            "price": trade.price,
                            "volume": trade.volume,
                            "time": trade.time,
                        }
                    )

            # 获取持仓
            positions = []
            all_positions = self.main_engine.get_all_positions()
            for position in all_positions:
                if position.gateway_name == gateway_type:
                    positions.append(
                        {
                            "symbol": position.symbol,
                            "direction": position.direction.value,
                            "volume": position.volume,
                            "frozen": position.frozen,
                            "price": position.price,
                            "pnl": position.pnl,
                        }
                    )

            # 获取账户
            accounts = []
            all_accounts = self.main_engine.get_all_accounts()
            for account in all_accounts:
                if account.gateway_name == gateway_type:
                    accounts.append(
                        {
                            "accountid": account.accountid,
                            "balance": account.balance,
                            "frozen": account.frozen,
                            "available": account.available,
                        }
                    )

            return {
                "success": True,
                "data": {
                    "orders": orders,
                    "trades": trades,
                    "positions": positions,
                    "accounts": accounts,
                    "gateway_name": gateway_name,
                    "gateway_type": gateway_type,
                },
            }

        except Exception as e:
            self._log_error("获取监控数据", e, gateway=gateway_name)
            return {
                "success": False,
                "message": f"获取失败: {str(e)}",
            }

    # ==================== 风险管理 ====================

    def get_risk_status(self) -> Dict[str, Any]:
        """获取风险管理状态.

        Returns:
            Dict: 风险管理状态信息
        """
        try:
            if not self.risk_engine:
                return {
                    "success": False,
                    "message": "风险管理引擎不可用",
                    "enabled": False,
                }

            # 获取风控状态
            status = {
                "enabled": True,
                "active": False,
                "parameters": {},
            }

            # 获取风控参数
            if hasattr(self.risk_engine, "get_parameters"):
                with contextlib.suppress(Exception):
                    status["parameters"] = self.risk_engine.get_parameters()

            # 获取风控激活状态
            if hasattr(self.risk_engine, "is_active"):
                with contextlib.suppress(Exception):
                    status["active"] = self.risk_engine.is_active()

            return {
                "success": True,
                "status": status,
            }

        except Exception as e:
            self._log_error("获取风险管理状态", e)
            return {
                "success": False,
                "message": f"获取失败: {str(e)}",
            }

    def update_risk_parameters(self, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """更新风控参数.

        Args:
            parameters: 风控参数字典

        Returns:
            Dict: 更新结果
        """
        try:
            if not self.risk_engine:
                return {
                    "success": False,
                    "message": "风险管理引擎不可用",
                }

            if hasattr(self.risk_engine, "update_setting"):
                self.risk_engine.update_setting(parameters)
                self.logger.info(f"风控参数已更新: {list(parameters.keys())}")

                return {
                    "success": True,
                    "message": "风控参数已更新",
                }
            else:
                return {
                    "success": False,
                    "message": "风险管理引擎不支持update_setting方法",
                }

        except Exception as e:
            self._log_error("更新风控参数", e)
            return {
                "success": False,
                "message": f"更新失败: {str(e)}",
            }

    def set_risk_active(self, active: bool) -> Dict[str, Any]:
        """启用/禁用风控.

        Args:
            active: True=启用，False=禁用

        Returns:
            Dict: 操作结果
        """
        try:
            if not self.risk_engine:
                return {
                    "success": False,
                    "message": "风险管理引擎不可用",
                }

            if hasattr(self.risk_engine, "set_active"):
                self.risk_engine.set_active(active)
                action = "启用" if active else "禁用"
                self.logger.info(f"风控已{action}")

                return {
                    "success": True,
                    "message": f"风控已{action}",
                }
            else:
                return {
                    "success": False,
                    "message": "风险管理引擎不支持set_active方法",
                }

        except Exception as e:
            self._log_error("设置风控状态", e)
            return {
                "success": False,
                "message": f"操作失败: {str(e)}",
            }

    # ==================== 策略状态事件发送 ====================

    def _emit_strategy_status_event(
        self, gateway_name: str, strategy_name: str, status: str, engine_name: str
    ):
        """发送策略状态变化事件.

        Args:
            gateway_name: 网关名称
            strategy_name: 策略名称
            status: 状态（running/stopped）
            engine_name: 引擎名称
        """
        try:
            from backend.core.base import get_event_engine
            from backend.core.utils import EVENT_STRATEGY_STATUS_CHANGED
            from vnpy.event import Event

            event_engine = get_event_engine()
            if not event_engine:
                return

            # 构建事件数据
            event_data = {
                "gateway_name": gateway_name,
                "strategy_name": strategy_name,
                "status": status,
                "engine_name": engine_name,
                "engine_type": engine_name.lower() if isinstance(engine_name, str) else "ctastrategy",
                "timestamp": datetime.now().isoformat(),
                "active_count": self._count_active_strategies(gateway_name),
            }

            # 发送事件
            event = Event(EVENT_STRATEGY_STATUS_CHANGED, event_data)
            event_engine.put(event)

            self.logger.debug(
                f"📢 已发送策略状态变化事件: {gateway_name}.{strategy_name} -> {status}"
            )

        except Exception as e:
            self.logger.warning(f"发送策略状态事件失败: {e}")

    def _emit_gateway_status_event(
        self, gateway_name: str, status: str, gateway_type: str
    ):
        """发送网关状态变化事件.

        Args:
            gateway_name: 网关名称
            status: 状态（connected/disconnected）
            gateway_type: 网关类型
        """
        try:
            from backend.core.base import get_event_engine
            from backend.core.utils import EVENT_GATEWAY_STATUS_CHANGED
            from vnpy.event import Event

            event_engine = get_event_engine()
            if not event_engine:
                return

            # 构建事件数据
            event_data = {
                "gateway_name": gateway_name,
                "status": status,
                "gateway_type": gateway_type,
                "timestamp": datetime.now().isoformat(),
                "strategy_count": len(self.strategy_instances.get(gateway_name, {})),
            }

            # 发送事件
            event = Event(EVENT_GATEWAY_STATUS_CHANGED, event_data)
            event_engine.put(event)

            self.logger.debug(f"📢 已发送网关状态变化事件: {gateway_name} -> {status}")

        except Exception as e:
            self.logger.warning(f"发送网关状态事件失败: {e}")

    def _count_active_strategies(self, gateway_name: str) -> int:
        """统计网关的激活策略数量.

        Args:
            gateway_name: 网关名称

        Returns:
            int: 激活策略数量
        """
        if gateway_name not in self.strategy_instances:
            return 0

        strategies = self.strategy_instances[gateway_name]
        return sum(1 for s in strategies.values() if s.get("status") == "running")

    def get_single_strategy_gateways(self) -> List[Dict[str, Any]]:
        """获取只激活1个策略的网关列表.

        对应需求：策略池只激活了1个策略的交易网关都会被动的出现在交易监控界面。

        Returns:
            List[Dict]: 单策略网关列表
        """
        single_strategy_gateways = []

        for gateway_name, strategies in self.strategy_instances.items():
            active_strategies = [s for s in strategies.values() if s.get("status") == "running"]

            # 只有激活1个策略时才返回
            if len(active_strategies) == 1:
                strategy = active_strategies[0]
                engine_name = strategy.get("engine_name", "CtaStrategy")
                strategy_type = (
                    engine_name.lower() if isinstance(engine_name, str) else "ctastrategy"
                )

                single_strategy_gateways.append({
                    "gateway_name": gateway_name,
                    "strategy_name": strategy.get("name", ""),
                    "strategy_class": strategy.get("class", ""),
                    "engine_name": engine_name,
                    "strategy_type": strategy_type,
                    "monitor_template": self.get_monitor_template_for_strategy(strategy_type),
                })

        return single_strategy_gateways

    # ==================== 策略类型识别与监控适配 ====================

    def get_active_strategy_for_monitoring(self, gateway_name: str) -> Optional[Dict[str, Any]]:
        """获取网关的监控策略（仅当激活1个策略时返回）.

        Args:
            gateway_name: 网关名称

        Returns:
            Dict: 监控信息（包含策略、引擎名称、监控模板），如果不满足条件则返回None
        """
        try:
            if gateway_name not in self.strategy_instances:
                return None

            strategies = self.strategy_instances[gateway_name]
            active_strategies = [s for s in strategies.values() if s.get("status") == "running"]

            # 只有激活1个策略时才返回监控信息
            if len(active_strategies) == 1:
                strategy = active_strategies[0]
                strategy_name = strategy.get("name", "")
                engine_name = strategy.get("engine_name", "CtaStrategy")
                strategy_type = (
                    engine_name.lower() if isinstance(engine_name, str) else "ctastrategy"
                )

                monitor_template = self.get_monitor_template_for_strategy(
                    strategy_type=strategy_type
                )

                return {
                    "strategy": strategy,
                    "strategy_name": strategy_name,
                    "engine_name": engine_name,
                    "strategy_type": strategy_type,
                    "monitor_template": monitor_template,
                }

            return None

        except Exception as e:
            self.logger.error("获取监控策略失败: %s", e)
            return None

    def identify_strategy_type(
        self,
        strategy_class_name: str,
        gateway_name: Optional[str] = None,
        strategy_name: Optional[str] = None,
    ) -> str:
        """识别策略类型.

        通过策略类名或策略实例的继承关系识别策略类型。

        Args:
            strategy_class_name: 策略类名
            gateway_name: 网关名称（可选，用于查找已部署策略）
            strategy_name: 策略名称（可选，用于查找已部署策略）

        Returns:
            str: 策略引擎类型 (algotrading/ctastrategy/optionmaster/portfoliostrategy/scripttrader/spreadtrading)
        """
        try:
            # 方法1: 根据策略类名模式识别
            class_name_lower = strategy_class_name.lower()

            # algotrading: 算法交易策略
            if any(
                keyword in class_name_lower
                for keyword in ["algo", "twap", "vwap", "iceberg", "sniper", "stop"]
            ):
                return StrategyEngineType.ALGO_TRADING.value

            # optionmaster: 期权策略
            if any(
                keyword in class_name_lower
                for keyword in ["option", "greeks", "delta", "gamma", "vega", "theta"]
            ):
                return StrategyEngineType.OPTION_MASTER.value

            # spreadtrading: 价差交易
            if any(keyword in class_name_lower for keyword in ["spread", "arbitrage", "pair"]):
                return StrategyEngineType.SPREAD_TRADING.value

            # portfoliostrategy: 组合策略
            if any(keyword in class_name_lower for keyword in ["portfolio", "multi", "basket"]):
                return StrategyEngineType.PORTFOLIO_STRATEGY.value

            # scripttrader: 脚本交易
            if any(keyword in class_name_lower for keyword in ["script", "manual"]):
                return StrategyEngineType.SCRIPT_TRADER.value

            # 方法2: 从已部署的策略实例获取引擎类型
            if (
                gateway_name
                and strategy_name
                and gateway_name in self.strategy_instances
                and strategy_name in self.strategy_instances[gateway_name]
            ):
                strategy_info = self.strategy_instances[gateway_name][strategy_name]
                engine_type = strategy_info.get("engine_type", "")
                if engine_type:
                    return engine_type.lower()

            # 默认返回CTA策略
            return StrategyEngineType.CTA_STRATEGY.value

        except Exception as e:
            self.logger.error(f"识别策略类型失败: {e}")
            return StrategyEngineType.CTA_STRATEGY.value

    def get_monitor_template_for_strategy(
        self, strategy_type: Optional[str] = None, strategy_class_name: Optional[str] = None
    ) -> str:
        """获取策略对应的监控UI模板.

        Args:
            strategy_type: 策略引擎类型
            strategy_class_name: 策略类名（如果strategy_type未提供）

        Returns:
            str: 监控模板名称
        """
        try:
            # 如果未提供策略类型，先识别
            if not strategy_type and strategy_class_name:
                strategy_type = self.identify_strategy_type(strategy_class_name)

            # 确保strategy_type不为None
            if strategy_type is None:
                return "default_monitor"

            # 根据策略类型返回对应的监控模板
            monitor_templates = {
                StrategyEngineType.ALGO_TRADING.value: "algo_monitor",
                StrategyEngineType.CTA_STRATEGY.value: "cta_monitor",
                StrategyEngineType.OPTION_MASTER.value: "option_monitor",
                StrategyEngineType.PORTFOLIO_STRATEGY.value: "portfolio_monitor",
                StrategyEngineType.SCRIPT_TRADER.value: "default_monitor",
                StrategyEngineType.SPREAD_TRADING.value: "spread_monitor",
            }

            return monitor_templates.get(strategy_type, "default_monitor")  # 默认返回通用监控模板

        except Exception as e:
            self.logger.error(f"获取监控模板失败: {e}")
            return "default_monitor"

    def get_strategy_monitoring_data(self, gateway_name: str, strategy_name: str) -> Dict[str, Any]:
        """获取策略监控数据.

        根据策略类型返回不同的监控数据结构。

        Args:
            gateway_name: 网关名称
            strategy_name: 策略名称

        Returns:
            Dict: 监控数据（包含策略类型、监控模板、监控数据）
        """
        try:
            # 检查策略是否存在
            if gateway_name not in self.strategy_instances:
                return {"success": False, "message": f"网关 '{gateway_name}' 不存在"}

            if strategy_name not in self.strategy_instances[gateway_name]:
                return {"success": False, "message": f"策略 '{strategy_name}' 不存在"}

            strategy_info = self.strategy_instances[gateway_name][strategy_name]

            # 识别策略类型
            strategy_class = strategy_info.get("class_name", "")
            strategy_type = self.identify_strategy_type(strategy_class, gateway_name, strategy_name)

            # 获取监控模板
            monitor_template = self.get_monitor_template_for_strategy(strategy_type)

            # 构建监控数据
            monitoring_data = {
                "success": True,
                "strategy_name": strategy_name,
                "strategy_class": strategy_class,
                "strategy_type": strategy_type,
                "monitor_template": monitor_template,
                "status": strategy_info.get("status", "stopped"),
                "data": self._get_strategy_specific_data(strategy_type, strategy_info),
            }

            return monitoring_data

        except Exception as e:
            self._log_error(f"获取策略监控数据[{gateway_name}.{strategy_name}]", e)
            return {"success": False, "message": f"获取失败: {str(e)}"}

    def _get_strategy_specific_data(
        self, strategy_type: str, strategy_info: Dict[str, Any]
    ) -> Dict[str, Any]:
        """获取策略类型特定的监控数据.

        Args:
            strategy_type: 策略类型
            strategy_info: 策略信息

        Returns:
            Dict: 策略特定监控数据
        """
        # 基础监控数据
        base_data = {
            "parameters": strategy_info.get("parameters", {}),
            "variables": strategy_info.get("variables", {}),
            "timestamp": datetime.now().isoformat(),
        }

        # 根据策略类型添加特定数据
        if strategy_type == StrategyEngineType.ALGO_TRADING.value:
            # 算法交易：执行进度、目标价格、成交进度
            base_data.update(
                {
                    "progress_percent": strategy_info.get("progress_percent", 0),
                    "target_price": strategy_info.get("target_price", 0),
                    "filled_volume": strategy_info.get("filled_volume", 0),
                    "target_volume": strategy_info.get("target_volume", 0),
                }
            )

        elif strategy_type == StrategyEngineType.CTA_STRATEGY.value:
            # CTA策略：持仓、K线数据
            base_data.update(
                {
                    "position": strategy_info.get("position", 0),
                    "entry_price": strategy_info.get("entry_price", 0),
                    "current_price": strategy_info.get("current_price", 0),
                    "pnl": strategy_info.get("pnl", 0),
                }
            )

        elif strategy_type == StrategyEngineType.OPTION_MASTER.value:
            # 期权策略：希腊字母、T型报价
            base_data.update(
                {
                    "delta": strategy_info.get("delta", 0),
                    "gamma": strategy_info.get("gamma", 0),
                    "vega": strategy_info.get("vega", 0),
                    "theta": strategy_info.get("theta", 0),
                    "underlying_price": strategy_info.get("underlying_price", 0),
                }
            )

        elif strategy_type == StrategyEngineType.PORTFOLIO_STRATEGY.value:
            # 组合策略：多品种持仓
            base_data.update(
                {
                    "positions": strategy_info.get("positions", {}),
                    "total_value": strategy_info.get("total_value", 0),
                    "weights": strategy_info.get("weights", {}),
                }
            )

        elif strategy_type == StrategyEngineType.SPREAD_TRADING.value:
            # 价差交易：价差实时价格
            base_data.update(
                {
                    "spread_price": strategy_info.get("spread_price", 0),
                    "leg1_price": strategy_info.get("leg1_price", 0),
                    "leg2_price": strategy_info.get("leg2_price", 0),
                    "spread_position": strategy_info.get("spread_position", 0),
                }
            )

        return base_data
