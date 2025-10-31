"""
简单并发测试 - 验证基本并发能力
"""
import asyncio
import time
import sys

sys.path.insert(0, '.')

from async_ipc import AsyncIPCPipe


async def simple_echo_pair(pipe_name: str):
    """单个管道的回显测试对"""
    async def server():
        try:
            async with await AsyncIPCPipe.server(pipe_name) as pipe:
                # 等待客户端连接并读取数据
                data = await pipe.read(1024)
                # 回显数据
                await pipe.write(data)
                return True
        except Exception as e:
            print(f"Server {pipe_name} error: {e}")
            return False
    
    async def client():
        try:
            # 稍微等待服务器准备
            await asyncio.sleep(0.8)
            async with await AsyncIPCPipe.client(pipe_name) as pipe:
                # 发送测试数据
                test_data = b"Test " + pipe_name.encode()
                await pipe.write(test_data)
                # 读取回显
                received = await pipe.read(len(test_data))
                return received == test_data
        except Exception as e:
            print(f"Client {pipe_name} error: {e}")
            return False
    
    server_task = asyncio.create_task(server())
    client_task = asyncio.create_task(client())
    
    server_result, client_result = await asyncio.gather(server_task, client_task)
    return server_result and client_result


async def test_sequential_pipes():
    """测试顺序执行多个管道"""
    print("\n=== 测试：顺序执行3个管道 ===")
    
    for i in range(3):
        pipe_name = f"test_seq_{i}"
        result = await simple_echo_pair(pipe_name)
        if result:
            print(f"✅ 管道 {i} 成功")
        else:
            print(f"❌ 管道 {i} 失败")
            return False
    
    print("✅ 顺序测试通过")
    return True


async def test_parallel_pipes(count=3):
    """测试并行执行多个管道"""
    print(f"\n=== 测试：并行执行{count}个管道 ===")
    
    tasks = []
    for i in range(count):
        pipe_name = f"test_par_{i}"
        task = asyncio.create_task(simple_echo_pair(pipe_name))
        tasks.append(task)
    
    results = await asyncio.gather(*tasks)
    
    success_count = sum(1 for r in results if r)
    print(f"成功: {success_count}/{count}")
    
    if success_count == count:
        print("✅ 并行测试通过")
        return True
    else:
        print(f"❌ 并行测试失败：{count - success_count}个管道失败")
        return False


async def main():
    """运行简单并发测试"""
    print("=" * 60)
    print("简单并发测试")
    print("=" * 60)
    
    # 测试1: 顺序执行
    result1 = await test_sequential_pipes()
    
    # 测试2: 并行执行(小规模)
    result2 = await test_parallel_pipes(count=3)
    
    # 测试3: 并行执行(中等规模)
    result3 = await test_parallel_pipes(count=5)
    
    print("\n" + "=" * 60)
    if result1 and result2 and result3:
        print("✅ 所有测试通过!")
    else:
        print("❌ 部分测试失败")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
