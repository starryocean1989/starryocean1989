# -*- coding: utf-8 -*-
"""
修复剩余的DEBUG print语句
"""
import re
from pathlib import Path


def fix_ui_debug_prints():
    """修复UI中所有的DEBUG print"""
    file_path = Path("ui/modules/data_center_view.py")
    if not file_path.exists():
        print(f"❌ 文件不存在: {file_path}")
        return False

    content = file_path.read_text(encoding="utf-8")
    original_len = len(content)

    # 移除所有DEBUG print语句
    patterns = [
        r'print\(f?["\']🔍.*?DEBUG.*?["\']\).*?#.*?调试语句\d+',
        r'print\(f?["\']✅.*?DEBUG.*?["\']\).*?#.*?调试语句\d+',
        r'print\(f?["\']❌.*?DEBUG.*?["\']\).*?#.*?调试语句\d+',
        r'print\(f?["\'][^"\']*?DEBUG[^"\']*?["\']\)',
        r'print\(f?["\']   [^"\']*?=.*?["\']\)',  # 缩进的debug输出
    ]

    for pattern in patterns:
        content = re.sub(pattern, "# print(...)  # 🔧 已移除：DEBUG调试输出", content)

    if len(content) != original_len:
        file_path.write_text(content, encoding="utf-8")
        print(f"✅ 已修复: {file_path}")
        print(f"   - 移除了所有DEBUG print语句")
        return True
    else:
        print(f"⚠️ 未找到DEBUG print: {file_path}")
        return False


def main():
    """执行修复"""
    print("=" * 70)
    print("🔧 修复剩余的DEBUG print语句")
    print("=" * 70)
    print()

    success = fix_ui_debug_prints()

    print()
    print("=" * 70)
    if success:
        print("✅ 修复完成！")
        print()
        print("建议：运行 python verify_terminal_output_optimization.py 重新验证")
    else:
        print("⚠️ 修复未应用")
    print("=" * 70)

    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
