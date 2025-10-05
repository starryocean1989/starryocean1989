# -*- coding: utf-8 -*-
"""
文件操作模块

提供文件和目录的基本操作功能.
"""

import os
import shutil
import logging
import stat
import glob
from typing import Dict, Any, List, Optional, Union

logger = logging.getLogger(__name__)


class FileManager:
    """文件管理器"""

    def create_directory(self, path: str, exist_ok: bool = True) -> bool:
        """创建目录"""
        try:
            os.makedirs(path, exist_ok=exist_ok)
            return True
        except (OSError, PermissionError) as e:
            logger.error("创建目录失败: %s", e)
            return False

    def delete_file(self, path: str) -> bool:
        """删除文件"""
        try:
            if os.path.isfile(path):
                os.remove(path)
                return True
            return False
        except (OSError, PermissionError) as e:
            logger.error("删除文件失败: %s", e)
            return False

    def copy_file(self, src: str, dst: str) -> bool:
        """复制文件"""
        try:
            shutil.copy2(src, dst)
            return True
        except (OSError, PermissionError, shutil.Error) as e:
            logger.error("复制文件失败: %s", e)
            return False


class DirectoryManager:
    """目录管理器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def list_directory(
        self, path: str, pattern: str = "*", recursive: bool = False
    ) -> List[str]:
        """列出目录内容"""
        try:
            if not os.path.exists(path):
                self.logger.warning("目录不存在: %s", path)
                return []

            if not os.path.isdir(path):
                self.logger.warning("路径不是目录: %s", path)
                return []

            if recursive:
                # 递归搜索
                search_pattern = os.path.join(path, "**", pattern)
                return glob.glob(search_pattern, recursive=True)
            else:
                # 非递归搜索
                search_pattern = os.path.join(path, pattern)
                return glob.glob(search_pattern)

        except (OSError, PermissionError) as e:
            self.logger.error("列出目录内容失败: %s", e)
            return []

    def get_directory_info(self, path: str) -> Optional[Dict[str, Any]]:
        """获取目录信息"""
        try:
            if not os.path.exists(path):
                return None

            stat_info = os.stat(path)
            return {
                "path": path,
                "size": stat_info.st_size,
                "created": stat_info.st_ctime,
                "modified": stat_info.st_mtime,
                "accessed": stat_info.st_atime,
                "permissions": oct(stat_info.st_mode)[-3:],
                "is_directory": os.path.isdir(path),
                "is_file": os.path.isfile(path),
                "is_symlink": os.path.islink(path)
            }
        except (OSError, PermissionError) as e:
            self.logger.error("获取目录信息失败: %s", e)
            return None

    def delete_directory(self, path: str, recursive: bool = False) -> bool:
        """删除目录"""
        try:
            if not os.path.exists(path):
                self.logger.warning("目录不存在: %s", path)
                return True

            if not os.path.isdir(path):
                self.logger.warning("路径不是目录: %s", path)
                return False

            if recursive:
                shutil.rmtree(path)
            else:
                os.rmdir(path)

            return True
        except (OSError, PermissionError, shutil.Error) as e:
            self.logger.error("删除目录失败: %s", e)
            return False

    def copy_directory(
        self, src: str, dst: str,
        ignore_patterns: Optional[List[str]] = None
    ) -> bool:
        """复制目录"""
        try:
            if not os.path.exists(src):
                self.logger.error("源目录不存在: %s", src)
                return False

            if not os.path.isdir(src):
                self.logger.error("源路径不是目录: %s", src)
                return False

            # 创建目标目录的父目录
            os.makedirs(os.path.dirname(dst), exist_ok=True)

            if ignore_patterns:
                def ignore_func(_, names):
                    ignored = []
                    for pattern in ignore_patterns:
                        for name in names:
                            if glob.fnmatch.fnmatch(name, pattern):
                                ignored.append(name)
                    return ignored
                shutil.copytree(src, dst, ignore=ignore_func)
            else:
                shutil.copytree(src, dst)

            return True
        except (OSError, PermissionError, shutil.Error) as e:
            self.logger.error("复制目录失败: %s", e)
            return False

    def move_directory(self, src: str, dst: str) -> bool:
        """移动目录"""
        try:
            if not os.path.exists(src):
                self.logger.error("源目录不存在: %s", src)
                return False

            if not os.path.isdir(src):
                self.logger.error("源路径不是目录: %s", src)
                return False

            shutil.move(src, dst)
            return True
        except (OSError, PermissionError, shutil.Error) as e:
            self.logger.error("移动目录失败: %s", e)
            return False

    def get_directory_size(self, path: str) -> int:
        """获取目录大小(字节)"""
        try:
            if not os.path.exists(path):
                return 0

            total_size = 0
            for dirpath, _, filenames in os.walk(path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    try:
                        total_size += os.path.getsize(filepath)
                    except (OSError, PermissionError):
                        continue

            return total_size
        except (OSError, PermissionError) as e:
            self.logger.error("获取目录大小失败: %s", e)
            return 0

    def clean_empty_directories(self, path: str) -> int:
        """清理空目录,返回清理的目录数量"""
        try:
            cleaned_count = 0

            for root, dirs, _ in os.walk(path, topdown=False):
                for dir_name in dirs:
                    dir_path = os.path.join(root, dir_name)
                    try:
                        if not os.listdir(dir_path):  # 目录为空
                            os.rmdir(dir_path)
                            cleaned_count += 1
                    except (OSError, PermissionError):
                        continue

            return cleaned_count
        except (OSError, PermissionError) as e:
            self.logger.error("清理空目录失败: %s", e)
            return 0


class FilePermissionManager:
    """文件权限管理器"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_permissions(self, path: str) -> Optional[Dict[str, Any]]:
        """获取文件或目录权限信息"""
        try:
            if not os.path.exists(path):
                self.logger.warning("路径不存在: %s", path)
                return None

            stat_info = os.stat(path)
            mode = stat_info.st_mode

            return {
                "path": path,
                "mode": oct(mode),
                "permissions": oct(mode)[-3:],
                "owner_read": bool(mode & stat.S_IRUSR),
                "owner_write": bool(mode & stat.S_IWUSR),
                "owner_execute": bool(mode & stat.S_IXUSR),
                "group_read": bool(mode & stat.S_IRGRP),
                "group_write": bool(mode & stat.S_IWGRP),
                "group_execute": bool(mode & stat.S_IXGRP),
                "other_read": bool(mode & stat.S_IROTH),
                "other_write": bool(mode & stat.S_IWOTH),
                "other_execute": bool(mode & stat.S_IXOTH),
                "is_directory": stat.S_ISDIR(mode),
                "is_file": stat.S_ISREG(mode),
                "is_symlink": stat.S_ISLNK(mode)
            }
        except (OSError, PermissionError) as e:
            self.logger.error("获取权限信息失败: %s", e)
            return None

    def set_permissions(self, path: str, mode: Union[int, str]) -> bool:
        """设置文件或目录权限"""
        try:
            if not os.path.exists(path):
                self.logger.error("路径不存在: %s", path)
                return False

            if isinstance(mode, str):
                # 如果是字符串格式(如 "755", "644")
                if mode.startswith('0'):
                    mode = int(mode, 8)
                else:
                    mode = int(mode, 8)

            os.chmod(path, mode)
            return True
        except (OSError, PermissionError) as e:
            self.logger.error("设置权限失败: %s", e)
            return False

    def _get_permission_mask(self, permission: str) -> Optional[int]:
        """获取权限掩码"""
        permission_masks = {
            "read": stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH,
            "write": stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH,
            "execute": stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH,
            "owner_read": stat.S_IRUSR,
            "owner_write": stat.S_IWUSR,
            "owner_execute": stat.S_IXUSR,
            "group_read": stat.S_IRGRP,
            "group_write": stat.S_IWGRP,
            "group_execute": stat.S_IXGRP,
            "other_read": stat.S_IROTH,
            "other_write": stat.S_IWOTH,
            "other_execute": stat.S_IXOTH,
        }
        return permission_masks.get(permission)

    def add_permission(self, path: str, permission: str) -> bool:
        """添加权限"""
        try:
            if not os.path.exists(path):
                self.logger.error("路径不存在: %s", path)
                return False

            current_mode = os.stat(path).st_mode
            permission_mask = self._get_permission_mask(permission)

            if permission_mask is None:
                self.logger.error("未知的权限类型: %s", permission)
                return False

            new_mode = current_mode | permission_mask
            os.chmod(path, new_mode)
            return True
        except (OSError, PermissionError) as e:
            self.logger.error("添加权限失败: %s", e)
            return False

    def remove_permission(self, path: str, permission: str) -> bool:
        """移除权限"""
        try:
            if not os.path.exists(path):
                self.logger.error("路径不存在: %s", path)
                return False

            current_mode = os.stat(path).st_mode
            permission_mask = self._get_permission_mask(permission)

            if permission_mask is None:
                self.logger.error("未知的权限类型: %s", permission)
                return False

            new_mode = current_mode & ~permission_mask
            os.chmod(path, new_mode)
            return True
        except (OSError, PermissionError) as e:
            self.logger.error("移除权限失败: %s", e)
            return False

    def is_readable(self, path: str) -> bool:
        """检查文件或目录是否可读"""
        try:
            return os.access(path, os.R_OK)
        except (OSError, PermissionError) as e:
            self.logger.error("检查读权限失败: %s", e)
            return False

    def is_writable(self, path: str) -> bool:
        """检查文件或目录是否可写"""
        try:
            return os.access(path, os.W_OK)
        except (OSError, PermissionError) as e:
            self.logger.error("检查写权限失败: %s", e)
            return False

    def is_executable(self, path: str) -> bool:
        """检查文件或目录是否可执行"""
        try:
            return os.access(path, os.X_OK)
        except (OSError, PermissionError) as e:
            self.logger.error("检查执行权限失败: %s", e)
            return False

    def set_secure_permissions(
        self, path: str, is_directory: bool = False
    ) -> bool:
        """设置安全权限(文件644,目录755)"""
        try:
            if is_directory:
                mode = 0o755  # rwxr-xr-x
            else:
                mode = 0o644  # rw-r--r--

            return self.set_permissions(path, mode)
        except (OSError, PermissionError) as e:
            self.logger.error("设置安全权限失败: %s", e)
            return False

    def batch_set_permissions(
        self, paths: List[str], mode: Union[int, str]
    ) -> List[bool]:
        """批量设置权限"""
        results = []
        for path in paths:
            results.append(self.set_permissions(path, mode))
        return results


def _handle_file_operations(
    operation: Dict[str, Any], file_manager: FileManager
) -> bool:
    """处理文件操作"""
    op_type = operation.get('operation')
    path = operation.get('path')

    if op_type == 'create_file':
        content = operation.get('content', '')
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    elif op_type == 'delete_file':
        return file_manager.delete_file(path)
    elif op_type == 'copy_file':
        dst = operation.get('destination')
        return file_manager.copy_file(path, dst) if dst else False
    return False


def _handle_directory_operations(
    operation: Dict[str, Any], dir_manager: DirectoryManager
) -> bool:
    """处理目录操作"""
    op_type = operation.get('operation')
    path = operation.get('path')

    if op_type == 'create_directory':
        exist_ok = operation.get('exist_ok', True)
        return dir_manager.create_directory(path, exist_ok)
    elif op_type == 'delete_directory':
        recursive = operation.get('recursive', False)
        return dir_manager.delete_directory(path, recursive)
    elif op_type == 'copy_directory':
        dst = operation.get('destination')
        ignore_patterns = operation.get('ignore_patterns')
        return (
            dir_manager.copy_directory(path, dst, ignore_patterns)
            if dst else False
        )
    elif op_type == 'move_directory':
        dst = operation.get('destination')
        return dir_manager.move_directory(path, dst) if dst else False
    elif op_type == 'get_info':
        info = dir_manager.get_directory_info(path)
        return info is not None
    elif op_type == 'list_directory':
        pattern = operation.get('pattern', '*')
        recursive = operation.get('recursive', False)
        files = dir_manager.list_directory(path, pattern, recursive)
        return len(files) >= 0
    return False


def _handle_permission_operations(
    operation: Dict[str, Any], perm_manager: FilePermissionManager
) -> bool:
    """处理权限操作"""
    op_type = operation.get('operation')
    path = operation.get('path')

    if op_type == 'set_permissions':
        mode = operation.get('mode')
        return (
            perm_manager.set_permissions(path, mode)
            if mode is not None else False
        )
    return False


def _execute_file_operation(
    operation: Dict[str, Any], file_manager: FileManager,
    dir_manager: DirectoryManager, perm_manager: FilePermissionManager
) -> bool:
    """执行单个文件操作"""
    op_type = operation.get('operation')
    path = operation.get('path')

    if not op_type or not path:
        return False

    # 尝试文件操作
    result = _handle_file_operations(operation, file_manager)
    if result is not False:
        return result

    # 尝试目录操作
    result = _handle_directory_operations(operation, dir_manager)
    if result is not False:
        return result

    # 尝试权限操作
    result = _handle_permission_operations(operation, perm_manager)
    if result is not False:
        return result

    logger.warning("未知的操作类型: %s", op_type)
    return False


def batch_file_operations(operations: List[Dict[str, Any]]) -> List[bool]:
    """批量文件操作

    Args:
        operations: 操作列表,每个操作包含以下字段:
            - operation: 操作类型 ('create_file', 'delete_file', 'copy_file',
                      'create_directory', 'delete_directory', 'copy_directory',
                      'move_directory', 'set_permissions', 'get_info',
                      'list_directory')
            - path: 文件或目录路径
            - 其他操作特定参数

    Returns:
        操作结果列表,True表示成功,False表示失败
    """
    file_manager = FileManager()
    dir_manager = DirectoryManager()
    perm_manager = FilePermissionManager()

    results = []

    for operation in operations:
        try:
            result = _execute_file_operation(
                operation, file_manager, dir_manager, perm_manager
            )
            results.append(result)
        except (OSError, PermissionError, shutil.Error, IOError) as e:
            logger.error("批量操作执行失败: %s", e)
            results.append(False)

    return results


__all__ = [
    "FileManager",
    "DirectoryManager",
    "FilePermissionManager",
    "batch_file_operations",
]
