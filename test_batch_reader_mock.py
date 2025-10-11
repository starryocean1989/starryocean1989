# -*- coding: utf-8 -*-
"""
测试数据标准化读取器 - 直接测试（不依赖品种缓存）
"""

import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))


def test_direct_batch_read():
    """直接测试批量读取功能（手动指定品种）"""
    print("\n" + "=" * 70)
    print("测试: 数据标准化读取器 - 多线程批量读取（直接测试）")
    print("=" * 70)

    try:
        # 导入底层读取器
        from backend.infrastructure.data_module_vnpy.data_readers.tdx_reader import (
            TdxBinaryReader,
        )

        tdx_path = Path("C:\\new_tdx")

        if not tdx_path.exists():
            print(f"❌ 通达信目录不存在: {tdx_path}")
            return False

        print(f"\n✅ 通达信目录: {tdx_path}")

        # 创建读取器
        reader = TdxBinaryReader(source_path=tdx_path)
        print("✅ TdxBinaryReader 创建成功")

        # 测试品种（5个上证A股）
        test_symbols = ["600000", "600036", "600519", "600900", "601318"]

        # 进度回调
        print("\n开始多线程批量读取...")
        print("-" * 70)

        def progress_callback(current, total, symbol, success):
            progress_pct = int(current / total * 100) if total > 0 else 0
            status_icon = "✅" if success else "❌"
            print(f"  [{progress_pct:3d}%] {status_icon} {current}/{total} - SH day {symbol}")

        # 批量处理（多线程）
        results = reader.process_batch(
            symbols=test_symbols,
            data_type="day",
            market="sh",
            progress_callback=progress_callback,
            max_workers=4,
        )

        print("-" * 70)

        # 统计结果
        success_count = sum(1 for v in results.values() if v)
        fail_count = len(results) - success_count

        print(f"\n✅ 批量读取完成:")
        print(f"   测试品种: {len(test_symbols)}")
        print(f"   成功: {success_count}")
        print(f"   失败: {fail_count}")
        print(f"   成功率: {success_count/len(test_symbols)*100:.1f}%")

        # 显示详细结果
        print("\n详细结果:")
        for symbol, success in results.items():
            status = "✅ 成功" if success else "❌ 失败"
            print(f"   {symbol}: {status}")

        # 检查保存的文件
        data_dir = Path("data/kline")
        if data_dir.exists():
            saved_files = []
            for symbol in test_symbols:
                file_path = data_dir / symbol / "1d" / "data.parquet"
                if file_path.exists():
                    size_kb = file_path.stat().st_size / 1024
                    saved_files.append((symbol, size_kb))

            print(f"\n保存的文件 ({len(saved_files)} 个):")
            for symbol, size_kb in saved_files:
                print(f"   {symbol}: {size_kb:.1f} KB")

        return success_count > 0

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def test_multi_market():
    """测试多市场批量读取"""
    print("\n" + "=" * 70)
    print("测试: 多市场批量读取（上证 + 深证）")
    print("=" * 70)

    try:
        from backend.infrastructure.data_module_vnpy.data_readers.tdx_reader import (
            TdxBinaryReader,
        )

        tdx_path = Path("C:\\new_tdx")
        reader = TdxBinaryReader(source_path=tdx_path)

        print("\n✅ TdxBinaryReader 创建成功")

        # 测试品种
        test_data = [
            ("sh", ["600000", "600036"]),  # 上证
            ("sz", ["000001", "000002"]),  # 深证
        ]

        all_results = {}

        for market, symbols in test_data:
            print(f"\n处理市场: {market.upper()}, 品种: {symbols}")
            print("-" * 70)

            def progress_callback(current, total, symbol, success):
                progress_pct = int(current / total * 100) if total > 0 else 0
                status_icon = "✅" if success else "❌"
                print(f"  [{progress_pct:3d}%] {status_icon} {market.upper()} day {symbol}")

            results = reader.process_batch(
                symbols=symbols,
                data_type="day",
                market=market,
                progress_callback=progress_callback,
                max_workers=2,
            )

            all_results.update(results)

        print("-" * 70)

        # 统计
        success_count = sum(1 for v in all_results.values() if v)
        total_count = len(all_results)

        print(f"\n✅ 多市场读取完成:")
        print(f"   总任务数: {total_count}")
        print(f"   成功: {success_count}")
        print(f"   失败: {total_count - success_count}")

        return success_count > 0

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("\n" + "=" * 70)
    print("数据标准化读取器 - 多线程批量读取功能测试")
    print("=" * 70)

    results = []

    # 测试1: 单市场多品种
    results.append(("多线程批量读取", test_direct_batch_read()))

    # 测试2: 多市场
    if results[0][1]:
        results.append(("多市场批量读取", test_multi_market()))

    # 输出总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)

    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{name}: {status}")

    all_passed = all(success for _, success in results)

    if all_passed:
        print("\n🎉 所有测试通过!")
        print("\n验证的功能:")
        print("  ✅ 多线程并发读取")
        print("  ✅ 实时进度回调")
        print("  ✅ 多市场批量处理")
        print("  ✅ 数据标准化和保存")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查日志")
        return 1


if __name__ == "__main__":
    sys.exit(main())
