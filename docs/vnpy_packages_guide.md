# -*- coding: utf-8 -*-
# VNPY扩展包安装指南

## 📦 概述

星辰金融终端基于VNPY框架开发，需要安装一系列VNPY扩展包才能使用完整功能。本文档提供详细的安装指南和故障排除方法。

---

## ✅ 必需包列表

以下是终端正常运行所必需的VNPY扩展包：

| 包名 | 功能 | 安装命令 |
|------|------|---------|
| **vnpy_sqlite** | SQLite数据库支持 | `pip install git+https://github.com/vnpy/vnpy_sqlite.git` |
| **vnpy_ctastrategy** | CTA策略引擎 | `pip install git+https://github.com/vnpy/vnpy_ctastrategy.git` |
| **vnpy_ctabacktester** | CTA回测引擎 | `pip install git+https://github.com/vnpy/vnpy_ctabacktester.git` |
| **vnpy_paperaccount** | 模拟交易网关 | `pip install git+https://github.com/vnpy/vnpy_paperaccount.git` |
| **vnpy_datarecorder** | 数据录制服务 | `pip install git+https://github.com/vnpy/vnpy_datarecorder.git` |
| **vnpy_riskmanager** | 风险管理服务 | `pip install git+https://github.com/vnpy/vnpy_riskmanager.git` |
| **vnpy_chartwizard** | 图表可视化 | `pip install git+https://github.com/vnpy/vnpy_chartwizard.git` |

---

## 💡 可选包列表

以下是增强功能的可选扩展包：

### 策略引擎

| 包名 | 功能 | 安装命令 |
|------|------|---------|
| **vnpy_portfoliostrategy** | 组合策略引擎 | `pip install git+https://github.com/vnpy/vnpy_portfoliostrategy.git` |
| **vnpy_algotrading** | 算法交易引擎 | `pip install git+https://github.com/vnpy/vnpy_algotrading.git` |
| **vnpy_spreadtrading** | 价差交易引擎 | `pip install git+https://github.com/vnpy/vnpy_spreadtrading.git` |
| **vnpy_optionmaster** | 期权策略引擎 | `pip install git+https://github.com/vnpy/vnpy_optionmaster.git` |
| **vnpy_scripttrader** | 脚本交易引擎 | `pip install git+https://github.com/vnpy/vnpy_scripttrader.git` |

### 交易网关

| 包名 | 功能 | 安装命令 |
|------|------|---------|
| **vnpy_ctp** | CTP期货网关 | `pip install git+https://github.com/vnpy/vnpy_ctp.git` |
| **vnpy_ctptest** | CTP测试网关 | `pip install git+https://github.com/vnpy/vnpy_ctptest.git` |
| **vnpy_mini** | CTP Mini网关 | `pip install git+https://github.com/vnpy/vnpy_mini.git` |
| **vnpy_sopt** | 期权网关 | `pip install git+https://github.com/vnpy/vnpy_sopt.git` |
| **vnpy_tts** | 仿真交易网关 | `pip install git+https://github.com/vnpy/vnpy_tts.git` |
| **vnpy_ib** | IB网关 | `pip install git+https://github.com/vnpy/vnpy_ib.git` |

### 数据源

| 包名 | 功能 | 安装命令 |
|------|------|---------|
| **vnpy_tushare** | Tushare数据源 | `pip install git+https://github.com/vnpy/vnpy_tushare.git` |
| **vnpy_rqdata** | RQData数据源 | `pip install git+https://github.com/vnpy/vnpy_rqdata.git` |
| **vnpy_ifind** | iFind数据源 | `pip install git+https://github.com/vnpy/vnpy_ifind.git` |

---

## 🚀 一键安装

### 方法1：使用安装脚本（推荐）

项目提供了自动化安装脚本，支持批量安装：

```bash
# 仅安装必需包
python scripts/install_vnpy_packages.py --essential

# 安装所有包（包括可选包）
python scripts/install_vnpy_packages.py --all

# 按类别安装
python scripts/install_vnpy_packages.py --category "策略引擎"
python scripts/install_vnpy_packages.py --category "交易网关"

# 安装指定包
python scripts/install_vnpy_packages.py --packages vnpy_ctp vnpy_tushare
```

### 方法2：手动安装

如果脚本安装失败，可以手动逐个安装：

```bash
# 激活虚拟环境（如果使用）
# Windows
venv310\Scripts\activate

# Linux/Mac
# source venv310/bin/activate

# 安装必需包
pip install git+https://github.com/vnpy/vnpy_sqlite.git
pip install git+https://github.com/vnpy/vnpy_ctastrategy.git
pip install git+https://github.com/vnpy/vnpy_ctabacktester.git
pip install git+https://github.com/vnpy/vnpy_paperaccount.git
pip install git+https://github.com/vnpy/vnpy_datarecorder.git
pip install git+https://github.com/vnpy/vnpy_riskmanager.git
pip install git+https://github.com/vnpy/vnpy_chartwizard.git
```

---

## 🔍 安装验证

安装完成后，运行检查脚本验证：

```bash
python scripts/check_vnpy_packages.py
```

脚本会生成详细的安装状态报告，包括：
- ✅ 已安装的包和版本
- ❌ 未安装的包
- ⚠️ 必需但未安装的包（需要优先安装）

---

## ❓ 常见问题

### Q1: 安装时提示"git不可用"

**原因**: 系统未安装git或git不在PATH环境变量中。

**解决方案**:
1. 下载并安装Git: https://git-scm.com/downloads
2. 安装后重启命令行窗口
3. 验证: `git --version`

### Q2: 安装时出现网络超时

**原因**: GitHub访问不稳定。

**解决方案**:
1. 使用国内镜像（如果可用）
2. 配置Git代理:
   ```bash
   git config --global http.proxy http://127.0.0.1:7890
   git config --global https.proxy http://127.0.0.1:7890
   ```
3. 手动克隆后安装:
   ```bash
   git clone https://github.com/vnpy/vnpy_ctp.git
   cd vnpy_ctp
   pip install -e .
   ```

### Q3: 安装成功但导入失败

**原因**: 虚拟环境或Python路径问题。

**解决方案**:
1. 确认使用正确的Python环境:
   ```bash
   which python  # Linux/Mac
   where python  # Windows
   ```
2. 确认包已安装:
   ```bash
   pip list | grep vnpy
   ```
3. 尝试重新安装:
   ```bash
   pip uninstall vnpy_ctp
   pip install git+https://github.com/vnpy/vnpy_ctp.git
   ```

### Q4: CTP网关安装失败（Windows）

**原因**: CTP网关需要特定的C++运行库。

**解决方案**:
1. 安装Microsoft Visual C++ Redistributable:
   - 下载: https://aka.ms/vs/17/release/vc_redist.x64.exe
   - 安装后重启
2. 重新安装vnpy_ctp:
   ```bash
   pip install git+https://github.com/vnpy/vnpy_ctp.git
   ```

### Q5: vnpy_chartwizard导入失败

**原因**: 缺少PySide6或相关依赖。

**解决方案**:
1. 确认PySide6已安装:
   ```bash
   pip install PySide6>=6.2.0
   ```
2. 重新安装vnpy_chartwizard:
   ```bash
   pip install git+https://github.com/vnpy/vnpy_chartwizard.git
   ```

---

## 🔧 高级配置

### 使用国内镜像加速

如果GitHub访问缓慢，可以使用国内镜像（如果可用）：

```bash
# 配置pip镜像
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# 或使用临时镜像
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple package_name
```

### 离线安装

1. 在有网络的环境下载包：
   ```bash
   git clone https://github.com/vnpy/vnpy_ctp.git
   cd vnpy_ctp
   python setup.py sdist
   ```

2. 将生成的`dist/`目录复制到离线环境

3. 在离线环境安装：
   ```bash
   pip install dist/vnpy_ctp-*.tar.gz
   ```

---

## 📊 包依赖关系

```
星辰金融终端
├── vnpy (核心框架) ✅ 必需
│
├── 数据库
│   └── vnpy_sqlite ✅ 必需
│
├── 策略引擎
│   ├── vnpy_ctastrategy ✅ 必需
│   ├── vnpy_ctabacktester ✅ 必需
│   ├── vnpy_portfoliostrategy 💡 可选
│   ├── vnpy_algotrading 💡 可选
│   ├── vnpy_spreadtrading 💡 可选
│   ├── vnpy_optionmaster 💡 可选
│   └── vnpy_scripttrader 💡 可选
│
├── 交易网关
│   ├── vnpy_paperaccount ✅ 必需
│   ├── vnpy_ctp 💡 可选
│   ├── vnpy_ctptest 💡 可选
│   ├── vnpy_mini 💡 可选
│   ├── vnpy_sopt 💡 可选
│   ├── vnpy_tts 💡 可选
│   └── vnpy_ib 💡 可选
│
├── 数据服务
│   ├── vnpy_datarecorder ✅ 必需
│   └── vnpy_riskmanager ✅ 必需
│
├── 数据源
│   ├── vnpy_tushare 💡 可选
│   ├── vnpy_rqdata 💡 可选
│   └── vnpy_ifind 💡 可选
│
└── 图表可视化
    └── vnpy_chartwizard ✅ 必需
```

---

## 📝 更新日志

### v1.0.0 (2025-10-09)
- 初始版本
- 支持7个必需包
- 支持19个可选包
- 提供一键安装脚本

---

## 🆘 获取帮助

如果遇到本文档未覆盖的问题：

1. **查看终端日志**: `logs/terminal_v0.50.log`
2. **运行检查脚本**: `python scripts/check_vnpy_packages.py`
3. **查看VNPY官方文档**: https://www.vnpy.com/docs/
4. **联系技术支持**: support@example.com

---

## 📚 相关文档

- [数据存储架构文档](data_storage_architecture.md)
- [系统架构说明](../README.md)
- [开发指南](development_guide.md)

