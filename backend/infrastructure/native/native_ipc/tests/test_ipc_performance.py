# -*- coding: utf-8 -*-
"""
native_ipc 性能测试

测试异步IPC管道的性能指标：
- 吞吐量（MB/s）
- 延迟（ms）
- 并发能力
- 内存占用
"""

import asyncio
import os
import time
import platform
import pytest

# 仅Windows平台运行测试
pytestmark = pytest.mark.skipif(
    platform.system() != "Windows",
    reason="IPC tests only run on Windows"
)


class TestThroughput:
    """吞吐量测试"""

    @pytest.mark.asyncio
    async def test_single_pipe_throughput(self):
        """测试单管道吞吐量"""
        from backend.infrastructure.native.native_ipc import AsyncIPCPipe

        pipe_name = "test_throughput"

        # 传输10MB数据
        chunk_size = 4096
        num_chunks = 2560  # 10MB / 4KB
        test_chunk = b"X" * chunk_size

        total_bytes = 0
        start_time = 0.0

        async def server_task():
            nonlocal total_bytes
            async with AsyncIPCPipe.server(pipe_name) as pipe:
                await asyncio.sleep(0.1)

                for _ in range(num_chunks):
                    data = await pipe.read(chunk_size)
                    total_bytes += len(data)

        async def client_task():
            nonlocal start_time
            await asyncio.sleep(0.2)

            async with AsyncIPCPipe.client(pipe_name) as pipe:
                start_time = time.time()

                for _ in range(num_chunks):
                    await pipe.write(test_chunk)

        await asyncio.gather(server_task(), client_task())

        elapsed = time.time() - start_time
        throughput_mbps = (total_bytes / (1024 * 1024)) / elapsed

        print(f"\n单管道吞吐量: {throughput_mbps:.2f} MB/s")
        print(f"传输数据: {total_bytes / (1024 * 1024):.2f} MB")
        print(f"耗时: {elapsed:.3f} 秒")

        min_throughput = float(os.getenv("IPC_THROUGHPUT_MIN_MBPS", "80"))

        # 预期吞吐量具有一定下限，保守默认80 MB/s，可通过环境变量调整
        assert throughput_mbps > min_throughput, (
            f"Throughput too low: {throughput_mbps:.2f} MB/s "
            f"(expected > {min_throughput:.2f} MB/s)"
        )

    @pytest.mark.asyncio
    async def test_multi_pipe_throughput(self):
        """测试多管道并发吞吐量"""
        from backend.infrastructure.native.native_ipc import AsyncIPCPipe

        num_pipes = 5
        chunk_size = 4096
        num_chunks = 256  # 1MB per pipe
        test_chunk = b"X" * chunk_size

        total_bytes = 0
        start_time = 0.0

        async def server_task(pipe_id):
            nonlocal total_bytes
            pipe_name = f"test_multi_throughput_{pipe_id}"

            async with AsyncIPCPipe.server(pipe_name) as pipe:
                await asyncio.sleep(0.1)

                for _ in range(num_chunks):
                    data = await pipe.read(chunk_size)
                    total_bytes += len(data)

        async def client_task(pipe_id):
            await asyncio.sleep(0.2)

            pipe_name = f"test_multi_throughput_{pipe_id}"
            async with AsyncIPCPipe.client(pipe_name) as pipe:
                for _ in range(num_chunks):
                    await pipe.write(test_chunk)

        start_time = time.time()

        server_tasks = [server_task(i) for i in range(num_pipes)]
        client_tasks = [client_task(i) for i in range(num_pipes)]

        await asyncio.gather(*server_tasks, *client_tasks)

        elapsed = time.time() - start_time
        throughput_mbps = (total_bytes / (1024 * 1024)) / elapsed

        print(f"\n多管道并发吞吐量: {throughput_mbps:.2f} MB/s")
        print(f"管道数量: {num_pipes}")
        print(f"总传输数据: {total_bytes / (1024 * 1024):.2f} MB")
        print(f"耗时: {elapsed:.3f} 秒")

        min_multi_throughput = float(os.getenv("IPC_MULTIPIPE_THROUGHPUT_MIN_MBPS", "15"))

        # 多管道并发应该有更高的总吞吐量，默认阈值保守，可通过环境变量调整
        assert throughput_mbps > min_multi_throughput, (
            f"Multi-pipe throughput too low: {throughput_mbps:.2f} MB/s "
            f"(expected > {min_multi_throughput:.2f} MB/s)"
        )


class TestLatency:
    """延迟测试"""

    @pytest.mark.asyncio
    async def test_small_message_latency(self):
        """测试小消息延迟（往返时间RTT）"""
        from backend.infrastructure.native.native_ipc import AsyncIPCPipe

        pipe_name = "test_latency"
        num_rounds = 100
        small_message = b"test"

        latencies = []

        async def server_task():
            async with AsyncIPCPipe.server(pipe_name) as pipe:
                await asyncio.sleep(0.1)

                for _ in range(num_rounds):
                    # 接收请求
                    request = await pipe.read()
                    # 立即发送响应
                    await pipe.write(request)

        async def client_task():
            await asyncio.sleep(0.2)

            async with AsyncIPCPipe.client(pipe_name) as pipe:
                for _ in range(num_rounds):
                    # 记录发送时间
                    start = time.time()

                    # 发送请求
                    await pipe.write(small_message)
                    # 接收响应
                    response = await pipe.read()

                    # 计算往返时间
                    rtt = (time.time() - start) * 1000  # 转换为毫秒
                    latencies.append(rtt)

        await asyncio.gather(server_task(), client_task())

        avg_latency = sum(latencies) / len(latencies)
        min_latency = min(latencies)
        max_latency = max(latencies)

        print(f"\n小消息延迟统计 ({num_rounds} 次往返):")
        print(f"平均延迟: {avg_latency:.3f} ms")
        print(f"最小延迟: {min_latency:.3f} ms")
        print(f"最大延迟: {max_latency:.3f} ms")

        # 预期平均延迟 < 10ms
        assert avg_latency < 10, f"Average latency too high: {avg_latency:.3f} ms"


class TestConcurrency:
    """并发能力测试"""

    @pytest.mark.asyncio
    async def test_100_concurrent_pipes(self):
        """测试100个并发管道通信"""
        from backend.infrastructure.native.native_ipc import AsyncIPCPipe

        num_pipes = 100
        test_data = b"concurrent_test"

        success_count = 0

        async def server_task(pipe_id):
            nonlocal success_count
            pipe_name = f"test_concurrent_{pipe_id}"

            try:
                async with AsyncIPCPipe.server(pipe_name) as pipe:
                    await asyncio.sleep(0.1)

                    data = await pipe.read()
                    assert data == test_data

                    await pipe.write(b"ACK")
                    success_count += 1
            except Exception as e:
                print(f"Server {pipe_id} failed: {e}")

        async def client_task(pipe_id):
            await asyncio.sleep(0.2)

            pipe_name = f"test_concurrent_{pipe_id}"
            try:
                async with AsyncIPCPipe.client(pipe_name) as pipe:
                    await pipe.write(test_data)

                    response = await pipe.read()
                    assert response == b"ACK"
            except Exception as e:
                print(f"Client {pipe_id} failed: {e}")

        start_time = time.time()

        server_tasks = [server_task(i) for i in range(num_pipes)]
        client_tasks = [client_task(i) for i in range(num_pipes)]

        await asyncio.gather(*server_tasks, *client_tasks, return_exceptions=True)

        elapsed = time.time() - start_time

        print(f"\n并发测试结果:")
        print(f"管道数量: {num_pipes}")
        print(f"成功数量: {success_count}")
        print(f"总耗时: {elapsed:.3f} 秒")
        print(f"成功率: {success_count / num_pipes * 100:.1f}%")

        # 预期至少90%成功
        assert success_count >= num_pipes * 0.9, f"Success rate too low: {success_count}/{num_pipes}"


class TestStability:
    """稳定性测试"""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_continuous_operation(self):
        """测试连续操作（运行100轮）"""
        from backend.infrastructure.native.native_ipc import AsyncIPCPipe

        pipe_name = "test_stability"
        num_rounds = 100

        async def server_task():
            async with AsyncIPCPipe.server(pipe_name) as pipe:
                await asyncio.sleep(0.1)

                for i in range(num_rounds):
                    data = await pipe.read()
                    await pipe.write(f"response_{i}".encode())

        async def client_task():
            await asyncio.sleep(0.2)

            async with AsyncIPCPipe.client(pipe_name) as pipe:
                for i in range(num_rounds):
                    await pipe.write(f"request_{i}".encode())
                    response = await pipe.read()
                    assert response == f"response_{i}".encode()

        start_time = time.time()
        await asyncio.gather(server_task(), client_task())
        elapsed = time.time() - start_time

        print(f"\n稳定性测试结果:")
        print(f"操作轮数: {num_rounds}")
        print(f"总耗时: {elapsed:.3f} 秒")
        print(f"平均每轮: {elapsed / num_rounds * 1000:.3f} ms")

        # 测试成功即表示稳定性良好


class TestPerformanceReport:
    """生成性能报告"""

    @pytest.mark.asyncio
    async def test_generate_performance_report(self):
        """生成综合性能报告"""
        from backend.infrastructure.native.native_ipc import AsyncIPCPipe
        import json

        report = {
            "platform": platform.system(),
            "python_version": platform.python_version(),
            "tests": {}
        }

        # 吞吐量测试
        pipe_name = "test_report_throughput"
        chunk_size = 4096
        num_chunks = 1000
        test_chunk = b"X" * chunk_size

        async def server_throughput():
            async with AsyncIPCPipe.server(pipe_name) as pipe:
                await asyncio.sleep(0.1)
                for _ in range(num_chunks):
                    await pipe.read(chunk_size)

        async def client_throughput():
            await asyncio.sleep(0.2)
            async with AsyncIPCPipe.client(pipe_name) as pipe:
                start = time.time()
                for _ in range(num_chunks):
                    await pipe.write(test_chunk)
                return time.time() - start

        elapsed = await asyncio.gather(server_throughput(), client_throughput())
        throughput = (num_chunks * chunk_size / (1024 * 1024)) / elapsed[1]

        report["tests"]["throughput"] = {
            "value": round(throughput, 2),
            "unit": "MB/s",
            "data_size": f"{num_chunks * chunk_size / (1024 * 1024):.2f} MB"
        }

        # 延迟测试
        pipe_name = "test_report_latency"
        num_pings = 50

        async def server_latency():
            async with AsyncIPCPipe.server(pipe_name) as pipe:
                await asyncio.sleep(0.1)
                for _ in range(num_pings):
                    data = await pipe.read()
                    await pipe.write(data)

        async def client_latency():
            await asyncio.sleep(0.2)
            latencies = []
            async with AsyncIPCPipe.client(pipe_name) as pipe:
                for _ in range(num_pings):
                    start = time.time()
                    await pipe.write(b"ping")
                    await pipe.read()
                    latencies.append((time.time() - start) * 1000)
            return latencies

        latencies = await asyncio.gather(server_latency(), client_latency())
        avg_latency = sum(latencies[1]) / len(latencies[1])

        report["tests"]["latency"] = {
            "average": round(avg_latency, 3),
            "min": round(min(latencies[1]), 3),
            "max": round(max(latencies[1]), 3),
            "unit": "ms"
        }

        # 打印报告
        print("\n" + "=" * 60)
        print("性能测试报告")
        print("=" * 60)
        print(json.dumps(report, indent=2))
        print("=" * 60)

        # 保存报告
        report_path = "native_ipc_performance_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2)

        print(f"\n报告已保存到: {report_path}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
