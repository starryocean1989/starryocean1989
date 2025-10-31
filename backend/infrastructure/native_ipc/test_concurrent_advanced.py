"""
并发通信能力测试 - 验证多管道同时通信的能力
"""
import asyncio
import time
import sys
import os

# 添加路径以导入模块
sys.path.insert(0, os.path.dirname(__file__))

from async_ipc import AsyncIPCPipe


async def concurrent_server(pipe_name: str, message_count: int = 10):
    """并发服务器处理"""
    results = []
    try:
        async with await AsyncIPCPipe.server(pipe_name) as pipe:
            # 等待客户端连接
            await asyncio.sleep(2.5)  # 增加等待时间
            
            for i in range(message_count):
                data = await pipe.read(4096)
                results.append(len(data))
                # 回显数据
                await pipe.write(data)
    except Exception as e:
        print(f"Server {pipe_name} error: {e}")
        raise
    return results


async def concurrent_client(pipe_name: str, message_count: int = 10, data_size: int = 1024):
    """并发客户端通信"""
    results = []
    try:
        # 不需要额外等待，因为主函数已经等待
        async with await AsyncIPCPipe.client(pipe_name) as pipe:
            for i in range(message_count):
                test_data = b'X' * data_size
                await pipe.write(test_data)
                
                # 读取回显
                received = await pipe.read(data_size)
                results.append(len(received) == data_size)
    except Exception as e:
        print(f"Client {pipe_name} error: {e}")
        raise
    return results


async def test_multiple_pipes_concurrent(pipe_count: int = 10):
    """测试多个管道并发通信（分批执行）"""
    print(f"\n=== 测试 {pipe_count} 个管道并发通信（分批执行） ===")
    
    start_time = time.time()
    
    # 分批执行，每批次同时处理多个管道
    batch_size = 5
    all_success_count = 0
    all_error_count = 0
    
    for batch_start in range(0, pipe_count, batch_size):
        batch_end = min(batch_start + batch_size, pipe_count)
        batch_count = batch_end - batch_start
        print(f"  批次 {batch_start//batch_size + 1}: 管道 {batch_start}-{batch_end-1}")
        
        # 先启动所有服务器
        server_tasks = []
        for i in range(batch_start, batch_end):
            pipe_name = f"test_concurrent_{i}"
            server_task = asyncio.create_task(concurrent_server(pipe_name, message_count=5))
            server_tasks.append(server_task)
        
        # 等待服务器启动
        await asyncio.sleep(2.0)
        
        # 启动所有客户端
        client_tasks = []
        for i in range(batch_start, batch_end):
            pipe_name = f"test_concurrent_{i}"
            client_task = asyncio.create_task(concurrent_client(pipe_name, message_count=5, data_size=1024))
            client_tasks.append(client_task)
        
        # 等待批次完成
        all_tasks = server_tasks + client_tasks
        results = await asyncio.gather(*all_tasks, return_exceptions=True)
        
        # 统计结果
        success_count = sum(1 for r in results if not isinstance(r, Exception))
        error_count = sum(1 for r in results if isinstance(r, Exception))
        
        all_success_count += success_count
        all_error_count += error_count
        
        if error_count > 0:
            print(f"    失败: {error_count}/{len(all_tasks)}")
        else:
            print(f"    成功: {len(all_tasks)}/{len(all_tasks)}")
    
    elapsed = time.time() - start_time
    total_tasks = pipe_count * 2
    
    print(f"\n完成时间: {elapsed:.2f} 秒")
    print(f"成功任务: {all_success_count}/{total_tasks}")
    print(f"失败任务: {all_error_count}/{total_tasks}")
    
    assert all_error_count == 0, f"有 {all_error_count} 个任务失败"
    print("✅ 并发管道测试通过")


async def test_high_throughput_concurrent():
    """测试高吞吐量并发场景"""
    print("\n=== 测试高吞吐量并发（5个管道，每个传输1MB×10） ===")
    
    pipe_count = 5
    data_size = 1024 * 1024  # 1MB per message
    message_count = 10
    
    start_time = time.time()
    
    # 先启动所有服务器
    server_tasks = []
    for i in range(pipe_count):
        pipe_name = f"test_throughput_{i}"
        server_task = asyncio.create_task(concurrent_server(pipe_name, message_count=message_count))
        server_tasks.append(server_task)
    
    # 等待服务器启动
    await asyncio.sleep(2.0)
    
    # 启动所有客户端
    client_tasks = []
    for i in range(pipe_count):
        pipe_name = f"test_throughput_{i}"
        client_task = asyncio.create_task(concurrent_client(pipe_name, message_count=message_count, data_size=data_size))
        client_tasks.append(client_task)
    
    all_tasks = server_tasks + client_tasks
    results = await asyncio.gather(*all_tasks, return_exceptions=True)
    
    elapsed = time.time() - start_time
    total_bytes = pipe_count * message_count * data_size * 2  # *2 for bidirectional
    throughput_mbps = (total_bytes / (1024 * 1024)) / elapsed
    
    error_count = sum(1 for r in results if isinstance(r, Exception))
    
    print(f"完成时间: {elapsed:.2f} 秒")
    print(f"总数据量: {total_bytes / (1024 * 1024):.2f} MB")
    print(f"并发吞吐量: {throughput_mbps:.2f} MB/s")
    print(f"失败任务: {error_count}/{len(all_tasks)}")
    
    assert error_count == 0, f"有 {error_count} 个任务失败"
    print("✅ 高吞吐量并发测试通过")


async def test_stress_many_pipes():
    """压力测试 - 大量管道"""
    print("\n=== 压力测试：50个管道并发（分批执行） ===")
    
    pipe_count = 50
    
    start_time = time.time()
    
    # 分批执行避免资源耗尽
    batch_size = 10
    all_success = True
    
    for batch_start in range(0, pipe_count, batch_size):
        batch_end = min(batch_start + batch_size, pipe_count)
        print(f"执行批次 {batch_start}-{batch_end}...")
        
        # 先启动服务器
        server_tasks = []
        for i in range(batch_start, batch_end):
            pipe_name = f"test_stress_{i}"
            server_task = asyncio.create_task(concurrent_server(pipe_name, message_count=3))
            server_tasks.append(server_task)
        
        # 等待服务器启动
        await asyncio.sleep(2.0)
        
        # 启动客户端
        client_tasks = []
        for i in range(batch_start, batch_end):
            pipe_name = f"test_stress_{i}"
            client_task = asyncio.create_task(concurrent_client(pipe_name, message_count=3, data_size=512))
            client_tasks.append(client_task)
        
        all_tasks = server_tasks + client_tasks
        results = await asyncio.gather(*all_tasks, return_exceptions=True)
        error_count = sum(1 for r in results if isinstance(r, Exception))
        
        if error_count > 0:
            all_success = False
            print(f"  批次失败: {error_count}/{len(all_tasks)}")
        else:
            print(f"  批次成功: {len(all_tasks)}/{len(all_tasks)}")
    
    elapsed = time.time() - start_time
    print(f"总完成时间: {elapsed:.2f} 秒")
    
    assert all_success, "部分批次失败"
    print("✅ 压力测试通过")


async def main():
    """运行所有并发测试"""
    print("=" * 60)
    print("并发通信能力测试套件")
    print("=" * 60)
    
    try:
        # 测试1: 中等规模并发
        await test_multiple_pipes_concurrent(pipe_count=10)
        
        # 测试2: 高吞吐量并发
        await test_high_throughput_concurrent()
        
        # 测试3: 大量管道压力测试
        await test_stress_many_pipes()
        
        print("\n" + "=" * 60)
        print("✅ 所有并发测试通过!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
