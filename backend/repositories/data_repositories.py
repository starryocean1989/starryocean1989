# -*- coding: utf-8 -*-
"""
数据相关仓库.

整合品种、数据源、下载任务仓库。
"""

import logging
from typing import Any, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


# ==================== 品种仓库 ====================


class SymbolRepository:
    """品种仓库."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.SymbolRepository")
        self._symbols: Dict[str, Dict[str, Any]] = {}

    def create(self, symbol_data: Dict[str, Any]) -> bool:
        """创建品种."""
        try:
            symbol_id = f"{symbol_data['symbol']}.{symbol_data['exchange']}"
            self._symbols[symbol_id] = symbol_data
            return True
        except Exception as e:
            self.logger.error(f"创建品种失败: {e}")
            return False

    def get(self, symbol: str, exchange: str) -> Optional[Dict[str, Any]]:
        """获取品种."""
        symbol_id = f"{symbol}.{exchange}"
        return self._symbols.get(symbol_id)

    def list(self, exchange: Optional[str] = None, limit: int = 1000) -> List[Dict[str, Any]]:
        """获取品种列表."""
        symbols = list(self._symbols.values())
        if exchange:
            symbols = [s for s in symbols if s.get("exchange") == exchange]
        return symbols[:limit]

    def update(self, symbol: str, exchange: str, data: Dict[str, Any]) -> bool:
        """更新品种."""
        try:
            symbol_id = f"{symbol}.{exchange}"
            if symbol_id in self._symbols:
                self._symbols[symbol_id].update(data)
                return True
            return False
        except Exception as e:
            self.logger.error(f"更新品种失败: {e}")
            return False

    def delete(self, symbol: str, exchange: str) -> bool:
        """删除品种."""
        try:
            symbol_id = f"{symbol}.{exchange}"
            if symbol_id in self._symbols:
                del self._symbols[symbol_id]
                return True
            return False
        except Exception as e:
            self.logger.error(f"删除品种失败: {e}")
            return False


# ==================== 数据源仓库 ====================


class DataSourceRepository:
    """数据源仓库."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.DataSourceRepository")
        self._data_sources: Dict[str, Dict[str, Any]] = {}

    def create(self, source_data: Dict[str, Any]) -> bool:
        """创建数据源."""
        try:
            source_id = source_data["source_id"]
            self._data_sources[source_id] = source_data
            return True
        except Exception as e:
            self.logger.error(f"创建数据源失败: {e}")
            return False

    def get(self, source_id: str) -> Optional[Dict[str, Any]]:
        """获取数据源."""
        return self._data_sources.get(source_id)

    def list(self) -> List[Dict[str, Any]]:
        """获取所有数据源."""
        return list(self._data_sources.values())

    def update(self, source_id: str, data: Dict[str, Any]) -> bool:
        """更新数据源."""
        try:
            if source_id in self._data_sources:
                self._data_sources[source_id].update(data)
                return True
            return False
        except Exception as e:
            self.logger.error(f"更新数据源失败: {e}")
            return False

    def delete(self, source_id: str) -> bool:
        """删除数据源."""
        try:
            if source_id in self._data_sources:
                del self._data_sources[source_id]
                return True
            return False
        except Exception as e:
            self.logger.error(f"删除数据源失败: {e}")
            return False


# ==================== 下载任务仓库 ====================


class DownloadTaskRepository:
    """下载任务仓库."""

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.DownloadTaskRepository")
        self._tasks: Dict[str, Dict[str, Any]] = {}

    def create(self, task_data: Dict[str, Any]) -> bool:
        """创建任务."""
        try:
            task_id = task_data["task_id"]
            self._tasks[task_id] = task_data
            return True
        except Exception as e:
            self.logger.error(f"创建任务失败: {e}")
            return False

    def get(self, task_id: str) -> Optional[Dict[str, Any]]:
        """获取任务."""
        return self._tasks.get(task_id)

    def list(self, limit: int = 100) -> List[Dict[str, Any]]:
        """获取任务列表."""
        tasks = list(self._tasks.values())
        tasks.sort(key=lambda t: t.get("created_time", ""), reverse=True)
        return tasks[:limit]

    def update(self, task_id: str, data: Dict[str, Any]) -> bool:
        """更新任务."""
        try:
            if task_id in self._tasks:
                self._tasks[task_id].update(data)
                return True
            return False
        except Exception as e:
            self.logger.error(f"更新任务失败: {e}")
            return False

    def delete(self, task_id: str) -> bool:
        """删除任务."""
        try:
            if task_id in self._tasks:
                del self._tasks[task_id]
                return True
            return False
        except Exception as e:
            self.logger.error(f"删除任务失败: {e}")
            return False


__all__ = [
    "SymbolRepository",
    "DataSourceRepository",
    "DownloadTaskRepository",
]
