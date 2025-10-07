# -*- coding: utf-8 -*-
"""
日志管理服务.

提供日志收集、查询、分析功能。
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class LogService:
    """日志管理服务."""

    def __init__(self):
        """初始化日志服务."""
        self.logs: List[Dict[str, Any]] = []
        self.max_logs = 10000  # 最大缓存日志数
        logger.info("日志管理服务初始化完成")

    def query_logs(
        self,
        level: Optional[str] = None,
        module: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """查询日志."""
        try:
            # TODO: 从数据库查询日志
            # 暂时从内存返回
            filtered_logs = self.logs

            if level:
                filtered_logs = [
                    log for log in filtered_logs if log.get("level") == level
                ]

            if module:
                filtered_logs = [
                    log for log in filtered_logs if log.get("module") == module
                ]

            # 返回最新的N条
            return filtered_logs[-limit:]

        except Exception as e:
            logger.error("查询日志失败: %s", e)
            raise

    def search_logs(
        self,
        keyword: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """搜索日志."""
        try:
            # TODO: 使用正则表达式或全文搜索
            results = []

            for log in self.logs:
                if keyword.lower() in log.get("message", "").lower():
                    # 检查时间范围
                    if start_time and log.get("timestamp"):
                        log_time = datetime.fromisoformat(log["timestamp"])
                        if log_time < start_time:
                            continue

                    if end_time and log.get("timestamp"):
                        log_time = datetime.fromisoformat(log["timestamp"])
                        if log_time > end_time:
                            continue

                    results.append(log)

            logger.info("日志搜索完成: keyword=%s, results=%d", keyword, len(results))
            return results

        except Exception as e:
            logger.error("搜索日志失败: %s", e)
            raise

    def analyze_logs(self) -> Dict[str, Any]:
        """分析日志统计."""
        try:
            # 统计各级别日志数量
            level_count = {}
            module_count = {}

            for log in self.logs:
                level = log.get("level", "UNKNOWN")
                module = log.get("module", "UNKNOWN")

                level_count[level] = level_count.get(level, 0) + 1
                module_count[module] = module_count.get(module, 0) + 1

            analysis = {
                "total_logs": len(self.logs),
                "level_distribution": level_count,
                "module_distribution": module_count,
                "error_count": level_count.get("ERROR", 0),
                "warning_count": level_count.get("WARNING", 0),
                "info_count": level_count.get("INFO", 0),
            }

            logger.info("日志分析完成: total=%d", len(self.logs))
            return analysis

        except Exception as e:
            logger.error("分析日志失败: %s", e)
            raise

    def add_log(self, log_entry: Dict[str, Any]) -> None:
        """添加日志条目."""
        self.logs.append(log_entry)

        # 限制缓存大小
        if len(self.logs) > self.max_logs:
            self.logs = self.logs[-self.max_logs // 2 :]


__all__ = ["LogService"]
