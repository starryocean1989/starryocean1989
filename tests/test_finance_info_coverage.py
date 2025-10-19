# -*- coding: utf-8 -*-
"""
测试 get_finance_info 接口对不同品种类型的支持情况

测试范围：
1. 北交所股票（市场代码2，代码9xxxxx）
2. 可转债（上海110xxx，深圳123xxx）
3. ETF（上海51xxxx，深圳15xxxx）
4. LOF基金（上海501xxx，深圳16xxxx）
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, List

from backend.infrastructure.tdx_asyncio import AsyncTdxHq_API

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# 直接使用固定的测试服务器（避免依赖服务器池启动）
TEST_SERVERS = [
    ("119.147.212.81", 7709),  # 通达信主站
    ("124.71.186.122", 7709),  # 备用服务器1
    ("60.191.117.167", 7709),  # 备用服务器2
]


# 测试样本：不同品种类型（基于实际品种列表缓存）
TEST_SAMPLES = {
    "北交所股票": [
        {"market": 2, "code": "920000", "name": "安徽凤凰"},  # 北交所92开头
        {"market": 2, "code": "920001", "name": "纬达光电"},
        {"market": 2, "code": "920002", "name": "万达轴承"},
    ],
    "可转债-深圳": [
        {"market": 0, "code": "123107", "name": "温氏转债"},
        {"market": 0, "code": "128136", "name": "立讯转债"},
        {"market": 0, "code": "127019", "name": "国城转债"},
    ],
    "可转债-上海": [
        {"market": 1, "code": "110059", "name": "浦发转债"},  # 实际存在的11开头可转债
        {"market": 1, "code": "110060", "name": "天路转债"},
        {"market": 1, "code": "110062", "name": "烽火转债"},
    ],
    "ETF-深圳": [
        {"market": 0, "code": "159919", "name": "300ETF"},
        {"market": 0, "code": "159915", "name": "创业板ETF"},
        {"market": 0, "code": "159601", "name": "医药ETF"},
    ],
    "ETF-上海": [
        {"market": 1, "code": "510050", "name": "50ETF"},
        {"market": 1, "code": "510300", "name": "300ETF"},
        {"market": 1, "code": "510880", "name": "红利ETF"},
    ],
    "LOF基金-深圳": [
        {"market": 0, "code": "161725", "name": "招商中证白酒"},
        {"market": 0, "code": "163406", "name": "兴全合润"},
        {"market": 0, "code": "160632", "name": "鹏华创新"},
    ],
    "LOF基金-上海": [
        {"market": 1, "code": "501018", "name": "南方原油"},
        {"market": 1, "code": "501300", "name": "汇添富沪深300"},
        {"market": 1, "code": "501058", "name": "南方中证500"},
    ],
}


async def test_single_symbol(
    client: AsyncTdxHq_API, category: str, symbol: Dict[str, Any]
) -> Dict[str, Any]:
    """测试单个品种的 get_finance_info 接口

    Args:
        client: tdx异步客户端
        category: 品种类别
        symbol: 品种信息 {"market": 0, "code": "123456", "name": "品种名"}

    Returns:
        测试结果字典
    """
    market = symbol["market"]
    code = symbol["code"]
    name = symbol["name"]

    result = {
        "category": category,
        "market": market,
        "code": code,
        "name": name,
        "success": False,
        "has_ipo_date": False,
        "ipo_date": None,
        "ipo_date_readable": None,
        "response_data": None,
        "error": None,
    }

    try:
        logger.info(f"测试 {category}: {name}({code}), 市场={market}")

        # 调用接口
        finance_info = await asyncio.wait_for(
            client.get_finance_info(market=market, code=code), timeout=10.0
        )

        if finance_info:
            result["success"] = True
            result["response_data"] = finance_info

            # 检查 ipo_date 字段
            ipo_date_value = finance_info.get("ipo_date")

            if ipo_date_value and ipo_date_value > 0:
                result["has_ipo_date"] = True
                result["ipo_date"] = ipo_date_value

                # 转换为可读日期
                try:
                    ipo_str = str(int(ipo_date_value)).zfill(8)
                    if len(ipo_str) == 8:
                        ipo_date_obj = datetime.strptime(ipo_str, "%Y%m%d")
                        result["ipo_date_readable"] = ipo_date_obj.strftime("%Y-%m-%d")
                except Exception as e:
                    result["ipo_date_readable"] = f"解析失败: {e}"

            # 打印关键字段
            logger.info(f"  ✓ 成功获取财务信息")
            logger.info(f"    - ipo_date: {result['ipo_date']} -> {result['ipo_date_readable']}")
            logger.info(f"    - 流通股本: {finance_info.get('liutongguben', 0):.0f}")
            logger.info(f"    - 总股本: {finance_info.get('zongguben', 0):.0f}")
            logger.info(f"    - 行业代码: {finance_info.get('industry', 0)}")
            logger.info(f"    - 省份代码: {finance_info.get('province', 0)}")

        else:
            logger.warning(f"  ✗ 返回空数据")
            result["error"] = "返回空数据"

    except asyncio.TimeoutError:
        logger.error(f"  ✗ 查询超时")
        result["error"] = "查询超时"

    except Exception as e:
        logger.error(f"  ✗ 查询失败: {e}")
        result["error"] = str(e)

    return result


async def test_all_categories():
    """测试所有品种类别"""

    logger.info("=" * 80)
    logger.info("开始测试 get_finance_info 接口对不同品种类型的支持情况")
    logger.info("=" * 80)

    # 尝试连接服务器（多个服务器重试）
    client = None
    for server in TEST_SERVERS:
        try:
            logger.info(f"尝试连接服务器: {server[0]}:{server[1]}")
            client = await asyncio.wait_for(
                AsyncTdxHq_API.factory(
                    server=server, timeout=8.0, heartbeat=False, raise_exception=False
                ),
                timeout=15.0,
            )

            if client:
                logger.info(f"✓ 连接成功: {server[0]}:{server[1]}\n")
                break
            else:
                logger.warning(f"✗ 连接失败: {server[0]}:{server[1]}")

        except Exception as e:
            logger.warning(f"✗ 连接异常 {server[0]}:{server[1]}: {e}")
            continue

    if not client:
        logger.error("无法连接到任何服务器")
        return

    try:
        all_results = []

        # 遍历所有类别
        for category, symbols in TEST_SAMPLES.items():
            logger.info(f"\n{'=' * 80}")
            logger.info(f"测试类别: {category}")
            logger.info(f"{'=' * 80}")

            for symbol in symbols:
                result = await test_single_symbol(client, category, symbol)
                all_results.append(result)

                # 暂停100ms，避免请求过快
                await asyncio.sleep(0.1)

        # 统计结果
        logger.info(f"\n{'=' * 80}")
        logger.info("测试结果汇总")
        logger.info(f"{'=' * 80}")

        # 按类别统计
        category_stats = {}
        for result in all_results:
            cat = result["category"]
            if cat not in category_stats:
                category_stats[cat] = {"total": 0, "success": 0, "has_ipo": 0, "samples": []}

            category_stats[cat]["total"] += 1
            if result["success"]:
                category_stats[cat]["success"] += 1
            if result["has_ipo_date"]:
                category_stats[cat]["has_ipo"] += 1
                category_stats[cat]["samples"].append(
                    {
                        "code": result["code"],
                        "name": result["name"],
                        "ipo_date": result["ipo_date_readable"],
                    }
                )

        # 打印统计
        for category, stats in category_stats.items():
            logger.info(f"\n【{category}】")
            logger.info(f"  测试数量: {stats['total']}")
            logger.info(f"  成功查询: {stats['success']} ({stats['success']*100//stats['total']}%)")
            logger.info(
                f"  有效IPO日期: {stats['has_ipo']} ({stats['has_ipo']*100//stats['total'] if stats['total'] > 0 else 0}%)"
            )

            if stats["samples"]:
                logger.info(f"  IPO日期样例:")
                for sample in stats["samples"][:3]:
                    logger.info(f"    - {sample['name']}({sample['code']}): {sample['ipo_date']}")

        # 输出结论
        logger.info(f"\n{'=' * 80}")
        logger.info("结论")
        logger.info(f"{'=' * 80}")

        for category, stats in category_stats.items():
            if stats["has_ipo"] > 0:
                logger.info(f"✓ {category}: 支持查询上市日期 ({stats['has_ipo']}/{stats['total']})")
            elif stats["success"] > 0:
                logger.info(
                    f"⚠ {category}: 可以查询但无IPO日期字段 ({stats['success']}/{stats['total']})"
                )
            else:
                logger.info(f"✗ {category}: 不支持查询 (0/{stats['total']})")

    finally:
        await client.close()
        logger.info("\n✓ 测试完成，连接已关闭")


if __name__ == "__main__":
    asyncio.run(test_all_categories())
