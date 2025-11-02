#!/usr/bin/env python3
"""
监控进程IPC通信诊断脚本
用于诊断"未知错误"和空响应问题
"""

import asyncio
import json
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_monitor_ipc():
    """测试监控进程IPC通信"""
    print("🔧 监控进程IPC通信诊断")
    print("=" * 60)
    
    try:
        from backend.infrastructure.native_ipc import AsyncIPCPipe, IPC_AVAILABLE
        
        if not IPC_AVAILABLE:
            print("❌ Native IPC不可用，请编译C扩展")
            return False
            
        print("✅ Native IPC可用")
        
        # 测试各种查询
        test_queries = [
            {"action": "get_data", "description": "获取监控数据"},
            {"action": "get_all", "description": "获取所有数据"},
            {"action": "trigger_smart", "description": "触发SMART采集"},
            {"action": "get_bandwidth", "description": "获取带宽信息"},
            {"action": "invalid_action", "description": "无效操作（测试错误处理）"}
        ]
        
        for i, query in enumerate(test_queries, 1):
            print(f"\n[测试 {i}/{len(test_queries)}] {query['description']}")
            print(f"请求: {query['action']}")
            
            try:
                async with AsyncIPCPipe.client("monitor_query") as pipe:
                    # 发送请求
                    request = json.dumps({"action": query["action"]})
                    await pipe.write(request.encode())
                    print(f"✅ 请求已发送: {len(request)} 字节")
                    
                    # 读取响应
                    response_data = await asyncio.wait_for(
                        pipe.read(size=65536), timeout=5.0
                    )
                    print(f"✅ 响应已接收: {len(response_data)} 字节")
                    
                    # 解析响应
                    if response_data:
                        try:
                            response = json.loads(response_data.decode())
                            print(f"✅ JSON解析成功")
                            
                            # 分析响应内容
                            if isinstance(response, dict):
                                if "status" in response:
                                    status = response["status"]
                                    print(f"📊 状态: {status}")
                                    
                                    if status == "success":
                                        if "data" in response:
                                            data = response["data"]
                                            if isinstance(data, dict):
                                                print(f"📊 数据键: {list(data.keys())}")
                                                # 检查各个数据部分
                                                for key in ["system", "hardware", "process", "bandwidth"]:
                                                    if key in data:
                                                        value = data[key]
                                                        if isinstance(value, dict):
                                                            print(f"  - {key}: {len(value)} 个字段")
                                                        else:
                                                            print(f"  - {key}: {type(value).__name__}")
                                            else:
                                                print(f"📊 数据类型: {type(data).__name__}")
                                        else:
                                            print("📊 无data字段")
                                    elif status == "error":
                                        message = response.get("message", "无错误信息")
                                        print(f"❌ 错误: {message}")
                                elif "error" in response:
                                    error = response["error"]
                                    print(f"❌ 错误: {error}")
                                else:
                                    print(f"📊 响应字段: {list(response.keys())}")
                                    print(f"📊 响应内容: {str(response)[:200]}...")
                            else:
                                print(f"⚠️ 响应不是字典: {type(response).__name__}")
                                print(f"📊 响应内容: {str(response)[:200]}...")
                                
                        except json.JSONDecodeError as e:
                            print(f"❌ JSON解析失败: {e}")
                            print(f"📊 原始数据: {response_data[:200]}...")
                    else:
                        print("❌ 响应为空")
                        
            except asyncio.TimeoutError:
                print("❌ 请求超时（5秒）")
            except Exception as e:
                print(f"❌ 请求失败: {e}")
                import traceback
                traceback.print_exc()
                
        return True
        
    except ImportError as e:
        print(f"❌ 导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_monitor_status():
    """检查监控进程状态"""
    print("\n🔍 监控进程状态检查")
    print("=" * 60)
    
    # 检查信号文件
    signal_file = "logs/monitor_ready.signal"
    if os.path.exists(signal_file):
        print(f"✅ 监控信号文件存在: {signal_file}")
        try:
            with open(signal_file, 'r') as f:
                signal_data = json.load(f)
                print(f"📊 监控进程PID: {signal_data.get('pid')}")
                print(f"📊 状态: {signal_data.get('status')}")
                print(f"📊 管道: {signal_data.get('pipes', {})}")
                
                # 检查进程是否还在运行
                import psutil
                pid = signal_data.get('pid')
                if pid:
                    try:
                        proc = psutil.Process(pid)
                        if proc.is_running():
                            print(f"✅ 监控进程正在运行 (PID: {pid})")
                            print(f"📊 CPU使用率: {proc.cpu_percent()}%")
                            print(f"📊 内存使用: {proc.memory_info().rss / 1024 / 1024:.1f} MB")
                        else:
                            print(f"❌ 监控进程已停止 (PID: {pid})")
                    except psutil.NoSuchProcess:
                        print(f"❌ 监控进程不存在 (PID: {pid})")
                        
        except Exception as e:
            print(f"❌ 读取信号文件失败: {e}")
    else:
        print(f"❌ 监控信号文件不存在: {signal_file}")

def main():
    """主函数"""
    print("🚀 监控进程IPC通信诊断工具")
    print("=" * 80)
    
    # 检查监控进程状态
    asyncio.run(test_monitor_status())
    
    # 测试IPC通信
    success = asyncio.run(test_monitor_ipc())
    
    print("\n" + "=" * 80)
    if success:
        print("🎉 诊断完成！请查看上述输出分析问题。")
    else:
        print("❌ 诊断失败！请检查环境配置。")
    
    print("\n💡 常见问题解决方案:")
    print("1. 如果响应为空 -> 检查监控进程是否正常运行")
    print("2. 如果JSON解析失败 -> 检查数据传输是否完整")
    print("3. 如果连接失败 -> 检查管道是否创建成功")
    print("4. 如果超时 -> 检查监控进程是否卡死")

if __name__ == "__main__":
    main()