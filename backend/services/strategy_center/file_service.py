# -*- coding: utf-8 -*-
"""
策略文件管理服务.

提供策略文件的创建、读取、更新、删除等管理功能。
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from backend.repositories.strategy_repository import StrategyRepository

logger = logging.getLogger(__name__)


class FileService:
    """策略文件管理服务."""

    def __init__(self):
        """初始化文件管理服务."""
        self.base_path = Path("strategies")
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.repository = StrategyRepository()
        logger.info("策略文件管理服务初始化完成，根路径: %s", self.base_path.absolute())

    def get_file_tree(self, folder_path: Optional[str] = None) -> Dict[str, Any]:
        """
        获取文件树结构.

        Args:
            folder_path: 文件夹路径，None表示根目录

        Returns:
            Dict[str, Any]: 文件树结构
        """
        try:
            # 确定扫描路径
            if folder_path:
                scan_path = self.base_path / folder_path.lstrip("/")
            else:
                scan_path = self.base_path

            # 检查路径是否存在
            if not scan_path.exists():
                logger.warning("路径不存在: %s", scan_path)
                return {
                    "name": scan_path.name,
                    "type": "folder",
                    "path": str(scan_path.relative_to(self.base_path)),
                    "children": [],
                }

            # 递归构建文件树
            return self._build_tree(scan_path)

        except Exception as e:
            logger.error("获取文件树失败: %s", e)
            raise

    def _build_tree(self, path: Path) -> Dict[str, Any]:
        """
        递归构建文件树.

        Args:
            path: 路径对象

        Returns:
            Dict[str, Any]: 树节点
        """
        try:
            # 获取相对路径
            rel_path = str(path.relative_to(self.base_path))
            if rel_path == ".":
                rel_path = "/"

            # 如果是文件
            if path.is_file():
                stat = path.stat()
                return {
                    "name": path.name,
                    "type": "file",
                    "path": rel_path,
                    "size": stat.st_size,
                    "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }

            # 如果是文件夹
            children = []
            try:
                for item in sorted(path.iterdir(), key=lambda x: (not x.is_dir(), x.name)):
                    # 跳过隐藏文件和__pycache__
                    if item.name.startswith(".") or item.name == "__pycache__":
                        continue
                    children.append(self._build_tree(item))
            except PermissionError:
                logger.warning("无权限访问: %s", path)

            return {
                "name": path.name if path != self.base_path else "strategies",
                "type": "folder",
                "path": rel_path,
                "children": children,
            }

        except Exception as e:
            logger.error("构建文件树节点失败: %s, error: %s", path, e)
            raise

    async def create_file(
        self,
        file_name: str,
        folder_path: str,
        file_type: str = "python",
        content: str = "",
    ) -> Dict[str, Any]:
        """
        创建新文件.

        Args:
            file_name: 文件名
            folder_path: 文件夹路径
            file_type: 文件类型
            content: 初始内容

        Returns:
            Dict[str, Any]: 文件信息
        """
        try:
            # 构建完整路径
            folder = self.base_path / folder_path.lstrip("/")
            folder.mkdir(parents=True, exist_ok=True)

            file_path = folder / file_name
            if file_path.exists():
                raise ValueError(f"文件已存在: {file_name}")

            # 写入文件内容
            file_path.write_text(content, encoding="utf-8")

            # 生成文件ID
            file_id = f"file_{int(datetime.now().timestamp() * 1000)}"
            rel_path = str(file_path.relative_to(self.base_path))

            # 保存到数据库
            file_data = {
                "id": file_id,
                "name": file_name,
                "path": rel_path,
                "type": file_type,
                "content": content,
            }
            await self.repository.create_strategy(file_data)

            logger.info("文件创建成功: %s", rel_path)
            return {
                "file_id": file_id,
                "file_name": file_name,
                "folder_path": folder_path,
                "file_type": file_type,
                "path": rel_path,
                "size": len(content.encode("utf-8")),
                "created_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("创建文件失败: %s/%s, error: %s", folder_path, file_name, e)
            raise

    async def get_file_content(self, file_id: str) -> Dict[str, Any]:
        """
        获取文件内容.

        Args:
            file_id: 文件ID

        Returns:
            Dict[str, Any]: 文件内容信息
        """
        try:
            # 从数据库获取文件信息
            file_info = await self.repository.get_strategy(file_id)
            if not file_info:
                raise ValueError(f"文件不存在: {file_id}")

            # 从文件系统读取内容
            file_path = self.base_path / file_info["path"]
            if file_path.exists():
                content = file_path.read_text(encoding="utf-8")
            else:
                # 如果文件不存在，使用数据库中的内容
                content = file_info.get("content", "")
                logger.warning("文件不存在于文件系统: %s", file_path)

            logger.info("获取文件内容成功: %s", file_id)
            return {
                "file_id": file_id,
                "file_name": file_info["name"],
                "path": file_info["path"],
                "file_type": file_info["type"],
                "content": content,
                "size": len(content.encode("utf-8")),
                "updated_at": file_info.get("updated_at", datetime.now().isoformat()),
            }

        except Exception as e:
            logger.error("获取文件内容失败: %s, error: %s", file_id, e)
            raise

    async def update_file_content(
        self, file_id: str, content: str, file_name: Optional[str] = None
    ) -> bool:
        """
        更新文件内容.

        Args:
            file_id: 文件ID
            content: 新内容
            file_name: 新文件名（可选）

        Returns:
            bool: 是否成功
        """
        try:
            # 从数据库获取文件信息
            file_info = await self.repository.get_strategy(file_id)
            if not file_info:
                raise ValueError(f"文件不存在: {file_id}")

            # 更新文件系统中的内容
            old_path = self.base_path / file_info["path"]

            # 如果改名了，需要重命名文件
            if file_name and file_name != file_info["name"]:
                new_path = old_path.parent / file_name
                if new_path.exists() and new_path != old_path:
                    raise ValueError(f"文件名已存在: {file_name}")
                old_path.rename(new_path)
                old_path = new_path
                new_rel_path = str(new_path.relative_to(self.base_path))
            else:
                new_rel_path = file_info["path"]

            # 写入新内容
            old_path.write_text(content, encoding="utf-8")

            # 更新数据库
            updates = {
                "content": content,
                "path": new_rel_path,
            }
            if file_name:
                updates["name"] = file_name

            success = await self.repository.update_strategy(file_id, updates)

            if success:
                logger.info("文件更新成功: %s", file_id)
            return success

        except Exception as e:
            logger.error("更新文件内容失败: %s, error: %s", file_id, e)
            raise

    async def delete_file(self, file_id: str) -> bool:
        """
        删除文件.

        Args:
            file_id: 文件ID

        Returns:
            bool: 是否成功
        """
        try:
            # 从数据库获取文件信息
            file_info = await self.repository.get_strategy(file_id)
            if not file_info:
                raise ValueError(f"文件不存在: {file_id}")

            # 删除文件系统中的文件
            file_path = self.base_path / file_info["path"]
            if file_path.exists():
                file_path.unlink()

            # 从数据库删除
            success = await self.repository.delete_strategy(file_id)

            if success:
                logger.info("文件删除成功: %s", file_id)
            return success

        except Exception as e:
            logger.error("删除文件失败: %s, error: %s", file_id, e)
            raise

    async def create_folder(self, folder_name: str, parent_path: str) -> Dict[str, Any]:
        """
        创建文件夹.

        Args:
            folder_name: 文件夹名
            parent_path: 父路径

        Returns:
            Dict[str, Any]: 文件夹信息
        """
        try:
            # 构建完整路径
            parent = self.base_path / parent_path.lstrip("/")
            folder_path = parent / folder_name

            if folder_path.exists():
                raise ValueError(f"文件夹已存在: {folder_name}")

            # 创建文件夹
            folder_path.mkdir(parents=True, exist_ok=False)

            rel_path = str(folder_path.relative_to(self.base_path))
            logger.info("文件夹创建成功: %s", rel_path)

            return {
                "folder_name": folder_name,
                "parent_path": parent_path,
                "path": rel_path,
                "created_at": datetime.now().isoformat(),
            }

        except Exception as e:
            logger.error("创建文件夹失败: %s/%s, error: %s", parent_path, folder_name, e)
            raise

    async def move_file(self, file_id: str, target_path: str) -> bool:
        """
        移动文件.

        Args:
            file_id: 文件ID
            target_path: 目标路径

        Returns:
            bool: 是否成功
        """
        try:
            # 从数据库获取文件信息
            file_info = await self.repository.get_strategy(file_id)
            if not file_info:
                raise ValueError(f"文件不存在: {file_id}")

            # 构建源路径和目标路径
            source = self.base_path / file_info["path"]
            target_dir = self.base_path / target_path.lstrip("/")
            target_dir.mkdir(parents=True, exist_ok=True)

            target = target_dir / source.name

            if target.exists():
                raise ValueError(f"目标路径已存在文件: {target.name}")

            # 移动文件
            shutil.move(str(source), str(target))

            # 更新数据库
            new_rel_path = str(target.relative_to(self.base_path))
            success = await self.repository.update_strategy(file_id, {"path": new_rel_path})

            if success:
                logger.info("文件移动成功: %s -> %s", file_info["path"], new_rel_path)
            return success

        except Exception as e:
            logger.error("移动文件失败: %s, error: %s", file_id, e)
            raise


__all__ = ["FileService"]
