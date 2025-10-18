# -*- coding: utf-8 -*-
"""调试拼音首字母生成崩溃问题."""

import sys
import os

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def test_pinyin_crash():
    """测试拼音首字母生成是否会导致崩溃."""

    print("=" * 60)
    print("拼音首字母生成崩溃诊断")
    print("=" * 60)

    # 测试可能导致崩溃的输入
    test_cases = [
        "浦发银行",  # 正常中文
        "万 科Ａ",  # 中文+英文+空格
        "162416",  # 纯数字代码
        "123161",  # 纯数字代码
        "",  # 空字符串
        "   ",  # 空白字符串
        "中国平安A股",  # 长中文名称
        "货币ETF",  # 中文+英文
        "*ST国华",  # 特殊字符开头
        "万科A",  # 中文+英文
    ]

    try:
        from pypinyin import lazy_pinyin

        print("使用 pypinyin 库测试:")
        print("-" * 60)

        for test_text in test_cases:
            try:
                print(f"测试文本: '{test_text}'")
                pinyin_list = lazy_pinyin(test_text)
                result = "".join([p[0].lower() for p in pinyin_list])
                print(f"  拼音列表: {pinyin_list}")
                print(f"  首字母: '{result}'")
                print("  ✅ 成功")

            except Exception as e:
                print(f"  ❌ 失败: {e}")
                print(f"  错误类型: {type(e).__name__}")

            print("-" * 30)

    except ImportError:
        print("pypinyin未安装，使用模拟测试:")
        print("-" * 60)

        def mock_lazy_pinyin(text):
            """模拟拼音生成，可能导致崩溃"""
            if not text or text.strip() == "":
                return []

            # 模拟对数字的处理（这可能导致问题）
            if text.isdigit():
                # 数字拼音转换可能有问题
                return [str(text)]  # 返回数字本身

            # 模拟中文拼音
            return (
                ["zhong", "guo", "ping", "an"]
                if "中国平安" in text
                else ["pu", "fa", "yin", "hang"]
            )

        for test_text in test_cases:
            try:
                print(f"测试文本: '{test_text}'")
                pinyin_list = mock_lazy_pinyin(test_text)
                result = "".join([p[0].lower() for p in pinyin_list])
                print(f"  拼音列表: {pinyin_list}")
                print(f"  首字母: '{result}'")
                print("  ✅ 成功")

            except Exception as e:
                print(f"  ❌ 失败: {e}")
                print(f"  错误类型: {type(e).__name__}")

            print("-" * 30)

    # 分析崩溃原因
    print("\n崩溃原因分析:")
    print("-" * 60)

    print("可能的原因:")
    print("1. 纯数字代码传入拼音库：lazy_pinyin('162416')")
    print("2. 空字符串处理不当：lazy_pinyin('')")
    print("3. 特殊字符处理：lazy_pinyin('*ST国华')")
    print("4. 内存访问违规：数组越界或空指针")

    print("\n解决方案:")
    print("1. 在调用拼音库前进行输入验证")
    print("2. 对非中文字符使用不同的处理逻辑")
    print("3. 添加异常捕获和防护措施")

    print("=" * 60)


if __name__ == "__main__":
    test_pinyin_crash()
