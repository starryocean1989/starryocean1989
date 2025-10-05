# -*- coding: utf-8 -*-
"""
设置代码质量检查工具

确保Cursor IDE能正确显示代码错误和警告
"""

import json
import subprocess
import sys
from pathlib import Path


def install_packages():
    """安装代码质量检查工具"""
    packages = ["flake8>=7.3.0", "pylint>=3.0.0", "black>=23.0.0", "isort>=5.12.0"]

    print("正在安装代码质量检查工具...")
    for package in packages:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            print(f"✓ 已安装 {package}")
        except subprocess.CalledProcessError as e:
            print(f"✗ 安装 {package} 失败: {e}")


def test_linting():
    """测试linter是否正常工作"""
    test_file = "ui/components/market_dashboard/main_view.py"

    print(f"\n测试文件: {test_file}")

    # 测试flake8
    try:
        result = subprocess.run(
            [sys.executable, "-m", "flake8", test_file],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            print("✓ flake8: 无错误")
        else:
            print(f"⚠ flake8 发现问题:\n{result.stdout}")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"✗ flake8 测试失败: {e}")

    # 测试pylint
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pylint", test_file],
            capture_output=True,
            text=True,
            check=False,
        )
        score_text = "N/A"
        if "rated at" in result.stdout:
            score_parts = result.stdout.split("rated at ")[1].split("/")
            if len(score_parts) > 0:
                score_text = score_parts[0]
        print(f"✓ pylint 检查完成 (评分: {score_text})")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"✗ pylint 测试失败: {e}")


def create_vscode_config():
    """创建VSCode/Cursor配置"""
    vscode_dir = Path(".vscode")
    vscode_dir.mkdir(exist_ok=True)

    settings = {
        "python.defaultInterpreterPath": "./venv310/Scripts/python.exe",
        "python.linting.enabled": True,
        "python.linting.pylintEnabled": True,
        "python.linting.flake8Enabled": True,
        "python.linting.mypyEnabled": False,
        "python.linting.pylintArgs": [
            "--disable=C0413,C0415,C0301,W0718,W0611,W0621,W0404,R1705"
        ],
        "python.linting.flake8Args": [
            "--max-line-length=88",
            "--extend-ignore=E402,D400,I100",
        ],
        "python.analysis.typeCheckingMode": "basic",
        "python.analysis.autoImportCompletions": True,
        "python.analysis.diagnosticMode": "workspace",
        "files.associations": {"*.py": "python"},
        "editor.formatOnSave": True,
        "python.formatting.provider": "black",
        "python.sortImports.args": ["--profile", "black"],
    }

    with open(vscode_dir / "settings.json", "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)

    print("✓ 已创建 .vscode/settings.json 配置文件")


def main():
    """主函数"""
    print("=== Cursor IDE 代码质量检查设置 ===\n")

    # 检查虚拟环境
    venv_path = Path("venv310/Scripts/python.exe")
    if not venv_path.exists():
        print("⚠ 警告: 虚拟环境路径不存在，请确保venv310已正确创建")

    # 安装工具
    install_packages()

    # 创建配置
    create_vscode_config()

    # 测试linter
    test_linting()

    print("\n=== 设置完成 ===")
    print("请重启Cursor IDE以使配置生效")
    print("如果问题仍然存在，请检查:")
    print("1. Python解释器路径是否正确")
    print("2. 是否安装了Python扩展")
    print("3. 语言服务器是否正常运行")


if __name__ == "__main__":
    main()
