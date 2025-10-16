# -*- coding: utf-8 -*-
"""
诊断工具模块.

提供日志分析、性能瓶颈识别、系统优化建议等诊断功能.
"""

import logging
import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class LogAnalyzer:
    """日志分析器 - 智能分析错误模式."""

    def __init__(self):
        """初始化日志分析器."""
        self.logger = logging.getLogger(__name__)

        # 常见错误模式
        self.error_patterns = {
            "module_not_found": r"ModuleNotFoundError|ImportError",
            "connection_error": r"ConnectionError|ConnectionTimeout|ConnectionRefusedError",
            "timeout": r"TimeoutError|timeout",
            "permission": r"PermissionError|AccessDenied",
            "file_not_found": r"FileNotFoundError",
            "type_error": r"TypeError",
            "value_error": r"ValueError",
            "key_error": r"KeyError",
            "attribute_error": r"AttributeError",
            "memory_error": r"MemoryError|Out of memory",
        }

    def analyze_error_logs(self, log_file: str, hours: int = 24) -> Dict[str, Any]:
        """分析错误日志.

        Args:
            log_file: 日志文件路径
            hours: 分析最近多少小时的日志

        Returns:
            Dict: 分析结果
        """
        try:
            log_path = Path(log_file)
            if not log_path.exists():
                return {
                    "success": False,
                    "message": f"日志文件不存在: {log_file}",
                }

            # 读取日志
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                logs = f.readlines()

            # 时间过滤
            cutoff_time = datetime.now() - timedelta(hours=hours)
            filtered_logs = self._filter_by_time(logs, cutoff_time)

            # 识别错误模式
            error_patterns = self.identify_error_patterns(filtered_logs)

            # 统计错误频率
            error_counts = Counter([e["type"] for e in error_patterns])

            # 提取TOP错误
            top_errors = error_counts.most_common(10)

            return {
                "success": True,
                "total_errors": len(error_patterns),
                "error_types": len(error_counts),
                "top_errors": [
                    {"type": error_type, "count": count} for error_type, count in top_errors
                ],
                "error_patterns": error_patterns[:50],  # 最多返回50条
                "analysis_time": datetime.now().isoformat(),
            }

        except Exception as e:
            self.logger.error("分析日志失败: %s", e)
            return {
                "success": False,
                "message": f"分析失败: {str(e)}",
            }

    def identify_error_patterns(self, logs: List[str]) -> List[Dict[str, Any]]:
        """识别错误模式.

        Args:
            logs: 日志行列表

        Returns:
            List: 错误模式列表
        """
        errors = []

        for i, line in enumerate(logs):
            # 检查是否包含ERROR或CRITICAL
            if "ERROR" not in line and "CRITICAL" not in line:
                continue

            # 匹配错误类型
            error_type = "unknown"
            for pattern_name, pattern in self.error_patterns.items():
                if re.search(pattern, line, re.IGNORECASE):
                    error_type = pattern_name
                    break

            # 提取时间戳
            timestamp = self._extract_timestamp(line)

            # 提取错误消息
            error_msg = line.strip()

            errors.append(
                {
                    "type": error_type,
                    "message": error_msg[:200],  # 限制长度
                    "timestamp": timestamp,
                    "line_number": i + 1,
                }
            )

        return errors

    def _filter_by_time(self, logs: List[str], cutoff_time: datetime) -> List[str]:
        """按时间过滤日志.

        Args:
            logs: 日志行列表
            cutoff_time: 截止时间

        Returns:
            List: 过滤后的日志
        """
        filtered = []
        for line in logs:
            timestamp = self._extract_timestamp(line)
            if timestamp:
                try:
                    log_time = datetime.fromisoformat(timestamp)
                    if log_time >= cutoff_time:
                        filtered.append(line)
                except (ValueError, TypeError):
                    # 无法解析时间，保留该行
                    filtered.append(line)
            else:
                # 没有时间戳，保留该行
                filtered.append(line)

        return filtered

    def _extract_timestamp(self, line: str) -> Optional[str]:
        """提取日志时间戳.

        Args:
            line: 日志行

        Returns:
            Optional[str]: 时间戳字符串
        """
        # 尝试匹配常见时间戳格式
        patterns = [
            r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}",  # 2025-01-01 12:00:00
            r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}",  # 2025-01-01T12:00:00
        ]

        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                return match.group(0).replace(" ", "T")

        return None


class PerformanceAnalyzer:
    """性能分析器 - 识别瓶颈."""

    def __init__(self):
        """初始化性能分析器."""
        self.logger = logging.getLogger(__name__)

    def analyze_bottlenecks(self) -> List[Dict[str, Any]]:
        """分析性能瓶颈.

        Returns:
            List: 瓶颈列表
        """
        try:
            import psutil

            bottlenecks = []

            # CPU瓶颈检查
            cpu_percent: float = psutil.cpu_percent(interval=1, percpu=False)  # type: ignore[assignment]
            if cpu_percent > 80:
                bottlenecks.append(
                    {
                        "type": "cpu",
                        "severity": "high" if cpu_percent > 90 else "medium",
                        "current_value": cpu_percent,
                        "threshold": 80,
                        "description": f"CPU使用率过高: {cpu_percent:.1f}%",
                        "impact": "系统响应变慢，策略计算延迟增加",
                    }
                )

            # 内存瓶颈检查
            memory = psutil.virtual_memory()
            if memory.percent > 80:
                bottlenecks.append(
                    {
                        "type": "memory",
                        "severity": "high" if memory.percent > 90 else "medium",
                        "current_value": memory.percent,
                        "threshold": 80,
                        "description": f"内存使用率过高: {memory.percent:.1f}%",
                        "impact": "可能导致OOM错误，系统崩溃风险增加",
                    }
                )

            # 磁盘瓶颈检查
            disk = psutil.disk_usage("/")
            if disk.percent > 85:
                bottlenecks.append(
                    {
                        "type": "disk",
                        "severity": "high" if disk.percent > 95 else "medium",
                        "current_value": disk.percent,
                        "threshold": 85,
                        "description": f"磁盘使用率过高: {disk.percent:.1f}%",
                        "impact": "数据写入失败，日志丢失风险",
                    }
                )

            # 磁盘I/O瓶颈检查
            disk_io = psutil.disk_io_counters()
            if disk_io:
                # 检查I/O等待时间（如果可用）
                io_time_ms = getattr(disk_io, "busy_time", 0) / 1000  # 转换为秒
                if io_time_ms > 0:
                    bottlenecks.append(
                        {
                            "type": "disk_io",
                            "severity": "medium",
                            "current_value": io_time_ms,
                            "threshold": 0,
                            "description": "磁盘I/O繁忙",
                            "impact": "数据读写速度下降",
                        }
                    )

            # 网络瓶颈检查（简化版）
            net_io = psutil.net_io_counters()
            if net_io and hasattr(net_io, "errin") and hasattr(net_io, "errout"):
                # 检查错误包
                error_count: int = net_io.errin + net_io.errout  # type: ignore[attr-defined]

                if error_count > 100:
                    bottlenecks.append(
                        {
                            "type": "network",
                            "severity": "medium",
                            "current_value": error_count,
                            "threshold": 100,
                            "description": f"网络错误包数量: {error_count}",
                            "impact": "网络连接不稳定",
                        }
                    )

            return bottlenecks

        except Exception as e:
            self.logger.error("分析性能瓶颈失败: %s", e)
            return []

    def generate_optimization_suggestions(
        self, bottlenecks: Optional[List[Dict[str, Any]]] = None
    ) -> List[str]:
        """生成优化建议.

        Args:
            bottlenecks: 瓶颈列表（可选）

        Returns:
            List: 优化建议列表
        """
        if bottlenecks is None:
            bottlenecks = self.analyze_bottlenecks()

        suggestions = []

        # 根据瓶颈类型生成建议
        bottleneck_types = {b["type"] for b in bottlenecks}

        if "cpu" in bottleneck_types:
            suggestions.extend(
                [
                    "1. 启用策略结果缓存，减少重复计算",
                    "2. 优化策略算法，降低计算复杂度",
                    "3. 考虑使用多进程并行处理",
                    "4. 检查是否有死循环或无限递归",
                ]
            )

        if "memory" in bottleneck_types:
            suggestions.extend(
                [
                    "1. 启用数据分页加载，避免一次性加载大量数据",
                    "2. 及时释放不再使用的对象",
                    "3. 使用生成器代替列表减少内存占用",
                    "4. 检查是否存在内存泄漏",
                ]
            )

        if "disk" in bottleneck_types:
            suggestions.extend(
                [
                    "1. 清理临时文件和日志文件",
                    "2. 启用日志轮转和自动清理",
                    "3. 将大文件迁移到其他磁盘",
                    "4. 考虑扩展磁盘容量",
                ]
            )

        if "disk_io" in bottleneck_types:
            suggestions.extend(
                [
                    "1. 启用SSD固态硬盘提升I/O性能",
                    "2. 使用异步I/O操作",
                    "3. 批量读写减少I/O次数",
                    "4. 启用数据库连接池",
                ]
            )

        if "network" in bottleneck_types:
            suggestions.extend(
                [
                    "1. 检查网络连接质量",
                    "2. 启用数据压缩减少传输量",
                    "3. 增加请求重试次数",
                    "4. 考虑使用CDN加速",
                ]
            )

        # 通用优化建议
        if not suggestions:
            suggestions = [
                "系统运行正常，暂无优化建议",
                "建议定期监控系统性能指标",
                "保持系统和依赖库的更新",
            ]

        return suggestions


class AutoFixer:
    """自动修复建议生成器."""

    def __init__(self):
        """初始化自动修复器."""
        self.logger = logging.getLogger(__name__)

    def suggest_fixes(self, issue_type: str) -> List[Dict[str, Any]]:
        """生成修复建议.

        Args:
            issue_type: 问题类型

        Returns:
            List: 修复建议列表
        """
        fixes = []

        if issue_type == "module_not_found":
            fixes.append(
                {
                    "title": "安装缺失的模块",
                    "command": "pip install <module_name>",
                    "description": "使用pip安装缺失的Python模块",
                    "auto_fixable": False,
                    "risk_level": "low",
                }
            )

        elif issue_type == "connection_error":
            fixes.extend(
                [
                    {
                        "title": "检查网络连接",
                        "command": "ping <target_host>",
                        "description": "检查目标主机是否可达",
                        "auto_fixable": False,
                        "risk_level": "low",
                    },
                    {
                        "title": "增加连接超时时间",
                        "command": None,
                        "description": "在配置中增加timeout参数",
                        "auto_fixable": True,
                        "risk_level": "low",
                    },
                    {
                        "title": "启用连接重试",
                        "command": None,
                        "description": "启用自动重试机制",
                        "auto_fixable": True,
                        "risk_level": "low",
                    },
                ]
            )

        elif issue_type == "permission":
            fixes.append(
                {
                    "title": "修改文件权限",
                    "command": "chmod 755 <file_path>",
                    "description": "给予文件适当的读写权限",
                    "auto_fixable": False,
                    "risk_level": "medium",
                }
            )

        elif issue_type == "file_not_found":
            fixes.extend(
                [
                    {
                        "title": "检查文件路径",
                        "command": None,
                        "description": "确认文件路径是否正确",
                        "auto_fixable": False,
                        "risk_level": "low",
                    },
                    {
                        "title": "创建缺失的目录",
                        "command": "mkdir -p <dir_path>",
                        "description": "创建必要的目录结构",
                        "auto_fixable": True,
                        "risk_level": "low",
                    },
                ]
            )

        elif issue_type == "memory_error":
            fixes.extend(
                [
                    {
                        "title": "增加系统内存",
                        "command": None,
                        "description": "扩展物理内存或虚拟内存",
                        "auto_fixable": False,
                        "risk_level": "low",
                    },
                    {
                        "title": "启用内存优化",
                        "command": None,
                        "description": "启用数据分页和惰性加载",
                        "auto_fixable": True,
                        "risk_level": "low",
                    },
                    {
                        "title": "清理内存缓存",
                        "command": None,
                        "description": "手动触发垃圾回收",
                        "auto_fixable": True,
                        "risk_level": "low",
                    },
                ]
            )

        else:
            fixes.append(
                {
                    "title": "查看详细日志",
                    "command": None,
                    "description": "检查日志文件获取更多信息",
                    "auto_fixable": False,
                    "risk_level": "low",
                }
            )

        return fixes


# 导出类
__all__ = [
    "LogAnalyzer",
    "PerformanceAnalyzer",
    "AutoFixer",
]
