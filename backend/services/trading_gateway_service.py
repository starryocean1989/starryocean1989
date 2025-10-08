# -*- coding: utf-8 -*-
"""
交易网关服务.

提供完整的交易网关管理功能，包括：
- 7种网关的注册和管理（CTP, CTP mini, Sopt, TTS, IB, PaperAccount, TDX Gateway）
- 策略实例管理（策略池、部署、控制）
- 交易监控（6种策略模板适配、交易数据、风险监控）
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from enum import Enum

from backend.services.base_service import BaseService


class GatewayType(Enum):
    """网关类型枚举."""

    CTP = "ctp"  # 国内期货、期权
    CTP_MINI = "ctp_mini"  # 国内期货、期权（迷你版）
    SOPT = "sopt"  # 国内ETF期权
    TTS = "tts"  # 国内期货仿真交易
    IB = "ib"  # 海外证券、期货、期权、贵金属
    PAPER_ACCOUNT = "paperaccount"  # 纯本地模拟交易
    TDX_GATEWAY = "tdx"  # 国内股票交易（通达信）


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

    def __init__(self):
        """初始化交易网关服务."""
        super().__init__()

        # 网关实例管理
        self.gateway_instances: Dict[str, Dict[str, Any]] = {}

        # 策略实例管理（按网关组织）
        self.strategy_instances: Dict[str, Dict[str, Any]] = {}

        # 网关配置模板
        self.gateway_config_templates = self._init_gateway_templates()

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
            GatewayType.TDX_GATEWAY.value: {
                "name": "TDX Gateway",
                "description": "国内股票交易（通达信）",
                "requires_address": True,
                "config_fields": ["服务器地址", "用户名", "密码", "通达信路径"],
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

            # PaperAccount
            try:
                from vnpy_paperaccount import PaperAccountGateway

                self.gateway_classes[GatewayType.PAPER_ACCOUNT.value] = PaperAccountGateway
                self.logger.info("✅ PaperAccount网关类可用")
            except ImportError:
                self.logger.warning("⚠️ PaperAccount网关类不可用")

            # TODO: 导入其他网关类

        except Exception as e:
            self.logger.error("初始化网关类失败: %s", e, exc_info=True)

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
            self.logger.info(f"网关类 {gateway_type} 已注册到MainEngine")

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

            self.logger.info(f"网关 '{gateway_name}' (类型: {gateway_type}) 创建成功")

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

            # 调用main_engine连接
            # gateway_name作为vnpy中的gateway_name参数
            self.main_engine.connect(connect_setting, gateway_type)

            # 更新状态
            gateway_info["connected"] = True

            self.logger.info(f"网关 '{gateway_name}' 连接请求已发送")

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
            gateway_type = gateway_info["type"]

            # 先停止该网关的所有策略
            self._stop_gateway_strategies(gateway_name)

            # 断开网关（使用gateway_type作为gateway_name参数）
            if self.main_engine:
                self.main_engine.close()  # 关闭所有网关连接
                # 注意：VNPY的close()会关闭所有网关，如果需要单独关闭，需要其他方法

            gateway_info["connected"] = False

            self.logger.info(f"网关 '{gateway_name}' 已断开")

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

            # 删除网关
            if self.terminal_engine:
                self.terminal_engine.remove_gateway(gateway_name)

            del self.gateway_instances[gateway_name]
            if gateway_name in self.strategy_instances:
                del self.strategy_instances[gateway_name]

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
            engine_name = strategy_params.get("engine_type", "CtaStrategy")

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

            # 准备策略配置
            vt_symbols = strategy_params.get("vt_symbols", [])
            setting = {
                k: v for k, v in strategy_params.items() if k not in ["engine_type", "vt_symbols"]
            }

            # 部署策略到引擎
            try:
                strategy_engine.add_strategy(
                    class_name=strategy_class,
                    strategy_name=strategy_name,
                    vt_symbols=vt_symbols,
                    setting=setting,
                )

                self.logger.info(f"策略 '{strategy_name}' 已添加到引擎 '{engine_name}'")

            except Exception as e:
                self.logger.error(f"添加策略失败: {e}", exc_info=True)
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
                "vt_symbols": vt_symbols,
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
            engine_name = strategy_info.get("engine_name", "CtaStrategy")

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

            # 初始化并启动策略
            try:
                # 先初始化策略
                strategy_engine.init_strategy(strategy_name)
                self.logger.info(f"策略 '{strategy_name}' 初始化完成")

                # 启动策略
                strategy_engine.start_strategy(strategy_name)
                self.logger.info(f"策略 '{strategy_name}' 已启动")

            except Exception as e:
                self.logger.error(f"启动策略失败: {e}", exc_info=True)
                return {
                    "success": False,
                    "message": f"启动策略失败: {str(e)}",
                }

            # 更新状态
            strategy_info["status"] = "running"

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
            engine_name = strategy_info.get("engine_name", "CtaStrategy")

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
                self.logger.info(f"策略 '{strategy_name}' 已停止")

            except Exception as e:
                self.logger.error(f"停止策略失败: {e}", exc_info=True)
                return {
                    "success": False,
                    "message": f"停止策略失败: {str(e)}",
                }

            # 更新状态
            strategy_info["status"] = "stopped"

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
        for gateway_name in self.strategy_instances.keys():
            self._stop_gateway_strategies(gateway_name)

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
