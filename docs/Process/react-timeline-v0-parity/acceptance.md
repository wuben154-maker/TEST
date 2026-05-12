# Acceptance — `react-timeline-v0-parity`（数据与顺序）

## Metadata

- **Slug:** `react-timeline-v0-parity`
- **Updated:** 2026-03-30（Task List 分桶 + 正式回答协议）
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope

- 时间线构建纯函数、SSE 语义消费、与后端 `step` 约定；**不含** OpenSpec CLI。

## Functional criteria


| ID   | Criterion                                                                                                                                                                           | Evidence                                                                           |
| ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| A-01 | `buildReActTimeline`（或等价）对输入条目按 `**seq` 升序** 决定**用户可见块**顺序                                                                                                                          | Vitest：交错 fixture                                                                  |
| A-02 | `**type: step`** 且未被 `internal`/`visibility: debug` 过滤的条目，在输出中占 **独立块**，与 reasoning / task tool / action tool 块可任意穿插                                                                | Vitest + 一条集成流                                                                     |
| A-03 | **同一 `listBucketKey`** 下，多次 `write_todos` 对**同一任务 id** 更新状态/标题，不重复新增行（upsert）                                                                                                       | Vitest：同桶两帧，相同 id 变 status                                                         |
| A-08 | **不同 `listBucketKey`**（如不同 `subagentName`，或 `listId`/`planSessionId` 变化）在时间线上产生 **多个** Task List 块，按 `seq` 排列；**不得**把子代理列表覆盖进主列表块                                                   | Vitest：main + subagent fixture                                                     |
| A-04 | **Tool 块**不将 `tool_result.toolOutput` 序列化为用户可见正文（本阶段）                                                                                                                               | Vitest + 手动流                                                                       |
| A-05 | Tool 行展示字符串由 `**toolInput` JSON** 解析（多键 fallback 顺序见实现注释）                                                                                                                           | Vitest：多 fixture                                                                   |
| A-06 | **正式回答**仅来自 `design.md` **Flows §Reasoning vs 正式回答** 的**首选或备选**通道（独立 `type` / `displayLane` / `contentKind: 'answer'`）；**禁止**在无标识时把默认 `reasoning` 当作正式回答；避免与 Result / conclusion 双显 | `design.md` + Vitest 去重/分流                                                         |
| A-07 | 分析对话区挂载路径对旧时间线组件 **零引用**（或仅 dead code / 未使用的 export），与 `ReActTimelineView` **互斥**                                                                                                   | `rg` / CI grep 或 Code review：`AnalysisTurnPanel`（及父级）不渲染 `TimelineUnifiedBody` 等旧链 |


## Backend coordination（非阻塞前端合并，但需一致）


| ID   | Criterion                                                                                                | Evidence                  |
| ---- | -------------------------------------------------------------------------------------------------------- | ------------------------- |
| B-01 | 「委派子智能体」等里程碑由后端发 `**step`**，载荷含用户可读 `**label` 和/或 `detail**`                                             | 抓包或 pytest SSE 断言（若本仓库覆盖） |
| B-02 | 前端 **不得** 依赖硬编码中文「委派」作为唯一显示逻辑；允许 i18n **映射表**以 `label` 为 key                                             | Code review               |
| B-03 | 后端按 `design.md` 发出正式回答信号（**方案 A 或 B**）；`write_todos` 载荷含 **稳定任务 id**；子代理列表与主图 **scope/subagentName** 可分桶 | pytest / 抓包 / 与前端联调记录     |


## Sign-off


| ID        | Result | Verifier | Date | Notes |
| --------- | ------ | -------- | ---- | ----- |
| A-01–A-08 |        |          |      |       |
| B-01–B-03 |        |          |      |       |


