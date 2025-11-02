#!/usr/bin/env python3
"""
重启监控进程工具
"""

import asyncio
import json
import sys
import os
import time
import psutil
import subprocess
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

def find_monitor_process():
    """查找监控进程"""
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                cmdline = proc.info['cmdline'] or []
                cmdline_str = ' '.join(cmdline)
                if 'monitor_system' in cmdline_str:
                    return proc.info['pid']
        except:
            pass
    return None

def kill_monitor_process():
    """终止监控进程"""
    pid = find_monitor_process()
    if pid:
        try:
            proc = psutil.Process(pid)
            proc.terminate()
            proc.wait(timeout=5)
            print(f"✅ 监控进程 {pid} 已终止")
            return True
        except psutil.TimeoutExpired:
            try:
                proc.kill()
                print(f"✅ 监控进程 {pid} 已强制终止")
                return True
            except:
                print(f"❌ 无法终止监控进程 {pid}")
                return False
        except Exception as e:
            print(f"❌ 终止监控进程失败: {e}")
            return False
    else:
        print("ℹ️ 未找到监控进程")
        return True

def cleanup_signal_files():
    """清理信号文件"""
    signal_files = [
        "logs/monitor_ready.signal",
        "logs/monitor_ports.json"
    ]
    
    for file_path in signal_files:
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                print(f"✅ 已删除信号文件: {file_path}")
            except Exception as e:
                print(f"❌ 删除信号文件失败 {file_path}: {e}")

def start_monitor_process():
    """启动监控进程"""
    try:
        # 使用与主进程相同的Python环境
        python_exe = sys.executable
        script_path = Path("backend/infrastructure/system_vnpy/monitor_system.py").resolve()
        
        print(f"启动监控进程: {python_exe} {script_path}")
        
        # 设置环境变量，确保Python能找到模块
        env = os.environ.copy()
        project_root = str(Path(__file__).parent.resolve())
        if 'PYTHONPATH' in env:
            env['PYTHONPATH'] = f"{project_root};{env['PYTHONPATH']}"
        else:
            env['PYTHONPATH'] = project_root
        
        # 启动监控进程
        proc = subprocess.Popen(
            [python_exe, str(script_path)],
            cwd=project_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        
        print(f"✅ 监控进程已启动，PID: {proc.pid}")
        
        # 等待信号文件创建
        signal_file = "logs/monitor_ready.signal"
        max_wait = 10  # 最多等待10秒
        
        for i in range(max_wait):
            if os.path.exists(signal_file):
                try:
                    with open(signal_file, 'r') as f:
                        signal_data = json.load(f)
                    print(f"✅ 监控进程就绪，状态: {signal_data.get('status')}")
                    return True
                except:
                    pass
            
            print(f"⏳ 等待监控进程就绪... ({i+1}/{max_wait})")
            time.sleep(1)
        
        print("❌ 监控进程启动超时")
        return False
        
    except Exception as e:
        print(f"❌ 启动监控进程失败: {e}")
        return False

async def test_ipc_connection():
    """测试IPC连接"""
    try:
        from backend.infrastructure.native_ipc import aopen_client, IPC_AVAILABLE
        
        if not IPC_AVAILABLE:
            print("❌ IPC扩展不可用")
            return False
        
        print("🔍 测试IPC连接...")
        
        async with await aopen_client("monitor_query") as pipe:
            print("✅ IPC连接成功")
            
            # 发送测试请求
            request = {"action": "get_data"}
            request_bytes = json.dumps(request).encode('utf-8')
            
            await pipe.write(request_bytes)
            response_bytes = await asyncio.wait_for(pipe.read(size=65536), timeout=3.0)
            
            if response_bytes:
                response_data = json.loads(response_bytes.decode('utf-8'))
                print(f"✅ 收到响应，包含键: {list(response_data.keys())}")
                return True
            else:
                print("❌ 收到空响应")
                return False
                
    except Exception as e:
        print(f"❌ IPC连接测试失败: {e}")
        return False

def main():
    """主函数"""
    print("🔧 监控进程重启工具")
    print("=" * 50)
    
    # 1. 终止现有监控进程
    print("\n📊 步骤1: 终止现有监控进程")
    if not kill_monitor_process():
        print("❌ 无法终止监控进程，请手动处理")
        return
    
    # 2. 清理信号文件
    print("\n📊 步骤2: 清理信号文件")
    cleanup_signal_files()
    
    # 3. 等待一下
    print("\n📊 步骤3: 等待系统清理...")
    time.sleep(2)
    
    # 4. 启动新的监控进程
    print("\n📊 步骤4: 启动新的监控进程")
    if not start_monitor_process():
        print("❌ 监控进程启动失败")
        return
    
    # 5. 测试IPC连接
    print("\n📊 步骤5: 测试IPC连接")
    try:
        success = asyncio.run(test_ipc_connection())
        if success:
            print("🎉 监控进程重启成功！")
        else:
            print("❌ IPC连接仍有问题")
    except Exception as e:
        print(f"❌ IPC测试失败: {e}")

if __name__ == "__main__":
    main()