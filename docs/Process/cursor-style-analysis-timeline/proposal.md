# Proposal — Cursor-style analysis timeline (product UI)

## Metadata

- **Slug:** `cursor-style-analysis-timeline`
- **Updated:** 2026-03-27（双栏布局 + 左栏严格时间序 + `design.md` 内 **Todo list** 章节勾选）
- **Related:** [design.md](./design.md), [acceptance-ui.md](./acceptance-ui.md), [acceptance.md](./acceptance.md)

## Delivery pipeline compliance

- **Phase 2 on-disk artifacts:** `proposal` / `design` / `acceptance-ui` / `acceptance` 均已落盘；**Sign-off 表 Phase 6 填写**。
- **Acceptance content:** `acceptance*.md` 准则以 **用户确认与直接编辑** 为准；Agent 仅负责结构与可追溯 id。
- **Mockups:** [mockups/](./mockups/) — `1.jpeg`/`2.jpeg`（布局）、`3.jpeg`（Lovable 控件）；登记见 [acceptance-ui.md](./acceptance-ui.md)。
- **design.md** 须 **深于** Cursor Plan 气泡，且含靠前 **`## Todo list`**（GFM **`- [ ]` / `- [x]`**，每项带稳定 **id**）；Phase 4 随进度勾选。文首 YAML 仅可选 **`name` / `overview`**（与 Cursor Plan 元数据类似，**不含** `todos:`，避免 Markdown 预览里待办不像列表）。

## Relation to OpenSpec

本交付在 **delivery-pipeline** 下以 `docs/Process/cursor-style-analysis-timeline/` 为执行与验收真源。技术目标与历史方案 [openspec/changes/agent-timeline-product-ui/](../../../openspec/changes/agent-timeline-product-ui/)（含 [specs/reasoning-timeline-ui/spec.md](../../../openspec/changes/agent-timeline-product-ui/specs/reasoning-timeline-ui/spec.md)）**对齐**：单列严格时序、文字优先工具行、任务块锚定更新、子代理单行委托且后续行与主流程同组件、无 UUID 灰条。OpenSpec 目录保留作跨工具引用；若正文冲突，**以本目录 `design.md` + acceptance 为准**并回写 OpenSpec 说明。

## Problem

分析对话区同时混用多种呈现（气泡 Markdown、日志行、渐变思考块、另一套 Thinking 链），导致：

- thinking 与工具执行 **视觉方言不统一**；
- 纵向 **间距刻度不一致**；
- **字号阶梯过多**（xs / sm / prose / 固定 px 混用）；
- 子代理路径与主时间线 **嵌套感** 与产品目标不符。
- **双控件分栏渲染**（如上线性摘要 + 下时间线）导致 **summary 夹在中间**，垂直顺序与真实 **时间线 `seq`** 不一致。

## Goals

- **布局：** **左栏** = Agent 执行过程（Cursor 式轨迹）；**右栏** = 用户需求/对话列表（参考 [mockups/1.jpeg](./mockups/1.jpeg)、[2.jpeg](./mockups/2.jpeg)）。
- **控件风格：** 右栏气泡与左栏 **需用户操作的块**（HITL、主按钮、选项）参考 **Lovable 向** [mockups/3.jpeg](./mockups/3.jpeg)；执行列表主体仍文字优先（见 design 双轨 token）。
- **HITL 三形态：** 单选、多选、参数表单，均在左栏时间序原位，映射 `decision_request` / `parameter_request`。
- **左栏严格时间序：** **单一**有序列表驱动；`conclusion` / `task_summary` 等必须落在 **与 `seq` 一致** 的序位，**禁止**独立控件插在两段执行 UI 之间造成错乱。
- **统一行模型**：`delegation_line` | `text` | `tool_line` | `task_block` | `user_input` | `error_line`，由纯函数 reducer 从 merged timeline 生成。
- **工具行模板化**（read / web / shell / script / generic），详情默认折叠；**相邻同路径 Read 合并**，写路径类工具打断合并。
- **任务列表单锚点**：首次出现后位置固定，后续 `task_*` 仅更新状态。
- **子代理**：**恰好一行**委托说明，其后事件与主 Agent **同一套 `TraceRow` 组件**。
- **视觉冷静面**：轨迹区避免强渐变；全轨迹 **≤2 档 sans 正文 + 1 档 mono（仅展开区）**；**单一纵向间距刻度**；流式反馈 **≤1 种**主动画。

## Non-goals

- 不强制变更 SSE 协议（优先 `toolName` + payload 客户端映射）。
- 不做营销落地页式视觉；不做独立 HITL 悬浮坞（控件仍在时间序原位）。
- 不要求与 Cursor 内部实现逐像素一致，仅 **同类信息架构与密度**。

## Users

- 使用 Command Center / 分析工作区的终端用户（中英界面）。
- 需要可扫读「做了什么」与「结论在哪」的审阅者。

## Scope

- **前端：** 双栏壳层 + merged timeline → `timelineToTraceRows` → **左栏唯一** `TraceList` / `TraceRow`；右栏对话列表。**重构** [UnifiedAnalysisTracePanel.tsx](../../../src/components/reasoning/UnifiedAnalysisTracePanel.tsx) / [ReactLinearTraceView.tsx](../../../src/components/reasoning/ReactLinearTraceView.tsx) 等，**消除**「线性块与时间线块」纵向拼接导致的序错乱。收敛 [TimelineActivity.tsx](../../../src/components/reasoning/TimelineActivity.tsx)、[ReasoningPanel.tsx](../../../src/components/reasoning/ReasoningPanel.tsx)、[ChatMessage.tsx](../../../src/components/reasoning/ChatMessage.tsx)、[CommandCenter.tsx](../../../src/components/CommandCenter.tsx)。
- **测试：** reducer 与关键 UI 行为的单元/组件测试（见 design.md）。
- **文档：** [docs/SSE_EVENT_CATALOG.md](../../SSE_EVENT_CATALOG.md) 仅在需约定新展示语义时更新（本阶段尽量不增协议字段）。

## Dependencies

- 现有 canonical timeline 类型与合并逻辑（`AnalysisTimelineEntry`、[unifiedTimelineItems.ts](../../../src/lib/unifiedTimelineItems.ts)、[timelineDisplay.ts](../../../src/lib/timelineDisplay.ts)）。
- i18n（[src/i18n/locales/](../../../src/i18n/locales/)）；用户可见文案走语言文件，验收以行为与布局为主。

## Success metrics

- **左栏** 垂直顺序与 **事件 `seq`** 一致，**无** summary 夹在双控件之间（U-11 + A-07）。
- **右栏** 对话与 mockup 一致（U-12）；双栏职责不串。
- **控件** 与 `3.jpeg` Lovable 风一致（U-13）；HITL 三态可完成（I-08～I-10）。
- 同屏轨迹 **肉眼可感知为一套行组件**（U-01～U-10）。
- Reducer 行为 **A-01～A-08** 可测。
- 回放 stored timeline 与线上一致（A-06）。

## Open questions（需在实现前定稿或推迟并记入 design.md）

- 子代理委托行的 **唯一信号源**（仅 `step` / `scope` 翻转 / 其他）— 优先单一信号避免重复行。
- **toolName → 模板** 完整表（web_search、读文件、终端等）— 在 `design.md` 或代码 registry 维护。

## Phase 1 exploration

已在 Ask 中完成方向对齐；本 proposal 落盘即视为进入 Phase 2。若需补充探索，在 `design.md` 的 Open questions 更新后再批准编码。
