# UI Acceptance — `cursor-style-analysis-timeline`

## Metadata

- **Slug:** `cursor-style-analysis-timeline`
- **Updated:** 2026-03-26
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Criteria ownership (delivery-pipeline)

- **Source of truth:** **Product owner / you** — criteria below were **structured from prior exploration** and templates. **Edit freely** in IDE; major changes should match what you agreed in conversation.
- **Agent role:** Only **transcribe and format** (`U-` / `I-` ids, tables). Do not treat this file as immutable without human review.

## Scope

- **Screens / routes:** Command Center / 分析工作区：**左栏执行过程** + **右栏用户对话/需求**（见 [design.md](./design.md) Layout 节）。
- **Components:** `TraceList` / `TraceRow`、双栏布局、右栏对话、**HITL 三态**（单选/多选/参数）；`TimelineActivity` / `UnifiedAnalysisTracePanel` 迁移；不包含无关 workspace 块。

## Reference assets (`mockups/`)

| File (repo-relative) | Description |
|----------------------|-------------|
| `docs/Process/cursor-style-analysis-timeline/mockups/1.jpeg` | 参考：左执行 / 右对话布局与视觉层级 |
| `docs/Process/cursor-style-analysis-timeline/mockups/2.jpeg` | 参考：同上（补充视角或状态） |
| `docs/Process/cursor-style-analysis-timeline/mockups/3.jpeg` | 参考：**Lovable 向控件**（圆角卡片、主按钮、选项样式）；用于右栏气泡与左栏 **HITL / 可交互块** |

## Visual criteria

| ID | Criterion | How to verify |
|----|-----------|---------------|
| U-01 | **左栏**主轨迹为 **单列**，工具/推理/错误行共用 **同一行骨架**（左 gutter + 主文 + 右状态），无「气泡 + 日志」混排感 | 对照 `mockups/1.jpeg`、`2.jpeg` 与同视口实机 |
| U-02 | 全轨迹 **最多 2 档 sans 正文 + 1 档 mono（仅展开区/代码）**；工具主标题 **非整行 mono** | 开发者工具检查 computed font-size / font-family |
| U-03 | **单一纵向间距刻度**（如统一 8px gap）；列表内无与 `mb-4` 级外边距混用导致的「忽松忽紧」 | 测量相邻行间距或审查 DOM class |
| U-04 | 轨迹主区域 **无紫/粉强渐变背景**；表面以中性色 + 细边框为主 | 目视 + 与 design Visual tokens 对照 |
| U-05 | **任务块** 单锚点：更新时列表顶位置不「整列复制下移」 | 同一 session 录屏 |
| U-06 | **子代理**：委托 **一行**；后续行与主流程 **同组件样式**，无持久嵌套框 | 含 subagent 流程目视 |
| U-07 | **不展示** taskId/UUID 灰条；次要文案仅在人话有意义时出现 | 检索 uuid chip |
| U-08 | **结论/摘要** 在 **左栏时间序** 中位置正确（见 U-11），且相对过程区可扫读 | 产品确认 + U-11 |
| U-09 | 流式 **至多一种**主反馈动画 | 录屏一回合 |
| U-10 | 深色模式 `muted` 大段推理仍可读（目标 WCAG AA 正文） | 主题切换抽样 |
| **U-11** | **时间序正确：** 左栏 **仅一个**执行流容器；`task_summary` / `conclusion` **不得**出现在「两个独立控件之间」导致垂直阅读顺序与事件 `seq` 不一致（禁止历史双段布局） | 见 [design.md](./design.md) 反模式图；用含中段工具 + 末段结论的 fixture 查 DOM 顺序 |
| **U-12** | **右栏** 为 **用户需求/对话列表**（与 mockup 一致）；**左栏** 仅为执行过程；两栏职责不串 | 对照 `1.jpeg`/`2.jpeg` |
| **U-13** | **交互控件气质**与 `3.jpeg` 一致：HITL 块、右栏用户气泡、主按钮与选项卡 **Lovable 风**；左栏 **纯执行行** 仍保持文字优先、不过度卡片化（与 [design.md](./design.md) 双轨 token 一致） | 对照 `3.jpeg` + 实机 |

## Interaction criteria

| ID | Criterion | How to verify |
|----|-----------|---------------|
| I-01 | 工具行可展开详情时，键盘可聚焦且 `aria-expanded` 正确 | Tab / SR |
| I-02 | 折叠/展开触控目标 **≥ 44px**（或等价 padding） | 量测 |
| I-03 | HITL 在左栏时间序 **原位**；提交后续流正常 | 各走通一条含 HITL 的回合 |
| **I-08** | **单选** HITL：`allowMultiple=false` 时仅可选一项；未选提交应提示或禁用主按钮 | fixture / 手测 |
| **I-09** | **多选** HITL：`allowMultiple=true`；按产品规则校验（默认至少一项）后提交 | fixture / 手测 |
| **I-10** | **参数** HITL：表单必填/类型校验；错误态可见；提交后 resume | fixture / 手测 |
| I-04 | 长推理/长 JSON 展开不撑破布局 | 极端 fixture |
| I-05 | **中英文**切换后模板语句可换行不溢出 | `en` / `zh` |
| I-06 | 键盘可完成展开工具 + 完成 **任一种** HITL 提交 | 无鼠标走通 |
| **I-07** | 窄屏栈叠时，两栏内容仍完整可用（顺序见 design / 与产品约定） | 375px 视口 |

## Responsive

- **375px:** 双栏 **栈叠**（具体上下顺序以 design 为准）；轨迹区横向不溢出；`break-words` / `min-w-0`。
- **768px:** 与桌面同一信息优先级或按产品断点切换双栏。
- **1440px:** 对照 `1.jpeg`/`2.jpeg`（布局）与 `3.jpeg`（控件）；U-01、U-12、U-13。

## Accessibility

- **Contrast:** WCAG 2.1 AA 目标；状态不单靠颜色。
- **Focus:** 可见焦点环；左栏 `TraceList` 内顺序合理。
- **Touch targets:** 见 I-02。

## Sign-off

| ID | Result | Verifier | Date | Notes |
|----|--------|----------|------|-------|
| U-01 | | | | |
| U-02 | | | | |
| U-03 | | | | |
| U-04 | | | | |
| U-05 | | | | |
| U-06 | | | | |
| U-07 | | | | |
| U-08 | | | | |
| U-09 | | | | |
| U-10 | | | | |
| U-11 | | | | |
| U-12 | | | | |
| U-13 | | | | |
| I-01 | | | | |
| I-02 | | | | |
| I-03 | | | | |
| I-04 | | | | |
| I-05 | | | | |
| I-06 | | | | |
| I-07 | | | | |
| I-08 | | | | |
| I-09 | | | | |
| I-10 | | | | |
