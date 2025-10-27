# -*- coding: utf-8 -*-
"""
规则验证器模块

验证YAML配置文件的语法和完整性
"""

import yaml
from pathlib import Path
from typing import Dict, List, Any


class RuleValidator:
    """规则验证器（检查YAML配置正确性）

    验证内容：
    - YAML语法正确性
    - 日志类型/级别/目标是否合法
    - 必需字段是否存在
    - 阶段/模块/场景配置完整性

    使用场景：
    - 系统启动时自动验证
    - 配置文件修改后验证
    - CI/CD流程中验证
    """

    VALID_LOG_TYPES = {"SYSTEM", "PROGRESS", "NOTIFICATION", "ALERT", "USER_FEEDBACK", "DEBUG"}
    VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    VALID_TARGETS = {
        "console",
        "file",
        "database",
        "event",
        "event_throttled",
        "statusbar",
        "ui_dialog",
        "zmq_push",
        "email",
        "sms",
    }

    def __init__(self, config_dir: str):
        """初始化验证器

        Args:
            config_dir: 配置文件目录路径
        """
        self.config_dir = Path(config_dir)
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate_all(self) -> bool:
        """验证所有配置文件

        Returns:
            是否验证通过（True表示无错误）
        """
        self.errors = []
        self.warnings = []

        # 验证各配置文件
        self._validate_file("rules_global.yaml")
        self._validate_file("rules_stage.yaml", check_stage=True)
        self._validate_file("rules_module.yaml", check_module=True)
        self._validate_file("rules_scenario.yaml", check_scenario=True)

        # 输出验证结果
        if self.errors:
            print("❌ 配置验证失败:")
            for error in self.errors:
                print(f"  - {error}")
            return False

        if self.warnings:
            print("⚠️  配置警告:")
            for warning in self.warnings:
                print(f"  - {warning}")

        print("✅ 配置验证通过")
        return True

    def _validate_file(
        self,
        filename: str,
        check_stage: bool = False,
        check_module: bool = False,
        check_scenario: bool = False,
    ):
        """验证单个配置文件

        Args:
            filename: 文件名
            check_stage: 是否检查阶段规则
            check_module: 是否检查模块规则
            check_scenario: 是否检查场景规则
        """
        file_path = self.config_dir / filename

        if not file_path.exists():
            self.errors.append(f"{filename}: 文件不存在")
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                rules: Any = yaml.safe_load(f) or {}
        except Exception as e:
            self.errors.append(f"{filename}: YAML解析失败 - {e}")
            return

        # 验证规则结构
        if check_stage:
            self._validate_stage_rules(filename, rules)
        elif check_module:
            self._validate_module_rules(filename, rules)
        elif check_scenario:
            self._validate_scenario_rules(filename, rules)
        else:
            self._validate_global_rules(filename, rules)

    def _validate_global_rules(self, filename: str, rules: Any):
        """验证全局规则

        Args:
            filename: 文件名
            rules: 规则字典
        """
        # 检查所有必需的LogType是否存在
        required_types = self.VALID_LOG_TYPES
        for log_type in required_types:
            if log_type not in rules:
                self.errors.append(f"{filename}: 缺少LogType '{log_type}'")

        for log_type, levels in rules.items():
            if log_type not in self.VALID_LOG_TYPES:
                self.errors.append(f"{filename}: 无效的日志类型 '{log_type}'")
                continue

            if not isinstance(levels, dict):
                self.errors.append(f"{filename}: {log_type} 的值必须是字典")
                continue

            for level, targets in levels.items():
                if level not in self.VALID_LEVELS:
                    self.errors.append(f"{filename}: {log_type}.{level} 无效的级别")
                    continue

                if not isinstance(targets, list):
                    self.errors.append(f"{filename}: {log_type}.{level} 的值必须是列表")
                    continue

                for target in targets:
                    if target not in self.VALID_TARGETS:
                        self.errors.append(f"{filename}: {log_type}.{level} 无效的目标 '{target}'")

    def _validate_stage_rules(self, filename: str, rules: Any):
        """验证阶段规则

        Args:
            filename: 文件名
            rules: 规则字典
        """
        for stage_key, stage_config in rules.items():
            if not stage_key.startswith("stage_"):
                self.warnings.append(f"{filename}: 阶段键 '{stage_key}' 建议以 'stage_' 开头")

            # 检查是否有描述
            if "description" not in stage_config:
                self.warnings.append(f"{filename}: {stage_key} 缺少 'description' 字段")

            # 验证日志类型规则
            for log_type, levels in stage_config.items():
                if log_type in ["description", "duration", "priority"]:
                    continue  # 跳过元数据字段

                if log_type not in self.VALID_LOG_TYPES:
                    self.errors.append(f"{filename}: {stage_key}.{log_type} 无效的日志类型")
                    continue

                self._validate_levels(filename, f"{stage_key}.{log_type}", levels)

    def _validate_module_rules(self, filename: str, rules: Any):
        """验证模块规则

        Args:
            filename: 文件名
            rules: 规则字典
        """
        for module_key, module_config in rules.items():
            if not module_key.startswith("module_"):
                self.warnings.append(f"{filename}: 模块键 '{module_key}' 建议以 'module_' 开头")

            # 检查是否有source_modules
            if "source_modules" not in module_config:
                self.errors.append(f"{filename}: {module_key} 缺少 'source_modules' 字段")

            # 验证日志类型规则
            for log_type, levels in module_config.items():
                if log_type in ["source_modules", "priority", "transport"]:
                    continue  # 跳过元数据字段

                if log_type not in self.VALID_LOG_TYPES:
                    self.errors.append(f"{filename}: {module_key}.{log_type} 无效的日志类型")
                    continue

                self._validate_levels(filename, f"{module_key}.{log_type}", levels)

    def _validate_scenario_rules(self, filename: str, rules: Any):
        """验证场景规则

        Args:
            filename: 文件名
            rules: 规则字典
        """
        for scenario_key, scenario_config in rules.items():
            if not scenario_key.startswith("scenario_"):
                self.warnings.append(f"{filename}: 场景键 '{scenario_key}' 建议以 'scenario_' 开头")

            # 检查是否有描述
            if "description" not in scenario_config:
                self.warnings.append(f"{filename}: {scenario_key} 缺少 'description' 字段")

            # 验证日志类型规则
            for log_type, levels in scenario_config.items():
                if log_type in ["description", "duration", "trigger", "frequency", "priority"]:
                    continue  # 跳过元数据字段

                if log_type not in self.VALID_LOG_TYPES:
                    self.errors.append(f"{filename}: {scenario_key}.{log_type} 无效的日志类型")
                    continue

                self._validate_levels(filename, f"{scenario_key}.{log_type}", levels)

    def _validate_levels(self, filename: str, prefix: str, levels: Any):
        """验证级别和目标

        Args:
            filename: 文件名
            prefix: 前缀（用于错误消息）
            levels: 级别字典
        """
        if not isinstance(levels, dict):
            self.errors.append(f"{filename}: {prefix} 的值必须是字典")
            return

        for level, targets in levels.items():
            if level not in self.VALID_LEVELS:
                self.errors.append(f"{filename}: {prefix}.{level} 无效的级别")
                continue

            if not isinstance(targets, list):
                self.errors.append(f"{filename}: {prefix}.{level} 的值必须是列表")
                continue

            for target in targets:
                if target not in self.VALID_TARGETS:
                    self.errors.append(f"{filename}: {prefix}.{level} 无效的目标 '{target}'")


# 使用示例
if __name__ == "__main__":
    validator = RuleValidator("backend/infrastructure/system_vnpy/config")
    if validator.validate_all():
        print("✅ 所有配置文件验证通过")
    else:
        print("❌ 配置文件验证失败")
        exit(1)
