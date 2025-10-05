# -*- coding: utf-8 -*-

import pandas as pd
import json
import logging
from typing import Dict, Any, List, Union
from pathlib import Path

# flake8: noqa

logger = logging.getLogger(__name__)


class DataSaver:
    """数据保存器"""

    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def save_to_csv(
        self, data: Union[List[Dict[str, Any]], pd.DataFrame], file_path: str
    ) -> bool:
        """
        保存数据到CSV文件

        Args:
            data: 要保存的数据
            file_path: 文件路径

        Returns:
            保存是否成功
        """
        try:
            path = Path(file_path)
            path.parent.mkdir(parents=True, exist_ok=True)

            if isinstance(data, list):
                df = pd.DataFrame(data)
            else:
                df = data

            df.to_csv(path, index=False)
            self.logger.info(f"数据已保存到 {file_path}")
            return True

        except Exception as e:
            self.logger.error(f"保存CSV文件失败: {e}")
            return False


def save_to_json(self, data: Any, file_path: str) -> bool:
    """
    保存数据到JSON文件

    Args:
        data: 要保存的数据
        file_path: 文件路径

    Returns:
        保存是否成功
    """
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        self.logger.info(f"数据已保存到 {file_path}")
        return True

    except Exception as e:
        self.logger.error(f"保存JSON文件失败: {e}")
        return False


def save_to_excel(
    self,
    data: Union[List[Dict[str, Any]], pd.DataFrame],
    file_path: str,
    sheet_name: str = "Sheet1",
) -> bool:
    """
    保存数据到Excel文件

    Args:
        data: 要保存的数据
        file_path: 文件路径
        sheet_name: 工作表名称

    Returns:
        保存是否成功
    """
    try:
        path = Path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        if isinstance(data, list):
            df = pd.DataFrame(data)
        else:
            df = data

        df.to_excel(path, sheet_name=sheet_name, index=False)
        self.logger.info(f"数据已保存到 {file_path}")
        return True

    except Exception as e:
        self.logger.error(f"保存Excel文件失败: {e}")
        return False
