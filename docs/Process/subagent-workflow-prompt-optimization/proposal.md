# Proposal: Subagent Workflow Prompt Optimization

## Problem

子Agent（web-security, email-security, binary-analysis, soc-alert）在执行分析任务时，模型自主规划的 Task List 与 SKILL.md 中定义的 Workflow 严重偏离。以 web-security 为例，模型创建了 8 步任务（包括手动读文件、grep 搜索危险函数等），而 SKILL.md 的 Workflow 只有 6 步且以工具调用为核心。

根本原因：SKILL.md 中同时存在 **YAML `workflow_steps`**（frontmatter）和 **`## Workflow`**（文本 body）两套指导，且两者内容不一致，造成认知噪音。加上 `workflow_steps` feature flag 为 `False`（程序端不消费），模型无法判断哪套是权威，最终两套都不跟，自由发挥。

## Goals

1. **消除认知噪音**：去掉无人消费的 YAML `workflow_steps`，保留唯一权威的文本 `## Workflow`
2. **约束模型行为**：将 `## Workflow` 从"建议性描述"升级为**强制 SOP**，加入明确的"必须做"和"禁止做"指令
3. **统一改动**：4 个子 Agent 的 SKILL.md + AGENT.md 全部同步优化
4. **不动代码**：纯 prompt/config 变更，不改 Python 代码逻辑（`is_skill_doc_read` 死代码除外）
5. **web-security SKILL.md 全面重构**：按 Agent Skills spec 标准优化 frontmatter（仅保留 `name` + `description`）；删除模型已知/工具已覆盖的冗余攻击模式知识（~40行）；将工具输出文档重构为紧凑表格；提升信噪比（~220行→~130行）

## Non-goals

- 不实现 `workflow_steps: True` 的程序化驱动（方向 B，留作未来考虑）
- 不改变 `detect_web_attack` 等工具的内部逻辑
- 不改变前端 Task List 的渲染逻辑
- 不清理前端 `isWorkflowStep` 类型定义（标记为后续技术债）

## Users

- 所有使用 SecManus 子 Agent 分析功能的终端用户
- 子 Agent 的 LLM 运行时（直接读取 SKILL.md 和 AGENT.md）

## Scope

| In scope | Out of scope |
|----------|-------------|
| 4 个 SKILL.md 的 YAML frontmatter 清理 | 前端渲染逻辑 |
| 4 个 SKILL.md 的 `## Workflow` 重写 | `workflow_steps` feature flag 程序化实现 |
| 4 个 AGENT.md 的行为约束加强 | 新增工具或 API |
| `app/main.py` feature flag 注释更新 | |
| `deepagents_stream_adapter.py` 删除 `is_skill_doc_read` 死代码 | |

## Dependencies

- 无外部依赖
- 需要确保 `loader.py` 在 `workflow_steps` 字段缺失时不报错（已确认：`frontmatter.get("workflow_steps", [])` 默认空列表，安全）

## Success metrics

- 模型的 Task List 步骤数 ≤ SKILL.md `## Workflow` 定义的步骤数 + 2（允许合理的上下文准备和报告写作步骤）
- 模型在调用 `detect_web_attack` / `analyze_email_headers` 等核心工具**之前**不再手动 grep/搜索文件内容
- 无 Python 测试回归（现有 pytest 全绿）

## Open questions (resolved)

| Question | Resolution |
|----------|-----------|
| YAML `workflow_steps` 是否有任何运行时消费者？ | 无。`FEATURE_FLAGS["workflow_steps"] = False`，DeepAgents `graph.py` / `skills.py` 不读取，前端 `isWorkflowStep` 从不赋值。 |
| `loader.py` 删除 `workflow_steps` 后是否安全？ | 安全。`frontmatter.get("workflow_steps", [])` 返回空列表，`WorkflowStep` 类保留但不实例化。 |
| 是否需要同步修改 `loader.py` 代码？ | 不需要。代码兼容空列表，保留 `WorkflowStep` 类避免破坏未来可能的扩展。 |
