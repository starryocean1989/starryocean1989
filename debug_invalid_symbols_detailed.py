# -*- coding: utf-8 -*-
"""详细调试无效品种的具体原因."""

import sys
import os
import json
import logging
from pathlib import Path

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def debug_invalid_symbols_in_detail():
    """详细分析无效品种的具体数据和原因."""

    print("=" * 80)
    print("无效品种详细诊断")
    print("=" * 80)

    try:
        from backend.infrastructure.data_module_vnpy.config import config_manager

        cache_dir = config_manager.get_cache_dir()
        json_cache_file = cache_dir / "stock_list_classified.json"

        if not json_cache_file.exists():
            print(f"❌ 缓存文件不存在: {json_cache_file}")
            return

        # 读取品种缓存数据
        with open(json_cache_file, "r", encoding="utf-8") as f:
            cache_data = json.load(f)

        classified = cache_data.get("classified", {})
        all_symbols = []

        # 收集所有品种
        for market_type, codes in classified.items():
            for code in codes:
                if isinstance(code, dict):
                    # 新格式：品种是字典
                    all_symbols.append(code)
                elif isinstance(code, str):
                    # 旧格式：品种是字符串（只有代码）
                    all_symbols.append({"code": code, "name": code})

        print(f"📊 总品种数: {len(all_symbols)}")

        # 分析品种数据结构
        print("\n品种数据结构分析:")
        print("-" * 50)

        data_structures = {}
        for symbol in all_symbols[:20]:  # 只分析前20个
            struct_type = type(symbol).__name__
            if struct_type not in data_structures:
                data_structures[struct_type] = []
            data_structures[struct_type].append(symbol)

        for struct_type, symbols in data_structures.items():
            print(f"  {struct_type}: {len(symbols)} 个品种")
            if symbols:
                print(f"    示例: {symbols[0]}")

        # 查找无效品种
        print("\n🔍 无效品种详细分析:")
        print("-" * 50)

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

        invalid_symbols = []
        valid_symbols = []

        for symbol in all_symbols:
            try:
                code = extract_symbol_code(symbol)
                raw_name = extract_symbol_name(symbol)
                cleaned_name = clean_symbol_name_encoding(raw_name)

                # 判断是否有效
                is_valid = code and cleaned_name and cleaned_name.strip()

                if is_valid:
                    valid_symbols.append(
                        {
                            "code": code,
                            "raw_name": raw_name,
                            "cleaned_name": cleaned_name,
                            "data": symbol,
                        }
                    )
                else:
                    invalid_symbols.append(
                        {
                            "code": code,
                            "raw_name": raw_name,
                            "cleaned_name": cleaned_name,
                            "reason": (
                                "名称为空"
                                if not cleaned_name
                                else "名称只有空白字符" if not cleaned_name.strip() else "代码为空"
                            ),
                            "data": symbol,
                        }
                    )

            except Exception as e:
                invalid_symbols.append(
                    {
                        "code": "ERROR",
                        "raw_name": str(e),
                        "cleaned_name": "",
                        "reason": f"处理异常: {e}",
                        "data": symbol,
                    }
                )

        print(f"✅ 有效品种: {len(valid_symbols)}")
        print(f"❌ 无效品种: {len(invalid_symbols)}")

        # 详细分析无效品种
        if invalid_symbols:
            print("\n❌ 无效品种详情:")
            print("-" * 50)

            for i, invalid in enumerate(invalid_symbols[:20]):  # 只显示前20个
                print(f"无效品种 {i+1}:")
                print(f"  代码: '{invalid['code']}'")
                print(f"  原始名称: '{invalid['raw_name']}'")
                print(f"  清理后名称: '{invalid['cleaned_name']}'")
                print(f"  原因: {invalid['reason']}")
                print(f"  数据结构: {type(invalid['data']).__name__}")
                if isinstance(invalid["data"], dict):
                    print(f"  数据内容: {invalid['data']}")
                print("-" * 30)

            # 统计无效品种的类型
            print("\n无效品种类型统计:")
            print("-" * 30)

            reason_stats = {}
            for invalid in invalid_symbols:
                reason = invalid["reason"]
                reason_stats[reason] = reason_stats.get(reason, 0) + 1

            for reason, count in reason_stats.items():
                print(f"  {reason}: {count} 个")

        # 分析有效品种中的潜在问题
        print("\n🔍 有效品种中的潜在问题:")
        print("-" * 50)

        problematic_valid = []
        for valid in valid_symbols[:50]:  # 检查前50个有效品种
            raw_name = valid["raw_name"]
            cleaned_name = valid["cleaned_name"]

            # 检查是否有乱码残留
            if (
                "\x00" in raw_name
                or "\u0000" in raw_name
                or "\ufffd" in raw_name
                or raw_name != cleaned_name
            ):
                problematic_valid.append(
                    {
                        "code": valid["code"],
                        "raw_name": raw_name,
                        "cleaned_name": cleaned_name,
                        "issue": "仍有乱码残留" if raw_name != cleaned_name else "名称被修改",
                    }
                )

        if problematic_valid:
            print(f"发现 {len(problematic_valid)} 个有潜在问题的有效品种:")
            for problem in problematic_valid[:10]:  # 只显示前10个
                print(
                    f"  {problem['code']}: '{problem['raw_name']}' -> '{problem['cleaned_name']}' ({problem['issue']})"
                )
        else:
            print("✓ 前50个有效品种都没有乱码问题")

    except Exception as e:
        print(f"❌ 诊断失败: {e}")
        import traceback

        traceback.print_exc()

    print("=" * 80)


if __name__ == "__main__":
    debug_invalid_symbols_in_detail()
