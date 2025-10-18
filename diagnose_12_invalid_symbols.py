# -*- coding: utf-8 -*-
"""精确诊断12个无效品种的根本原因"""

import json
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def clean_symbol_name_encoding(name: str) -> str:
    """清理品种名称中的乱码字符（与UI代码完全一致）"""
    if not name:
        return ""
    
    cleaned = name.replace("\x00", "")
    cleaned = cleaned.replace("\u0000", "")
    cleaned = cleaned.replace("\ufffd", "")
    cleaned = cleaned.strip()
    
    return cleaned


def extract_symbol_code(symbol_data):
    """提取品种代码（与UI代码完全一致）"""
    if not isinstance(symbol_data, dict):
        return ""
    return str(symbol_data.get("symbol") or symbol_data.get("code") or "")


def diagnose_invalid_symbols():
    """精确诊断12个无效品种"""
    
    print("=" * 80)
    print("12个无效品种精确诊断")
    print("=" * 80)
    
    # 加载品种缓存数据
    cache_file = "data/cache/stock_list_classified.json"
    
    try:
        with open(cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)
    except Exception as e:
        print(f"❌ 无法加载缓存文件: {e}")
        return
    
    print(f"\n📊 缓存数据基本信息:")
    print(f"  总品种数: {cache_data.get('total_count', 0)}")
    print(f"  市场分类数: {len(cache_data.get('classified', {}))}")
    
    # 收集所有品种
    all_symbols = []
    for market_type, symbols in cache_data.get("classified", {}).items():
        for symbol in symbols:
            all_symbols.append({"market": market_type, "data": symbol})
    
    print(f"  实际品种总数: {len(all_symbols)}")
    
    # 模拟UI的处理逻辑，找出无效品种
    print("\n" + "=" * 80)
    print("开始模拟UI处理逻辑...")
    print("=" * 80)
    
    valid_symbols = []
    invalid_symbols = []
    
    for item in all_symbols:
        symbol = item["data"]
        market_type = item["market"]
        
        try:
            if isinstance(symbol, dict):
                # 提取代码和名称（与UI代码完全一致）
                code = extract_symbol_code(symbol)
                raw_name = str(symbol.get("name") or "")
                cleaned_name = clean_symbol_name_encoding(raw_name)
                
                # 使用清理后的名称作为最终名称
                final_name = cleaned_name
                
                # 判断是否有效（与UI代码完全一致）
                if code and final_name:
                    valid_symbols.append({
                        "code": code,
                        "name": final_name,
                        "market": market_type
                    })
                else:
                    # 这就是"无效品种"
                    invalid_symbols.append({
                        "code": code,
                        "raw_name": raw_name,
                        "cleaned_name": cleaned_name,
                        "final_name": final_name,
                        "market": market_type,
                        "reason": "代码为空" if not code else "名称为空",
                        "full_data": symbol
                    })
            else:
                invalid_symbols.append({
                    "reason": "非字典类型",
                    "data": symbol
                })
        except Exception as e:
            invalid_symbols.append({
                "reason": f"处理异常: {e}",
                "data": symbol
            })
    
    print(f"\n✅ 有效品种: {len(valid_symbols)}")
    print(f"❌ 无效品种: {len(invalid_symbols)}")
    
    # 详细分析无效品种
    if invalid_symbols:
        print("\n" + "=" * 80)
        print(f"无效品种详细分析（共{len(invalid_symbols)}个）")
        print("=" * 80)
        
        for i, invalid in enumerate(invalid_symbols, 1):
            print(f"\n【无效品种 #{i}】")
            print(f"  市场分类: {invalid.get('market', 'N/A')}")
            print(f"  品种代码: '{invalid.get('code', 'N/A')}'")
            print(f"  原始名称: '{invalid.get('raw_name', 'N/A')}'")
            print(f"  清理后名称: '{invalid.get('cleaned_name', 'N/A')}'")
            print(f"  最终名称: '{invalid.get('final_name', 'N/A')}'")
            print(f"  无效原因: {invalid.get('reason', 'N/A')}")
            
            # 深度分析原始名称的字节内容
            raw_name = invalid.get('raw_name', '')
            if raw_name:
                print(f"  原始名称字节分析:")
                print(f"    长度: {len(raw_name)}")
                print(f"    字节表示: {repr(raw_name)}")
                has_null = '\x00' in raw_name
                has_replacement = '\ufffd' in raw_name
                print(f"    包含\\x00: {'是' if has_null else '否'}")
                print(f"    包含\\ufffd: {'是' if has_replacement else '否'}")
            
            # 显示完整的品种数据
            full_data = invalid.get('full_data', {})
            if full_data:
                print(f"  完整数据: {json.dumps(full_data, ensure_ascii=False)}")
    
    # 总结
    print("\n" + "=" * 80)
    print("🎯 诊断结论")
    print("=" * 80)
    
    # 按无效原因分组统计
    reason_stats = {}
    for invalid in invalid_symbols:
        reason = invalid.get("reason", "未知")
        reason_stats[reason] = reason_stats.get(reason, 0) + 1
    
    print("\n📊 无效原因分布:")
    for reason, count in reason_stats.items():
        print(f"  {reason}: {count} 个")
    
    print("\n💡 根本原因分析:")
    if any("名称为空" in inv.get("reason", "") for inv in invalid_symbols):
        print("  ✓ 存在名称字段经清理后变为空字符串的品种")
        print("  ✓ 这些品种的原始名称可能完全由\\x00等乱码字符组成")
    
    if any("代码为空" in inv.get("reason", "") for inv in invalid_symbols):
        print("  ✓ 存在代码字段为空的品种")
        print("  ✓ 这可能是数据源本身的问题")
    
    print("\n🔧 建议修复方案:")
    print("  方案1: 对于名称为空的品种，使用代码作为fallback名称")
    print("  方案2: 对于代码为空的品种，检查数据源并过滤掉")
    print("  方案3: 向上游数据源（通达信API或配置文件）追溯原始数据")
    
    print("=" * 80)
    
    return invalid_symbols


if __name__ == "__main__":
    diagnose_invalid_symbols()

