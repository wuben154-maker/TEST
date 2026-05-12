## Why

主 Agent 的分析流与任务 UI 呈现为「固定阶段流水线」（思考 → 探索 → 任务 → 结果），与 LangGraph 实际的 **多轮「推理 ↔ 工具」循环** 不同构；同时子 Agent 经队列合并后事件类型与主路径不一致，前端将 `skill_*` 等压成泛化 `step`，导致信息发散、难以循环展示。需要在 **后端 SSE 协议** 与 **前端归并与展示** 上统一建模，并对子 Agent 输出做与主 Agent 同构的 **白名单化** 与降噪。

## What Changes

- 定义 **规范 SSE 事件信封**（版本、作用域 `main`/`subagent`、任务/运行关联、顺序号或轮次、用户可见 `kind` + `payload`），主图与子图适配层 **仅产出该集合内的类型**（或映射旧类型为规范类型）。
- 调整主适配器策略：在 **不重复最终结论** 的前提下，支持 **工具调用之后多轮** 的推理增量对用户可见（与当前「首个 tool 后 largely 不再发 reasoning」的行为解耦）。
- 子 Agent 桥接（含 `subagent_sse_event_queue`、研究子图等）**映射到与主 Agent 相同的 `kind`**，差异仅体现在 `scope` / `parentTaskId` / `subagentName` 等字段；禁止将无关内部日志作为用户可见事件透出。
- 前端引入 **单一时间线归并**（或等价数据结构），`ReasoningPanel` / `StreamEventRenderer` / `thinkingSteps` 从同源消费；移除或废弃「将 `skill_reasoning` 等统一改写为 `type: step`」导致语义丢失的做法。
- **UI 循环**：每轮 **Thinking（动画+时长，必有）→ Reasoning（可选，视模型是否有 reasoning 事件）→ 工具执行**，可重复多轮；无 reasoning 时不展示 reasoning 区域。
- **持久化**：会话与进度存储 **仅采用新形状**（规范 `timeline` JSONB 或 migration 中定义的单一结构），**不**为旧版 `thinking_steps` + `__extended` 保留加载逻辑。**可选** 提供 Supabase/PostgreSQL migration 增加新列并迁移数据；**开发环境可直接清空相关表**（`messages`、`project_analysis_progress` 等），无需兼容旧行。

## Capabilities

### New Capabilities

- `agent-stream-protocol`：分析流式 API（`POST /analyze` SSE）的规范事件模型、主/子 Agent 对齐规则、降噪与调试事件分级。
- `reasoning-timeline-ui`：工作台对话区对规范事件的归并、按时间顺序的循环展示（推理与工具交替）、子任务嵌套展示与 Dev 模式。

### Modified Capabilities

- （无）仓库根目录 `openspec/specs/` 下尚无已归档的同名全局规范；本变更以新增能力规范为主。

## Impact

- **后端**：`python-agent-service/app/parsers/deepagents_stream_adapter.py`、`adapt_subagent_astream_to_skill_events`、研究子图/任务工具注入队列处、相关 `pytest`。
- **前端**：`src/hooks/useStreamingAnalysisMulti.ts`（及必要时 `useStreamingAnalysis.ts`）、`src/types/analysis.ts`、`src/components/reasoning/*`、`StreamEventRenderer` / `ThinkingChain` / `CommandCenter` 数据流。
- **文档与类型**：可选增加 `docs/` 下 SSE 协议简述；实现后更新 `project_context.md`。
- **数据库**：可选 migration；dev 清表策略见 `design.md`。
- **测试**：适配器单测、前端归并逻辑单测或组件测（按 AGENT.md TDD 在实现阶段执行）。
