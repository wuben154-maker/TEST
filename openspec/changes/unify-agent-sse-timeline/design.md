## Context

- **当前状态**：`adapt_astream_to_sse` 将 LangGraph 流映射为多种 SSE `type`；主 Agent 对 `reasoning` 的发出受 `saw_first_tool_call` 等门控约束，易表现为「首轮思考后只见工具与任务」。子 Agent 经 `subagent_sse_event_queue` 合并并 `_tag_merged_subagent_sse` 打标，事件形态与主路径不完全一致。
- **前端**：`useStreamingAnalysisMulti` 将 `skill_*` / `workflow_step` 等合并进 `thinkingSteps` 时改写为 `type: 'step'`，与 `reasoning`、`streamEvents` 并行，导致展示流水线化、子路径语义稀释。
- **约束**：产品未对外发布，**仅支持新协议与新持久化形状**，不维护旧客户端/旧行数据兼容；须遵守 AGENT.md（TDD、英文代码注释）；用户可见文案走 i18n。

## Goals / Non-Goals

**Goals:**

- 主、子 Agent **用户可见事件** 共享同一套 **canonical `type`（kind）** 与 **信封字段**，仅通过 `scope` / 关联 id 区分层级。
- 支持 **多轮推理增量** 在工具调用之后仍可展示，并与 `conclusion` **去重**（不两次全文展示最终答案）。
- 前端以 **单一有序 timeline** 为源，驱动现有面板组件或轻量重构后的组件。
- **展示语义（每轮循环）**：**Thinking**（加载动画 + 已用时间）在模型工作或等待下一事件时 **必须出现**；**Reasoning**（可折叠文本）**仅在有 reasoning 增量时**展示——无 reasoning 的模型跳过该段，不预留空壳；随后进入 **工具执行**（`tool_call` / `tool_result` 等）。多轮则为 **Thinking → [Reasoning] → 工具 → Thinking → …** 直至 `conclusion` / 结束。
- 调试类事件与生产 UI **分级**。

**Non-Goals:**

- 不改变非流式 `ainvoke` 业务契约（除非为修复一致性所必需）。
- 不为已弃用的 `thinking_steps` 数组 + `__extended` 包一层保留解析（除可选一次性 DB migration 脚本外）；**开发环境可直接清表**（见 Migration Plan）。
- 不重新定义租户级 Skill 模型（与 `agent-skill-tenancy-capability-model` 变更正交）。

## Decisions

### D1: Canonical kind 命名与首版集合

- **决策**：`schemaVersion: 1` 为当前**唯一**支持的流式协议版本；`type` 字符串尽量沿用现有稳定值并 **叠加** 信封字段（`seq`, `scope` 等），避免无意义改名。
- **理由**：团队内单一代码路径；产品未发布，无需双发或旧客户端忽略未知字段的兼容故事。
- **备选**：若未来对外部集成开放，再单独定义版本协商；本变更不实现。

### D2: 顺序字段 `seq`

- **决策**：由适配器在 **单次 SSE 连接** 内维护递增整数 `seq`，所有主/子合并事件共用。
- **理由**：前端无需依赖时钟；合并队列与主循环交错时顺序明确。
- **备选**：仅用时间戳——多源并发下不可靠。

### D3: 多轮 `reasoning` 与 `conclusion` 去重

- **决策**：将「意图阶段一次性 reasoning」与「工具后 synthesis」区分：`reasoning` 仅承载 **增量可展示推理**；最终面向用户的完整答案 **仅** 通过 `conclusion`（及既有 `task_summary` 等）发出。适配器在发出 `conclusion` 前对已与 `conclusion` 重叠的 reasoning 缓冲做 **哈希/后缀裁剪**（具体启发式在实现任务中细化并配测试）。
- **理由**：对齐当前「不把最终答案当 reasoning」的意图，同时放开工具后的中间推理。
- **备选**：按 `turn` 分桶多个 reasoning 块——可作为 v2 增强，首版可用 `seq` 顺序表达。

### D4: 子 Agent 映射层

- **决策**：在 **单一点**（如 `_tag_merged_subagent_sse` 之后或研究桥接出口）将 `skill_reasoning` 等 **映射** 为 `reasoning`，`skill_start`/`skill_complete` 映射为 `step` 或 **新的** `lifecycle` kind（若与 `task_step` 冲突则在 tasks 中二选一并写死）。
- **理由**：单一映射表便于审计「用户可见白名单」。
- **备选**：各子图各自改——易再次发散。

### D5: 前端归并位置

- **决策**：在 `useStreamingAnalysisMulti`（及废弃路径若仍需修复）内实现 `reduceEventToTimeline(prev, ev)`，输出 `timeline: TimelineItem[]`；`ReasoningPanel` 接收 `timeline` 或由其派生的切片，逐步废弃并行且语义丢失的 reducer 分支。
- **理由**：一处归并，避免 CommandCenter 再排序。

### D6: Thinking 与 Reasoning 解耦

- **决策**：**Thinking** 由前端根据 **「分析进行中且当前轮次尚未收到下一块可见增量」** 驱动（或显式 `step`/heartbeat，若后续补充），与是否收到 `reasoning` 事件无关。**Reasoning** 仅绑定 `reasoning`（及映射后的等价）事件；无事件则不渲染 reasoning 区块。
- **理由**：部分模型不提供可展示的 reasoning 通道；用户仍需看到「在工作」的反馈（动画 + 时长）。
- **备选**：后端发空 `reasoning` 占位——增加噪音，不采用。

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| 放开工具后 reasoning 导致与 `conclusion` 重复 | 去重测试用例 + 缓冲上限防止超大流 |
| `seq` 与重连/续传 | 文档约定「每次请求独立计数」；持久化用服务端存储时需另议 |
| 时间线项过多导致性能差 | 虚拟列表、折叠旧 turn、Dev 全量 |
| 本地已有脏数据 | **Dev**：`TRUNCATE`/删除 `messages`、`project_analysis_progress` 等相关行即可；若有不能丢的数据则用可选 migration |

## Migration Plan

**持久化：仅新格式 + 可选 DB migration**

1. **Schema（可选 migration）**：在 `messages`（及需对齐的 `project_analysis_progress` 等）增加 **`timeline` JSONB**（或等价：用单一列存规范时间线数组），写入/读取只认该形状；逐步停止依赖 `thinking_steps` 内嵌 `__extended` 的补丁模式。是否 `DROP`/废弃旧列由 migration 脚本单独说明。
2. **开发环境**：无需迁移历史；对本地/开发库执行 **清表** 即可，例如清空 `messages`、`project_analysis_progress`（及团队约定的关联数据），避免旧行被加载。**生产前**若已有数据再跑可选 migration 或一次性导出后重建。
3. **实现顺序**：后端 SSE 信封与归一 → 前端 `timeline` 单源 → `message_persistence` / `messages` API / `useProjects` 加载逻辑改为读写新列 → 删除旧归并与双写分支。
4. 文档更新 `project_context.md` 与可选 `docs/` SSE + 持久化简述。

**Rollback**：以 Git 回退为准；不承诺运行时切回旧协议（非目标）。

## Open Questions

- `step` 与 `workflow_step` 是否在 v1 合并为单一 canonical 类型（需对照 `labels.py` 与前端 Dev 面板）。
- 共享报告 / 只读链接是否必须重放完整 timeline，还是仅摘要（影响持久化字段）。

### Resolved: `turn`（ReAct 周期）

- **实现**：`app/parsers/react_turn.py` 中 `ReactTurnTracker`；主 Agent `adapt_astream_to_sse`、子 Agent `adapt_subagent_astream_to_skill_events`（与主 SSE 合并时经 `_tag_merged_subagent_sse`）、research 队列（`open_deep_research_compiled`）、vendor `subagents._ainvoke_subagent_with_sse_queue`、`task_planner._execute_subagent_task` 均通过 `attach_turn_to_event` 写入 `turn`。
- **语义**：同一轮 Think（流式多条 `reasoning`）与紧随其后的 Act（`tool_call` / `tool_result`）共享同一 `turn`；`tool_result` 后为下一轮 Think 递增。并行多个 `tool_result` 只递增一次（pending 覆盖）。
- **前端**：`aggregateReasoningSegmentsFromTimeline` 默认 `scope: main`，仅按 `reasoning` 上的 `turn` 分段；缺省 `turn` 视为 `0`。子 Agent 时间线内 `mergeSubagentReasoningByTurn` 合并同 `turn` 的连续 reasoning。
- **文档**：`docs/Process/SSE_REACT_TURN.md`。
