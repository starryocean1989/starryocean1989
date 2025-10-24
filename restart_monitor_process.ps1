# 重启监控进程脚本
# 请以管理员身份运行此脚本

Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  系统监控重构 - 重启监控进程" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""

# 1. 停止旧监控进程
Write-Host "[1/3] 停止旧监控进程..." -ForegroundColor Yellow
$oldPID = 11588
try {
    Stop-Process -Id $oldPID -Force -ErrorAction Stop
    Write-Host "✅ 成功停止进程 PID: $oldPID" -ForegroundColor Green
    Start-Sleep -Seconds 2
}
catch {
    Write-Host "⚠️ 进程 $oldPID 可能已经停止或不存在" -ForegroundColor Yellow
}

# 2. 检查端口是否释放
Write-Host ""
Write-Host "[2/3] 检查端口5557..." -ForegroundColor Yellow
$port5557 = netstat -ano | findstr "5557"
if ($port5557) {
    Write-Host "⚠️ 端口5557仍被占用:" -ForegroundColor Yellow
    Write-Host $port5557
    Write-Host ""
    Write-Host "正在强制释放..." -ForegroundColor Yellow
    $pidOnPort = ($port5557 | Select-String -Pattern '\d+$').Matches.Value
    if ($pidOnPort) {
        Stop-Process -Id $pidOnPort -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }
}
else {
    Write-Host "✅ 端口5557已释放" -ForegroundColor Green
}

# 3. 启动新监控进程
Write-Host ""
Write-Host "[3/3] 启动新监控进程（集成瓶颈分析）..." -ForegroundColor Yellow
Write-Host ""

$projectRoot = "C:\Users\USER\Desktop\terminal_v0.50"
$pythonExe = "$projectRoot\venv310\Scripts\python.exe"
$monitorScript = "$projectRoot\backend\infrastructure\system_vnpy\monitor_process_entry.py"

Write-Host "项目路径: $projectRoot" -ForegroundColor Cyan
Write-Host "Python路径: $pythonExe" -ForegroundColor Cyan
Write-Host "脚本路径: $monitorScript" -ForegroundColor Cyan
Write-Host ""

# 启动新监控进程（后台运行）
Start-Process -FilePath $pythonExe -ArgumentList $monitorScript -WorkingDirectory $projectRoot -WindowStyle Minimized

Write-Host "✅ 新监控进程已启动（最小化窗口）" -ForegroundColor Green
Write-Host ""
Write-Host "等待3秒让进程初始化..." -ForegroundColor Yellow
Start-Sleep -Seconds 3

# 4. 验证新进程
Write-Host ""
Write-Host "[验证] 检查新监控进程..." -ForegroundColor Yellow
$newPort = netstat -ano | findstr "5557"
if ($newPort) {
    Write-Host "✅ 监控进程正在运行！" -ForegroundColor Green
    Write-Host $newPort
    $newPID = ($newPort | Select-String -Pattern '\d+$').Matches.Value
    Write-Host ""
    Write-Host "新监控进程 PID: $newPID" -ForegroundColor Green
}
else {
    Write-Host "❌ 监控进程未成功启动，请检查日志" -ForegroundColor Red
}

# 5. 运行验证脚本
Write-Host ""
Write-Host "[验证] 运行ZMQ测试..." -ForegroundColor Yellow
Write-Host ""
& $pythonExe "$projectRoot\tests\test_ui_performance_tab.py"

Write-Host ""
Write-Host "================================================" -ForegroundColor Cyan
Write-Host "  重启完成！" -ForegroundColor Cyan
Write-Host "================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "下一步: 启动主UI进行完整验证" -ForegroundColor Yellow
Write-Host "运行: .\启动终端（增强版）.bat" -ForegroundColor Cyan
Write-Host ""
Write-Host "按任意键退出..." -ForegroundColor Gray
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")

