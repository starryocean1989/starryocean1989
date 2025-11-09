# -*- coding: utf-8 -*-
# native_load_balancer 扩展

高频负载均衡配置计算在 Python 层存在多次浮点缩放、整数约束和分支判断，1 秒刷新频率下会阻塞资源采集线程。本模块将核心计算下沉至 C 扩展，实现 <1ms 的配置出结果。

## 功能

- `optimize(...) -> dict`：根据资源瓶颈、队列压力、服务器约束和任务规模返回最优 `processes` 与 `coroutines_per_process`。
- `LOAD_BALANCER_AVAILABLE`：扩展是否可用，用于调用方降级。

## 编译

```powershell
cd backend/infrastructure/native/native_load_balancer
python setup.py build_ext --inplace
```

或运行 `backend/infrastructure/native/compile_all.bat`。

## 日志集成

已集成 NativeLogBridge，支持负载均衡优化过程的结构化日志记录：

- **C 层**：优化计算启动、参数解析异常等关键事件。
- **Python 层**：使用 `@native_call_guard` 装饰器捕获包装层异常，回退实现提供基础日志。


