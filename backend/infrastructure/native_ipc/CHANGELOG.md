# 变更日志

本文档记录 native_ipc 的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2025-11-01

### 新增

#### C 扩展层
- ✨ 实现 `IPCAsyncPipe` C 对象
- ✨ 支持命名管道创建（服务端）
- ✨ 支持命名管道连接（客户端）
- ✨ 异步读写操作（`read_async`, `write_async`）
- ✨ IOCP 完成端口集成
- ✨ Windows 事件对象管理
- ✨ 完成状态检查（`check_completion`）

#### Python API 层
- ✨ 实现 `AsyncIPCPipe` 类
- ✨ 工厂方法（`server()`, `client()`）
- ✨ 异步读写方法（`read()`, `write()`）
- ✨ 上下文管理器支持（`async with`）
- ✨ 简化 API（`aopen_server()`, `aopen_client()`）
- ✨ 完整的错误处理机制

#### 事件循环集成层
- ✨ 实现 `IPCCompletionHandler`
- ✨ 实现 `IPCEventLoopExtension`
- ✨ 事件对象等待机制（优化轮询）
- ✨ asyncio 深度集成
- ✨ 全局单例模式（`get_loop_extension()`）

#### 文档和示例
- 📝 完整的 README 文档
- 📝 快速入门指南（QUICKSTART.md）
- 📝 实现总结（IMPLEMENTATION_SUMMARY.md）
- 💻 5个完整使用示例
- 💻 基础功能示例（hello world）
- 💻 双向通信示例
- 💻 大数据传输示例
- 💻 并发通信示例
- 💻 简化 API 示例

#### 测试
- 🧪 基础功能测试套件（test_ipc_basic.py）
  - 服务端-客户端通信测试
  - 大数据传输测试
  - 双向通信测试
  - 上下文管理器测试
  - 并发通信测试
  - 错误处理测试
- 🧪 性能测试套件（test_ipc_performance.py）
  - 吞吐量测试（单管道、多管道）
  - 延迟测试（RTT）
  - 并发能力测试（100个管道）
  - 稳定性测试（连续操作）
  - 性能报告生成

#### 工具和配置
- 🔧 C 扩展编译配置（setup.py）
- 🔧 模块导出配置（__init__.py）
- 🔧 平台检测和自动降级

### 技术特性

- ⚡ 真正的异步 I/O（基于 Windows IOCP）
- ⚡ 无线程池开销
- ⚡ 高性能（预期吞吐量 > 100 MB/s）
- ⚡ 低延迟（预期 < 10ms）
- 🏗️ 完全对标 native_iocp 架构
- 🏗️ 三层架构设计
- 🏗️ 清晰的 API 风格
- 🔒 完整的资源管理（上下文管理器）
- 🔒 异常安全保证

### 已知限制

- ⚠️ 仅支持 Windows 平台
- ⚠️ 单服务端对应单客户端连接
- ⚠️ 字节流模式（暂不支持消息模式）
- ⚠️ 需要编译 C 扩展

### 架构对比

| 组件 | native_iocp | native_ipc | 状态 |
|------|-------------|------------|------|
| C 对象 | IOCPFile | IPCAsyncPipe | ✅ 对标 |
| Python 类 | AsyncIOCPFile | AsyncIPCPipe | ✅ 对标 |
| 事件循环扩展 | IOCPEventLoopExtension | IPCEventLoopExtension | ✅ 对标 |
| 核心方法 | read/write/close | read/write/close | ✅ 一致 |
| 简化 API | aopen | aopen_server/client | ✅ 对标 |

### 性能指标

预期性能指标（待实际测试验证）：

- 吞吐量：> 100 MB/s（单管道）
- 延迟：< 10ms（小消息）
- 并发：支持 100+ 并发管道
- 内存：< 10MB（100个管道）

### 代码统计

- C 代码：622 行（ipc_async.c）
- Python 代码：1,053 行
  - async_ipc.py: 350 行
  - ipc_loop.py: 328 行
  - __init__.py: 73 行
  - setup.py: 80 行
  - 示例代码: 236 行
- 测试代码：680 行
  - test_ipc_basic.py: 305 行
  - test_ipc_performance.py: 375 行
- 文档：约 900 行

**总计**：约 3,300 行（含注释和文档）

## [未来计划]

### 1.1.0（计划中）

#### 功能增强
- [ ] 多客户端连接支持
- [ ] 消息模式支持（PIPE_TYPE_MESSAGE）
- [ ] 连接超时配置
- [ ] 自动重连机制
- [ ] 更详细的错误信息

#### 性能优化
- [ ] 深度集成 ProactorEventLoop
- [ ] 减少数据拷贝
- [ ] 内存池管理
- [ ] 批量操作优化

#### 安全性
- [ ] ACL 权限控制
- [ ] 数据加密传输
- [ ] 身份验证机制

### 1.2.0（计划中）

#### 上层模式
- [ ] REQ/REP 模式实现
- [ ] PUB/SUB 模式实现
- [ ] ROUTER/DEALER 模式实现
- [ ] RPC 框架封装
- [ ] 消息序列化支持（JSON, Protobuf）

### 2.0.0（长期计划）

#### 跨平台支持
- [ ] Linux 支持（Unix Domain Socket + io_uring）
- [ ] macOS 支持（Unix Domain Socket + kqueue）
- [ ] 统一的跨平台 API

#### 高级功能
- [ ] 服务发现机制
- [ ] 负载均衡
- [ ] 故障转移
- [ ] 监控和指标收集

## 贡献者

- Terminal Project Team

## 许可证

MIT License
