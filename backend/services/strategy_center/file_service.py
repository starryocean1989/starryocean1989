# -*- coding: utf-8 -*-
"""
策略文件服务.

提供策略文件管理、树状图生成、文件操作等功能。
"""

import logging
import os
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class FileService:
    """策略文件服务."""

    def __init__(self, strategies_root: str = "strategies"):
        """初始化文件服务."""
        self.strategies_root = Path(strategies_root)
        self._ensure_default_folders()
        logger.info("策略文件服务初始化完成: root=%s", self.strategies_root)

    def _ensure_default_folders(self):
        """确保默认文件夹存在."""
        default_folders = [
            "cta_strategies",
            "algo_strategies",
            "option_strategies",
            "portfolio_strategies",
            "script_strategies",
            "spread_strategies",
        ]

        for folder in default_folders:
            folder_path = self.strategies_root / folder
            folder_path.mkdir(parents=True, exist_ok=True)

        logger.info("默认文件夹已创建")

    def get_file_tree(self, folder_path: Optional[str] = None) -> Dict[str, Any]:
        """获取文件树."""
        try:
            if folder_path:
                target_path = self.strategies_root / folder_path
            else:
                target_path = self.strategies_root

            if not target_path.exists():
                raise ValueError(f"路径不存在: {target_path}")

            return self._build_tree(target_path, target_path)

        except Exception as e:
            logger.error("获取文件树失败: %s", e)
            raise

    def _build_tree(self, path: Path, root: Path) -> Dict[str, Any]:
        """递归构建文件树."""
        relative_path = path.relative_to(root.parent)

        if path.is_file():
            return {
                "name": path.name,
                "type": "file",
                "path": str(relative_path).replace("\\", "/"),
                "size": path.stat().st_size,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
            }
        else:
            children = []
            for item in sorted(path.iterdir()):
                if not item.name.startswith("."):
                    children.append(self._build_tree(item, root))

            return {
                "name": path.name,
                "type": "folder",
                "path": str(relative_path).replace("\\", "/"),
                "children": children,
            }

    def create_file(
        self, file_name: str, folder_path: str, content: str = ""
    ) -> Dict[str, Any]:
        """创建文件."""
        try:
            target_path = self.strategies_root / folder_path / file_name

            if target_path.exists():
                raise ValueError(f"文件已存在: {file_name}")

            # 确保父目录存在
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # 写入文件
            target_path.write_text(content, encoding="utf-8")

            logger.info("文件创建成功: %s", target_path)

            return {
                "file_id": str(target_path.relative_to(self.strategies_root)),
                "file_name": file_name,
                "folder_path": folder_path,
                "created_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("创建文件失败: %s", e)
            raise

    def get_file_content(self, file_id: str) -> Dict[str, Any]:
        """获取文件内容."""
        try:
            file_path = self.strategies_root / file_id

            if not file_path.exists():
                raise ValueError(f"文件不存在: {file_id}")

            content = file_path.read_text(encoding="utf-8")

            return {
                "file_id": file_id,
                "file_name": file_path.name,
                "content": content,
                "modified_at": datetime.fromtimestamp(
                    file_path.stat().st_mtime
                ).isoformat(),
            }

        except Exception as e:
            logger.error("获取文件内容失败: %s", e)
            raise

    def update_file_content(self, file_id: str, content: str) -> bool:
        """更新文件内容."""
        try:
            file_path = self.strategies_root / file_id

            if not file_path.exists():
                raise ValueError(f"文件不存在: {file_id}")

            file_path.write_text(content, encoding="utf-8")

            logger.info("文件更新成功: %s", file_id)
            return True

        except Exception as e:
            logger.error("更新文件失败: %s", e)
            raise

    def delete_file(self, file_id: str) -> bool:
        """删除文件."""
        try:
            file_path = self.strategies_root / file_id

            if not file_path.exists():
                raise ValueError(f"文件不存在: {file_id}")

            file_path.unlink()

            logger.info("文件删除成功: %s", file_id)
            return True

        except Exception as e:
            logger.error("删除文件失败: %s", e)
            raise

    def create_folder(self, folder_name: str, parent_path: str = "") -> Dict[str, Any]:
        """创建文件夹."""
        try:
            if parent_path:
                folder_path = self.strategies_root / parent_path / folder_name
            else:
                folder_path = self.strategies_root / folder_name

            if folder_path.exists():
                raise ValueError(f"文件夹已存在: {folder_name}")

            folder_path.mkdir(parents=True, exist_ok=True)

            logger.info("文件夹创建成功: %s", folder_path)

            return {
                "folder_name": folder_name,
                "folder_path": str(
                    folder_path.relative_to(self.strategies_root)
                ).replace("\\", "/"),
                "created_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("创建文件夹失败: %s", e)
            raise

    def move_file(self, file_id: str, target_path: str) -> bool:
        """移动文件."""
        try:
            source_path = self.strategies_root / file_id
            dest_path = self.strategies_root / target_path / source_path.name

            if not source_path.exists():
                raise ValueError(f"源文件不存在: {file_id}")

            if dest_path.exists():
                raise ValueError(f"目标位置已存在同名文件: {dest_path.name}")

            # 确保目标目录存在
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            # 移动文件
            shutil.move(str(source_path), str(dest_path))

            logger.info("文件移动成功: %s -> %s", source_path, dest_path)
            return True

        except Exception as e:
            logger.error("移动文件失败: %s", e)
            raise

    def rename_file(self, file_id: str, new_name: str) -> bool:
        """重命名文件."""
        try:
            source_path = self.strategies_root / file_id
            dest_path = source_path.parent / new_name

            if not source_path.exists():
                raise ValueError(f"文件不存在: {file_id}")

            if dest_path.exists():
                raise ValueError(f"目标名称已存在: {new_name}")

            source_path.rename(dest_path)

            logger.info("文件重命名成功: %s -> %s", file_id, new_name)
            return True

        except Exception as e:
            logger.error("重命名文件失败: %s", e)
            raise


__all__ = ["FileService"]
