# -*- coding: utf-8 -*-
# AI助手配置说明

## DeepSeek API Key 设置方法

### 方式1：使用.env文件（推荐）✅

1. **在项目根目录创建`.env`文件**
   ```
   C:\Users\USER\Desktop\terminal_v0.50\.env
   ```

2. **在.env文件中添加以下内容**：
   ```env
   AI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

3. **保存文件，重启应用即可**

**完整示例**：
```env
# AI助手配置
AI_API_KEY=sk-your-actual-api-key-here
AI_MODEL=deepseek-chat
AI_MAX_TOKENS=2000
AI_TEMPERATURE=0.7
```

---

### 方式2：Windows环境变量（永久有效）

1. **打开系统环境变量设置**：
   - 右键"此电脑" → 属性
   - 高级系统设置 → 环境变量
   - 在"用户变量"中点击"新建"

2. **添加变量**：
   - 变量名：`AI_API_KEY`
   - 变量值：`sk-your-actual-api-key-here`

3. **点击确定，重启应用**

---

### 方式3：PowerShell临时设置（本次会话）

打开PowerShell，输入：
```powershell
$env:AI_API_KEY="sk-your-actual-api-key-here"
```

然后在同一个PowerShell窗口启动应用：
```powershell
python start_terminal.py
```

---

### 方式4：批处理文件启动

创建一个`start_with_ai.bat`文件：
```batch
@echo off
set AI_API_KEY=sk-your-actual-api-key-here
python start_terminal.py
pause
```

双击运行此批处理文件即可。

---

## 如何获取DeepSeek API Key

1. **访问DeepSeek官网**：https://platform.deepseek.com/

2. **注册账号**（如果还没有）

3. **进入API管理页面**

4. **创建API Key**

5. **复制API Key**（格式类似：sk-xxxxxxxxxxxx）

---

## 验证配置是否生效

### 方法1：通过Python测试
```bash
cd C:\Users\USER\Desktop\terminal_v0.50
.\venv310\Scripts\python.exe -c "import os; print('AI_API_KEY:', 'configured' if os.getenv('AI_API_KEY') else 'not configured')"
```

### 方法2：查看应用日志
启动应用后，查看日志文件：
```
logs/terminal_v0.50.log
```

如果看到：
- `AI助手服务初始化完成（DeepSeek API已配置）` ✅ 配置成功
- `AI助手服务初始化完成（API Key未配置，使用模拟模式）` ⚠️ 未配置

---

## 不配置API Key的影响

**完全可以正常使用！** ✅

- AI助手会自动切换到**模拟模式**
- 会提供基础的响应和使用指南
- 不影响其他功能（数据、策略、回测、交易等）

只有需要AI辅助编写策略时，才需要配置真实的API Key。

---

## 费用说明

DeepSeek API是按使用量计费：
- 新用户通常有免费额度
- 具体价格查看：https://platform.deepseek.com/pricing
- 可以设置使用上限避免超支

---

## 推荐配置（.env文件）

```env
# ========== AI助手配置 ==========
AI_API_KEY=sk-your-actual-api-key-here
AI_MODEL=deepseek-chat
AI_MAX_TOKENS=2000
AI_TEMPERATURE=0.7
AI_TIMEOUT=30

# ========== 其他配置（可选）==========
# 日志级别
LOG_LEVEL=INFO

# 数据库路径
SQLITE_PATH=data/terminal.db

# API服务端口
API_PORT=8000
```

---

## 快速开始

1. **创建.env文件**
   ```
   在 C:\Users\USER\Desktop\terminal_v0.50\ 目录下
   新建文本文件，命名为 .env（注意没有.txt后缀）
   ```

2. **编辑.env文件**
   ```env
   AI_API_KEY=sk-你的API密钥
   ```

3. **保存并启动应用**
   ```bash
   python start_terminal.py
   ```

4. **验证**
   - 启动后查看日志
   - 或在策略中心尝试使用AI助手

---

**配置完成后即可享受AI辅助编程功能！** 🎉

