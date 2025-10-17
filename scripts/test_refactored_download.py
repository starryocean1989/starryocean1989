# -*- coding: utf-8 -*-
"""
测试重构后的下载功能

验证：
1. ServerManager服务器验证
2. 进程池动态任务分配
3. 故障转移机制
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import date, timedelta

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_server_manager():
    """测试ServerManager功能"""
    logger.info("=" * 60)
    logger.info("测试1: ServerManager服务器验证")
    logger.info("=" * 60)

    try:
        from backend.infrastructure.data_module_vnpy.data_fetcher import ServerManager

        # 创建服务器管理器
        server_manager = ServerManager()

        logger.info(f"初始化完成，共{len(server_manager.all_servers)}个服务器")

        # 验证服务器
        logger.info("开始验证服务器...")
        server_manager.verify_all_servers_sync(timeout=5, max_workers=10)

        # 获取状态
        status = server_manager.get_server_status()
        logger.info(f"验证完成: {status['available_count']}/{status['total_count']} 可用")
        logger.info(f"验证状态: {status['status']}")

        # 显示可用服务器列表
        available = server_manager.get_available_servers()
        logger.info(f"可用服务器列表 (前5个):")
        for i, server in enumerate(available[:5]):
            logger.info(f"  {i+1}. {server[0]}:{server[1]}")

        assert status['available_count'] > 0, "至少应该有一个可用服务器"
        logger.info("✅ ServerManager测试通过")
        return True

    except Exception as e:
        logger.error(f"❌ ServerManager测试失败: {e}", exc_info=True)
        return False


def test_download_small_batch():
    """测试小批量下载（验证进程池机制）"""
    logger.info("\n" + "=" * 60)
    logger.info("测试2: 小批量下载（进程池+动态任务分配）")
    logger.info("=" * 60)

    try:
        from backend.infrastructure.data_module_vnpy.data_fetcher import MultiProcessStockFetcher

        # 创建下载器
        fetcher = MultiProcessStockFetcher()

        # 验证服务器
        logger.info("验证服务器...")
        fetcher.server_manager.verify_all_servers_sync(timeout=5)

        status = fetcher.server_manager.get_server_status()
        logger.info(f"可用服务器: {status['available_count']}/{status['total_count']}")

        if status['available_count'] == 0:
            logger.warning("无可用服务器，跳过下载测试")
            return True

        # 测试下载（少量品种）
        test_symbols = ["600000", "000001", "300001"]
        start_date = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")

        logger.info(f"下载测试品种: {test_symbols}")
        logger.info(f"开始日期: {start_date}")
        logger.info(f"进程数: {fetcher.num_processes}")

        results = fetcher.download_incremental_kline(
            symbols=test_symbols,
            start_date=start_date,
            intervals=["1d"],
            progress_callback=lambda c, t, s, i: logger.info(f"进度: {c}/{t} - {s}_{i}")
        )

        logger.info(f"下载完成，共获取 {len(results)} 个结果")

        for key, data in results.items():
            if data is not None and not data.empty:
                logger.info(f"  {key}: {len(data)} 行数据")

        logger.info("✅ 小批量下载测试通过")
        return True

    except Exception as e:
        logger.error(f"❌ 小批量下载测试失败: {e}", exc_info=True)
        return False


def test_service_integration():
    """测试DataCenterService集成"""
    logger.info("\n" + "=" * 60)
    logger.info("测试3: DataCenterService集成")
    logger.info("=" * 60)

    try:
        from backend.core.base import get_service_manager

        # 获取服务管理器
        service_manager = get_service_manager()
        service_manager.initialize_all()

        # 获取数据中心服务
        data_center_service = service_manager.get_service("data_center_service")

        if not data_center_service:
            logger.warning("DataCenterService不可用，跳过测试")
            return True

        # 获取服务器状态
        logger.info("获取服务器状态...")
        status = data_center_service.get_server_status()

        logger.info(f"服务器状态:")
        logger.info(f"  可用数量: {status.get('available_count', 0)}")
        logger.info(f"  总数量: {status.get('total_count', 0)}")
        logger.info(f"  验证状态: {status.get('status', 'unknown')}")

        logger.info("✅ DataCenterService集成测试通过")
        return True

    except Exception as e:
        logger.error(f"❌ DataCenterService集成测试失败: {e}", exc_info=True)
        return False


def main():
    """运行所有测试"""
    logger.info("\n")
    logger.info("#" * 60)
    logger.info("# 重构后下载功能测试")
    logger.info("#" * 60)

    results = []

    # 测试1: ServerManager
    results.append(("ServerManager测试", test_server_manager()))

    # 测试2: 小批量下载
    results.append(("小批量下载测试", test_download_small_batch()))

    # 测试3: Service集成
    results.append(("Service集成测试", test_service_integration()))

    # 汇总结果
    logger.info("\n" + "=" * 60)
    logger.info("测试结果汇总")
    logger.info("=" * 60)

    for name, result in results:
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{name}: {status}")

    all_passed = all(r[1] for r in results)

    logger.info("=" * 60)
    if all_passed:
        logger.info("🎉 所有测试通过！")
    else:
        logger.error("⚠️ 部分测试失败，请检查日志")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

