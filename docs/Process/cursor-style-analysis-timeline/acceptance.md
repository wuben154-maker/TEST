# Acceptance — `cursor-style-analysis-timeline`

## Metadata

- **Slug:** `cursor-style-analysis-timeline`
- **Owner:** TBD（请填写负责签核人）
- **Updated:** 2026-03-26
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Criteria ownership (delivery-pipeline)

- **Source of truth:** **You / tech lead** — 下列 **A-** / **N-** 条为 Agent 根据探索与设计 **结构化草稿**。**非协议**：请按真实契约删减或增补，并保持 id 稳定。
- **Agent role:** 仅维护表格结构与可验证性（Given/Verification）；**不得**在 Phase 4 无用户要求时重写全文。

## Scope

本验收覆盖 **客户端 timeline → TraceRow 行模型** 的行为与回归，补充 UI 验收无法自动化的 **确定性规则**：

- `timelineToTraceRows`（或等价纯函数）的合并、打断与锚点逻辑。
- **同一输入事件序列** 在 **流式结束** 与 **历史回放** 下输出行序列一致（在 design 约定范围内）。

不包含：后端 LangGraph 拓扑变更、SSE 字段新增（除非另行开需求）。

## Environment

- **Runtime:** 本地 `pnpm`/`npm` dev + 单元测试（Vitest/Jest 以仓库为准）。
- **Feature flags:** 若实现使用 flag，在此列出；默认 **本地 dev 开启新轨迹** 以便测。
- **Data:** 使用 fixture 数组 `AnalysisTimelineEntry[]`（可来自 golden JSON）。

## Functional criteria


| ID   | Criterion                                                                                                                                       | Verification                         |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ |
| A-01 | **相邻**两条 Read 类 `tool_line`（同规范化 path）中间 **无其它 row** 时，合并为 **一条** `tool_line`                                                                   | `timelineToTraceRows.test.ts` 用例名或等价 |
| A-02 | 在 Read 合并后若中间插入 **写路径类** 工具（design 中 BREAK_TOOLS 列表之一），后续 Read **不**与之前合并                                                                       | 同上                                   |
| A-03 | **子代理**边界产生 **恰好一行** `delegation_line`；其后 `tool_line`/`text` 与主流程 **相同 kind 集合**（无仅 subagent 才有的包裹 row）                                         | 单测 fixture + 可选组件快照                  |
| A-04 | 首次 `task_plan`/`task_create`（或 design 约定首事件）插入 **单个** `task_block` 锚点；后续 `task_update` **更新同一锚点** 内列表，**不**新增第二个并列 task_board（同 `anchorKey` 语义） | 单测                                   |
| A-05 | 未知 `toolName` 仍产出 **一条** `tool_line`（generic 模板），不抛错、不中断列表                                                                                      | 单测                                   |
| A-06 | **相同** `events[]` 输入 reducer **两次**，输出 `rows` 的 **kind 序列与关键 id** 一致（确定性，不含随机）                                                                  | 单测 snapshot 或 deep equal             |
| A-07 | 对任意 fixture，`TraceRow[]` 按 **`seq`（或合同规定的 `sortKey`）严格非降序**；合并行继承明确序规则并在注释与测试中固定 | `timelineToTraceRows.test.ts` |
| A-08 | `decision_request`：`allowMultiple=false` → `hitlKind=decision_single`；`true` → `decision_multi`；`parameter_request` → `parameter_form` | `timelineToTraceRows.test.ts` |

## Non-functional criteria


| ID   | Criterion                                                      | Verification          |
| ---- | -------------------------------------------------------------- | --------------------- |
| N-01 | Reducer 对 **1k 级**事件数组在本地测试耗时 **可接受**（如 < 50ms 量级，依 CI 机器调整阈值） | 可选 perf test 或手动 note |
| N-02 | 新模块 **不**引入 `any` 滥用；公共导出类型与 `AnalysisTimelineEntry` 兼容层有注释    | Code review / lint    |


## Evidence notes

- A-01～A-08：**粘贴测试文件路径 + 用例名**；CI green 即证据。
- 回放一致性（若与 A-06 分开）：可在 `buildConversationMessages` 或存储层加一条集成测试（若 scope 内实现）。

## Sign-off


| ID   | Result | Verifier | Date | Notes |
| ---- | ------ | -------- | ---- | ----- |
| A-01 |        |          |      |       |
| A-02 |        |          |      |       |
| A-03 |        |          |      |       |
| A-04 |        |          |      |       |
| A-05 |        |          |      |       |
| A-06 |        |          |      |       |
| A-07 |        |          |      |       |
| A-08 |        |          |      |       |
| N-01 |        |          |      |       |
| N-02 |        |          |      |       |


