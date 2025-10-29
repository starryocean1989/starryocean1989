# -*- coding: utf-8 -*-
# UI架构说明文档

> 星辰金融终端 - 前端界面层完整架构说明

## 📂 UI文件夹整体结构

```
ui/
├── __init__.py                    # UI层统一导出（MainWindow, ThemeManager）
│
├── main_window.py                 # 主窗口：应用程序的主界面框架
├── startup_coordinator.py         # 启动协调器：管理应用启动顺序和后端初始化
│
├── core/                          # 核心功能模块
│   ├── __init__.py
│   ├── boot_orchestrator.py       # 启动编排器：管理分层启动就绪状态
│   └── shortcut_manager.py        # 快捷键管理器：全局快捷键系统
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

#### 1.3 `startup_coordinator.py`
**作用**：启动协调器 - 管理应用启动顺序和异步初始化
**功能**：
- 后台线程异步初始化后端服务（六阶段初始化策略）
- 管理启动进度显示和用户反馈
- 启动监控系统（wmi_smart_monitor）
- 监控进程看门狗管理
- 异常处理和错误恢复机制

**关键类**：
- `BackendInitializerWorker(QObject)` - 后端初始化工作线程
  - 信号：`progress_updated` / `initialization_completed` / `error_occurred`
  - 方法：`run()` - 并行启动后端服务和监控系统

**六阶段初始化流程**：
1. **阶段1（0-10%）**：配置系统初始化
2. **阶段2（10-30%）**：核心服务初始化
3. **阶段3（30-60%）**：业务服务初始化
4. **阶段4（60-80%）**：数据服务初始化
5. **阶段5（80-95%）**：监控服务初始化
6. **阶段6（95-100%）**：启动完成

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

#### 2.2 `shortcut_manager.py`
**作用**：全局快捷键管理系统
**功能**：
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

所有UI组件通过EventEngine监听后端事件，实现松耦合：

```python
from vnpy.event import Event, EventEngine

# 注册事件监听
self.event_engine.register(EVENT_TICK, self.on_tick)

# 事件处理
def on_tick(self, event: Event):
    tick = event.data
    self.update_display(tick)
```

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
9. 注册快捷键（ShortcutManager）
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

**文档版本**：v1.0.0
**最后更新**：2025-10-29
**维护团队**：星辰金融终端开发组

