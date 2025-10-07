# -*- coding: utf-8 -*-
"""
代码分析服务.

提供代码验证、语法检查、策略类型识别等功能。
"""

import ast
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class CodeService:
    """代码分析服务."""

    def __init__(self):
        """初始化代码服务."""
        self.strategy_base_classes = {
            "CtaTemplate": "ctastrategy",
            "AlgoTemplate": "algotrading",
            "OptionTemplate": "optionmaster",
            "StrategyTemplate": "portfoliostrategy",
            "SpreadStrategyTemplate": "spreadtrading",
            "ScriptEngine": "scripttrader",
        }
        logger.info("代码分析服务初始化完成")

    def validate_code(self, code: str, file_type: str = "python") -> Dict[str, Any]:
        """验证代码语法."""
        try:
            errors = []
            warnings = []
            is_valid = True
            strategy_type = None

            if file_type == "python":
                try:
                    # 解析Python代码
                    tree = ast.parse(code)

                    # 识别策略类型
                    strategy_type = self._identify_strategy_type(tree)

                except SyntaxError as e:
                    is_valid = False
                    errors.append(
                        {
                            "line": e.lineno,
                            "column": e.offset,
                            "message": str(e.msg),
                            "type": "SyntaxError",
                        }
                    )

            return {
                "is_valid": is_valid,
                "errors": errors,
                "warnings": warnings,
                "strategy_type": strategy_type,
            }

        except Exception as e:
            logger.error("验证代码失败: %s", e)
            raise

    def analyze_code(self, code: str) -> Dict[str, Any]:
        """分析代码结构."""
        try:
            tree = ast.parse(code)

            # 分析类定义
            classes = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_info = {
                        "class_name": node.name,
                        "base_classes": [
                            base.id for base in node.bases if isinstance(base, ast.Name)
                        ],
                        "methods": [
                            m.name for m in node.body if isinstance(m, ast.FunctionDef)
                        ],
                    }
                    classes.append(class_info)

            # 识别策略类型
            strategy_type = self._identify_strategy_type(tree)

            # 提取参数定义
            parameters = self._extract_parameters(tree)

            # 提取类变量
            variables = self._extract_class_variables(tree)

            return {
                "strategy_type": strategy_type,
                "classes": classes,
                "parameters": parameters,
                "variables": variables,
            }

        except Exception as e:
            logger.error("分析代码失败: %s", e)
            raise

    def _identify_strategy_type(self, tree: ast.AST) -> Optional[str]:
        """识别策略类型."""
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        base_name = base.id
                        if base_name in self.strategy_base_classes:
                            return self.strategy_base_classes[base_name]

        return None

    def _extract_parameters(self, tree: ast.AST) -> List[Dict[str, Any]]:
        """提取参数定义."""
        parameters = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.AnnAssign):
                        if isinstance(item.target, ast.Name):
                            param_name = item.target.id
                            # 获取默认值
                            default_value = None
                            if item.value:
                                if isinstance(item.value, ast.Constant):
                                    default_value = item.value.value

                            parameters.append(
                                {
                                    "name": param_name,
                                    "default": default_value,
                                }
                            )

        return parameters

    def _extract_class_variables(self, tree: ast.AST) -> List[str]:
        """提取类变量."""
        variables = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.Assign):
                        for target in item.targets:
                            if isinstance(target, ast.Name):
                                variables.append(target.id)

        return variables


__all__ = ["CodeService"]
