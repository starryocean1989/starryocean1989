# -*- coding: utf-8 -*-
"""
修复Cursor IDE Python语言服务器问题
解决 'python.analysis.restartLanguageServer' not found 错误
"""

import subprocess
import sys
import os
import json
from pathlib import Path


def check_python_extension():
    """检查Python扩展状态"""
    print("=== 检查Python扩展状态 ===")

    # 检查是否有Python相关的扩展
    extensions_to_check = [
        "ms-python.python",
        "ms-python.pylint",
        "ms-python.flake8",
        "ms-python.black-formatter",
    ]

    print("需要安装的Python扩展:")
    for ext in extensions_to_check:
        print(f"- {ext}")

    print("\n请在Cursor IDE中:")
    print("1. 按 Ctrl+Shift+X 打开扩展面板")
    print("2. 搜索并安装 'Python' (Microsoft)")
    print("3. 搜索并安装 'Pylint' (Microsoft)")
    print("4. 搜索并安装 'Black Formatter' (Microsoft)")


def create_enhanced_vscode_config():
    """创建增强的VSCode/Cursor配置"""
    print("\n=== 创建增强的IDE配置 ===")

    vscode_dir = Path(".vscode")
    vscode_dir.mkdir(exist_ok=True)

    # 增强的settings.json配置
    settings = {
        # Python解释器配置
        "python.defaultInterpreterPath": "./venv310/Scripts/python.exe",
        "python.pythonPath": "./venv310/Scripts/python.exe",
        # 语言服务器配置
        "python.languageServer": "Pylance",
        "python.analysis.typeCheckingMode": "basic",
        "python.analysis.autoImportCompletions": True,
        "python.analysis.diagnosticMode": "workspace",
        "python.analysis.indexing": True,
        "python.analysis.packageIndexDepths": [
            {"name": "", "depth": 2},
            {"name": "vnpy", "depth": 1},
        ],
        # Linting配置
        "python.linting.enabled": True,
        "python.linting.pylintEnabled": True,
        "python.linting.flake8Enabled": True,
        "python.linting.mypyEnabled": False,
        "python.linting.lintOnSave": True,
        "python.linting.pylintArgs": [
            "--disable=C0413,C0415,C0301,W0718,W0611,W0621,W0404,R1705"
        ],
        "python.linting.flake8Args": [
            "--max-line-length=88",
            "--extend-ignore=E402,D400,I100",
        ],
        # 格式化配置
        "editor.formatOnSave": True,
        "python.formatting.provider": "black",
        "python.formatting.blackArgs": ["--line-length=88"],
        "python.sortImports.args": ["--profile", "black"],
        # 文件关联
        "files.associations": {"*.py": "python"},
        # 终端配置
        "python.terminal.activateEnvironment": True,
        "python.terminal.activateEnvInCurrentTerminal": True,
        # 调试配置
        "python.debugging.console": "integratedTerminal",
        # 工作区配置
        "python.analysis.extraPaths": ["./backend", "./ui", "./utils"],
    }

    # 写入settings.json
    with open(vscode_dir / "settings.json", "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)

    print("✓ 已创建增强的 .vscode/settings.json")

    # 创建launch.json用于调试
    launch_config = {
        "version": "0.2.0",
        "configurations": [
            {
                "name": "Python: Current File",
                "type": "python",
                "request": "launch",
                "program": "${file}",
                "console": "integratedTerminal",
                "cwd": "${workspaceFolder}",
                "python": "./venv310/Scripts/python.exe",
            },
            {
                "name": "Python: Terminal App",
                "type": "python",
                "request": "launch",
                "program": "start_terminal.py",
                "console": "integratedTerminal",
                "cwd": "${workspaceFolder}",
                "python": "./venv310/Scripts/python.exe",
            },
        ],
    }

    with open(vscode_dir / "launch.json", "w", encoding="utf-8") as f:
        json.dump(launch_config, f, indent=4, ensure_ascii=False)

    print("✓ 已创建 .vscode/launch.json")


def create_python_workspace_config():
    """创建Python工作区配置"""
    print("\n=== 创建Python工作区配置 ===")

    # 创建pyrightconfig.json (Pylance配置)
    pyright_config = {
        "include": ["backend/**/*", "ui/**/*", "utils/**/*"],
        "exclude": ["**/__pycache__", "**/venv*", "**/node_modules"],
        "pythonVersion": "3.10",
        "pythonPlatform": "Windows",
        "executionEnvironments": [
            {"root": ".", "pythonVersion": "3.10", "pythonPlatform": "Windows"}
        ],
        "typeCheckingMode": "basic",
        "useLibraryCodeForTypes": True,
        "autoImportCompletions": True,
    }

    with open("pyrightconfig.json", "w", encoding="utf-8") as f:
        json.dump(pyright_config, f, indent=4, ensure_ascii=False)

    print("✓ 已创建 pyrightconfig.json")


def test_python_environment():
    """测试Python环境"""
    print("\n=== 测试Python环境 ===")

    # 测试Python解释器
    try:
        result = subprocess.run(
            [sys.executable, "--version"], capture_output=True, text=True
        )
        print(f"✓ Python版本: {result.stdout.strip()}")
    except Exception as e:
        print(f"✗ Python测试失败: {e}")

    # 测试虚拟环境
    venv_python = Path("venv310/Scripts/python.exe")
    if venv_python.exists():
        try:
            result = subprocess.run(
                [str(venv_python), "--version"], capture_output=True, text=True
            )
            print(f"✓ 虚拟环境Python: {result.stdout.strip()}")
        except Exception as e:
            print(f"✗ 虚拟环境测试失败: {e}")
    else:
        print("⚠ 虚拟环境不存在")

    # 测试关键包
    packages = ["pylint", "flake8", "black", "isort"]
    for package in packages:
        try:
            result = subprocess.run(
                [sys.executable, "-m", package, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                version = result.stdout.strip().split("\n")[0]
                print(f"✓ {package}: {version}")
            else:
                print(f"⚠ {package}: 版本检查失败")
        except Exception as e:
            print(f"✗ {package}: {e}")


def create_restart_script():
    """创建重启脚本"""
    print("\n=== 创建重启脚本 ===")

    restart_script = '''# -*- coding: utf-8 -*-
"""
Cursor IDE Python语言服务器重启脚本
当遇到 'python.analysis.restartLanguageServer' not found 时使用
"""

import subprocess
import sys
import time
from pathlib import Path

def restart_cursor_python():
    """重启Cursor IDE的Python功能"""
    print("=== 重启Cursor IDE Python功能 ===")

    # 检查虚拟环境
    venv_python = Path("venv310/Scripts/python.exe")
    if not venv_python.exists():
        print("✗ 虚拟环境不存在，请先创建虚拟环境")
        return False

    print("✓ 虚拟环境存在")

    # 测试Python包
    packages = ["pylint", "flake8", "black"]
    for package in packages:
        try:
            subprocess.run([str(venv_python), "-m", package, "--version"],
                          capture_output=True, timeout=5)
            print(f"✓ {package} 可用")
        except Exception:
            print(f"⚠ {package} 不可用")

    print("\\n请按以下步骤操作:")
    print("1. 关闭Cursor IDE")
    print("2. 重新打开Cursor IDE")
    print("3. 按 Ctrl+Shift+P")
    print("4. 搜索 'Python: Select Interpreter'")
    print("5. 选择: ./venv310/Scripts/python.exe")
    print("6. 按 Ctrl+Shift+P")
    print("7. 搜索 'Developer: Reload Window'")
    print("8. 等待语言服务器启动")

    return True

if __name__ == "__main__":
    restart_cursor_python()
'''

    with open("restart_cursor_python.py", "w", encoding="utf-8") as f:
        f.write(restart_script)

    print("✓ 已创建 restart_cursor_python.py")


def main():
    """主函数"""
    print("=== 修复Cursor IDE Python语言服务器 ===\\n")

    check_python_extension()
    create_enhanced_vscode_config()
    create_python_workspace_config()
    test_python_environment()
    create_restart_script()

    print("\\n=== 修复完成 ===")
    print("\\n如果问题仍然存在，请:")
    print("1. 确保安装了Python扩展")
    print("2. 运行: python restart_cursor_python.py")
    print("3. 按照脚本提示重启Cursor IDE")
    print("4. 检查输出面板中的Python日志")


if __name__ == "__main__":
    main()
