# -*- coding: utf-8 -*-
"""
诊断北证品种代码和文件名匹配问题
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def check_bj_files():
    """检查北证文件实际存在的品种"""
    print("\n" + "=" * 70)
    print("诊断: 北证数据文件检查")
    print("=" * 70)

    bj_dir = Path("C:\\new_tdx\\vipdoc\\bj\\lday")

    if not bj_dir.exists():
        print(f"❌ 目录不存在: {bj_dir}")
        return

    # 获取所有.day文件
    day_files = list(bj_dir.glob("*.day"))
    print(f"\n✅ 找到 {len(day_files)} 个日线文件")

    # 提取品种代码
    symbols = []
    for f in day_files[:20]:  # 显示前20个
        # 文件名格式: bj920000.day
        name = f.stem  # bj920000
        if name.startswith("bj"):
            symbol = name[2:]  # 920000
            symbols.append(symbol)
            print(f"   文件: {f.name} → 品种代码: {symbol}")

    # 测试读取一个存在的品种
    print("\n" + "=" * 70)
    print("测试: 读取一个存在的北证品种")
    print("=" * 70)

    if symbols:
        test_symbol = symbols[0]
        print(f"\n测试品种: {test_symbol}")

        from backend.infrastructure.data_module_vnpy.data_readers.tdx_reader import (
            TdxBinaryReader,
        )

        tdx_path = Path("C:\\new_tdx")
        reader = TdxBinaryReader(source_path=tdx_path)

        try:
            # 读取数据
            raw_data = reader.read(symbol=test_symbol, data_type="day", market="bj")
            print(f"✅ 读取成功: {len(raw_data)} 条记录")

            # 标准化
            df = reader.standardize(raw_data)
            print(f"✅ 标准化成功: {len(df)} 条记录")

            # 保存
            success = reader.save(df)
            if success:
                print(f"✅ 保存成功")
            else:
                print(f"❌ 保存失败")

        except Exception as e:
            print(f"❌ 处理失败: {e}")
            import traceback

            traceback.print_exc()


if __name__ == "__main__":
    check_bj_files()
