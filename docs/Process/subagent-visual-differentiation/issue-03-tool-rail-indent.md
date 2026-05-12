# Issue 3：工具执行组 — 彩色左导轨 + 嵌套深度缩进

**类型**：AFK  
**阻塞**：Issue 1  
**父文档**：[prd.md](./prd.md)

---

## What to build

在 `ReActTimelineView` 中，让归属于某个子 Agent 的工具执行组（`ToolExecutionBlockView`）在外层包裹一条与头部同色的彩色左导轨，并随嵌套深度向右缩进，使工具行的视觉归属与 `delegation_group` 头部保持视觉上的垂直对齐。

端到端行为：当用户看到「🔵 二进制分析」头部（蓝色，depth=2，缩进 12px）后，紧随其后的 `file_identify`、`document_extract` 工具 pill 左侧有一条蓝色竖线，且整组缩进 12px 与头部文字对齐；属于主 Agent 的工具组无彩色导轨、无额外缩进。

---

## Acceptance criteria

- [ ] `ToolExecutionBlockView` 新增可选 props：`subagentId?: string`、`indentPx?: number`
- [ ] 当 `subagentId` 有值时，现有 pill 列表外层包裹 `<div style={{ marginLeft: indentPx ?? 0 }} className={cn('border-l-2 pl-2', borderClass)}>`，`borderClass` 查 `SUBAGENT_ACCENT`（与 Issue 2 共用同一常量），未知 id 使用 `border-border/40`
- [ ] 当 `subagentId` 为 `undefined` 时，`ToolExecutionBlockView` 渲染与现有完全一致（无包裹层、无额外缩进）
- [ ] `ReActTimelineView` 主渲染循环向 `ToolExecutionBlockView` 传递 `block.subagentId` 和 `indentPx`，其中 `indentPx = (block.delegationDepth - 1) * 12`（depth=1 时为 0，即顶格）
- [ ] depth=2 的 `binary-analysis` 工具组缩进 12px，与头部文字水平起点对齐（人工验证）
- [ ] 现有 pill 的展开/折叠、工具输出复制等交互行为不受影响
- [ ] 主 Agent 工具组（`subagentId` 为 `undefined`）外观与改动前完全一致

---

## Blocked by

Issue 1（需要 `ReActToolExecutionBlock.subagentId` 和 `delegationDepth` 字段）
