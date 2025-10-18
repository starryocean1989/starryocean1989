# -*- coding: utf-8 -*-
"""调试无效品种数据分析."""

import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def debug_invalid_symbols():
    """调试无效品种的具体原因."""

    # 模拟后端返回的品种数据结构（基于实际观察）
    sample_symbols = [
        # 有效品种示例
        {
            "symbol": "601318",
            "code": "601318",
            "name": "中国平安",
            "exchange": "上交所",
            "product_type": "股票",
        },
        # 可能的无效品种示例
        {
            "symbol": "000001",
            "code": "000001",
            "name": "",  # 名称为空
            "exchange": "深交所",
            "product_type": "股票",
        },
        {
            "symbol": "600000",
            "code": "600000",
            "name": "   ",  # 名称只有空白字符
            "exchange": "上交所",
            "product_type": "股票",
        },
        {
            "symbol": "",
            "code": "",  # 代码为空
            "name": "浦发银行",
            "exchange": "上交所",
            "product_type": "股票",
        },
        # 非字典格式（理论上不应该出现）
        "INVALID_STRING_DATA",
        # 嵌套字典格式（理论上也不应该出现）
        {"data": {"symbol": "000002", "name": "万科A"}},
    ]

    print("=" * 60)
    print("无效品种数据分析")
    print("=" * 60)

    def extract_symbol_code(symbol_data):
        """模拟品种代码提取逻辑"""
        if not isinstance(symbol_data, dict):
            return ""
        return str(symbol_data.get("symbol") or symbol_data.get("code") or "")

    def extract_symbol_name(symbol_data):
        """模拟品种名称提取逻辑"""
        if not isinstance(symbol_data, dict):
            return ""
        return str(symbol_data.get("name") or "")

    success_count = 0
    error_count = 0
    invalid_details = []

    for i, symbol in enumerate(sample_symbols):
        try:
            if isinstance(symbol, dict):
                code = extract_symbol_code(symbol)
                name = extract_symbol_name(symbol)

                print(f"\n品种 {i+1}:")
                print(f"  数据: {symbol}")
                print(f"  代码: '{code}'")
                print(f"  名称: '{name}'")
                print(f"  名称.strip(): '{name.strip()}'")

                # 检查有效性条件
                is_valid = code and name and name.strip()

                if is_valid:
                    print("  ✅ 有效品种")
                    success_count += 1
                else:
                    print("  ❌ 无效品种")
                    print(f"     原因: code='{code}', name='{name}', name.strip()='{name.strip()}'")
                    error_count += 1
                    invalid_details.append(
                        {
                            "index": i + 1,
                            "code": code,
                            "name": name,
                            "reason": (
                                "code为空"
                                if not code
                                else "name为空" if not name else "name只有空白字符"
                            ),
                        }
                    )
            else:
                print(f"\n品种 {i+1}: ❌ 非字典格式数据: {symbol}")
                error_count += 1
                invalid_details.append({"index": i + 1, "data": symbol, "reason": "非字典格式"})

        except Exception as e:
            print(f"\n品种 {i+1}: ❌ 处理异常: {e}")
            error_count += 1
            invalid_details.append({"index": i + 1, "error": str(e), "reason": "处理异常"})

    print(f"\n{'='*60}")
    print(f"统计结果: {success_count} 个有效品种, {error_count} 个无效品种")

    if invalid_details:
        print(f"\n无效品种详情:")
        for detail in invalid_details:
            if "data" in detail:
                print(f"  品种 {detail['index']}: {detail['reason']} - {detail['data']}")
            elif "error" in detail:
                print(f"  品种 {detail['index']}: {detail['reason']} - {detail['error']}")
            else:
                print(
                    f"  品种 {detail['index']}: {detail['reason']} (code='{detail['code']}', name='{detail['name']}')"
                )

    print(f"{'='*60}")

    # 分析常见无效品种模式
    print("\n常见无效品种模式分析:")
    print("1. 名称为空: name=''")
    print("2. 名称只有空白字符: name='   '")
    print("3. 代码为空: code=''")
    print("4. 非字典格式数据")
    print("5. 数据结构异常")

    print("\n可能的原因:")
    print("• 数据源API返回不完整的数据")
    print("• 数据解析过程中丢失了关键字段")
    print("• 缓存数据损坏")
    print("• 新增品种但名称尚未同步")

    print(f"{'='*60}")


if __name__ == "__main__":
    debug_invalid_symbols()
