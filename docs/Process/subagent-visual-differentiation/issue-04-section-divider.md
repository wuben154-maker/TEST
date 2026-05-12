# Issue 4：段落分隔线 — 每个委派分组头部前插入 `<hr>`

**类型**：AFK  
**阻塞**：无，可立即开始（不依赖 Issue 1）  
**父文档**：[prd.md](./prd.md)

---

## What to build

在 `ReActTimelineView` 主渲染循环中，每当遇到 `stepVariant === 'delegation_group'` 的 block，在其渲染输出之前插入一条极细分隔线，明确划出「新的子 Agent 段落开始」的边界。

端到端行为：时间轴从主 Agent 内容切换到 `email-security` 时，中间有一条细线；从 `email-security` 内容切换到 `binary-analysis` 时，中间也有一条细线。用户无需逐行阅读文字，即可快速定位切换点。

---

## Acceptance criteria

- [ ] `ReActTimelineView` 的 `blocks.map()` 循环中，当 `b.kind === 'step' && b.stepVariant === 'delegation_group'` 时，在该 block 的 JSX 之前输出 `<hr className="border-border/20 my-1.5" />`
- [ ] 分隔线对所有 delegation_group block 统一插入（不区分 depth、不跳过第一个）
- [ ] 分隔线使用 `border-border/20`（极低透明度），视觉上足够细不抢夺注意力（人工验证）
- [ ] 所有现有 block 类型的渲染顺序和输出内容不受影响
- [ ] 无 `delegation_group` block 的时间轴（纯主 Agent 分析）不出现任何额外分隔线

---

## Blocked by

无 — 可立即开始，与 Issue 1/2/3 并行
