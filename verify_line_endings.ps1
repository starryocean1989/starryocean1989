# 验证bat文件的行结束符

$batFile = "C:\Users\Administrator\Desktop\terminal_v0.50\启动终端（新架构版）.bat"

Write-Host "`n验证bat文件的行结束符..." -ForegroundColor Cyan
Write-Host ""

$bytes = [System.IO.File]::ReadAllBytes($batFile)
Write-Host "文件大小: $($bytes.Length) 字节" -ForegroundColor White
Write-Host ""

# 检查行结束符
$crlfCount = 0
$lfCount = 0
$crCount = 0

for ($i = 0; $i -lt ($bytes.Length - 1); $i++) {
    if ($bytes[$i] -eq 0x0D -and $bytes[$i+1] -eq 0x0A) {
        $crlfCount++
    }
}

# 单独检查LF（不在CRLF中的）
for ($i = 0; $i -lt $bytes.Length; $i++) {
    if ($bytes[$i] -eq 0x0A) {
        # 检查前面是否有CR
        if ($i -eq 0 -or $bytes[$i-1] -ne 0x0D) {
            $lfCount++
        }
    }
    if ($bytes[$i] -eq 0x0D) {
        # 检查后面是否有LF
        if ($i -eq ($bytes.Length - 1) -or $bytes[$i+1] -ne 0x0A) {
            $crCount++
        }
    }
}

Write-Host "行结束符统计:" -ForegroundColor Yellow
Write-Host "  CRLF (0x0D 0x0A) 数量: $crlfCount" -ForegroundColor White
Write-Host "  LF only (0x0A) 数量: $lfCount" -ForegroundColor White
Write-Host "  CR only (0x0D) 数量: $crCount" -ForegroundColor White
Write-Host ""

if ($lfCount -eq 0 -and $crCount -eq 0 -and $crlfCount -gt 0) {
    Write-Host "✓ 文件使用CRLF格式（Windows标准）" -ForegroundColor Green
} elseif ($lfCount -gt 0) {
    Write-Host "❌ 文件包含LF格式行结束符（Unix格式）" -ForegroundColor Red
    Write-Host "⚠ 这会导致CMD解析错误" -ForegroundColor Yellow
} else {
    Write-Host "⚠ 文件行结束符格式异常" -ForegroundColor Yellow
}

Write-Host ""

# 检查前20字节和最后20字节
Write-Host "前20字节 (Hex):" -ForegroundColor Yellow
$hexBytes = $bytes[0..19] | ForEach-Object { '{0:X2}' -f $_ }
Write-Host ($hexBytes -join ' ') -ForegroundColor White

Write-Host ""
Write-Host "最后20字节 (Hex):" -ForegroundColor Yellow
$lastBytes = $bytes[-20..-1] | ForEach-Object { '{0:X2}' -f $_ }
Write-Host ($lastBytes -join ' ') -ForegroundColor White

Write-Host ""

