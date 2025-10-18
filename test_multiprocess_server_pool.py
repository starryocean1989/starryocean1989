# -*- coding: utf-8 -*-
"""
测试多进程服务器池管理器

验证改造后的 ServerPoolManager 多进程架构是否正常工作。
"""

import sys
import time
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from backend.core.base import setup_logging
from backend.infrastructure.data_module_vnpy import server_pool_manager


def test_multiprocess_mode():
    """测试多进程模式"""
    print("=" * 70)
    print("🧪 测试多进程服务器池管理器")
    print("=" * 70)

    # 设置日志
    logger = setup_logging(
        name="TestMultiprocess", level="INFO", log_file="logs/test_multiprocess_server_pool.log"
    )

    try:
        # 1. 检查配置
        print("\n[步骤1] 检查配置...")
        print(f"  - 服务器数量: {server_pool_manager.server_count}")
        print(f"  - 多进程模式: {server_pool_manager.use_multiprocess}")
        print(f"  - 每进程最多协程: {server_pool_manager.max_coroutines_per_process}")

        if server_pool_manager.server_count <= server_pool_manager.max_coroutines_per_process:
            print("  ⚠️  服务器数量未超过单进程阈值，将使用单进程模式")
        else:
            import math

            expected_processes = math.ceil(
                server_pool_manager.server_count / server_pool_manager.max_coroutines_per_process
            )
            print(f"  ✅ 预计启动 {expected_processes} 个进程")

        # 2. 启动服务器池
        print("\n[步骤2] 启动服务器池管理器...")
        start_time = time.time()

        success = server_pool_manager.start()

        elapsed = time.time() - start_time

        if not success:
            print("  ❌ 启动失败！")
            return False

        print(f"  ✅ 启动成功，耗时: {elapsed*1000:.0f}ms")

        # 3. 获取统计信息
        print("\n[步骤3] 获取统计信息...")
        stats = server_pool_manager.get_stats()

        print(f"  - 运行模式: {stats['mode']}")
        print(f"  - 运行状态: {'运行中' if stats['running'] else '未运行'}")
        print(f"  - 测试服务器: {stats['total']}个")
        print(f"  - 可用服务器: {stats['available']}个")
        print(f"  - 不可用服务器: {stats['unavailable']}个")
        print(f"  - 运行时长: {stats['uptime']:.1f}秒")

        # 4. 获取最快服务器
        print("\n[步骤4] 获取最快服务器...")
        try:
            best_server = server_pool_manager.get_best_server()
            print(f"  ✅ 最快服务器: {best_server[0]}:{best_server[1]}")
        except Exception as e:
            print(f"  ❌ 获取最快服务器失败: {e}")
            return False

        # 5. 获取Top 10服务器
        print("\n[步骤5] 获取Top 10服务器...")
        try:
            top10 = server_pool_manager.get_servers(count=10)
            print(f"  ✅ 获取成功，Top 10服务器：")
            for i, (ip, port) in enumerate(top10, 1):
                print(f"     {i}. {ip}:{port}")
        except Exception as e:
            print(f"  ❌ 获取Top 10服务器失败: {e}")
            return False

        # 6. 验证结果
        print("\n[步骤6] 验证结果...")

        if stats["mode"] == "multiprocess":
            print("  ✅ 确认使用多进程模式")
        elif stats["mode"] == "singleprocess":
            print("  ⚠️  使用单进程模式（服务器数量可能未超过阈值）")

        if stats["available"] > 0:
            print(f"  ✅ 找到 {stats['available']} 个可用服务器")
        else:
            print("  ❌ 没有找到可用服务器")
            return False

        print("\n" + "=" * 70)
        print("✅ 多进程服务器池管理器测试通过！")
        print("=" * 70)

        return True

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        print(f"\n❌ 测试失败: {e}")
        return False

    finally:
        # 清理
        print("\n[清理] 停止服务器池管理器...")
        try:
            server_pool_manager.stop()
            print("  ✅ 已停止")
        except Exception as e:
            print(f"  ⚠️  停止时出现异常: {e}")


if __name__ == "__main__":
    success = test_multiprocess_mode()
    sys.exit(0 if success else 1)
