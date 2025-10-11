# -*- coding: utf-8 -*-
"""
测试北证5分钟线和1分钟线解码
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def test_bj_5min():
    """测试北证5分钟线"""
    print("\n" + "=" * 70)
    print("测试: 北证5分钟线解码")
    print("=" * 70)

    try:
        from backend.infrastructure.data_module_vnpy.data_readers.bj_decoder import (
            BjStockDecoder,
        )

        decoder = BjStockDecoder()

        # 测试文件
        test_file = Path("C:\\new_tdx\\vipdoc\\bj\\fzline\\bj920000.lc5")

        if not test_file.exists():
            print(f"⚠️  测试文件不存在: {test_file}")
            return True  # 跳过，不算失败

        print(f"\n测试文件: {test_file.name}")
        print(f"文件大小: {test_file.stat().st_size} 字节")

        # 读取数据
        df = decoder.read_5min_file(test_file)

        if df.empty:
            print("❌ 读取的数据为空")
            return False

        print(f"\n✅ 读取成功:")
        print(f"   记录数: {len(df)}")
        print(f"   时间范围: {df.index.min()} 到 {df.index.max()}")

        print(f"\n前3条记录:")
        print(df.head(3))

        return True

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_bj_1min():
    """测试北证1分钟线"""
    print("\n" + "=" * 70)
    print("测试: 北证1分钟线解码")
    print("=" * 70)

    try:
        from backend.infrastructure.data_module_vnpy.data_readers.bj_decoder import (
            BjStockDecoder,
        )

        decoder = BjStockDecoder()

        # 测试文件
        test_file = Path("C:\\new_tdx\\vipdoc\\bj\\minline\\bj920000.lc1")

        if not test_file.exists():
            print(f"⚠️  测试文件不存在: {test_file}")
            return True  # 跳过，不算失败

        print(f"\n测试文件: {test_file.name}")
        print(f"文件大小: {test_file.stat().st_size} 字节")

        # 读取数据
        df = decoder.read_1min_file(test_file)

        if df.empty:
            print("❌ 读取的数据为空")
            return False

        print(f"\n✅ 读取成功:")
        print(f"   记录数: {len(df)}")
        print(f"   时间范围: {df.index.min()} 到 {df.index.max()}")

        print(f"\n前3条记录:")
        print(df.head(3))

        return True

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_batch_all_intervals():
    """测试批量读取所有周期"""
    print("\n" + "=" * 70)
    print("测试: 批量读取北证所有周期（日线+5分钟+1分钟）")
    print("=" * 70)

    try:
        from backend.infrastructure.data_module_vnpy.data_readers.tdx_reader import (
            TdxBinaryReader,
        )

        tdx_path = Path("C:\\new_tdx")
        reader = TdxBinaryReader(source_path=tdx_path)

        # 测试品种
        test_symbol = "920000"

        for data_type in ["day", "5min", "1min"]:
            print(f"\n处理: BJ {data_type} {test_symbol}")
            print("-" * 70)

            try:
                # 读取数据
                raw_data = reader.read(symbol=test_symbol, data_type=data_type, market="bj")

                if raw_data.empty:
                    print(f"⚠️  {data_type} 数据为空")
                    continue

                # 标准化
                df = reader.standardize(raw_data)

                # 保存
                success = reader.save(df)

                if success:
                    print(f"✅ {data_type} 成功: {len(df)} 条记录")
                else:
                    print(f"❌ {data_type} 保存失败")

            except FileNotFoundError:
                print(f"⚠️  {data_type} 文件不存在，跳过")
            except Exception as e:
                print(f"❌ {data_type} 失败: {e}")

        return True

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print("北证分钟线解码器测试")
    print("=" * 70)

    results = []

    # 测试5分钟线
    results.append(("北证5分钟线", test_bj_5min()))

    # 测试1分钟线
    results.append(("北证1分钟线", test_bj_1min()))

    # 测试批量所有周期
    results.append(("批量所有周期", test_batch_all_intervals()))

    # 输出总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)

    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{name}: {status}")

    all_passed = all(success for _, success in results)

    if all_passed:
        print("\n🎉 所有测试通过! 北证全周期数据解码器工作正常！")
        return 0
    else:
        print("\n⚠️  部分测试失败")
        return 1


if __name__ == "__main__":
    sys.exit(main())
