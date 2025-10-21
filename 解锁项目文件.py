# -*- coding: utf-8 -*-
"""
解锁项目文件 - 清理所有可能导致文件锁定的缓存和进程
"""
import os
import sys
import shutil
import psutil
from pathlib import Path
import time

def kill_related_processes():
    """终止与项目相关的Python进程"""
    current_pid = os.getpid()
    parent_pid = os.getppid()
    project_path = Path(__file__).parent.resolve()
    killed_pids = []
    
    print("🔍 检查正在运行的Python进程...")
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cwd']):
        try:
            # 跳过当前进程和父进程
            if proc.info['pid'] == current_pid or proc.info['pid'] == parent_pid:
                continue
                
            # 检查是否是Python进程
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                # 检查工作目录或命令行是否包含项目路径
                cwd = proc.info.get('cwd', '')
                cmdline = ' '.join(proc.info.get('cmdline', []))
                
                # 排除解锁脚本本身
                if '解锁项目文件.py' in cmdline:
                    continue
                
                if str(project_path) in cwd or str(project_path) in cmdline:
                    print(f"  ❌ 发现相关进程 PID={proc.info['pid']}: {proc.info['name']}")
                    print(f"     命令行: {cmdline[:100]}...")
                    proc.kill()
                    killed_pids.append(proc.info['pid'])
                    
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    
    if killed_pids:
        print(f"✅ 已终止 {len(killed_pids)} 个进程")
        time.sleep(1)  # 等待进程完全终止
    else:
        print("✅ 未发现需要终止的进程")
    
    return killed_pids

def clean_pycache():
    """清理所有 __pycache__ 目录"""
    print("\n🔍 清理 __pycache__ 目录...")
    project_path = Path(__file__).parent
    count = 0
    
    for pycache_dir in project_path.rglob('__pycache__'):
        try:
            shutil.rmtree(pycache_dir)
            print(f"  ✅ 删除: {pycache_dir.relative_to(project_path)}")
            count += 1
        except Exception as e:
            print(f"  ⚠️ 无法删除 {pycache_dir.relative_to(project_path)}: {e}")
    
    if count > 0:
        print(f"✅ 清理了 {count} 个 __pycache__ 目录")
    else:
        print("✅ 未发现 __pycache__ 目录")

def clean_pyc_files():
    """清理所有 .pyc 和 .pyo 文件"""
    print("\n🔍 清理 .pyc/.pyo 文件...")
    project_path = Path(__file__).parent
    count = 0
    
    for pattern in ['*.pyc', '*.pyo']:
        for pyc_file in project_path.rglob(pattern):
            try:
                pyc_file.unlink()
                count += 1
            except Exception as e:
                print(f"  ⚠️ 无法删除 {pyc_file.relative_to(project_path)}: {e}")
    
    if count > 0:
        print(f"✅ 清理了 {count} 个 .pyc/.pyo 文件")
    else:
        print("✅ 未发现 .pyc/.pyo 文件")

def clean_cache_files():
    """清理缓存文件"""
    print("\n🔍 清理缓存文件...")
    project_path = Path(__file__).parent
    cache_dir = project_path / 'cache'
    
    if cache_dir.exists():
        count = 0
        for cache_file in cache_dir.glob('*'):
            if cache_file.is_file():
                try:
                    cache_file.unlink()
                    print(f"  ✅ 删除: {cache_file.name}")
                    count += 1
                except Exception as e:
                    print(f"  ⚠️ 无法删除 {cache_file.name}: {e}")
        
        if count > 0:
            print(f"✅ 清理了 {count} 个缓存文件")
        else:
            print("✅ cache目录为空")
    else:
        print("✅ cache目录不存在")

def remove_readonly(func, path, excinfo):
    """移除只读属性后重试删除"""
    os.chmod(path, 0o777)
    func(path)

def unlock_readonly_files():
    """解锁所有只读文件"""
    print("\n🔍 检查只读文件...")
    project_path = Path(__file__).parent
    count = 0
    
    for file_path in project_path.rglob('*'):
        if file_path.is_file():
            try:
                # 检查是否为只读
                if not os.access(file_path, os.W_OK):
                    os.chmod(file_path, 0o666)
                    count += 1
            except Exception as e:
                print(f"  ⚠️ 无法修改 {file_path.relative_to(project_path)}: {e}")
    
    if count > 0:
        print(f"✅ 解锁了 {count} 个只读文件")
    else:
        print("✅ 未发现只读文件")

def main():
    print("=" * 60)
    print("🔧 项目文件解锁工具")
    print("=" * 60)
    
    try:
        # 1. 终止相关进程
        kill_related_processes()
        
        # 2. 清理缓存目录
        clean_pycache()
        
        # 3. 清理编译文件
        clean_pyc_files()
        
        # 4. 清理缓存文件
        clean_cache_files()
        
        # 5. 解锁只读文件
        unlock_readonly_files()
        
        print("\n" + "=" * 60)
        print("✅ 文件解锁完成！")
        print("=" * 60)
        print("\n现在您可以尝试复制项目文件了。")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ 用户中断操作")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()

