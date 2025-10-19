# -*- coding: utf-8 -*-
"""
健康检查模块

提供系统健康检查功能，从core.py迁移
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict

from ..config import config_manager


logger = logging.getLogger(__name__)


class HealthChecker:
    """系统健康检查器"""

    @staticmethod
    def check_system_health() -> Dict[str, Any]:
        """
        健康检查：验证关键目录与最小数据可用性（从core.py迁移）

        Returns:
            {"ready": bool, "message": str, "details": {...}}
        """
        details: Dict[str, Any] = {}
        ready = True
        message = "OK"

        try:
            cache_dir = config_manager.get_cache_dir()
            data_dir = config_manager.get_data_dir()
            details["cache_dir"] = str(cache_dir)
            details["data_dir"] = str(data_dir)

            # 目录存在性与可写性
            cache_dir.mkdir(parents=True, exist_ok=True)
            data_dir.mkdir(parents=True, exist_ok=True)
            details["cache_dir_exists"] = cache_dir.exists()
            details["data_dir_exists"] = data_dir.exists()

            # 尝试写入/读取探针文件（权限检测）
            probe = cache_dir / ".probe"
            try:
                probe.write_text("ok", encoding="utf-8")
                details["cache_dir_writable"] = True
                with probe.open("r", encoding="utf-8") as f:
                    _ = f.read()
                probe.unlink(missing_ok=True)
            except Exception:
                details["cache_dir_writable"] = False
                ready = False
                message = "cache_dir 不可写"

            # 最小数据可用性（非强制）
            parquet_count = 0
            try:
                for root, _, files in os.walk(data_dir):
                    for fn in files:
                        if fn.lower().endswith(".parquet"):
                            parquet_count += 1
                            if parquet_count >= 1:
                                break
                    if parquet_count >= 1:
                        break
            except Exception:
                pass
            details["parquet_files"] = parquet_count

            if parquet_count == 0 and ready:
                message = "未检测到最小数据集（可后续通过增量下载或导入TDX生成）"

        except Exception as e:
            ready = False
            message = f"健康检查异常: {e}"
            logger.error("健康检查异常: %s", e, exc_info=True)

        return {"ready": bool(ready), "message": message, "details": details}
