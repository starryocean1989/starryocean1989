# -*- coding: utf-8 -*-
"""
日志Repository.

提供日志的数据库操作。
"""

import logging
from datetime import datetime
from typing import List, Optional

from backend.repositories.base_repository import InMemoryRepository

logger = logging.getLogger(__name__)


class LogRepository(InMemoryRepository[dict]):
    """日志Repository."""

    def __init__(self):
        """初始化."""
        super().__init__(table_name="logs")
        self._log_counter = 0
        logger.info("日志Repository初始化完成")

    async def save_log(self, log_data: dict) -> bool:
        """保存日志."""
        try:
            # 为日志分配唯一ID
            self._log_counter += 1
            log_id = str(self._log_counter)

            # 添加必要的元数据
            log_entry = {
                "id": log_id,
                "timestamp": log_data.get("timestamp", datetime.now().isoformat()),
                "level": log_data.get("level", "INFO"),
                "module": log_data.get("module", ""),
                "message": log_data.get("message", ""),
                **log_data,
            }

            # 保存到内存存储
            self._data[log_id] = log_entry

            logger.debug("保存日志成功: %s", log_id)
            return True

        except Exception as e:
            logger.error("保存日志失败: %s", e)
            return False

    async def query_logs(
        self,
        level: Optional[str] = None,
        module: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[dict]:
        """查询日志."""
        try:
            results = []

            for log_entry in self._data.values():
                # 过滤条件
                if level and log_entry.get("level") != level:
                    continue

                if module and log_entry.get("module") != module:
                    continue

                # 时间过滤
                if start_time or end_time:
                    timestamp_str = log_entry.get("timestamp")
                    if timestamp_str:
                        try:
                            log_time = datetime.fromisoformat(timestamp_str)
                            if start_time and log_time < start_time:
                                continue
                            if end_time and log_time > end_time:
                                continue
                        except (ValueError, TypeError):
                            continue

                results.append(log_entry)

            # 按时间倒序排序（最新的在前）
            results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

            logger.debug(
                "查询日志完成 - level: %s, module: %s, "
                "start_time: %s, end_time: %s, 结果数: %d",
                level,
                module,
                start_time,
                end_time,
                len(results),
            )

            return results[:limit]

        except Exception as e:
            logger.error("查询日志失败: %s", e)
            return []

    async def search_logs(
        self,
        keyword: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> List[dict]:
        """搜索日志."""
        try:
            results = []
            keyword_lower = keyword.lower()

            for log_entry in self._data.values():
                # 时间过滤
                if start_time or end_time:
                    timestamp_str = log_entry.get("timestamp")
                    if timestamp_str:
                        try:
                            log_time = datetime.fromisoformat(timestamp_str)
                            if start_time and log_time < start_time:
                                continue
                            if end_time and log_time > end_time:
                                continue
                        except (ValueError, TypeError):
                            continue

                # 关键字搜索（在message、module、level中搜索）
                message = str(log_entry.get("message", "")).lower()
                module = str(log_entry.get("module", "")).lower()
                level = str(log_entry.get("level", "")).lower()

                if (
                    keyword_lower in message
                    or keyword_lower in module
                    or keyword_lower in level
                ):
                    results.append(log_entry)

            # 按时间倒序排序
            results.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

            logger.debug(
                "搜索日志完成 - keyword: %s, start_time: %s, "
                "end_time: %s, 结果数: %d",
                keyword,
                start_time,
                end_time,
                len(results),
            )

            return results

        except Exception as e:
            logger.error("搜索日志失败: %s", e)
            return []


__all__ = ["LogRepository"]
