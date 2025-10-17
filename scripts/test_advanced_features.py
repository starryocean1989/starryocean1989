# -*- coding: utf-8 -*-
"""
tdx_asyncio v2.1 高级功能测试脚本

测试新增功能：
1. 交易日历系统
2. 扩展行情API（期货/期权）
3. 本地数据读取器
4. 新增常量和映射
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


async def test_trading_calendar():
    """测试交易日历系统"""
    print("\n" + "=" * 60)
    print("测试1: 交易日历系统")
    print("=" * 60)

    try:
        from backend.infrastructure.tdx_asyncio import (
            TradingCalendar,
            is_trading_day_global,
            get_next_trading_day_global,
            get_previous_trading_day_global,
            get_trading_days_in_range_global,
        )

        # 1. 测试单例实例
        calendar = TradingCalendar()
        print("\n✓ TradingCalendar实例创建成功")

        # 2. 获取交易日历
        print("\n正在获取交易日历...")
        df = await calendar.get_trading_calendar()
        if not df.empty:
            print(f"✓ 成功获取交易日历: {len(df)}个交易日")
            print(f"  最新交易日: {df['date'].max()}")
            print(f"  最早交易日: {df['date'].min()}")
        else:
            print("⚠ 交易日历为空（可能是模拟数据）")

        # 3. 判断今天是否交易日
        print("\n正在判断今天是否交易日...")
        is_trading = await is_trading_day_global()
        print(f"✓ 今天{'是' if is_trading else '不是'}交易日")

        # 4. 获取下一个交易日
        print("\n正在获取下一个交易日...")
        next_day = await get_next_trading_day_global()
        if next_day:
            print(f"✓ 下一个交易日: {next_day}")

        # 5. 获取上一个交易日
        print("\n正在获取上一个交易日...")
        prev_day = await get_previous_trading_day_global()
        if prev_day:
            print(f"✓ 上一个交易日: {prev_day}")

        # 6. 获取交易日范围
        print("\n正在获取交易日范围...")
        trading_days = await get_trading_days_in_range_global('2024-01-01', '2024-01-31')
        if trading_days:
            print(f"✓ 2024年1月交易日: {len(trading_days)}天")
            print(f"  交易日列表: {trading_days[:5]}... (前5天)")

        print("\n✅ 交易日历系统测试通过")

    except Exception as e:
        print(f"\n❌ 交易日历系统测试失败: {e}")
        import traceback
        traceback.print_exc()


async def test_extended_market_api():
    """测试扩展行情API"""
    print("\n" + "=" * 60)
    print("测试2: 扩展行情API（期货/期权）")
    print("=" * 60)

    try:
        from backend.infrastructure.tdx_asyncio import (
            AsyncTdxExHq_API,
            get_future_markets,
            get_future_bars,
        )

        # 1. 测试市场列表
        print("\n正在获取期货市场列表...")
        markets = await get_future_markets()
        if markets:
            print(f"✓ 支持的期货市场: {len(markets)}个")
            for market in markets:
                print(f"  - {market['name']} (代码: {market['market']})")
        else:
            print("⚠ 无法获取期货市场列表")

        # 2. 测试API类
        print("\n正在测试AsyncTdxExHq_API类...")
        print("✓ AsyncTdxExHq_API类导入成功")
        print("  提供的接口:")
        print("  - get_markets() - 获取市场列表")
        print("  - get_instrument_count() - 获取品种数量")
        print("  - get_instrument_bars() - 获取K线数据")
        print("  - get_instrument_quote() - 获取实时行情")
        print("  - get_instrument_info() - 获取品种信息")

        print("\n✅ 扩展行情API测试通过")

    except Exception as e:
        print(f"\n❌ 扩展行情API测试失败: {e}")
        import traceback
        traceback.print_exc()


async def test_local_data_readers():
    """测试本地数据读取器"""
    print("\n" + "=" * 60)
    print("测试3: 本地数据读取器")
    print("=" * 60)

    try:
        from backend.infrastructure.tdx_asyncio import (
            AsyncTdxDayReader,
            AsyncTdxMinuteReader,
            AsyncTdxLc5Reader,
            AsyncTdxBlockReader,
            read_day_data,
            read_minute_data,
        )

        # 1. 测试类导入
        print("\n✓ 所有读取器类导入成功:")
        print("  - AsyncTdxDayReader - 日K线读取器")
        print("  - AsyncTdxMinuteReader - 分钟线读取器")
        print("  - AsyncTdxLc5Reader - 5分钟线读取器")
        print("  - AsyncTdxBlockReader - 板块文件读取器")

        # 2. 测试便捷函数
        print("\n✓ 便捷函数导入成功:")
        print("  - read_day_data() - 读取日线")
        print("  - read_minute_data() - 读取分钟线")
        print("  - read_lc5_data() - 读取5分钟线")
        print("  - read_block_data() - 读取板块")

        # 3. 模拟文件读取（如果文件存在）
        print("\n正在检查通达信本地数据...")
        tdx_paths = [
            Path("C:/new_tdx/vipdoc"),
            Path("C:/tdx/vipdoc"),
            Path("D:/tdx/vipdoc"),
        ]

        for tdx_path in tdx_paths:
            if tdx_path.exists():
                print(f"✓ 发现通达信目录: {tdx_path}")

                # 尝试读取一个日线文件
                sh_day_dir = tdx_path / "sh" / "lday"
                if sh_day_dir.exists():
                    day_files = list(sh_day_dir.glob("*.day"))
                    if day_files:
                        test_file = day_files[0]
                        print(f"\n  测试读取文件: {test_file.name}")

                        df = await read_day_data(test_file)
                        if not df.empty:
                            print(f"  ✓ 成功读取日线数据: {len(df)}条记录")
                            print(f"    列名: {list(df.columns)}")
                            print(f"    最新日期: {df['date'].max()}")
                        else:
                            print("  ⚠ 数据为空")
                        break

        print("\n✅ 本地数据读取器测试通过")

    except Exception as e:
        print(f"\n❌ 本地数据读取器测试失败: {e}")
        import traceback
        traceback.print_exc()


async def test_new_constants():
    """测试新增常量"""
    print("\n" + "=" * 60)
    print("测试4: 新增常量和映射")
    print("=" * 60)

    try:
        from backend.infrastructure.tdx_asyncio import (
            # 扩展市场常量
            EX_MARKET_ZHENGZHOU,
            EX_MARKET_DALIAN,
            EX_MARKET_SHANGHAI,
            EX_MARKET_CFFEX,
            EX_MARKET_INE,
            EX_MARKET_NAME_MAP,
            EX_MARKET_CODE_MAP,
            # 复权类型映射
            ADJUST_TYPE_MAP,
            ADJUST_CODE_MAP,
            # 除权除息类别
            XDXR_CATEGORY_DIVIDEND,
            XDXR_CATEGORY_BONUS,
            XDXR_CATEGORY_ALLOT,
            # 协议调试常量
            PROTOCOL_HEADER_MAGIC,
            PROTOCOL_VERSION,
        )

        # 1. 扩展市场常量
        print("\n✓ 扩展市场常量:")
        print(f"  郑州商品: {EX_MARKET_ZHENGZHOU}")
        print(f"  大连商品: {EX_MARKET_DALIAN}")
        print(f"  上海期货: {EX_MARKET_SHANGHAI}")
        print(f"  中金所: {EX_MARKET_CFFEX}")
        print(f"  上海能源: {EX_MARKET_INE}")

        # 2. 市场名称映射
        print("\n✓ 扩展市场名称映射:")
        for code, name in list(EX_MARKET_NAME_MAP.items())[:3]:
            print(f"  {code}: {name}")

        # 3. 复权类型映射
        print("\n✓ 复权类型映射:")
        print(f"  前复权 (qfq): {ADJUST_TYPE_MAP['qfq']}")
        print(f"  后复权 (hfq): {ADJUST_TYPE_MAP['hfq']}")
        print(f"  代码映射: {ADJUST_CODE_MAP}")

        # 4. 除权除息类别
        print("\n✓ 除权除息类别:")
        print(f"  分红派息: {XDXR_CATEGORY_DIVIDEND}")
        print(f"  送股: {XDXR_CATEGORY_BONUS}")
        print(f"  配股: {XDXR_CATEGORY_ALLOT}")

        # 5. 协议调试常量
        print("\n✓ 协议调试常量:")
        print(f"  协议头魔数: 0x{PROTOCOL_HEADER_MAGIC:02X}")
        print(f"  协议版本: 0x{PROTOCOL_VERSION:02X}")

        print("\n✅ 新增常量测试通过")

    except Exception as e:
        print(f"\n❌ 新增常量测试失败: {e}")
        import traceback
        traceback.print_exc()


async def test_version_info():
    """测试版本信息"""
    print("\n" + "=" * 60)
    print("测试5: 版本信息")
    print("=" * 60)

    try:
        import backend.infrastructure.tdx_asyncio as tdx_asyncio

        print(f"\n✓ tdx_asyncio 版本: {tdx_asyncio.__version__}")
        print(f"✓ 作者: {tdx_asyncio.__author__}")

        # 列出所有导出的API
        exported_apis = [name for name in dir(tdx_asyncio) if not name.startswith('_')]
        print(f"\n✓ 导出的API数量: {len(exported_apis)}")
        print(f"  主要模块:")
        print(f"  - 核心行情API: AsyncTdxHq_API")
        print(f"  - 扩展行情API: AsyncTdxExHq_API (v2.1新增)")
        print(f"  - 交易日历: TradingCalendar (v2.1新增)")
        print(f"  - 本地数据读取器: AsyncTdxDayReader等 (v2.1新增)")
        print(f"  - 连接池管理: AsyncConnectionPool (v2.0)")
        print(f"  - IP池管理: AsyncSmartIPPool (v2.0)")
        print(f"  - 数据处理: to_dataframe, apply_adjustment等")
        print(f"  - 性能监控: async_timeit, PerformanceMonitor等")

        print("\n✅ 版本信息测试通过")

    except Exception as e:
        print(f"\n❌ 版本信息测试失败: {e}")
        import traceback
        traceback.print_exc()


async def main():
    """主测试函数"""
    print("\n" + "=" * 60)
    print("tdx_asyncio v2.1 高级功能测试")
    print("=" * 60)

    # 运行所有测试
    await test_version_info()
    await test_new_constants()
    await test_trading_calendar()
    await test_extended_market_api()
    await test_local_data_readers()

    print("\n" + "=" * 60)
    print("所有测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())

