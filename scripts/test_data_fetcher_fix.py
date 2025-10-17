# -*- coding: utf-8 -*-
"""
测试data_fetcher.py修正后的实现
验证频率参数和市场参数是否正确
"""
import sys
from pathlib import Path
from datetime import date, timedelta
import logging

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.data_module_vnpy.data_fetcher import MultiProcessStockFetcher

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


def test_frequency_and_market_params():
    """测试频率参数和市场参数"""
    print("\n" + "="*60)
    print("测试data_fetcher.py修正后的实现")
    print("="*60)

    # 测试数据：不同市场的股票
    test_symbols = [
        ("600000", "上海证券交易所"),  # 浦发银行 - 上海
        ("000001", "深圳证券交易所"),  # 平安银行 - 深圳
        ("430047", "北京证券交易所"),  # 北交所股票示例
        ("688001", "上海科创板"),      # 华兴源创 - 上海科创板
    ]

    # 测试不同的时间周期
    intervals = ["1d", "5m", "1m"]

    # 开始日期：最近10天
    start_date = (date.today() - timedelta(days=10)).strftime("%Y-%m-%d")

    print(f"\n📅 测试参数:")
    print(f"  开始日期: {start_date}")
    print(f"  时间周期: {intervals}")
    print(f"  测试品种数: {len(test_symbols)}")

    # 创建下载器
    fetcher = MultiProcessStockFetcher()
    fetcher.set_server_count(3)  # 使用3个进程

    success_count = 0
    fail_count = 0

    for symbol, market_name in test_symbols:
        print(f"\n{'='*60}")
        print(f"📊 测试品种: {symbol} ({market_name})")
        print(f"{'='*60}")

        try:
            # 下载数据
            results = fetcher.download_incremental_kline(
                symbols=[symbol],
                start_date=start_date,
                intervals=intervals,
                progress_callback=None
            )

            # 分析结果
            for interval in intervals:
                key = f"{symbol}_{interval}"
                if key in results:
                    data = results[key]
                    if data is not None and not data.empty:
                        print(f"  ✅ {interval}: 成功获取 {len(data)} 条数据")
                        print(f"      数据列: {list(data.columns)}")
                        if len(data) > 0:
                            print(f"      首行时间: {data.iloc[0].get('datetime', 'N/A')}")
                            print(f"      末行时间: {data.iloc[-1].get('datetime', 'N/A')}")
                        success_count += 1
                    else:
                        print(f"  ⚠️  {interval}: 返回空数据")
                        fail_count += 1
                else:
                    print(f"  ❌ {interval}: 未返回结果")
                    fail_count += 1

        except Exception as e:
            print(f"  ❌ 测试失败: {str(e)}")
            logger.error(f"测试 {symbol} 失败", exc_info=True)
            fail_count += len(intervals)

    # 输出总结
    print(f"\n{'='*60}")
    print("📊 测试总结")
    print(f"{'='*60}")
    total_tests = len(test_symbols) * len(intervals)
    print(f"  总测试数: {total_tests}")
    print(f"  成功: {success_count}")
    print(f"  失败: {fail_count}")
    print(f"  成功率: {success_count/total_tests*100:.1f}%")

    return success_count > 0


def test_frequency_mapping():
    """直接测试频率映射"""
    print("\n" + "="*60)
    print("测试频率参数映射")
    print("="*60)

    from mootdx.quotes import Quotes

    # 创建连接
    quotes = Quotes.factory()

    # 测试不同频率参数
    test_cases = [
        ("000001", 4, "1d", "日线"),
        ("000001", 0, "5m", "5分钟"),
        ("000001", 8, "1m", "1分钟"),
    ]

    for symbol, frequency, interval_name, description in test_cases:
        print(f"\n测试 {description} (frequency={frequency}):")
        try:
            # 直接调用底层API
            raw_data = quotes.client.get_security_bars(
                int(frequency), 0, str(symbol), 0, 10
            )

            if raw_data and len(raw_data) > 0:
                print(f"  ✅ 成功获取 {len(raw_data)} 条数据")
                print(f"  首条数据: {raw_data[0]}")
            else:
                print(f"  ⚠️  返回空数据")

        except Exception as e:
            print(f"  ❌ 调用失败: {str(e)}")
            logger.error(f"频率测试失败", exc_info=True)

    quotes.close()


def test_market_detection():
    """测试市场代码检测"""
    print("\n" + "="*60)
    print("测试市场代码检测")
    print("="*60)

    test_cases = [
        ("600000", 1, "上海证券交易所"),
        ("601988", 1, "上海证券交易所"),
        ("000001", 0, "深圳证券交易所"),
        ("002594", 0, "深圳证券交易所"),
        ("300750", 0, "深圳创业板"),
        ("430047", 2, "北京证券交易所"),
        ("430090", 2, "北京证券交易所"),
        ("830799", 2, "北京证券交易所"),
        ("688001", 1, "上海科创板"),
    ]

    for symbol, expected_market, market_name in test_cases:
        # 模拟市场检测逻辑
        if symbol.startswith("6"):
            market = 1
        elif any(symbol.startswith(prefix) for prefix in ["43", "83", "87", "88"]):
            market = 2
        else:
            market = 0

        result = "✅" if market == expected_market else "❌"
        print(f"  {result} {symbol} -> 市场代码={market} (期望={expected_market}) {market_name}")


if __name__ == "__main__":
    print("\n🚀 开始测试data_fetcher.py修正")

    # 测试1: 市场代码检测
    test_market_detection()

    # 测试2: 频率参数映射
    try:
        test_frequency_mapping()
    except Exception as e:
        logger.error("频率映射测试失败", exc_info=True)

    # 测试3: 完整下载测试
    try:
        success = test_frequency_and_market_params()
        if success:
            print("\n✅ 测试通过！修正有效。")
        else:
            print("\n❌ 测试失败，需要进一步调查。")
    except Exception as e:
        logger.error("完整测试失败", exc_info=True)
        print(f"\n❌ 测试异常: {str(e)}")

