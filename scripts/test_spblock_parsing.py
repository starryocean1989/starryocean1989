# -*- coding: utf-8 -*-
"""
spblock.dat解析测试脚本

专门测试从spblock.dat中解析T+0基金品种、北交所股票、可转债品种的功能。
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

import logging
from backend.infrastructure.data_module_vnpy.block_parser import BlockParser
from backend.infrastructure.data_module_vnpy.config import config_manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)


def test_spblock_parsing():
    """测试spblock.dat解析功能"""
    print("=" * 60)
    print("spblock.dat解析测试")
    print("=" * 60)

    try:
        # 创建BlockParser实例
        print("正在初始化BlockParser...")
        tdx_dir = config_manager.get_tdx_dir()
        if tdx_dir:
            print(f"使用配置的通达信目录: {tdx_dir}")
            parser = BlockParser(tdx_dir)
        else:
            print("未配置通达信目录，使用默认路径搜索...")
            parser = BlockParser()

        # 检查文件是否可用
        print("\n检查spblock.dat文件...")
        if parser.is_available():
            file_info = parser.get_file_info()
            print("✓ spblock.dat可用")
            print(f"  文件路径: {file_info['path']}")
            print(f"  文件大小: {file_info['size']}")
        else:
            print("✗ spblock.dat不可用")
            return

        # 解析板块文件
        print("\n解析板块文件...")
        df = parser.parse_block_file()

        if df is not None and not df.empty:
            print(f"✓ 成功解析 {len(df)} 条记录")
            print(f"  板块数量: {df['blockname'].nunique()}")

            # 显示前几个板块名称
            unique_blocks = df["blockname"].unique()[:10]
            print(f"  前10个板块: {list(unique_blocks)}")
        else:
            print("✗ 解析失败或返回空数据")
            return

        # 测试目标板块解析
        print("\n测试目标板块解析...")

        # 获取北证A股
        beijing_stocks = parser.get_beijing_stocks()
        print(f"北证A股: {len(beijing_stocks)} 个品种")
        if beijing_stocks:
            print(f"  示例: {beijing_stocks[:5]}...")

        # 获取T+0基金
        t0_funds = parser.get_t0_funds()
        print(f"T+0基金: {len(t0_funds)} 个品种")
        if t0_funds:
            print(f"  示例: {t0_funds[:5]}...")

        # 获取可转债
        convertible_bonds = parser.get_convertible_bonds()
        print(f"含可转债: {len(convertible_bonds)} 个品种")
        if convertible_bonds:
            print(f"  示例: {convertible_bonds[:5]}...")

        # 获取所有目标品种
        all_targets = parser.get_all_target_stocks()
        print(f"所有目标品种: {len(all_targets)} 个品种")

        # 分析板块分布
        print("\n板块分布分析...")
        target_blocks = parser.get_target_blocks()

        for block_name, stocks in target_blocks.items():
            print(f"  {block_name}: {len(stocks)} 个品种")

        # 检查具体的融资融券板块
        print("\n检查融资融券板块中的北证A股...")
        financing_blocks = [name for name in df["blockname"].unique() if "融资融券" in str(name)]
        print(f"融资融券相关板块: {financing_blocks}")

        # 检查T+0基金板块
        t0_blocks = [name for name in df["blockname"].unique() if "T+0基金" in str(name)]
        print(f"T+0基金相关板块: {t0_blocks}")

        # 检查可转债板块
        bond_blocks = [name for name in df["blockname"].unique() if "可转债" in str(name)]
        print(f"可转债相关板块: {bond_blocks}")

        print("\n" + "=" * 60)
        print("spblock.dat解析测试完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n✗ 测试失败: {e}")
        logger.exception("测试过程中发生异常")
        sys.exit(1)


if __name__ == "__main__":
    test_spblock_parsing()
