# -*- coding: utf-8 -*-
import json
from pathlib import Path

cache_file = Path("data/cache/stock_list_classified.json")

if cache_file.exists():
    with open(cache_file, encoding="utf-8") as f:
        cache = json.load(f)

    classified = cache.get("classified", {})

    print("品种缓存统计:")
    print(f"上证A股: {len(classified.get('上证A股', []))} 个")
    print(f"深证A股: {len(classified.get('深证A股', []))} 个")
    print(f"北证A股: {len(classified.get('北证A股', []))} 个")
    print(f"T+0基金: {len(classified.get('T+0基金', []))} 个")
    print(f"含可转债: {len(classified.get('含可转债', []))} 个")

    bj_stocks = classified.get("北证A股", [])
    if bj_stocks:
        print(f"\n北证前10个品种: {bj_stocks[:10]}")
    else:
        print("\n⚠️  北证品种列表为空！")
else:
    print(f"❌ 缓存文件不存在: {cache_file}")
