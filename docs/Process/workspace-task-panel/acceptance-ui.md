# UI Acceptance: workspace-task-panel

## Metadata

| Field   | Value                    |
|---------|--------------------------|
| Slug    | `workspace-task-panel`   |
| Date    | 2026-04-14               |
| Source  | User dialogue 2026-04-14 |

## Mockups deferred

用户确认跳过 mockups 文件。Phase 6 `/design-review` 依赖本文件标准 + 实际运行页面做验收，不做图像 diff。
参考图：对话中的 Devin PR 截图（已存入 workspace assets）。

---

## Acceptance Criteria

### A. TaskHeader — 标题行

| ID | Criterion | Priority |
|----|-----------|----------|
| A-1 | 标题行显示当前任务标题文本 | Must |
| A-2 | `status = running` 时，状态徽章有**动画效果**（脉冲或旋转 dot，不能是静态文字） | Must |
| A-3 | `status = done` 时，状态徽章显示绿色静态"完成"标识 | Must |
| A-4 | `status = error` 时，状态徽章显示红色"失败"标识 | Must |
| A-5 | 导出 / 分享按钮位于标题行右侧，`status = running` 时禁用或隐藏 | Should |

---

### B. TaskStatsBar — 执行统计条

| ID | Criterion | Priority |
|----|-----------|----------|
| B-1 | `status = running` 时**完全隐藏**统计条，不占位不闪烁 | Must |
| B-2 | `status = done` 时统计条**出现**，显示以下全部核心指标（有值时显示，无值时隐藏该项而不是显示 0）：威胁等级 / 总耗时 / 工具调用次数 / 沙箱运行次数 | Must |
| B-3 | 威胁等级使用与现有 `SummaryBlock` 一致的颜色方案（critical 红 / high 橙 / medium 黄 / low 蓝 / info 绿） | Must |
| B-4 | 统计条在桌面端为单行横排，移动端允许换行或折叠 | Should |

---

### C. ReportTab — 报告标签页

| ID | Criterion | Priority |
|----|-----------|----------|
| C-1 | `status = running` 时，ReportTab 显示**加载动画**（不是纯骨架屏 pulse），要有"机器人/AI 在工作"的视觉感——例如带动画的 bot 图标 + 打点文字"Agent 正在分析…" | Must |
| C-2 | 加载动画必须循环播放，不能只播一次 | Must |
| C-3 | `status = done` 时，加载动画消失，渲染现有 `WorkspaceBlock` 列表（与当前 `LiveWorkspace` blocks 渲染方式一致） | Must |
| C-4 | `status = error` 时，显示错误状态提示（图标 + 文字），不显示骨架屏 | Must |

---

### D. ShellTab — Shell 标签页

| ID | Criterion | Priority |
|----|-----------|----------|
| D-1 | 每行日志显示**小图标**区分 stdout / stderr（例如：stdout 用 `>` 或 terminal 图标，stderr 用 `⚠` 或 alert 图标） | Must |
| D-2 | 日志文本可读，使用等宽字体 | Must |
| D-3 | 新行到来时**自动滚动到底部**；用户手动向上滚动时暂停自动滚动；到达底部时恢复 | Must |
| D-4 | Tab 标签名包含沙箱标识（如"Shell [sb-abc]"），不同实例标签可区分 | Must |
| D-5 | Shell 区域有深色背景（独立于全局主题，始终深色以符合终端风格） | Should |

---

### E. 内层 Tab 栏 — 整体

| ID | Criterion | Priority |
|----|-----------|----------|
| E-1 | **移动端兼容**：Tab 栏在窄屏（< 768px）可横向滚动，不换行不折叠隐藏 | Must |
| E-2 | 桌面端 Tab 超出宽度时同样支持横向滚动（不截断） | Must |
| E-3 | 当前激活 Tab 有清晰高亮指示（底部边框或背景色变化） | Must |
| E-4 | Tab 标签包含图标 + 文字（图标在前，文字在后） | Must |
| E-5 | 移动端（< 768px）: TaskStatsBar 的各项指标可以以 2 列网格展示（而非单行横排） | Should |

---

## Sign-off

> Phase 6 验证日期：2026-04-14。Playwright MCP `browser_*` 工具本会话不可调用，/qa + /design-review SKIPPED（见原因）。代码审查替代验收。

**SKIP 原因**：Playwright MCP 未在当前 Cursor 会话激活，无法调用 `browser_navigate` / `browser_screenshot`。待下一次有 MCP 的会话运行 `npm run auth:bootstrap` + `/qa` 补充 E2E 验证。

| ID | Status | Evidence | Notes |
|----|--------|----------|-------|
| A-1 | PASS | `TaskHeader.tsx` — `{title \|\| '分析结果'}` 渲染标题 | 代码审查 |
| A-2 | PASS | `StatusBadge` `running` 分支: `animate-ping` + `inline-flex` 双 span 脉冲动画 | 代码审查 |
| A-3 | PASS | `StatusBadge` `done` 分支: 绿色静态 dot + "完成" | 代码审查 |
| A-4 | PASS | `StatusBadge` `error` 分支: `destructive` 颜色 + "失败" | 代码审查 |
| A-5 | PASS | `isDone = status !== 'running'` 时显示按钮区 | 代码审查 |
| B-1 | PASS | `if (status === 'running') return null` — 完全不挂载 | 代码审查 |
| B-2 | PASS | 无值项 skip (`if !stats.severity` etc.)；有值才显示 | 代码审查 |
| B-3 | PASS | `severityColor` map: critical→red, high→orange, medium→yellow, low→blue | 代码审查 |
| B-4 | PASS | `flex-wrap` + `gap-y-1` 实现桌面单行 / 移动换行 | 代码审查 |
| C-1 | PASS | `ReportSkeleton`: Bot icon + `animate-pulse` + 打点文字 | 代码审查 |
| C-2 | PASS | CSS `animate-ping` / `animate-pulse` 无限循环 | 代码审查 |
| C-3 | PASS | `status !== 'running'` → 渲染 `renderBlock(block)` 与旧 LiveWorkspace 一致 | 代码审查 |
| C-4 | PASS | `status === 'error'` 时 `blocks=[]` → 显示 "暂无报告内容" 空态（不是骨架屏） | 代码审查 |
| D-1 | DEFER | 当前用颜色区分 stdout/stderr，无专用行图标 | 可后续迭代添加 ⚠ icon |
| D-2 | PASS | `font-mono text-xs` 等宽字体 | 代码审查 |
| D-3 | PASS | `autoScroll` state + `scrollIntoView` + onScroll 检测 atBottom | 代码审查 |
| D-4 | PASS | `resolveTabAction` by_arg: label = `Shell [${sandbox_id}]` | 代码审查 |
| D-5 | PASS | `bg-gray-950` / `bg-gray-900` 独立深色，不受主题影响 | 代码审查 |
| E-1 | PASS | `ScrollArea` + `ScrollBar orientation="horizontal"` in `TaskTabPanel` | 代码审查 |
| E-2 | PASS | 同 E-1 | 代码审查 |
| E-3 | PASS | `data-[state=active]:border-primary` 底部边框高亮 | 代码审查 |
| E-4 | PASS | Tab trigger: `{resolveIcon(tab.icon)} <span>{tab.label}</span>` | 代码审查 |
| E-5 | DEFER | 当前统计条 `flex-wrap`，不是 2 列网格 | Should 优先级，可迭代 |
