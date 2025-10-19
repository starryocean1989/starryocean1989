# -*- coding: utf-8 -*-
"""
IPO缓存机制单元测试
"""

import pytest
import tempfile
from pathlib import Path
from datetime import date, datetime
from backend.infrastructure.data_module_vnpy.local_data.data_quality import IPODateCache


class TestIPODateCache:
    """IPO缓存测试类"""

    @pytest.fixture
    def temp_cache_file(self):
        """创建临时缓存文件"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            temp_path = Path(f.name)
        yield temp_path
        # 清理
        if temp_path.exists():
            temp_path.unlink()

    @pytest.fixture
    def cache(self, temp_cache_file):
        """创建IPO缓存实例"""
        return IPODateCache(cache_file=temp_cache_file)

    def test_cache_initialization(self, cache, temp_cache_file):
        """测试缓存初始化"""
        assert cache.cache_file == temp_cache_file
        assert cache._memory_cache == {}
        stats = cache.get_stats()
        assert stats["cache_size"] == 0
        assert stats["hits"] == 0
        assert stats["misses"] == 0

    def test_cache_set_and_get(self, cache):
        """测试缓存设置和获取"""
        # 设置缓存
        test_date = date(2020, 1, 15)
        cache.set("600000", test_date)

        # 获取缓存（应该命中）
        result, is_cached = cache.get("600000")
        assert is_cached is True
        assert result == test_date

        # 获取不存在的缓存（应该未命中）
        result2, is_cached2 = cache.get("600001")
        assert is_cached2 is False
        assert result2 is None

    def test_cache_none_value(self, cache):
        """测试缓存None值（API查询失败的情况）"""
        cache.set("600000", None)

        result, is_cached = cache.get("600000")
        assert is_cached is True
        assert result is None

    def test_cache_persistence(self, temp_cache_file):
        """测试缓存持久化"""
        # 创建第一个缓存实例并保存数据
        cache1 = IPODateCache(cache_file=temp_cache_file)
        test_date = date(2020, 1, 15)
        cache1.set("600000", test_date, save_immediately=True)

        # 创建第二个缓存实例，应该自动加载之前的数据
        cache2 = IPODateCache(cache_file=temp_cache_file)
        result, is_cached = cache2.get("600000")

        assert is_cached is True
        assert result == test_date

    def test_batch_save(self, cache, temp_cache_file):
        """测试批量保存"""
        # 设置多个缓存项
        cache.set("600000", date(2020, 1, 15))
        cache.set("600001", date(2020, 2, 20))
        cache.set("600002", None)  # 查询失败的情况

        # 批量保存
        cache.batch_save()

        # 验证文件是否存在
        assert temp_cache_file.exists()

        # 重新加载验证
        cache2 = IPODateCache(cache_file=temp_cache_file)
        assert cache2.get("600000")[0] == date(2020, 1, 15)
        assert cache2.get("600001")[0] == date(2020, 2, 20)
        assert cache2.get("600002")[0] is None

    def test_cache_stats(self, cache):
        """测试缓存统计"""
        # 设置一些数据
        cache.set("600000", date(2020, 1, 15))
        cache.set("600001", date(2020, 2, 20))

        # 命中测试
        cache.get("600000")  # 命中
        cache.get("600000")  # 再次命中
        cache.get("600999")  # 未命中

        stats = cache.get_stats()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["total_queries"] == 3
        assert stats["hit_rate"] == pytest.approx(66.67, rel=0.1)
        assert stats["cache_size"] == 2

    def test_api_call_stats(self, cache):
        """测试API调用统计"""
        # 记录API调用
        cache.record_api_call(success=True)
        cache.record_api_call(success=True)
        cache.record_api_call(success=False, timeout=True)
        cache.record_api_call(success=False)

        stats = cache.get_stats()
        assert stats["api_calls"] == 4
        assert stats["api_success"] == 2
        assert stats["api_timeout"] == 1
        assert stats["errors"] == 1

    def test_corrupted_cache_file(self, temp_cache_file):
        """测试损坏的缓存文件处理"""
        # 写入无效的JSON
        with open(temp_cache_file, "w") as f:
            f.write("invalid json content {{{")

        # 应该能够处理损坏的文件并重建缓存
        cache = IPODateCache(cache_file=temp_cache_file)
        assert cache._memory_cache == {}

        # 应该能正常使用
        cache.set("600000", date(2020, 1, 15))
        result, is_cached = cache.get("600000")
        assert is_cached is True
        assert result == date(2020, 1, 15)

    def test_thread_safety(self, cache):
        """测试线程安全（基本验证）"""
        import threading

        results = []

        def set_cache(symbol, ipo_date):
            cache.set(symbol, ipo_date)
            result, _ = cache.get(symbol)
            results.append((symbol, result))

        # 创建多个线程同时设置缓存
        threads = []
        for i in range(10):
            symbol = f"60000{i}"
            ipo_date = date(2020, 1, i + 1)
            t = threading.Thread(target=set_cache, args=(symbol, ipo_date))
            threads.append(t)
            t.start()

        # 等待所有线程完成
        for t in threads:
            t.join()

        # 验证所有数据都正确保存
        assert len(results) == 10
        for symbol, result in results:
            assert result is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
