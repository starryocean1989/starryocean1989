"""检查数据实际状态：到底有多少品种有数据，多少品种过时"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from backend.infrastructure.data_module_vnpy.data_quality import (
    IPODateCache,
    StorageManager,
    DataValidator,
)
from backend.infrastructure.data_module_vnpy.data_module import config_manager


def main():
    """检查数据状态"""
    print("=" * 80)
    print("数据状态诊断报告")
    print("=" * 80)

    # 1. 加载参考品种列表（from IPO cache）
    ipo_cache = IPODateCache()  # 使用默认缓存文件路径
    reference_symbols = list(ipo_cache._memory_cache.keys())
    print(f"\n1. 参考品种总数: {len(reference_symbols)}")

    # 2. 检查本地有数据的品种
    storage_manager = StorageManager()
    local_symbols = storage_manager.get_local_data_index(use_cache=False)
    print(f"2. 本地有数据的品种数: {len(local_symbols)}")

    # 3. 计算缺失品种
    missing_symbols = [s for s in reference_symbols if s not in local_symbols]
    print(f"3. 缺失数据的品种数: {len(missing_symbols)}")

    # 4. 检查前10个有数据的品种（看看数据日期）
    print("\n" + "=" * 80)
    print("前10个有数据品种的最新数据日期：")
    print("=" * 80)

    validator = DataValidator()  # 不需要参数，自己创建 StorageManager

    for i, symbol in enumerate(list(local_symbols)[:10], 1):
        try:
            freshness = validator.check_data_freshness(symbol, "1d")
            if freshness["has_data"]:
                print(
                    f"{i:2d}. {symbol:12s} | 最新日期: {freshness['local_latest_date']} | "
                    f"滞后: {freshness['gap_days']}天 | 最新交易日: {freshness['latest_trading_day']}"
                )
            else:
                print(f"{i:2d}. {symbol:12s} | 无数据")
        except Exception as e:
            print(f"{i:2d}. {symbol:12s} | 检查失败: {e}")

    # 5. 统计滞后>1天的品种
    print("\n" + "=" * 80)
    print("统计数据新鲜度（可能需要1-2分钟）...")
    print("=" * 80)

    outdated_count = 0
    fresh_count = 0
    gap_days_list = []

    # 只检查有数据的品种（限制前100个，避免太慢）
    check_limit = min(100, len(local_symbols))
    for i, symbol in enumerate(list(local_symbols)[:check_limit], 1):
        try:
            freshness = validator.check_data_freshness(symbol, "1d")
            if freshness["has_data"]:
                gap_days = freshness["gap_days"]
                if gap_days > 1:
                    outdated_count += 1
                else:
                    fresh_count += 1
                if gap_days >= 0:
                    gap_days_list.append(gap_days)
        except Exception:
            pass

        if i % 20 == 0:
            print(f"  已检查: {i}/{check_limit}")

    avg_gap = int(sum(gap_days_list) / len(gap_days_list)) if gap_days_list else 0

    print(f"\n✓ 检查完成（前{check_limit}个有数据的品种）:")
    print(f"  - 数据较新（滞后<=1天）: {fresh_count}")
    print(f"  - 数据过时（滞后>1天）: {outdated_count}")
    print(f"  - 平均滞后: {avg_gap}天")

    # 6. 总结
    print("\n" + "=" * 80)
    print("诊断结论")
    print("=" * 80)
    print(f"1. 总品种数: {len(reference_symbols)}")
    print(
        f"2. 有数据的品种数: {len(local_symbols)} ({len(local_symbols)/len(reference_symbols)*100:.1f}%)"
    )
    print(
        f"3. 缺失数据的品种数: {len(missing_symbols)} ({len(missing_symbols)/len(reference_symbols)*100:.1f}%)"
    )
    print(f"4. 有数据但过时的品种数（前{check_limit}个）: {outdated_count}")
    print(f"\n💡 UI显示的问题：")
    print(f'   - 当前「过时」指标只统计"有数据但滞后>1天"的品种')
    print(f'   - 如果您从未下载过数据，"缺失数据"={len(missing_symbols)}，"过时"=0')
    print(f"   - 这个语义是混淆的！")
    print(f"\n建议：")
    print(f"   - 「缺失」应该表示：品种在参考列表中，但本地没有任何数据文件")
    print(f"   - 「过时」应该表示：品种有数据，但数据日期滞后>1天")
    print(f'   - 两者加起来才是"需要下载/更新的品种数"')


if __name__ == "__main__":
    main()
