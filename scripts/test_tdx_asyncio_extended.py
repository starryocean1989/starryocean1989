# -*- coding: utf-8 -*-
"""
测试tdx_asyncio扩展接口（接口2-6）
验证：实时行情、证券列表、除权除息、分时图、指数K线
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


async def test_security_quotes():
    """
    测试1: 实时行情（批量）
    预期性能提升：6144股票从102分钟 → 2.7分钟 (38倍)
    """
    logger.info("=" * 80)
    logger.info("测试1: 实时行情（批量查询）")
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

    # 测试批量查询20只股票
    test_stocks = [
        (1, "600000"),  # 浦发银行
        (0, "000001"),  # 平安银行
        (1, "600519"),  # 贵州茅台
        (0, "000002"),  # 万科A
        (1, "600036"),  # 招商银行
        (0, "000858"),  # 五粮液
        (1, "601318"),  # 中国平安
        (1, "600016"),  # 民生银行
        (0, "000333"),  # 美的集团
        (1, "601166"),  # 兴业银行
        (1, "600030"),  # 中信证券
        (0, "000725"),  # 京东方A
        (1, "601288"),  # 农业银行
        (0, "000063"),  # 中兴通讯
        (1, "601398"),  # 工商银行
        (0, "002415"),  # 海康威视
        (1, "600887"),  # 伊利股份
        (0, "000651"),  # 格力电器
        (1, "600585"),  # 海螺水泥
        (0, "002594"),  # 比亚迪
    ]

    start_time = time.time()

    try:
        logger.info(f"批量查询 {len(test_stocks)} 只股票实时行情...")
        quotes = await client.get_security_quotes(test_stocks)

        elapsed = time.time() - start_time

        if quotes:
            logger.info(f"  ✓ 成功获取 {len(quotes)} 只股票行情")
            logger.info(f"    示例数据:")
            for i, quote in enumerate(quotes[:3]):
                logger.info(
                    f"      {i+1}. {quote['code']} - "
                    f"价格: {quote['price']}, 开盘: {quote['open']}, "
                    f"最高: {quote['high']}, 最低: {quote['low']}, "
                    f"成交量: {quote['vol']}"
                )
            logger.info(f"  耗时: {elapsed:.2f}秒")
            logger.info(f"  平均: {elapsed/len(test_stocks)*1000:.2f}ms/股")
        else:
            logger.warning("未获取到数据")

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)

    await client.close()
    logger.info("")


async def test_security_list():
    """
    测试2: 证券列表（分页）
    预期性能提升：全市场加载从7秒 → 0.2秒 (35倍)
    """
    logger.info("=" * 80)
    logger.info("测试2: 证券列表（分页查询）")
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
    client = await AsyncTdxHq_API.factory(server=server, timeout=10.0, raise_exception=True)

    if not client:
        logger.error("连接失败")
        return

    logger.info("正在分页获取证券列表（上海市场）...")

    start_time = time.time()
    all_stocks = []

    try:
        # 分页获取（每页1000条）
        for start in range(0, 3000, 1000):  # 获取前3000只
            batch = await client.get_security_list(market=1, start=start)
            all_stocks.extend(batch)
            logger.info(f"  已获取 {len(all_stocks)} 只证券...")

        elapsed = time.time() - start_time

        logger.info(f"  ✓ 成功获取 {len(all_stocks)} 只证券")
        logger.info(f"    示例数据:")
        for i, stock in enumerate(all_stocks[:5]):
            logger.info(
                f"      {i+1}. {stock['code']} - {stock['name']} "
                f"(前收: {stock['pre_close']}, 小数位: {stock['decimal_point']})"
            )
        logger.info(f"  耗时: {elapsed:.2f}秒")
        logger.info(f"  速度: {len(all_stocks)/elapsed:.2f} 股/秒")

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)

    await client.close()
    logger.info("")


async def test_xdxr_info():
    """
    测试3: 除权除息
    预期性能提升：6144股票从51分钟 → 1.35分钟 (38倍)
    """
    logger.info("=" * 80)
    logger.info("测试3: 除权除息数据")
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

    # 测试10只股票
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
    total_records = 0

    try:
        logger.info(f"查询 {len(test_stocks)} 只股票的除权除息数据...")

        for market, code, name in test_stocks:
            xdxr = await client.get_xdxr_info(market, code)
            total_records += len(xdxr)
            if xdxr:
                logger.info(f"  ✓ {name}({code}): {len(xdxr)} 条除权除息记录")
                if len(xdxr) > 0:
                    latest = xdxr[0]
                    logger.info(
                        f"      最新: {latest['year']}-{latest['month']:02d}-{latest['day']:02d} "
                        f"{latest['name']}"
                    )

        elapsed = time.time() - start_time

        logger.info(f"  总记录数: {total_records}")
        logger.info(f"  耗时: {elapsed:.2f}秒")
        logger.info(f"  平均: {elapsed/len(test_stocks)*1000:.2f}ms/股")

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)

    await client.close()
    logger.info("")


async def test_minute_time_data():
    """
    测试4: 分时图（当日）
    预期性能提升：50股票从25秒 → 0.7秒 (35倍)
    """
    logger.info("=" * 80)
    logger.info("测试4: 分时图数据（当日）")
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

    test_stocks = [
        (1, "600000", "浦发银行"),
        (0, "000001", "平安银行"),
        (1, "600519", "贵州茅台"),
    ]

    start_time = time.time()

    try:
        logger.info(f"查询 {len(test_stocks)} 只股票的分时图数据...")

        for market, code, name in test_stocks:
            timeseries = await client.get_minute_time_data(market, code)
            if timeseries:
                logger.info(f"  ✓ {name}({code}): {len(timeseries)} 个分钟点")
                if len(timeseries) > 0:
                    logger.info(
                        f"      首个点: 价格={timeseries[0]['price']}, 成交量={timeseries[0]['vol']}"
                    )

        elapsed = time.time() - start_time

        logger.info(f"  耗时: {elapsed:.2f}秒")
        logger.info(f"  平均: {elapsed/len(test_stocks)*1000:.2f}ms/股")

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)

    await client.close()
    logger.info("")


async def test_index_bars():
    """
    测试5: 指数K线
    预期性能提升：10指数从5秒 → 0.13秒 (38倍)
    """
    logger.info("=" * 80)
    logger.info("测试5: 指数K线数据")
    logger.info("=" * 80)

    from backend.infrastructure.tdx_asyncio import AsyncTdxHq_API
    from backend.infrastructure.tdx_asyncio.constants import TDXParams
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

    # 测试主要指数
    test_indices = [
        (1, "000001", "上证指数"),
        (0, "399001", "深证成指"),
        (0, "399006", "创业板指"),
        (1, "000016", "上证50"),
        (1, "000300", "沪深300"),
        (1, "000688", "科创50"),
    ]

    start_time = time.time()

    try:
        logger.info(f"查询 {len(test_indices)} 个指数的日K线...")

        for market, code, name in test_indices:
            klines = await client.get_index_bars(
                category=TDXParams.KLINE_TYPE_DAILY,
                market=market,
                code=code,
                start=0,
                count=10
            )
            if klines:
                logger.info(f"  ✓ {name}({code}): {len(klines)} 条K线")
                if len(klines) > 0:
                    latest = klines[0]
                    logger.info(
                        f"      最新: {latest['datetime']}, "
                        f"收盘={latest['close']}, "
                        f"涨家数={latest['up_count']}, 跌家数={latest['down_count']}"
                    )

        elapsed = time.time() - start_time

        logger.info(f"  耗时: {elapsed:.2f}秒")
        logger.info(f"  平均: {elapsed/len(test_indices)*1000:.2f}ms/指数")

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)

    await client.close()
    logger.info("")


async def test_pool_concurrent():
    """
    测试6: 连接池并发测试（混合接口）
    验证150个协程并发查询，使用38个连接
    """
    logger.info("=" * 80)
    logger.info("测试6: 连接池并发测试（混合接口）")
    logger.info("=" * 80)

    from backend.infrastructure.tdx_asyncio.async_connection_pool import AsyncConnectionPool
    from backend.infrastructure.tdx_asyncio.constants import TDXParams
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

        # 混合查询任务
        tasks = []

        # 20个实时行情查询
        for i in range(20):
            code = f"60{i:04d}"
            tasks.append(("quotes", 1, code))

        # 20个除权除息查询
        for i in range(20):
            code = f"00{i:04d}"
            tasks.append(("xdxr", 0, code))

        # 10个分时图查询
        for i in range(10):
            code = f"60{i:04d}"
            tasks.append(("minute", 1, code))

        logger.info(f"准备执行 {len(tasks)} 个混合任务...")

        async def run_task(task_type, market, code):
            """执行单个任务"""
            try:
                conn = await pool.acquire()
                try:
                    if task_type == "quotes":
                        result = await conn.get_security_quotes([(market, code)])
                    elif task_type == "xdxr":
                        result = await conn.get_xdxr_info(market, code)
                    elif task_type == "minute":
                        result = await conn.get_minute_time_data(market, code)
                    else:
                        result = None

                    return (task_type, len(result) if result else 0, True)
                finally:
                    pool.release()
            except Exception as e:
                logger.debug(f"任务失败 {task_type} {code}: {e}")
                return (task_type, 0, False)

        start_time = time.time()

        # 并发执行所有任务
        results = await asyncio.gather(*[run_task(t, m, c) for t, m, c in tasks])

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
    logger.info(f"\n开始测试 tdx_asyncio 扩展接口")
    logger.info(f"测试时间: {datetime.now()}")
    logger.info(f"测试接口: 实时行情、证券列表、除权除息、分时图、指数K线")
    logger.info("")

    try:
        # 测试1: 实时行情
        await test_security_quotes()
        await asyncio.sleep(1)

        # 测试2: 证券列表
        await test_security_list()
        await asyncio.sleep(1)

        # 测试3: 除权除息
        await test_xdxr_info()
        await asyncio.sleep(1)

        # 测试4: 分时图
        await test_minute_time_data()
        await asyncio.sleep(1)

        # 测试5: 指数K线
        await test_index_bars()
        await asyncio.sleep(1)

        # 测试6: 连接池并发
        await test_pool_concurrent()

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)

    logger.info("")
    logger.info("所有测试完成！")
    logger.info(f"实现率: 6/16 (37.5%)")
    logger.info(f"覆盖场景: K线、实时行情、股票列表、复权、分时、指数")


if __name__ == "__main__":
    asyncio.run(main())

