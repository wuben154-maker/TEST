---
name: pre-pr-sync
description: |
  提交 PR 前的分支同步与冲突处理。自动将 origin/<pr-base> fetch 并 rebase 进当前 feature 分支，
  检测冲突后分级引导解决（无冲突自动通过），验证工作区干净、无冲突标记后输出"可执行 pr-commit-with-review"信号。
  触发词："同步分支"、"合并主线"、"解决冲突"、"pre-pr-sync"、"提PR前准备"、"pre pr sync"。
---

# Pre-PR 同步（pre-pr-sync）

在执行 `pr-commit-with-review` 之前，将集成分支 `origin/<pr-base>` 的最新变更合入当前 feature 分支，并验证结果干净可用。

---

## 项目配置

**统一配置入口：** `.cursor/project-config.md`，在该文件的 `## Git Workflow` 表格中修改 `PR_BASE`，此处不维护副本。

Agent 在 Step 0 读取 `.cursor/project-config.md § Git Workflow` 中的 `PR_BASE`，所有出现 `<pr-base>` 的地方均使用该值。

**运行时覆盖：** 若用户在调用时明确指定了目标分支（如"同步到 release/v2"），本次运行使用该值，文件不修改。

---

## Step 0 — 预检

1. `git branch --show-current` → 记为 `<head>`
   - 若为空（detached HEAD）→ **停止**，提示用户切换到 feature 分支
2. 解析 `<pr-base>`：
   - 若用户本次调用明确指定了目标分支 → 使用该值
   - 否则 → 读取 `.cursor/project-config.md § Git Workflow` 中的 `PR_BASE`
   - 打印 `<pr-base>` 及其来源（配置 / 运行时覆盖）
3. 若 `<head>` 等于 `<pr-base>` → **停止**，警告不应在集成分支上直接操作
4. `git status` → 若有未提交的修改：
   - 提示用户先 `git stash` 或提交，**不自动 stash**（避免覆盖用户意图）
5. `git fetch origin --quiet` → 拉取最新远端状态
   - 若 `origin/<pr-base>` 不存在 → **停止**，提示检查 `PR_BASE` 配置或远端状态

---

## Step 1 — Rebase 集成分支

```bash
git rebase origin/<pr-base>
```

- **无冲突** → 自动进入 Step 3（验证）
- **有冲突** → 进入 Step 2（冲突处理）

> 选用 rebase 而非 merge：使 feature 分支历史保持线性，PR diff 更清晰。
> 若用户明确要求 merge，改用：`git merge origin/<pr-base>`

---

## Step 2 — 冲突处理（仅在有冲突时执行）

### 2a. 展示冲突清单

```bash
git diff --name-only --diff-filter=U
```

列出所有冲突文件，并对每个文件说明冲突区域（`<<<<<<<` 位置）。

### 2b. 分级处理策略

| 冲突类型 | 判断依据 | 建议操作 |
|---------|---------|---------|
| **格式/空白冲突** | 两侧代码语义相同，仅缩进/换行不同 | 取 `--ours`，说明理由 |
| **非重叠修改** | 双方改了同一文件的不同区域 | 两侧都保留，手动合并后确认 |
| **逻辑冲突** | 同一逻辑被两侧不同修改 | **必须人工判断**，不自动选边 |

> **重要原则：对逻辑冲突绝不自动取舍。** 列出冲突内容，提供选项让用户决定。

### 2c. 解决完成后继续 rebase

```bash
git add <已解决的文件>
git rebase --continue
```

若用户放弃：

```bash
git rebase --abort
```

---

## Step 3 — 验证

依次执行以下检查，全部通过才输出"就绪"信号：

```bash
# 1. 工作区应干净
git status

# 2. 无残留冲突标记
git diff HEAD | grep -E "^(\+.*<<<<<<<|\+.*=======|\+.*>>>>>>>)"
# 若有输出 → 报错，提示哪个文件还有冲突标记

# 3. 确认已领先 origin/<pr-base>（有自己的提交）
git log --oneline origin/<pr-base>..HEAD
```

**可选：运行项目测试**（若 `.cursor/project-config.md § Test` 中 `TEST_CMD` 已设置）：

```bash
# 读取 TEST_CMD 后执行，例如：npm test / pytest / go test ./...
# 若 TEST_CMD 为 (unset)，跳过此步，不报错
```

若验证全部通过，输出：

```
✅ pre-pr-sync 完成
   分支：<head>
   PR 目标（pr-base）：<pr-base>
   领先 origin/<pr-base>：N 个提交
   工作区：干净，无冲突标记
   → 可执行 pr-commit-with-review
```

---

## 中止与回滚

| 情况 | 操作 |
|------|------|
| rebase 中途想放弃 | `git rebase --abort` |
| 已 rebase 但想撤销 | `git reset --hard ORIG_HEAD`（仅限本地未 push） |
| 已 force-push 后想回退 | 需人工处理，**此 skill 不执行** |

---

## 与其他 skill 的衔接

```
pre-pr-sync（本 skill）
      ↓ 验证通过
pr-commit-with-review
      ↓ PR 创建成功
land-and-deploy（可选）
```
