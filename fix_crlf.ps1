# 修复bat文件的行结束符：确保所有行都使用CRLF

$batFile = "C:\Users\Administrator\Desktop\terminal_v0.50\启动终端（新架构版）.bat"

Write-Host "正在修复bat文件的行结束符..." -ForegroundColor Yellow

# 读取文件内容（作为文本）
$content = Get-Content $batFile -Raw -Encoding Default

# 统一行结束符为CRLF
# 先替换所有CRLF为临时标记
$content = $content -replace "`r`n", "`n"
# 然后替换所有LF为CRLF
$content = $content -replace "`n", "`r`n"

# 保存文件（使用Out-File，它会自动使用CRLF）
$content | Out-File -FilePath $batFile -Encoding Default -NoNewline

Write-Host "修复完成！" -ForegroundColor Green

# 验证
$bytes = [System.IO.File]::ReadAllBytes($batFile)
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

Write-Host "验证结果:" -ForegroundColor White
Write-Host "  CRLF数量: $crlfCount" -ForegroundColor White
Write-Host "  单独LF数量: $lfCount" -ForegroundColor White
Write-Host "  单独CR数量: $crCount" -ForegroundColor White

if ($lfCount -eq 0 -and $crCount -eq 0) {
    Write-Host "✓ 文件已成功转换为CRLF格式（所有行都使用CRLF）" -ForegroundColor Green
} else {
    Write-Host "⚠ 仍有单独的行结束符（LF: $lfCount, CR: $crCount）" -ForegroundColor Yellow
}

