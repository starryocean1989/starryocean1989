# -*- coding: utf-8 -*-
"""验证品种数据修复效果的测试."""


def test_fix_verification():
    """测试修复后的品种缓存加载逻辑."""

    print("=" * 60)
    print("品种数据修复验证测试")
    print("=" * 60)

    # 模拟从后端获取的品种数据（包括有问题的品种）
    mock_backend_symbols = [
        # 正常品种
        {"symbol": "600000", "code": "600000", "name": "浦发银行", "exchange": "上交所"},
        {"symbol": "000002", "code": "000002", "name": "万 科Ａ\x00", "exchange": "深交所"},
        # 名称为空的品种（这就是我们发现的12个无效品种）
        {"symbol": "162416", "code": "162416", "name": "", "exchange": "深交所"},
        {"symbol": "123161", "code": "123161", "name": "", "exchange": "深交所"},
        {"symbol": "123162", "code": "123162", "name": "", "exchange": "深交所"},
        {"symbol": "123200", "code": "123200", "name": "", "exchange": "深交所"},
        {"symbol": "123232", "code": "123232", "name": "", "exchange": "深交所"},
        {"symbol": "123244", "code": "123244", "name": "", "exchange": "深交所"},
        {"symbol": "128076", "code": "128076", "name": "", "exchange": "深交所"},
        {"symbol": "128081", "code": "128081", "name": "", "exchange": "深交所"},
        {"symbol": "128132", "code": "128132", "name": "", "exchange": "深交所"},
        {"symbol": "111007", "code": "111007", "name": "", "exchange": "上交所"},
        {"symbol": "113545", "code": "113545", "name": "", "exchange": "上交所"},
        {"symbol": "113690", "code": "113690", "name": "", "exchange": "上交所"},
    ]

    def extract_symbol_code(symbol_data):
        """提取品种代码"""
        if isinstance(symbol_data, dict):
            return str(symbol_data.get("symbol") or symbol_data.get("code") or "")
        return str(symbol_data)

    def extract_symbol_name(symbol_data):
        """提取品种名称"""
        if isinstance(symbol_data, dict):
            return str(symbol_data.get("name") or "")
        return str(symbol_data)

    def clean_symbol_name_encoding(name: str) -> str:
        """清理品种名称中的乱码字符"""
        if not name:
            return ""

        # 清理常见乱码字符
        cleaned = name.replace("\x00", "")  # 移除空字符
        cleaned = cleaned.replace("\u0000", "")  # 移除Unicode空字符
        cleaned = cleaned.replace("\ufffd", "")  # 移除替换字符
        cleaned = cleaned.strip()  # 移除前后空白字符

        return cleaned

    def get_pinyin_initials(text: str) -> str:
        """获取文本的拼音首字母（模拟）"""
        try:
            from pypinyin import lazy_pinyin

            pinyin_list = lazy_pinyin(text)
            return "".join([p[0].lower() for p in pinyin_list])
        except ImportError:
            # 模拟拼音首字母生成
            return "".join([c[0].lower() for c in text.split() if c])

    # 应用修复逻辑：模拟品种缓存加载
    symbol_cache = []
    success_count = 0
    error_count = 0

    print("模拟品种缓存加载过程:")
    print("-" * 60)

    for symbol in mock_backend_symbols:
        code = extract_symbol_code(symbol)
        raw_name = extract_symbol_name(symbol)
        cleaned_name = clean_symbol_name_encoding(raw_name)

        # 应用修复逻辑：如果清理后名称为空，使用代码作为名称
        final_name = cleaned_name if cleaned_name.strip() else code

        print(f"品种 {code}:")
        print(f"  原始名称: '{raw_name}'")
        print(f"  清理后: '{cleaned_name}'")
        print(f"  最终名称: '{final_name}'")

        # 判断是否有效
        if code and final_name:
            pinyin = get_pinyin_initials(final_name)
            symbol_cache.append({"code": code, "name": final_name, "pinyin": pinyin})
            success_count += 1
            print(f"  ✅ 有效: 拼音='{pinyin}'")
        else:
            error_count += 1
            print(f"  ❌ 无效")

        print("-" * 30)

    print(f"\n最终结果:")
    print(f"✅ 有效品种: {success_count}")
    print(f"❌ 无效品种: {error_count}")
    print(f"📊 总计: {success_count + error_count}")

    # 验证修复效果
    print("\n🔍 修复效果验证:")
    print("-" * 60)

    expected_total = len(mock_backend_symbols)
    expected_valid = expected_total  # 修复后应该全部有效

    if success_count == expected_valid and error_count == 0:
        print("✅ 修复成功！所有品种现在都是有效的")
        print(f"   预期有效品种: {expected_valid}")
        print(f"   实际有效品种: {success_count}")
        print(f"   预期无效品种: 0")
        print(f"   实际无效品种: {error_count}")
    else:
        print("❌ 修复失败！")
        print(f"   预期有效品种: {expected_valid}")
        print(f"   实际有效品种: {success_count}")
        print(f"   预期无效品种: 0")
        print(f"   实际无效品种: {error_count}")

    # 测试拼音匹配功能
    print("\n🧪 拼音匹配功能测试:")
    print("-" * 60)

    def test_symbol_match(symbol_cache, search_text):
        """测试品种匹配功能"""
        matches = []
        text_lower = search_text.lower()

        for symbol in symbol_cache:
            code = symbol.get("code", "")
            name = symbol.get("name", "")
            pinyin = symbol.get("pinyin", "")

            if text_lower in code.lower() or text_lower in name.lower() or text_lower in pinyin:
                matches.append(f"{code} {name}")

        return matches

    test_cases = [
        ("162416", "代码匹配"),
        ("123161", "代码匹配"),
        ("浦发", "名称匹配"),
        ("万科", "名称匹配"),
        ("万", "拼音匹配"),
        ("hdf", "拼音匹配"),
    ]

    for search_text, match_type in test_cases:
        results = test_symbol_match(symbol_cache, search_text)
        print(f"搜索 '{search_text}' ({match_type}) -> {len(results)} 个结果: {results[:3]}...")

    print("=" * 60)


if __name__ == "__main__":
    test_fix_verification()
