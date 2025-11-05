#!/bin/bash
# -*- coding: utf-8 -*-
# Git 远程仓库初始化和首次推送脚本
# 使用方法: bash scripts/setup-remote-and-push.sh <远程仓库地址>

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Git 远程仓库初始化和首次推送 ===${NC}\n"

# 检查是否提供了远程仓库地址
if [ -z "$1" ]; then
    echo -e "${RED}错误: 请提供远程仓库地址${NC}"
    echo "使用方法: bash scripts/setup-remote-and-push.sh <远程仓库地址>"
    echo ""
    echo "示例:"
    echo "  bash scripts/setup-remote-and-push.sh https://github.com/username/repo.git"
    echo "  bash scripts/setup-remote-and-push.sh git@github.com:username/repo.git"
    exit 1
fi

REMOTE_URL="$1"
REMOTE_NAME="origin"
CURRENT_BRANCH=$(git branch --show-current)

echo -e "${YELLOW}当前分支: ${CURRENT_BRANCH}${NC}"
echo -e "${YELLOW}远程仓库地址: ${REMOTE_URL}${NC}\n"

# 检查是否已有远程仓库
if git remote | grep -q "^${REMOTE_NAME}$"; then
    EXISTING_URL=$(git remote get-url ${REMOTE_NAME})
    echo -e "${YELLOW}警告: 已存在远程仓库 '${REMOTE_NAME}'${NC}"
    echo -e "${YELLOW}当前地址: ${EXISTING_URL}${NC}"
    read -p "是否要更新为新的地址? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git remote set-url ${REMOTE_NAME} "${REMOTE_URL}"
        echo -e "${GREEN}✓ 远程仓库地址已更新${NC}\n"
    else
        echo -e "${YELLOW}跳过更新，使用现有远程仓库${NC}\n"
        REMOTE_URL="${EXISTING_URL}"
    fi
else
    # 添加远程仓库
    echo -e "${GREEN}添加远程仓库 '${REMOTE_NAME}'...${NC}"
    git remote add ${REMOTE_NAME} "${REMOTE_URL}"
    echo -e "${GREEN}✓ 远程仓库已添加${NC}\n"
fi

# 验证远程仓库
echo -e "${GREEN}验证远程仓库连接...${NC}"
git remote -v
echo ""

# 检查是否有未提交的更改
if ! git diff-index --quiet HEAD --; then
    echo -e "${YELLOW}警告: 检测到未提交的更改${NC}"
    echo "建议先提交所有更改，然后再推送"
    read -p "是否继续推送? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${YELLOW}操作已取消${NC}"
        exit 0
    fi
fi

# 首次推送并设置 upstream
echo -e "${GREEN}推送分支到远程并设置 upstream...${NC}"
echo -e "${YELLOW}执行: git push -u ${REMOTE_NAME} ${CURRENT_BRANCH}${NC}\n"

if git push -u ${REMOTE_NAME} ${CURRENT_BRANCH}; then
    echo -e "\n${GREEN}✓✓✓ 首次推送成功！${NC}\n"
    echo -e "${GREEN}当前分支已设置为跟踪远程分支: ${REMOTE_NAME}/${CURRENT_BRANCH}${NC}\n"
    
    # 验证 upstream 设置
    echo -e "${GREEN}验证 upstream 设置:${NC}"
    git branch -vv | grep "^\\*"
    echo ""
    
    echo -e "${GREEN}之后你可以使用以下简化命令:${NC}"
    echo "  git push    # 推送到远程"
    echo "  git pull    # 从远程拉取"
    echo "  git status -sb  # 查看与远程的差异"
else
    echo -e "\n${RED}✗ 推送失败${NC}"
    echo -e "${YELLOW}可能的原因:${NC}"
    echo "  1. 远程仓库地址错误"
    echo "  2. 没有访问权限（检查SSH key或HTTPS认证）"
    echo "  3. 网络连接问题"
    exit 1
fi
