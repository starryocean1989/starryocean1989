# 🚀 星辰金融终端启动指南

本指南介绍如何使用星辰金融终端的启动脚本和热更新功能。

## 📋 前置要求

- Python 3.10+
- 虚拟环境已创建（`venv310`）
- 依赖包已安装

## 🎯 快速开始

### Windows 用户

双击运行 `start_terminal.bat` 启动交互式菜单：

```bash
start_terminal.bat
```

### 命令行用户

直接运行启动脚本：

```bash
# 完整启动（推荐）
python start_terminal.py

# 快速启动
python start_terminal.py quick
```

## 🔧 启动模式

### 1. 完整启动（推荐）
- 启动后端服务（VNPY引擎）
- 启动UI界面
- 启用守护进程监控
- 支持自动重启

### 2. 快速启动
- 仅启动必要服务
- 快速验证系统状态
- 适合调试和测试

### 3. 开发模式
- 启用调试日志
- 支持热更新
- 实时监控文件变化

### 4. 诊断模式
- 检查系统环境
- 验证依赖完整性
- 显示详细状态信息

## 🔥 热更新功能

### 启动热更新监控

```bash
python hot_reload.py
```

热更新会自动监控以下类型的文件变化：
- `.py` - Python源代码
- `.json` - 配置文件
- `.yaml/.yml` - YAML配置

### 热更新特性

- ✅ **自动检测文件变化**
- ✅ **智能重启服务**
- ✅ **防止频繁重启**
- ✅ **忽略无关文件**
- ✅ **详细日志记录**

### 监控范围

默认监控以下目录：
- `backend/` - 后端代码
- `ui/` - 前端界面
- `start_terminal.py` - 启动脚本

## 📊 系统诊断

运行诊断检查系统状态：

```bash
# 通过批处理文件
start_terminal.bat -> 选择诊断模式

# 通过命令行
python -c "
import sys
sys.path.insert(0, '.')
from start_terminal import TerminalLauncher

launcher = TerminalLauncher()
diagnostics = launcher.run_diagnostics()

print('📊 系统诊断结果:')
for key, value in diagnostics.items():
    if key == 'import_error':
        continue
    status = '✅' if value else '❌'
    print(f'{status} {key}: {value}')
"
```

## 🔍 日志查看

系统运行时会产生以下日志文件：

- `logs/terminal_v0.50.log` - 主应用日志
- `logs/launcher.log` - 启动器日志
- `logs/hot_reload.log` - 热更新日志

## ⚙️ 高级配置

### 修改启动配置

编辑 `start_terminal.py` 中的 `TerminalLauncher` 类：

```python
class TerminalLauncher:
    def __init__(self):
        # 虚拟环境路径
        self.venv_path = self.project_root / "venv310"

        # 自动重启配置
        self.auto_restart = True
        self.restart_delay = 2.0

        # 热更新配置
        self.enable_hot_reload = True
```

### 自定义监控路径

```python
# 在 hot_reload.py 中添加监控路径
monitor.add_watch_path("custom_modules/")

# 忽略特定文件
monitor.add_ignore_pattern("temp/")
```

## 🚨 故障排除

### 常见问题

1. **虚拟环境不存在**
   ```bash
   python -m venv venv310
   venv310\Scripts\activate.bat  # Windows
   # 或
   source venv310/bin/activate  # Unix/Mac
   ```

2. **依赖包缺失**
   ```bash
   pip install -r requirements.txt
   ```

3. **端口冲突**
   - 检查是否有其他应用占用端口
   - 修改配置文件中的端口设置

4. **权限问题**
   - Windows: 以管理员身份运行
   - Unix/Mac: 检查文件权限

### 获取帮助

如果遇到问题，请：

1. 查看日志文件获取详细错误信息
2. 运行诊断模式检查系统状态
3. 检查虚拟环境和依赖安装

## 📈 性能优化

### 启动优化

- 使用快速启动模式进行调试
- 仅在开发时启用热更新
- 定期清理日志文件

### 监控优化

- 调整热更新监控间隔（默认2秒）
- 根据需要添加/移除监控路径
- 使用忽略模式排除无关文件

## 🔄 更新说明

- **热更新**: 修改代码后自动重启服务
- **手动重启**: 按 Ctrl+C 退出后重新启动
- **版本升级**: 拉取最新代码后重启服务

---

*本启动指南适用于星辰金融终端 v5.0.0。如有问题，请联系技术支持。*
