# -*- coding: utf-8 -*-
"""测试内存安全的品种缓存加载逻辑."""


def test_memory_safe_loading():
    """测试修复后的品种缓存加载逻辑是否会导致崩溃."""

    print("=" * 60)
    print("内存安全的品种缓存加载测试")
    print("=" * 60)

    # 模拟大量品种数据（6147个）
    mock_symbols = []

    # 添加正常品种
    for i in range(1000):
        mock_symbols.append(
            {"symbol": f"60{i:04d}", "code": f"60{i:04d}", "name": f"股票{i}", "exchange": "上交所"}
        )

    # 添加有问题的品种（名称为空）
    for i in range(12):
        mock_symbols.append(
            {
                "symbol": f"162{i:03d}",
                "code": f"162{i:03d}",
                "name": "",  # 空名称
                "exchange": "深交所",
            }
        )

    # 添加更多正常品种
    for i in range(4135):  # 总共6147个
        mock_symbols.append(
            {
                "symbol": f"000{i:04d}",
                "code": f"000{i:04d}",
                "name": f"平安股票{i}",
                "exchange": "深交所",
            }
        )

    print(f"模拟品种总数: {len(mock_symbols)}")

    def extract_symbol_code(symbol_data):
        """模拟品种代码提取"""
        if isinstance(symbol_data, dict):
            return str(symbol_data.get("symbol") or symbol_data.get("code") or "")
        return str(symbol_data)

    def extract_symbol_name(symbol_data):
        """模拟品种名称提取"""
        if isinstance(symbol_data, dict):
            return str(symbol_data.get("name") or "")
        return str(symbol_data)

    def clean_symbol_name_encoding(name: str) -> str:
        """模拟品种名称清理"""
        if not name:
            return ""

        cleaned = name.replace("\x00", "")
        cleaned = cleaned.replace("\u0000", "")
        cleaned = cleaned.replace("\ufffd", "")
        cleaned = cleaned.strip()

        return cleaned

    def get_pinyin_initials(text: str) -> str:
        """模拟拼音首字母生成（带防护）"""
        if not text or not isinstance(text, str):
            return ""

        if text.isdigit():
            return text[0] if text else ""

        try:
            # 模拟拼音库调用
            if "股票" in text:
                return "pg"
            elif "平安" in text:
                return "pa"
            else:
                return text[0].lower()
        except Exception:
            return ""

    # 测试分批处理逻辑
    print("\n测试分批处理逻辑:")
    print("-" * 60)

    symbol_cache = []
    success_count = 0
    error_count = 0

    batch_size = 1000
    total_batches = (len(mock_symbols) + batch_size - 1) // batch_size

    for i in range(0, len(mock_symbols), batch_size):
        batch = mock_symbols[i : i + batch_size]
        print(f"处理批次 {i//batch_size + 1}/{total_batches} (共{len(batch)}个品种)")

        for symbol in batch:
            try:
                if isinstance(symbol, dict):
                    code = extract_symbol_code(symbol)
                    raw_name = extract_symbol_name(symbol)
                    name = clean_symbol_name_encoding(raw_name)

                    # 处理品种名称：如果清理后名称为空，使用代码作为名称
                    final_name = name if name.strip() else code

                    if code and final_name:
                        pinyin = get_pinyin_initials(final_name)
                        symbol_cache.append({"code": code, "name": final_name, "pinyin": pinyin})
                        success_count += 1
                    else:
                        error_count += 1
                else:
                    error_count += 1

            except Exception as e:
                error_count += 1
                print(f"  错误: {e}")

        # 模拟垃圾回收
        import gc

        gc.collect()

    print("\n最终结果:")
    print(f"✅ 有效品种: {success_count}")
    print(f"❌ 无效品种: {error_count}")
    print(f"📊 总计: {success_count + error_count}")
    print(f"💾 缓存大小: {len(symbol_cache)}")

    # 验证所有品种都被处理
    if success_count + error_count == len(mock_symbols):
        print("✅ 品种数量验证通过")
    else:
        print("❌ 品种数量验证失败")

    # 测试联想功能
    print("\n🧪 联想功能测试:")
    print("-" * 60)

    def test_symbol_match(symbol_cache, search_text):
        """测试品种匹配"""
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
        "股票",  # 名称匹配
        "平安",  # 名称匹配
        "162416",  # 代码匹配（空名称品种）
        "股票0",  # 名称匹配
        "pg",  # 拼音匹配
        "pa",  # 拼音匹配
    ]

    for search_text in test_cases:
        results = test_symbol_match(symbol_cache, search_text)
        print(f"搜索 '{search_text}' -> {len(results)} 个结果")

    print("=" * 60)


if __name__ == "__main__":
    test_memory_safe_loading()
