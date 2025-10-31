# native_ipc 快速入门

## 5分钟上手指南

### 1. 编译 C 扩展

```bash
# 进入目录
cd backend/infrastructure/native_ipc

# 编译（需要 Visual Studio Build Tools）
python setup.py build_ext --inplace
```

### 2. 验证安装

```python
from backend.infrastructure.native_ipc import IPC_AVAILABLE

if IPC_AVAILABLE:
    print("✅ IPC 扩展已成功加载")
else:
    print("❌ IPC 扩展未加载，请检查编译")
```

### 3. 第一个示例：Hello World

创建文件 `hello_ipc.py`：

```python
import asyncio
from backend.infrastructure.native_ipc import AsyncIPCPipe

async def server():
    async with AsyncIPCPipe.server("hello_pipe") as pipe:
        print("服务端：等待客户端...")
        await asyncio.sleep(0.1)
        
        # 接收消息
        message = await pipe.read()
        print(f"服务端收到: {message.decode()}")
        
        # 发送响应
        await pipe.write(b"Hello from server!")

async def client():
    await asyncio.sleep(0.2)  # 等待服务端准备好
    
    async with AsyncIPCPipe.client("hello_pipe") as pipe:
        # 发送消息
        await pipe.write(b"Hello from client!")
        
        # 接收响应
        response = await pipe.read()
        print(f"客户端收到: {response.decode()}")

async def main():
    await asyncio.gather(server(), client())

if __name__ == "__main__":
    asyncio.run(main())
```

运行：
```bash
python hello_ipc.py
```

### 4. 常见使用模式

#### 模式1：请求-响应

```python
async def request_response():
    async with AsyncIPCPipe.server("rpc_service") as pipe:
        await asyncio.sleep(0.1)
        request = await pipe.read()
        # 处理请求
        result = process(request)
        await pipe.write(result)
```

#### 模式2：双向流式通信

```python
async def streaming():
    async with AsyncIPCPipe.server("stream_pipe") as pipe:
        await asyncio.sleep(0.1)
        
        for i in range(10):
            # 接收数据
            data = await pipe.read()
            # 处理并返回
            result = transform(data)
            await pipe.write(result)
```

#### 模式3：并发处理多个连接

```python
async def multi_client_server():
    async def handle_client(client_id):
        pipe_name = f"service_{client_id}"
        async with AsyncIPCPipe.server(pipe_name) as pipe:
            await asyncio.sleep(0.1)
            data = await pipe.read()
            await pipe.write(b"Processed")
    
    # 启动多个服务端
    tasks = [handle_client(i) for i in range(10)]
    await asyncio.gather(*tasks)
```

### 5. 性能优化建议

#### 大数据传输

```python
# 指定足够的读取缓冲区大小
data = await pipe.read(1024 * 1024)  # 1MB
```

#### 批量操作

```python
# 一次性发送多个数据块
chunks = [b"data1", b"data2", b"data3"]
for chunk in chunks:
    await pipe.write(chunk)
```

### 6. 错误处理

```python
async def safe_communication():
    try:
        async with AsyncIPCPipe.client("service") as pipe:
            await pipe.write(b"request")
            response = await pipe.read()
    except ConnectionError as e:
        print(f"连接失败: {e}")
    except TimeoutError as e:
        print(f"超时: {e}")
    except Exception as e:
        print(f"其他错误: {e}")
```

### 7. 调试技巧

#### 启用详细日志

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

#### 检查管道状态

```python
pipe = AsyncIPCPipe("test_pipe", role="server")
print(f"管道状态: {pipe}")
# 输出: <AsyncIPCPipe: test_pipe role=server status=not opened>
```

### 8. 下一步

- 📖 阅读 [README.md](README.md) 了解完整功能
- 💻 查看 [example_usage.py](example_usage.py) 的完整示例
- 🧪 运行测试：`pytest tests/test_ipc_basic.py -v`
- 📊 性能测试：`pytest tests/test_ipc_performance.py -v`

### 9. 常见问题

**Q: 编译失败怎么办？**

A: 确保已安装 Visual Studio Build Tools 和 Windows SDK。

**Q: 客户端连接超时？**

A: 确保服务端先启动，或增加客户端等待时间。

**Q: 如何实现跨进程通信？**

A: 将服务端和客户端代码分别运行在不同的 Python 进程中。

**Q: 性能如何？**

A: 预期单管道吞吐量 > 100 MB/s，延迟 < 10ms。

### 10. 获取帮助

- 📝 查看设计文档：[设计文档](../../.qoder/quests/cross-process-coroutine-communication-package.md)
- 🔍 查看实现总结：[IMPLEMENTATION_SUMMARY.md](IMPLEMENTATION_SUMMARY.md)
- 📧 提交问题：创建 Issue

---

**开始使用 native_ipc，享受真正的异步跨进程通信！** 🚀
