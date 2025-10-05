# -*- coding: utf-8 -*-
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
    
    print("\n请按以下步骤操作:")
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
