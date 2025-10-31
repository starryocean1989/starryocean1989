# -*- coding: utf-8 -*-
"""
简单的 IPC 测试 - 验证基本功能
"""

import asyncio
import time


async def test_simple_ipc():
    """最简单的IPC测试"""
    import sys
    sys.path.insert(0, 'C:/Users/USER/Desktop/terminal_v0.50')
    from backend.infrastructure.native_ipc import AsyncIPCPipe
    
    pipe_name = "test_simple"
    
    async def server():
        print("服务端：创建管道...")
        async with await AsyncIPCPipe.server(pipe_name) as pipe:
            print("服务端：管道已创建，等待客户端连接...")
            
            # 等待更长时间确保客户端连接
            await asyncio.sleep(1.0)
            
            print("服务端：尝试读取...")
            try:
                data = await pipe.read()
                print(f"服务端：收到数据 - {data}")
                
                print("服务端：发送响应...")
                await pipe.write(b"Hello from server")
                print("服务端：完成")
            except Exception as e:
                print(f"服务端错误: {e}")
                import traceback
                traceback.print_exc()
    
    async def client():
        print("客户端：等待服务端准备...")
        await asyncio.sleep(0.5)
        
        print("客户端：连接到服务端...")
        try:
            async with await AsyncIPCPipe.client(pipe_name) as pipe:
                print("客户端：已连接")
                
                print("客户端：发送数据...")
                await pipe.write(b"Hello from client")
                print("客户端：数据已发送")
                
                print("客户端：等待响应...")
                response = await pipe.read()
                print(f"客户端：收到响应 - {response}")
                print("客户端：完成")
        except Exception as e:
            print(f"客户端错误: {e}")
            import traceback
            traceback.print_exc()
    
    print("=" * 60)
    print("开始 IPC 测试")
    print("=" * 60)
    
    await asyncio.gather(server(), client())
    
    print("=" * 60)
    print("测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_simple_ipc())
