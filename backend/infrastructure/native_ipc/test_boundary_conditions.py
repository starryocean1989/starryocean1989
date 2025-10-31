"""
边界条件测试 - 测试超大数据块、超长消息等边界场景
"""
import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))

from async_ipc import AsyncIPCPipe


async def echo_server(pipe_name: str, read_size: int = 4096):
    """回显服务器"""
    async with await AsyncIPCPipe.server(pipe_name) as pipe:
        # 等待客户端连接
        await asyncio.sleep(2.5)
        
        while True:
            try:
                data = await pipe.read(read_size)
                if not data:
                    break
                await pipe.write(data)
            except Exception:
                break


async def test_very_small_data():
    """测试极小数据（1字节）"""
    print("\n=== 测试：极小数据（1字节）===")
    
    pipe_name = "test_small_data"
    
    async def client():
        await asyncio.sleep(2.0)  # 等待服务器准备
        async with await AsyncIPCPipe.client(pipe_name) as pipe:
            await pipe.write(b"X")
            data = await pipe.read(1)
            assert data == b"X", f"数据不匹配: {data}"
            print(f"✅ 成功传输 1 字节")
            return True
    
    server_task = asyncio.create_task(echo_server(pipe_name))
    client_task = asyncio.create_task(client())
    
    result = await client_task
    server_task.cancel()
    
    return result


async def test_zero_byte_data():
    """测试零字节数据"""
    print("\n=== 测试：零字节数据 ===")
    
    pipe_name = "test_zero_byte"
    
    async def client():
        await asyncio.sleep(2.0)  # 等待服务器准备
        async with await AsyncIPCPipe.client(pipe_name) as pipe:
            await pipe.write(b"")
            # 发送一个标记表示结束
            await pipe.write(b"END")
            data = await pipe.read(3)
            assert data == b"END", f"数据不匹配: {data}"
            print(f"✅ 零字节写入不会崩溃")
            return True
    
    server_task = asyncio.create_task(echo_server(pipe_name))
    client_task = asyncio.create_task(client())
    
    result = await client_task
    server_task.cancel()
    
    return result


async def test_large_data_block():
    """测试大数据块（1MB）"""
    print("\n=== 测试：大数据块（1MB）===")
    
    pipe_name = "test_large_block"
    data_size = 1024 * 1024  # 1MB
    
    async def client():
        await asyncio.sleep(2.0)  # 等待服务器准备
        async with await AsyncIPCPipe.client(pipe_name) as pipe:
            test_data = b"A" * data_size
            
            start_time = time.time()
            await pipe.write(test_data)
            
            # 读取回显数据
            received = b""
            while len(received) < data_size:
                chunk = await pipe.read(65536)
                if not chunk:
                    break
                received += chunk
            
            elapsed = time.time() - start_time
            
            assert len(received) == data_size, f"数据大小不匹配: {len(received)} vs {data_size}"
            print(f"✅ 成功传输 {data_size / 1024 / 1024:.2f} MB，耗时 {elapsed:.2f}s")
            return True
    
    server_task = asyncio.create_task(echo_server(pipe_name, read_size=65536))
    client_task = asyncio.create_task(client())
    
    result = await client_task
    server_task.cancel()
    
    return result


async def test_very_large_data():
    """测试超大数据块（10MB）"""
    print("\n=== 测试：超大数据块（10MB）===")
    
    pipe_name = "test_very_large"
    data_size = 10 * 1024 * 1024  # 10MB
    
    async def client():
        await asyncio.sleep(2.0)  # 等待服务器准备
        async with await AsyncIPCPipe.client(pipe_name) as pipe:
            test_data = b"B" * data_size
            
            start_time = time.time()
            await pipe.write(test_data)
            
            # 读取回显数据
            received = b""
            while len(received) < data_size:
                chunk = await pipe.read(65536)
                if not chunk:
                    break
                received += chunk
            
            elapsed = time.time() - start_time
            
            assert len(received) == data_size, f"数据大小不匹配: {len(received)} vs {data_size}"
            throughput = (data_size / (1024 * 1024)) / elapsed
            print(f"✅ 成功传输 {data_size / 1024 / 1024:.2f} MB，耗时 {elapsed:.2f}s，吞吐量 {throughput:.2f} MB/s")
            return True
    
    server_task = asyncio.create_task(echo_server(pipe_name, read_size=65536))
    client_task = asyncio.create_task(client())
    
    result = await client_task
    server_task.cancel()
    
    return result


async def test_massive_data():
    """测试巨大数据块（50MB）"""
    print("\n=== 测试：巨大数据块（50MB）===")
    
    pipe_name = "test_massive"
    data_size = 50 * 1024 * 1024  # 50MB
    
    async def client():
        await asyncio.sleep(2.0)  # 等待服务器准备
        async with await AsyncIPCPipe.client(pipe_name) as pipe:
            # 分块发送以避免内存问题
            chunk_size = 1024 * 1024  # 1MB chunks
            total_sent = 0
            
            start_time = time.time()
            
            # 发送数据
            while total_sent < data_size:
                chunk = b"C" * min(chunk_size, data_size - total_sent)
                await pipe.write(chunk)
                total_sent += len(chunk)
            
            # 读取回显数据
            total_received = 0
            while total_received < data_size:
                chunk = await pipe.read(65536)
                if not chunk:
                    break
                total_received += len(chunk)
            
            elapsed = time.time() - start_time
            
            assert total_received == data_size, f"数据大小不匹配: {total_received} vs {data_size}"
            throughput = (data_size / (1024 * 1024)) / elapsed
            print(f"✅ 成功传输 {data_size / 1024 / 1024:.2f} MB，耗时 {elapsed:.2f}s，吞吐量 {throughput:.2f} MB/s")
            return True
    
    server_task = asyncio.create_task(echo_server(pipe_name, read_size=65536))
    client_task = asyncio.create_task(client())
    
    result = await client_task
    server_task.cancel()
    
    return result


async def test_rapid_small_messages():
    """测试快速连续的小消息"""
    print("\n=== 测试：快速连续小消息（1000条）===")
    
    pipe_name = "test_rapid_small"
    message_count = 1000
    
    async def server():
        async with await AsyncIPCPipe.server(pipe_name) as pipe:
            for _ in range(message_count):
                data = await pipe.read(10)
                await pipe.write(data)
    
    async def client():
        await asyncio.sleep(2.0)  # 等待服务器准备
        async with await AsyncIPCPipe.client(pipe_name) as pipe:
            start_time = time.time()
            
            for i in range(message_count):
                msg = f"MSG{i:06d}".encode()
                await pipe.write(msg)
                received = await pipe.read(10)
                assert received == msg, f"消息不匹配: {received} vs {msg}"
            
            elapsed = time.time() - start_time
            rate = message_count / elapsed
            print(f"✅ 成功传输 {message_count} 条小消息，耗时 {elapsed:.2f}s，速率 {rate:.0f} msg/s")
            return True
    
    server_task = asyncio.create_task(server())
    client_task = asyncio.create_task(client())
    
    result = await client_task
    await server_task
    
    return result


async def test_mixed_size_messages():
    """测试混合大小的消息"""
    print("\n=== 测试：混合大小消息 ===")
    
    pipe_name = "test_mixed_size"
    
    # 不同大小的消息
    sizes = [1, 10, 100, 1000, 10000, 100000, 1000000]
    
    async def server():
        async with await AsyncIPCPipe.server(pipe_name) as pipe:
            for size in sizes:
                data = await pipe.read(size)
                await pipe.write(data)
    
    async def client():
        await asyncio.sleep(2.0)  # 等待服务器准备
        async with await AsyncIPCPipe.client(pipe_name) as pipe:
            for size in sizes:
                test_data = b"X" * size
                await pipe.write(test_data)
                received = await pipe.read(size)
                assert len(received) == size, f"大小不匹配: {len(received)} vs {size}"
            
            print(f"✅ 成功传输混合大小消息: {sizes}")
            return True
    
    server_task = asyncio.create_task(server())
    client_task = asyncio.create_task(client())
    
    result = await client_task
    await server_task
    
    return result


async def main():
    """运行所有边界条件测试"""
    print("=" * 60)
    print("边界条件测试套件")
    print("=" * 60)
    
    tests = [
        ("极小数据（1字节）", test_very_small_data),
        ("零字节数据", test_zero_byte_data),
        ("大数据块（1MB）", test_large_data_block),
        ("超大数据块（10MB）", test_very_large_data),
        ("巨大数据块（50MB）", test_massive_data),
        ("快速连续小消息", test_rapid_small_messages),
        ("混合大小消息", test_mixed_size_messages),
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
    else:
        print(f"\n⚠️  {total - passed} 个测试未通过")


if __name__ == "__main__":
    asyncio.run(main())
