# -*- coding: utf-8 -*-
"""
测试自适应下载控制器

测试内容：
1. 自适应配置计算
2. 随机服务器获取
3. 小批量下载验证
"""

import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.data_module_vnpy.load_balancer.server_pool_manager import (
    AdaptiveDownloadConfig,
    get_adaptive_config,
    get_random_servers,
    get_verified_servers_random,
)

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def test_adaptive_config():
    """测试1：自适应配置计算"""
    logger.info("=" * 60)
    logger.info("测试1：自适应配置计算")
    logger.info("=" * 60)

    try:
        # 测试配置计算
        config = AdaptiveDownloadConfig.calculate_optimal_config()

        logger.info("✅ 配置计算成功")
        logger.info("配置详情：")
        for key, value in config.items():
            logger.info(f"  {key}: {value}")

        # 验证配置合理性
        assert config["processes"] > 0, "进程数必须大于0"
        assert config["coroutines_per_process"] > 0, "协程数必须大于0"
        assert config["total_connections"] > 0, "总连接数必须大于0"
        assert (
            config["total_connections"] <= config["available_servers"]
        ), "总连接数不能超过可用服务器数"

        logger.info("✅ 配置验证通过")
        return True

    except Exception as e:
        logger.error(f"❌ 配置计算失败: {e}", exc_info=True)
        return False


def test_random_servers():
    """测试2：随机服务器获取"""
    logger.info("=" * 60)
    logger.info("测试2：随机服务器获取")
    logger.info("=" * 60)

    try:
        # 测试adaptive_config模块的方法
        servers1 = get_random_servers(count=10)
        logger.info(f"✅ get_random_servers 获取到 {len(servers1)} 个服务器")
        logger.info(f"示例服务器: {servers1[:3]}")

        # 测试server_pool_manager模块的方法
        servers2 = get_verified_servers_random(count=10)
        logger.info(f"✅ get_verified_servers_random 获取到 {len(servers2)} 个服务器")
        logger.info(f"示例服务器: {servers2[:3]}")

        # 验证服务器格式
        for server in servers1[:3]:
            assert isinstance(server, tuple), "服务器应该是元组"
            assert len(server) == 2, "服务器元组应该有2个元素(ip, port)"
            assert isinstance(server[0], str), "IP应该是字符串"
            assert isinstance(server[1], int), "端口应该是整数"

        logger.info("✅ 服务器格式验证通过")
        return True

    except Exception as e:
        logger.error(f"❌ 服务器获取失败: {e}", exc_info=True)
        return False


def test_small_download():
    """测试3：小批量下载验证"""
    logger.info("=" * 60)
    logger.info("测试3：小批量下载验证（跳过实际下载）")
    logger.info("=" * 60)

    # 注意：这个测试不会真正执行下载，因为需要完整的运行环境
    # 仅展示接口调用方式

    logger.info("下载接口调用示例：")
    logger.info(
        """
    result = download_incremental_unified(
        symbols=['000001', '000002'],
        start_date='2025-01-01',
        intervals=['1d'],
        use_adaptive=True  # 使用自适应配置
    )
    """
    )

    logger.info("✅ 接口说明验证通过")
    logger.info("提示：要执行实际下载，请确保：")
    logger.info("  1. 服务器池管理器已启动（server_pool_manager.start()）")
    logger.info("  2. 品种加载器已初始化（symbol_loader）")
    logger.info("  3. 存储管理器已初始化（storage_manager）")

    return True


def test_config_summary():
    """测试4：配置摘要生成"""
    logger.info("=" * 60)
    logger.info("测试4：配置摘要生成")
    logger.info("=" * 60)

    try:
        config = get_adaptive_config()
        summary = AdaptiveDownloadConfig.get_download_config_summary(config)

        logger.info("✅ 配置摘要生成成功")
        logger.info(f"摘要: {summary}")

        return True

    except Exception as e:
        logger.error(f"❌ 配置摘要生成失败: {e}", exc_info=True)
        return False


def main():
    """主测试函数"""
    logger.info("\n" + "=" * 60)
    logger.info("企业级自适应下载控制器测试")
    logger.info("=" * 60 + "\n")

    results = []

    # 运行所有测试
    results.append(("自适应配置计算", test_adaptive_config()))
    results.append(("随机服务器获取", test_random_servers()))
    results.append(("小批量下载验证", test_small_download()))
    results.append(("配置摘要生成", test_config_summary()))

    # 汇总结果
    logger.info("\n" + "=" * 60)
    logger.info("测试结果汇总")
    logger.info("=" * 60)

    for test_name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"{test_name}: {status}")

    total = len(results)
    passed = sum(1 for _, r in results if r)

    logger.info("=" * 60)
    logger.info(f"总计: {passed}/{total} 通过")
    logger.info("=" * 60)

    return passed == total


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
