# -*- coding: utf-8 -*-
"""测试完整的拼音首字母匹配修复."""


def get_pinyin_initials(text: str) -> str:
    """获取文本的拼音首字母."""
    try:
        from pypinyin import lazy_pinyin

        pinyin_list = lazy_pinyin(text)
        result = "".join([p[0].lower() for p in pinyin_list])
        return result
    except ImportError:
        print("pypinyin未安装，请先安装: pip install pypinyin")
        return ""
    except Exception as e:
        print(f"获取拼音首字母失败: {e}")
        return ""


def test_complete_symbol_matching():
    """测试完整的品种匹配逻辑."""

    # 模拟后端返回的品种数据结构
    mock_symbol_data = {
        "symbol": "601318",
        "code": "601318",
        "name": "中国平安",
        "exchange": "上交所",
        "product_type": "股票",
    }

    # 模拟前端品种缓存（包含拼音首字母）
    mock_symbol_cache = [
        {"code": "601318", "name": "中国平安", "pinyin": get_pinyin_initials("中国平安")}
    ]

    print("=" * 60)
    print("完整拼音匹配测试")
    print("=" * 60)

    # 测试拼音首字母生成
    pinyin = mock_symbol_cache[0]["pinyin"]
    print(f"中国平安 -> 拼音首字母: {pinyin}")

    # 测试各种匹配方式
    test_cases = [
        ("zgpa", "拼音匹配"),
        ("ZGPA", "拼音匹配（大写）"),
        ("中国", "名称匹配"),
        ("平安", "名称匹配"),
        ("601318", "代码匹配"),
        ("6013", "代码部分匹配"),
        ("中国平安", "名称完全匹配"),
    ]

    for test_input, match_type in test_cases:
        # 模拟品种列表搜索的匹配逻辑
        def matches_symbol(symbol_data, search_text, symbol_cache):
            try:
                code = str(symbol_data.get("symbol") or symbol_data.get("code") or "").lower()
                name = str(symbol_data.get("name") or "").lower()

                # 查找该品种的拼音首字母
                pinyin = ""
                for cached_symbol in symbol_cache:
                    if cached_symbol.get("code") == code and cached_symbol.get("name") == name:
                        pinyin = cached_symbol.get("pinyin", "").lower()
                        break

                # 三种匹配方式
                result = (
                    search_text.lower() in code
                    or search_text.lower() in name
                    or search_text.lower() in pinyin
                )

                return result, code, name, pinyin

            except Exception as e:
                # 如果出现异常，至少保证代码和名称匹配
                code = str(symbol_data.get("symbol") or symbol_data.get("code") or "").lower()
                name = str(symbol_data.get("name") or "").lower()
                result = search_text.lower() in code or search_text.lower() in name
                return result, code, name, ""

        matches, code, name, pinyin = matches_symbol(
            mock_symbol_data, test_input, mock_symbol_cache
        )
        status = "✓" if matches else "✗"

        print(
            f"{status} 输入: {test_input:12s} | 类型: {match_type:12s} | 拼音: {pinyin:6s} | 匹配: {matches}"
        )

    print("=" * 60)

    # 测试联想功能（模拟前端联想逻辑）
    print("\n联想功能测试")
    print("=" * 60)

    def simulate_autocomplete(symbol_cache, input_text):
        """模拟自动完成逻辑"""
        matches = []
        text_lower = input_text.lower()

        for symbol in symbol_cache:
            code = symbol.get("code", "")
            name = symbol.get("name", "")
            pinyin = symbol.get("pinyin", "")

            # 匹配规则：代码包含、名称包含、拼音首字母包含
            if text_lower in code.lower() or text_lower in name.lower() or text_lower in pinyin:
                display = f"{code} {name}"
                matches.append(display)

        return matches[:20]  # 限制20条

    test_inputs = ["z", "zg", "zgp", "zgpa", "中国", "平", "601", "6"]

    for test_input in test_inputs:
        results = simulate_autocomplete(mock_symbol_cache, test_input)
        print(f"输入: {test_input:6s} -> 联想结果: {results}")

    print("=" * 60)


if __name__ == "__main__":
    test_complete_symbol_matching()
