# -*- coding: utf-8 -*-
"""
快速测试多进程服务器池 - 只测试60个服务器（2个进程）
"""

import sys
import time
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from backend.core.base import setup_logging
from backend.core.config import init_settings

# 初始化配置
init_settings()

# 临时修改配置（只测试60个服务器）
from backend.infrastructure.data_module_vnpy.config import config_manager

config_manager._config["chinastock.server_pool.server_count"] = 60  # 60个服务器 = 2个进程

from backend.infrastructure.data_module_vnpy.server_pool_manager import ServerPoolManager


def test_quick():
    """快速测试"""
    print("=" * 70)
    print("🧪 快速测试多进程（60个服务器 → 2个进程）")
    print("=" * 70)

    logger = setup_logging(name="QuickTest", level="INFO")

    try:
        # 创建新实例
        manager = ServerPoolManager()

        print(f"\n配置：")
        print(f"  - 服务器数量: {manager.server_count}")
        print(f"  - 多进程模式: {manager.use_multiprocess}")
        print(f"  - 每进程最多: {manager.max_coroutines_per_process}")

        import math

        expected = math.ceil(manager.server_count / manager.max_coroutines_per_process)
        print(f"  - 预计进程数: {expected}")

        print("\n⏳ 开始测速（预计20-30秒）...\n")
        start = time.time()

        success = manager.start()

        elapsed = time.time() - start

        if not success:
            print("\n❌ 测速失败")
            return False

        print(f"\n✅ 测速完成！总耗时: {elapsed:.1f}秒\n")

        # 获取结果
        stats = manager.get_stats()
        print("统计信息：")
        print(f"  - 模式: {stats['mode']}")
        print(f"  - 可用服务器: {stats['available']}/{stats['total']}")

        if stats["available"] > 0:
            best = manager.get_best_server()
            top5 = manager.get_servers(count=5)

            print(f"\n最快服务器: {best[0]}:{best[1]}")
            print("\nTop 5:")
            for i, (ip, port) in enumerate(top5, 1):
                print(f"  {i}. {ip}:{port}")

            print("\n" + "=" * 70)
            print("✅ 测试通过！sorted_servers 已生成")
            print("=" * 70)
            return True
        else:
            print("\n❌ 没有可用服务器")
            return False

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        print(f"\n❌ 异常: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        try:
            manager.stop()
        except:
            pass


if __name__ == "__main__":
    success = test_quick()
    sys.exit(0 if success else 1)
