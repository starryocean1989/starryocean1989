#!/usr/bin/env python3
"""
监控进程IPC通信详细测试工具
"""

import asyncio
import json
import sys
import os
import time
import traceback
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from backend.infrastructure.native_ipc import AsyncIPCPipe, aopen_client, IPC_AVAILABLE

async def test_monitor_communication():
    """测试监控进程通信"""
    print("🔍 开始详细IPC通信测试")
    print("=" * 80)
    
    # 检查IPC是否可用
    if not IPC_AVAILABLE:
        print("❌ IPC扩展不可用")
        return
    
    # 1. 检查监控进程状态
    print("\n📊 步骤1: 检查监控进程状态")
    signal_file = "logs/monitor_ready.signal"
    if os.path.exists(signal_file):
        with open(signal_file, 'r') as f:
            signal_content = f.read().strip()
            print(f"✅ 监控信号文件存在")
            print(f"   内容: {signal_content}")
            
            try:
                signal_data = json.loads(signal_content)
                print(f"   PID: {signal_data.get('pid')}")
                print(f"   状态: {signal_data.get('status')}")
                print(f"   管道: {signal_data.get('pipes', {})}")
            except json.JSONDecodeError:
                print(f"   ⚠️ 信号文件格式错误")
    else:
        print("❌ 监控信号文件不存在")
        return
    
    # 2. 测试管道连接
    print("\n📊 步骤2: 测试管道连接")
    pipe_name = "monitor_query"
    
    try:
        # 3. 测试连接
        print("\n📊 步骤3: 尝试连接管道")
        async with await aopen_client(pipe_name) as pipe:
            print("✅ 管道连接成功")
            
            # 4. 发送测试请求
            print("\n📊 步骤4: 发送测试请求")
            test_requests = [
                {"action": "get_data"},
                {"action": "get_summary"},
                {"action": "ping"}
            ]
            
            for i, request in enumerate(test_requests, 1):
                print(f"\n🔄 测试请求 {i}: {request}")
                try:
                    # 发送请求
                    request_json = json.dumps(request)
                    request_bytes = request_json.encode('utf-8')
                    print(f"   发送数据: {len(request_bytes)} bytes")
                    
                    await pipe.write(request_bytes)
                    print("   ✅ 请求发送成功")
                    
                    # 等待响应
                    print("   ⏳ 等待响应...")
                    response_bytes = await asyncio.wait_for(
                        pipe.read(size=65536), 
                        timeout=5.0
                    )
                    
                    if response_bytes:
                        print(f"   ✅ 收到响应: {len(response_bytes)} bytes")
                        
                        try:
                            response_text = response_bytes.decode('utf-8')
                            print(f"   响应文本长度: {len(response_text)}")
                            
                            # 尝试解析JSON
                            response_data = json.loads(response_text)
                            print(f"   ✅ JSON解析成功")
                            print(f"   响应键: {list(response_data.keys())}")
                            
                            # 显示部分响应内容
                            if "timestamp" in response_data:
                                print(f"   时间戳: {response_data['timestamp']}")
                            if "system" in response_data:
                                system_keys = list(response_data["system"].keys()) if response_data["system"] else []
                                print(f"   系统数据键: {system_keys}")
                                
                        except json.JSONDecodeError as e:
                            print(f"   ❌ JSON解析失败: {e}")
                            print(f"   原始响应: {response_text[:200]}...")
                        except UnicodeDecodeError as e:
                            print(f"   ❌ 响应解码失败: {e}")
                            print(f"   原始字节: {response_bytes[:100]}...")
                    else:
                        print("   ❌ 收到空响应")
                        
                except asyncio.TimeoutError:
                    print("   ❌ 响应超时")
                except Exception as e:
                    print(f"   ❌ 请求失败: {e}")
                    traceback.print_exc()
                
                # 短暂等待
                await asyncio.sleep(0.5)
        
        print("\n✅ 连接已关闭")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("🎉 IPC通信测试完成")

if __name__ == "__main__":
    asyncio.run(test_monitor_communication())