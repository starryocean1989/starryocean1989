# -*- coding: utf-8 -*-
"""测试拼音首字母匹配功能."""


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


def test_pinyin_matching():
    """测试拼音匹配功能."""
    test_cases = [
        ("中国平安", "zgpa"),
        ("浦发银行", "pfyh"),
        ("工商银行", "gsyh"),
        ("招商银行", "zsyh"),
        ("贵州茅台", "gzmt"),
        ("五粮液", "wly"),
        ("宁德时代", "ndsd"),
        ("比亚迪", "byd"),
        ("平安银行", "payh"),
        ("中信证券", "zxzq"),
    ]

    print("=" * 60)
    print("拼音首字母生成测试")
    print("=" * 60)

    all_passed = True
    for name, expected_pinyin in test_cases:
        actual_pinyin = get_pinyin_initials(name)
        passed = actual_pinyin == expected_pinyin
        status = "✓" if passed else "✗"

        print(f"{status} {name:10s} -> {actual_pinyin:6s} (期望: {expected_pinyin})")

        if not passed:
            all_passed = False

    print("=" * 60)
    if all_passed:
        print("✅ 所有测试通过！")
    else:
        print("❌ 部分测试失败！")
    print("=" * 60)

    # 测试匹配逻辑
    print("\n匹配逻辑测试")
    print("=" * 60)

    test_symbol = {"code": "601318", "name": "中国平安", "pinyin": get_pinyin_initials("中国平安")}

    print(f"测试品种: {test_symbol['code']} {test_symbol['name']}")
    print(f"拼音首字母: {test_symbol['pinyin']}")
    print()

    test_inputs = ["zgpa", "ZGPA", "中国", "平安", "601318", "6013"]

    for text in test_inputs:
        text_lower = text.lower()
        code = test_symbol.get("code", "")
        name = test_symbol.get("name", "")
        pinyin = test_symbol.get("pinyin", "")

        # 原来的匹配逻辑（有问题）
        old_match = text_lower in code.lower() or text in name or text_lower in pinyin

        # 新的匹配逻辑（修复后）
        new_match = text_lower in code.lower() or text_lower in name.lower() or text_lower in pinyin

        print(f"输入: {text:10s} | 旧逻辑: {old_match} | 新逻辑: {new_match}")

    print("=" * 60)


if __name__ == "__main__":
    test_pinyin_matching()
