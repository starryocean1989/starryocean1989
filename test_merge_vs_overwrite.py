# -*- coding: utf-8 -*-
"""
性能对比测试：增量模式 vs 覆盖模式
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def test_overwrite_mode():
    """测试覆盖模式性能"""
    print("\n" + "=" * 70)
    print("测试1: 覆盖模式性能")
    print("=" * 70)

    try:
        from backend.infrastructure.data_module_vnpy.data_readers.tdx_reader import (
            TdxBinaryReader,
        )

        tdx_path = Path("C:\\new_tdx")
        reader = TdxBinaryReader(source_path=tdx_path)

        # 测试品种
        test_symbols = ["600000", "600036", "600519", "600900", "601318"]

        print(f"\n测试品种: {len(test_symbols)} 个")
        print(f"保存模式: 覆盖（merge=False）")

        # 计时开始
        start_time = time.time()

        for symbol in test_symbols:
            # 读取
            raw_data = reader.read(symbol=symbol, data_type="day", market="sh")
            # 标准化
            df = reader.standardize(raw_data)
            # 保存（覆盖模式）
            reader.save(df, merge=False)

        # 计时结束
        elapsed = time.time() - start_time

        print(f"\n✅ 覆盖模式完成")
        print(f"   总耗时: {elapsed:.2f} 秒")
        print(f"   平均每个品种: {elapsed/len(test_symbols):.2f} 秒")

        return elapsed

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return None


def test_merge_mode():
    """测试增量模式性能"""
    print("\n" + "=" * 70)
    print("测试2: 增量模式性能")
    print("=" * 70)

    try:
        from backend.infrastructure.data_module_vnpy.data_readers.tdx_reader import (
            TdxBinaryReader,
        )

        tdx_path = Path("C:\\new_tdx")
        reader = TdxBinaryReader(source_path=tdx_path)

        # 测试品种（和覆盖模式相同）
        test_symbols = ["600000", "600036", "600519", "600900", "601318"]

        print(f"\n测试品种: {len(test_symbols)} 个")
        print(f"保存模式: 增量（merge=True）")

        # 计时开始
        start_time = time.time()

        for symbol in test_symbols:
            # 读取
            raw_data = reader.read(symbol=symbol, data_type="day", market="sh")
            # 标准化
            df = reader.standardize(raw_data)
            # 保存（增量模式）
            reader.save(df, merge=True)

        # 计时结束
        elapsed = time.time() - start_time

        print(f"\n✅ 增量模式完成")
        print(f"   总耗时: {elapsed:.2f} 秒")
        print(f"   平均每个品种: {elapsed/len(test_symbols):.2f} 秒")

        return elapsed

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback

        traceback.print_exc()
        return None


def analyze_performance():
    """分析性能差异"""
    print("\n" + "=" * 70)
    print("性能对比分析")
    print("=" * 70)

    # 测试覆盖模式
    overwrite_time = test_overwrite_mode()

    # 等待1秒
    time.sleep(1)

    # 测试增量模式
    merge_time = test_merge_mode()

    # 对比分析
    print("\n" + "=" * 70)
    print("性能对比结果")
    print("=" * 70)

    if overwrite_time and merge_time:
        print(f"\n覆盖模式: {overwrite_time:.2f} 秒")
        print(f"增量模式: {merge_time:.2f} 秒")
        print(
            f"增量额外耗时: {merge_time - overwrite_time:.2f} 秒 (+{(merge_time/overwrite_time - 1)*100:.1f}%)"
        )

        print("\n" + "-" * 70)
        print("结论分析:")
        print("-" * 70)

        if merge_time < overwrite_time * 1.2:
            print("✅ 增量模式性能损失 < 20%，推荐使用增量模式")
        elif merge_time < overwrite_time * 1.5:
            print("⚠️  增量模式性能损失 20-50%，可根据场景选择")
        else:
            print("❌ 增量模式性能损失 > 50%，首次导入建议用覆盖模式")

        print("\n使用建议:")
        print("  - 首次全量导入: 覆盖模式（更快）")
        print("  - 日常增量更新: 增量模式（安全）")
        print("  - 数据修复: 增量模式（不丢失数据）")


if __name__ == "__main__":
    analyze_performance()
