# UI Acceptance — Workspace 知识库

## Metadata

- **Slug:** `workspace-knowledge-base`
- **Updated:** 2026-04-28
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope

- **路由/页面：** 知识库列表页（含空状态、已登录态）。
- **组件：** `ProjectSidebar` 新增导航项；折叠/展开两种侧栏形态。
- **展示：** 路径列或以副标题展示的 `Workspace/knowledge/…`。
- **与后端：** 依赖 [`acceptance.md`](./acceptance.md) 中存档与列表 API。

## Reference assets (`mockups/`)

本交付 **不提供** 参考 PNG（已确认 **Mockups deferred**）；不阻塞开发。可选后续补充：`docs/Process/workspace-knowledge-base/mockups/01-knowledge-desktop.png`。

## Visual criteria

| ID | Criterion | How to verify |
|----|-----------|---------------|
| U-01 | 侧栏展开状态下，「知识库」入口位于既定导航分组内，与其它项（专业子 Agent、专项技能）视觉层级一致（字重、行高、留白）。 | `/design-review` 或 Phase 6 手动 |
| U-02 | 知识库页面标题与子标题可读；深色背景下对比度不因灰字过低而不可读（参考现有 Billing/用量页）。 | 浏览器 + 目测 |
| U-03 | 列表或卡片中展示的「路径」或副标题与用户约定一致：以 `Workspace/knowledge/` 开头（或与 i18n 占位一致），不出现裸 `u_` 段为主视觉（若在调试模式显示可收起）。 | 截图对比 `design.md` |
| U-04 | 空状态时明确说明依赖「专业类（安全/研究）任务」完成后自动归档。 | `/design-review` 或文案 review |

## Interaction criteria

| ID | Criterion | How to verify |
|----|-----------|----------------|
| I-01 | 点击侧栏「知识库」跳转正确路由且无整页报错。 | Playwright |
| I-02 | 折叠侧栏仅用图标仍可进入知识库（Tooltip 含对应文案）。 | 键盘 Tab + 悬停 |
| I-03 | （若有下载）下载按钮对已登录可用；失败时出现非阻塞 Toast（与现有 Sonner 风格一致）。 | 手动 / E2E |
| I-04 | 专业任务完成触发自动存档后，用户导航到知识库可见新条目（或刷新后可见），无需硬刷新整站。 | E2E 或 staging |

## Responsive

- **375px：** 侧栏抽屉内同样显示知识库入口；主内容区列表可横向滚动或折行不截断关键列。
- **768px / 1024px：** 布局与现有 Workspace 一致，无重叠 fixed 层。

## Accessibility

- 侧栏项具备可聚焦与 `aria-label`（与现有 `NavLink` 模式一致）。
- 对比度：正文与 `muted` 文本保持团队既有 WCAG 目标（与 Account 页同级）。

## Sign-off

| ID | Result | Evidence | Verifier | Date | Notes |
|----|--------|----------|----------|------|-------|
| U-01 | | | | | |
| U-02 | | | | | |
| U-03 | | | | | |
| U-04 | | | | | |
| I-01 | | | | | |
| I-02 | | | | | |
| I-03 | | | | | |
| I-04 | | | | | |
