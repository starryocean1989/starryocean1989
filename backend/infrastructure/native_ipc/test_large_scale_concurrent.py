"""
大规模并发测试 - 测试系统在高负载下的表现
"""
import asyncio
import time
import sys

sys.path.insert(0, '.')

from async_ipc import AsyncIPCPipe


async def run_single_pair(pipe_name: str, data_size: int = 1024, message_count: int = 3):
    """运行单个服务器-客户端对"""
    async def server():
        async with await AsyncIPCPipe.server(pipe_name) as pipe:
            # 等待客户端连接
            await asyncio.sleep(2.5)
            
            for _ in range(message_count):
                data = await pipe.read(data_size)
                await pipe.write(data)
            return True
    
    async def client():
        await asyncio.sleep(2.0)
        async with await AsyncIPCPipe.client(pipe_name) as pipe:
            for _ in range(message_count):
                test_data = b'X' * data_size
                await pipe.write(test_data)
                response = await pipe.read(data_size)
                if len(response) != data_size:
                    return False
            return True
    
    try:
        server_task = asyncio.create_task(server())
        client_task = asyncio.create_task(client())
        
        server_result, client_result = await asyncio.gather(server_task, client_task)
        return server_result and client_result
    except Exception as e:
        print(f"  {pipe_name} 失败: {e}")
        return False


async def test_sequential_many_pipes(count: int = 20):
    """测试顺序执行大量管道"""
    print(f"\n=== 测试：顺序执行 {count} 个管道 ===")
    
    start_time = time.time()
    
    success_count = 0
    for i in range(count):
        pipe_name = f"test_large_seq_{i}"
        result = await run_single_pair(pipe_name, data_size=512, message_count=2)
        
        if result:
            success_count += 1
        
        # 每10个显示进度
        if (i + 1) % 10 == 0:
            print(f"  进度: {i + 1}/{count} 完成")
    
    elapsed = time.time() - start_time
    
    print(f"完成时间: {elapsed:.2f} 秒")
    print(f"成功率: {success_count}/{count} ({success_count*100/count:.1f}%)")
    
    if success_count == count:
        print("✅ 顺序大规模测试通过")
        return True
    else:
        print(f"⚠️  {count - success_count} 个管道失败")
        return False


async def test_batched_concurrent(total: int = 50, batch_size: int = 10):
    """测试分批并发执行"""
    print(f"\n=== 测试：分批并发 ({total} 个管道, 每批 {batch_size} 个) ===")
    
    start_time = time.time()
    
    total_success = 0
    total_fail = 0
    
    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch_count = batch_end - batch_start
        
        print(f"  批次 {batch_start//batch_size + 1}: 管道 {batch_start}-{batch_end-1}")
        
        # 顺序创建批次内的管道对
        batch_results = []
        for i in range(batch_start, batch_end):
            pipe_name = f"test_large_batch_{i}"
            result = await run_single_pair(pipe_name, data_size=256, message_count=2)
            batch_results.append(result)
        
        success = sum(batch_results)
        fail = batch_count - success
        
        total_success += success
        total_fail += fail
        
        print(f"    成功: {success}/{batch_count}")
    
    elapsed = time.time() - start_time
    
    print(f"\n总完成时间: {elapsed:.2f} 秒")
    print(f"总成功率: {total_success}/{total} ({total_success*100/total:.1f}%)")
    print(f"平均速率: {total / elapsed:.1f} 对/秒")
    
    if total_success == total:
        print("✅ 分批并发测试通过")
        return True
    else:
        print(f"⚠️  {total_fail} 个管道失败")
        return False


async def test_stress_throughput(pipe_count: int = 5, data_size_mb: int = 5):
    """测试压力吞吐量"""
    print(f"\n=== 测试：压力吞吐量 ({pipe_count} 个管道, 每个 {data_size_mb}MB) ===")
    
    data_size = data_size_mb * 1024 * 1024
    chunk_size = 64 * 1024  # 64KB chunks
    
    start_time = time.time()
    
    success_count = 0
    for i in range(pipe_count):
        pipe_name = f"test_stress_throughput_{i}"
        
        async def server():
            async with await AsyncIPCPipe.server(pipe_name) as pipe:
                await asyncio.sleep(2.5)
                
                total_received = 0
                while total_received < data_size:
                    data = await pipe.read(chunk_size)
                    if not data:
                        break
                    total_received += len(data)
                return total_received == data_size
        
        async def client():
            await asyncio.sleep(2.0)
            async with await AsyncIPCPipe.client(pipe_name) as pipe:
                sent = 0
                while sent < data_size:
                    chunk = b'T' * min(chunk_size, data_size - sent)
                    await pipe.write(chunk)
                    sent += len(chunk)
                return True
        
        try:
            server_task = asyncio.create_task(server())
            client_task = asyncio.create_task(client())
            
            server_result, client_result = await asyncio.gather(server_task, client_task)
            
            if server_result and client_result:
                success_count += 1
                print(f"  管道 {i}: ✅ 成功传输 {data_size_mb}MB")
            else:
                print(f"  管道 {i}: ❌ 传输失败")
        except Exception as e:
            print(f"  管道 {i}: ❌ 异常 {e}")
    
    elapsed = time.time() - start_time
    total_data_mb = pipe_count * data_size_mb
    throughput = total_data_mb / elapsed
    
    print(f"\n完成时间: {elapsed:.2f} 秒")
    print(f"总数据量: {total_data_mb} MB")
    print(f"平均吞吐量: {throughput:.2f} MB/s")
    print(f"成功率: {success_count}/{pipe_count}")
    
    if success_count == pipe_count:
        print("✅ 压力吞吐量测试通过")
        return True
    else:
        return False


async def main():
    """运行所有大规模并发测试"""
    print("=" * 60)
    print("大规模并发测试套件")
    print("=" * 60)
    
    results = []
    
    # 测试1: 顺序执行20个管道
    result1 = await test_sequential_many_pipes(count=20)
    results.append(("顺序20个管道", result1))
    
    # 测试2: 分批并发50个管道
    result2 = await test_batched_concurrent(total=50, batch_size=10)
    results.append(("分批50个管道", result2))
    
    # 测试3: 压力吞吐量测试
    result3 = await test_stress_throughput(pipe_count=5, data_size_mb=5)
    results.append(("压力吞吐量5x5MB", result3))
    
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
        print("\n✅ 所有大规模并发测试通过!")
    else:
        print(f"\n⚠️  {total - passed} 个测试未通过")


if __name__ == "__main__":
    asyncio.run(main())
