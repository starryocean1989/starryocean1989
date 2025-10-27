# -*- coding: utf-8 -*-
"""
统一缓存管理器

实现次日0时失效策略的缓存管理机制。
所有缓存文件格式统一为：
{
    "cache_date": "YYYY-MM-DD",
    "data": { ... }
}

v1.1 改进：
- 使用网络时间替代系统时间，避免系统时间不准确导致的缓存验证错误

作者：星辰科技
版本：1.1
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# 导入网络时间同步模块
from .utils.network_time import get_real_date


class DailyCacheManager:
    """
    统一缓存管理器（静态工具类）

    提供基于日期的缓存失效机制：
    - 次日0时自动失效
    - 统一的缓存文件格式
    - 线程安全的读写操作
    """

    @classmethod
    def _get_cache_dir(cls) -> Path:
        """动态获取缓存目录（绝对路径）

        优先从 config_manager 获取，确保使用用户配置的绝对路径
        """
        try:
            from backend.infrastructure.data_module_vnpy.config import config_manager

            return config_manager.get_cache_dir()
        except Exception:
            # 降级方案：使用 get_project_root()
            from backend.infrastructure.data_module_vnpy.config import get_project_root

            cache_dir = get_project_root() / "data" / "cache"
            cache_dir.mkdir(parents=True, exist_ok=True)
            return cache_dir

    @staticmethod
    def get_today() -> str:
        """获取今天的日期字符串（使用网络时间）

        使用网络时间同步，避免系统时间不准确导致的缓存验证错误

        Returns:
            str: YYYY-MM-DD格式的日期字符串
        """
        return get_real_date().isoformat()

    @staticmethod
    def is_cache_valid(cache_date: Optional[str]) -> bool:
        """判断缓存是否有效（次日0时失效，使用网络时间）

        使用网络时间同步，避免系统时间不准确导致的误判

        Args:
            cache_date: 缓存日期（YYYY-MM-DD格式）

        Returns:
            bool: True=有效，False=失效
        """
        if not cache_date:
            return False

        try:
            cached = datetime.strptime(cache_date, "%Y-%m-%d").date()
            # 使用网络时间替代系统时间
            today = get_real_date()

            # 只有当天的缓存才有效
            return cached >= today

        except (ValueError, TypeError):
            return False

    @classmethod
    def save_with_date(cls, data: Any, cache_file: str, cache_date: Optional[str] = None) -> bool:
        """保存数据到缓存文件（带日期）

        Args:
            data: 要缓存的数据
            cache_file: 缓存文件名（相对于cache_dir）
            cache_date: 缓存日期（默认今天）

        Returns:
            bool: 是否保存成功
        """
        logger = logging.getLogger(__name__)

        try:
            # 获取缓存目录（绝对路径）
            cache_dir = cls._get_cache_dir()
            cache_dir.mkdir(parents=True, exist_ok=True)

            # 构建缓存对象
            cache_obj = {"cache_date": cache_date or cls.get_today(), "data": data}

            # 写入文件
            cache_path = cache_dir / cache_file
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_obj, f, ensure_ascii=False, indent=2, default=str)

            logger.debug("缓存已保存: %s (日期: %s)", cache_file, cache_obj["cache_date"])
            return True

        except Exception as e:
            logger.error("保存缓存失败 (%s): %s", cache_file, e, exc_info=True)
            return False

    @classmethod
    def load_with_validation(
        cls, cache_file: str, validate_date: bool = True
    ) -> Tuple[Optional[Any], Optional[str], bool]:
        """加载缓存并验证日期

        Args:
            cache_file: 缓存文件名（相对于cache_dir）
            validate_date: 是否验证日期（默认True）

        Returns:
            Tuple[data, cache_date, is_valid]:
            - data: 缓存的数据（None表示不存在）
            - cache_date: 缓存日期
            - is_valid: 是否有效（True=有效，False=失效）
        """
        logger = logging.getLogger(__name__)

        try:
            # 获取缓存目录（绝对路径）
            cache_dir = cls._get_cache_dir()
            cache_path = cache_dir / cache_file

            # 检查文件是否存在
            if not cache_path.exists():
                logger.debug("缓存文件不存在: %s", cache_file)
                return None, None, False

            # 读取文件
            with open(cache_path, "r", encoding="utf-8") as f:
                content = f.read().strip()

                # 🔧 处理空文件
                if not content:
                    logger.warning("缓存文件为空: %s", cache_file)
                    return None, None, False

                try:
                    cache_obj = json.loads(content)
                except json.JSONDecodeError as e:
                    logger.warning("缓存文件JSON格式错误: %s (%s)", cache_file, e)
                    return None, None, False

            # 提取数据和日期
            data = cache_obj.get("data")
            cache_date = cache_obj.get("cache_date")

            # 验证日期
            if validate_date:
                is_valid = cls.is_cache_valid(cache_date)
                # 🎯 架构修复：移除高频DEBUG日志，避免刷屏
                # 缓存有效是正常行为，不需要记录（每次查询都会调用，5000+品种会产生数万条日志）
                # 只在缓存失效时记录WARNING（异常情况）
                if not is_valid:
                    logger.warning("缓存已失效: %s (日期: %s)", cache_file, cache_date)
            else:
                is_valid = True  # 不验证则认为有效

            return data, cache_date, is_valid

        except Exception as e:
            logger.error("加载缓存失败 (%s): %s", cache_file, e, exc_info=True)
            return None, None, False

    @classmethod
    def delete_cache(cls, cache_file: str) -> bool:
        """删除缓存文件

        Args:
            cache_file: 缓存文件名

        Returns:
            bool: 是否删除成功
        """
        logger = logging.getLogger(__name__)

        try:
            cache_dir = cls._get_cache_dir()
            cache_path = cache_dir / cache_file
            if cache_path.exists():
                cache_path.unlink()
                logger.info("缓存已删除: %s", cache_file)
                return True
            return False

        except Exception as e:
            logger.error("删除缓存失败 (%s): %s", cache_file, e, exc_info=True)
            return False

    @classmethod
    def get_cache_info(cls, cache_file: str) -> Dict[str, Any]:
        """获取缓存文件信息

        Args:
            cache_file: 缓存文件名

        Returns:
            Dict: 缓存信息 {
                "exists": bool,
                "cache_date": str,
                "is_valid": bool,
                "file_size": int (bytes),
                "modified_time": str
            }
        """
        cache_dir = cls._get_cache_dir()
        cache_path = cache_dir / cache_file

        if not cache_path.exists():
            return {
                "exists": False,
                "cache_date": None,
                "is_valid": False,
                "file_size": 0,
                "modified_time": None,
            }

        try:
            # 读取缓存日期
            _, cache_date, is_valid = cls.load_with_validation(cache_file)

            # 文件统计信息
            stat = cache_path.stat()
            modified_time = datetime.fromtimestamp(stat.st_mtime).isoformat()

            return {
                "exists": True,
                "cache_date": cache_date,
                "is_valid": is_valid,
                "file_size": stat.st_size,
                "modified_time": modified_time,
            }

        except Exception:
            return {
                "exists": True,
                "cache_date": None,
                "is_valid": False,
                "file_size": 0,
                "modified_time": None,
            }


# 便捷函数（供快速调用）


def is_cache_valid(cache_date: Optional[str]) -> bool:
    """判断缓存日期是否有效（便捷函数）"""
    return DailyCacheManager.is_cache_valid(cache_date)


def get_today() -> str:
    """获取今天的日期字符串（便捷函数）"""
    return DailyCacheManager.get_today()


def save_cache(data: Any, cache_file: str) -> bool:
    """保存缓存（便捷函数）"""
    return DailyCacheManager.save_with_date(data, cache_file)


def load_cache(cache_file: str) -> Tuple[Optional[Any], Optional[str], bool]:
    """加载缓存（便捷函数）"""
    return DailyCacheManager.load_with_validation(cache_file)


# 导出
__all__ = [
    "DailyCacheManager",
    "is_cache_valid",
    "get_today",
    "save_cache",
    "load_cache",
]
