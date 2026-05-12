---
name: merge-branch-safely
description: 安全地将一个 Git branch merge 进另一个 branch，处理明确的 merge conflict，运行验证并汇报结果。适用于用户要求合并分支、将 feature branch 同步进 dev-for-master/main/master、处理 merge conflict，或提到「合并分支」「解决冲突」「merge branch」「merge conflict」「sync branch」等场景。
---

# Merge Branch Safely（安全合并分支）

当用户希望将一个 Git branch 合并进另一个 branch，并期望 assistant 协助处理 conflict 与验证时，使用本 workflow。

## 必填输入（Required Inputs）

在动手改代码前先确认或推断：

- **Source branch**：要被并入的分支（变更来源）。
- **Target branch**：接收变更的分支。
- **Push policy**：默认不 push，除非用户明确要求。
- **Commit policy**：仅在本次请求的 merge 流程内允许创建 merge commit；不要产生无关 commit。

若任一 branch 不明确，先询问再继续。

## 安全规则（Safety Rules）

- 除非用户明确要求并确认，否则不要执行破坏性 Git 命令，例如 `git reset --hard`、`git checkout -- <path>`、`git clean`、`git push --force` 或 `--force-with-lease`。
- 默认不要 rebase；除非用户要求 rebase 流程，否则使用 merge。
- 除非用户明确要求 push，否则不要 push 到 remote。
- 若 `git status --porcelain` 显示与用户无关或未提交的改动，在 merge 前先停下。
- 不要提交 secret 或本地环境文件。将 `.env`、凭证、私钥、生成缓存、本地上传等视为高风险。
- 若 target branch 领先于其 upstream，在 push 前说明「本地 commit 会被一并推送」。
- 若 remote 上的 target branch 已前进，优先在 target branch 上使用 `git pull --ff-only`。若无法 fast-forward，停下并询问用户。
- 保留用户改动；不要撤销并非为本次 merge 有意修改的文件。

## Workflow（流程）

1. **检查仓库状态**
   - 运行 `git status -sb` 与 `git status --porcelain`。
   - 用 `git branch --show-current` 确认当前 branch。
   - 确认 source 与 target 在本地或 remote 存在。
   - 运行 `git branch -vv --list <source> <target>` 查看 upstream tracking。

2. **Fetch remote refs**
   - 运行 `git fetch origin`。
   - 本流程中不要 prune、删除 branch 或改写历史。

3. **对比分支**
   - 运行 `git log --oneline --decorate --left-right <target>...<source>`。
   - 运行 `git diff --stat <target>...<source>`。
   - 若 diff 很大或触及敏感文件，merge 前先概括预期影响。

4. **准备 target branch**
   - 用 `git switch <target>` 切换到 target。
   - 若 target 跟踪 `origin/<target>`，除非仅有本地 commit 或非 fast-forward 状态需要用户确认，否则运行 `git pull --ff-only origin <target>`。

5. **Merge**
   - 运行 `git merge --no-ff <source>`。
   - 若成功，进入验证步骤。
   - 若出现 conflict，查看 `git status --short` 与冲突文件。

6. **解决 conflict**
   - 仅当从邻近代码、branch 历史、测试或文件职责能明确意图时，自动解决 conflict。
   - 涉及语义取舍、大块删除、migration、认证/安全代码、环境/配置文件、lockfile、生成物或 public API contract 的 conflict，解决前先问用户。
   - 优先在兼容的前提下保留双方改动并调整集成代码，而非盲目选一侧。
   - 每解决完一个文件，确保 conflict marker 已清除。

7. **完成 merge commit**
   - 仅 stage merge 解决所必需的文件。
   - 尽量使用默认的 merge commit message。
   - 若需要自定义 message，保持简短并说明 source 与 target branch。

8. **Verify（验证）**
   - 针对改动区域运行最相关的测试。
   - 本仓库中若改动 Python agent 相关代码，优先在 `python-agent-service` 内运行 `python -m pytest`。
   - 若有前端改动，在仓库已有命令的前提下运行对应 build 或 test。
   - 若因缺少依赖或服务无法运行验证，清楚说明阻塞原因。

9. **Final report（最终汇报）**
   - 说明 source branch、target branch 以及最终 commit 状态。
   - 概括已解决的 conflict 及需要判断的文件。
   - 汇报验证命令与结果。
   - 说明是否已 push；若未 push，仅在有用时给出精确的 push 命令。

## Stop And Ask（停下并询问）

在以下情况停下并询问用户：

- merge 前 working tree 不干净。
- 任一分支缺失或存在歧义。
- `git pull --ff-only` 失败。
- conflict 解决需要产品、安全、数据模型、migration 或 API contract 层面的判断。
- 测试因与 merge 无关的原因失败且修复不明显。
- 下一步需要 push 到 protected branch，或必须使用破坏性命令。
