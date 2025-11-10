# -*- coding: utf-8 -*-

# backend.core ↔ backend.startup 解耦迁移说明

## 背景

- 历史上，`backend.core.base` 暴露了 VNPY 引擎、服务初始化器和大量全局 getter/setter。
- 启动流程（`backend.startup`）与后端服务层长期依赖这些全局单例，导致循环导入和状态不一致风险。
- 本次迁移按照 **单一事实原则**（Single Source of Truth）重构依赖，约束引擎与服务的来源，并保留必要的兼容桥接。

## 变更总览

| 项目 | 变更说明 |
| --- | --- |
| `backend.core.__init__` | ✅ 缩减导出范围，默认仅暴露核心模型/配置；VNPY 相关符号改为需显式从 `backend.core.vnpy_imports` 引入。 |
| `backend.core.base` | ✅ `__getattr__` 新增迁移提示，对服务初始化 & VNPY 依赖发出 `DeprecationWarning`。 |
| `backend.startup.context` | ✅ 仅在上下文内维护 `event_engine`、`main_engine`、`china_stock_engine`，不再写入全局 getter。 |
| `service_initializer` & 各启动 stage | ✅ 全量改为从 `StartupContext` 读取/设置依赖，兼容模式仅在缺省时创建引擎。 |
| 服务层迁移 | ✅ 所有业务服务（SystemManagerService、StrategyCenterService、TradingGatewayService、DataCenterService、PortfolioService、MarketBoardService）已迁移，支持通过构造函数注入 StartupContext 或 RuntimeLocator 获取依赖。 |

## 已完成迁移的服务模块

### 核心服务
- `SystemManagerService` - 已修改构造函数和内部调用
- `StrategyCenterService` - 已修改构造函数和内部调用
- `TradingGatewayService` - 已修改构造函数和内部调用

### 数据服务
- `DataCenterService` - 已修改构造函数和部分内部调用
- `MarketBoardService` - 已修改构造函数和内部调用

### 业务服务
- `PortfolioService` - 已修改构造函数和内部调用

### 启动模块
- `StartupContext` - 已移除对全局 getter 的依赖
- `ServiceInitializer` - 已改为从 context 获取依赖
- `backend_init.py` - 已移除全局引擎设置
- `qt_framework.py` - 已移除全局引擎设置
- `startup_coordinator.py` - 已改为使用 RuntimeLocator

## 推荐使用方式

1. **创建启动上下文**
   ```python
   from backend.startup.context import StartupContext
   context = StartupContext()
   ```
2. **初始化服务**
   ```python
   from backend.startup.initializers.service_initializer import ServiceInitializer
   initializer = ServiceInitializer(
       service_manager=context.service_manager,
       context=context,
   )
   initializer.initialize_all_services()
   ```
3. **访问依赖**
   ```python
   service_manager = context.service_manager
   service_registry = context.service_registry
   data_center = service_registry.resolve_optional("data_center_service")
   ```
4. **关闭服务**
   ```python
   initializer.shutdown_services()
   ```

## 兼容策略

- `backend.core.base.get_*` / `set_*` / `ServiceInitializer` 等函数仍保留，但调用时会触发 `DeprecationWarning`。
- `RuntimeLocator` 继续兜底旧代码路径，优先返回 `StartupContext` 中的实例。
- 旧版文档示例已更新，如需迁移，可对照 `backend/README.md` 与 `backend/startup/README.md` 中的最新示例。

## 迁移建议

1. **入口应用 / CLI**
   - 调整为创建 `StartupContext` 并显式传递给依赖模块。
2. **服务实现**
   - 构造函数支持 `context` 参数，优先从上下文/注册表读取依赖。
3. **自定义脚本**
   - 避免直接调用 `backend.core.base` 的全局 getter，若无法立即迁移，可接受警告并计划后续重构。

## 迁移完成总结

### 达成目标
1. ✅ **消除循环导入风险** - 通过依赖注入模式，启动模块不再直接依赖 `backend.core.base` 的全局函数
2. ✅ **实现单一事实原则** - VNPY 引擎现在只保存在 `StartupContext` 中，避免状态不一致
3. ✅ **保持向后兼容** - 旧代码仍可运行，但会收到 `DeprecationWarning` 提示
4. ✅ **缩小核心包导出面** - `backend.core` 现在只导出核心功能，VNPY 相关导入需显式指定

### 兼容策略验证
- `RuntimeLocator` 作为兜底机制，确保在没有 `StartupContext` 时仍能获取依赖
- `backend.core.base.__getattr__` 提供迁移提示，帮助团队逐步更新代码
- 所有服务模块都支持通过构造函数注入上下文的模式

## 回归验证建议

- 运行 `pytest tests/test_startup.py`（或自定义启动脚本）验证引擎初始化与服务注册是否成功。
- 手动启动 UI/后端流程，观察 `logs/application_startup_*.log` 中的阶段日志与 `DeprecationWarning`。
- 验证所有服务模块仍能正常获取所需依赖（通过 context 或 RuntimeLocator）。

## 后续维护建议

1. **新代码编写** - 优先使用 `StartupContext` 模式，避免直接调用全局 getter
2. **旧代码迁移** - 逐步将现有代码改为依赖注入模式，消除 `DeprecationWarning`
3. **文档更新** - 确保所有示例代码都遵循新的使用方式

---

**迁移状态**: ✅ 已完成
**验证状态**: ⏳ 待验证
如需进一步支持，请联系架构组或提交 issue。***

