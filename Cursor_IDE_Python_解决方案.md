# Cursor IDE Python 环境完整解决方案

## 问题描述
Cursor IDE 显示 `command 'python.analysis.restartLanguageServer' not found` 错误，无法正常显示代码错误和警告。

## 根本原因
1. **缺少Python扩展**：Cursor IDE 没有安装必要的Python语言支持扩展
2. **语言服务器配置错误**：Python语言服务器（Pylance）没有正确配置
3. **解释器路径问题**：IDE没有正确识别Python解释器路径

## 完整解决方案

### 第一步：安装必要的扩展

在Cursor IDE中按 `Ctrl+Shift+X` 打开扩展面板，搜索并安装以下扩展：

1. **Python** (ms-python.python) - 核心Python支持
2. **Pylint** (ms-python.pylint) - 代码检查
3. **Black Formatter** (ms-python.black-formatter) - 代码格式化
4. **Python Debugger** (ms-python.debugpy) - 调试支持

### 第二步：配置Python解释器

1. 按 `Ctrl+Shift+P`
2. 搜索 `Python: Select Interpreter`
3. 选择 `./venv310/Scripts/python.exe`

### 第三步：重启语言服务器

由于 `Python: Restart Language Server` 命令不可用，请使用以下替代方法：

1. 按 `Ctrl+Shift+P`
2. 搜索 `Developer: Reload Window`
3. 或者完全关闭并重新打开Cursor IDE

### 第四步：验证配置

运行以下命令验证环境：

```bash
# 检查Python环境
python diagnose_cursor.py

# 如果问题仍然存在，运行修复脚本
python fix_cursor_python.py

# 重启Python功能
python restart_cursor_python.py
```

## 已创建的配置文件

### 1. `.vscode/settings.json`
包含完整的Python开发环境配置：
- Python解释器路径
- 语言服务器设置（Pylance）
- Linting配置（pylint, flake8）
- 格式化配置（black, isort）
- 调试配置

### 2. `pyrightconfig.json`
Pylance语言服务器的配置文件

### 3. `.vscode/launch.json`
调试配置文件，支持：
- 当前文件调试
- 终端应用调试

## 验证方法

重启Cursor IDE后，您应该能看到：

1. **代码错误显示**：红色波浪线显示语法错误
2. **代码警告显示**：黄色波浪线显示代码质量问题
3. **自动补全**：智能代码补全功能
4. **悬停信息**：鼠标悬停显示类型信息
5. **问题面板**：底部问题面板显示所有错误和警告

## 故障排除

### 如果仍然不显示错误：

1. **检查输出面板**：
   - 按 `Ctrl+Shift+U` 打开输出面板
   - 选择 "Python" 查看语言服务器日志

2. **手动重启语言服务器**：
   - 按 `Ctrl+Shift+P`
   - 搜索 `Python: Restart Language Server`
   - 如果命令不存在，使用 `Developer: Reload Window`

3. **检查Python扩展状态**：
   - 按 `Ctrl+Shift+P`
   - 搜索 `Python: Show Output`
   - 查看是否有错误信息

4. **重新安装扩展**：
   - 卸载Python扩展
   - 重启Cursor IDE
   - 重新安装Python扩展

## 高级配置

### 自定义Linting规则

在 `.vscode/settings.json` 中可以自定义：

```json
{
    "python.linting.pylintArgs": [
        "--disable=C0413,C0415,C0301,W0718,W0611,W0621,W0404,R1705"
    ],
    "python.linting.flake8Args": [
        "--max-line-length=88",
        "--extend-ignore=E402,D400,I100"
    ]
}
```

### 工作区特定设置

项目根目录的 `pyrightconfig.json` 提供项目特定的类型检查配置。

## 总结

通过以上步骤，Cursor IDE应该能够：
- 正确显示Python代码错误和警告
- 提供智能代码补全
- 支持代码格式化
- 启用调试功能

如果问题仍然存在，请检查：
1. Python扩展是否正确安装
2. 解释器路径是否正确
3. 语言服务器是否正常运行
4. 输出面板中的错误日志
