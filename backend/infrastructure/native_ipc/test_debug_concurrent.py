"""
调试并发问题 - 最小测试用例
"""
import asyncio
import sys

sys.path.insert(0, '.')

from async_ipc import AsyncIPCPipe


async def test_single_pipe():
    """测试单个管道"""
    print("\\n=== 测试单个管道 ===")
    
    pipe_name = "test_debug_single"
    
    async def server():
        print(f"[Server] Creating pipe: {pipe_name}")
        async with await AsyncIPCPipe.server(pipe_name) as pipe:
            print("[Server] Pipe created, waiting for client...")
            # 延迟等待,让客户端有时间连接
            await asyncio.sleep(2.0)
            
            print("[Server] Reading data...")
            data = await pipe.read(1024)
            print(f"[Server] Received: {data}")
            
            print("[Server] Writing response...")
            await pipe.write(b"Echo: " + data)
            print("[Server] Done")
    
    async def client():
        print("[Client] Waiting for server...")
        await asyncio.sleep(1.0)
        
        print(f"[Client] Connecting to pipe: {pipe_name}")
        try:
            async with await AsyncIPCPipe.client(pipe_name) as pipe:
                print("[Client] Connected")
                
                print("[Client] Sending data...")
                await pipe.write(b"Test message")
                print("[Client] Data sent")
                
                print("[Client] Reading response...")
                response = await pipe.read(1024)
                print(f"[Client] Received: {response}")
                print("[Client] Done")
                
                return True
        except Exception as e:
            print(f"[Client] Error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    server_task = asyncio.create_task(server())
    client_task = asyncio.create_task(client())
    
    try:
        await asyncio.gather(server_task, client_task)
        print("✅ 单管道测试成功")
        return True
    except Exception as e:
        print(f"❌ 单管道测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_two_pipes_sequential():
    """测试两个管道顺序执行"""
    print("\\n=== 测试两个管道顺序执行 ===")
    
    for i in range(2):
        pipe_name = f"test_debug_seq_{i}"
        
        print(f"\\n--- Pipe {i} ---")
        
        async def server():
            async with await AsyncIPCPipe.server(pipe_name) as pipe:
                await asyncio.sleep(2.0)
                data = await pipe.read(1024)
                await pipe.write(b"Echo: " + data)
                return True
        
        async def client():
            await asyncio.sleep(1.0)
            async with await AsyncIPCPipe.client(pipe_name) as pipe:
                await pipe.write(b"Test")
                response = await pipe.read(1024)
                return response.startswith(b"Echo:")
        
        server_task = asyncio.create_task(server())
        client_task = asyncio.create_task(client())
        
        try:
            results = await asyncio.gather(server_task, client_task)
            if all(results):
                print(f"✅ Pipe {i} 成功")
            else:
                print(f"❌ Pipe {i} 失败")
                return False
        except Exception as e:
            print(f"❌ Pipe {i} 异常: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    print("✅ 顺序执行测试成功")
    return True


async def main():
    print("=" * 60)
    print("调试并发问题")
    print("=" * 60)
    
    # Test 1: 单管道
    result1 = await test_single_pipe()
    
    # Test 2: 两个管道顺序执行
    result2 = await test_two_pipes_sequential()
    
    print("\\n" + "=" * 60)
    if result1 and result2:
        print("✅ 所有调试测试通过")
    else:
        print("❌ 部分调试测试失败")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
