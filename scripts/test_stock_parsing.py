# -*- coding: utf-8 -*-
"""
品种解析测试脚本

用于测试品种列表的获取和解析逻辑，特别是验证spblock.dat解析是否正常工作。
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


def test_stock_parsing():
    """测试品种解析功能"""
    print("=" * 60)
    print("品种解析测试")
    print("=" * 60)

    try:
        # 导入所需模块
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

        # 测试品种列表获取
        print("\n测试品种列表获取...")
        stocks = engine.get_all_market_stocks()

        if stocks:
            total = sum(len(v) for v in stocks.values())
            print(f"✓ 品种列表获取成功: {total} 个品种")
            for market_type, codes in stocks.items():
                print(f"  - {market_type}: {len(codes)} 个品种")
        else:
            print("✗ 品种列表获取失败")

        # 检查spblock.dat是否可用
        print("\n检查通达信板块文件...")
        if hasattr(engine, 'block_parser'):
            if engine.block_parser.is_available():
                print("✓ spblock.dat可用")
                block_info = engine.block_parser.get_file_info()
                print(f"  文件信息: {block_info}")
            else:
                print("⚠ spblock.dat不可用，这将影响特殊品种的解析")
        else:
            print("⚠ 无法访问block_parser")

        # 关闭引擎
        print("\n正在关闭VnPy引擎...")
        main_engine.close()
        event_engine.stop()

        print("\n" + "=" * 60)
        print("品种解析测试完成！")
        print("=" * 60)

    except ImportError as e:
        print(f"\n✗ 导入错误: {e}")
        print("\n请确保已安装所有依赖:")
        print("  pip install -r requirements.txt")
        sys.exit(1)

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        logger.exception("测试过程中发生异常")
        sys.exit(1)


if __name__ == "__main__":
    test_stock_parsing()
