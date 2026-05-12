## Why

SecManus Deep Agent 已具备 LangGraph checkpointer、统一 SSE 时间线与前端对 `decision_request` / `parameter_request` 的占位处理，但**主 Agent 与子 Agent 尚未形成可恢复的 Human-in-the-loop（HITL）闭环**：危险/敏感工具缺少执行前闸门，模型主动收集表单或选择题缺少与 `interrupt`/`resume` 对齐的协议。需要在不推翻 `task()` 委托模型的前提下，区分两类需求并分别落地：**工具执行前审批**（`interrupt_on` + 官方 `HumanInTheLoopMiddleware`）与**显式向用户索取信息**（专用工具 + 自定义 `interrupt` 载荷）。

## What Changes

- 为**主 Agent**配置并打通 `HumanInTheLoopMiddleware`：通过 `create_deep_agent(..., interrupt_on=...)` 对主图可见工具按名声明审批策略；流式分析在 `interrupt` 时**有序结束或进入明确等待态**，并提供 **HTTP resume**（同一 `session_id` / `thread_id`）以 `Command(resume=...)` 或当前 LangGraph 版本等价方式续跑。
- 为**标准子 Agent**（registry → `build_subagent_specs`）扩展配置：按 subagent 或工具配置 **`interrupt_on`**，使中断发生在 **task 委托的子图内**（`after_model` 钩子），无需改写 `task` 工具体。
- 新增**专用工具**（名称待定，如 `request_user_input`）：子 Agent（及可选主 Agent）可调用以发起**表单/选择题/自由文本**类请求；工具实现使用 **`langgraph.types.interrupt` 与自定义 TypedDict 载荷**（与 `HITLRequest` 区分）；适配器将载荷映射为 SSE（复用或扩展 `parameter_request` / `decision_request`），resume 时将用户应答注入为 **ToolMessage** 或等价状态更新。
- 更新 `docs/Process/SSE_EVENT_CATALOG.md` 与 `src/types/analysis.ts`：为 HITL 等待态、resume 关联字段（如 `interruptKind`、`resumeToken`）做**可加字段**说明；**BREAKING** 若强制新版本 `schemaVersion` 则显式标注（默认优先在 v1 内前向兼容扩展）。
- **CompiledSubAgent**（如 deep-research）：在 spec 中要求**单独策略**——或在编译图内挂载等价中间件/工具，或文档声明 Phase 1 仅支持 standard registry 子 Agent 的 HITL。

## Capabilities

### New Capabilities

- `agent-hitl-orchestration`: 主 Agent 的 `interrupt_on` 配置、LangGraph interrupt/resume 与 FastAPI 入口、与现有 `/analyze` 流的关系、并发与超时策略。
- `subagent-hitl`: 子 Agent registry/YAML 对 `interrupt_on` 的声明与合并、专用 `request_user_input`（暂定名）工具 schema、自定义 interrupt 载荷与 SSE 映射、compiled 子 Agent 例外说明。

### Modified Capabilities

- （无）根目录 `openspec/specs/` 当前无已发布基线；与流协议相关的历史要求见 `openspec/changes/unify-agent-sse-timeline/specs/agent-stream-protocol/spec.md`，本变更在各自新 spec 中与之对齐而非修改该归档 change。

## Impact

- **后端**：`python-agent-service/app/agents/deep_agent.py`、`create_deep_agent` 调用、`app/main.py` 分析路由、新 resume 路由或扩展请求体、`deepagents_stream_adapter`、工具注册（`enhanced_tools` / research tools）、`subagent_registry` 与 `config/subagents.registry.yaml` schema。
- **前端**：`useStreamingAnalysis` / `useStreamingAnalysisMulti`、等待态 UI、resume 提交（新 endpoint 或同 session 的第二种操作）。
- **文档**：`SSE_EVENT_CATALOG.md`、`project_context.md`、可选 `MASTER_AGENT.md` / 子 Agent `AGENT.md` 中说明何时用审批类 vs 问答类工具。
- **依赖**：以当前 `langchain` / `langgraph` 版本为准验证 `interrupt` 与 `Command.resume` 的准确签名（实现阶段 spike）。
