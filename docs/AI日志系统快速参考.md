# AI日志系统快速参考

## 📝 日志级别速查

| 级别 | 图标 | 用途 | Terminal | AI文件 | 示例 |
|------|------|------|---------|--------|------|
| **DEBUG** | 🔍 | 调试信息 | ❌ | ✅ | `logger.debug("变量值: count=%d", count)` |
| **INFO** | ℹ️ | 流程信息 | ❌* | ✅ | `logger.info("开始处理数据")` |
| **WARNING** | ⚠️ | 警告信息 | ✅ | ✅ | `logger.warning("连接超时，重试中")` |
| **ERROR** | ❌ | 错误信息 | ✅ | ✅ | `logger.error("处理失败: %s", error)` |
| **CRITICAL** | 🔥 | 严重错误 | ✅ | ✅ | `logger.critical("系统无法继续")` |

*注: INFO级别的STAGE_NODE和NOTIFICATION会输出到Terminal

---

## 🚀 快速使用

### 上下文管理器（推荐）

```python
from backend.infrastructure.system_vnpy.unified_log_system import ai_log_process
import logging

logger = logging.getLogger("backend.my_module")

with ai_log_process("my_feature", metadata={"version": "1.0"}):
    logger.debug("调试信息")   # 只写AI文件
    logger.info("流程信息")    # 只写AI文件
    logger.warning("警告")     # Terminal + AI文件
    logger.error("错误")       # Terminal + AI文件
```

### 手动控制

```python
from backend.infrastructure.system_vnpy.unified_log_system import (
    start_ai_process,
    end_ai_process,
)

log_file = start_ai_process("my_feature", metadata={"version": "1.0"})
# ... 业务逻辑 ...
end_ai_process(success=True, summary="完成处理")
```

### 装饰器

```python
from backend.infrastructure.system_vnpy.unified_log_system import (
    ai_log_process_decorator,
)

@ai_log_process_decorator(process_name="my_feature")
def my_function():
    logger = logging.getLogger("backend.my_module")
    logger.info("函数执行")
```

---

## 📁 文件格式预览

### 文件头
```
================================================================================
AI助手专用日志文件 - my_feature
================================================================================
流程名称: my_feature
开始时间: 2025-10-28 15:25:09
文件路径: logs/ai/my_feature_20251028_152509.log
日志级别: DEBUG及以上所有级别
```

### 日志条目
```
🔍 [时间] [DEBUG   ] [logger名称                             ] [函数:行号]
    调试信息

ℹ️ [时间] [INFO    ] [logger名称                             ] [函数:行号]
    流程信息

────────────────────────────────────────────────────────────────────────────────
⚠️ [时间] [WARNING ] [logger名称                             ] [函数:行号]
    警告信息
────────────────────────────────────────────────────────────────────────────────
```

### 文件尾
```
================================================================================
流程结束 - my_feature
================================================================================
结束时间: 2025-10-28 15:27:45
执行结果: 成功

日志统计:
  - 总日志条数: 150
  - DEBUG: 50 条
  - INFO: 80 条
  - WARNING: 15 条
  - ERROR: 5 条
  - CRITICAL: 0 条
================================================================================
```

---

## 🎯 最佳实践

### ✅ 好的做法

```python
# 1. 使用backend开头的logger名称
logger = logging.getLogger("backend.my_module")

# 2. 提供充分的上下文
logger.error("下载失败: 品种=%s, 错误=%s", symbol, error)

# 3. 使用logger.exception记录异常
try:
    process_data()
except Exception:
    logger.exception("处理失败")

# 4. 使用元数据传递业务参数
with ai_log_process("download", metadata={"count": 1000}):
    # ...
```

### ❌ 避免的做法

```python
# 1. 不使用backend开头（DEBUG日志会被过滤）
logger = logging.getLogger("test.module")

# 2. 信息不足
logger.error("失败")

# 3. 不记录异常堆栈
except Exception as e:
    logger.error("失败: %s", e)

# 4. 日志级别不当
logger.info("变量值: count=%d", count)  # 应该用DEBUG
```

---

## 🔧 预定义流程名称

```python
from backend.infrastructure.system_vnpy.unified_log_system import ProcessNames

ProcessNames.STARTUP           # 系统启动
ProcessNames.SHUTDOWN          # 系统关闭
ProcessNames.SYMBOL_REFRESH    # 品种列表刷新
ProcessNames.DOWNLOAD_KLINE    # K线下载
ProcessNames.QUALITY_SCAN      # 质量扫描
ProcessNames.STRATEGY_BACKTEST # 策略回测
# ... 更多常量
```

---

## 📊 统计信息

查看AI日志Handler统计:

```python
from backend.infrastructure.system_vnpy.unified_log_system import get_ai_log_handler

ai_handler = get_ai_log_handler()
stats = ai_handler.get_statistics()

print(stats)
# {
#     'process_count': 5,
#     'total_logs': 2567,
#     'level_counts': {
#         'DEBUG': 1234,
#         'INFO': 1000,
#         'WARNING': 320,
#         'ERROR': 10,
#         'CRITICAL': 3
#     },
#     'current_process': 'download_klines',
#     'current_file': 'logs/ai/download_klines_20251028_152509.log'
# }
```

---

## 🐛 常见问题

### Q: AI日志文件为空？
A: 检查是否正确初始化AILogFileHandler并设置到LoggingHub

### Q: DEBUG日志未记录？
A: 确保logger名称以`backend`或`ui`开头

### Q: 统计信息不准确？
A: 确保流程正常结束（使用上下文管理器或手动调用end_process）

---

## 📄 文档链接

- 完整使用指南: [docs/AI日志系统使用指南.md](./AI日志系统使用指南.md)
- 优化报告: [AI日志系统优化报告.md](../AI日志系统优化报告.md)
- 日志系统v5.0文档: [backend/infrastructure/system_vnpy/日志系统完整文档v5.0.md](../backend/infrastructure/system_vnpy/日志系统完整文档v5.0.md)
