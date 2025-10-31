# -*- coding: utf-8 -*-
"""
快速性能测试 - 验证吞吐量
"""

import asyncio
import time


async def test_throughput():
    """测试吞吐量"""
    import sys
    sys.path.insert(0, 'C:/Users/USER/Desktop/terminal_v0.50')
    from backend.infrastructure.native_ipc import AsyncIPCPipe
    
    pipe_name = "test_throughput"
    
    # 发送 10MB 数据
    chunk_size = 4096
    num_chunks = 2560  # 10MB
    test_chunk = b"X" * chunk_size
    
    total_bytes = 0
    start_time = 0.0
    
    async def server():
        nonlocal total_bytes
        async with await AsyncIPCPipe.server(pipe_name) as pipe:
            print("服务端：准备接收数据...")
            await asyncio.sleep(0.5)
            
            for i in range(num_chunks):
                data = await pipe.read(chunk_size)
                total_bytes += len(data)
                if i % 256 == 0:  # 每 1MB 打印一次
                    print(f"服务端：已接收 {total_bytes / (1024 * 1024):.2f} MB")
    
    async def client():
        nonlocal start_time
        await asyncio.sleep(0.3)
        
        async with await AsyncIPCPipe.client(pipe_name) as pipe:
            print("客户端：开始发送数据...")
            start_time = time.time()
            
            for i in range(num_chunks):
                await pipe.write(test_chunk)
                if i % 256 == 0:
                    print(f"客户端：已发送 {(i * chunk_size) / (1024 * 1024):.2f} MB")
    
    print("=" * 60)
    print("吞吐量测试开始")
    print("=" * 60)
    
    await asyncio.gather(server(), client())
    
    elapsed = time.time() - start_time
    throughput_mbps = (total_bytes / (1024 * 1024)) / elapsed
    
    print("=" * 60)
    print(f"测试完成！")
    print(f"传输数据: {total_bytes / (1024 * 1024):.2f} MB")
    print(f"耗时: {elapsed:.3f} 秒")
    print(f"吞吐量: {throughput_mbps:.2f} MB/s")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_throughput())
