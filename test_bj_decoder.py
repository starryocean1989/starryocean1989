# -*- coding: utf-8 -*-
"""
测试北证数据解码器
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def test_bj_decoder():
    """测试北证解码器"""
    print("\n" + "=" * 70)
    print("测试: 北证数据解码器")
    print("=" * 70)

    try:
        from backend.infrastructure.data_module_vnpy.data_readers.bj_decoder import (
            BjStockDecoder,
        )

        # 创建解码器
        decoder = BjStockDecoder()
        print("\n✅ BjStockDecoder 创建成功")

        # 测试读取一个北证日线文件
        test_file = Path("C:\\new_tdx\\vipdoc\\bj\\lday\\bj920000.day")

        if not test_file.exists():
            print(f"❌ 测试文件不存在: {test_file}")
            return False

        print(f"\n测试文件: {test_file}")
        print(f"文件大小: {test_file.stat().st_size} 字节")

        # 读取数据
        df = decoder.read_day_file(test_file)

        if df.empty:
            print("❌ 读取的数据为空")
            return False

        print(f"\n✅ 读取成功:")
        print(f"   记录数: {len(df)}")
        print(f"   列名: {df.columns.tolist()}")
        print(f"   时间范围: {df.index.min()} 到 {df.index.max()}")

        print(f"\n前5条记录:")
        print(df.head())

        print(f"\n最新5条记录:")
        print(df.tail())

        return True

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_bj_batch():
    """测试批量读取北证数据"""
    print("\n" + "=" * 70)
    print("测试: 批量读取北证数据（使用TdxBinaryReader）")
    print("=" * 70)

    try:
        from backend.infrastructure.data_module_vnpy.data_readers.tdx_reader import (
            TdxBinaryReader,
        )

        tdx_path = Path("C:\\new_tdx")
        reader = TdxBinaryReader(source_path=tdx_path)

        print("\n✅ TdxBinaryReader 创建成功")

        # 测试北证品种
        test_symbols = ["920000", "920001", "920002"]

        print(f"\n测试品种: {test_symbols}")
        print("-" * 70)

        def progress_callback(current, total, symbol, success):
            progress_pct = int(current / total * 100) if total > 0 else 0
            status_icon = "✅" if success else "❌"
            print(f"  [{progress_pct:3d}%] {status_icon} BJ day {symbol}")

        # 批量处理
        results = reader.process_batch(
            symbols=test_symbols,
            data_type="day",
            market="bj",
            progress_callback=progress_callback,
            max_workers=2,
        )

        print("-" * 70)

        # 统计
        success_count = sum(1 for v in results.values() if v)
        print(f"\n✅ 批量读取完成:")
        print(f"   总数: {len(test_symbols)}")
        print(f"   成功: {success_count}")
        print(f"   失败: {len(test_symbols) - success_count}")

        # 验证保存的文件
        if success_count > 0:
            data_dir = Path("data/kline")
            for symbol in test_symbols:
                file_path = data_dir / symbol / "1d" / "data.parquet"
                if file_path.exists():
                    import pandas as pd

                    df = pd.read_parquet(file_path)
                    print(f"\n✅ {symbol} 已保存: {len(df)} 条记录")

        return success_count > 0

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print("北证数据解码器测试")
    print("=" * 70)

    results = []

    # 测试1: 单文件解码
    results.append(("北证解码器", test_bj_decoder()))

    # 测试2: 批量读取
    if results[0][1]:
        results.append(("批量读取北证", test_bj_batch()))

    # 输出总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)

    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{name}: {status}")

    all_passed = all(success for _, success in results)

    if all_passed:
        print("\n🎉 所有测试通过! 北证数据解码器工作正常！")
        return 0
    else:
        print("\n⚠️  部分测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
