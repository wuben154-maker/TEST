# Issue 2：委派分组头部 — 专属图标 + 彩色边框 + Badge Chip

**类型**：AFK  
**阻塞**：Issue 1  
**父文档**：[prd.md](./prd.md)

---

## What to build

在 `ReActTimelineView` 中，将 `delegation_group` 类型的 `StepBlockView` 从通用外观（Bot 图标 + 中性边框）升级为按子 Agent 强调色渲染的专属外观。

端到端行为：当时间轴中出现 `email-security` 的 `delegation_group` block 时，用户看到：琥珀色左边框 + Mail 图标 + 标题旁的琥珀色 badge 显示 `email-security`；当出现 `binary-analysis` 时，看到蓝色左边框 + Cpu 图标 + 蓝色 badge；未预置的 subagentId 回落为通用 Bot 图标 + 中性边框，无 badge。

---

## Acceptance criteria

- [ ] `ReActTimelineView.tsx` 内定义 `SUBAGENT_ACCENT` 常量，包含至少 `email-security`（琥珀/Mail）、`binary-analysis`（蓝/Cpu）、`web-security`（翠绿/Globe）、`deep-research`（紫/BookOpen）四条记录
- [ ] 每条记录包含 `Icon`（Lucide 图标组件）、`borderClass`（Tailwind 完整类名，如 `border-amber-400/70`）、`badgeClass`（完整类名，如 `bg-amber-400/15 text-amber-600`）
- [ ] `StepBlockView` 在 `stepVariant === 'delegation_group'` 时查 `SUBAGENT_ACCENT`，渲染专属 Icon；未知 id 回落 Bot
- [ ] 左侧 `border-l-2` 颜色切换为查得的 `borderClass`；未知 id 保留 `border-border/40`
- [ ] 标题行尾部渲染 badge chip（`rounded-full px-1.5 py-0.5 text-[10px] font-medium`），内容为 `subagentId` 字符串；`subagentId` 为 `undefined` 时不渲染 badge
- [ ] Tailwind 颜色类使用完整字符串（禁止动态拼接），确保 purge 阶段类名被保留
- [ ] 视觉在深色和浅色模式下均保持可辨识对比度（人工验证即可，无需自动化）
- [ ] 现有 `StepBlockView` 的 `subagent_task` 和 `generic` 变体外观不受影响

---

## Blocked by

Issue 1（需要 `ReActStepBlock.subagentId` 字段）
