# -*- coding: utf-8 -*-
"""
IOCP 使用示例
演示如何在 Python 中使用 IOCP (完成端口) 进行高性能异步 I/O
"""
import asyncio
import platform
import sys
from pathlib import Path

# 添加项目路径
project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))


async def example_network_io():
    """示例1: 异步网络 I/O（自动使用 IOCP，Windows ProactorEventLoop）"""
    print("=" * 60)
    print("示例1: 异步网络 I/O")
    print("=" * 60)

    try:
        # 异步网络连接（自动使用 IOCP on Windows）
        reader, writer = await asyncio.open_connection('example.com', 80)

        # 发送 HTTP 请求
        request = b'GET / HTTP/1.0\r\nHost: example.com\r\n\r\n'
        writer.write(request)
        await writer.drain()

        # 接收响应
        response = await reader.read(1024)
        print(f"✅ 收到响应（前100字节）: {response[:100].decode('utf-8', errors='ignore')}")

        writer.close()
        await writer.wait_closed()
        print("✅ 网络 I/O 完成")

    except Exception as e:
        print(f"❌ 网络 I/O 失败: {e}")


async def example_file_io():
    """示例2: 异步文件 I/O（使用 aiofiles，自动使用 IOCP）"""
    print("\n" + "=" * 60)
    print("示例2: 异步文件 I/O")
    print("=" * 60)

    try:
        import aiofiles

        # 写入文件
        async with aiofiles.open('test_iocp.txt', 'w', encoding='utf-8') as f:
            await f.write('Hello, IOCP!\n这是使用 IOCP 的异步文件 I/O 示例。\n')
        print("✅ 文件写入完成")

        # 读取文件
        async with aiofiles.open('test_iocp.txt', 'r', encoding='utf-8') as f:
            content = await f.read()
        print(f"✅ 文件读取完成:\n{content}")

        # 清理
        Path('test_iocp.txt').unlink(missing_ok=True)
        print("✅ 临时文件已清理")

    except ImportError:
        print("⚠️  aiofiles 未安装，请运行: pip install aiofiles")
    except Exception as e:
        print(f"❌ 文件 I/O 失败: {e}")


async def example_concurrent_io():
    """示例3: 并发异步 I/O（展示 IOCP 的并发优势）"""
    print("\n" + "=" * 60)
    print("示例3: 并发异步 I/O")
    print("=" * 60)

    async def fetch_url(url, port=80):
        """获取单个 URL"""
        try:
            reader, writer = await asyncio.open_connection(url, port, timeout=5)
            request = f'GET / HTTP/1.0\r\nHost: {url}\r\n\r\n'.encode()
            writer.write(request)
            await writer.drain()
            response = await reader.read(512)
            writer.close()
            await writer.wait_closed()
            return f"{url}: ✅ 成功 ({len(response)} 字节)"
        except Exception as e:
            return f"{url}: ❌ 失败 ({e})"

    # 并发请求多个服务器
    urls = ['example.com', 'httpbin.org', 'www.baidu.com']
    print(f"并发请求 {len(urls)} 个服务器...")

    import time
    start_time = time.time()

    # 使用 asyncio.gather 并发执行
    results = await asyncio.gather(*[fetch_url(url) for url in urls])

    elapsed = (time.time() - start_time) * 1000

    print("\n结果:")
    for result in results:
        print(f"  {result}")

    print(f"\n✅ 并发 I/O 完成，耗时: {elapsed:.0f}ms")
    print("💡 IOCP 的优势：多个请求并发执行，不需要多线程")


def check_event_loop_type():
    """检查当前使用的事件循环类型"""
    print("\n" + "=" * 60)
    print("事件循环信息")
    print("=" * 60)

    try:
        loop = asyncio.get_event_loop()
        loop_type = type(loop).__name__
        policy = asyncio.get_event_loop_policy()
        policy_type = type(policy).__name__

        print(f"当前事件循环: {loop_type}")
        print(f"当前事件循环策略: {policy_type}")

        if platform.system() == "Windows":
            if "Proactor" in loop_type:
                print("✅ 使用 ProactorEventLoop (基于 IOCP)")
                print("   → 这是 Windows 上性能最优的选择")
            elif "Selector" in loop_type:
                print("ℹ️  使用 SelectorEventLoop")
                print("   → 兼容性更好，但性能略低于 IOCP")
                print("   → 通常用于需要 ZMQ 的场景")
        else:
            print("ℹ️  非 Windows 平台，使用 epoll/select")

    except Exception as e:
        print(f"❌ 获取事件循环信息失败: {e}")


async def main():
    """主函数"""
    print("\n" + "=" * 70)
    print("IOCP (完成端口) 使用示例")
    print("=" * 70)
    print(f"平台: {platform.system()} {platform.release()}")
    print(f"Python: {sys.version.split()[0]}")

    # 检查事件循环类型
    check_event_loop_type()

    # 运行示例（注意：示例需要网络连接）
    try:
        # 示例1: 网络 I/O
        await example_network_io()
    except Exception as e:
        print(f"⚠️  示例1跳过（需要网络连接）: {e}")

    # 示例2: 文件 I/O
    await example_file_io()

    # 示例3: 并发 I/O（需要网络连接）
    try:
        await example_concurrent_io()
    except Exception as e:
        print(f"⚠️  示例3跳过（需要网络连接）: {e}")

    print("\n" + "=" * 70)
    print("示例完成")
    print("=" * 70)


if __name__ == "__main__":
    # Windows 上可以尝试使用 ProactorEventLoop（如果不使用 ZMQ）
    if platform.system() == "Windows":
        try:
            # 检查是否在使用 ZMQ
            import zmq
            print("ℹ️  检测到 pyzmq，保持 SelectorEventLoop（ZMQ 需要）")
        except ImportError:
            # 不使用 ZMQ，可以使用 ProactorEventLoop（更高性能）
            print("ℹ️  未检测到 pyzmq，可以使用 ProactorEventLoop（IOCP）")
            print("💡 要启用 IOCP，取消下面这行的注释：")
            print("   # asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())")

    # 运行示例
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n❌ 用户中断")
    except Exception as e:
        print(f"\n\n❌ 运行失败: {e}")
        import traceback
        traceback.print_exc()

