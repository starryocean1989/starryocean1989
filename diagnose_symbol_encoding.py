# -*- coding: utf-8 -*-
"""品种数据编码问题深度诊断."""

import sys
import os
import json
import logging
from pathlib import Path

# 添加项目根目录到路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from backend.infrastructure.tdx_asyncio.parser.std.async_get_security_list import (
    AsyncGetSecurityList,
)

# 配置日志
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def diagnose_encoding_issues():
    """诊断品种数据编码问题."""

    print("=" * 80)
    print("品种数据编码问题深度诊断")
    print("=" * 80)

    # 1. 检查缓存文件编码
    print("\n1. 检查品种缓存文件编码")
    print("-" * 50)

    try:
        from backend.infrastructure.data_module_vnpy.config import config_manager

        cache_dir = config_manager.get_cache_dir()
        json_cache_file = cache_dir / "stock_list_classified.json"

        if json_cache_file.exists():
            # 读取文件内容，检查编码
            with open(json_cache_file, "rb") as f:
                raw_data = f.read()

            # 尝试不同的编码解码
            encodings_to_try = ["utf-8", "gbk", "gb2312", "utf-16"]

            for encoding in encodings_to_try:
                try:
                    decoded = raw_data.decode(encoding)
                    print(f"  ✓ 文件可以用 {encoding} 编码正确解码")

                    # 解析JSON并检查品种名称
                    data = json.loads(decoded)
                    classified = data.get("classified", {})

                    # 检查每个市场的品种名称
                    for market, codes in classified.items():
                        print(f"\n  市场: {market}")
                        print(f"    品种数量: {len(codes)}")

                        # 检查前3个品种的名称
                        for i, code in enumerate(codes[:3]):
                            print(f"    品种 {i+1}: {code}")

                    break

                except UnicodeDecodeError:
                    print(f"  ✗ 文件不可以用 {encoding} 编码解码")
                    continue
                except json.JSONDecodeError:
                    print(f"  ✗ {encoding} 编码的文件内容不是有效的JSON")
                    continue
        else:
            print(f"  ⚠ 缓存文件不存在: {json_cache_file}")

    except Exception as e:
        print(f"  ✗ 检查缓存文件失败: {e}")

    # 2. 分析通达信API返回的数据结构
    print("\n\n2. 通达信API数据结构分析")
    print("-" * 50)

    print("通达信API返回的品种数据结构:")
    print("```python")
    print("{")
    print("    'code': '600000',      # 品种代码 (UTF-8)")
    print("    'volunit': 100,        # 成交量单位")
    print("    'decimal_point': 2,    # 小数点位数")
    print("    'name': '浦发银行',     # 品种名称 (GBK编码)")
    print("    'pre_close': 8.85      # 昨收价")
    print("}")
    print("```")

    print("\n编码转换过程:")
    print("原始字节数据 (GBK) → decode('gbk', errors='ignore') → Python字符串")
    print("如果品种名称包含非GBK字符，会出现乱码或丢失")

    # 3. 检查可能的乱码来源
    print("\n\n3. 乱码来源分析")
    print("-" * 50)

    print("常见乱码来源:")
    print("• 非GBK字符：如股票名称中的英文、数字、特殊符号")
    print("• 编码不匹配：API返回的数据编码与解码方式不一致")
    print("• 数据损坏：网络传输过程中的数据损坏")
    print("• 字符集转换错误：不同系统间的字符集转换问题")

    # 4. 检查具体品种数据
    print("\n\n4. 具体品种数据检查")
    print("-" * 50)

    try:
        # 尝试从缓存加载品种数据进行分析
        symbols = []
        if json_cache_file.exists():
            with open(json_cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                classified = data.get("classified", {})

                # 收集所有品种
                for market, codes in classified.items():
                    for code in codes:
                        symbols.append({"code": code, "name": code, "market": market})

        if symbols:
            print(f"总品种数: {len(symbols)}")

            # 查找可能有问题的品种（名称等于代码或包含特殊字符）
            problematic_symbols = []
            for symbol in symbols[:100]:  # 只检查前100个
                code = symbol.get("code", "")
                name = symbol.get("name", "")

                if code == name or name == "" or "?" in name or "□" in name:
                    problematic_symbols.append(symbol)

            if problematic_symbols:
                print(f"\n发现 {len(problematic_symbols)} 个可能有问题的品种:")
                for symbol in problematic_symbols[:10]:  # 只显示前10个
                    print(f"  代码: {symbol['code']}, 名称: '{symbol['name']}'")
            else:
                print("✓ 前100个品种名称都正常")

        else:
            print("无法加载品种数据进行分析")

    except Exception as e:
        print(f"检查品种数据失败: {e}")

    # 5. 提出解决方案
    print("\n\n5. 解决方案建议")
    print("-" * 50)

    print("方案1 - 改进字符编码处理:")
    print("• 修改 AsyncGetSecurityList.py 中的解码逻辑")
    print("• 使用更宽容的编码处理方式")
    print("• 添加字符编码验证和修复机制")

    print("\n方案2 - 增强前端数据处理:")
    print("• 在前端添加字符编码检测和修复")
    print("• 对乱码数据进行清理和标准化")
    print("• 添加品种名称验证机制")

    print("\n方案3 - 数据源验证:")
    print("• 检查通达信API返回数据的原始编码")
    print("• 验证不同服务器返回数据的一致性")
    print("• 建立数据质量监控机制")

    print("=" * 80)


if __name__ == "__main__":
    diagnose_encoding_issues()
