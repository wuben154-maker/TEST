# Issue 1：构建器 — 给委派类 block 标记 `subagentId` 与 `delegationDepth`

**类型**：AFK  
**阻塞**：无，可立即开始  
**父文档**：[prd.md](./prd.md)

---

## What to build

在 ReAct 时间轴构建器中追踪「当前活跃子 Agent」上下文，并将其写入两类 block 的字段，使渲染层可直接读取而无需按顺序推断。

端到端行为：给定一段包含 `scope: 'subagent'`、带委派信封字段（`delegationDepth`、`rootDelegationId`）的时间轴事件序列，`buildReActTimeline` 输出的 block 数组中：

- `delegation_group` 类型的 `ReActStepBlock` 携带 `subagentId`（值为子 Agent 技术标识符，如 `email-security`）；
- 紧随其后 flush 出的 `ReActToolExecutionBlock` 携带相同的 `subagentId` 和对应的 `delegationDepth`；
- 当事件流返回主图（`scope: 'main'`）后 flush 的 `ReActToolExecutionBlock`，`subagentId` 为 `undefined`。

---

## Acceptance criteria

- [ ] `ReActStepBlock` 类型新增可选字段 `subagentId?: string`
- [ ] `ReActToolExecutionBlock` 类型新增可选字段 `subagentId?: string` 和 `delegationDepth?: number`
- [ ] `buildReActTimeline` 主循环新增 `currentSubagentId: string | null` 跟踪变量，在插入 `delegation_group` banner 时更新，遇到主图 `llm_invoke_start` 或其他主图触发 flush 时清空
- [ ] `flushTools()` 将 `currentSubagentId` 和最近一次 `delegationDepth` 写入推送的 `tool_execution` block
- [ ] 新增测试：`delegation_group` step block 的 `subagentId` 等于事件的 `subagentName`
- [ ] 新增测试：depth=1 子 Agent 后 flush 的工具块 `subagentId` 正确、`delegationDepth === 1`
- [ ] 新增测试：depth=2 嵌套子 Agent 的工具块 `delegationDepth === 2`
- [ ] 新增测试：主图工具块 `subagentId` 为 `undefined`
- [ ] 新增测试：legacy 行（仅有 `subagentName`、无委派信封）flush 的工具块 `subagentId` 为 `undefined`
- [ ] 所有现有 `buildReActTimeline` 测试继续通过

---

## Blocked by

无 — 可立即开始
