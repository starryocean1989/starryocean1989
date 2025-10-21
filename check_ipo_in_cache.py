# -*- coding: utf-8 -*-
"""检查stock_list_classified.json中的ipo_date字段"""
import json
from pathlib import Path

cache_file = Path("data/cache/stock_list_classified.json")
with open(cache_file, "r", encoding="utf-8") as f:
    data = json.load(f)

all_stocks = []
for category, stocks in data["data"]["classified"].items():
    all_stocks.extend(stocks)

with_ipo = [s for s in all_stocks if "ipo_date" in s and s["ipo_date"]]

print(f"品种总数: {len(all_stocks)}")
print(f"包含ipo_date字段的品种数: {len(with_ipo)}")

if len(with_ipo) > 0:
    print(f"\n前5个包含ipo_date的品种示例:")
    for stock in with_ipo[:5]:
        print(f"  {stock['code']} {stock['name']}: {stock.get('ipo_date')}")
else:
    print("\n⚠️ 没有品种包含ipo_date字段")

if len(with_ipo) < len(all_stocks):
    print(f"\n⚠️ 有 {len(all_stocks) - len(with_ipo)} 个品种缺少ipo_date字段")
