# -*- coding: utf-8 -*-
"""列表传感器模块 - 用于处理CSV文件的列表数据操作"""

import logging
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

# flake8: noqa

logger = logging.getLogger(__name__)


class ListSensor:
    """列表传感器"""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def load_list_from_csv(self, file_path: str) -> List[Dict[str, Any]]:
        """
        从CSV文件加载列表数据

        Args:
            file_path: CSV文件路径

        Returns:
            数据列表
        """
        try:
            path = Path(file_path)
            if not path.exists():
                self.logger.error("文件不存在: %s", file_path)
                return []

            df = pd.read_csv(path)
            data = df.to_dict("records")

            self.logger.info("从 %s 加载了 %d 条数据", file_path, len(data))
            return data  # type: ignore

        except (FileNotFoundError, pd.errors.EmptyDataError, pd.errors.ParserError, ValueError) as e:
            self.logger.error("加载CSV文件失败: %s", e)
            return []

    def save_list_to_csv(self, data: List[Dict[str, Any]], file_path: str) -> bool:
        """
        将列表数据保存到CSV文件

        Args:
            data: 要保存的数据
            file_path: CSV文件路径

        Returns:
            保存是否成功
        """
        try:
            df = pd.DataFrame(data)
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            df.to_csv(path, index=False)
            self.logger.info("保存了 %d 条数据到 %s", len(data), file_path)
            return True

        except (OSError, PermissionError, ValueError) as e:
            self.logger.error("保存CSV文件失败: %s", e)
            return False

    def filter_list(
        self, data: List[Dict[str, Any]], filters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        过滤列表数据

        Args:
            data: 原始数据
            filters: 过滤条件

        Returns:
            过滤后的数据
        """
        try:
            filtered_data = data

            for key, value in filters.items():
                filtered_data = [
                    item for item in filtered_data if item.get(key) == value
                ]

            self.logger.info("过滤后剩余 %d 条数据", len(filtered_data))
            return filtered_data

        except (KeyError, TypeError, AttributeError) as e:
            self.logger.error("过滤数据失败: %s", e)
            return data
