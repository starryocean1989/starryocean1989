# -*- coding: utf-8 -*-
# 🌟 星辰金融终端 v0.50

**纯Python量化交易桌面应用**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![VnPy](https://img.shields.io/badge/VnPy-3.0+-green.svg)](https://www.vnpy.com/)
[![Qt](https://img.shields.io/badge/Qt-PySide6-brightgreen.svg)](https://www.qt.io/)
[![Architecture](https://img.shields.io/badge/架构-纯桌面应用-orange.svg)]()
[![License](https://img.shields.io/badge/License-Private-red.svg)]()

---

## 📋 项目简介

星辰金融终端是一个功能完整的**纯Python量化交易桌面应用**，提供：
- 📊 专业的行情分析和看盘
- 🧠 策略编写、回测和AI辅助
- 🔗 多种交易网关支持
- 💼 组合投资管理
- 🗃️ 完整的数据中心
- 🛠️ 系统监控和管理

**架构特点：**
- ✅ 纯Python桌面应用，单进程运行
- ✅ UI直接调用服务层，无需Web框架
- ✅ 基于VnPy生态系统，功能强大
- ✅ 简洁高效，易于开发和调试

---

## ✅ 当前状态

**版本**: v0.50
**开发状态**: ✅ 完成
**测试状态**: ✅ 13/13测试通过
**部署状态**: ✅ 生产就绪

### 最新完成（2025-10-07）

- ✅ 完整的数据库层（11表，7Repository）
- ✅ VnPy集成（6种回测引擎 + 7种交易网关）
- ✅ DeepSeek AI助手集成
- ✅ 快捷键系统（28个快捷键）
- ✅ 主题切换（暗色/亮色）
- ✅ 完整的集成测试

---

## 🚀 快速开始

### 1. 环境要求

- Python 3.10+
- Windows 10/11
- 虚拟环境已创建（venv310）

### 2. 安装依赖

```bash
# 激活虚拟环境
.\venv310\Scripts\activate

# 安装基础依赖
pip install -r requirements.txt

# 安装VnPy包（可选）
python install_vnpy_packages.py --essential
```

### 3. 运行测试

```bash
# 数据库和VnPy集成测试
python test_database_integration.py

# 端到端测试
python test_e2e.py

# 前端功能测试
python test_frontend_integration.py
```

**期望结果**: 所有测试应该通过（13/13）

### 4. 启动应用

```bash
# 方式1：标准启动（推荐）
python start_terminal.py

# 方式2：快速启动
python start_terminal.py quick

# 方式3：使用批处理文件
start_terminal.bat

# 方式4：直接运行UI（开发调试用）
python ui/main_window.py
```

**注意：** 本项目是纯桌面应用，只启动一个UI进程，无需启动后端服务器。

---

## 🎮 功能特性

### 6个功能界面

1. **🛠️ 系统管理** - 8个子界面
   - 系统状态监控、性能指标、告警管理
   - 服务健康检查、系统配置
   - 日志管理、系统诊断、工具集合

2. **🗃️ 数据中心** - 4个子界面
   - 品种列表、数据下载
   - 本地数据、数据源管理

3. **📈 行情看板** - 单一界面
   - K线/分时/tick图表
   - 技术指标、品种叠加
   - 全时段支持

4. **🧠 策略指标中心** - 1固有组件 + 2子界面
   - 策略管理器（固有组件）
   - 策略编写（代码编辑器 + AI助手）
   - 策略回测（6种回测引擎）

5. **🔗 交易网关** - 1固有组件 + 2子界面
   - 网关管理器（固有组件）
   - 策略实例（策略池管理）
   - 交易监控（6种策略模板适配）

6. **📊 组合投资** - 2固有组件
   - 组合管理（自动识别 + 自定义）
   - 组合监控（业绩分析 + 风险管理）

### 核心能力

- ✅ **数据持久化** - SQLite数据库，11个表
- ✅ **回测能力** - 6种VnPy回测引擎
- ✅ **交易能力** - 7种VnPy交易网关
- ✅ **AI助手** - DeepSeek代码分析和生成
- ✅ **快捷键** - 28个预设快捷键
- ✅ **主题** - 暗色/亮色主题切换

---

## 🔧 配置说明

### AI助手配置（可选）

```bash
# 方式1：环境变量
set AI_API_KEY=your_deepseek_api_key

# 方式2：.env文件
echo AI_API_KEY=your_deepseek_api_key > .env
```

获取API Key: https://platform.deepseek.com/

### VnPy包安装（可选）

```bash
# 安装必需包（数据库 + 模拟交易）
python install_vnpy_packages.py --essential

# 或安装所有包
python install_vnpy_packages.py --all
```

**注意**: 不安装也可以正常使用，系统会自动使用模拟模式。

---

## ⌨️ 快捷键

### 常用快捷键

| 快捷键 | 功能 | 快捷键 | 功能 |
|--------|------|--------|------|
| Ctrl+S | 保存文件 | F5 | 刷新数据 |
| Ctrl+N | 新建策略 | F9 | 运行回测 |
| Ctrl+G | 连接网关 | Ctrl+H | 显示帮助 |
| Ctrl+1-6 | 切换功能界面 | Ctrl+Q | 退出应用 |

**查看所有快捷键**: 启动应用后按 `Ctrl+H`

---

## 🎨 主题

### 可用主题

- **dark** - 暗色主题（默认）
- **light** - 亮色主题

### 切换方法

在应用中：菜单栏 → 视图 → 切换主题

---

## 📁 项目结构

```
terminal_v0.50/
├── backend/              # 后端服务层（无Web框架）
│   ├── core/            # 核心模块（数据库等）
│   ├── repositories/    # 数据访问层（7个）
│   └── services/        # 业务逻辑层
├── ui/                   # UI界面层（PySide6）
│   ├── components/      # 6个功能界面
│   ├── core/            # 核心模块（快捷键）
│   ├── themes/          # 主题系统
│   └── widgets/         # 通用组件
├── docs/                 # 文档
├── config/               # 配置文件
├── data/                 # 数据文件
├── logs/                 # 日志文件
└── tests/                # 测试文件
```

## 🏗️ 架构说明

**纯Python桌面应用架构：**

本项目是纯Python桌面应用，采用简洁的三层架构：

```
┌──────────────────────────────────┐
│  UI Layer (PySide6)              │  ← 用户界面层
│  - 6个功能界面                   │
│  - 主题系统                       │
│  - 通用组件                       │
└────────────┬─────────────────────┘
             │ 直接调用
┌────────────▼─────────────────────┐
│  Service Layer                   │  ← 业务逻辑层
│  - 数据中心服务                  │
│  - 行情看板服务                  │
│  - 策略中心服务                  │
│  - 交易网关服务                  │
│  - 组合投资服务                  │
│  - 系统管理服务                  │
└────────────┬─────────────────────┘
             │ 调用
┌────────────▼─────────────────────┐
│  Core Layer                      │  ← 核心功能层
│  - VnPy引擎                      │
│  - 数据库（SQLite）              │
│  - 事件引擎                      │
│  - Repository层                  │
└──────────────────────────────────┘
```

**架构特点：**
- ✅ 单进程运行，UI直接调用服务层
- ✅ 无需FastAPI/uvicorn等Web框架
- ✅ 无需WebSocket等网络通信
- ✅ 简洁高效，易于调试

---

## 🧪 测试

### 运行所有测试

```bash
# 数据库和VnPy集成测试
python test_database_integration.py

# 前端功能测试
python test_frontend_integration.py

# 端到端测试
python test_e2e.py
```

### 测试覆盖

- ✅ 数据库初始化和操作
- ✅ Repository层CRUD
- ✅ 回测引擎（6种）
- ✅ 交易网关（7种）
- ✅ AI助手功能
- ✅ 快捷键系统
- ✅ 主题切换
- ✅ 完整业务流程

---

## 📚 文档

### 核心文档

- **FINAL_ACCEPTANCE_REPORT.md** ⭐ 验收报告（本次完成的全部工作）
- **NEXT_STEPS.md** ⭐ 下一步操作指南
- **README_启动指南.md** - 详细启动说明

### 技术文档

- **后端实现完成报告.md** - 后端架构和API
- **UI_架构使用指南.md** - 前端架构说明
- **docs/** - 需求和底层功能文档

---

## 🛠️ 技术栈

### UI层

- **PySide6** - Qt for Python（UI框架）
- **QSS** - Qt样式表（主题系统）
- **pyqtgraph** - 高性能图表（数据可视化）

### 服务层

- **VnPy** - 量化交易框架（核心引擎）
- **SQLite** - 数据库（数据存储）
- **DeepSeek** - AI服务（代码辅助）
- **aiohttp** - 异步HTTP客户端（网络请求）

### 工具

- **pytest** - 单元测试框架
- **black/flake8** - 代码质量工具

---

## 📞 问题排查

### 常见问题

**Q: 数据库初始化失败？**
A: 检查data目录权限

**Q: VnPy包安装失败？**
A: 网络问题，可直接使用模拟模式

**Q: AI助手不工作？**
A: 设置AI_API_KEY环境变量，或使用模拟模式

**Q: 快捷键冲突？**
A: 可以自定义快捷键

### 日志文件

- `logs/terminal_v0.50.log` - 应用日志
- `logs/launcher.log` - 启动日志

---

## 📖 更多信息

### 详细文档

完整的实现细节和使用说明，请查看：
- FINAL_COMPLETION_REPORT.md - 最详细的完成报告
- IMPLEMENTATION_COMPLETE.md - 快速开始指南
- WORK_SUMMARY.md - 工作总结

### 开发说明

如需了解开发过程和技术细节，请查看：
- PROGRESS_REPORT.md - 详细进度报告
- STAGE3_COMPLETION.md - VnPy集成说明

---

## 🎊 致谢

感谢您使用星辰金融终端！

如有问题或建议，请查看文档或运行测试定位问题。

---

**项目版本**: v0.50
**更新时间**: 2025-10-07
**维护状态**: ✅ 活跃

**Happy Trading! 🚀**

