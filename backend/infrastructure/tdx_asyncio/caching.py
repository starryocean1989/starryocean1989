# -*- coding: utf-8 -*-
"""
异步缓存系统模块

提供智能文件缓存和内存缓存功能，完全异步化实现，
借鉴mootdx的设计但不依赖任何外部库。

作者：[项目名称]
版本：2.0
"""

import asyncio
import hashlib
import json
import os
import pickle
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Union
from functools import wraps

import pandas as pd

# 🚀 原生IOCP异步文件I/O：优先使用Windows IOCP，自动降级到aiofiles
try:
    from backend.infrastructure.native_iocp import compat_aopen
    _USE_IOCP = True
except ImportError:
    compat_aopen = None
    _USE_IOCP = False

from .logger import logger


class AsyncFileCache:
    """
    异步文件缓存装饰器（完全重写为异步）

    特性：
    - 基于文件修改时间的自动刷新
    - 异步读写（不阻塞）
    - 异常恢复机制
    - 支持 pickle/json/parquet 格式
    - 内存缓存优化
    """

    def __init__(
        self,
        filepath: str,
        refresh_time: Optional[float] = None,
        format_type: str = 'pickle',
        memory_cache: bool = True,
        cache_dir: str = 'cache'
    ):
        """
        初始化缓存装饰器

        :param filepath: 缓存文件路径
        :param refresh_time: 刷新间隔（秒），None表示只检查文件修改时间
        :param format_type: 缓存格式 ('pickle', 'json', 'parquet')
        :param memory_cache: 是否启用内存缓存
        :param cache_dir: 缓存目录
        """
        self.filepath = Path(filepath)
        self.refresh_time = refresh_time
        self.format_type = format_type.lower()
        self.memory_cache = memory_cache
        self.cache_dir = Path(cache_dir)

        # 内存缓存
        self._memory_cache: Dict[str, tuple] = {}  # {key: (data, timestamp)}

        # 确保缓存目录存在
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def __call__(self, func: Callable) -> Callable:
        """装饰器实现"""
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 生成缓存键
            cache_key = self._generate_cache_key(func.__name__, args, kwargs)

            # 检查内存缓存
            if self.memory_cache and cache_key in self._memory_cache:
                data, timestamp = self._memory_cache[cache_key]
                if self._is_cache_valid(timestamp):
                    logger.debug(f"使用内存缓存: {cache_key}")
                    return data

            # 检查文件缓存
            file_data = await self._load_from_file(cache_key)
            if file_data is not None:
                # 更新内存缓存
                if self.memory_cache:
                    self._memory_cache[cache_key] = (file_data, time.time())
                return file_data

            # 执行函数并缓存结果
            logger.debug(f"执行函数并缓存: {cache_key}")
            result = await func(*args, **kwargs)

            # 保存到文件
            await self._save_to_file(cache_key, result)

            # 更新内存缓存
            if self.memory_cache:
                self._memory_cache[cache_key] = (result, time.time())

            return result

        return wrapper

    def _generate_cache_key(self, func_name: str, args: tuple, kwargs: dict) -> str:
        """生成缓存键"""
        # 简单的键生成策略（可以根据需要优化）
        key_data = f"{func_name}:{args}:{sorted(kwargs.items())}"
        return hashlib.md5(key_data.encode()).hexdigest()

    def _is_cache_valid(self, timestamp: float) -> bool:
        """检查缓存是否有效"""
        if self.refresh_time is None:
            return True  # 只检查文件修改时间

        return (time.time() - timestamp) < self.refresh_time

    async def _load_from_file(self, cache_key: str) -> Any:
        """从文件加载缓存"""
        filepath = self.cache_dir / f"{cache_key}.{self.format_type}"

        try:
            # 检查文件是否存在且未过期
            if not filepath.exists():
                return None

            file_mtime = os.path.getmtime(filepath)
            if not self._is_cache_valid(file_mtime):
                logger.debug(f"文件缓存过期: {filepath}")
                return None

            # 异步读取文件
            if self.format_type == 'pickle':
                return await self._async_load_pickle(filepath)
            elif self.format_type == 'json':
                return await self._async_load_json(filepath)
            elif self.format_type == 'parquet':
                return await self._async_load_parquet(filepath)
            else:
                logger.warning(f"不支持的缓存格式: {self.format_type}")
                return None

        except Exception as e:
            logger.warning(f"加载缓存失败: {e}")
            return None

    async def _save_to_file(self, cache_key: str, data: Any) -> None:
        """保存数据到文件"""
        filepath = self.cache_dir / f"{cache_key}.{self.format_type}"

        try:
            # 异步写入文件
            if self.format_type == 'pickle':
                await self._async_save_pickle(filepath, data)
            elif self.format_type == 'json':
                await self._async_save_json(filepath, data)
            elif self.format_type == 'parquet':
                await self._async_save_parquet(filepath, data)
            else:
                logger.warning(f"不支持的缓存格式: {self.format_type}")

        except Exception as e:
            logger.error(f"保存缓存失败: {e}")

    async def _async_load_pickle(self, filepath: Path) -> Any:
        """异步加载pickle文件"""
        def _load():
            with open(filepath, 'rb') as f:
                return pickle.load(f)
        return await asyncio.get_event_loop().run_in_executor(None, _load)

    async def _async_save_pickle(self, filepath: Path, data: Any) -> None:
        """异步保存pickle文件"""
        def _save():
            with open(filepath, 'wb') as f:
                pickle.dump(data, f)
        await asyncio.get_event_loop().run_in_executor(None, _save)

    async def _async_load_json(self, filepath: Path) -> Any:
        """异步加载JSON文件"""
        def _load():
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return await asyncio.get_event_loop().run_in_executor(None, _load)

    async def _async_save_json(self, filepath: Path, data: Any) -> None:
        """异步保存JSON文件"""
        def _save():
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        await asyncio.get_event_loop().run_in_executor(None, _save)

    async def _async_load_parquet(self, filepath: Path) -> pd.DataFrame:
        """异步加载Parquet文件（使用native_iocp真异步）"""
        try:
            if _USE_IOCP and compat_aopen is not None:
                # 🚀 使用native_iocp异步读取（真异步，无线程池）
                file_obj = await compat_aopen(filepath, 'rb')
                async with file_obj:
                    data = await file_obj.read()

                # 使用pyarrow解析Parquet数据
                import pyarrow.parquet as pq
                import io
                table = pq.read_table(io.BytesIO(data))
                return table.to_pandas()
            else:
                # 降级到executor
                def _load():
                    return pd.read_parquet(filepath)
                return await asyncio.get_event_loop().run_in_executor(None, _load)
        except Exception as e:
            logger.warning(f"异步读取Parquet失败，降级到executor: {e}")
            # 最终降级到executor
            def _load():
                return pd.read_parquet(filepath)
            return await asyncio.get_event_loop().run_in_executor(None, _load)

    async def _async_save_parquet(self, filepath: Path, data: pd.DataFrame) -> None:
        """异步保存Parquet文件"""
        def _save():
            data.to_parquet(filepath, index=False)
        await asyncio.get_event_loop().run_in_executor(None, _save)


class AsyncDataCache:
    """
    异步数据缓存管理器

    提供内存缓存管理，支持TTL和模式匹配清除
    """

    def __init__(self, default_ttl: Optional[float] = None):
        """
        初始化缓存管理器

        :param default_ttl: 默认TTL（秒）
        """
        self.default_ttl = default_ttl
        self._cache: Dict[str, Dict[str, Any]] = {}  # {key: {'data': data, 'timestamp': ts, 'ttl': ttl}}

    async def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        """
        设置缓存

        :param key: 缓存键
        :param value: 缓存值
        :param ttl: TTL（秒），None使用默认值
        """
        ttl = ttl or self.default_ttl
        self._cache[key] = {
            'data': value,
            'timestamp': time.time(),
            'ttl': ttl
        }

    async def get(self, key: str) -> Optional[Any]:
        """
        获取缓存

        :param key: 缓存键
        :return: 缓存值或None
        """
        if key not in self._cache:
            return None

        cache_item = self._cache[key]

        # 检查是否过期
        if cache_item['ttl'] is not None:
            if time.time() - cache_item['timestamp'] > cache_item['ttl']:
                del self._cache[key]
                return None

        return cache_item['data']

    async def clear(self, pattern: Optional[str] = None) -> int:
        """
        清除缓存

        :param pattern: 匹配模式（支持通配符）
        :return: 删除的缓存数量
        """
        if pattern is None:
            # 清空所有缓存
            count = len(self._cache)
            self._cache.clear()
            return count

        # 模式匹配删除
        import fnmatch
        keys_to_delete = []

        for key in self._cache.keys():
            if fnmatch.fnmatch(key, pattern):
                keys_to_delete.append(key)

        for key in keys_to_delete:
            del self._cache[key]

        return len(keys_to_delete)

    async def size(self) -> int:
        """获取缓存大小"""
        return len(self._cache)

    async def cleanup(self) -> int:
        """清理过期缓存"""
        current_time = time.time()
        keys_to_delete = []

        for key, cache_item in self._cache.items():
            if cache_item['ttl'] is not None:
                if current_time - cache_item['timestamp'] > cache_item['ttl']:
                    keys_to_delete.append(key)

        for key in keys_to_delete:
            del self._cache[key]

        return len(keys_to_delete)


# ==================== 便捷装饰器工厂 ====================

def async_file_cache(
    filepath: str,
    refresh_time: Optional[float] = None,
    format_type: str = 'pickle'
):
    """
    创建异步文件缓存装饰器

    :param filepath: 缓存文件路径
    :param refresh_time: 刷新间隔（秒）
    :param format_type: 缓存格式
    :return: 装饰器函数
    """
    def decorator(func):
        cache_instance = AsyncFileCache(filepath, refresh_time, format_type)
        return cache_instance(func)
    return decorator


# ==================== 使用示例 ====================

async def example_usage():
    """使用示例"""

    # 1. 文件缓存装饰器示例
    @async_file_cache('cache/expensive_data.pkl', refresh_time=3600)  # 缓存1小时
    async def expensive_query():
        print("执行耗时查询...")
        await asyncio.sleep(2)  # 模拟耗时操作
        return {'data': 'expensive_result'}

    # 第一次调用（会执行函数并缓存）
    result1 = await expensive_query()
    print(f"第一次结果: {result1}")

    # 第二次调用（使用缓存）
    result2 = await expensive_query()
    print(f"第二次结果: {result2}")

    # 2. 数据缓存管理器示例
    cache = AsyncDataCache(default_ttl=60)  # 默认缓存60秒

    await cache.set('key1', 'value1', ttl=30)  # 缓存30秒
    await cache.set('key2', 'value2')  # 使用默认TTL

    value1 = await cache.get('key1')
    value2 = await cache.get('key2')

    print(f"缓存值1: {value1}")
    print(f"缓存值2: {value2}")

    # 等待30秒后key1过期
    await asyncio.sleep(35)
    value1_expired = await cache.get('key1')  # None
    print(f"过期后的key1: {value1_expired}")

    # 清理过期缓存
    cleaned = await cache.cleanup()
    print(f"清理了{cleaned}个过期缓存")


if __name__ == "__main__":
    # 运行示例
    asyncio.run(example_usage())
