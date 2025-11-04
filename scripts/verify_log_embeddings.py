# -*- coding: utf-8 -*-
"""
验证日志埋点脚本

检查所有日志输出是否正确配置：
1. 日志类型标记（log_type）是否正确
2. 场景标记（scenario）是否正确
3. 日志级别是否合理
4. 是否符合路由规则配置
"""

import re
import os
from pathlib import Path
from typing import Dict, List, Tuple, Set

# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent

# 需要检查的文件列表
FILES_TO_CHECK = [
    "backend/startup/stages/env_setup.py",
    "backend/startup/stages/logging_init.py",
    "backend/startup/stages/qt_framework.py",
    "backend/startup/stages/backend_init.py",
    "backend/startup/stages/ui_activation.py",
    "ui/modules/data_center_view.py",
    "ui/modules/system_manager_view.py",
    "backend/services/data_center_service.py",
    "backend/services/system_manager_service.py",
    "backend/infrastructure/data_module_vnpy/data_acquisition.py",
    "backend/infrastructure/data_module_vnpy/data_quality.py",
]

# 有效的日志类型
VALID_LOG_TYPES = {
    "SYSTEM", "PROGRESS", "NOTIFICATION", "ALERT", 
    "USER_FEEDBACK", "DEBUG", "STAGE_NODE"
}

# 有效的场景标记
VALID_SCENARIOS = {
    "application_startup",
    "manual_speedtest",
    "tdx_data_read",
    "refresh_symbol_list",
    "data_download",
    "manual_data_scan",
}

# 有效的日志级别
VALID_LEVELS = {
    "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"
}

# 日志级别映射
LEVEL_MAPPING = {
    "logger.debug": "DEBUG",
    "logger.info": "INFO",
    "logger.warning": "WARNING",
    "logger.error": "ERROR",
    "logger.critical": "CRITICAL",
}


class LogEmbeddingValidator:
    """日志埋点验证器"""
    
    def __init__(self):
        self.issues: List[Dict] = []
        self.stats: Dict = {
            "total_files": 0,
            "total_logs": 0,
            "by_log_type": {},
            "by_scenario": {},
            "by_level": {},
        }
    
    def validate_file(self, file_path: Path) -> Dict:
        """验证单个文件的日志埋点"""
        if not file_path.exists():
            return {"error": f"文件不存在: {file_path}"}
        
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception as e:
            return {"error": f"读取文件失败: {e}"}
        
        issues = []
        log_count = 0
        
        # 匹配所有日志调用
        # 匹配 logger.debug/info/warning/error/critical(..., extra={...})
        log_pattern = re.compile(
            r'logger\.(debug|info|warning|error|critical)\s*\([^)]*extra\s*=\s*\{[^}]*\}',
            re.MULTILINE | re.DOTALL
        )
        
        matches = log_pattern.finditer(content)
        
        for match in matches:
            log_count += 1
            log_line = match.group(0)
            log_method = match.group(1)
            level = LEVEL_MAPPING.get(f"logger.{log_method}", log_method.upper())
            
            # 提取 extra 参数
            extra_match = re.search(r'extra\s*=\s*\{([^}]+)\}', log_line, re.DOTALL)
            if not extra_match:
                issues.append({
                    "type": "missing_extra",
                    "line": content[:match.start()].count('\n') + 1,
                    "message": f"日志调用缺少extra参数: {log_method}",
                    "code": log_line[:100],
                })
                continue
            
            extra_content = extra_match.group(1)
            
            # 提取 log_type
            log_type_match = re.search(r'"log_type"\s*:\s*"([^"]+)"', extra_content)
            log_type = log_type_match.group(1) if log_type_match else None
            
            # 提取 scenario
            scenario_match = re.search(r'"scenario"\s*:\s*"([^"]+)"', extra_content)
            scenario = scenario_match.group(1) if scenario_match else None
            
            # 验证 log_type
            if log_type:
                if log_type not in VALID_LOG_TYPES:
                    issues.append({
                        "type": "invalid_log_type",
                        "line": content[:match.start()].count('\n') + 1,
                        "message": f"无效的log_type: {log_type}",
                        "code": log_line[:100],
                        "expected": list(VALID_LOG_TYPES),
                    })
                else:
                    # 统计
                    self.stats["by_log_type"][log_type] = \
                        self.stats["by_log_type"].get(log_type, 0) + 1
            else:
                issues.append({
                    "type": "missing_log_type",
                    "line": content[:match.start()].count('\n') + 1,
                    "message": f"日志调用缺少log_type标记: {log_method}",
                    "code": log_line[:100],
                })
            
            # 验证 scenario
            if scenario:
                if scenario not in VALID_SCENARIOS:
                    issues.append({
                        "type": "invalid_scenario",
                        "line": content[:match.start()].count('\n') + 1,
                        "message": f"无效的scenario: {scenario}",
                        "code": log_line[:100],
                        "expected": list(VALID_SCENARIOS),
                    })
                else:
                    # 统计
                    self.stats["by_scenario"][scenario] = \
                        self.stats["by_scenario"].get(scenario, 0) + 1
            else:
                # scenario 在某些情况下是可选的（如启动阶段的全局日志）
                # 但业务场景的日志应该都有 scenario
                if "application_startup" not in content[:match.start()]:
                    issues.append({
                        "type": "missing_scenario",
                        "line": content[:match.start()].count('\n') + 1,
                        "message": f"业务场景日志缺少scenario标记: {log_method}",
                        "code": log_line[:100],
                        "severity": "warning",  # 警告级别，不是错误
                    })
            
            # 统计日志级别
            self.stats["by_level"][level] = self.stats["by_level"].get(level, 0) + 1
            
            # 验证日志级别和类型的匹配
            if log_type == "STAGE_NODE":
                # STAGE_NODE 通常使用 INFO 级别
                if level not in ["INFO", "WARNING", "ERROR"]:
                    issues.append({
                        "type": "inappropriate_level",
                        "line": content[:match.start()].count('\n') + 1,
                        "message": f"STAGE_NODE类型通常使用INFO/WARNING/ERROR级别，当前使用{level}",
                        "code": log_line[:100],
                        "severity": "warning",
                    })
            
            if log_type == "PROGRESS":
                # PROGRESS 通常使用 DEBUG 或 INFO 级别
                if level not in ["DEBUG", "INFO"]:
                    issues.append({
                        "type": "inappropriate_level",
                        "line": content[:match.start()].count('\n') + 1,
                        "message": f"PROGRESS类型通常使用DEBUG/INFO级别，当前使用{level}",
                        "code": log_line[:100],
                        "severity": "warning",
                    })
            
            if log_type == "SYSTEM" and level == "DEBUG":
                # SYSTEM DEBUG 应该只输出到文件和AI日志，不输出到Terminal
                # 这是正确的，但需要确保场景标记正确
                pass
        
        return {
            "file": str(file_path.relative_to(PROJECT_ROOT)),
            "log_count": log_count,
            "issues": issues,
        }
    
    def validate_all(self) -> Dict:
        """验证所有文件"""
        results = []
        
        for file_path_str in FILES_TO_CHECK:
            file_path = PROJECT_ROOT / file_path_str
            self.stats["total_files"] += 1
            
            result = self.validate_file(file_path)
            if "error" in result:
                print(f"❌ {result['error']}")
                continue
            
            results.append(result)
            self.stats["total_logs"] += result["log_count"]
            
            if result["issues"]:
                self.issues.extend([
                    {**issue, "file": result["file"]}
                    for issue in result["issues"]
                ])
        
        return {
            "results": results,
            "issues": self.issues,
            "stats": self.stats,
        }
    
    def print_report(self, validation_result: Dict):
        """打印验证报告"""
        print("=" * 80)
        print("日志埋点验证报告")
        print("=" * 80)
        print()
        
        # 统计信息
        stats = validation_result["stats"]
        print("📊 统计信息:")
        print(f"  - 检查文件数: {stats['total_files']}")
        print(f"  - 日志总数: {stats['total_logs']}")
        print()
        
        print("📈 按日志类型分布:")
        for log_type, count in sorted(stats["by_log_type"].items()):
            print(f"  - {log_type}: {count}")
        print()
        
        print("📈 按场景分布:")
        for scenario, count in sorted(stats["by_scenario"].items()):
            print(f"  - {scenario}: {count}")
        print()
        
        print("📈 按级别分布:")
        for level, count in sorted(stats["by_level"].items()):
            print(f"  - {level}: {count}")
        print()
        
        # 问题报告
        issues = validation_result["issues"]
        if not issues:
            print("✅ 未发现问题！所有日志埋点配置正确。")
            return
        
        print("=" * 80)
        print("⚠️ 发现问题:")
        print("=" * 80)
        
        # 按问题类型分组
        issues_by_type: Dict[str, List] = {}
        for issue in issues:
            issue_type = issue["type"]
            if issue_type not in issues_by_type:
                issues_by_type[issue_type] = []
            issues_by_type[issue_type].append(issue)
        
        # 按严重程度排序
        severity_order = {
            "error": 0,
            "warning": 1,
        }
        
        for issue_type, type_issues in sorted(issues_by_type.items()):
            print()
            print(f"🔍 {issue_type} ({len(type_issues)}个):")
            for issue in type_issues[:10]:  # 只显示前10个
                print(f"  - {issue['file']}:{issue['line']}")
                print(f"    {issue['message']}")
                if "expected" in issue:
                    print(f"    期望值: {', '.join(issue['expected'])}")
                if "code" in issue:
                    print(f"    代码: {issue['code'][:80]}...")
            if len(type_issues) > 10:
                print(f"  ... 还有 {len(type_issues) - 10} 个类似问题")
        
        # 总结
        error_count = sum(1 for i in issues if i.get("severity") != "warning")
        warning_count = sum(1 for i in issues if i.get("severity") == "warning")
        
        print()
        print("=" * 80)
        print(f"📋 总结: {error_count}个错误, {warning_count}个警告, 共{len(issues)}个问题")
        print("=" * 80)


def main():
    """主函数"""
    validator = LogEmbeddingValidator()
    result = validator.validate_all()
    validator.print_report(result)
    
    # 返回退出码
    error_count = sum(1 for i in result["issues"] if i.get("severity") != "warning")
    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    exit(main())

