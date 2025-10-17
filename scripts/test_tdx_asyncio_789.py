# -*- coding: utf-8 -*-
"""
测试tdx_asyncio接口7-9（历史分时、逐笔成交）
验证：历史分时图、当日逐笔成交、历史逐笔成交
"""
import asyncio
import logging
import sys
import time
from datetime import datetime, timedelta
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


async def test_history_minute_time_data():
    """
    测试7: 历史分时图
    预期性能提升：100只股票×30天历史 = 同步125分钟 → 异步3分钟 (40倍)
    """
    logger.info("=" * 80)
    logger.info("测试7: 历史分时图数据")
    logger.info("=" * 80)

    from backend.infrastructure.tdx_asyncio import AsyncTdxHq_API
    from backend.infrastructure.data_module_vnpy.data_fetcher import ServerManager

    # 获取可用服务器
    logger.info("正在验证服务器...")
    server_manager = ServerManager()
    server_manager.verify_all_servers_sync(timeout=3, max_workers=20)

    available_servers = server_manager.get_available_servers(count=1)
    if not available_servers:
        logger.error("没有可用的服务器")
        return

    server = available_servers[0]
    logger.info(f"正在连接服务器: {server}")

    # 连接客户端
    client = await AsyncTdxHq_API.factory(server=server, timeout=10.0, raise_exception=True)

    if not client:
        logger.error("连接失败")
        return

    logger.info("连接成功")

    # 测试5只股票最近5天的历史分时图
    test_stocks = [
        (1, "600000", "浦发银行"),
        (0, "000001", "平安银行"),
        (1, "600519", "贵州茅台"),
        (0, "000002", "万科A"),
        (1, "600036", "招商银行"),
    ]

    # 计算最近5天的日期
    today = datetime.now()
    test_dates = [(today - timedelta(days=i)).strftime('%Y%m%d') for i in range(5)]

    start_time = time.time()
    total_points = 0

    try:
        logger.info(f"查询 {len(test_stocks)} 只股票 {len(test_dates)} 天的历史分时图...")

        for market, code, name in test_stocks:
            for date in test_dates:
                timeseries = await client.get_history_minute_time_data(market, code, int(date))

                if timeseries:
                    logger.info(f"  ✓ {name}({code}) {date}: {len(timeseries)} 个分钟点")
                    total_points += len(timeseries)
                    if len(timeseries) > 0:
                        logger.info(
                            f"      示例: 价格={timeseries[0]['price']}, 成交量={timeseries[0]['vol']}"
                        )

        elapsed = time.time() - start_time

        logger.info(f"  总分钟点点数: {total_points}")
        logger.info(f"  耗时: {elapsed:.2f}秒")
        logger.info(f"  平均: {elapsed/(len(test_stocks)*len(test_dates))*1000:.2f}ms/只股票/天")

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)

    await client.close()
    logger.info("")


async def test_transaction_data():
    """
    测试8: 当日逐笔成交
    预期性能提升：50只股票实时扫描 = 同步63秒 → 异步1.7秒 (38倍)
    """
    logger.info("=" * 80)
    logger.info("测试8: 当日逐笔成交数据")
    logger.info("=" * 80)

    from backend.infrastructure.tdx_asyncio import AsyncTdxHq_API
    from backend.infrastructure.data_module_vnpy.data_fetcher import ServerManager

    server_manager = ServerManager()
    server_manager.verify_all_servers_sync(timeout=3, max_workers=20)

    available_servers = server_manager.get_available_servers(count=1)
    if not available_servers:
        logger.error("没有可用的服务器")
        return

    server = available_servers[0]
    client = await AsyncTdxHq_API.factory(server=server, timeout=10.0, raise_exception=True)

    if not client:
        logger.error("连接失败")
        return

    # 测试10只股票的当日逐笔成交（每只2000笔）
    test_stocks = [
        (1, "600000", "浦发银行"),
        (0, "000001", "平安银行"),
        (1, "600519", "贵州茅台"),
        (0, "000002", "万科A"),
        (1, "600036", "招商银行"),
        (0, "000858", "五粮液"),
        (1, "601318", "中国平安"),
        (1, "600016", "民生银行"),
        (0, "000333", "美的集团"),
        (1, "601166", "兴业银行"),
    ]

    start_time = time.time()
    total_transactions = 0

    try:
        logger.info(f"查询 {len(test_stocks)} 只股票的当日逐笔成交...")

        for market, code, name in test_stocks:
            transactions = await client.get_transaction_data(market, code, 0, 2000)
            total_transactions += len(transactions) if transactions else 0

            if transactions:
                logger.info(f"  ✓ {name}({code}): {len(transactions)} 笔成交")
                if len(transactions) > 0:
                    latest = transactions[0]
                    logger.info(
                        f"      最新成交: {latest['time']}, 价格={latest['price']}, "
                        f"成交量={latest['vol']}, 买卖={latest['buyorsell']}"
                    )

        elapsed = time.time() - start_time

        logger.info(f"  总成交笔数: {total_transactions}")
        logger.info(f"  耗时: {elapsed:.2f}秒")
        logger.info(f"  平均: {elapsed/len(test_stocks)*1000:.2f}ms/股")

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)

    await client.close()
    logger.info("")


async def test_history_transaction_data():
    """
    测试9: 历史逐笔成交
    预期性能提升：50只股票×10天历史 = 同步105分钟 → 异步2.6分钟 (40倍)
    """
    logger.info("=" * 80)
    logger.info("测试9: 历史逐笔成交数据")
    logger.info("=" * 80)

    from backend.infrastructure.tdx_asyncio import AsyncTdxHq_API
    from backend.infrastructure.data_module_vnpy.data_fetcher import ServerManager

    server_manager = ServerManager()
    server_manager.verify_all_servers_sync(timeout=3, max_workers=20)

    available_servers = server_manager.get_available_servers(count=1)
    if not available_servers:
        logger.error("没有可用的服务器")
        return

    server = available_servers[0]
    client = await AsyncTdxHq_API.factory(server=server, timeout=10.0, raise_exception=True)

    if not client:
        logger.error("连接失败")
        return

    # 测试5只股票最近3天的历史逐笔成交
    test_stocks = [
        (1, "600000", "浦发银行"),
        (0, "000001", "平安银行"),
        (1, "600519", "贵州茅台"),
        (0, "000002", "万科A"),
        (1, "600036", "招商银行"),
    ]

    # 计算最近3天的日期
    today = datetime.now()
    test_dates = [(today - timedelta(days=i)).strftime('%Y%m%d') for i in range(3)]

    start_time = time.time()
    total_transactions = 0

    try:
        logger.info(f"查询 {len(test_stocks)} 只股票 {len(test_dates)} 天的历史逐笔成交...")

        for market, code, name in test_stocks:
            for date in test_dates:
                transactions = await client.get_history_transaction_data(market, code, 0, 2000, int(date))
                total_transactions += len(transactions) if transactions else 0

                if transactions:
                    logger.info(f"  ✓ {name}({code}) {date}: {len(transactions)} 笔历史成交")
                    if len(transactions) > 0:
                        latest = transactions[0]
                        logger.info(
                            f"      示例: {latest['time']}, 价格={latest['price']}, "
                            f"成交量={latest['vol']}, 买卖={latest['buyorsell']}"
                        )

        elapsed = time.time() - start_time

        logger.info(f"  总历史成交笔数: {total_transactions}")
        logger.info(f"  耗时: {elapsed:.2f}秒")
        logger.info(f"  平均: {elapsed/(len(test_stocks)*len(test_dates))*1000:.2f}ms/只股票/天")

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)

    await client.close()
    logger.info("")


async def test_pool_concurrent_789():
    """
    测试: 连接池并发测试（接口7-9混合）
    验证50个协程并发查询历史分时+逐笔成交，使用38个连接
    """
    logger.info("=" * 80)
    logger.info("测试: 连接池并发测试（接口7-9混合）")
    logger.info("=" * 80)

    from backend.infrastructure.tdx_asyncio.async_connection_pool import AsyncConnectionPool
    from backend.infrastructure.tdx_asyncio import AsyncTdxHq_API
    from backend.infrastructure.data_module_vnpy.data_fetcher import ServerManager

    # 获取可用服务器
    logger.info("正在验证服务器...")
    server_manager = ServerManager()
    server_manager.verify_all_servers_sync(timeout=3, max_workers=20)

    available_servers = server_manager.get_available_servers()
    if not available_servers:
        logger.error("没有可用的服务器")
        return

    logger.info(f"找到 {len(available_servers)} 个可用服务器")

    # 创建连接池
    pool = AsyncConnectionPool(
        servers=available_servers,
        max_connections=min(38, len(available_servers)),
        timeout=10.0
    )

    async with pool:
        logger.info(f"连接池已就绪: {pool.max_connections}个连接")

        # 混合查询任务：历史分时 + 逐笔成交
        tasks = []

        # 20个历史分时图查询
        today = datetime.now()
        for i in range(20):
            code = f"60{i:04d}"
            date = (today - timedelta(days=i % 5)).strftime('%Y%m%d')
            tasks.append(("history_minute", 1, code, int(date)))

        # 20个当日逐笔成交查询
        for i in range(20):
            code = f"00{i:04d}"
            tasks.append(("transaction", 0, code, 0, 2000))

        # 10个历史逐笔成交查询
        for i in range(10):
            code = f"60{i:04d}"
            date = (today - timedelta(days=i % 3)).strftime('%Y%m%d')
            tasks.append(("history_transaction", 1, code, 0, 2000, int(date)))

        logger.info(f"准备执行 {len(tasks)} 个混合任务...")

        async def run_task(task_type, *args):
            """执行单个任务"""
            try:
                conn = await pool.acquire()
                try:
                    if task_type == "history_minute":
                        result = await conn.get_history_minute_time_data(args[0], args[1], args[2])
                    elif task_type == "transaction":
                        result = await conn.get_transaction_data(args[0], args[1], args[2], args[3])
                    elif task_type == "history_transaction":
                        result = await conn.get_history_transaction_data(args[0], args[1], args[2], args[3], args[4])
                    else:
                        result = None

                    return (task_type, len(result) if result else 0, True)
                finally:
                    await pool.release(conn)
            except Exception as e:
                logger.debug(f"任务失败 {task_type} {args}: {e}")
                return (task_type, 0, False)

        start_time = time.time()

        # 并发执行所有任务
        results = await asyncio.gather(*[run_task(t, *a) for t, *a in tasks])

        elapsed = time.time() - start_time

        # 统计结果
        success_count = sum(1 for _, _, success in results if success)
        total_records = sum(count for _, count, _ in results)

        logger.info("=" * 80)
        logger.info(f"并发测试完成:")
        logger.info(f"  总任务数: {len(tasks)}")
        logger.info(f"  成功: {success_count}")
        logger.info(f"  失败: {len(tasks) - success_count}")
        logger.info(f"  总数据条数: {total_records}")
        logger.info(f"  耗时: {elapsed:.2f}秒")
        logger.info(f"  速度: {len(tasks)/elapsed:.2f} 任务/秒")
        logger.info(f"  平均: {elapsed/len(tasks)*1000:.2f}ms/任务")
        logger.info("=" * 80)

    logger.info("")


async def main():
    """
    主测试函数
    """
    logger.info(f"\n开始测试 tdx_asyncio 接口7-9")
    logger.info(f"测试时间: {datetime.now()}")
    logger.info(f"测试接口: 历史分时图、当日逐笔成交、历史逐笔成交")
    logger.info("")

    try:
        # 测试7: 历史分时图
        await test_history_minute_time_data()
        await asyncio.sleep(1)

        # 测试8: 当日逐笔成交
        await test_transaction_data()
        await asyncio.sleep(1)

        # 测试9: 历史逐笔成交
        await test_history_transaction_data()
        await asyncio.sleep(1)

        # 连接池并发测试
        await test_pool_concurrent_789()

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)

    logger.info("")
    logger.info("所有测试完成！")
    logger.info(f"实现率: 9/16 (56.25%)")
    logger.info(f"覆盖场景: K线、实时行情、股票列表、复权、分时(当日+历史)、逐笔成交(当日+历史)、指数")


if __name__ == "__main__":
    asyncio.run(main())

