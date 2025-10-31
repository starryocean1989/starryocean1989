"""
快速并发测试
"""
import asyncio
import time
import sys

sys.path.insert(0, '.')

from async_ipc import AsyncIPCPipe


async def run_pair(pipe_name: str):
    """运行一对服务器/客户端"""
    async def server():
        async with await AsyncIPCPipe.server(pipe_name) as pipe:
            await asyncio.sleep(3.0)  # 等待连接
            data = await pipe.read(1024)
            await pipe.write(b"OK: " + data)
            return True
    
    async def client():
        await asyncio.sleep(2.0)
        async with await AsyncIPCPipe.client(pipe_name) as pipe:
            await pipe.write(b"test")
            response = await pipe.read(1024)
            return response == b"OK: test"
    
    s = asyncio.create_task(server())
    c = asyncio.create_task(client())
    results = await asyncio.gather(s, c, return_exceptions=True)
    
    if any(isinstance(r, Exception) for r in results):
        print(f"❌ {pipe_name} 失败")
        for r in results:
            if isinstance(r, Exception):
                print(f"   {type(r).__name__}: {r}")
        return False
    
    print(f"✅ {pipe_name} 成功")
    return True


async def main():
    print("=" * 60)
    print("快速并发测试 (3个管道,分批)")
    print("=" * 60)
    
    start = time.time()
    
    # 批次1
    print("\n批次1...")
    results = []
    for i in range(3):
        result = await run_pair(f"test_fast_{i}")
        results.append(result)
    
    elapsed = time.time() - start
    success = sum(results)
    
    print(f"\n结果: {success}/3 成功，耗时 {elapsed:.1f}秒")
    
    if success == 3:
        print("✅ 所有测试通过")
    else:
        print("❌ 部分测试失败")


if __name__ == "__main__":
    asyncio.run(main())
