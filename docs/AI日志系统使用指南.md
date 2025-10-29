# AI日志系统使用指南

**版本**: v5.1  
**更新日期**: 2025-10-28  
**状态**: ✅ 生产就绪

---

## 📖 概述

本系统提供了**Terminal简洁、AI详细**的双轨日志输出：

- **Terminal输出**: 简化95.3%，只显示关键节点（阶段、通知、告警、错误）
- **AI日志文件**: 完整详细，包含所有DEBUG/INFO/WARNING/ERROR/CRITICAL日志
- **自动分类**: 智能路由，自动选择合适的输出渠道
- **视觉增强**: 图标、分隔线、统计，快速定位问题

---

## 🚀 快速开始

### 1. 基础使用（上下文管理器）

```python
import logging
from backend.infrastructure.system_vnpy.unified_log_system import ai_log_process

# 创建logger
logger = logging.getLogger("backend.my_module")

# 使用AI日志流程
with ai_log_process("download_klines", metadata={"symbols": 1000}):
    logger.debug("开始初始化下载器")  # 只写AI日志文件
    logger.info("连接服务器成功")     # 只写AI日志文件
    logger.warning("网络延迟较高")    # Terminal + AI日志文件
    logger.error("下载失败，重试中")  # Terminal + AI日志文件 + 数据库
```

**输出效果**:

- **Terminal**: 只显示WARNING和ERROR
- **AI日志文件**: 完整记录所有4条日志，包含DEBUG

### 2. 手动控制（适合长时间流程）

```python
from backend.infrastructure.system_vnpy.unified_log_system import (
    start_ai_process,
    end_ai_process,
)

# 开始流程
log_file_path = start_ai_process(
    "quality_scan",
    metadata={"total_symbols": 5000, "scan_type": "full"}
)

logger.info(f"AI日志文件: {log_file_path}")

try:
    # 执行业务逻辑
    logger.debug("加载品种列表")
    logger.info("开始扫描数据质量")
    # ...
    
    # 成功结束
    end_ai_process(success=True, summary="扫描完成，发现10个问题")
except Exception as e:
    # 失败结束
    logger.exception("扫描失败")
    end_ai_process(success=False, summary=f"扫描异常: {e}")
```

### 3. 装饰器方式

```python
from backend.infrastructure.system_vnpy.unified_log_system import (
    ai_log_process_decorator,
)

@ai_log_process_decorator(
    process_name="backtest_strategy",
    metadata_func=lambda *args, **kwargs: {
        "strategy": args[0].name if args else "unknown",
        "start_date": kwargs.get("start_date"),
        "end_date": kwargs.get("end_date"),
    }
)
def run_backtest(strategy, start_date, end_date):
    logger = logging.getLogger("backend.strategy.backtest")
    
    logger.debug(f"策略参数: {strategy.params}")
    logger.info(f"回测周期: {start_date} ~ {end_date}")
    logger.info("回测完成")
    
    return backtest_result
```

---

## 📊 日志级别使用建议

### DEBUG 🔍

**用途**: 调试信息，帮助理解代码执行流程

**何时使用**:
- 变量值检查
- 函数调用追踪
- 条件分支判断
- 循环迭代详情

**示例**:
```python
logger.debug("变量值: count=%d, status=%s", count, status)
logger.debug("进入分支: mode=%s", mode)
logger.debug("循环第%d次，处理品种: %s", i, symbol)
```

**输出到**: AI日志文件（不输出到Terminal）

### INFO ℹ️

**用途**: 正常流程信息，记录关键步骤

**何时使用**:
- 流程开始/结束
- 任务状态更新
- 重要操作完成
- 配置加载

**示例**:
```python
logger.info("开始下载K线数据")
logger.info("已处理 %d/%d 个品种", processed, total)
logger.info("配置加载完成: %d 项配置", len(config))
```

**输出到**: AI日志文件（不输出到Terminal，除非是STAGE_NODE或NOTIFICATION类型）

### WARNING ⚠️

**用途**: 警告信息，可能存在的问题

**何时使用**:
- 非致命错误
- 重试操作
- 数据质量问题
- 配置不推荐

**示例**:
```python
logger.warning("连接超时，第%d次重试", retry_count)
logger.warning("数据缺失: 品种=%s, 日期=%s", symbol, date)
logger.warning("配置项缺失，使用默认值: %s", key)
```

**输出到**: Terminal + AI日志文件 + 数据库 + 事件

### ERROR ❌

**用途**: 错误信息，发生了错误但可恢复

**何时使用**:
- 操作失败
- 数据验证失败
- 网络错误
- 文件访问错误

**示例**:
```python
logger.error("下载失败: 品种=%s, 错误=%s", symbol, error)
logger.error("数据验证失败: %s", validation_error)
logger.error("网络请求失败: url=%s, status=%d", url, status_code)
```

**输出到**: Terminal + AI日志文件 + 数据库 + 事件 + UI状态栏

### CRITICAL 🔥

**用途**: 严重错误，系统可能无法继续

**何时使用**:
- 系统级错误
- 资源耗尽
- 致命异常
- 数据损坏

**示例**:
```python
logger.critical("数据库连接断开，系统即将关闭")
logger.critical("内存不足，无法继续执行")
logger.critical("配置文件损坏，系统无法启动")
```

**输出到**: Terminal + AI日志文件 + 数据库 + 事件 + UI弹窗

---

## 🎨 AI日志文件格式

### 文件头

```
================================================================================
AI助手专用日志文件 - download_klines
================================================================================
流程名称: download_klines
开始时间: 2025-10-28 15:25:09
文件路径: logs/ai/download_klines_20251028_152509.log
日志级别: DEBUG及以上所有级别
日志用途: AI助手分析、问题诊断、性能分析

说明：
  1. 本文件包含完整的DEBUG/INFO/WARNING/ERROR/CRITICAL日志
  2. Terminal输出经过简化，仅显示关键节点
  3. 本文件提供完整上下文，供AI助手深度分析
  4. 异常时包含完整堆栈信息
  5. 实时写入，确保崩溃时可追溯

流程元数据:
  - symbols: 1000

================================================================================
```

### 日志条目

```
🔍 [2025-10-28 15:25:09] [DEBUG   ] [backend.data_center.download            ] [download_klines:123]
    初始化TDX连接池，最大连接数: 10

ℹ️ [2025-10-28 15:25:09] [INFO    ] [backend.data_center.download            ] [download_klines:145]
    开始下载K线数据，品种数: 1000

────────────────────────────────────────────────────────────────────────────────
⚠️ [2025-10-28 15:25:10] [WARNING ] [backend.data_center.download            ] [download_klines:189]
    连接超时，第3次重试，剩余7次
────────────────────────────────────────────────────────────────────────────────

────────────────────────────────────────────────────────────────────────────────
❌ [2025-10-28 15:25:11] [ERROR   ] [backend.data_center.download            ] [download_klines:234]
    下载失败: 品种=600000, 原因=连接超时

异常堆栈跟踪:
Traceback (most recent call last):
  File "...", line 234, in download_klines
    result = await client.get_kline_data(symbol)
TimeoutError: Connection timeout after 30s
════════════════════════════════════════════════════════════════════════════════
────────────────────────────────────────────────────────────────────────────────
```

### 文件尾

```
================================================================================
流程结束 - download_klines
================================================================================
结束时间: 2025-10-28 15:27:45
执行结果: 成功

执行摘要:
下载完成，成功990个，失败10个

日志统计:
  - 总日志条数: 2567
  - DEBUG: 1234 条
  - INFO: 1000 条
  - WARNING: 320 条
  - ERROR: 10 条
  - CRITICAL: 3 条

================================================================================
```

---

## 🔍 AI助手分析技巧

### 1. 快速定位问题

**查找ERROR和CRITICAL**:
- 使用分隔线（────）快速滚动
- 关注红色图标（❌ 🔥）

### 2. 理解执行流程

**查看DEBUG和INFO**:
- DEBUG提供详细的变量值和条件分支
- INFO记录关键步骤和状态变化

### 3. 评估问题严重程度

**查看文件尾统计**:
```
日志统计:
  - ERROR: 10 条     ← 有10个错误
  - CRITICAL: 3 条   ← 有3个严重问题
```

### 4. 追踪异常原因

**查看异常堆栈**:
- 完整的堆栈跟踪
- 双重分隔线（════）标识

---

## 📁 预定义流程名称

使用 `ProcessNames` 类的预定义常量：

```python
from backend.infrastructure.system_vnpy.unified_log_system import (
    ProcessNames,
    ai_log_process,
)

with ai_log_process(ProcessNames.STARTUP):
    logger.info("系统启动")

with ai_log_process(ProcessNames.DOWNLOAD_KLINE, metadata={"count": 1000}):
    logger.info("下载K线")

with ai_log_process(ProcessNames.QUALITY_SCAN, metadata={"symbols": 5000}):
    logger.info("扫描数据质量")
```

**可用常量**:
- `ProcessNames.STARTUP` - 系统启动
- `ProcessNames.SHUTDOWN` - 系统关闭
- `ProcessNames.SYMBOL_REFRESH` - 品种列表刷新
- `ProcessNames.SYMBOL_LOAD` - 品种列表加载
- `ProcessNames.DOWNLOAD_KLINE` - K线下载
- `ProcessNames.DOWNLOAD_TICK` - Tick下载
- `ProcessNames.QUALITY_SCAN` - 质量扫描
- `ProcessNames.QUALITY_REPAIR` - 质量修复
- `ProcessNames.STRATEGY_BACKTEST` - 策略回测
- `ProcessNames.STRATEGY_OPTIMIZE` - 策略优化
- `ProcessNames.STRATEGY_DEPLOY` - 策略部署

---

## ⚙️ 配置说明

### 日志文件位置

默认位置: `logs/ai/`

自定义位置:
```python
from backend.infrastructure.system_vnpy.unified_log_system import AILogFileHandler

ai_handler = AILogFileHandler(base_dir="custom/path/to/logs")
```

### 日志级别过滤

**全局配置** (`config/rules_global.yaml`):
```yaml
SYSTEM:
  DEBUG: [file, ai_file]  # DEBUG只写文件和AI日志
  INFO: [file, ai_file]   # INFO只写文件和AI日志
  WARNING: [file, console, database, event, ai_file]  # WARNING输出到Terminal
```

**阶段配置** (`config/rules_stage.yaml`):
```yaml
stage_downloading:
  PROGRESS:
    INFO: [file, event_throttled, ai_file]  # 下载进度不输出Terminal
```

---

## 🐛 故障排查

### 问题1: AI日志文件为空

**原因**: AILogFileHandler未正确初始化

**解决**:
```python
from backend.infrastructure.system_vnpy.unified_log_system import (
    get_logging_hub,
    get_ai_log_handler,
)

hub = get_logging_hub()
ai_handler = get_ai_log_handler()
hub.set_ai_log_handler(ai_handler)  # ✅ 关键步骤
```

### 问题2: DEBUG日志未记录

**原因**: Logger名称不符合规范

**解决**:
```python
# ❌ 错误：不会记录DEBUG
logger = logging.getLogger("test.module")

# ✅ 正确：会记录DEBUG
logger = logging.getLogger("backend.test.module")
```

### 问题3: 文件尾统计不准确

**原因**: 流程未正常结束

**解决**:
```python
# ✅ 使用上下文管理器（推荐）
with ai_log_process("my_process"):
    # ... 业务逻辑 ...
    pass  # 自动调用end_process

# ⚠️ 手动控制（需要确保调用end_process）
start_ai_process("my_process")
try:
    # ... 业务逻辑 ...
    end_ai_process(success=True)
except:
    end_ai_process(success=False)  # ✅ 确保调用
```

---

## 📚 最佳实践

### 1. 合理使用日志级别

```python
# ✅ 好的做法
logger.debug("变量值: count=%d", count)  # 调试信息
logger.info("开始处理数据")             # 流程信息
logger.warning("连接超时，重试中")       # 警告
logger.error("处理失败: %s", error)      # 错误

# ❌ 不好的做法
logger.info("变量值: count=%d", count)   # 应该用DEBUG
logger.warning("开始处理数据")           # 应该用INFO
```

### 2. 提供充分的上下文

```python
# ✅ 好的做法
logger.error("下载失败: 品种=%s, 日期=%s, 错误=%s", symbol, date, error)

# ❌ 不好的做法
logger.error("下载失败")  # 缺少关键信息
```

### 3. 使用元数据传递业务参数

```python
# ✅ 好的做法
with ai_log_process(
    "download_klines",
    metadata={
        "total_symbols": 1000,
        "start_date": "2024-01-01",
        "end_date": "2024-12-31",
    }
):
    # ... 业务逻辑 ...
```

### 4. 记录异常堆栈

```python
# ✅ 好的做法
try:
    process_data()
except Exception as e:
    logger.exception("数据处理失败")  # 自动记录堆栈

# ❌ 不好的做法
try:
    process_data()
except Exception as e:
    logger.error("数据处理失败: %s", e)  # 没有堆栈信息
```

---

## 🎓 总结

### 核心优势

1. **Terminal简洁**: 95.3%的日志减少，用户体验极佳
2. **AI详细**: 100%的日志保留，AI分析无障碍
3. **智能路由**: 自动选择合适的输出渠道
4. **视觉增强**: 图标、分隔线、统计，快速定位问题

### 适用场景

- ✅ 所有需要AI助手参与的流程
- ✅ 复杂的多步骤业务逻辑
- ✅ 需要详细调试信息的功能
- ✅ 高频操作（下载、扫描等）

### 不适用场景

- ❌ 一次性简单操作（使用普通logger即可）
- ❌ 性能敏感的热路径（避免过多日志）

---

**文档版本**: v5.1  
**最后更新**: 2025-10-28  
**维护者**: 系统团队
