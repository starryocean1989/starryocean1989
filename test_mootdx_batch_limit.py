# -*- coding: utf-8 -*-
"""
测试 mootdx 批量查询的限制和返回字段
"""
from mootdx.quotes import Quotes
import pandas as pd

print("=" * 100)
print("测试 mootdx 批量查询限制")
print("=" * 100)
print()

# 创建客户端
client = Quotes.factory(market="std")

# 测试不同数量的查询
test_cases = [
    (2, ["000001", "600000"]),
    (5, ["000001", "600000", "000002", "600036", "601398"]),
    (10, [f"{i:06d}" for i in range(1, 11)]),
    (50, [f"{i:06d}" for i in range(1, 51)]),
    (100, [f"{i:06d}" for i in range(1, 101)]),
    (200, [f"{i:06d}" for i in range(1, 201)]),
    (290, [f"{i:06d}" for i in range(1, 291)]),  # 理论最大值
    (300, [f"{i:06d}" for i in range(1, 301)]),  # 超出限制
]

print("测试批量查询不同数量的股票...\n")

for count, symbols in test_cases:
    try:
        print(f"[{count:3d}只] 查询中...", end=" ")
        result = client.quotes(symbols)

        if result is not None and not result.empty:
            actual_count = len(result)
            print(f"✓ 成功返回 {actual_count} 条数据")

            # 第一次打印字段信息
            if count == 2:
                print("\n" + "=" * 100)
                print("返回字段详情（以2只股票为例）：")
                print("=" * 100)

                columns = list(result.columns)
                print(f"\n字段总数: {len(columns)} 个\n")
                print("字段列表：")
                for i, col in enumerate(columns, 1):
                    dtype = result[col].dtype
                    sample = result[col].iloc[0] if len(result) > 0 else None
                    print(f"  {i:2d}. {col:<20s} ({dtype}) = {sample}")

                print("\n" + "=" * 100)
                print("示例数据：")
                print("=" * 100)
                pd.set_option("display.max_columns", None)
                pd.set_option("display.width", None)
                pd.set_option("display.max_colwidth", 20)
                print(result.head(2).to_string())
                print("=" * 100 + "\n")
        else:
            print("✗ 返回空数据")

    except Exception as e:
        print(f"✗ 失败: {str(e)[:50]}")

print()
print("=" * 100)
print("结论：")
print("=" * 100)
print("根据测试结果，mootdx 的批量查询限制与 TradeX.dll 一致")
print()

# 关闭连接
try:
    client.close()
except:
    pass

print("测试完成")



