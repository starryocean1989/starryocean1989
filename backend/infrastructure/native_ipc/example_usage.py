# -*- coding: utf-8 -*-
"""
native_ipc 使用示例

演示如何使用 native_ipc 进行跨进程通信。
"""

import asyncio
from backend.infrastructure.native_ipc import AsyncIPCPipe, IPC_AVAILABLE


async def example_basic_communication():
    """示例1：基本的服务端-客户端通信"""
    print("\n=== 示例1：基本通信 ===")
    
    pipe_name = "example_basic"
    
    async def server():
        async with await AsyncIPCPipe.server(pipe_name) as pipe:
            print("服务端：已启动，等待客户端连接...")
            await asyncio.sleep(0.5)  # 等待客户端连接
            
            # 接收客户端请求
            request = await pipe.read()
            print(f"服务端：收到请求 - {request.decode()}")
            
            # 发送响应
            response = b"Hello from server!"
            await pipe.write(response)
            print(f"服务端：已发送响应 - {response.decode()}")
    
    async def client():
        await asyncio.sleep(0.3)  # 等待服务端准备好
        
        async with await AsyncIPCPipe.client(pipe_name) as pipe:
            print("客户端：已连接到服务端")
            
            # 发送请求
            request = b"Hello from client!"
            await pipe.write(request)
            print(f"客户端：已发送请求 - {request.decode()}")
            
            # 接收响应
            response = await pipe.read()
            print(f"客户端：收到响应 - {response.decode()}")
    
    await asyncio.gather(server(), client())


async def example_bidirectional_communication():
    """示例2：双向通信（多次往返）"""
    print("\n=== 示例2：双向通信 ===")
    
    pipe_name = "example_bidirectional"
    
    async def server():
        async with await AsyncIPCPipe.server(pipe_name) as pipe:
            print("服务端：已启动")
            await asyncio.sleep(0.5)
            
            for i in range(3):
                # 接收请求
                request = await pipe.read()
                print(f"服务端：第{i+1}次收到 - {request.decode()}")
                
                # 发送响应
                response = f"Response {i+1}".encode()
                await pipe.write(response)
                print(f"服务端：第{i+1}次发送 - {response.decode()}")
    
    async def client():
        await asyncio.sleep(0.2)
        
        async with AsyncIPCPipe.client(pipe_name) as pipe:
            print("客户端：已连接")
            
            for i in range(3):
                # 发送请求
                request = f"Request {i+1}".encode()
                await pipe.write(request)
                print(f"客户端：第{i+1}次发送 - {request.decode()}")
                
                # 接收响应
                response = await pipe.read()
                print(f"客户端：第{i+1}次收到 - {response.decode()}")
    
    await asyncio.gather(server(), client())


async def example_large_data_transfer():
    """示例3：大数据传输"""
    print("\n=== 示例3：大数据传输 ===")
    
    pipe_name = "example_large_data"
    
    # 创建1MB数据
    large_data = b"X" * (1024 * 1024)
    
    async def server():
        async with AsyncIPCPipe.server(pipe_name) as pipe:
            print(f"服务端：准备接收大数据...")
            await asyncio.sleep(0.1)
            
            import time
            start = time.time()
            
            # 接收大数据
            data = await pipe.read(len(large_data))
            
            elapsed = time.time() - start
            throughput = (len(data) / (1024 * 1024)) / elapsed
            
            print(f"服务端：接收完成")
            print(f"  - 数据大小: {len(data) / (1024 * 1024):.2f} MB")
            print(f"  - 耗时: {elapsed:.3f} 秒")
            print(f"  - 吞吐量: {throughput:.2f} MB/s")
    
    async def client():
        await asyncio.sleep(0.2)
        
        async with AsyncIPCPipe.client(pipe_name) as pipe:
            print(f"客户端：开始发送大数据（{len(large_data) / (1024 * 1024):.2f} MB）...")
            
            import time
            start = time.time()
            
            # 发送大数据
            await pipe.write(large_data)
            
            elapsed = time.time() - start
            print(f"客户端：发送完成，耗时 {elapsed:.3f} 秒")
    
    await asyncio.gather(server(), client())


async def example_concurrent_pipes():
    """示例4：多管道并发通信"""
    print("\n=== 示例4：并发通信 ===")
    
    num_pipes = 5
    
    async def server_handler(pipe_id):
        pipe_name = f"example_concurrent_{pipe_id}"
        async with AsyncIPCPipe.server(pipe_name) as pipe:
            await asyncio.sleep(0.1)
            
            request = await pipe.read()
            print(f"服务端{pipe_id}：收到 - {request.decode()}")
            
            response = f"Response from server {pipe_id}".encode()
            await pipe.write(response)
    
    async def client_handler(pipe_id):
        await asyncio.sleep(0.2)
        
        pipe_name = f"example_concurrent_{pipe_id}"
        async with AsyncIPCPipe.client(pipe_name) as pipe:
            request = f"Request from client {pipe_id}".encode()
            await pipe.write(request)
            print(f"客户端{pipe_id}：发送 - {request.decode()}")
            
            response = await pipe.read()
            print(f"客户端{pipe_id}：收到 - {response.decode()}")
    
    # 创建多个服务端和客户端任务
    server_tasks = [server_handler(i) for i in range(num_pipes)]
    client_tasks = [client_handler(i) for i in range(num_pipes)]
    
    print(f"启动 {num_pipes} 个并发管道...")
    await asyncio.gather(*server_tasks, *client_tasks)
    print("所有并发通信完成")


async def example_simplified_api():
    """示例5：使用简化API"""
    print("\n=== 示例5：简化API ===")
    
    from backend.infrastructure.native_ipc import aopen_server, aopen_client
    
    pipe_name = "example_simplified"
    
    async def server():
        # 使用简化API创建服务端
        async with await aopen_server(pipe_name) as pipe:
            print("服务端：使用简化API启动")
            await asyncio.sleep(0.1)
            
            data = await pipe.read()
            print(f"服务端：收到 - {data.decode()}")
            await pipe.write(b"ACK")
    
    async def client():
        await asyncio.sleep(0.2)
        
        # 使用简化API连接客户端
        async with await aopen_client(pipe_name) as pipe:
            print("客户端：使用简化API连接")
            
            await pipe.write(b"Hello with simplified API")
            response = await pipe.read()
            print(f"客户端：收到 - {response.decode()}")
    
    await asyncio.gather(server(), client())


async def main():
    """运行所有示例"""
    print("=" * 60)
    print("native_ipc 使用示例")
    print("=" * 60)
    
    # 检查IPC是否可用
    if not IPC_AVAILABLE:
        print("\n错误：IPC扩展不可用")
        print("请先编译C扩展：")
        print("  cd backend/infrastructure/native_ipc")
        print("  python setup.py build_ext --inplace")
        return
    
    print(f"IPC扩展已加载，开始运行示例...\n")
    
    # 运行所有示例
    await example_basic_communication()
    await example_bidirectional_communication()
    await example_large_data_transfer()
    await example_concurrent_pipes()
    await example_simplified_api()
    
    print("\n" + "=" * 60)
    print("所有示例运行完成！")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
