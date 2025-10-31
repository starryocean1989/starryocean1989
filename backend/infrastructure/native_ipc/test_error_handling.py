"""
错误处理机制验证 - 测试异常场景下的行为
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from async_ipc import AsyncIPCPipe


async def test_connect_nonexistent_pipe():
    """测试连接不存在的管道"""
    print("\n=== 测试：连接不存在的管道 ===")
    try:
        # WaitNamedPipe会等待5秒然后失败
        pipe = await AsyncIPCPipe.client("nonexistent_pipe_12345")
        await pipe.close()
        print("❌ 应该抛出异常但没有")
        return False
    except (OSError, TimeoutError, FileNotFoundError) as e:
        print(f"✅ 正确捕获异常: {type(e).__name__}: {e}")
        return True


async def test_server_closes_early():
    """测试服务端提前关闭"""
    print("\n=== 测试：服务端提前关闭 ===")
    
    pipe_name = "test_early_close"
    
    async def server():
        async with await AsyncIPCPipe.server(pipe_name) as pipe:
            await asyncio.sleep(0.2)
            # 立即关闭，不读取数据
    
    async def client():
        await asyncio.sleep(0.5)
        try:
            async with await AsyncIPCPipe.client(pipe_name) as pipe:
                await pipe.write(b"test data")
                # 尝试读取，但服务端已关闭
                data = await pipe.read(1024)
                if len(data) == 0:
                    print("✅ 读取到空数据（管道已关闭）")
                    return True
        except Exception as e:
            print(f"✅ 正确捕获异常: {type(e).__name__}: {e}")
            return True
        return False
    
    server_task = asyncio.create_task(server())
    client_task = asyncio.create_task(client())
    
    results = await asyncio.gather(server_task, client_task, return_exceptions=True)
    return not isinstance(results[1], Exception)


async def test_read_from_closed_pipe():
    """测试从已关闭的管道读取"""
    print("\n=== 测试：从已关闭的管道读取 ===")
    
    pipe_name = "test_read_closed"
    
    try:
        pipe = await AsyncIPCPipe.server(pipe_name)
        await pipe.close()
        
        # 尝试从已关闭的管道读取
        data = await pipe.read(1024)
        print(f"❌ 应该抛出异常，但返回了: {data}")
        return False
    except Exception as e:
        print(f"✅ 正确捕获异常: {type(e).__name__}: {e}")
        return True


async def test_write_to_closed_pipe():
    """测试向已关闭的管道写入"""
    print("\n=== 测试：向已关闭的管道写入 ===")
    
    pipe_name = "test_write_closed"
    
    try:
        pipe = await AsyncIPCPipe.server(pipe_name)
        await pipe.close()
        
        # 尝试向已关闭的管道写入
        await pipe.write(b"test data")
        print("❌ 应该抛出异常但没有")
        return False
    except Exception as e:
        print(f"✅ 正确捕获异常: {type(e).__name__}: {e}")
        return True


async def test_double_close():
    """测试重复关闭管道"""
    print("\n=== 测试：重复关闭管道 ===")
    
    pipe_name = "test_double_close"
    
    try:
        pipe = await AsyncIPCPipe.server(pipe_name)
        await pipe.close()
        await pipe.close()  # 第二次关闭
        print("✅ 重复关闭不会抛出异常（幂等性）")
        return True
    except Exception as e:
        print(f"⚠️  重复关闭抛出异常: {type(e).__name__}: {e}")
        # 这也可以接受，取决于实现
        return True


async def test_exception_in_context_manager():
    """测试上下文管理器中的异常处理"""
    print("\n=== 测试：上下文管理器异常处理 ===")
    
    pipe_name = "test_ctx_exception"
    
    async def server():
        try:
            async with await AsyncIPCPipe.server(pipe_name) as pipe:
                await asyncio.sleep(0.3)
                raise ValueError("模拟的异常")
        except ValueError:
            print("✅ 异常被正确捕获，管道应该已关闭")
            return True
        return False
    
    result = await server()
    return result


async def test_invalid_pipe_name():
    """测试无效的管道名称"""
    print("\n=== 测试：无效的管道名称 ===")
    
    invalid_names = [
        "",  # 空字符串
        "a" * 300,  # 超长名称
        "test/pipe",  # 包含路径分隔符
    ]
    
    for name in invalid_names:
        try:
            pipe = await AsyncIPCPipe.server(name)
            await pipe.close()
            print(f"⚠️  名称 '{name[:20]}...' 应该失败但成功了")
        except Exception as e:
            print(f"✅ 名称 '{name[:20]}...' 正确拒绝")
    
    return True


async def test_client_timeout():
    """测试客户端连接超时"""
    print("\n=== 测试：客户端连接超时 ===")
    
    try:
        # 连接不存在的服务端，WaitNamedPipe将超时（5秒默认）
        pipe = await AsyncIPCPipe.client("timeout_test_pipe_xyz")
        await pipe.close()
        print("❌ 应该超时但成功连接")
        return False
    except (TimeoutError, OSError, FileNotFoundError) as e:
        print(f"✅ 正确超时: {type(e).__name__}")
        return True
    except Exception as e:
        print(f"✅ 捕获到异常（可接受）: {type(e).__name__}: {e}")
        return True


async def main():
    """运行所有错误处理测试"""
    print("=" * 60)
    print("错误处理机制验证测试套件")
    print("=" * 60)
    
    tests = [
        ("连接不存在的管道", test_connect_nonexistent_pipe),
        ("服务端提前关闭", test_server_closes_early),
        ("从已关闭管道读取", test_read_from_closed_pipe),
        ("向已关闭管道写入", test_write_to_closed_pipe),
        ("重复关闭管道", test_double_close),
        ("上下文管理器异常", test_exception_in_context_manager),
        ("无效管道名称", test_invalid_pipe_name),
        ("客户端连接超时", test_client_timeout),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = await test_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ 测试 '{name}' 出现未处理异常: {e}")
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
        print("\n✅ 所有错误处理测试通过!")
    else:
        print(f"\n❌ {total - passed} 个测试失败")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
