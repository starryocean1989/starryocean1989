"""
边界条件简化测试
"""
import asyncio
import sys
import time

sys.path.insert(0, '.')

from async_ipc import AsyncIPCPipe


async def test_tiny_data():
    """测试极小数据（1字节）"""
    print("\n=== 测试：1字节数据 ===")
    
    pipe_name = "test_tiny"
    
    async def server():
        async with await AsyncIPCPipe.server(pipe_name) as pipe:
            await asyncio.sleep(2.5)
            data = await pipe.read(10)
            await pipe.write(data)
    
    async def client():
        await asyncio.sleep(2.0)
        async with await AsyncIPCPipe.client(pipe_name) as pipe:
            await pipe.write(b"X")
            response = await pipe.read(1)
            return response == b"X"
    
    s = asyncio.create_task(server())
    c = asyncio.create_task(client())
    result = await c
    await s
    
    if result:
        print("✅ 1字节数据传输成功")
    return result


async def test_large_data():
    """测试大数据块（1MB）"""
    print("\n=== 测试：1MB数据块 ===")
    
    pipe_name = "test_large"
    data_size = 1024 * 1024
    
    async def server():
        async with await AsyncIPCPipe.server(pipe_name) as pipe:
            await asyncio.sleep(2.5)
            
            received = b""
            while len(received) < data_size:
                chunk = await pipe.read(65536)
                if not chunk:
                    break
                received += chunk
            
            # 等待客户端准备好接收  
            await asyncio.sleep(0.5)
            await pipe.write(b"OK")
            return len(received) == data_size
    
    async def client():
        await asyncio.sleep(2.0)
        async with await AsyncIPCPipe.client(pipe_name) as pipe:
            test_data = b"A" * data_size
            await pipe.write(test_data)
            
            response = await pipe.read(10)
            return response == b"OK"
    
    s = asyncio.create_task(server())
    c = asyncio.create_task(client())
    
    start = time.time()
    server_result, client_result = await asyncio.gather(s, c)
    elapsed = time.time() - start
    
    result = server_result and client_result
    
    if result:
        throughput = (data_size / (1024 * 1024)) / elapsed
        print(f"✅ 1MB数据传输成功，耗时 {elapsed:.2f}s，吞吐量 {throughput:.2f} MB/s")
    
    return result


async def test_very_large_data():
    """测试超大数据块（10MB）"""
    print("\n=== 测试：10MB数据块 ===")
    
    pipe_name = "test_very_large"
    data_size = 10 * 1024 * 1024
    
    async def server():
        async with await AsyncIPCPipe.server(pipe_name) as pipe:
            await asyncio.sleep(2.5)
            
            received = b""
            while len(received) < data_size:
                chunk = await pipe.read(65536)
                if not chunk:
                    break
                received += chunk
            
            # 等待客户端准备好接收  
            await asyncio.sleep(0.5)
            await pipe.write(b"OK")
            return len(received) == data_size
    
    async def client():
        await asyncio.sleep(2.0)
        async with await AsyncIPCPipe.client(pipe_name) as pipe:
            test_data = b"B" * data_size
            await pipe.write(test_data)
            
            response = await pipe.read(10)
            return response == b"OK"
    
    s = asyncio.create_task(server())
    c = asyncio.create_task(client())
    
    start = time.time()
    server_result, client_result = await asyncio.gather(s, c)
    elapsed = time.time() - start
    
    result = server_result and client_result
    
    if result:
        throughput = (data_size / (1024 * 1024)) / elapsed
        print(f"✅ 10MB数据传输成功，耗时 {elapsed:.2f}s，吞吐量 {throughput:.2f} MB/s")
    
    return result


async def test_mixed_sizes():
    """测试混合大小消息"""
    print("\n=== 测试：混合大小消息 ===")
    
    pipe_name = "test_mixed"
    sizes = [1, 10, 100, 1000, 10000]
    
    async def server():
        async with await AsyncIPCPipe.server(pipe_name) as pipe:
            await asyncio.sleep(2.5)
            
            for size in sizes:
                data = await pipe.read(size)
                await pipe.write(data)
    
    async def client():
        await asyncio.sleep(2.0)
        async with await AsyncIPCPipe.client(pipe_name) as pipe:
            for size in sizes:
                test_data = b"X" * size
                await pipe.write(test_data)
                response = await pipe.read(size)
                if len(response) != size:
                    return False
            return True
    
    s = asyncio.create_task(server())
    c = asyncio.create_task(client())
    result = await c
    await s
    
    if result:
        print(f"✅ 混合大小消息传输成功: {sizes}")
    
    return result


async def main():
    """运行所有边界条件测试"""
    print("=" * 60)
    print("边界条件简化测试套件")
    print("=" * 60)
    
    tests = [
        ("1字节数据", test_tiny_data),
        ("1MB数据块", test_large_data),
        ("10MB数据块", test_very_large_data),
        ("混合大小消息", test_mixed_sizes),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ 测试 '{name}' 失败: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    print("\n" + "=" * 60)
    print("测试结果汇总:")
    print("=" * 60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\n总计: {passed}/{total} 通过")
    
    if passed == total:
        print("\n✅ 所有边界条件测试通过!")


if __name__ == "__main__":
    asyncio.run(main())
