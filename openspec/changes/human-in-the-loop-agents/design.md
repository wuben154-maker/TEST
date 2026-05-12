## Context

- 主 Agent 由 vendored `create_deep_agent` 构建，工具含文件系统、`execute`、`task` 等；`checkpointer` 已接 Postgres / Memory，`thread_id` 与业务 `session_id` 对齐。
- 子 Agent 由 `SubAgentMiddleware` 注入 `task` 工具，registry（`build_subagent_specs_from_registry`）产出 SubAgent dict；`SubAgentMiddleware._get_subagents` 已支持 per-spec `interrupt_on` → `HumanInTheLoopMiddleware`。
- LangChain `HumanInTheLoopMiddleware` 在 `after_model` 对指定工具名的 `tool_calls` 调用 `langgraph.types.interrupt(HITLRequest)`，resume 需返回 `decisions` 列表（approve / edit / reject）。
- 前端已有 `decision_request` / `parameter_request` 事件处理，但缺少与 **图级 interrupt + resume** 绑定的闭环。
- `docs/Process/SSE_EVENT_CATALOG.md` 与 `unify-agent-sse-timeline` 变更定义了 canonical SSE；HITL 应在同一套类型上扩展载荷，避免平行协议。

## Goals / Non-Goals

**Goals:**

- 主 Agent：对选定工具使用 `interrupt_on`，执行前可审批/编辑/拒绝；流可感知等待态；同一 session 可 resume。
- 子 Agent：**危险/敏感工具**仅用 `interrupt_on`（与主 Agent 同一中间件语义，发生在 task 子图内）。
- 子 Agent（及可选主 Agent）：**主动收集信息**通过**专用工具** + **自定义 interrupt 载荷**（非 `HITLRequest`），映射到 `parameter_request` / `decision_request` 或文档化的新子类型。
- 文档化 compiled subagent（如 deep-research）的 HITL 策略与限制。

**Non-Goals:**

- 多人审批工作流、角色权限矩阵（可留后续）。
- 替换 `task()` 为显式父图节点（A 方案）；本设计以 B/C + `interrupt_on` 为主。
- 修改 LangGraph / LangChain 上游源码（仅 vendored 补丁若绝对必要，需在 tasks 中单列评审）。

## Decisions

### D1 — 主 Agent：`create_deep_agent(interrupt_on=...)`

- **选择**：在 `DeepAgentWithIntent._build_official_agent` 传入 `interrupt_on`，来源为 settings 或静态映射（如 `execute`、`edit_file`、`write_file` 等按环境分级）。
- **理由**：与官方 deepagents `graph.py` 一致——同时作用于主 Agent middleware 与 general-purpose 子 Agent 的 gp_middleware；主图工具与「内建危险工具」统一策略入口。
- **备选**：仅在自定义 middleware 中手写 interrupt — 重复实现 `HumanInTheLoopMiddleware` 行为，维护成本高。

### D2 — 子 Agent：registry 扩展 `interrupt_on`

- **选择**：在 `subagents.registry.yaml`（或并行 defaults 文件）为每个 entry 增加可选 `interrupt_on`；`build_subagent_specs_from_registry` 合并进 SubAgent dict。
- **理由**：`SubAgentMiddleware._get_subagents` 已读取 `spec.get("interrupt_on")`；无需改 `atask` 体。
- **备选**：全局一份 YAML 映射 `subagent_id -> interrupt_on` — 适合全站统一，但弱化 per-agent 差异；可二期合并。

### D3 — 专用工具 C：单一 `request_user_input`（名称可最终定）

- **选择**：注册结构化工具，参数包含 `kind`（如 `choice` | `form` | `text`）、`prompt`、`options?`、`fields?`、`request_id?`；实现内 `interrupt(UserInputRequestPayload)`；resume 值为 `UserInputResponsePayload`（含 `answers` / `selected` / `cancelled`）。
- **理由**：与「模型主动问人」语义一致；载荷与 `HITLRequest` 分离，前端可按 kind 渲染不同 UI。
- **备选**：全靠 `interrupt_on` — 无法表达任意表单，仅能审批已有 tool call。

### D4 — Resume API

- **选择**：新增 `POST /analyze/resume`（或 `/agent/resume`）body：`session_id`、`resume` 对象（与 LangGraph `Command(resume=...)` 对齐；需 spike 确认嵌套子图时 `checkpoint_ns`）。鉴权与 `/analyze` 一致。
- **理由**：与「新用户消息」分离，避免误触发新 turn；便于前端显式「提交审批/表单」。
- **备选**：复用 `POST /analyze` 加 `mode: resume` — 可接受，需在 spec 中二选一并统一。

### D5 — SSE 映射

- **选择**：`HumanInTheLoopMiddleware` 触发的 interrupt：适配器从 graph stream 的 `__interrupt__`（或当前 API 等价物）读取 `HITLRequest`，发出 `decision_request`（或 dedicated `hitl_tool_review` 若需避免与 C 混淆 — 优先复用 `decision_request` 并扩展 payload）。
- **选择**：专用工具 C：发出 `parameter_request`（表单）或 `decision_request`（选择题），载荷含 `interruptKind: user_input_v1` 便于客户端分支。
- **理由**：对齐现有目录与 hooks；减少新 `type` 数量。

### D6 — Compiled subagent

- **选择**：Phase 1 文档声明 deep-research 等 **不**从 registry 继承 `interrupt_on`；若需 HITL，在 `build_open_deep_research_compiled_subagent` 编译链中显式加入 middleware 或工具（单独 task）。
- **理由**：`CompiledSubAgent` 路径忽略 spec 上的 `interrupt_on`（当前代码行为）。

## Risks / Trade-offs

- **[Risk] 嵌套图 interrupt 的 checkpoint_ns 与 resume 错位** → Mitigation：实现前用最小图 + task 内子 agent + Postgres checkpointer 做 spike；集成测试覆盖「主图等待 + resume 后继续 task」。
- **[Risk] SSE 长连接在 interrupt 时未正确关闭导致前端状态错乱** → Mitigation：`done` 与 `awaitingHuman` 语义在 spec 中固定；前端单 session 单 open interrupt。
- **[Risk] 模型滥用 `request_user_input`** → Mitigation：prompt 约束 + 速率限制可选；日志审计。
- **[Trade-off]** `interrupt_on` 仅覆盖「已声明工具名」；新增工具默认不拦截，需配置清单同步更新。

## Migration Plan

1. 默认 `interrupt_on` 为空或仅 dev 环境启用，避免生产突然全量停工具。
2. 发布顺序：后端 resume + 适配器 → 前端等待态 → registry YAML → 收紧生产 `interrupt_on`。
3. Rollback：关闭 feature flag / 清空 `interrupt_on` 配置；旧客户端未发 resume 时超时策略返回友好错误。

## Open Questions

- LangGraph 当前锁定版本下，`Command(resume=...)` 与 subgraph 的精确 payload（是否需 `checkpoint_ns`）以 spike 为准。
- `request_user_input` 是否暴露给主 Agent（除子 Agent 外）由产品决定；设计允许两路注册。
- 是否与现有 `parameter_callbacks` 表整合用于跨进程 resume（当前单实例可仅用 checkpoint）。
