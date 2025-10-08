# -*- coding: utf-8 -*-
"""
策略管理验证工具.

提供策略部署、生命周期管理和模板识别验证功能。
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StrategyHelper:
    """策略管理验证工具类."""

    # VnPy支持的6种策略模板
    VNPY_STRATEGY_TEMPLATES = [
        "algotrading",
        "ctastrategy",
        "optionmaster",
        "portfoliostrategy",
        "scripttrader",
        "spreadtrading",
    ]

    def __init__(self):
        """初始化策略助手."""
        self.logger = logging.getLogger(self.__class__.__name__)

    def verify_strategy_deployment(
        self,
        strategy_pool: List[Dict[str, Any]],
        strategy_id: str,
    ) -> Dict[str, Any]:
        """
        验证策略部署.

        Args:
            strategy_pool: 策略池列表
            strategy_id: 策略ID

        Returns:
            验证结果字典
        """
        try:
            # 检查策略是否在池中
            strategy = None
            for s in strategy_pool:
                if s.get("id") == strategy_id:
                    strategy = s
                    break

            if not strategy:
                return {
                    "deployed": False,
                    "reason": f"策略未找到: {strategy_id}",
                }

            # 验证策略基本信息
            required_fields = ["id", "name", "status", "gateway"]
            missing_fields = [f for f in required_fields if f not in strategy]

            if missing_fields:
                return {
                    "deployed": True,
                    "valid": False,
                    "reason": f"缺少字段: {missing_fields}",
                }

            self.logger.info(f"策略部署验证通过: {strategy_id}, 状态={strategy.get('status')}")
            return {
                "deployed": True,
                "valid": True,
                "strategy": strategy,
            }

        except Exception as e:
            self.logger.error(f"策略部署验证失败: {e}")
            return {
                "deployed": False,
                "error": str(e),
            }

    def verify_strategy_lifecycle_transition(
        self,
        strategy: Dict[str, Any],
        from_status: str,
        to_status: str,
    ) -> bool:
        """
        验证策略状态流转.

        Args:
            strategy: 策略对象
            from_status: 起始状态
            to_status: 目标状态

        Returns:
            是否流转成功
        """
        try:
            current_status = strategy.get("status")

            # 检查起始状态
            if current_status != from_status:
                self.logger.warning(f"起始状态不匹配: 当前={current_status}, 期望={from_status}")
                return False

            # 检查状态流转的合法性
            valid_transitions = {
                "pending": ["running", "stopped"],
                "running": ["stopped", "error"],
                "stopped": ["running", "deleted"],
                "error": ["stopped", "deleted"],
            }

            allowed = valid_transitions.get(from_status, [])
            if to_status not in allowed:
                self.logger.warning(f"非法状态流转: {from_status} -> {to_status}, 允许={allowed}")
                return False

            self.logger.info(f"策略状态流转验证通过: {from_status} -> {to_status}")
            return True

        except Exception as e:
            self.logger.error(f"策略状态流转验证失败: {e}")
            return False

    def identify_strategy_template(
        self,
        strategy_code: str,
    ) -> Optional[str]:
        """
        识别策略模板类型.

        Args:
            strategy_code: 策略代码

        Returns:
            模板类型，未识别返回None
        """
        try:
            # 简单的模板识别逻辑（基于import语句）
            for template in self.VNPY_STRATEGY_TEMPLATES:
                if f"from vnpy_{template}" in strategy_code:
                    self.logger.info(f"识别到策略模板: {template}")
                    return template
                if f"import vnpy_{template}" in strategy_code:
                    self.logger.info(f"识别到策略模板: {template}")
                    return template

            # 检查是否为scripttrader（无特定import）
            if "StrategyTemplate" in strategy_code or "Strategy" in strategy_code:
                self.logger.info("识别到策略模板: scripttrader (默认)")
                return "scripttrader"

            self.logger.warning("未识别到策略模板")
            return None

        except Exception as e:
            self.logger.error(f"策略模板识别失败: {e}")
            return None

    def verify_monitoring_interface_adaptation(
        self,
        strategy_template: str,
        monitoring_widget,
    ) -> Dict[str, Any]:
        """
        验证监控界面适配.

        Args:
            strategy_template: 策略模板类型
            monitoring_widget: 监控界面组件

        Returns:
            验证结果字典
        """
        try:
            # 检查监控组件类型
            widget_type = getattr(monitoring_widget, "_widget_type", None)

            # 验证模板与监控界面的匹配
            expected_widget_types = {
                "algotrading": "algo_monitor",
                "ctastrategy": "cta_monitor",
                "optionmaster": "option_monitor",
                "portfoliostrategy": "portfolio_monitor",
                "scripttrader": "default_monitor",
                "spreadtrading": "spread_monitor",
            }

            expected_type = expected_widget_types.get(strategy_template, "default_monitor")
            matched = widget_type == expected_type

            result = {
                "adapted": True,
                "matched": matched,
                "strategy_template": strategy_template,
                "widget_type": widget_type,
                "expected_type": expected_type,
            }

            if matched:
                self.logger.info(
                    f"监控界面适配正确: template={strategy_template}, widget={widget_type}"
                )
            else:
                self.logger.warning(
                    f"监控界面适配不匹配: template={strategy_template}, "
                    f"widget={widget_type}, expected={expected_type}"
                )

            return result

        except Exception as e:
            self.logger.error(f"监控界面适配验证失败: {e}")
            return {
                "adapted": False,
                "error": str(e),
            }

    def verify_batch_strategy_control(
        self,
        strategy_pool_before: List[Dict[str, Any]],
        strategy_pool_after: List[Dict[str, Any]],
        expected_status: str,
    ) -> Dict[str, Any]:
        """
        验证批量策略控制.

        Args:
            strategy_pool_before: 操作前策略池
            strategy_pool_after: 操作后策略池
            expected_status: 期望的目标状态

        Returns:
            验证结果字典
        """
        try:
            # 统计状态变化
            changed_count = 0
            unchanged_count = 0
            error_count = 0

            for before, after in zip(strategy_pool_before, strategy_pool_after):
                before_status = before.get("status")
                after_status = after.get("status")

                if after_status == expected_status:
                    if before_status != expected_status:
                        changed_count += 1
                    else:
                        unchanged_count += 1
                elif after_status == "error":
                    error_count += 1
                else:
                    unchanged_count += 1

            total = len(strategy_pool_before)
            success_rate = changed_count / total if total > 0 else 0.0

            result = {
                "success": success_rate >= 0.8,  # 80%以上成功
                "total_count": total,
                "changed_count": changed_count,
                "unchanged_count": unchanged_count,
                "error_count": error_count,
                "success_rate": success_rate,
                "expected_status": expected_status,
            }

            self.logger.info(
                f"批量控制验证: 总数={total}, 成功={changed_count}, "
                f"失败={error_count}, 成功率={success_rate:.2%}"
            )
            return result

        except Exception as e:
            self.logger.error(f"批量策略控制验证失败: {e}")
            return {
                "success": False,
                "error": str(e),
            }

    def verify_gateway_strategy_isolation(
        self,
        gateway1_pool: List[Dict[str, Any]],
        gateway2_pool: List[Dict[str, Any]],
    ) -> bool:
        """
        验证多网关策略池隔离.

        Args:
            gateway1_pool: 网关1的策略池
            gateway2_pool: 网关2的策略池

        Returns:
            是否隔离正确
        """
        try:
            # 提取策略ID
            gateway1_ids = {s.get("id") for s in gateway1_pool}
            gateway2_ids = {s.get("id") for s in gateway2_pool}

            # 检查是否有重叠
            overlap = gateway1_ids & gateway2_ids

            if overlap:
                self.logger.warning(f"网关策略池有重叠: {overlap}")
                return False

            self.logger.info(
                f"网关策略池隔离验证通过: gateway1={len(gateway1_ids)}, "
                f"gateway2={len(gateway2_ids)}"
            )
            return True

        except Exception as e:
            self.logger.error(f"网关策略池隔离验证失败: {e}")
            return False

    def verify_portfoliostrategy_special_handling(
        self,
        strategy: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        验证portfoliostrategy的特殊处理.

        portfoliostrategy是单策略多品种，而非多策略。

        Args:
            strategy: 策略对象

        Returns:
            验证结果字典
        """
        try:
            strategy_type = strategy.get("type")
            symbols = strategy.get("symbols", [])

            is_portfolio = strategy_type == "portfoliostrategy"
            is_multi_symbol = len(symbols) > 1

            # portfoliostrategy应该支持多品种
            correct_handling = is_portfolio and is_multi_symbol

            result = {
                "is_portfolio": is_portfolio,
                "symbol_count": len(symbols),
                "symbols": symbols,
                "correct_handling": correct_handling,
            }

            if correct_handling:
                self.logger.info(f"portfoliostrategy特殊处理正确: 品种数={len(symbols)}")
            else:
                self.logger.warning(
                    f"portfoliostrategy特殊处理异常: is_portfolio={is_portfolio}, "
                    f"symbols={len(symbols)}"
                )

            return result

        except Exception as e:
            self.logger.error(f"portfoliostrategy特殊处理验证失败: {e}")
            return {
                "correct_handling": False,
                "error": str(e),
            }


# 导出公共接口
__all__ = ["StrategyHelper"]
