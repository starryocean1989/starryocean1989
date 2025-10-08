# -*- coding: utf-8 -*-
"""
策略模板服务.

提供策略模板管理功能。
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class TemplateService:
    """策略模板服务."""

    def __init__(self):
        """初始化模板服务."""
        self._builtin_templates = self._load_builtin_templates()
        logger.info("策略模板服务初始化完成，内置模板数: %d", len(self._builtin_templates))

    def _load_builtin_templates(self) -> List[Dict[str, Any]]:
        """加载内置模板."""
        templates = [
            {
                "template_id": "cta_basic",
                "template_name": "CTA策略基础模板",
                "strategy_type": "ctastrategy",
                "description": "基于CtaTemplate的CTA策略模板",
                "template_code": '''# -*- coding: utf-8 -*-
from vnpy_ctastrategy import CtaTemplate
from vnpy.trader.object import BarData, TickData


class MyCtaStrategy(CtaTemplate):
    """CTA策略示例."""

    author = "Your Name"

    # 策略参数
    fast_window = 10
    slow_window = 20

    # 策略变量
    fast_ma = 0.0
    slow_ma = 0.0

    parameters = ["fast_window", "slow_window"]
    variables = ["fast_ma", "slow_ma"]

    def __init__(self, cta_engine, strategy_name, vt_symbol, setting):
        """初始化."""
        super().__init__(cta_engine, strategy_name, vt_symbol, setting)

    def on_init(self):
        """初始化回调."""
        self.write_log("策略初始化")

    def on_start(self):
        """启动回调."""
        self.write_log("策略启动")

    def on_stop(self):
        """停止回调."""
        self.write_log("策略停止")

    def on_tick(self, tick: TickData):
        """Tick回调."""
        pass

    def on_bar(self, bar: BarData):
        """K线回调."""
        pass
''',
                "is_builtin": True,
                "created_at": "2024-01-01T00:00:00",
            },
            {
                "template_id": "algo_twap",
                "template_name": "TWAP算法模板",
                "strategy_type": "algotrading",
                "description": "时间加权平均价格算法模板",
                "template_code": '''# -*- coding: utf-8 -*-
from vnpy_algotrading import AlgoTemplate


class TwapAlgo(AlgoTemplate):
    """TWAP算法示例."""

    display_name = "TWAP"

    default_setting = {
        "time_interval": 60,
    }

    variables = []

    def __init__(self, algo_engine, algo_name, setting):
        """初始化."""
        super().__init__(algo_engine, algo_name, setting)
''',
                "is_builtin": True,
                "created_at": "2024-01-01T00:00:00",
            },
        ]

        return templates

    def list_templates(self, strategy_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """获取模板列表."""
        try:
            templates = self._builtin_templates.copy()

            if strategy_type:
                templates = [t for t in templates if t["strategy_type"] == strategy_type]

            return templates

        except Exception as e:
            logger.error("获取模板列表失败: %s", e)
            raise

    def get_template(self, template_id: str) -> Optional[Dict[str, Any]]:
        """获取模板详情."""
        try:
            for template in self._builtin_templates:
                if template["template_id"] == template_id:
                    return template

            return None

        except Exception as e:
            logger.error("获取模板详情失败: %s", e)
            raise

    def apply_template(
        self,
        template_id: str,
        file_name: str,
        folder_path: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """应用模板创建文件."""
        try:
            template = self.get_template(template_id)
            if not template:
                raise ValueError(f"模板不存在: {template_id}")

            # 获取模板代码
            code = template["template_code"]

            # 替换模板中的占位符
            code = self._replace_placeholders(code, parameters)

            result = {
                "file_id": f"{folder_path}/{file_name}".replace("\\", "/"),
                "file_name": file_name,
                "folder_path": folder_path,
                "template_id": template_id,
                "code": code,
                "created_at": datetime.now().isoformat(),
            }

            logger.info("模板应用成功: template_id=%s", template_id)
            return result

        except Exception as e:
            logger.error("应用模板失败: %s", e)
            raise

    def _replace_placeholders(
        self, content: str, parameters: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        替换模板中的占位符.

        Args:
            content: 模板内容
            parameters: 参数字典

        Returns:
            str: 替换后的内容
        """
        if not parameters:
            parameters = {}

        # 默认参数
        defaults = {
            "author": parameters.get("author", "Anonymous"),
            "strategy_name": parameters.get("strategy_name", "MyStrategy"),
            "description": parameters.get("description", "自定义策略"),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "parameters": self._format_parameters(parameters.get("strategy_parameters", [])),
            "variables": self._format_variables(parameters.get("strategy_variables", [])),
        }

        # 替换所有占位符（支持 {{key}} 格式）
        result = content
        for key, value in defaults.items():
            placeholder = f"{{{{{key}}}}}"
            result = result.replace(placeholder, str(value))

        # 同时支持传入的自定义参数
        for key, value in parameters.items():
            placeholder = f"{{{{{key}}}}}"
            result = result.replace(placeholder, str(value))

        return result

    def _format_parameters(self, params: List[Dict[str, Any]]) -> str:
        """
        格式化策略参数.

        Args:
            params: 参数列表

        Returns:
            str: 格式化后的参数代码
        """
        if not params:
            return "# 无参数"

        lines = []
        for param in params:
            name = param.get("name", "param")
            value = param.get("value", 0)
            comment = param.get("comment", "")

            if comment:
                lines.append(f"    {name} = {value}  # {comment}")
            else:
                lines.append(f"    {name} = {value}")

        return "\n".join(lines)

    def _format_variables(self, variables: List[Dict[str, Any]]) -> str:
        """
        格式化策略变量.

        Args:
            variables: 变量列表

        Returns:
            str: 格式化后的变量代码
        """
        if not variables:
            return "# 无变量"

        lines = []
        for var in variables:
            name = var.get("name", "var")
            value = var.get("value", 0)
            comment = var.get("comment", "")

            if comment:
                lines.append(f"    {name} = {value}  # {comment}")
            else:
                lines.append(f"    {name} = {value}")

        return "\n".join(lines)


__all__ = ["TemplateService"]
