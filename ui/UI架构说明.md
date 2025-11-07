# -*- coding: utf-8 -*-
# UI架构说明文档

> 星辰金融终端 - 前端界面层完整架构说明

## 📂 UI文件夹整体结构

```
ui/
├── __init__.py                    # UI层统一导出（MainWindow, ThemeManager）
│
├── main_window.py                 # 主窗口：应用程序的主界面框架（包含 ShortcutManager）
│                                    # 注意：startup_coordinator 已迁移到 backend/startup/ui_startup/
│
├── core/                          # 核心功能模块（已精简）
│   ├── __init__.py
│   └── boot_orchestrator.py       # 启动编排器：管理分层启动就绪状态
│                                    # 注意：shortcut_manager 和 async_utils 已合并到各自使用者文件
│
├── components/                    # 可复用UI组件库
│   ├── __init__.py
│   ├── README.md                  # 组件库详细文档
│   ├── widgets.py                 # 基础组件集合
│   ├── theme_system.py            # 主题系统（DashboardTheme + ThemeManager）
│   ├── enhanced_statusbar.py      # 增强状态栏组件
│   ├── basic_monitors.py          # 基础监控组件（订单/成交/持仓/账户）
│   ├── charts.py                  # 图表组件集合
│   ├── task_queue_monitor.py      # 任务队列监控组件
│   ├── resource_limit_config.py   # 资源限制配置组件
│   ├── themes.json                # 主题配置文件
│   ├── theme_preference.json      # 用户主题偏好
│   ├── modern_dark_style.qss      # 暗色主题样式表
│   └── modern_light_style.qss     # 亮色主题样式表
│
└── modules/                       # 六大功能模块视图
    ├── __init__.py
    ├── data_center_view.py        # 数据中心界面
    ├── market_board_view.py       # 行情看板界面
    ├── trading_gateway_view.py    # 交易网关界面
    ├── portfolio_view.py          # 组合投资界面
    ├── strategy_center_view.py    # 策略中心界面
    └── system_manager_view.py     # 系统管理界面
```

---

## 📋 文件详细说明

### 1. 核心文件

#### 1.1 `__init__.py`
**作用**：UI层统一导出接口
- 导出 `MainWindow`（主窗口类）
- 导出 `ThemeManager`（主题管理器）
- 为外部提供简洁的导入路径

```python
from .main_window import MainWindow
from .components.theme_system import ThemeManager

__all__ = ["MainWindow", "ThemeManager"]
```

---

#### 1.2 `main_window.py`
**作用**：星辰金融终端的主窗口框架
**功能**：
- 应用程序的顶层窗口，管理整个UI布局
- 左侧：功能模块导航列表（6个模块）
- 右侧：QStackedWidget堆叠式视图容器
- 底部：增强状态栏（显示实时状态、告警、资源监控）
- 顶部菜单栏：文件、编辑、视图、工具、帮助等
- 管理主题切换、窗口状态保存/恢复
- 监听后端事件，实时更新UI状态

**关键类**：
- `MainWindow(QMainWindow)` - 主窗口类

**技术细节**：
- 使用PySide6.QtWidgets框架
- 集成EventEngine事件系统监听后端事件
- 支持QSplitter可调节布局
- 内存占用优化（延迟加载、弱引用）

---

#### 1.3 `startup_coordinator.py` ⚠️ 已迁移
**状态**：已迁移到 `backend/startup/ui_startup/startup_coordinator.py`  
**原因**：启动协调器属于后端启动流程的一部分，已整合到后端启动模块  
**位置**：`backend/startup/ui_startup/startup_coordinator.py`

**架构更新（v0.50 三进程）**：
- UI 进程只负责 UI + 业务服务骨架，真实数据服务与监控服务分别运行在数据进程、监控进程。
- `StartupCoordinator` 不再直接驱动六阶段初始化，而是作为 UI 侧的观测者，连接 `StartupOrchestrator` 的阶段信号、Terminal 输出与启动画面。
- 三大 Worker (`DataLauncherWorker`、`MonitorLauncherWorker`、`BackendInitializerWorker`) 由 `BackendInitStage` 管理，`StartupCoordinator` 负责：
  - 监听 `startup.stage` 日志，将 Stage 3 的分支 A/B/C 进度转换为 UI 文案；
  - 根据 `BackendInitStage` 结果触发 UI 预加载与主窗口展示；
  - 捕获 `MultiProcessLogCollector` Level 0/1/2 事件，在启动画面实时呈现数据/监控进程状态；
  - 在异常情况下回放 `application_startup_*.log` 的关键信息，提示用户查看详细日志。

**三进程职责概览**：
- UI 进程：`StartupCoordinator` + `MainWindow`，渲染界面、注册服务代理、订阅事件。
- 数据进程：`data_process_main.py`，执行数据下载、质量扫描、RPC 请求处理，并通过 `data_process_ready.signal` 反馈状态。
- 监控进程：`monitor_system.py`，负责系统/硬件监控，向 UI 进程推送 `ALERT`/`NOTIFICATION` 事件。
- 跨进程通信：统一通过 `native_ipc` + `LOGGING_QUEUE_TOKEN`，日志路由回主进程的 `LoggingHub`。

**关键类**：
- `BackendInitializerWorker(QObject)` - UI 线程内的占位 Worker，现仅在需要时用于回放业务服务初始化日志；
  - 信号：`progress_updated` / `initialization_completed` / `error_occurred`
  - 方法：`run()` - 兼容模式下仍可串行执行旧版六阶段流程（测试环境使用）
- `StartupCoordinator` - Splash 层控制器，负责：
  - `start()`：订阅 `StartupOrchestrator` 事件，显示启动画面；
  - `handle_stage_update()`：解析 Stage 3 分支日志（PID、IPC、Level 2）并更新 UI；
  - `on_startup_completed()`：通知 `MainWindow` 初始化功能模块，关闭 Splash；
  - `on_startup_failed()`：展示错误对话框并附带日志路径。

> ✅ **提示**：Terminal 的 Stage 3 输出与启动画面完全一致。Terminal 仅展示 `STAGE_NODE` / `WARNING+`，详细 DEBUG 日志保存在 `logs/application_startup_YYYYMMDD_HHMMSS.log`，`StartupCoordinator` 的“查看详版日志”按钮即指向该文件。

---

### 2. 核心功能模块（core/）

#### 2.1 `boot_orchestrator.py`
**作用**：启动编排器 - 前端就绪协议与分层启动管理
**功能**：
- 统一管理就绪阶段标记（config_ready, backend_ready, ui_ready, ui_visible）
- 允许模块订阅某些就绪点后再执行回调（on_ready）
- 查询就绪状态（is_ready）
- 线程安全，可跨线程标记

**关键类**：
- `BootOrchestrator` - 启动编排器类

**核心方法**：
- `mark_ready(flag: str)` - 标记某个就绪点达到
- `is_ready(flag: str) -> bool` - 查询就绪状态
- `on_ready(flag: str, callback)` - 订阅就绪点回调

**设计特点**：
- 轻量级纯Python，不依赖Qt对象
- 支持异步回调机制
- 幂等性设计（重复标记不会重复触发）

---

#### 2.2 `shortcut_manager.py` ⚠️ 已迁移
**状态**：已合并到 `ui/main_window.py`
**原因**：该模块仅被 `MainWindow` 使用，为减少模块间依赖，已合并到主窗口文件
**位置**：`ui/main_window.py` 中的 `ShortcutManager` 类

**原始功能**：
- 快捷键注册和管理
- 快捷键冲突检测
- 快捷键配置持久化（保存到JSON）
- 支持动态修改快捷键

**关键类**：
- `ShortcutManager(QObject, LoggerMixin)` - 快捷键管理器

**默认快捷键分类**：
- **文件操作**：Ctrl+N（新建）、Ctrl+S（保存）、Ctrl+W（关闭）
- **编辑操作**：Ctrl+Z（撤销）、Ctrl+C（复制）、Ctrl+V（粘贴）
- **导航操作**：Ctrl+G（跳转行）、Ctrl+P（跳转文件）
- **视图操作**：F11（全屏）、Ctrl+Tab（切换标签）
- **运行调试**：F5（运行）、F9（断点）、F10（单步）
- **终端操作**：Ctrl+`（打开终端）

**核心方法**：
- `register_shortcut(action_id, key_sequence, callback)` - 注册快捷键
- `unregister_shortcut(action_id)` - 注销快捷键
- `get_shortcut(action_id)` - 获取快捷键
- `save_shortcuts()` / `load_shortcuts()` - 持久化

---

### 3. 可复用组件库（components/）

#### 3.1 `widgets.py`
**作用**：基础UI组件集合
**包含组件**：

**1️⃣ 基础框架**：
- `ErrorCategory` - 错误分类枚举
- `ErrorSeverity` - 错误严重程度枚举
- `BaseWidget` - 所有自定义Widget的基类

**2️⃣ Dashboard组件**：
- `MetricCard` - 大数字指标卡片（带趋势图）
- `MiniSparkline` - 迷你趋势折线图
- `GaugeWidget` - 半圆仪表盘（显示百分比进度）
- `StatusIndicator` - 状态指示器（成功/警告/错误）
- `CompactTable` - 紧凑型表格

**3️⃣ Monaco编辑器**：
- `LineNumberArea` - 行号显示区域
- `PythonHighlighter` - Python语法高亮器
- `MonacoEditorWidget` - Monaco风格代码编辑器（基于QPlainTextEdit + Pygments）

**特性**：
- 零外部依赖（无需WebEngine）
- 统一使用DashboardTheme主题配置
- 高性能渲染和实时更新

---

#### 3.2 `theme_system.py`
**作用**：统一主题系统
**包含类**：

**1️⃣ DashboardTheme（静态配置类）**：
- 提供统一的色板、字体规格、样式生成器
- 颜色分类：背景色、主题色、文本色、状态色、指标类型色、边框色
- 样式生成方法：
  - `get_card_style()` - 卡片样式
  - `get_metric_value_style()` - 指标数值样式
  - `get_button_style()` - 按钮样式
  - `get_compact_table_style()` - 表格样式
  - `get_progress_bar_style()` - 进度条样式

**2️⃣ ThemeManager（动态管理类）**：
- 应用主题到QApplication
- 主题切换（dark/light）
- 主题配置持久化（theme_preference.json）
- 加载QSS样式表

**核心方法**：
- `apply_theme(app)` - 应用主题
- `switch_theme(theme_name, app)` - 切换主题
- `get_color(key, default)` - 获取主题颜色
- `load_theme_preference()` / `save_theme_preference()` - 持久化

---

#### 3.3 `enhanced_statusbar.py`
**作用**：增强状态栏组件
**功能模块**：

**左侧区域**：
- 当前操作状态消息（临时消息自动清除）

**中间区域**：
- 后台任务指示器（显示正在运行的任务数量）
- 点击可打开任务详情对话框

**中间-右区域**：
- 告警汇总按钮（显示未读告警数量）
- 点击可打开告警列表对话框

**右侧区域**：
- 系统资源监控（CPU/内存使用率，需要psutil）
- 实时更新（1秒刷新间隔）

**关键类**：
- `BackgroundTaskIndicator` - 后台任务指示器
- `AlertButton` - 告警汇总按钮
- `TaskDetailDialog` - 任务详情对话框
- `AlertListDialog` - 告警列表对话框

**事件监听**：
- `EVENT_LOG_PROGRESS` - 进度更新
- `EVENT_LOG_ALERT` - 告警推送
- `EVENT_UI_STATUSBAR` - 状态栏消息

---

#### 3.4 `basic_monitors.py`
**作用**：基础交易监控组件集合（VnPy集成）
**包含组件**：

**1️⃣ OrderMonitor（订单监控）**：
- 显示所有委托订单
- 实时更新订单状态
- 支持撤单操作
- 支持CSV导出

**2️⃣ TradeMonitor（成交监控）**：
- 显示所有成交记录
- 实时更新成交数据
- 支持CSV导出

**3️⃣ PositionMonitor（持仓监控）**：
- 显示当前持仓
- 实时更新持仓盈亏
- 支持平仓操作
- 支持CSV导出

**4️⃣ AccountMonitor（账户监控）**：
- 显示账户资金信息
- 实时更新账户余额、可用资金、持仓市值
- 盈亏统计

**技术实现**：
- 基于vnpy.event.EventEngine事件驱动
- 监听VnPy标准事件（EVENT_ORDER, EVENT_TRADE, EVENT_POSITION, EVENT_ACCOUNT）
- 自动数据更新和缓存管理

---

#### 3.5 `charts.py`
**作用**：专业图表组件集合
**包含组件**：

**1️⃣ ChartWidget（金融图表）**：
- 基于pyqtgraph的高性能K线图
- 支持蜡烛图、折线图、柱状图
- 支持多指标叠加（均线、MACD、RSI等）
- 支持十字光标、缩放、平移

**2️⃣ ChartToolbar（图表工具栏）**：
- 时间周期切换（1min/5min/15min/60min/1day）
- 图表类型切换（蜡烛图/折线图）
- 指标添加/删除
- 截图导出

**3️⃣ SubplotIndicatorManager（副图指标管理器）**：
- 管理副图指标（MACD、KDJ、RSI等）
- 支持多副图叠加
- 指标参数配置

**4️⃣ IndicatorPlotWidget（指标副图组件）**：
- 在主图下方显示指标副图
- 自动同步X轴缩放和平移
- 支持多条指标曲线

**技术特性**：
- 使用pyqtgraph实现高性能渲染
- 异步数据加载（后台线程）
- VnPy数据适配器集成

---

#### 3.6 `task_queue_monitor.py`
**作用**：任务队列监控组件
**功能**：
- 显示任务队列的实时状态
- 队列长度监控
- 任务吞吐量统计
- 平均等待时间计算
- 优先级分布可视化

**关键类**：
- `TaskQueueMonitorWidget` - 任务队列监控组件

**可视化**：
- MetricCard显示关键指标
- pyqtgraph实时曲线图

---

#### 3.7 `resource_limit_config.py`
**作用**：资源限制配置组件
**功能**：
- 配置小任务CPU/内存限制
- 配置大任务CPU/内存限制
- 配置任务超时阈值
- 配置资源监控间隔
- 实时预览当前系统资源

**关键类**：
- `ResourceLimitConfigWidget` - 资源限制配置组件

**UI元素**：
- QSlider滑块调节
- QSpinBox数值输入
- QCheckBox开关控制
- 实时资源占用显示（通过psutil）

---

#### 3.8 配置文件说明

**themes.json**：
- 主题配置文件（合并了dark/light主题）
- 定义颜色、字体、边框圆角等

**theme_preference.json**：
- 用户主题偏好配置
- 自动保存用户选择的主题

**modern_dark_style.qss / modern_light_style.qss**：
- Qt样式表（QSS）文件
- 定义详细的控件样式（按钮、输入框、表格等）

---

### 4. 六大功能模块视图（modules/）

#### 4.1 `data_center_view.py`
**模块名**：数据中心
**架构**：标准架构 - 4个子界面采用选项卡形式

**功能分类**：

**📊 Tab 1: 数据查询**
- 股票代码搜索（支持自动补全）
- K线数据查询（日线/分钟线）
- Tick数据查询
- 支持日期范围选择
- 数据导出（CSV/Excel）

**📥 Tab 2: 数据下载**
- 中国股票数据批量下载
- 支持多数据源选择（TDX/VnPy）
- 下载进度实时显示
- 下载任务管理（暂停/恢复/取消）

**🔍 Tab 3: 数据浏览**
- 数据表格展示
- 支持排序、筛选
- 支持图表可视化
- 支持数据统计分析

**⚙️ Tab 4: 数据管理**
- 数据库管理（清理/备份/恢复）
- 数据完整性检查
- 数据质量报告
- 存储空间监控

**关键类**：
- `DataCenter(BaseWidget, LoggerMixin)` - 数据中心主界面

**后端服务**：
- `DataCenterService` - 数据中心后端服务

**事件监听**：
- `EVENT_CHINASTOCK_DOWNLOAD` - 中国股票下载事件
- `EVENT_TICK` - Tick数据推送

---

#### 4.2 `market_board_view.py`
**模块名**：行情看板
**架构**：基于vnpy_chartwizard的专业图表应用

**功能特性**：

**📈 实时行情**：
- 多品种同时监控
- 实时数据自动订阅
- Tick转K线自动合成

**📊 图表功能**：
- 专业K线图（蜡烛图/折线图）
- 支持品种叠加对比
- 支持指标叠加（MA/MACD/KDJ/RSI/BOLL等）
- 支持对数坐标
- 支持多周期切换

**🎯 交互功能**：
- 十字光标
- 区间缩放
- 拖拽平移
- 截图导出

**关键类**：
- `MarketDashboard(BaseWidget, LoggerMixin)` - 行情看板主界面
- `ChartWizardEnhanced` - 增强版ChartWizard（集成vnpy_chartwizard）

**后端服务**：
- `MarketBoardService` - 行情看板后端服务

**技术集成**：
- 使用官方vnpy_chartwizard包
- 基于pyqtgraph高性能渲染
- 支持分钟线/日线/Tick级别数据

---

#### 4.3 `trading_gateway_view.py`
**模块名**：交易网关
**架构**：混合架构 - 网关管理器（固有组件）+ 2个子界面

**功能模块**：

**🌐 网关管理器**：
- 网关连接管理（连接/断开）
- 支持多网关类型：
  - CTP（国内期货、期权）
  - CTP Mini（迷你版）
  - SOPT（国内ETF期权）
  - TTS（期货仿真交易）
  - IB（海外证券、期货）
  - PaperAccount（本地模拟交易）
- 网关状态实时监控
- 账户信息显示

**📊 Tab 1: 交易监控**
- 订单监控（委托单）
- 成交监控（成交记录）
- 持仓监控（当前持仓）
- 账户监控（资金状态）
- 支持撤单、平仓操作

**🤖 Tab 2: 算法交易**
- 算法策略列表
- 策略参数配置
- 策略启动/停止
- 策略运行状态监控

**关键类**：
- `TradingGateway(BaseWidget, LoggerMixin)` - 交易网关主界面

**后端服务**：
- `TradingGatewayService` - 交易网关后端服务

**支持的网关**：
- vnpy_ctp
- vnpy_mini
- vnpy_sopt
- vnpy_tts
- vnpy_ib
- vnpy_paperaccount

---

#### 4.4 `portfolio_view.py`
**模块名**：组合投资
**架构**：混合架构 - 两个固有业务组件

**功能模块**：

**📈 组合管理**：
- 自动组合管理（智能配置）
- 自定义组合管理（手动配置）
- 组合创建/编辑/删除
- 组合持仓查看
- 组合收益分析

**📊 组合监控**：
- 组合实时盈亏
- 组合净值曲线
- 组合持仓分布
- 组合风险指标（夏普比率、最大回撤等）
- 组合归因分析

**📑 标签页**：
- Tab 1: 自动组合管理
- Tab 2: 自定义组合管理
- Tab 3: 组合监控大盘

**关键类**：
- `PortfolioInvestment(BaseWidget, LoggerMixin)` - 组合投资主界面

**后端服务**：
- `PortfolioService` - 组合投资后端服务

**可视化**：
- pyqtgraph实时曲线图
- QTableWidget持仓表格

---

#### 4.5 `strategy_center_view.py`
**模块名**：策略中心
**架构**：现代IDE风格

**布局结构**：

**🗂️ 左侧 - 文件管理器**：
- 策略文件树形列表
- 支持右键菜单（新建/删除/重命名）
- 支持拖拽移动
- 支持文件搜索
- 策略模板分类：
  - CTA策略（趋势跟踪）
  - 算法交易策略（TWAP/VWAP）
  - 组合策略
  - 期权策略
  - 价差策略
  - 脚本交易

**📝 中央 - 多标签编辑器**：
- 支持多文件同时编辑
- Monaco风格代码编辑器
- Python语法高亮
- 行号显示
- 自动补全
- 代码格式化

**🤖 右侧 - AI助手（可隐藏）**：
- AI代码建议
- 策略审核
- 错误诊断
- 智能补全

**⚙️ 底部 - 工具面板（可折叠）**：
- **回测面板**：策略回测配置和结果展示
- **终端**：Python交互式终端
- **调试控制台**：策略运行日志

**关键类**：
- `StrategyCenter(BaseWidget, LoggerMixin)` - 策略中心主界面

**后端服务**：
- `StrategyCenterService` - 策略中心后端服务
- `AIAssistantService` - AI助手服务

**核心功能**：
- 策略编写和编辑
- 策略回测
- 策略实盘运行
- 策略性能分析
- 策略参数优化

---

#### 4.6 `system_manager_view.py`
**模块名**：系统管理
**架构**：标准架构 - 8个子界面采用选项卡形式

**功能分类**：

**🖥️ Tab 1: 系统监控**
- CPU使用率监控
- 内存使用率监控
- 磁盘IO监控
- 网络流量监控
- 温度监控（如支持）
- 实时曲线图和仪表盘

**📋 Tab 2: 日志查询**
- 多级别日志查询（DEBUG/INFO/WARNING/ERROR/CRITICAL）
- 日志时间范围筛选
- 日志模块筛选
- 日志内容搜索
- 日志导出（CSV）
- 支持日志回放

**⚙️ Tab 3: 配置管理**
- 系统配置编辑
- 配置导入/导出
- 配置备份/恢复
- 配置版本管理

**📂 Tab 4: 数据库管理**
- 数据库备份
- 数据库恢复
- 数据库清理
- 数据库优化
- SQL查询工具

**🌐 Tab 5: 网络管理**
- 网络连接监控
- 代理配置
- 防火墙设置
- 端口监听

**🔔 Tab 6: 告警管理**
- 告警规则配置
- 告警历史查询
- 告警统计分析
- 告警通知设置

**🔧 Tab 7: 任务管理**
- 定时任务配置
- 任务执行历史
- 任务队列监控
- 资源限制配置

**📊 Tab 8: 性能诊断**
- 性能瓶颈分析
- 慢查询分析
- 内存泄漏检测
- 线程死锁检测

**关键类**：
- `SystemManager(BaseWidget, LoggerMixin)` - 系统管理主界面

**后端服务**：
- `SystemManagerService` - 系统管理后端服务

**可视化组件**：
- MetricCard（指标卡片）
- GaugeWidget（仪表盘）
- pyqtgraph曲线图
- QTableWidget数据表格

---

## 🏗️ 架构设计原则

### 1. 分层架构

```
┌─────────────────────────────────────────┐
│         UI Layer (ui/)                  │
│  ┌─────────────┐  ┌──────────────────┐ │
│  │ Main Window │  │  6 Module Views  │ │
│  └─────────────┘  └──────────────────┘ │
└─────────────────────────────────────────┘
                    ↕
┌─────────────────────────────────────────┐
│      Backend Layer (backend/)           │
│  ┌──────────────────────────────────┐  │
│  │   6 Service Classes              │  │
│  └──────────────────────────────────┘  │
└─────────────────────────────────────────┘
                    ↕
┌─────────────────────────────────────────┐
│   Infrastructure (infrastructure/)      │
│  ┌─────────┐ ┌──────────┐ ┌──────────┐ │
│  │  VnPy   │ │   TDX    │ │  System  │ │
│  └─────────┘ └──────────┘ └──────────┘ │
└─────────────────────────────────────────┘
```

### 2. 事件驱动

所有UI组件通过EventEngine监听后端事件，实现松耦合。在三进程架构下，事件可以跨进程传递：

**UI进程内事件**：
```python
from vnpy.event import Event, EventEngine

# 注册事件监听
self.event_engine.register(EVENT_TICK, self.on_tick)

# 事件处理
def on_tick(self, event: Event):
    tick = event.data
    self.update_display(tick)
```

**跨进程事件**（通过native_ipc）：
- 数据进程 → UI进程：数据下载进度、质量扫描结果
- 监控进程 → UI进程：系统告警、资源监控数据

### 3. 服务注入

UI层不直接创建后端对象，而是通过ServiceManager获取服务：

```python
from backend.core.base import get_service_manager

service_manager = get_service_manager()
data_service = service_manager.get_service("data_center_service")
```

### 4. 主题统一

所有UI组件使用DashboardTheme统一主题配置，避免硬编码颜色：

```python
from ui.components import DashboardTheme

widget.setStyleSheet(DashboardTheme.get_card_style())
```

### 5. 延迟加载

主窗口采用延迟加载策略，只在用户首次切换到某个模块时才初始化：

```python
def _lazy_init_module(self, module_name: str):
    if module_name not in self._module_cache:
        self._module_cache[module_name] = self._create_module(module_name)
    return self._module_cache[module_name]
```

---

## 🚀 启动流程

### 完整启动序列

```
1. main.py 启动
   ↓
2. 创建 QApplication
   ↓
3. 创建 StartupCoordinator
   ↓
4. 显示启动屏幕（SplashScreen）
   ↓
5. BackendInitializerWorker 后台初始化
   │  ├─ 阶段1: 配置系统初始化
   │  ├─ 阶段2: 核心服务初始化
   │  ├─ 阶段3: 业务服务初始化
   │  ├─ 阶段4: 数据服务初始化
   │  ├─ 阶段5: 监控服务初始化
   │  └─ 阶段6: 启动完成
   ↓
6. BootOrchestrator 标记就绪点
   │  ├─ config_ready
   │  ├─ backend_ready
   │  ├─ ui_ready
   │  └─ ui_visible
   ↓
7. 创建 MainWindow
   ↓
8. 应用主题（ThemeManager）
   ↓
9. 注册快捷键（ShortcutManager，已合并到 main_window.py）
   ↓
10. 显示主窗口
   ↓
11. 关闭启动屏幕
   ↓
12. 应用程序运行（QApplication.exec()）
```

---

## 🔧 技术栈

### UI框架
- **PySide6** (6.x) - Qt6 Python绑定
  - QtCore - 核心非GUI功能
  - QtGui - GUI基础类
  - QtWidgets - 传统桌面UI组件

### 数据可视化
- **pyqtgraph** - 高性能实时绘图
- **matplotlib** - 静态图表（可选）

### 后端集成
- **VnPy** - 量化交易框架
  - vnpy.event.EventEngine - 事件引擎
  - vnpy.trader - 交易接口
  - vnpy_chartwizard - 图表组件

### 系统监控
- **psutil** - 跨平台系统监控库

### 代码编辑
- **Pygments** - 语法高亮

---

## 📝 开发规范

### 1. 文件编码
所有Python文件必须使用UTF-8编码，并在文件开头添加：

```python
# -*- coding: utf-8 -*-
```

### 2. 日志规范
使用标准logging模块，按功能分类logger：

```python
import logging

# UI层通用logger
logger = logging.getLogger("ui.module_name")

# 用户反馈专用logger
logger_user = logging.getLogger("ui.user_feedback")
```

### 3. 继承基类
所有自定义Widget应继承BaseWidget：

```python
from ui.components import BaseWidget
from backend.core.service_base import LoggerMixin

class MyWidget(BaseWidget, LoggerMixin):
    def __init__(self, parent=None):
        super().__init__(parent, "窗口标题")
        self.init_ui()
```

### 4. 信号与槽
使用Qt信号槽机制实现组件通信：

```python
from PySide6.QtCore import Signal

class MyWidget(QWidget):
    data_updated = Signal(dict)  # 自定义信号

    def emit_data(self, data):
        self.data_updated.emit(data)
```

### 5. 线程安全
UI更新必须在主线程执行：

```python
from PySide6.QtCore import QTimer

# 跨线程更新UI
QTimer.singleShot(0, lambda: self.update_label(text))
```

---

## 🎯 使用示例

### 创建自定义模块视图

```python
# -*- coding: utf-8 -*-
"""我的自定义模块."""

from PySide6.QtWidgets import QVBoxLayout, QLabel
from ui.components import BaseWidget
from backend.core.service_base import LoggerMixin

class MyModuleView(BaseWidget, LoggerMixin):
    """我的自定义模块主界面."""

    def __init__(self, parent=None):
        # 初始化服务
        self.my_service = None

        # 调用父类初始化
        super().__init__(parent, "我的模块")
        self.logger.info("模块初始化开始")

        # 初始化UI
        self.init_ui()

    def init_ui(self):
        """初始化UI."""
        layout = QVBoxLayout(self)

        label = QLabel("我的模块内容")
        layout.addWidget(label)

    def cleanup(self):
        """清理资源（窗口关闭时调用）."""
        self.logger.info("模块清理")
```

### 集成到主窗口

在`main_window.py`中注册模块：

```python
# 在导航列表中添加
self.nav_list.addItem("我的模块")

# 在create_module_views中添加
from ui.modules.my_module_view import MyModuleView
self.my_module_view = MyModuleView(self)
self.right_panel.addWidget(self.my_module_view)
```

---

## 📚 参考资料

### 内部文档
- `ui/components/README.md` - 组件库详细文档
- `docs/6个功能界面.md` - 功能需求文档

### 外部文档
- [PySide6 官方文档](https://doc.qt.io/qtforpython-6/)
- [VnPy 官方文档](https://www.vnpy.com/)
- [pyqtgraph 文档](https://pyqtgraph.readthedocs.io/)

---

## 🤝 贡献指南

在修改UI代码时，请遵循以下规范：

1. ✅ 所有文件使用UTF-8编码
2. ✅ 遵循PEP 8 代码风格
3. ✅ 使用类型提示（Type Hints）
4. ✅ 添加docstring文档
5. ✅ 使用DashboardTheme统一主题
6. ✅ 通过ServiceManager获取后端服务
7. ✅ 通过EventEngine监听后端事件
8. ✅ 测试主题切换兼容性
9. ✅ 测试资源清理（cleanup方法）

---

## 📞 技术支持

如有问题或建议，请联系开发团队。

---

**文档版本**:v1.1.0
**最后更新**:2025-10-31
**维护团队**:星辰金融终端开发组

---

# 6. 异步编程(qasync使用指南)

> 🆕 **GUI异步集成已启用** - 统一Qt事件循环与asyncio事件循环,简化UI层异步代码

## 6.1 概述

### 6.1.1 为什么需要qasync?

**问题背景**:
- 后端数据服务大量使用**asyncio**协程(如tdx_asyncio纯异步TDX接口)
- 前端Qt UI使用**Qt事件循环**(QEventLoop)
- 两者**事件循环不兼容**,导致UI层调用后端异步服务时代码冗长

**传统解决方案的问题**:
```python
# ❌ 传统方式:需要手动创建QThread
class ReloadSymbolsThread(QThread):
    finished_signal = Signal(dict)
    
    def run(self):
        # 在子线程中同步等待异步任务
        result = self.data_center_service.reload_symbol_list()
        self.finished_signal.emit(result)

class DataCenterView(QWidget):
    def on_reload_button_clicked(self):
        # 创建线程
        self.reload_thread = ReloadSymbolsThread()
        self.reload_thread.finished_signal.connect(self._on_reload_finished)
        self.reload_thread.start()
```

**缺点**:
- 代码冗长(需要单独的QThread类)
- 需要手动管理线程生命周期
- 信号槽连接复杂
- 错误处理困难

**qasync解决方案**:
```python
# ✅ qasync方式:直接使用async/await
# 注意：async_slot 已合并到 data_center_view.py，直接使用即可
@async_slot
async def on_reload_button_clicked(self):
        try:
            self.reload_button.setEnabled(False)
            # 直接await异步服务
            result = await self.service.reload_symbol_list_async()
            self._on_reload_finished(result)
        finally:
            self.reload_button.setEnabled(True)
```

**优点**:
- 代码简洁(无需QThread类)
- 自动管理事件循环
- 原生async/await语法
- 错误处理简单(try/except)

---

## 6.2 qasync集成原理

### 6.2.1 事件循环统一

**架构图**:
```
┌─────────────────────────────────────────┐
│      应用启动 (start_async_fixed.py)      │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  1. 创建QApplication                     │
│     app = QApplication(sys.argv)        │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  2. 安装qasync事件循环                   │
│     loop = qasync.QEventLoop(app)       │
│     asyncio.set_event_loop(loop)        │
│     app._qasync_loop = loop             │
└─────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────┐
│  3. 启动统一事件循环                     │
│     with loop:                          │
│         loop.run_forever()              │
└─────────────────────────────────────────┘
                    │
      ┌─────────────┴─────────────┐
      ▼                           ▼
┌──────────┐              ┌──────────────┐
│  Qt事件   │  <──统一──>  │ asyncio事件   │
│  (UI交互) │              │  (后端服务)   │
└──────────┘              └──────────────┘
```

**关键代码** (`start_async_fixed.py`):
```python
# 🆕 GUI异步集成: 安装qasync事件循环
try:
    import qasync
    import asyncio

    # 创建qasync事件循环(统一Qt+asyncio)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    logger.debug("[QASYNC] ✅ qasync事件循环已安装,Qt+asyncio统一运行")
    stage_logger.info("✅ GUI异步集成已启用(qasync)")

    # 保存循环引用,便于UI中使用
    app._qasync_loop = loop

except ImportError:
    logger.warning("[QASYNC] ⚠️ qasync未安装,回退到纯Qt模式")
    app._qasync_loop = None

# 🆕 根据qasync是否可用,选择不同的事件循环启动方式
if hasattr(app, '_qasync_loop') and app._qasync_loop is not None:
    # qasync模式: 使用loop.run_forever()
    logger.info("[EVENT-LOOP] 使用qasync事件循环(Qt+asyncio统一)")
    with app._qasync_loop:
        app._qasync_loop.run_forever()
    return 0
else:
    # 纯Qt模式: 使用app.exec()
    logger.info("[EVENT-LOOP] 使用纯Qt事件循环")
    return app.exec()
```

### 6.2.2 向后兼容性

**重要特性**:qasync集成**完全向后兼容**,现有代码无需修改即可继续工作。

| 代码类型 | 兼容性 | 说明 |
|---------|--------|------|
| QThread | ✅ 完全兼容 | 现有线程代码继续工作 |
| Signal/Slot | ✅ 完全兼容 | 信号槽机制不受影响 |
| QTimer | ✅ 完全兼容 | 定时器正常工作 |
| EventEngine | ✅ 完全兼容 | 事件总线正常工作 |
| ServiceManager | ✅ 完全兼容 | 服务管理不受影响 |

**迁移策略**:
- **渐进式迁移**:逐步将适合的UI代码改为async/await,其他代码保持不变
- **非强制性**:开发者可自由选择使用qasync或传统QThread
- **零风险**:即使qasync未安装,系统自动回退到纯Qt模式

---

## 6.3 async_utils工具包 ⚠️ 已迁移

> **状态**：已合并到 `ui/modules/data_center_view.py`  
> **原因**：该工具包仅被 `DataCenterView` 使用，为减少模块间依赖，已合并到使用者文件  
> **位置**：`ui/modules/data_center_view.py` 文件开头部分的合并代码

> **原始位置**：`ui/core/async_utils.py` (已删除)

### 6.3.1 @async_slot装饰器

**功能**:将async函数转为Qt Slot,支持直接在UI层使用async/await。

**基础用法**:
```python
from PySide6.QtWidgets import QWidget, QPushButton
# 注意：如果需要在其他模块使用，需要从 data_center_view 导入
# 或复制相关函数到目标模块
from ui.modules.data_center_view import async_slot

class MyWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.button = QPushButton("加载数据")
        # 直接连接async函数
        self.button.clicked.connect(self.on_button_clicked)
    
    @async_slot  # 将async函数转为Slot
    async def on_button_clicked(self):
        print("开始加载...")
        try:
            # 直接await后端异步服务
            data = await self.backend_service.load_data_async()
            self.display_data(data)
        except Exception as e:
            self.show_error(f"加载失败: {e}")
```

**带参数用法**:
```python
class MyWidget(QWidget):
    @async_slot(int, str)  # 指定参数类型
    async def on_item_selected(self, index: int, name: str):
        data = await self.service.get_item_data_async(index, name)
        self.update_ui(data)
```

**实现原理**:
```python
def async_slot(*args, **kwargs):
    def decorator(func: Callable) -> Callable:
        if not asyncio.iscoroutinefunction(func):
            raise TypeError(f"{func.__name__} 必须是async函数")

        @Slot(*args, **kwargs)
        @functools.wraps(func)
        def wrapper(self_or_first_arg, *func_args, **func_kwargs):
            # 获取事件循环
            loop = _get_event_loop()
            
            # 创建协程任务
            coro = func(self_or_first_arg, *func_args, **func_kwargs)
            
            if QASYNC_AVAILABLE and loop is not None:
                # qasync模式: 提交到asyncio事件循环
                task = asyncio.ensure_future(coro, loop=loop)
                task.add_done_callback(_async_slot_done_callback)
            else:
                # 回退模式: 在后台线程执行
                _run_async_in_thread(coro, func.__name__)
        
        return wrapper
    return decorator
```

**错误处理**:
- 自动捕获异步函数中的未处理异常
- 记录错误日志到logger_alert
- 防止异常导致UI崩溃

### 6.3.2 AsyncTaskRunner类

**功能**:异步任务管理器,提供任务提交、跟踪、取消、结果获取等功能。

**完整示例**:
```python
from PySide6.QtWidgets import QWidget, QPushButton, QLabel
# 注意：AsyncTaskRunner 已合并到 data_center_view.py
from ui.modules.data_center_view import AsyncTaskRunner

class DataProcessingWidget(QWidget):
    def __init__(self):
        super().__init__()
        
        # 创建任务管理器
        self.task_runner = AsyncTaskRunner()
        
        # 连接任务完成信号
        self.task_runner.task_completed.connect(self.on_task_completed)
        
        self.start_button = QPushButton("开始处理")
        self.cancel_button = QPushButton("取消")
        self.status_label = QLabel("就绪")
        
        self.start_button.clicked.connect(self.start_processing)
        self.cancel_button.clicked.connect(self.cancel_processing)
        
        self.current_task_id = None
    
    def start_processing(self):
        # 提交异步任务
        self.current_task_id = self.task_runner.submit(
            self.backend_service.process_data_async()
        )
        self.status_label.setText(f"处理中... (Task: {self.current_task_id[:8]})")
        self.start_button.setEnabled(False)
    
    def cancel_processing(self):
        if self.current_task_id:
            # 取消任务
            if self.task_runner.cancel(self.current_task_id):
                self.status_label.setText("已取消")
                self.start_button.setEnabled(True)
    
    def on_task_completed(self, task_id: str, success: bool, result):
        if task_id == self.current_task_id:
            if success:
                self.status_label.setText(f"完成: {result}")
            else:
                self.status_label.setText(f"失败: {result}")
            self.start_button.setEnabled(True)
            self.current_task_id = None
```

**API参考**:

| 方法 | 说明 |
|------|------|
| `submit(coro) -> str` | 提交异步任务,返回task_id |
| `cancel(task_id) -> bool` | 取消任务,成功返回True |
| `get_task_status(task_id) -> dict` | 获取任务状态 |
| `get_result(task_id) -> Any` | 获取任务结果(阻塞直到完成) |
| `cleanup_completed()` | 清理已完成任务 |

**信号**:
- `task_completed(task_id: str, success: bool, result: object)` - 任务完成时发射

### 6.3.3 await_in_qt()函数

**功能**:在Qt槽函数(非async)中等待异步任务完成。

**使用场景**:当你无法将整个槽函数改为async时,但需要调用异步服务。

**示例**:
```python
from PySide6.QtCore import Slot
# 注意：await_in_qt 已合并到 data_center_view.py
from ui.modules.data_center_view import await_in_qt

class MyWidget(QWidget):
    @Slot()  # 普通Slot(非async)
    def on_button_clicked(self):
        # 在普通函数中等待异步任务
        result = await_in_qt(
            self.backend_service.get_data_async(),
            timeout=5.0  # 5秒超时
        )
        if result is not None:
            self.display_data(result)
        else:
            self.show_error("加载超时")
```

**注意事项**:
- ⚠️ **阻塞UI线程**:此函数会阻塞当前线程,直到任务完成或超时
- ✅ **推荐使用@async_slot**:优先使用@async_slot替代,避免阻塞UI
- 🎯 **适用场景**:仅用于无法改为async的遗留代码

### 6.3.4 error_handler()装饰器

**功能**:统一错误处理,支持async和普通函数。

**示例**:
```python
# 注意：已合并到 data_center_view.py
from ui.modules.data_center_view import async_slot, error_handler

class MyWidget(QWidget):
    @async_slot
    @error_handler("加载数据失败")  # 自动处理错误
    async def on_load_clicked(self):
        # 即使这里抛出异常,也会被自动捕获并记录
        data = await self.service.load_data_async()
        self.display(data)
```

**效果**:
- 自动捕获异常并记录到logger_alert
- 显示自定义错误消息
- 防止异常导致UI崩溃

---

## 6.4 使用场景和最佳实践

### 6.4.1 适合使用qasync的场景

| 场景 | 说明 | 示例 |
|------|------|------|
| **后端异步服务调用** | 调用tdx_asyncio等异步接口 | 加载K线、下载数据 |
| **长时间IO操作** | 网络请求、文件读写 | 导出报表、上传文件 |
| **多任务并发** | 需要同时执行多个异步任务 | 并发下载多个股票数据 |
| **实时数据流** | WebSocket、事件流 | 行情推送、日志流 |

### 6.4.2 不适合使用qasync的场景

| 场景 | 说明 | 推荐方案 |
|------|------|----------|
| **CPU密集型计算** | 大量计算会阻塞事件循环 | 使用QThread+进程池 |
| **简单的UI操作** | 纯UI交互无需异步 | 直接使用Slot |
| **已有QThread代码** | 现有代码工作良好 | 保持不变,无需迁移 |

### 6.4.3 最佳实践

#### ✅ DO - 推荐做法

```python
# 1. 使用@async_slot简化异步槽函数
@async_slot
async def on_load_clicked(self):
    self.button.setEnabled(False)
    try:
        data = await self.service.load_async()
        self.update_ui(data)
    finally:
        self.button.setEnabled(True)

# 2. 使用error_handler统一错误处理
@async_slot
@error_handler("操作失败")
async def on_action(self):
    await self.service.do_something()

# 3. 并发执行多个异步任务
@async_slot
async def load_multiple_data(self):
    results = await asyncio.gather(
        self.service.load_data1(),
        self.service.load_data2(),
        self.service.load_data3(),
    )
    self.display_all(results)

# 4. 使用超时控制
@async_slot
async def load_with_timeout(self):
    try:
        data = await asyncio.wait_for(
            self.service.load_async(),
            timeout=5.0
        )
        self.display(data)
    except asyncio.TimeoutError:
        self.show_error("加载超时")
```

#### ❌ DON'T - 避免做法

```python
# ❌ 不要在async函数中使用阻塞调用
@async_slot
async def bad_example1(self):
    # 错误: time.sleep会阻塞整个事件循环
    time.sleep(5)
    # 正确: 使用asyncio.sleep
    await asyncio.sleep(5)

# ❌ 不要忘记await
@async_slot
async def bad_example2(self):
    # 错误: 忘记await,返回协程对象而非结果
    data = self.service.load_async()
    # 正确: 使用await
    data = await self.service.load_async()

# ❌ 不要在async函数中直接操作数据库/文件
@async_slot
async def bad_example3(self):
    # 错误: 阻塞IO会阻塞事件循环
    with open("data.txt", "r") as f:
        data = f.read()
    # 正确: 使用asyncio线程池
    data = await asyncio.to_thread(self._read_file)
```

### 6.4.4 性能优化建议

1. **批量操作**:使用`asyncio.gather()`并发执行多个任务
   ```python
   # 并发下载多个股票数据
   results = await asyncio.gather(
       *[self.service.load_stock(code) for code in codes]
   )
   ```

2. **超时控制**:防止任务无限等待
   ```python
   data = await asyncio.wait_for(task, timeout=5.0)
   ```

3. **资源清理**:在cleanup中取消所有任务
   ```python
   def cleanup(self):
       if hasattr(self, 'task_runner'):
           self.task_runner.cleanup_completed()
   ```

---

## 6.5 迁移指南

### 6.5.1 从QThread迁移到@async_slot

**迁移前** (传统QThread方式):
```python
class ReloadSymbolsThread(QThread):
    finished_signal = Signal(dict)
    error_signal = Signal(str)
    
    def __init__(self, service):
        super().__init__()
        self.service = service
    
    def run(self):
        try:
            result = self.service.reload_symbol_list()
            self.finished_signal.emit(result)
        except Exception as e:
            self.error_signal.emit(str(e))

class DataCenterView(QWidget):
    def on_reload_button_clicked(self):
        self.reload_button.setEnabled(False)
        
        self.reload_thread = ReloadSymbolsThread(self.service)
        self.reload_thread.finished_signal.connect(self._on_reload_finished)
        self.reload_thread.error_signal.connect(self._on_reload_error)
        self.reload_thread.start()
    
    def _on_reload_finished(self, result: dict):
        self.reload_button.setEnabled(True)
        self.update_ui(result)
    
    def _on_reload_error(self, error: str):
        self.reload_button.setEnabled(True)
        self.show_error(error)
```

**迁移后** (qasync方式):
```python
# 注意：async_slot 已合并到 data_center_view.py，直接使用即可
@async_slot
async def on_reload_button_clicked_async(self):
    @async_slot
    async def on_reload_button_clicked(self):
        self.reload_button.setEnabled(False)
        try:
            # 直接await异步服务
            result = await self.service.reload_symbol_list_async()
            self.update_ui(result)
        except Exception as e:
            self.show_error(str(e))
        finally:
            self.reload_button.setEnabled(True)
```

**对比**:
- 代码量减少约70%(从30行降至12行)
- 无需单独的Thread类
- 无需信号槽连接
- 错误处理更直观

### 6.5.2 迁移检查清单

- [ ] 后端服务提供async版本方法(如`reload_symbol_list_async()`)
- [ ] 使用合并到 `data_center_view.py` 的 `async_slot`（或从该文件导入）
- [ ] 将槽函数改为async函数
- [ ] 添加`@async_slot`装饰器
- [ ] 使用`await`调用异步服务
- [ ] 添加try/except错误处理
- [ ] 添加finally清理逻辑
- [ ] 删除旧的QThread类
- [ ] 删除信号槽连接代码
- [ ] 测试功能正常

---

## 6.6 故障排查

### 6.6.1 常见问题

**问题1**: `RuntimeError: no running event loop`

**原因**: 在没有事件循环的上下文中调用async函数

**解决**: 确保qasync已正确安装,检查启动日志是否有`✅ GUI异步集成已启用(qasync)`

---

**问题2**: async函数没有执行

**原因**: 忘记添加`@async_slot`装饰器

**解决**: 在async函数上添加`@async_slot`装饰器
```python
# ❌ 错误
async def on_clicked(self):
    await self.service.load()

# ✅ 正确
@async_slot
async def on_clicked(self):
    await self.service.load()
```

---

**问题3**: UI卡顿

**原因**: 在async函数中使用了阻塞操作(如`time.sleep`、同步文件IO)

**解决**: 使用asyncio版本的API
```python
# ❌ 错误
await asyncio.sleep(1)  # 之前错误地使用了time.sleep(1)

# ✅ 正确(读取文件)
data = await asyncio.to_thread(self._read_file_sync)
```

---

**问题4**: 异常未被捕获

**原因**: async函数中的异常需要特殊处理

**解决**: 使用`@error_handler`装饰器或手动try/except
```python
@async_slot
@error_handler("操作失败")
async def on_action(self):
    await self.service.do_something()
```

### 6.6.2 调试技巧

1. **查看启动日志**:确认qasync是否启用
   ```
   [QASYNC] ✅ qasync事件循环已安装,Qt+asyncio统一运行
   ✅ GUI异步集成已启用(qasync)
   [EVENT-LOOP] 使用qasync事件循环(Qt+asyncio统一)
   ```

2. **检查事件循环**:在UI代码中验证
   ```python
   # 注意：get_event_loop 已合并到 data_center_view.py
   from ui.modules.data_center_view import get_event_loop
   loop = get_event_loop()
   print(f"Event loop: {loop}")  # 应该是QEventLoop实例
   ```

3. **启用asyncio调试模式**:
   ```python
   import asyncio
   asyncio.get_event_loop().set_debug(True)
   ```

---

## 6.7 总结

### 6.7.1 关键收益

| 指标 | 改进 |
|------|------|
| **代码量** | 减少60-70% |
| **开发效率** | 提升50% |
| **错误处理** | 更简洁 |
| **可维护性** | 更好 |
| **向后兼容** | 100% |

### 6.7.2 推荐使用场景

✅ **推荐使用qasync**:
- 新功能开发
- 大量异步服务调用
- 复杂的异步流程

🔄 **渐进式迁移**:
- 现有代码保持不变
- 逐步改造适合的模块

⚠️ **保持传统方式**:
- CPU密集型任务(使用QThread+进程池)
- 代码简单且工作良好(无需改动)

---

### 6.7.3 参考资源

- **qasync官方文档**: https://github.com/CabbageDevelopment/qasync
- **asyncio官方文档**: https://docs.python.org/zh-cn/3/library/asyncio.html
- **项目内工具模块**: 已合并到 `ui/modules/data_center_view.py`
- **示例代码**: `ui/modules/data_center_view.py`(异步工具函数位于文件开头)

---

**本章维护**: 星辰金融终端开发组
**最后更新**: 2025-10-31

