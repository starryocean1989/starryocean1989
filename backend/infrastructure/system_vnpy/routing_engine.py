# -*- coding: utf-8 -*-
"""
路由规则引擎模块

实现四层路由决策：场景 > 模块 > 阶段 > 全局
"""

import yaml
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any, TYPE_CHECKING

from .rule_cache import RuleCache

if TYPE_CHECKING:
    from .unified_logging import UnifiedLogRecord


class RoutingRuleEngine:
    """四层路由规则引擎（带缓存优化）

    四层架构：
    - Layer 4: 场景规则 (scenario_bulk_download) - 最高优先级
    - Layer 3: 模块规则 (module_data_center)
    - Layer 2: 阶段规则 (stage_downloading)
    - Layer 1: 全局规则 (global_defaults) - 最低优先级（兜底）

    特性：
    - YAML外部配置
    - 规则缓存（5秒TTL）
    - 阶段动态切换
    - 运行模式切换（dev/prod/ops）
    - 热更新支持
    """

    def __init__(self, config_dir: str = "backend/infrastructure/system_vnpy/config"):
        """初始化路由引擎

        Args:
            config_dir: 配置文件目录路径（相对于项目根目录）
        """
        # 🔧 修复路径问题：将相对路径转换为绝对路径
        # 计算项目根目录（从routing_engine.py所在位置向上3级）
        if not Path(config_dir).is_absolute():
            module_dir = Path(__file__).parent  # backend/infrastructure/system_vnpy
            project_root = module_dir.parent.parent.parent  # 向上3级到项目根目录
            self.config_dir = project_root / config_dir
        else:
            self.config_dir = Path(config_dir)

        self.logger = logging.getLogger(__name__)

        # 加载四层规则
        self.global_rules = self._load_yaml("rules_global.yaml")
        self.stage_rules = self._load_yaml("rules_stage.yaml")
        self.module_rules = self._load_yaml("rules_module.yaml")
        self.scenario_rules = self._load_yaml("rules_scenario.yaml")

        # 运行时状态
        self.current_stage = "startup"
        self.run_mode = "prod"  # dev/prod/ops

        # 规则缓存（性能优化）
        self.cache = RuleCache(ttl_seconds=5)

        # 统计信息
        self._route_count = 0

        self.logger.info("路由规则引擎初始化完成")
        self.logger.info(f"  - 全局规则: {len(self.global_rules)} 个LogType")
        self.logger.info(f"  - 阶段规则: {len(self.stage_rules)} 个阶段")
        self.logger.info(f"  - 模块规则: {len(self.module_rules)} 个模块")
        self.logger.info(f"  - 场景规则: {len(self.scenario_rules)} 个场景")

    def _load_yaml(self, filename: str) -> Any:
        """加载YAML配置文件

        Args:
            filename: 配置文件名

        Returns:
            解析后的字典，如果文件不存在或解析失败返回空字典
        """
        file_path = self.config_dir / filename
        if not file_path.exists():
            self.logger.warning("配置文件不存在: %s", file_path)
            return {}

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                rules = yaml.safe_load(f) or {}
            self.logger.info("加载配置文件: %s (%d 个规则)", filename, len(rules))
            return rules
        except yaml.YAMLError as e:
            self.logger.error("YAML语法错误: %s, 错误: %s", filename, e)
            return {}
        except Exception as e:
            self.logger.exception("加载配置文件失败: %s, 错误: %s", filename, e)
            return {}

    def route(self, record: "UnifiedLogRecord") -> List[str]:
        """执行路由决策（带缓存优化）

        优先级：场景 > 模块 > 阶段 > 全局

        Args:
            record: 统一日志记录对象

        Returns:
            路由目标列表，如 ["file", "console", "database"]
        """
        self._route_count += 1

        # 提取路由参数
        log_type = record.type.value.upper()  # 转为大写以匹配YAML配置
        level = logging.getLevelName(record.level)
        module = record.module
        scenario = record.details.get("scenario") if record.details else None

        # 构造缓存键
        cache_key = (log_type, level, module, scenario, self.current_stage)

        # 先查缓存（性能优化）
        cached_targets = self.cache.get(cache_key)
        if cached_targets is not None:
            return cached_targets

        # 缓存未命中，执行四层路由
        targets = self._route_with_layers(log_type, level, module, scenario)

        # 写入缓存
        self.cache.set(cache_key, targets)

        return targets

    def _route_with_layers(
        self, log_type: str, level: str, module: str, scenario: Optional[str]
    ) -> List[str]:
        """四层路由逻辑

        Args:
            log_type: 日志类型（SYSTEM/PROGRESS/NOTIFICATION等）
            level: 日志级别（DEBUG/INFO/WARNING等）
            module: 模块名称
            scenario: 场景名称（可选）

        Returns:
            路由目标列表
        """
        # Layer 4: 场景规则（最高优先级）
        if scenario:
            scenario_key = f"scenario_{scenario}"
            scenario_config = self.scenario_rules.get(scenario_key, {})
            targets = scenario_config.get(log_type, {}).get(level)
            if targets:
                return targets

        # Layer 3: 模块规则
        for module_key, module_config in self.module_rules.items():
            # 检查模块是否匹配
            source_modules = module_config.get("source_modules", [])
            if any(mod in module for mod in source_modules):
                targets = module_config.get(log_type, {}).get(level)
                if targets:
                    return targets

        # Layer 2: 阶段规则
        stage_key = f"stage_{self.current_stage}"
        stage_config = self.stage_rules.get(stage_key, {})
        targets = stage_config.get(log_type, {}).get(level)
        if targets:
            return targets

        # Layer 1: 全局规则（兜底）
        targets = self.global_rules.get(log_type, {}).get(level, ["file"])
        return targets

    def set_stage(self, stage: str):
        """切换阶段（清空缓存）

        阶段列表：
        - startup: 启动阶段
        - sensing: 数据感知阶段
        - downloading: 下载阶段
        - quality_scan: 质量扫描阶段
        - trading: 交易阶段
        - backtest: 回测阶段
        - monitoring: 监控阶段
        - shutdown: 关闭阶段

        Args:
            stage: 阶段名称
        """
        old_stage = self.current_stage
        self.current_stage = stage

        # 清空缓存（因为阶段规则改变了）
        self.cache.clear()

        self.logger.info(f"阶段切换: {old_stage} -> {stage}")

    def set_run_mode(self, mode: str):
        """切换运行模式

        运行模式：
        - dev: 开发模式（DEBUG全量输出）
        - prod: 生产模式（INFO+节流）
        - ops: 运维模式（告警强化）

        Args:
            mode: 运行模式（dev/prod/ops）
        """
        if mode not in ["dev", "prod", "ops"]:
            self.logger.warning(f"无效的运行模式: {mode}，保持当前模式: {self.run_mode}")
            return

        old_mode = self.run_mode
        self.run_mode = mode

        self.logger.info(f"运行模式切换: {old_mode} -> {mode}")

    def reload_rules(self):
        """热更新规则（重新加载YAML）

        用途：修改YAML配置后，无需重启即可生效
        """
        self.logger.info("开始热更新路由规则...")

        # 重新加载所有配置文件
        self.global_rules = self._load_yaml("rules_global.yaml")
        self.stage_rules = self._load_yaml("rules_stage.yaml")
        self.module_rules = self._load_yaml("rules_module.yaml")
        self.scenario_rules = self._load_yaml("rules_scenario.yaml")

        # 清空缓存
        self.cache.clear()

        self.logger.info("路由规则热更新完成")

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息

        Returns:
            统计信息字典，包含：
            - total_routes: 总路由次数
            - cache_stats: 缓存统计（含命中率百分比）
            - current_stage: 当前阶段
            - run_mode: 运行模式
        """
        cache_stats = self.cache.get_statistics()

        return {
            "total_routes": self._route_count,
            "cache_stats": {
                "size": cache_stats["size"],
                "hits": cache_stats["hits"],
                "misses": cache_stats["misses"],
                "hit_rate": "%s%%" % cache_stats["hit_rate"],  # 格式化为百分比
                "evictions": cache_stats["evictions"],
            },
            "current_stage": self.current_stage,
            "run_mode": self.run_mode,
            "rules_loaded": {
                "global": len(self.global_rules),
                "stage": len(self.stage_rules),
                "module": len(self.module_rules),
                "scenario": len(self.scenario_rules),
            },
        }

    def validate_config(self) -> bool:
        """验证配置完整性

        Returns:
            配置是否有效
        """
        # 检查必需的LogType是否都有全局规则
        required_log_types = [
            "SYSTEM",
            "PROGRESS",
            "NOTIFICATION",
            "ALERT",
            "USER_FEEDBACK",
            "DEBUG",
        ]
        missing_types = [lt for lt in required_log_types if lt not in self.global_rules]

        if missing_types:
            self.logger.error(f"全局规则缺少LogType: {missing_types}")
            return False

        self.logger.info("配置验证通过")
        return True


# 全局单例
_routing_engine: Optional[RoutingRuleEngine] = None


def get_routing_engine() -> RoutingRuleEngine:
    """获取全局路由引擎实例

    Returns:
        RoutingRuleEngine实例
    """
    global _routing_engine
    if _routing_engine is None:
        _routing_engine = RoutingRuleEngine()
    return _routing_engine
