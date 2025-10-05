# -*- coding: utf-8 -*-
"""
Cursor IDE 诊断脚本
检查为什么Cursor IDE不显示代码错误
"""

import subprocess
import sys
import os
import json
from pathlib import Path


def check_python_interpreter():
    """检查Python解释器"""
    print("=== Python解释器检查 ===")
    print(f"当前Python路径: {sys.executable}")
    print(f"Python版本: {sys.version}")

    # 检查虚拟环境
    venv_path = Path("venv310/Scripts/python.exe")
    if venv_path.exists():
        print(f"✓ 虚拟环境存在: {venv_path}")
    else:
        print(f"⚠ 虚拟环境不存在: {venv_path}")

    return sys.executable


def check_linting_tools():
    """检查linter工具"""
    print("\n=== Linter工具检查 ===")

    tools = {
        "flake8": "flake8 --version",
        "pylint": "pylint --version",
        "black": "black --version",
        "isort": "isort --version",
    }

    for tool, cmd in tools.items():
        try:
            result = subprocess.run(
                cmd.split(), capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                version = result.stdout.strip().split("\n")[0]
                print(f"✓ {tool}: {version}")
            else:
                print(f"✗ {tool}: 命令失败")
        except Exception as e:
            print(f"✗ {tool}: {e}")


def check_vscode_config():
    """检查VSCode/Cursor配置"""
    print("\n=== IDE配置检查 ===")

    vscode_dir = Path(".vscode")
    if vscode_dir.exists():
        print("✓ .vscode目录存在")

        settings_file = vscode_dir / "settings.json"
        if settings_file.exists():
            print("✓ settings.json存在")
            try:
                with open(settings_file, "r", encoding="utf-8") as f:
                    settings = json.load(f)
                print(f"✓ 配置项数量: {len(settings)}")

                # 检查关键配置
                key_settings = [
                    "python.linting.enabled",
                    "python.linting.pylintEnabled",
                    "python.linting.flake8Enabled",
                    "python.defaultInterpreterPath",
                ]

                for key in key_settings:
                    if key in settings:
                        print(f"✓ {key}: {settings[key]}")
                    else:
                        print(f"⚠ 缺少配置: {key}")

            except Exception as e:
                print(f"✗ 读取settings.json失败: {e}")
        else:
            print("✗ settings.json不存在")
    else:
        print("✗ .vscode目录不存在")


def test_linting_on_file():
    """测试文件linting"""
    print("\n=== 文件Linting测试 ===")

    test_file = "ui/components/market_dashboard/main_view.py"
    if not Path(test_file).exists():
        print(f"✗ 测试文件不存在: {test_file}")
        return

    print(f"测试文件: {test_file}")

    # 测试flake8
    try:
        result = subprocess.run(
            [sys.executable, "-m", "flake8", test_file],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            print("✓ flake8: 无错误")
        else:
            print(f"⚠ flake8发现问题:")
            for line in result.stdout.split("\n")[:5]:  # 只显示前5个问题
                if line.strip():
                    print(f"  {line}")
    except Exception as e:
        print(f"✗ flake8测试失败: {e}")

    # 测试pylint
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pylint", test_file],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if "rated at" in result.stdout:
            rating = result.stdout.split("rated at ")[1].split("/")[0]
            print(f"✓ pylint评分: {rating}/10")
        else:
            print("⚠ pylint输出格式异常")
    except Exception as e:
        print(f"✗ pylint测试失败: {e}")


def check_cursor_specific():
    """检查Cursor特定问题"""
    print("\n=== Cursor IDE特定检查 ===")

    # 检查是否有Cursor特定配置
    cursor_configs = [".cursor", ".cursorignore", "cursor.json"]

    for config in cursor_configs:
        if Path(config).exists():
            print(f"✓ 发现Cursor配置: {config}")
        else:
            print(f"- 无Cursor配置: {config}")

    # 检查Python扩展
    print("\n建议检查:")
    print("1. 确保安装了Python扩展")
    print("2. 检查Python解释器路径设置")
    print("3. 重启Cursor IDE")
    print("4. 检查输出面板中的Python日志")


def main():
    """主诊断函数"""
    print("=== Cursor IDE 诊断工具 ===\n")

    check_python_interpreter()
    check_linting_tools()
    check_vscode_config()
    test_linting_on_file()
    check_cursor_specific()

    print("\n=== 诊断完成 ===")
    print("\n如果Cursor IDE仍然不显示错误，请尝试:")
    print("1. 重启Cursor IDE")
    print("2. 按Ctrl+Shift+P，搜索'Python: Select Interpreter'")
    print("3. 选择正确的Python解释器")
    print("4. 按Ctrl+Shift+P，搜索'Python: Restart Language Server'")
    print("5. 检查输出面板中的Python日志")


if __name__ == "__main__":
    main()

