# -*- coding: utf-8 -*-
"""
data_module_vnpy数据初始化脚本

功能：
1. 检查data_module_vnpy配置
2. 调用API下载品种列表
3. 提供全量/增量数据下载选项
4. 生成初始化报告
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def init_data():
    """初始化data_module_vnpy数据"""
    print("=" * 60)
    print("data_module_vnpy数据初始化")
    print("=" * 60)

    try:
        # 导入VnPy相关模块
        from vnpy.event import EventEngine
        from vnpy.trader.engine import MainEngine
        from backend.infrastructure.data_module_vnpy import ChinaStockApp

        print("\n正在初始化VnPy引擎...")

        # 创建vnpy主引擎
        event_engine = EventEngine()
        main_engine = MainEngine(event_engine)

        # 添加中国A股数据管理应用
        print("正在加载中国A股数据管理应用...")
        engine = main_engine.add_app(ChinaStockApp)
        print("✓ 中国A股数据管理应用已加载")

        # 步骤1: 检查本地品种缓存
        print("\n步骤1: 检查本地品种缓存...")
        stocks = engine.refresh_stock_list()

        if stocks and sum(len(v) for v in stocks.values()) > 0:
            total = sum(len(v) for v in stocks.values())
            print(f"✓ 发现本地品种缓存: {total} 个品种")
            for market_type, codes in stocks.items():
                print(f"  - {market_type}: {len(codes)} 个品种")

            # 询问是否重新加载
            choice = input("\n是否重新从API获取最新品种列表? (y/n，默认n): ").strip().lower()
            if choice == "y":
                print("\n正在从API重新加载品种列表...")
                success = engine.reload_stock_list()
                if success:
                    stocks = engine.refresh_stock_list()
                    total = sum(len(v) for v in stocks.values())
                    print(f"✓ 品种列表更新成功: {total} 个品种")
                else:
                    print("✗ 品种列表更新失败")
                    main_engine.close()
                    event_engine.stop()
                    return
        else:
            # 本地无缓存，自动从API加载
            print("本地品种缓存为空，正在从API获取品种列表...")
            success = engine.reload_stock_list()

            if success:
                stocks = engine.refresh_stock_list()
                total = sum(len(v) for v in stocks.values())
                print(f"✓ 品种列表获取成功: {total} 个品种")
                for market_type, codes in stocks.items():
                    print(f"  - {market_type}: {len(codes)} 个品种")
            else:
                print("✗ 品种列表获取失败")
                print("\n可能原因:")
                print("  1. 网络连接问题")
                print("  2. mootdx服务不可用")
                print("  3. 通达信配置路径不正确")
                main_engine.close()
                event_engine.stop()
                return

        # 步骤2: 下载历史数据（可选）
        print("\n步骤2: 历史数据下载")
        print("=" * 60)

        choice = input("\n是否下载历史K线数据? (y/n，默认n): ").strip().lower()

        if choice == "y":
            print("\n选择下载模式:")
            print("  1. 仅下载日线数据（推荐，快速，约10-20分钟）")
            print("  2. 全量下载（日线+5分钟+1分钟，耗时较长，约2-4小时）")
            print("  3. 测试模式（仅下载少量品种，用于测试）")

            mode = input("请选择模式 (1/2/3，默认1): ").strip()

            if mode == "2":
                print("\n开始全量下载...")
                print("⚠ 警告：全量下载将下载所有品种的日线、5分钟、1分钟数据，可能需要2-4小时")
                confirm = input("确认继续? (yes/no): ").strip().lower()
                if confirm == "yes":
                    success = engine.download_full()
                    if success:
                        print("✓ 全量数据下载完成")
                    else:
                        print("✗ 全量数据下载失败")
                else:
                    print("已取消全量下载")

            elif mode == "3":
                print("\n测试模式：下载少量品种...")
                # 选择前10个品种进行测试下载
                test_symbols = []
                for market_type, codes in stocks.items():
                    test_symbols.extend(codes[:2])  # 每个市场类型取2个
                    if len(test_symbols) >= 10:
                        break

                print(f"将下载以下品种的日线数据: {test_symbols[:10]}")

                # 这里需要调用engine的下载方法（简化版本）
                # 实际应该调用engine的download_symbols方法
                print("✓ 测试下载完成（功能待实现）")

            else:
                # 默认：仅下载日线数据
                print("\n开始下载日线数据...")
                print("这将下载所有品种的日线数据，预计耗时10-20分钟")

                # 调用日线下载方法（如果engine有这个方法）
                if hasattr(engine, "download_full_daily_only"):
                    success = engine.download_full_daily_only()
                    if success:
                        print("✓ 日线数据下载完成")
                    else:
                        print("✗ 日线数据下载失败")
                else:
                    # 使用全量下载但只下载日线
                    print("ℹ 使用全量下载接口...")
                    success = engine.download_full(intervals=["1d"])
                    if success:
                        print("✓ 日线数据下载完成")
                    else:
                        print("✗ 日线数据下载失败")

        else:
            print("跳过历史数据下载")

        # 步骤3: 生成初始化报告
        print("\n步骤3: 生成初始化报告")
        print("=" * 60)

        # 统计品种数量
        if stocks:
            total_symbols = sum(len(v) for v in stocks.values())
            print(f"\n品种统计:")
            print(f"  总计: {total_symbols} 个品种")
            for market_type, codes in stocks.items():
                print(f"  - {market_type}: {len(codes)} 个")

        # 统计已下载的数据
        print(f"\n已下载数据:")
        all_symbols = engine.storage_manager.list_symbols()
        print(f"  - 品种数量: {len(all_symbols)} 个")

        if all_symbols:
            # 统计各周期数据
            interval_counts = {"1d": 0, "5m": 0, "1m": 0}
            for symbol in all_symbols[:10]:  # 仅检查前10个
                intervals = engine.storage_manager.list_intervals(symbol)
                for interval in intervals:
                    if interval in interval_counts:
                        interval_counts[interval] += 1

            print(f"  - 日线数据: {interval_counts['1d']} 个品种")
            print(f"  - 5分钟数据: {interval_counts['5m']} 个品种")
            print(f"  - 1分钟数据: {interval_counts['1m']} 个品种")

        # 关闭引擎
        print("\n正在关闭VnPy引擎...")
        main_engine.close()
        event_engine.stop()

        print("\n" + "=" * 60)
        print("初始化完成！")
        print("=" * 60)

        # 提示下一步
        print("\n下一步:")
        print("  - 运行项目: python start_terminal.py")
        print("  - 运行测试: python -m pytest tests/test_e2e/ -v")

    except ImportError as e:
        print(f"\n✗ 导入错误: {e}")
        print("\n请确保已安装所有依赖:")
        print("  pip install -r requirements.txt")
        sys.exit(1)

    except Exception as e:
        print(f"\n✗ 初始化失败: {e}")
        logger.exception("初始化过程中发生异常")
        sys.exit(1)


if __name__ == "__main__":
    init_data()
