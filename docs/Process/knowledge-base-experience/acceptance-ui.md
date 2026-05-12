# Acceptance — UI (`knowledge-base-experience`)

## Metadata

- **Slug**: `knowledge-base-experience`
- **Links**: [`proposal.md`](./proposal.md), [`design.md`](./design.md)
- **Updated**: 2026-05-06

## Scope

路由 `/knowledge`（`KnowledgeBase.tsx`）布局、汇总条、搜索、刷新、卡片列表、空状态、高亮与下载反馈。

## Reference assets

| File | Purpose |
|------|---------|
| — | **Mockups deferred**（用户未提供参考图；以 `design.md` 与线框描述为准） |

## Visual criteria

| ID | Criterion |
|----|-----------|
| U-01 | 页宽较前版略放宽（约 `max-w-4xl`），标题区与操作区对齐，垂直节奏一致 |
| U-02 | 汇总区在列表上方：至少展示条数、总大小、最近更新时间（有数据时） |
| U-03 | 每条为卡片：左侧类型图标、主标题一行、次要一行（大小 · 时间 · 关联状态） |
| U-04 | `?highlight=` 命中项有清晰高亮（描边或左侧色条），滚动入视口 |

## Interaction criteria

| ID | Criterion |
|----|-----------|
| I-01 | 搜索框对 `display_name` / `display_path` / `filename` 子串即时过滤，无匹配时有说明文案 |
| I-02 | 刷新按钮重新请求列表；加载中状态可感知 |
| I-03 | 点击**文档标题**进入关联项目工作区；无 `project_id` 时点击提示不可跳转（样式为禁用） |
| I-04 | 下载成功出现 toast（或等价反馈）；失败保留错误 toast |
| I-05 | 空列表显示引导 copy +「前往工作台」主按钮（或可导航至 `/start`） |

## Responsive

- **375px**：卡片 stacked；搜索与刷新可折行；操作按钮可触达。
- **768px+**：卡片内信息与按钮横排合理，无水平溢出。

## Accessibility

- 搜索框与刷新按钮有可用 `aria-label` 或可见标签；图标按钮补充 `aria-label`。
- 焦点顺序：搜索 → 刷新 → 卡片内控件合理。

## Sign-off

| ID | pass/fail | verifier | date | notes |
|----|-----------|----------|------|-------|
| U-01 | pass | agent | 2026-05-06 | `max-w-4xl` + 页头/工具栏对齐 |
| U-02 | pass | agent | 2026-05-06 | 条数·合计·最近更新 |
| U-03 | pass | agent | 2026-05-06 | 卡片 + 图标 + 元信息行 |
| U-04 | pass | agent | 2026-05-06 | ring + `scrollIntoView` |
| I-01 | pass | agent | 2026-05-06 | 前端过滤 + `noMatches` |
| I-02 | pass | agent | 2026-05-06 | 刷新重拉列表 |
| I-03 | pass | agent | 2026-05-06 | 独立「打开工作区」按钮 |
| I-04 | pass | agent | 2026-05-06 | `toast.success` 下载反馈 |
| I-05 | pass | agent | 2026-05-06 | `kb-empty-cta` → `/start`；E2E-03 |
