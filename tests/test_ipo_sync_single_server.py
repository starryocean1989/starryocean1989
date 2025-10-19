# -*- coding: utf-8 -*-
"""
测试单服务器单连接同步请求所有品种IPO日期的耗时

关键特性：
1. 单服务器、单连接
2. 完全同步（串行）请求
3. 测量总耗时和平均耗时
4. 统计成功率
"""
import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.infrastructure.tdx_asyncio import AsyncTdxHq_API
from backend.infrastructure.tdx_asyncio.constants import HQ_HOSTS
from backend.infrastructure.data_module_vnpy.data_acquisition.symbol_management import SymbolLoader
from backend.infrastructure.data_module_vnpy.config import config_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def fetch_ipo_single_sync(api, symbol: str, market: int, index: int, total: int):
    """
    同步获取单个品种的IPO日期

    Args:
        api: AsyncTdxHq_API实例
        symbol: 品种代码
        market: 市场代码 (0=深圳, 1=上海)
        index: 当前索引
        total: 总数量

    Returns:
        (symbol, ipo_date, elapsed_time, success)
    """
    start_time = time.time()

    try:
        # 同步请求财务信息
        finance_info = await api.get_finance_info(market, symbol)
        ipo_timestamp = finance_info.get("ipo_date")

        elapsed = time.time() - start_time

        if ipo_timestamp and ipo_timestamp > 0:
            # 解析IPO日期
            ipo_str = str(int(ipo_timestamp)).zfill(8)
            if len(ipo_str) == 8:
                ipo_date = datetime.strptime(ipo_str, "%Y%m%d").date()

                # 每100个输出一次进度
                if (index + 1) % 100 == 0:
                    logger.info(
                        f"进度: {index+1}/{total} | {symbol} | IPO: {ipo_date} | 耗时: {elapsed:.3f}s"
                    )

                return (symbol, ipo_date, elapsed, True)

        # IPO日期无效
        if (index + 1) % 100 == 0:
            logger.warning(f"进度: {index+1}/{total} | {symbol} | 无IPO日期 | 耗时: {elapsed:.3f}s")

        return (symbol, None, elapsed, False)

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error(f"查询 {symbol} IPO失败: {e}")
        return (symbol, None, elapsed, False)


async def test_sync_ipo_query():
    """
    测试单服务器单连接同步查询所有品种的IPO日期
    """
    print("=" * 80)
    print("测试：单服务器单连接同步查询所有品种IPO日期")
    print("=" * 80)

    # 步骤1：加载品种列表
    logger.info("步骤1：加载品种列表...")
    symbol_loader = SymbolLoader()

    # 从缓存加载
    classified = symbol_loader.load_from_cache()

    if not classified:
        logger.info("缓存为空，重新加载品种列表...")
        result = symbol_loader.reload_and_classify()
        if not result["success"]:
            logger.error("加载品种列表失败")
            return
        classified = symbol_loader.load_from_cache()

    # 提取所有品种代码（上证A股 + 深证A股）
    all_symbols = []

    for market_name in ["上证A股", "深证A股"]:
        if market_name in classified:
            symbols = [item["code"] for item in classified[market_name]]
            all_symbols.extend([(s, 1 if market_name == "上证A股" else 0) for s in symbols])
            logger.info(f"{market_name}: {len(symbols)} 个品种")

    total_count = len(all_symbols)
    logger.info(f"总计: {total_count} 个品种\n")

    if total_count == 0:
        logger.error("未找到任何品种")
        return

    # 步骤2：选择服务器（使用第一个可用服务器）
    logger.info("步骤2：连接服务器...")

    # 尝试多个服务器直到连接成功
    api = None
    server_info = None

    for idx, (name, host, port) in enumerate(HQ_HOSTS[:5]):  # 尝试前5个服务器
        try:
            logger.info(f"尝试连接服务器 {idx+1}: {name} - {host}:{port}")
            api = await AsyncTdxHq_API.factory((host, port), timeout=10.0)
            if api:
                server_info = f"{name} ({host}:{port})"
                logger.info(f"✓ 成功连接到服务器: {server_info}\n")
                break
        except Exception as e:
            logger.warning(f"连接失败: {e}")
            continue

    if not api:
        logger.error("无法连接到任何服务器")
        return

    try:
        # 步骤3：同步查询所有品种的IPO日期
        print("=" * 80)
        print("步骤3：开始同步查询IPO日期...")
        print(f"服务器: {server_info}")
        print(f"总品种数: {total_count}")
        print(f"查询模式: 单连接、完全同步（串行）")
        print("=" * 80)
        print()

        start_time = time.time()
        results = []

        # 完全同步查询：一个接一个
        for idx, (symbol, market) in enumerate(all_symbols):
            result = await fetch_ipo_single_sync(api, symbol, market, idx, total_count)
            results.append(result)

            # 可选：添加小延迟避免服务器压力（可以设置为0来测试最快速度）
            # await asyncio.sleep(0.01)  # 10ms延迟

        total_time = time.time() - start_time

        # 步骤4：统计结果
        print("\n" + "=" * 80)
        print("统计结果")
        print("=" * 80)

        success_count = sum(1 for _, _, _, success in results if success)
        failed_count = total_count - success_count

        valid_times = [elapsed for _, _, elapsed, success in results if success]
        all_times = [elapsed for _, _, elapsed, _ in results]

        avg_time = sum(all_times) / len(all_times) if all_times else 0
        avg_success_time = sum(valid_times) / len(valid_times) if valid_times else 0
        min_time = min(all_times) if all_times else 0
        max_time = max(all_times) if all_times else 0

        print(f"总品种数: {total_count}")
        print(f"成功查询: {success_count} ({success_count/total_count*100:.1f}%)")
        print(f"失败查询: {failed_count} ({failed_count/total_count*100:.1f}%)")
        print()
        print(f"总耗时: {total_time:.2f}秒 ({total_time/60:.2f}分钟)")
        print(f"平均耗时: {avg_time:.3f}秒/个")
        print(f"成功请求平均耗时: {avg_success_time:.3f}秒/个")
        print(f"最快请求: {min_time:.3f}秒")
        print(f"最慢请求: {max_time:.3f}秒")
        print()
        print(f"理论吞吐量: {total_count/total_time:.1f} 个/秒")
        print(f"理论完成5000个品种需要: {5000*avg_time:.1f}秒 ({5000*avg_time/60:.1f}分钟)")
        print("=" * 80)

        # 输出前10个成功的样例
        print("\n前10个成功查询样例:")
        success_samples = [(s, ipo, t) for s, ipo, t, success in results if success][:10]
        for symbol, ipo_date, elapsed in success_samples:
            print(f"  {symbol}: {ipo_date} (耗时: {elapsed:.3f}s)")

        # 输出前10个失败的样例
        if failed_count > 0:
            print(f"\n前10个失败查询样例:")
            failed_samples = [(s, t) for s, ipo, t, success in results if not success][:10]
            for symbol, elapsed in failed_samples:
                print(f"  {symbol}: 失败 (耗时: {elapsed:.3f}s)")

    finally:
        # 关闭连接
        await api.close()
        logger.info("\n✓ 连接已关闭")


async def test_sync_ipo_query_limited():
    """
    测试有限数量品种（100个）的IPO查询
    用于快速验证
    """
    print("=" * 80)
    print("快速测试：单服务器单连接同步查询100个品种IPO日期")
    print("=" * 80)

    # 步骤1：加载品种列表
    logger.info("步骤1：加载品种列表...")
    symbol_loader = SymbolLoader()

    classified = symbol_loader.load_from_cache()

    if not classified:
        logger.info("缓存为空，重新加载品种列表...")
        result = symbol_loader.reload_and_classify()
        if not result["success"]:
            logger.error("加载品种列表失败")
            return
        classified = symbol_loader.load_from_cache()

    # 提取前100个品种
    all_symbols = []

    for market_name in ["上证A股", "深证A股"]:
        if market_name in classified:
            symbols = [item["code"] for item in classified[market_name]]
            all_symbols.extend([(s, 1 if market_name == "上证A股" else 0) for s in symbols])

    # 限制为100个
    all_symbols = all_symbols[:100]
    total_count = len(all_symbols)
    logger.info(f"测试品种数: {total_count}\n")

    # 步骤2：连接服务器
    logger.info("步骤2：连接服务器...")

    api = None
    server_info = None

    for idx, (name, host, port) in enumerate(HQ_HOSTS[:5]):
        try:
            logger.info(f"尝试连接服务器 {idx+1}: {name} - {host}:{port}")
            api = await AsyncTdxHq_API.factory((host, port), timeout=10.0)
            if api:
                server_info = f"{name} ({host}:{port})"
                logger.info(f"✓ 成功连接到服务器: {server_info}\n")
                break
        except Exception as e:
            logger.warning(f"连接失败: {e}")
            continue

    if not api:
        logger.error("无法连接到任何服务器")
        return

    try:
        # 步骤3：同步查询
        print("=" * 80)
        print("开始同步查询...")
        print("=" * 80)

        start_time = time.time()
        results = []

        for idx, (symbol, market) in enumerate(all_symbols):
            result = await fetch_ipo_single_sync(api, symbol, market, idx, total_count)
            results.append(result)

        total_time = time.time() - start_time

        # 统计
        success_count = sum(1 for _, _, _, success in results if success)
        valid_times = [elapsed for _, _, elapsed, success in results if success]
        all_times = [elapsed for _, _, elapsed, _ in results]

        avg_time = sum(all_times) / len(all_times) if all_times else 0

        print("\n" + "=" * 80)
        print("快速测试结果")
        print("=" * 80)
        print(f"总耗时: {total_time:.2f}秒")
        print(f"平均耗时: {avg_time:.3f}秒/个")
        print(f"成功率: {success_count}/{total_count} ({success_count/total_count*100:.1f}%)")
        print(f"\n📊 外推估算全部品种（假设5000个）:")
        print(f"   预计总耗时: {5000*avg_time:.1f}秒 ({5000*avg_time/60:.1f}分钟)")
        print("=" * 80)

    finally:
        await api.close()
        logger.info("\n✓ 连接已关闭")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="测试单服务器同步IPO查询")
    parser.add_argument("--full", action="store_true", help="测试全部品种（默认只测试100个）")

    args = parser.parse_args()

    if args.full:
        print("⚠️  即将测试全部品种，这可能需要较长时间...\n")
        asyncio.run(test_sync_ipo_query())
    else:
        print("💡 快速测试模式（100个品种）\n")
        asyncio.run(test_sync_ipo_query_limited())
        print("\n💡 提示: 使用 --full 参数测试全部品种")
