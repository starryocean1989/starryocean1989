# -*- coding: utf-8 -*-
"""追溯12个空名称品种的数据来源"""

import json
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def trace_empty_names():
    """追溯空名称品种的数据来源"""
    
    print("=" * 80)
    print("追溯12个空名称品种的数据来源")
    print("=" * 80)
    
    # 这12个品种的代码
    empty_name_codes = [
        '162416',  # T+0基金
        '123161', '123162', '123200', '123232', '123244',  # 可转债（深圳）
        '128076', '128081', '128132',  # 可转债（深圳）
        '111007', '113545', '113690'   # 可转债（上海）
    ]
    
    print(f"\n📊 需要追溯的品种代码: {len(empty_name_codes)} 个")
    for code in empty_name_codes:
        print(f"  - {code}")
    
    # 1. 检查缓存文件中的原始数据
    print("\n" + "=" * 80)
    print("1. 检查缓存文件 (stock_list_classified.json)")
    print("=" * 80)
    
    cache_file = "data/cache/stock_list_classified.json"
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
        
        print(f"✓ 缓存文件加载成功")
        print(f"  缓存时间: {cache_data.get('cache_time', 'N/A')}")
        
        # 在缓存中查找这些品种
        found_in_cache = []
        for market_type, symbols in cache_data.get("classified", {}).items():
            for symbol in symbols:
                code = symbol.get("code", "")
                if code in empty_name_codes:
                    found_in_cache.append({
                        "code": code,
                        "name": symbol.get("name", ""),
                        "market": market_type,
                        "market_id": symbol.get("market", -1)
                    })
        
        print(f"\n在缓存中找到: {len(found_in_cache)} 个")
        for item in found_in_cache:
            print(f"  {item['code']}: name='{item['name']}' (len={len(item['name'])}), market={item['market']}, market_id={item['market_id']}")
    
    except Exception as e:
        print(f"❌ 缓存文件读取失败: {e}")
    
    # 2. 检查配置文件
    print("\n" + "=" * 80)
    print("2. 检查配置文件")
    print("=" * 80)
    
    config_files = [
        "backend/infrastructure/data_module_vnpy/config/sz_bond.txt",
        "backend/infrastructure/data_module_vnpy/config/sh_bond.txt",
        "backend/infrastructure/data_module_vnpy/config/etf_list.txt"
    ]
    
    found_in_config = {}
    for config_file in config_files:
        if os.path.exists(config_file):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                
                print(f"\n✓ {config_file}:")
                print(f"  总行数: {len(lines)}")
                
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    
                    # 解析配置行（格式可能是：代码,名称 或 代码）
                    parts = line.split(",")
                    code = parts[0].strip()
                    
                    if code in empty_name_codes:
                        name = parts[1].strip() if len(parts) > 1 else ""
                        found_in_config[code] = {
                            "code": code,
                            "name": name,
                            "source": config_file
                        }
                        print(f"    找到: {code}, name='{name}' (len={len(name)})")
            
            except Exception as e:
                print(f"  ❌ 读取失败: {e}")
        else:
            print(f"\n⚠️  文件不存在: {config_file}")
    
    # 3. 总结
    print("\n" + "=" * 80)
    print("🎯 数据来源分析结论")
    print("=" * 80)
    
    print("\n📊 统计:")
    print(f"  空名称品种总数: {len(empty_name_codes)}")
    print(f"  缓存中名称为空: {len([x for x in found_in_cache if not x['name']])}")
    print(f"  配置文件中找到: {len(found_in_config)}")
    
    # 检查配置文件中是否也是空名称
    config_empty_count = sum(1 for v in found_in_config.values() if not v['name'])
    print(f"  配置文件中名称为空: {config_empty_count}")
    
    print("\n💡 根本原因:")
    if config_empty_count > 0:
        print("  ✓ 配置文件中这些品种的名称字段就是空的")
        print("  ✓ 这不是乱码清理的问题，而是源数据本身没有名称")
    
    print("\n🔧 正确的解决方案:")
    print("  1. 对于配置文件中的品种，如果名称为空，使用代码作为显示名称")
    print("  2. 或者从通达信API重新获取这些品种的名称信息")
    print("  3. 修改UI代码，增加fallback机制：name为空时使用code")
    
    print("\n📝 需要修改的代码位置:")
    print("  文件: ui/modules/data_center_view.py")
    print("  方法: _load_symbol_cache_for_autocomplete()")
    print("  修改: final_name = cleaned_name if cleaned_name else code")
    
    print("=" * 80)


if __name__ == "__main__":
    trace_empty_names()

