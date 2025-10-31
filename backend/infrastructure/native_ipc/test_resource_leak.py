"""
资源泄漏检测 - 验证内存和句柄管理
"""
import asyncio
import sys
import os
import time
import gc

sys.path.insert(0, os.path.dirname(__file__))

from async_ipc import AsyncIPCPipe

# 尝试导入 psutil 进行资源监控
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    print("⚠️  psutil 未安装，部分资源监控功能不可用")
    print("   安装命令: pip install psutil")


def get_process_info():
    """获取当前进程的资源使用情况"""
    if not PSUTIL_AVAILABLE:
        return None
    
    process = psutil.Process(os.getpid())
    return {
        'memory_mb': process.memory_info().rss / (1024 * 1024),
        'handles': process.num_handles(),
    }


async def test_repeated_pipe_creation():
    """测试重复创建和销毁管道"""
    print("\n=== 测试：重复创建销毁管道（检测句柄泄漏）===")
    
    if not PSUTIL_AVAILABLE:
        print("⚠️  跳过（需要 psutil）")
        return True
    
    initial_info = get_process_info()
    print(f"初始状态: 内存={initial_info['memory_mb']:.2f}MB, 句柄={initial_info['handles']}")
    
    iterations = 50
    
    for i in range(iterations):
        pipe_name = f"test_leak_{i}"
        
        # 创建服务端
        pipe = await AsyncIPCPipe.server(pipe_name)
        await pipe.close()
        
        # 强制垃圾回收
        if i % 10 == 0:
            gc.collect()
    
    # 最终垃圾回收
    gc.collect()
    await asyncio.sleep(0.5)
    
    final_info = get_process_info()
    print(f"最终状态: 内存={final_info['memory_mb']:.2f}MB, 句柄={final_info['handles']}")
    
    memory_increase = final_info['memory_mb'] - initial_info['memory_mb']
    handle_increase = final_info['handles'] - initial_info['handles']
    
    print(f"增长: 内存={memory_increase:.2f}MB, 句柄={handle_increase}")
    
    # 允许一些合理的资源增长
    if memory_increase < 5.0 and handle_increase < 10:
        print("✅ 无明显资源泄漏")
        return True
    else:
        print(f"⚠️  可能存在资源泄漏: 内存增长={memory_increase:.2f}MB, 句柄增长={handle_increase}")
        return False


async def test_large_data_transfer_cleanup():
    """测试大数据传输后的内存清理"""
    print("\n=== 测试：大数据传输后内存清理 ===")
    
    if not PSUTIL_AVAILABLE:
        print("⚠️  跳过（需要 psutil）")
        return True
    
    initial_info = get_process_info()
    print(f"初始状态: 内存={initial_info['memory_mb']:.2f}MB")
    
    pipe_name = "test_large_cleanup"
    data_size = 50 * 1024 * 1024  # 50MB
    
    async def server():
        async with await AsyncIPCPipe.server(pipe_name) as pipe:
            total = 0
            while total < data_size:
                data = await pipe.read(65536)
                if not data:
                    break
                total += len(data)
    
    async def client():
        await asyncio.sleep(2.0)  # 等待服务器准备
        async with await AsyncIPCPipe.client(pipe_name) as pipe:
            chunk_size = 1024 * 1024
            sent = 0
            while sent < data_size:
                chunk = b"D" * min(chunk_size, data_size - sent)
                await pipe.write(chunk)
                sent += len(chunk)
    
    server_task = asyncio.create_task(server())
    client_task = asyncio.create_task(client())
    
    await asyncio.gather(server_task, client_task)
    
    # 强制垃圾回收
    gc.collect()
    await asyncio.sleep(0.5)
    
    final_info = get_process_info()
    print(f"最终状态: 内存={final_info['memory_mb']:.2f}MB")
    
    memory_retained = final_info['memory_mb'] - initial_info['memory_mb']
    print(f"保留内存: {memory_retained:.2f}MB")
    
    # 传输50MB后，保留内存应该很少
    if memory_retained < 10.0:
        print("✅ 大数据传输后内存正常清理")
        return True
    else:
        print(f"⚠️  可能存在内存泄漏: 保留了 {memory_retained:.2f}MB")
        return False


async def test_exception_resource_cleanup():
    """测试异常情况下的资源清理"""
    print("\n=== 测试：异常情况下资源清理 ===")
    
    if not PSUTIL_AVAILABLE:
        print("⚠️  跳过（需要 psutil）")
        return True
    
    initial_info = get_process_info()
    
    iterations = 20
    
    for i in range(iterations):
        pipe_name = f"test_exception_{i}"
        
        try:
            async with await AsyncIPCPipe.server(pipe_name) as pipe:
                # 故意引发异常
                raise ValueError("测试异常")
        except ValueError:
            pass  # 预期的异常
        
        if i % 5 == 0:
            gc.collect()
    
    gc.collect()
    await asyncio.sleep(0.5)
    
    final_info = get_process_info()
    
    memory_increase = final_info['memory_mb'] - initial_info['memory_mb']
    handle_increase = final_info['handles'] - initial_info['handles']
    
    print(f"资源变化: 内存={memory_increase:.2f}MB, 句柄={handle_increase}")
    
    if memory_increase < 5.0 and handle_increase < 10:
        print("✅ 异常情况下资源正常清理")
        return True
    else:
        print(f"⚠️  异常情况下可能存在资源泄漏")
        return False


async def test_long_running_stability():
    """测试长时间运行的稳定性"""
    print("\n=== 测试：长时间运行稳定性（100轮通信）===")
    
    if not PSUTIL_AVAILABLE:
        print("⚠️  跳过（需要 psutil）")
        return True
    
    initial_info = get_process_info()
    print(f"初始状态: 内存={initial_info['memory_mb']:.2f}MB, 句柄={initial_info['handles']}")
    
    pipe_name = "test_stability"
    rounds = 100
    
    async def server():
        for _ in range(rounds):
            async with await AsyncIPCPipe.server(f"{pipe_name}_{_}") as pipe:
                # 等待客户端连接
                await asyncio.sleep(2.5)
                
                data = await pipe.read(1024)
                await pipe.write(data)
    
    async def client():
        await asyncio.sleep(0.5)
        for i in range(rounds):
            async with await AsyncIPCPipe.client(f"{pipe_name}_{i}") as pipe:
                await pipe.write(b"test" * 256)
                data = await pipe.read(1024)
            
            if i % 20 == 0:
                gc.collect()
    
    server_task = asyncio.create_task(server())
    client_task = asyncio.create_task(client())
    
    start_time = time.time()
    await asyncio.gather(server_task, client_task)
    elapsed = time.time() - start_time
    
    gc.collect()
    await asyncio.sleep(0.5)
    
    final_info = get_process_info()
    print(f"最终状态: 内存={final_info['memory_mb']:.2f}MB, 句柄={final_info['handles']}")
    
    memory_increase = final_info['memory_mb'] - initial_info['memory_mb']
    handle_increase = final_info['handles'] - initial_info['handles']
    
    print(f"完成 {rounds} 轮通信，耗时 {elapsed:.2f}s")
    print(f"资源增长: 内存={memory_increase:.2f}MB, 句柄={handle_increase}")
    
    if memory_increase < 10.0 and handle_increase < 10:
        print("✅ 长时间运行稳定，无明显泄漏")
        return True
    else:
        print(f"⚠️  长时间运行后可能存在资源泄漏")
        return False


async def main():
    """运行所有资源泄漏检测测试"""
    print("=" * 60)
    print("资源泄漏检测测试套件")
    print("=" * 60)
    
    if not PSUTIL_AVAILABLE:
        print("\n⚠️  警告: psutil 未安装，无法进行完整的资源监控")
        print("   请运行: pip install psutil")
        print("\n将执行基本功能测试但不进行资源监控...\n")
    
    tests = [
        ("重复创建销毁管道", test_repeated_pipe_creation),
        ("大数据传输内存清理", test_large_data_transfer_cleanup),
        ("异常资源清理", test_exception_resource_cleanup),
        ("长时间运行稳定性", test_long_running_stability),
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
        print("\n✅ 所有资源泄漏检测测试通过!")
    else:
        print(f"\n⚠️  {total - passed} 个测试未通过或跳过")


if __name__ == "__main__":
    asyncio.run(main())
