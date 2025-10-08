# -*- coding: utf-8 -*-
"""
代码编辑服务.

提供代码验证和分析功能。
"""

import ast
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CodeService:
    """代码编辑服务."""

    def __init__(self):
        """初始化代码编辑服务."""
        logger.info("代码编辑服务初始化完成")

    def validate_code(self, code: str, file_type: str = "python") -> Dict[str, Any]:
        """
        验证代码语法.

        Args:
            code: 代码内容
            file_type: 文件类型

        Returns:
            Dict[str, Any]: 验证结果
        """
        try:
            errors = []
            warnings = []
            is_valid = True
            strategy_type = None

            # 仅支持Python代码验证
            if file_type != "python":
                warnings.append(f"不支持的文件类型: {file_type}，跳过验证")
                return {
                    "is_valid": True,
                    "errors": errors,
                    "warnings": warnings,
                    "strategy_type": strategy_type,
                }

            # 使用ast.parse验证语法
            try:
                tree = ast.parse(code)

                # 检查代码结构，识别策略类型
                strategy_type = self._detect_strategy_type(tree)

                logger.info("代码验证成功，策略类型: %s", strategy_type)

            except SyntaxError as e:
                is_valid = False
                error_msg = f"语法错误 (行{e.lineno}): {e.msg}"
                errors.append(
                    {
                        "line": e.lineno,
                        "column": e.offset,
                        "message": error_msg,
                        "type": "SyntaxError",
                    }
                )
                logger.warning("代码语法错误: %s", error_msg)

            except Exception as e:
                is_valid = False
                errors.append(
                    {
                        "line": 0,
                        "column": 0,
                        "message": f"解析错误: {str(e)}",
                        "type": "ParseError",
                    }
                )
                logger.error("代码解析失败: %s", e)

            return {
                "is_valid": is_valid,
                "errors": errors,
                "warnings": warnings,
                "strategy_type": strategy_type,
            }

        except Exception as e:
            logger.error("代码验证失败: %s", e)
            raise

    def analyze_code(self, code: str) -> Dict[str, Any]:
        """
        分析代码结构.

        Args:
            code: 代码内容

        Returns:
            Dict[str, Any]: 分析结果
        """
        try:
            # 解析代码
            tree = ast.parse(code)

            # 提取类信息
            classes = []
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    class_info = self._analyze_class(node)
                    classes.append(class_info)

            # 查找策略类（继承自CtaTemplate等）
            strategy_class = None
            strategy_type = None
            for cls in classes:
                base_classes = cls.get("base_classes", [])
                for base in base_classes:
                    if "Template" in base or "Strategy" in base:
                        strategy_class = cls
                        strategy_type = self._infer_strategy_type(base)
                        break
                if strategy_class:
                    break

            # 如果没有找到策略类，使用第一个类
            if not strategy_class and classes:
                strategy_class = classes[0]
                strategy_type = "unknown"

            if strategy_class:
                result = {
                    "strategy_type": strategy_type or "unknown",
                    "class_name": strategy_class["name"],
                    "base_classes": strategy_class["base_classes"],
                    "parameters": strategy_class.get("parameters", []),
                    "variables": strategy_class.get("variables", []),
                    "methods": strategy_class.get("methods", []),
                }
            else:
                result = {
                    "strategy_type": "unknown",
                    "class_name": None,
                    "base_classes": [],
                    "parameters": [],
                    "variables": [],
                    "methods": [],
                }

            logger.info(
                "代码分析完成: 类名=%s, 类型=%s", result["class_name"], result["strategy_type"]
            )
            return result

        except SyntaxError as e:
            logger.error("代码语法错误: %s", e)
            raise ValueError(f"代码语法错误 (行{e.lineno}): {e.msg}") from e

        except Exception as e:
            logger.error("代码分析失败: %s", e)
            raise

    def _detect_strategy_type(self, tree: ast.AST) -> Optional[str]:
        """
        检测策略类型.

        Args:
            tree: AST树

        Returns:
            Optional[str]: 策略类型，如果未检测到则返回None
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        base_name = base.id
                        return self._infer_strategy_type(base_name)
                    elif isinstance(base, ast.Attribute):
                        base_name = base.attr
                        return self._infer_strategy_type(base_name)
        return None

    def _infer_strategy_type(self, base_class: str) -> str:
        """
        根据基类推断策略类型.

        Args:
            base_class: 基类名称

        Returns:
            str: 策略类型
        """
        if "CtaTemplate" in base_class or "CtaStrategy" in base_class:
            return "ctastrategy"
        elif "AlgoTemplate" in base_class:
            return "algotrading"
        elif "OptionStrategy" in base_class:
            return "optionmaster"
        elif "PortfolioStrategy" in base_class or "StrategyTemplate" in base_class:
            return "portfoliostrategy"
        elif "SpreadStrategy" in base_class:
            return "spreadtrading"
        elif "ScriptEngine" in base_class:
            return "scripttrader"
        return "unknown"

    def _analyze_class(self, node: ast.ClassDef) -> Dict[str, Any]:
        """
        分析类定义.

        Args:
            node: 类定义节点

        Returns:
            Dict[str, Any]: 类信息
        """
        # 提取基类
        base_classes = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_classes.append(base.id)
            elif isinstance(base, ast.Attribute):
                base_classes.append(base.attr)

        # 提取类属性（参数和变量）
        parameters = []
        variables = []
        methods = []

        for item in node.body:
            # 提取赋值语句（类属性）
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        attr_name = target.id
                        # 通过命名约定区分参数和变量
                        if attr_name.isupper() or attr_name.endswith("_param"):
                            parameters.append(
                                {
                                    "name": attr_name,
                                    "type": "parameter",
                                }
                            )
                        else:
                            variables.append(
                                {
                                    "name": attr_name,
                                    "type": "variable",
                                }
                            )

            # 提取方法定义
            elif isinstance(item, ast.FunctionDef):
                method_info = {
                    "name": item.name,
                    "args": [arg.arg for arg in item.args.args if arg.arg != "self"],
                    "is_private": item.name.startswith("_"),
                }
                methods.append(method_info)

        return {
            "name": node.name,
            "base_classes": base_classes,
            "parameters": parameters,
            "variables": variables,
            "methods": methods,
        }


__all__ = ["CodeService"]
