# -*- coding: utf-8 -*-
"""品种数据综合修复方案."""

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


def fix_symbol_encoding_and_structure():
    """修复品种数据编码和结构问题."""

    print("=" * 80)
    print("品种数据综合修复方案")
    print("=" * 80)

    # 1. 分析当前问题
    print("\n1. 当前问题分析")
    print("-" * 50)

    print("发现的主要问题:")
    print("• 深证A股品种名称存在乱码: '万 科Ａ\\x00', '*ST国华\\x00'")
    print("• T+0基金品种名称存在乱码: '货币ETF\\x00'")
    print("• 缓存数据结构错误: name字段等于code字段")
    print("• 前端显示品种名称为字典字符串而非实际名称")

    # 2. 根本原因分析
    print("\n\n2. 根本原因分析")
    print("-" * 50)

    print("原因链条:")
    print("1. 通达信API返回品种名称时包含非GBK字符或空字符")
    print("2. AsyncGetSecurityList.py 使用 'gbk' + 'errors=ignore' 解码")
    print("3. 解码失败的字符被丢弃或替换为占位符")
    print("4. 后端缓存处理逻辑发现名称无效，用代码代替名称")
    print("5. 前端接收到 'name': code 的错误数据结构")
    print("6. 前端显示时输出字典字符串而不是品种名称")

    # 3. 修复方案设计
    print("\n\n3. 修复方案设计")
    print("-" * 50)

    print("方案1 - 修复通达信API数据解码:")
    print("• 修改 AsyncGetSecurityList.py 的解码逻辑")
    print("• 使用更宽容的编码处理方式")
    print("• 添加字符编码验证和修复机制")

    print("\n方案2 - 修复后端缓存处理逻辑:")
    print("• 修改 data_center_service.py 的缓存处理")
    print("• 确保品种名称正确保存和加载")
    print("• 添加数据验证和修复机制")

    print("\n方案3 - 增强前端数据处理:")
    print("• 改进前端品种数据提取逻辑")
    print("• 添加字符编码检测和修复")
    print("• 建立数据质量监控机制")

    # 4. 实施修复方案
    print("\n\n4. 实施修复方案")
    print("-" * 50)

    try:
        # 4.1 修复通达信API解码逻辑
        print("4.1 修复通达信API解码逻辑...")

        tdx_parser_file = "backend/infrastructure/tdx_asyncio/parser/std/async_get_security_list.py"

        if os.path.exists(tdx_parser_file):
            with open(tdx_parser_file, "r", encoding="utf-8") as f:
                content = f.read()

            # 检查当前解码逻辑
            if 'name_bytes.decode("gbk", errors="ignore")' in content:
                print("  ✓ 当前使用 gbk + errors='ignore' 解码")

                # 建议的改进方案
                print("  建议改进为更宽容的解码方式:")
                print("  ```python")
                print("  # 尝试多种编码方式")
                print("  try:")
                print("      name = name_bytes.decode('gbk')")
                print("  except UnicodeDecodeError:")
                print("      try:")
                print("          name = name_bytes.decode('utf-8')")
                print("      except UnicodeDecodeError:")
                print("          name = name_bytes.decode('gbk', errors='replace')")
                print("  ```")

        # 4.2 修复后端缓存处理逻辑
        print("\n4.2 修复后端缓存处理逻辑...")

        backend_file = "backend/services/data_center_service.py"

        if os.path.exists(backend_file):
            with open(backend_file, "r", encoding="utf-8") as f:
                content = f.read()

            # 检查缓存处理逻辑
            if '"name": code,' in content:
                print("  ✗ 发现问题：缓存中品种名称被错误设置为代码")

                # 显示问题代码
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if '"name": code,' in line:
                        print(f"    第{i+1}行: {line.strip()}")
                        if i > 0:
                            print(f"    上文: {lines[i-1].strip()}")
                        if i < len(lines) - 1:
                            print(f"    下文: {lines[i+1].strip()}")
                        break

        # 4.3 修复前端数据处理逻辑
        print("\n4.3 修复前端数据处理逻辑...")

        frontend_file = "ui/modules/data_center_view.py"

        if os.path.exists(frontend_file):
            with open(frontend_file, "r", encoding="utf-8") as f:
                content = f.read()

            # 检查前端品种数据提取逻辑
            if "_extract_symbol_name" in content:
                print("  ✓ 前端有品种名称提取方法")

                # 显示当前逻辑
                lines = content.split("\n")
                for i, line in enumerate(lines):
                    if "def _extract_symbol_name" in line:
                        print(f"    第{i+1}行: {line.strip()}")
                        # 显示方法体
                        for j in range(i + 1, min(i + 10, len(lines))):
                            if lines[j].strip() and not lines[j].startswith("    def"):
                                print(f"    {lines[j]}")
                            else:
                                break
                        break

    except Exception as e:
        print(f"  ✗ 修复方案分析失败: {e}")

    # 5. 具体修复步骤
    print("\n\n5. 具体修复步骤")
    print("-" * 50)

    print("步骤1 - 修复通达信API解码:")
    print("修改 async_get_security_list.py:")
    print("```python")
    print("# 替换第50行")
    print("# 原代码:")
    print('name = name_bytes.decode("gbk", errors="ignore")')
    print("# 新代码:")
    print("try:")
    print("    name = name_bytes.decode('gbk')")
    print("except UnicodeDecodeError:")
    print("    try:")
    print("        name = name_bytes.decode('utf-8')")
    print("    except UnicodeDecodeError:")
    print("        name = name_bytes.decode('gbk', errors='replace')")
    print("```")

    print("\n步骤2 - 修复后端缓存处理:")
    print("修改 data_center_service.py:")
    print("```python")
    print("# 替换第475行")
    print("# 原代码:")
    print('"name": code,  # JSON中只有代码，名称暂时用代码代替')
    print("# 新代码:")
    print('"name": stock_name,  # 使用实际品种名称')
    print("```")

    print("\n步骤3 - 增强前端数据验证:")
    print("修改 data_center_view.py:")
    print("```python")
    print("# 增强品种名称验证")
    print("def _validate_symbol_name(name, code):")
    print("    if not name or name == code or name.strip() == '':")
    print("        return code  # 如果名称无效，使用代码作为后备")
    print("    return name")
    print("```")

    print("\n步骤4 - 添加字符编码修复:")
    print("在品种名称处理中添加编码修复逻辑")
    print("```python")
    print("def _fix_symbol_name_encoding(name):")
    print("    if not name:")
    print("        return name")
    print("    # 清理常见乱码字符")
    print("    name = name.replace('\\x00', '')")
    print("    name = name.replace('\\u0000', '')")
    print("    return name.strip()")
    print("```")

    # 6. 预期效果
    print("\n\n6. 预期修复效果")
    print("-" * 50)

    print("修复后效果:")
    print("• 品种名称显示正确，不再有方框乱码")
    print("• 拼音首字母匹配正常工作")
    print("• 品种缓存中包含正确的品种名称")
    print("• 前端显示品种的实际名称而非代码")
    print("• 智能联想功能完全正常")

    print("=" * 80)


if __name__ == "__main__":
    fix_symbol_encoding_and_structure()
