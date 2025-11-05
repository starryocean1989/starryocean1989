# -*- coding: utf-8 -*-
# Git Upstream 分支设置指南

## 什么是 Upstream（上游分支）

**Upstream（上游分支）**是本地分支跟踪的远程分支。设置 upstream 后：
- 本地分支会"记住"对应的远程分支
- Git 可以自动比较本地和远程的差异
- 推送和拉取操作可以简化，无需每次指定远程和分支名

## 方案4：设置分支的 Upstream 并推送

### 前置条件

1. 本地已初始化 Git 仓库
2. 已添加远程仓库（如 GitHub、GitLab 等）

### 完整设置步骤

#### 步骤 1：添加远程仓库（如果还没有）

```bash
# 查看当前远程仓库
git remote -v

# 如果没有远程仓库，添加一个
git remote add origin https://github.com/username/repo.git

# 或者使用 SSH 方式（如果配置了 SSH key）
git remote add origin git@github.com:username/repo.git

# 验证添加成功
git remote -v
```

#### 步骤 2：首次推送并设置 Upstream（推荐方法）

**这是最常用和推荐的方法**，一次命令同时完成推送和设置：

```bash
# 推送当前分支并设置 upstream
git push -u origin 分支名

# 例如，当前分支是 rollback-to-multithreaded
git push -u origin rollback-to-multithreaded

# 如果远程分支不存在，Git 会自动创建它
```

**参数说明：**
- `-u` 或 `--set-upstream`：设置上游分支
- `origin`：远程仓库名称（通常是 origin）
- `分支名`：要推送的分支名称

#### 步骤 3：验证 Upstream 设置

设置成功后，可以用以下命令验证：

```bash
# 方法1：查看分支详细信息（会显示 [origin/分支名]）
git branch -vv

# 方法2：查看状态（会显示与远程分支的对比）
git status -sb

# 方法3：查看分支配置
git config branch.分支名.remote
git config branch.分支名.merge
```

**成功设置的标志：**
- `git branch -vv` 输出中，分支名后面会显示 `[origin/分支名]`
- `git status -sb` 会显示类似：`## 分支名...origin/分支名 [ahead 2]` 的信息

### 为已存在的分支设置 Upstream

如果分支已经推送过，但还没有设置 upstream，有两种方法：

#### 方法 A：使用 git push（推荐）

```bash
# 推送并设置 upstream（即使远程已存在）
git push -u origin 分支名
```

#### 方法 B：使用 git branch

```bash
# 仅设置 upstream，不推送
git branch --set-upstream-to=origin/分支名 分支名

# 或者简写（如果在目标分支上）
git branch --set-upstream-to=origin/分支名
```

### 设置前后的命令对比

#### ❌ 设置前（未配置 upstream）

```bash
# 每次推送都要指定完整路径
git push origin rollback-to-multithreaded

# 每次拉取也要指定
git pull origin rollback-to-multithreaded

# 查看状态时，不会显示与远程的差异
git status
# 输出：On branch rollback-to-multithreaded
#      nothing to commit, working tree clean

# 查看分支信息，没有远程分支信息
git branch -vv
# 输出：* rollback-to-multithreaded    7478d62 commit message
```

#### ✅ 设置后（已配置 upstream）

```bash
# 只需简单的 push，Git 自动知道推送到哪里
git push

# 拉取也只需简单命令
git pull

# 查看状态时，会显示与远程分支的对比
git status -sb
# 输出：## rollback-to-multithreaded...origin/rollback-to-multithreaded [ahead 2]
#      表示本地分支领先远程分支 2 个提交

# 查看分支信息，会显示远程跟踪信息
git branch -vv
# 输出：* rollback-to-multithreaded    7478d62 [origin/rollback-to-multithreaded] commit message
```

### 常用操作示例

#### 1. 查看本地分支与远程分支的差异

```bash
# 查看领先多少提交
git status -sb

# 查看详细的提交差异
git log origin/分支名..HEAD

# 查看将要推送的提交
git log @{upstream}..HEAD
```

#### 2. 推送时自动设置 Upstream

```bash
# 如果分支名相同，可以更简单
git push -u origin HEAD

# 或者让 Git 自动匹配远程分支名
git push -u origin $(git branch --show-current)
```

#### 3. 取消 Upstream 设置

```bash
# 如果不想跟踪远程分支了
git branch --unset-upstream 分支名

# 或者简写（如果在目标分支上）
git branch --unset-upstream
```

#### 4. 更改 Upstream 分支

```bash
# 如果远程分支名改变了，可以重新设置
git branch --set-upstream-to=origin/新分支名 本地分支名
```

### 实际工作流程示例

假设你正在 `rollback-to-multithreaded` 分支上工作：

```bash
# 1. 确保已添加远程仓库
git remote add origin https://github.com/username/repo.git

# 2. 首次推送并设置 upstream
git push -u origin rollback-to-multithreaded

# 3. 之后进行开发
git add .
git commit -m "feat: 添加新功能"

# 4. 推送时只需简单命令
git push

# 5. 如果远程有更新，拉取也很简单
git pull

# 6. 查看与远程的差异
git status -sb
```

### 注意事项

1. **首次推送必须指定远程和分支名**，之后可以简化
2. **远程分支必须存在或会在首次 push 时自动创建**
3. **如果远程分支名与本地不同**，需要明确指定：
   ```bash
   git push -u origin 本地分支名:远程分支名
   ```
4. **多人协作时**，确保分支命名规范，避免冲突
5. **设置 upstream 不会自动推送**，首次设置后的推送仍需要执行 `git push`

### 常见问题

#### Q1: 为什么 `git push` 还是提示需要指定上游？

**A:** 说明还没有设置 upstream。使用 `git push -u origin 分支名` 首次设置。

#### Q2: 如何知道当前分支是否设置了 upstream？

**A:** 使用 `git branch -vv` 查看，如果分支名后面有 `[origin/分支名]` 就表示已设置。

#### Q3: 设置了 upstream 后，commit 会直接到远程吗？

**A:** **不会**。`git commit` 仍然只会提交到本地仓库。需要执行 `git push` 才会推送到远程。设置 upstream 只是让 `git push` 更方便，不会改变这个基本流程

#### Q4: 可以设置自动推送吗？

**A:** 技术上可以通过 Git Hook 实现，但**不推荐**，因为：
- 失去了审查机会
- 可能推送错误的提交
- 网络问题可能导致失败
- 违反了 Git 的设计原则（本地提交和远程推送分离）

### 多台电脑协作工作流

**✅ 是的，完全可以！** 这正是 Git 分布式版本控制的核心特性。设置 upstream 后，你可以在任意多台电脑上：
- 从同一远程仓库拉取最新代码
- 推送更新到远程仓库
- 在多台电脑间同步代码

#### 场景：在两台或多台电脑上工作

假设你有一台**电脑A**（办公室）和一台**电脑B**（家里），都使用同一个远程仓库。

##### 电脑A：首次设置（或现有项目）

```bash
# 如果是从零开始
git clone https://github.com/username/repo.git
cd repo
git checkout -b rollback-to-multithreaded
# 或者如果分支已存在
git checkout rollback-to-multithreaded

# 首次推送并设置 upstream
git push -u origin rollback-to-multithreaded

# 之后的工作流程
git add .
git commit -m "feat: 在电脑A上添加功能"
git push  # 推送到远程
```

##### 电脑B：克隆远程仓库

```bash
# 克隆整个仓库（包括所有分支）
git clone https://github.com/username/repo.git
cd repo

# 切换到需要的分支
git checkout rollback-to-multithreaded

# 如果分支还没有 upstream，设置它
git branch --set-upstream-to=origin/rollback-to-multithreaded rollback-to-multithreaded

# 或者直接推送一次（如果本地有提交）
git push -u origin rollback-to-multithreaded
```

##### 日常多机同步流程

**在电脑A上：**
```bash
# 1. 开始工作前，先拉取远程最新代码
git pull

# 2. 进行开发工作
git add .
git commit -m "feat: 在电脑A上完成功能X"

# 3. 推送到远程
git push
```

**切换到电脑B：**
```bash
# 1. 先拉取电脑A推送的最新代码
git pull

# 2. 继续开发
git add .
git commit -m "feat: 在电脑B上完成功能Y"

# 3. 推送到远程
git push
```

**再回到电脑A：**
```bash
# 1. 拉取电脑B的更新
git pull

# 2. 继续开发...
```

#### 多机协作的注意事项

##### 1. 推送前先拉取（重要！）

在推送之前，**始终先拉取远程更新**，避免推送被拒绝：

```bash
# 推荐的工作流程
git pull   # 先拉取远程更新
git push   # 再推送本地更改
```

##### 2. 处理合并冲突

如果两台电脑修改了同一文件的同一部分，可能会产生冲突：

```bash
# 拉取时如果有冲突
git pull
# 输出：Auto-merging file.txt
#      CONFLICT (content): Merge conflict in file.txt

# 查看冲突文件
git status

# 手动解决冲突（编辑文件，删除冲突标记）
# <<<<<<< HEAD
# 电脑A的代码
# =======
# 电脑B的代码
# >>>>>>> origin/rollback-to-multithreaded

# 解决冲突后
git add .
git commit -m "merge: 解决冲突"
git push
```

##### 3. 查看远程更新

```bash
# 查看远程有哪些更新（不合并）
git fetch

# 查看远程分支的更新
git log HEAD..origin/rollback-to-multithreaded

# 查看本地相对于远程的更新
git log origin/rollback-to-multithreaded..HEAD
```

##### 4. 强制推送的警告

**⚠️ 一般不要使用 `git push --force`**，除非你确定要覆盖远程分支。在多机协作中，强制推送可能导致其他电脑的工作丢失。

#### 多机协作最佳实践

1. **推送前先拉取**：`git pull` 然后 `git push`
2. **频繁推送**：避免长时间不推送，减少冲突概率
3. **清晰的提交信息**：标注在哪个环境下完成的工作
4. **使用分支**：不同电脑可以工作在不同分支上，最后合并
5. **定期同步**：每天开始工作前先拉取最新代码

#### 示例：完整的多机工作流程

**周一，在电脑A：**
```bash
git pull                                    # 确保是最新的
git checkout rollback-to-multithreaded
# ... 开发工作 ...
git add .
git commit -m "feat: 完成登录功能 [电脑A]"
git push                                    # 推送到远程
```

**周一晚上，在电脑B：**
```bash
git pull                                    # 拉取电脑A的更新
git checkout rollback-to-multithreaded
# ... 继续开发 ...
git add .
git commit -m "feat: 完成注册功能 [电脑B]"
git push                                    # 推送到远程
```

**周二，在电脑A：**
```bash
git pull                                    # 拉取电脑B昨晚的更新
git checkout rollback-to-multithreaded
# 现在你有最新的代码，包括电脑B的更改
```

### 总结

方案4（设置 upstream）的优势：
- ✅ 简化日常推送和拉取命令
- ✅ 自动显示本地与远程的差异
- ✅ 提高工作效率
- ✅ 仍然是标准的 Git 工作流（commit 本地，push 远程）
- ✅ **支持多台电脑协作**：任意多台电脑可以从同一远程仓库同步代码

**核心要点：**
- `git commit` 永远只提交到本地仓库
- `git push` 才会推送到远程仓库
- 设置 upstream 只是让 `git push` 更方便，不会改变这个基本流程
- **多台电脑可以共享同一个远程仓库**，通过 `git pull` 和 `git push` 同步代码
- 推送前先拉取，避免冲突和推送被拒绝
