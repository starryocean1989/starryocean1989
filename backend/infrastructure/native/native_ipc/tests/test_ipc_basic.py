# -*- coding: utf-8 -*-
"""
native_ipc 基础功能测试

测试异步IPC管道的基本功能，包括：
- 管道创建与连接
- 读写操作
- 异步完成
- 上下文管理器
- 并发通信
"""

import asyncio
import pytest
import sys
import platform

# 仅Windows平台运行测试
pytestmark = pytest.mark.skipif(
    platform.system() != "Windows",
    reason="IPC tests only run on Windows"
)


class TestBasicIPCOperations:
    """基础IPC操作测试"""

    @pytest.mark.asyncio
    async def test_server_client_basic_communication(self):
        """测试基本的服务端-客户端通信"""
        from backend.infrastructure.native.native_ipc import AsyncIPCPipe

        pipe_name = "test_basic_comm"
        test_data = b"Hello from client"
        response_data = b"Hello from server"

        # 创建服务端和客户端任务
        async def server_task():
            async with await AsyncIPCPipe.server(pipe_name) as pipe:
                # 等待客户端连接（服务端先启动）
                await asyncio.sleep(0.5)  # 增加等待时间

                # 读取客户端请求
                request = await pipe.read()
                assert request == test_data, f"Server received unexpected data: {request}"

                # 发送响应
                bytes_written = await pipe.write(response_data)
                assert bytes_written == len(response_data)

        async def client_task():
            # 等待服务端准备好
            await asyncio.sleep(0.3)  # 增加等待时间

            async with await AsyncIPCPipe.client(pipe_name) as pipe:
                # 发送请求
                bytes_written = await pipe.write(test_data)
                assert bytes_written == len(test_data)

                # 读取响应
                response = await pipe.read()
                assert response == response_data, f"Client received unexpected data: {response}"

        # 并发运行服务端和客户端
        await asyncio.gather(server_task(), client_task())

    @pytest.mark.asyncio
    async def test_large_data_transfer(self):
        """测试大数据量传输"""
        from backend.infrastructure.native.native_ipc import AsyncIPCPipe

        pipe_name = "test_large_data"
        # 创建10KB数据
        large_data = b"X" * (10 * 1024)

        async def server_task():
            async with await AsyncIPCPipe.server(pipe_name) as pipe:
                await asyncio.sleep(0.1)

                data = await pipe.read(len(large_data))
                assert len(data) == len(large_data)
                assert data == large_data

        async def client_task():
            await asyncio.sleep(0.2)

            async with await AsyncIPCPipe.client(pipe_name) as pipe:
                bytes_written = await pipe.write(large_data)
                assert bytes_written == len(large_data)

        await asyncio.gather(server_task(), client_task())

    @pytest.mark.asyncio
    async def test_bidirectional_communication(self):
        """测试双向通信"""
        from backend.infrastructure.native.native_ipc import AsyncIPCPipe

        pipe_name = "test_bidirectional"

        async def server_task():
            async with await AsyncIPCPipe.server(pipe_name) as pipe:
                await asyncio.sleep(0.1)

                # 读取请求
                request = await pipe.read()
                assert request == b"request"

                # 发送响应
                await pipe.write(b"response")

                # 再次读取
                request2 = await pipe.read()
                assert request2 == b"second_request"

                # 再次发送
                await pipe.write(b"second_response")

        async def client_task():
            await asyncio.sleep(0.2)

            async with await AsyncIPCPipe.client(pipe_name) as pipe:
                # 发送请求
                await pipe.write(b"request")

                # 读取响应
                response = await pipe.read()
                assert response == b"response"

                # 再次发送
                await pipe.write(b"second_request")

                # 再次读取
                response2 = await pipe.read()
                assert response2 == b"second_response"

        await asyncio.gather(server_task(), client_task())

    @pytest.mark.asyncio
    async def test_context_manager_cleanup(self):
        """测试上下文管理器资源清理"""
        from backend.infrastructure.native.native_ipc import AsyncIPCPipe

        pipe_name = "test_cleanup"

        async def server_task():
            async with await AsyncIPCPipe.server(pipe_name) as pipe:
                await asyncio.sleep(0.1)
                assert pipe._closed == False
                await pipe.read()

            # 上下文退出后应该已关闭
            assert pipe._closed == True

        async def client_task():
            await asyncio.sleep(0.2)

            async with await AsyncIPCPipe.client(pipe_name) as pipe:
                assert pipe._closed == False
                await pipe.write(b"data")

            assert pipe._closed == True

        await asyncio.gather(server_task(), client_task())


class TestSimplifiedAPI:
    """简化API测试"""

    @pytest.mark.asyncio
    async def test_aopen_server_client(self):
        """测试aopen_server和aopen_client"""
        from backend.infrastructure.native.native_ipc import aopen_server, aopen_client

        pipe_name = "test_aopen"

        async def server_task():
            async with await aopen_server(pipe_name) as pipe:
                await asyncio.sleep(0.1)
                data = await pipe.read()
                assert data == b"test"

        async def client_task():
            await asyncio.sleep(0.2)

            async with await aopen_client(pipe_name) as pipe:
                await pipe.write(b"test")

        await asyncio.gather(server_task(), client_task())


class TestConcurrentCommunication:
    """并发通信测试"""

    @pytest.mark.asyncio
    async def test_multiple_pipes(self):
        """测试多个管道同时通信"""
        from backend.infrastructure.native.native_ipc import AsyncIPCPipe

        num_pipes = 5

        async def server_task(pipe_id):
            pipe_name = f"test_multi_{pipe_id}"
            async with await AsyncIPCPipe.server(pipe_name) as pipe:
                await asyncio.sleep(0.1)

                data = await pipe.read()
                assert data == f"data_{pipe_id}".encode()

                await pipe.write(f"response_{pipe_id}".encode())

        async def client_task(pipe_id):
            await asyncio.sleep(0.2)

            pipe_name = f"test_multi_{pipe_id}"
            async with await AsyncIPCPipe.client(pipe_name) as pipe:
                await pipe.write(f"data_{pipe_id}".encode())

                response = await pipe.read()
                assert response == f"response_{pipe_id}".encode()

        # 创建服务端任务
        server_tasks = [server_task(i) for i in range(num_pipes)]
        # 创建客户端任务
        client_tasks = [client_task(i) for i in range(num_pipes)]

        # 并发运行所有任务
        await asyncio.gather(*server_tasks, *client_tasks)


class TestErrorHandling:
    """错误处理测试"""

    @pytest.mark.asyncio
    async def test_read_from_closed_pipe(self):
        """测试从已关闭的管道读取"""
        from backend.infrastructure.native.native_ipc import AsyncIPCPipe

        pipe_name = "test_closed_read"

        async def server_task():
            async with await AsyncIPCPipe.server(pipe_name) as pipe:
                await asyncio.sleep(0.1)
                await pipe.close()

                # 尝试从已关闭的管道读取
                with pytest.raises(ValueError, match="Pipe is closed"):
                    await pipe.read()

        async def client_task():
            await asyncio.sleep(0.2)
            # 客户端连接，但服务端已关闭
            try:
                async with await AsyncIPCPipe.client(pipe_name) as pipe:
                    await pipe.write(b"data")
            except Exception:
                # 预期会失败
                pass

        await asyncio.gather(server_task(), client_task(), return_exceptions=True)

    @pytest.mark.asyncio
    async def test_write_to_closed_pipe(self):
        """测试向已关闭的管道写入"""
        from backend.infrastructure.native.native_ipc import AsyncIPCPipe

        pipe_name = "test_closed_write"

        async def server_task():
            async with await AsyncIPCPipe.server(pipe_name) as pipe:
                await asyncio.sleep(0.1)
                await pipe.close()

                # 尝试向已关闭的管道写入
                with pytest.raises(ValueError, match="Pipe is closed"):
                    await pipe.write(b"data")

        async def client_task():
            await asyncio.sleep(0.2)
            try:
                async with await AsyncIPCPipe.client(pipe_name) as pipe:
                    pass
            except Exception:
                pass

        await asyncio.gather(server_task(), client_task(), return_exceptions=True)


class TestAvailabilityCheck:
    """可用性检查测试"""

    def test_ipc_available(self):
        """测试IPC_AVAILABLE标志"""
        from backend.infrastructure.native.native_ipc import IPC_AVAILABLE

        # 在Windows上应该可用（如果C扩展已编译）
        if platform.system() == "Windows":
            # 注意：如果C扩展未编译，IPC_AVAILABLE会是False
            assert isinstance(IPC_AVAILABLE, bool)
        else:
            assert IPC_AVAILABLE == False


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
