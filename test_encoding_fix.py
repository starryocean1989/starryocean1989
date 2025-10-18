# -*- coding: utf-8 -*-
"""测试品种名称编码修复效果."""


def test_encoding_fix():
    """测试品种名称编码清理功能."""

    print("=" * 60)
    print("品种名称编码修复测试")
    print("=" * 60)

    # 模拟有乱码的品种名称
    test_cases = [
        ("浦发银行", "正常品种名称"),
        ("万 科Ａ\x00", "万科A后面有空字符"),
        ("*ST国华\x00", "*ST国华后面有空字符"),
        ("货币ETF\x00", "货币ETF后面有空字符"),
        ("   中国平安   ", "前后有空白字符"),
        ("", "空名称"),
        ("   ", "只有空白字符"),
    ]

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

    print("测试结果:")
    print("-" * 60)

    for original_name, description in test_cases:
        cleaned_name = clean_symbol_name_encoding(original_name)
        pinyin = get_pinyin_initials(cleaned_name) if cleaned_name else ""

        print(f"原始名称: '{original_name}' ({description})")
        print(f"清理后: '{cleaned_name}'")
        print(f"拼音首字母: '{pinyin}'")
        print(f"状态: {'✓ 有效' if cleaned_name and pinyin else '✗ 无效'}")
        print("-" * 30)

    print("=" * 60)

    # 测试品种缓存构建
    print("\n品种缓存构建测试")
    print("-" * 60)

    # 模拟后端品种数据（包含乱码）
    mock_backend_data = [
        {"symbol": "600000", "code": "600000", "name": "浦发银行", "exchange": "上交所"},
        {"symbol": "000002", "code": "000002", "name": "万 科Ａ\x00", "exchange": "深交所"},
        {"symbol": "000004", "code": "000004", "name": "*ST国华\x00", "exchange": "深交所"},
        {"symbol": "159001", "code": "159001", "name": "货币ETF\x00", "exchange": "深交所"},
        {"symbol": "600036", "code": "600036", "name": "", "exchange": "上交所"},
    ]

    def extract_symbol_code(symbol_data):
        return str(symbol_data.get("symbol") or symbol_data.get("code") or "")

    def extract_symbol_name(symbol_data):
        name = str(symbol_data.get("name") or "")
        # 清理乱码
        name = clean_symbol_name_encoding(name)
        return name

    # 构建品种缓存
    symbol_cache = []
    for symbol in mock_backend_data:
        code = extract_symbol_code(symbol)
        name = extract_symbol_name(symbol)

        if code and name and name.strip():
            pinyin = get_pinyin_initials(name)
            symbol_cache.append({"code": code, "name": name, "pinyin": pinyin})
            print(f"✓ 有效品种: {code} - {name} (拼音: {pinyin})")
        else:
            print(f"✗ 无效品种: {code} - '{name}' (跳过)")

    print(f"\n缓存构建完成: {len(symbol_cache)} 个有效品种")

    # 测试联想功能
    print("\n联想功能测试")
    print("-" * 60)

    def test_autocomplete(symbol_cache, input_text):
        matches = []
        text_lower = input_text.lower()

        for symbol in symbol_cache:
            code = symbol.get("code", "")
            name = symbol.get("name", "")
            pinyin = symbol.get("pinyin", "")

            if text_lower in code.lower() or text_lower in name.lower() or text_lower in pinyin:
                matches.append(f"{code} {name}")

        return matches[:5]  # 限制5个结果

    test_inputs = ["浦发", "万科", "zk", "wk", "hdf", "货币"]

    for test_input in test_inputs:
        results = test_autocomplete(symbol_cache, test_input)
        print(f"输入 '{test_input}' -> 联想结果: {results}")

    print("=" * 60)


if __name__ == "__main__":
    test_encoding_fix()
