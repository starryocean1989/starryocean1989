# -*- coding: utf-8 -*-
"""
测试财务信息接口
验证：财务数据查询功能和性能
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


async def test_single_finance():
    """
    测试单个股票财务信息查询
    """
    logger.info("=" * 80)
    logger.info("测试1: 单个股票财务信息查询")
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

    # 测试贵州茅台
    market, code, name = 1, "600519", "贵州茅台"

    logger.info(f"\n查询 {name}({code}) 财务信息...")
    start_time = time.time()

    info = await client.get_finance_info(market, code)

    elapsed = time.time() - start_time

    logger.info(f"\n{name}({code}) 财务数据:")
    logger.info(f"  ├─ 基本信息")
    logger.info(f"  │  ├─ 市场: {info['market']}")
    logger.info(f"  │  ├─ 代码: {info['code']}")
    logger.info(f"  │  ├─ 行业: {info['industry']}")
    logger.info(f"  │  ├─ 省份: {info['province']}")
    logger.info(f"  │  ├─ 上市日期: {info['ipo_date']}")
    logger.info(f"  │  └─ 更新日期: {info['updated_date']}")
    logger.info(f"  │")
    logger.info(f"  ├─ 股本结构")
    logger.info(f"  │  ├─ 总股本: {info['zongguben']/10000:.2f} 亿股")
    logger.info(f"  │  ├─ 流通股本: {info['liutongguben']/10000:.2f} 亿股")
    logger.info(f"  │  ├─ 流通比例: {info['liutongguben']/info['zongguben']*100:.2f}%")
    logger.info(f"  │  └─ 股东人数: {info['gudongrenshu']:.0f} 人")
    logger.info(f"  │")
    logger.info(f"  ├─ 资产负债")
    logger.info(f"  │  ├─ 总资产: {info['zongzichan']/10000:.2f} 亿元")
    logger.info(f"  │  ├─ 净资产: {info['jingzichan']/10000:.2f} 亿元")
    logger.info(f"  │  ├─ 流动资产: {info['liudongzichan']/10000:.2f} 亿元")
    logger.info(f"  │  ├─ 固定资产: {info['gudingzichan']/10000:.2f} 亿元")
    logger.info(f"  │  ├─ 流动负债: {info['liudongfuzhai']/10000:.2f} 亿元")
    logger.info(f"  │  └─ 长期负债: {info['changqifuzhai']/10000:.2f} 亿元")
    logger.info(f"  │")
    logger.info(f"  ├─ 经营成果")
    logger.info(f"  │  ├─ 主营收入: {info['zhuyingshouru']/10000:.2f} 亿元")
    logger.info(f"  │  ├─ 主营利润: {info['zhuyinglirun']/10000:.2f} 亿元")
    logger.info(f"  │  ├─ 营业利润: {info['yingyelirun']/10000:.2f} 亿元")
    logger.info(f"  │  └─ 净利润: {info['jinglirun']/10000:.2f} 亿元")
    logger.info(f"  │")
    logger.info(f"  ├─ 现金流量")
    logger.info(f"  │  ├─ 经营现金流: {info['jingyingxianjinliu']/10000:.2f} 亿元")
    logger.info(f"  │  └─ 总现金流: {info['zongxianjinliu']/10000:.2f} 亿元")
    logger.info(f"  │")
    logger.info(f"  └─ 财务指标")
    logger.info(f"     └─ 每股净资产: {info['meigujingzichan']:.2f} 元")

    logger.info(f"\n查询耗时: {elapsed*1000:.2f}ms")
    logger.info("")

    await client.close()


async def test_batch_finance():
    """
    测试批量财务信息查询
    预期性能：100只股票 = 同步125秒 → 异步3.8秒 (33倍提升)
    """
    logger.info("=" * 80)
    logger.info("测试2: 批量财务信息查询")
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

    # 测试20只主流股票
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
        (1, "600030", "中信证券"),
        (0, "000725", "京东方A"),
        (1, "601288", "农业银行"),
        (1, "601398", "工商银行"),
        (1, "601939", "建设银行"),
        (0, "000651", "格力电器"),
        (1, "600104", "上汽集团"),
        (0, "002594", "比亚迪"),
        (1, "601988", "中国银行"),
        (1, "600887", "伊利股份"),
    ]

    start_time = time.time()
    success_count = 0
    total_assets = 0
    total_profit = 0

    logger.info(f"开始批量查询 {len(test_stocks)} 只股票的财务信息...\n")

    for market, code, name in test_stocks:
        try:
            info = await client.get_finance_info(market, code)
            success_count += 1
            
            # 累计统计
            total_assets += info['zongzichan'] / 10000
            total_profit += info['jinglirun'] / 10000

            logger.info(
                f"  ✓ {name:8s}({code}) - "
                f"资产:{info['zongzichan']/10000:8.2f}亿 "
                f"利润:{info['jinglirun']/10000:7.2f}亿 "
                f"ROE:{info['jinglirun']/info['jingzichan']*100:5.2f}%"
            )
        except Exception as e:
            logger.error(f"  ✗ {name}({code}) 查询失败: {e}")

    elapsed = time.time() - start_time

    logger.info("")
    logger.info("=" * 80)
    logger.info(f"批量查询完成:")
    logger.info(f"  成功查询: {success_count}/{len(test_stocks)}")
    logger.info(f"  总资产: {total_assets:.2f} 亿元")
    logger.info(f"  总利润: {total_profit:.2f} 亿元")
    logger.info(f"  平均ROE: {total_profit/total_assets*100:.2f}%")
    logger.info(f"  耗时: {elapsed:.2f}秒")
    logger.info(f"  速度: {len(test_stocks)/elapsed:.2f} 查询/秒")
    logger.info(f"  平均: {elapsed/len(test_stocks)*1000:.2f}ms/查询")
    logger.info("=" * 80)

    await client.close()
    logger.info("")


async def test_pool_concurrent_finance():
    """
    测试连接池并发财务查询
    验证50个协程并发查询，使用38个连接
    """
    logger.info("=" * 80)
    logger.info("测试3: 连接池并发财务查询")
    logger.info("=" * 80)

    from backend.infrastructure.tdx_asyncio.async_connection_pool import AsyncConnectionPool
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

        # 准备50只股票查询任务
        tasks = []
        for i in range(50):
            if i % 2 == 0:
                market = 1
                code = f"60{i:04d}"
            else:
                market = 0
                code = f"00{i:04d}"
            tasks.append((market, code))

        logger.info(f"准备执行 {len(tasks)} 个并发财务查询...\n")

        async def query_finance(market, code):
            """执行单个财务查询"""
            try:
                conn = await pool.acquire()
                try:
                    info = await conn.get_finance_info(market, code)
                    return (code, info, True)
                finally:
                    await pool.release(conn)
            except Exception as e:
                logger.debug(f"查询失败 {code}: {e}")
                return (code, None, False)

        start_time = time.time()

        # 并发执行所有查询
        results = await asyncio.gather(*[query_finance(m, c) for m, c in tasks])

        elapsed = time.time() - start_time

        # 统计结果
        success_count = sum(1 for _, _, success in results if success)
        total_assets = sum(info['zongzichan']/10000 for _, info, success in results if success and info)
        total_profit = sum(info['jinglirun']/10000 for _, info, success in results if success and info)

        logger.info("=" * 80)
        logger.info(f"并发查询完成:")
        logger.info(f"  总任务数: {len(tasks)}")
        logger.info(f"  成功: {success_count}")
        logger.info(f"  失败: {len(tasks) - success_count}")
        logger.info(f"  总资产: {total_assets:.2f} 亿元")
        logger.info(f"  总利润: {total_profit:.2f} 亿元")
        logger.info(f"  耗时: {elapsed:.2f}秒")
        logger.info(f"  速度: {len(tasks)/elapsed:.2f} 查询/秒")
        logger.info(f"  平均: {elapsed/len(tasks)*1000:.2f}ms/查询")
        logger.info("=" * 80)

    logger.info("")


async def main():
    """
    主测试函数
    """
    logger.info(f"\n开始测试 tdx_asyncio 财务信息接口")
    logger.info(f"测试时间: {datetime.now()}")
    logger.info(f"测试接口: get_finance_info()")
    logger.info("")

    try:
        # 测试1: 单个查询
        await test_single_finance()
        await asyncio.sleep(1)

        # 测试2: 批量查询
        await test_batch_finance()
        await asyncio.sleep(1)

        # 测试3: 连接池并发
        await test_pool_concurrent_finance()

    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)

    logger.info("")
    logger.info("所有测试完成！")
    logger.info(f"实现进度: 10/16 (62.5%)")
    logger.info(f"覆盖场景: K线、行情、列表、复权、分时、逐笔、指数、财务")


if __name__ == "__main__":
    asyncio.run(main())

