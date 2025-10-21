# -*- coding: utf-8 -*-
"""
清理项目锁定文件

功能：
1. 停止所有Python进程
2. 清理__pycache__目录
3. 清理.pyc/.pyo文件
4. 清理临时缓存

作者：星辰科技
"""

import os
import sys
import shutil
import subprocess
import time
from pathlib import Path


def kill_python_processes():
    """停止所有Python进程"""
    print("[步骤1/4] 停止所有Python进程...")
    
    if sys.platform == "win32":
        # Windows
        subprocess.run(["taskkill", "/F", "/IM", "python.exe"], 
                      capture_output=True, check=False)
        subprocess.run(["taskkill", "/F", "/IM", "pythonw.exe"], 
                      capture_output=True, check=False)
    else:
        # Linux/Mac
        subprocess.run(["pkill", "-9", "python"], 
                      capture_output=True, check=False)
    
    time.sleep(2)
    print("✓ Python进程已停止\n")


def clean_pycache():
    """清理__pycache__目录"""
    print("[步骤2/4] 清理__pycache__目录...")
    
    count = 0
    for root, dirs, files in os.walk("."):
        if "__pycache__" in dirs:
            pycache_path = Path(root) / "__pycache__"
            try:
                shutil.rmtree(pycache_path)
                print(f"  删除: {pycache_path}")
                count += 1
            except Exception as e:
                print(f"  ⚠️ 无法删除: {pycache_path} - {e}")
    
    print(f"✓ 已清理 {count} 个__pycache__目录\n")


def clean_pyc_files():
    """清理.pyc和.pyo文件"""
    print("[步骤3/4] 清理.pyc/.pyo文件...")
    
    count = 0
    for root, dirs, files in os.walk("."):
        for file in files:
            if file.endswith((".pyc", ".pyo")):
                file_path = Path(root) / file
                try:
                    file_path.unlink()
                    count += 1
                except Exception as e:
                    print(f"  ⚠️ 无法删除: {file_path} - {e}")
    
    print(f"✓ 已清理 {count} 个.pyc/.pyo文件\n")


def clean_temp_caches():
    """清理临时缓存目录"""
    print("[步骤4/4] 清理临时缓存...")
    
    temp_dirs = [".pytest_cache", ".mypy_cache", ".ruff_cache"]
    count = 0
    
    for root, dirs, files in os.walk("."):
        for temp_dir in temp_dirs:
            if temp_dir in dirs:
                temp_path = Path(root) / temp_dir
                try:
                    shutil.rmtree(temp_path)
                    print(f"  删除: {temp_path}")
                    count += 1
                except Exception as e:
                    print(f"  ⚠️ 无法删除: {temp_path} - {e}")
    
    print(f"✓ 已清理 {count} 个临时缓存目录\n")


def main():
    """主函数"""
    print("=" * 50)
    print("清理项目锁定文件")
    print("=" * 50)
    print()
    
    try:
        kill_python_processes()
        clean_pycache()
        clean_pyc_files()
        clean_temp_caches()
        
        print("=" * 50)
        print("✅ 清理完成！")
        print("=" * 50)
        print()
        print("提示：如果仍然无法复制文件，请：")
        print("1. 关闭所有打开项目的IDE（VSCode/PyCharm等）")
        print("2. 重启Windows资源管理器")
        print("3. 使用管理员权限运行此脚本")
        print()
        
    except Exception as e:
        print(f"\n❌ 清理过程出错: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()



