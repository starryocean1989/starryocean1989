# -*- coding: utf-8 -*-
# 在另一台电脑上连接远程仓库 - 快速操作指南

## 前提条件

确保你已经通过以下任一方式将项目文件传输到另一台电脑：
- ✅ 通过U盘/网盘复制了整个项目文件夹（包括`.git`文件夹）
- ✅ 或者直接在另一台电脑上克隆了仓库

---

## 操作步骤

在另一台电脑上，进入项目目录后，依次执行以下命令：

### 步骤 1：添加远程仓库

```bash
git remote add origin https://github.com/starryocean1989/starryocean1989.git
```

### 步骤 2：拉取远程信息

```bash
git fetch origin
```

### 步骤 3：设置 upstream

```bash
git branch --set-upstream-to=origin/rollback-to-multithreaded rollback-to-multithreaded
```

### 步骤 4：同步代码

```bash
git pull
```

---

## 验证设置

执行完以上步骤后，可以验证设置是否成功：

```bash
# 查看远程仓库配置
git remote -v

# 查看分支跟踪关系
git branch -vv

# 查看状态
git status -sb
```

应该看到：
- `origin  https://github.com/starryocean1989/starryocean1989.git`
- `* rollback-to-multithreaded ... [origin/rollback-to-multithreaded]`

---

## 之后的使用

设置完成后，你就可以使用简化的命令：

```bash
# 拉取远程更新
git pull

# 推送到远程
git push

# 查看与远程的差异
git status -sb
```

---

## 注意事项

1. **如果远程仓库已存在**：如果执行步骤1时提示 `fatal: remote origin already exists`，说明远程已配置，可以跳过步骤1。

2. **如果分支名不同**：如果本地分支名不是 `rollback-to-multithreaded`，请将步骤3中的分支名替换为你的实际分支名。

3. **如果出现冲突**：如果 `git pull` 时出现冲突，需要先解决冲突后再继续。

4. **首次使用**：如果是首次使用GitHub，可能需要配置认证（SSH key 或 Personal Access Token）。

---

## 完整命令（一键复制）

```bash
# 添加远程仓库
git remote add origin https://github.com/starryocean1989/starryocean1989.git

# 拉取远程信息
git fetch origin

# 设置upstream
git branch --set-upstream-to=origin/rollback-to-multithreaded rollback-to-multithreaded

# 同步
git pull
```
