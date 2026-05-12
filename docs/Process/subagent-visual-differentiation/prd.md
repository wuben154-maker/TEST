# PRD：子 Agent 时间轴视觉区分

**特性标识**：`subagent-visual-differentiation`  
**状态**：待排期  
**日期**：2026-05-05

---

## Problem Statement

在 ReAct 时间轴中，当主 Agent 委派多个专业子 Agent（如 `email-security` → 嵌套调用 `binary-analysis`）时，用户无法通过视觉区分：

- 哪些思考/工具调用属于 `email-security`，哪些属于 `binary-analysis`；
- `binary-analysis` 何时「进入」、何时「结束返回」；
- 当两个 Agent 调用同名工具（如 `file_identify`、`document_extract`）时，工具行看起来完全相同，归属不明。

根本原因在于：委派分组头部（`delegation_group`）仅靠极小的文字缩进（12px）区分嵌套层级，且后续的工具 pill 不携带任何归属信息，整体时间轴呈现为一个扁平列表。

---

## Solution

为每个已知子 Agent 分配固定的**强调色 + 专属图标**，在 ReAct 时间轴上通过以下三个视觉信号明确归属边界：

1. **委派分组头部**：将通用的 Bot 图标换为子 Agent 专属图标，左侧竖边框染色，并在标题旁添加与颜色一致的标识徽章（badge）；
2. **工具执行组**：在整组工具 pill 的外层包裹一条彩色左导轨，并随嵌套深度缩进，使工具行的视觉归属与头部对齐；
3. **段落分隔线**：在每个委派分组头部之前插入极细分隔线，明确划出「新 Agent 段落开始」的边界。

---

## User Stories

1. 作为分析结果的阅读者，我希望每个子 Agent 的时间轴段落有明显的颜色和图标标识，以便我一眼分辨「这段是邮件安全分析」还是「这段是二进制分析」。
2. 作为阅读者，我希望同名工具（如 `file_identify`）在不同子 Agent 中显示时，能通过颜色导轨区分归属，以便我理解工具被哪个 Agent 调用了。
3. 作为阅读者，我希望嵌套子 Agent（如 `binary-analysis` 在 `email-security` 内部）有额外的缩进，以便我感知层级关系。
4. 作为阅读者，我希望子 Agent 段落的开始有一条细分隔线，以便我快速定位「切换点」而不必逐行阅读文字。
5. 作为阅读者，我希望当 `binary-analysis` 结束、流程返回 `email-security` 时，视觉上能清楚感知到段落切换，而不是两段工具行连续出现、无法区分。
6. 作为阅读者，我希望未被预置的子 Agent（未来新增的、未知 id）也能有合理的默认外观（通用图标 + 中性边框色），而不是渲染报错或视觉混乱。
7. 作为阅读者，我希望颜色强调在深色模式和浅色模式下都保持合适的对比度，不影响阅读工具名称和详情。
8. 作为开发者，我希望子 Agent 强调色配置集中在一处，以便在新增子 Agent 时只改一个地方。
9. 作为开发者，我希望「当前子 Agent 上下文」由构建器（builder）层确定并写入 block，而不是由渲染层根据顺序推断，以便时间轴可回放且行为可预期。
10. 作为开发者，我希望这一改动不影响 Thinking 块的现有外观和折叠/展开行为，以缩小改动范围和测试面。

---

## Implementation Decisions

### 模块改动

**模块 1：ReAct Block 类型定义**（`buildReActTimeline` 导出的类型）

- `ReActStepBlock`（`stepVariant === 'delegation_group'`）新增可选字段 `subagentId?: string`，值为子 Agent 的技术标识符（如 `email-security`）；
- `ReActToolExecutionBlock` 新增可选字段 `subagentId?: string` 和 `delegationDepth?: number`，分别用于查表取强调色和计算缩进量。

**模块 2：ReAct 时间轴构建器**（`buildReActTimeline` 函数）

- 在事件处理主循环中维护 `currentSubagentId: string | null` 局部变量；
- 在插入 `delegation_group` 步骤 block 时：写入 `subagentId = techId`，并更新 `currentSubagentId`；
- 当遇到 `scope === 'main'` 的 `llm_invoke_start` 或其他主图事件，将 `currentSubagentId` 清空；
- `flushTools()` 时：将 `currentSubagentId` 和当前 `delegationDepth`（来自最近一次 `delegation_group` 事件）一并写入推送的 `ReActToolExecutionBlock`。

**模块 3：子 Agent 强调色配置**（`ReActTimelineView.tsx` 内部）

- 定义 `SUBAGENT_ACCENT: Record<string, { Icon: LucideIcon; borderClass: string; badgeClass: string }>` 常量；
- 已知条目：`email-security`（琥珀色 + Mail 图标）、`binary-analysis`（蓝色 + Cpu 图标）、`web-security`（翠绿色 + Globe 图标）、`deep-research`（紫色 + BookOpen 图标）；
- 未知 `subagentId` 回落到默认值（Bot 图标 + `border-border/40`）。

**模块 4：`StepBlockView` 渲染**（`delegation_group` 分支）

- 读取 `block.subagentId`，查 `SUBAGENT_ACCENT` 取图标和颜色类；
- 用查得的图标替换通用 Bot；
- 左侧竖边框颜色改为 `borderClass`；
- 标题行尾部追加 badge chip：`<span className={badgeClass}>{block.subagentId}</span>`。

**模块 5：`ToolExecutionBlockView` 渲染**

- 新增 props：`subagentId?: string`，`indentPx?: number`；
- 当 `subagentId` 有值时，用 `<div style={{ marginLeft: indentPx ?? 0 }} className={cn('border-l-2 pl-2', borderClass)}>` 包裹现有 pill 列表；
- `indentPx = (delegationDepth - 1) * 12`（与头部文字缩进对齐）；depth=1 时 `indentPx = 0`（顶格）。

**模块 6：`ReActTimelineView` 主渲染循环**

- 在 `blocks.map()` 里，当当前 block 为 `delegation_group` step 时：先渲染 `<hr className="border-border/20 my-1.5" />`，再渲染 `StepBlockView`；
- 向 `ToolExecutionBlockView` 传递 `subagentId` 和 `indentPx`。

### 技术约定

- ThinkingBlock 不接收 `subagentId`，外观不变；
- `SUBAGENT_ACCENT` 配置只在 `ReActTimelineView.tsx` 内部，不提前抽为共享文件（YAGNI——目前无第二消费者）；
- Legacy 行（仅有 `subagentName`、无委派信封字段）不得到委派分组头，因此也不触发彩色导轨，保持既有行为；
- `<hr>` 分隔线在每个 `delegation_group` block 前统一插入，不按 depth 差值区分。

---

## Testing Decisions

### 什么是好的测试

- 只测**外部行为**（block 的字段值），不测内部变量（如 `currentSubagentId`）；
- `buildReActTimeline` 层的测试：构造输入 `AnalysisTimelineEntry[]`，断言输出 `ReActBlock[]` 中对应 block 的字段；
- 渲染层测试（如有）：使用现有的 `ReActTimelineView.test.tsx` 模式，传入 blocks 断言 DOM 类名或属性。

### 需要测试的模块

**`buildReActTimeline.ts`（新增测试用例）**：

- `delegation_group` block 携带正确的 `subagentId`（`email-security`、`binary-analysis` 等）；
- 紧随 `delegation_group` 之后 flush 的 `tool_execution` block 携带正确的 `subagentId` 和 `delegationDepth`；
- depth=2 的嵌套 `binary-analysis` 工具块的 `delegationDepth === 2`；
- 主 agent 工具块（`scope === 'main'`）`subagentId` 为 `undefined`；
- Legacy 行（无委派信封）flush 的工具块 `subagentId` 为 `undefined`。

**参考先例**：`buildReActTimeline.test.ts` 中的「inserts a delegation_group step when subagent rows include delegationDepth」系列测试——新增用例采用相同的 `entry()` helper 和断言模式。

---

## Out of Scope

- **ThinkingBlock 视觉区分**：Thinking 块不加颜色，仍使用统一的 Brain 图标；
- **折叠/展开子 Agent 段落**：方案 B（`subagent_section` 嵌套 block）不在本次范围内；
- **「返回上一层」文字提示**：只用 `<hr>` 分隔，不加 `↩ 返回 email-security` 等说明文字；
- **共享强调色配置文件**：暂不抽取，待有第二消费者（如任务看板标题）时再提取；
- **自定义主题/用户可配置颜色**：颜色硬编码，不暴露配置入口；
- **DOCX 导出适配**：导出层暂不反映子 Agent 视觉区分；
- **`subagentId` 透传给 TaskListBlock**：任务列表块当前无此需求，不改动。

---

## Further Notes

- 本方案（方案 C）是三个候选方案中改动最小的，保留了向方案 B（`subagent_section` 区块嵌套、可折叠）演进的空间——届时只需在构建器后处理阶段将连续 block 收拢为 section 容器。
- `SUBAGENT_ACCENT` 中颜色类需使用 Tailwind 的完整类名（如 `border-amber-400/70` 而非动态拼接），以保证 Tailwind 的 content 扫描正确生成 CSS。
- 若某次分析中同一子 Agent 被委派多次（如两次独立调用 `binary-analysis`），每次都有独立的 `rootDelegationId`，会产生多个 `delegation_group` 头——每个头前均加 `<hr>`，行为正确，无需特判。
