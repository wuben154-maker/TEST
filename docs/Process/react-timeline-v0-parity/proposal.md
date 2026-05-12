# Proposal — ReAct 对话时间线（v0 示例对齐）

## Metadata

- **Slug:** `react-timeline-v0-parity`
- **Updated:** 2026-03-30（Task List 分桶 + 正式回答协议）
- **Related:** [design.md](./design.md), [acceptance-ui.md](./acceptance-ui.md), [acceptance.md](./acceptance.md)

## Problem

当前分析对话区的 ReAct 展示分散在多个组件（如 `AnalysisTurnPanel`、`TimelineUnifiedBody`、`StreamEventRenderer`、`ThinkingChain` 等），视觉层次与交互不统一，难以对齐参考实现（本地示例 `b_lx7WQRylOUg-1774749340024` / [CodeGen 演示](https://v0-webui-ten.vercel.app/)）。零散改样式无法稳定达到目标观感。

## Goals

1. **视觉与信息架构**与参考示例一致：Thinking（含可折叠推理正文）、任务列表、工具执行（子行 + 路径/URL 从 JSON 解析）、结果摘要等按**同一时间线顺序**穿插展示。
2. **Thinking + Reasoning 合并为单一「Thinking」块**：可折叠区域承载推理过程；折叠在无推理正文时不可用；Thinking 阶段结束后展示 **Thought N 秒**；其**下方**展示模型**正式回答**（与「仅展示 reasoning、不展示最终回复」的旧行为区分）。
3. **任务列表**随 `write_todos`（及 task 类 tool 载荷）变化：**同一列表桶内**按 **任务唯一 ID** 合并更新行状态；**子代理新一轮任务 / 新列表桶**在时间线上出现**新的** Task List 块（与主列表并存、按 `seq` 排序），不把子代理待办覆盖进主列表块。
4. **工具执行**暂不展示 tool 返回内容；展示行从 `toolInput` JSON **解析**路径、URL 等（与示例 `Write` + `code` 路径一致的精神）。
5. **严格按 SSE `seq`（时间线）顺序**渲染；`step` 与 Thinking、TaskList、Tool Execution **同级**，由**后端 `step` 事件**驱动（前端不硬编码「委派子智能体」等文案）。

## Non-goals（本阶段明确不做）

- **删除**旧实现**源码文件**：`TimelineUnifiedBody`、`StreamEventRenderer`、`ThinkingChain` 等先保留在仓库内，待新时间线验收通过后再由你要求物理删除。
- **运行时双 UI**：新旧**不得同时挂载**；上线切换后对话区**只**挂载新时间线（`ReActTimelineView` 链），旧链路从挂载点移除，避免重复渲染与样式分叉。对比旧行为依赖 git 历史或临时分支，不靠 feature flag 并行两套 DOM。
- 工具返回内容的丰富预览、diff、折叠详情（后续迭代）。
- 重写后端图或 SSE 协议全貌；仅在设计中标出**已有/需补齐**的 `step` 与载荷约定。

## Users & scope

- **用户：** 使用主分析对话、需要可读 ReAct 轨迹的安全分析用户。
- **范围：** 前端展示层 + 纯函数「时间线 → 展示模型」适配；必要时与后端协调 `step` 载荷；**不**删除旧 UI 源文件，但**从 React 挂载点卸掉**旧链，仅保留新链。

## Dependencies

- 现有 SSE / `AnalysisTimelineEntry` / `multiAnalyzeStreamEvents` 合并逻辑。
- `docs/SSE_EVENT_CATALOG.md`、`src/types/analysis.ts` 中的 `step`、`tool_call`（含 `write_todos`）、`reasoning`、`conclusion` 等。

## Success metrics

- 验收清单（`acceptance-ui.md` / `acceptance.md`）在 Phase 6 可逐项对照通过。
- 与参考示例并排对比时，**块类型、顺序语义、折叠行为、任务/工具子行样式**一致（在无 mockup 时以 `acceptance-ui.md` + 在线参考为准）。

## Open questions

- `step` 是否已覆盖「委派子智能体」全场景；若否，后端补发而非前端写死。
- 「正式回答」协议已裁定，见 **`design.md` — §Reasoning vs 正式回答（协议决策）**；实现阶段与后端对齐首选方案或备选字段。
