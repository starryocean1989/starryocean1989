# -*- coding: utf-8 -*-
"""
测试tdx_asyncio异步K线下载功能
"""
import asyncio
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def test_single_connection():
    """
    测试1: 单个连接下载K线数据
    """
    logger.info("=" * 80)
    logger.info("测试1: 单个连接下载K线数据")
    logger.info("=" * 80)

    from backend.infrastructure.tdx_asyncio import AsyncTdxHq_API
    from backend.infrastructure.tdx_asyncio.constants import TDXParams
    from backend.infrastructure.data_module_vnpy.data_fetcher import ServerManager

    # 验证并获取可用服务器
    logger.info("正在验证服务器...")
    server_manager = ServerManager()
    server_manager.verify_all_servers_sync(timeout=3, max_workers=20)

    available_servers = server_manager.get_available_servers(count=1)
    if not available_servers:
        logger.error("没有可用的服务器")
        return

    server = available_servers[0]
    logger.info(f"正在连接服务器: {server}")

    client = await AsyncTdxHq_API.factory(
        server=server,
        timeout=10.0,
        heartbeat=False,
        raise_exception=True
    )

    if not client:
        logger.error("连接失败")
        return

    logger.info("连接成功")

    # 下载测试数据
    test_symbols = [
        ("600000", TDXParams.MARKET_SH, "浦发银行"),
        ("000001", TDXParams.MARKET_SZ, "平安银行"),
        ("600519", TDXParams.MARKET_SH, "贵州茅台"),
    ]

    category = TDXParams.KLINE_TYPE_DAILY  # 日K线

    start_time = time.time()

    for code, market, name in test_symbols:
        try:
            logger.info(f"下载 {name}({code}) 日K线...")

            klines = await client.get_security_bars(
                category=category,
                market=market,
                code=code,
                start=0,
                count=10
            )

            if klines:
                logger.info(f"  ✓ 成功获取 {len(klines)} 条K线")
                logger.info(f"    最新: {klines[0]['datetime']}, 收盘价: {klines[0]['close']}")
            else:
                logger.warning(f"  ✗ 未获取到数据")

        except Exception as e:
            logger.error(f"  ✗ 下载失败: {e}")

    elapsed = time.time() - start_time
    logger.info(f"单连接测试完成，耗时: {elapsed:.2f}秒")

    await client.close()


async def test_connection_pool():
    """
    测试2: 连接池并发下载
    """
    logger.info("=" * 80)
    logger.info("测试2: 连接池并发下载（38个连接）")
    logger.info("=" * 80)

    from backend.infrastructure.tdx_asyncio.async_connection_pool import AsyncConnectionPool
    from backend.infrastructure.tdx_asyncio.constants import TDXParams
    from backend.infrastructure.data_module_vnpy.data_fetcher import ServerManager

    # 验证并获取可用服务器
    logger.info("正在验证服务器...")
    server_manager = ServerManager()
    server_manager.verify_all_servers_sync(timeout=3, max_workers=20)

    available_servers = server_manager.get_available_servers()
    if not available_servers:
        logger.error("没有可用的服务器")
        return

    logger.info(f"找到 {len(available_servers)} 个可用服务器")

    # 创建连接池（使用可用服务器）
    pool = AsyncConnectionPool(servers=available_servers, max_connections=min(38, len(available_servers)), timeout=10.0)

    async with pool:
        logger.info(f"连接池已就绪: {pool.max_connections}个连接")

        # 生成测试任务
        test_symbols = [
            ("600000", TDXParams.MARKET_SH, "浦发银行"),
            ("000001", TDXParams.MARKET_SZ, "平安银行"),
            ("600519", TDXParams.MARKET_SH, "贵州茅台"),
            ("000002", TDXParams.MARKET_SZ, "万科A"),
            ("600036", TDXParams.MARKET_SH, "招商银行"),
            ("000858", TDXParams.MARKET_SZ, "五粮液"),
            ("601318", TDXParams.MARKET_SH, "中国平安"),
            ("600016", TDXParams.MARKET_SH, "民生银行"),
            ("000333", TDXParams.MARKET_SZ, "美的集团"),
            ("601166", TDXParams.MARKET_SH, "兴业银行"),
        ] * 5  # 50个任务

        async def download_task(code, market, name):
            """单个下载任务"""
            try:
                async with pool:
                    conn = await pool.acquire()
                    klines = await conn.get_security_bars(
                        category=TDXParams.KLINE_TYPE_DAILY,
                        market=market,
                        code=code,
                        start=0,
                        count=100
                    )
                    pool.release()

                    if klines:
                        return (name, code, len(klines), True)
                    else:
                        return (name, code, 0, False)

            except Exception as e:
                logger.error(f"下载 {name}({code}) 失败: {e}")
                return (name, code, 0, False)

        # 并发执行所有任务
        start_time = time.time()

        tasks = [download_task(code, market, name) for code, market, name in test_symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = time.time() - start_time

        # 统计结果
        success_count = sum(1 for r in results if isinstance(r, tuple) and r[3])
        total_klines = sum(r[2] for r in results if isinstance(r, tuple))

        logger.info("=" * 80)
        logger.info(f"并发测试完成:")
        logger.info(f"  总任务数: {len(test_symbols)}")
        logger.info(f"  成功: {success_count}")
        logger.info(f"  失败: {len(test_symbols) - success_count}")
        logger.info(f"  总K线数: {total_klines}")
        logger.info(f"  耗时: {elapsed:.2f}秒")
        logger.info(f"  速度: {len(test_symbols) / elapsed:.2f} 任务/秒")
        logger.info("=" * 80)


async def test_massive_concurrent():
    """
    测试3: 大规模并发（150个协程竞争38个连接）
    """
    logger.info("=" * 80)
    logger.info("测试3: 大规模并发（150个协程竞争38个连接）")
    logger.info("=" * 80)

    from backend.infrastructure.tdx_asyncio.async_connection_pool import AsyncConnectionPool
    from backend.infrastructure.tdx_asyncio.constants import TDXParams
    from backend.infrastructure.data_module_vnpy.data_fetcher import ServerManager

    # 验证并获取可用服务器
    logger.info("正在验证服务器...")
    server_manager = ServerManager()
    server_manager.verify_all_servers_sync(timeout=3, max_workers=20)

    available_servers = server_manager.get_available_servers()
    if not available_servers:
        logger.error("没有可用的服务器")
        return

    logger.info(f"找到 {len(available_servers)} 个可用服务器")

    # 创建连接池
    pool = AsyncConnectionPool(servers=available_servers, max_connections=min(38, len(available_servers)), timeout=10.0)

    async with pool:
        logger.info(f"连接池已就绪: {pool.max_connections}个连接")

        # 生成150个任务
        test_symbols = [
            ("600000", TDXParams.MARKET_SH),
            ("000001", TDXParams.MARKET_SZ),
            ("600519", TDXParams.MARKET_SH),
        ] * 50  # 150个任务

        async def download_task(code, market):
            """单个下载任务"""
            try:
                conn = await pool.acquire()
                try:
                    klines = await conn.get_security_bars(
                        category=TDXParams.KLINE_TYPE_DAILY,
                        market=market,
                        code=code,
                        start=0,
                        count=100
                    )
                    return len(klines) if klines else 0
                finally:
                    pool.release()

            except Exception as e:
                logger.debug(f"下载 {code} 失败: {e}")
                return 0

        # 并发执行
        start_time = time.time()

        tasks = [download_task(code, market) for code, market in test_symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        elapsed = time.time() - start_time

        # 统计
        success_count = sum(1 for r in results if isinstance(r, int) and r > 0)
        total_klines = sum(r for r in results if isinstance(r, int))

        logger.info("=" * 80)
        logger.info(f"大规模并发测试完成:")
        logger.info(f"  总任务数: {len(test_symbols)}")
        logger.info(f"  成功: {success_count}")
        logger.info(f"  失败: {len(test_symbols) - success_count}")
        logger.info(f"  总K线数: {total_klines}")
        logger.info(f"  耗时: {elapsed:.2f}秒")
        logger.info(f"  速度: {len(test_symbols) / elapsed:.2f} 任务/秒")
        logger.info(f"  平均每任务: {elapsed / len(test_symbols) * 1000:.2f}ms")
        logger.info("=" * 80)


async def main():
    """
    主测试函数
    """
    logger.info(f"开始测试 tdx_asyncio 异步库")
    logger.info(f"测试时间: {datetime.now()}")
    logger.info("")

    try:
        # 测试1: 单连接
        await test_single_connection()
        await asyncio.sleep(1)

        # 测试2: 连接池
        await test_connection_pool()
        await asyncio.sleep(1)

        # 测试3: 大规模并发
        await test_massive_concurrent()

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)

    logger.info("")
    logger.info("所有测试完成")


if __name__ == "__main__":
    asyncio.run(main())

