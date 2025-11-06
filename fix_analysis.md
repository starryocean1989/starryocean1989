# 系统配置问题分析与解决方案

## 问题定位证据

### 关键发现1：OutputEncoding设置错误
**诊断报告显示：**
```
OutputEncoding: US-ASCII (CodePage: 20127)
```
**应该是：** UTF-8 (CodePage: 65001)

### 关键发现2：PowerShell命令输出解析失败
**诊断报告显示：**
```
测试命令1: Write-Host '[测试] 这是测试'
输出: The string is missing the terminator: ".
```
所有测试都失败，说明CMD在解析PowerShell命令时的引号转义有问题。

### 关键发现3：配置文件可能未生效
- PowerShell配置文件存在且包含编码设置
- 但是从CMD调用PowerShell时，可能不加载配置文件
- 特别是使用`-NoProfile`或`-ExecutionPolicy Bypass`时

## 根本原因

**当从CMD调用PowerShell时：**
1. 如果不加载配置文件，`$OutputEncoding`默认是US-ASCII
2. 这导致PowerShell输出编码错误
3. CMD在解析PowerShell输出时，引号和特殊字符被错误解析
4. 结果：PowerShell输出被CMD当作命令执行

## 解决方案

**在bat文件的PowerShell命令中显式设置编码，而不是依赖配置文件。**

### 修改bat文件中的PowerShell命令

**第51行：**
```bat
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; $cleaned = 0; Get-Process python -ErrorAction SilentlyContinue | ForEach-Object { try { $cmdline = (Get-WmiObject Win32_Process -Filter \"ProcessId = $($_.Id)\").CommandLine; if ($cmdline) { if ($cmdline -match 'monitor_system\.py') { Write-Host \"[清理] 发现旧监控进程 (PID=$($_.Id))，正在终止...\"; Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue; if ($?) { Write-Host \"[OK] 已终止旧监控进程 (PID=$($_.Id))\"; $cleaned = 1 } } elseif ($cmdline -match 'start_new\.py|start_async_fixed\.py') { Write-Host \"[清理] 发现残留主进程 (PID=$($_.Id))，正在终止...\"; Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue; if ($?) { Write-Host \"[OK] 已终止残留主进程 (PID=$($_.Id))\"; $cleaned = 1 } } } } catch { } }; if ($cleaned -eq 0) { Write-Host \"[OK] 未发现残留进程\" } else { Write-Host \"[OK] 已清理残留进程，等待资源释放...\"; Start-Sleep -Seconds 2 }"
```

**第55行：**
```bat
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8; $ports = Get-NetTCPConnection -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in 5557,5558,5559 -and $_.State -eq 'Listen' }; if ($ports) { $ports | ForEach-Object { $proc = Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue; if ($proc) { Write-Host \"[警告] 端口 $($_.LocalPort) 被进程 $($_.OwningProcess) ($($proc.ProcessName)) 占用\" } } } else { Write-Host \"[OK] 监控端口未被占用\" }"
```

**关键修改：**
1. 添加`-NoProfile`参数：明确不加载配置文件
2. 在命令开头添加编码设置：`[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; $OutputEncoding = [System.Text.Encoding]::UTF8;`
3. 确保所有PowerShell命令都显式设置编码

## 验证

修复后，重新运行bat文件，应该不再出现：
- `'}' is not recognized` 错误
- `'.' is not recognized` 错误
- `'[✓]' is not recognized` 错误
- 中文乱码被当作命令的错误

