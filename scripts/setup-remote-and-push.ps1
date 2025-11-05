# -*- coding: utf-8 -*-
# Git 远程仓库初始化和首次推送脚本 (PowerShell版本)
# 使用方法: .\scripts\setup-remote-and-push.ps1 -RemoteUrl <远程仓库地址>

param(
    [Parameter(Mandatory=$true)]
    [string]$RemoteUrl,
    
    [string]$RemoteName = "origin"
)

$ErrorActionPreference = "Stop"

Write-Host "=== Git 远程仓库初始化和首次推送 ===" -ForegroundColor Green
Write-Host ""

# 获取当前分支
$CurrentBranch = git branch --show-current

Write-Host "当前分支: $CurrentBranch" -ForegroundColor Yellow
Write-Host "远程仓库地址: $RemoteUrl" -ForegroundColor Yellow
Write-Host ""

# 检查是否已有远程仓库
$existingRemotes = git remote
if ($existingRemotes -contains $RemoteName) {
    $existingUrl = git remote get-url $RemoteName
    Write-Host "警告: 已存在远程仓库 '$RemoteName'" -ForegroundColor Yellow
    Write-Host "当前地址: $existingUrl" -ForegroundColor Yellow
    $update = Read-Host "是否要更新为新的地址? (y/n)"
    if ($update -eq "y" -or $update -eq "Y") {
        git remote set-url $RemoteName $RemoteUrl
        Write-Host "✓ 远程仓库地址已更新" -ForegroundColor Green
        Write-Host ""
    } else {
        Write-Host "跳过更新，使用现有远程仓库" -ForegroundColor Yellow
        Write-Host ""
        $RemoteUrl = $existingUrl
    }
} else {
    # 添加远程仓库
    Write-Host "添加远程仓库 '$RemoteName'..." -ForegroundColor Green
    git remote add $RemoteName $RemoteUrl
    Write-Host "✓ 远程仓库已添加" -ForegroundColor Green
    Write-Host ""
}

# 验证远程仓库
Write-Host "验证远程仓库连接..." -ForegroundColor Green
git remote -v
Write-Host ""

# 检查是否有未提交的更改
$uncommitted = git diff-index --quiet HEAD --
if (-not $uncommitted) {
    Write-Host "警告: 检测到未提交的更改" -ForegroundColor Yellow
    Write-Host "建议先提交所有更改，然后再推送"
    $continue = Read-Host "是否继续推送? (y/n)"
    if ($continue -ne "y" -and $continue -ne "Y") {
        Write-Host "操作已取消" -ForegroundColor Yellow
        exit 0
    }
}

# 首次推送并设置 upstream
Write-Host "推送分支到远程并设置 upstream..." -ForegroundColor Green
Write-Host "执行: git push -u $RemoteName $CurrentBranch" -ForegroundColor Yellow
Write-Host ""

try {
    git push -u $RemoteName $CurrentBranch
    Write-Host ""
    Write-Host "✓✓✓ 首次推送成功！" -ForegroundColor Green
    Write-Host ""
    Write-Host "当前分支已设置为跟踪远程分支: ${RemoteName}/${CurrentBranch}" -ForegroundColor Green
    Write-Host ""
    
    # 验证 upstream 设置
    Write-Host "验证 upstream 设置:" -ForegroundColor Green
    git branch -vv | Select-String "^\*"
    Write-Host ""
    
    Write-Host "之后你可以使用以下简化命令:" -ForegroundColor Green
    Write-Host "  git push    # 推送到远程"
    Write-Host "  git pull    # 从远程拉取"
    Write-Host "  git status -sb  # 查看与远程的差异"
} catch {
    Write-Host ""
    Write-Host "✗ 推送失败" -ForegroundColor Red
    Write-Host "可能的原因:" -ForegroundColor Yellow
    Write-Host "  1. 远程仓库地址错误"
    Write-Host "  2. 没有访问权限（检查SSH key或HTTPS认证）"
    Write-Host "  3. 网络连接问题"
    Write-Host "错误详情: $_" -ForegroundColor Red
    exit 1
}
