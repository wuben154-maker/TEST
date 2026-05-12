# Proposal — `analysis-sse-layering`

## Metadata

- **Slug:** `analysis-sse-layering`
- **Updated:** 2026-03-28 (backend `app/sse` + registry both **required**, not optional)
- **Related:** [design.md](./design.md), [acceptance.md](./acceptance.md), [acceptance-ui.md](./acceptance-ui.md)

## Problem

- `docs/SSE_EVENT_CATALOG.md` 与 `src/types/analysis.ts` 已统一事件语义，但 **SSE 读流与 JSON 解析** 在 `useStreamingAnalysis` / `useStreamingAnalysisMulti` 中 **重复实现**，后续改协议易漏改、难测。
- **`write_todos` → 任务计划** 的逻辑在 `applyStreamingSwitch.ts` 与 `multiAnalyzeStreamEvents.ts` **各写一份**，与 catalog 要求的 **`toolPresentation: 'task'`** 演进不同步。
- 后端 `create_sse_message`、`_apply_sse_envelope` 分散在 `main.py` / `deepagents_stream_adapter.py`，模块边界不清晰。
- **`toolPresentation` / `parameterControl`**（[SSE_EVENT_CATALOG.md](../../SSE_EVENT_CATALOG.md) §6）若在适配器里用 **`if toolName == ...`** 扩散，工具一多就不可维护；展示语义必须是 **工程声明**（注册表 / 工具元数据 / 配置），**运行时不得由模型「推出来」**。

## Goals

1. **前端 L1（传输）**：单一实现将 `fetch` 流解析为逐条 `data:` JSON（与现有 buffer/切行行为一致）。
2. **前端 L2（协议）**：单一入口将 `unknown` 收窄为 `ThinkingEvent`；迁移期可在此做字段归一（如 `toolPresentation` 兜底）。
3. **去重**：共享 `write_todos` / 任务计划合成；hooks 只做生命周期与 state。
4. **后端 SSE 统一封装（必做）**：在 `python-agent-service` 内建立 **`app/sse/`** 模块边界：**成帧**（`create_sse_message` 从 `main.py` 迁入 `framing.py`）、**信封**（`_apply_sse_envelope` 等从 `deepagents_stream_adapter.py` 迁入 `envelope.py`）。所有 HTTP SSE 出口 **只经** 成帧层；适配器 **只产出 dict**，信封与 `mark_event_internal` 规则集中。**不改变** 对外 SSE 行格式与 JSON 形状（行为对齐重构前）。
5. **后端工具展示注册表（必做，可与 4 分 PR 但不得永久搁置）**：在后端建立 **`toolName → 展示元数据`** 的 **权威注册表**（见 [design.md](./design.md) **Tool presentation registry**）：
   - 键与 LangGraph / OpenAI 协议中的 **`toolName` 一致**；值至少含 **`toolPresentation`**：`task` | `action` | `state` | `parameter`；为 `parameter` 时再含 **`parameterControl`**：`single` | `multi` | `fill`。
   - **系统 / 框架工具**（`write_todos`、`task`、`read_file`、网关 `web_search` 等）在仓库内 **集中登记一次**，单测覆盖。
   - **自定义工具**：与工具定义 **同一 PR / 同一模块** 登记一行，或从 **YAML/JSON 配置** 加载，部署时 **合并进总表**。
   - **可选合并来源**：LangChain `BaseTool` 等对象上的声明字段（如 `presentation`），在 **wrap / 注册** 时读入并 **写入或覆盖注册表**（与纯配置二选一或合并策略见 design）。
   - **适配器职责收窄**：发出 `tool_call` 事件前只做 **`meta = REGISTRY.get(toolName) or DEFAULT`**，把字段 **抄到事件上**，禁止无限 `if toolName`。
   - **未知 `toolName`**：必须有 **默认策略**（产品选定：**默认 `action`** 为保守可见，或默认 `state` 更安静 —— 须书面选定）+ **结构化日志** `unknown_tool_name`；可选 **开发环境 assert** 强制新工具先登记再合并。
   - 前端 L3 以事件上的 `toolPresentation` 为主、`toolName` 仅兜底；与 catalog §11 维护顺序一致。

## Non-goals

- 不改变 **Slice A** 下对外 SSE **JSON 契约**（除非为 bugfix）。
- 不引入新的 npm/PyPI 依赖（除非 `design.md` ADR 记录）。
- 不在推理时让模型 **编造** `toolPresentation`（字段只来自注册表 / 工具元数据 / 合并后的总表 + DEFAULT）。
- 不生成 mockup 图片；参考图由用户放入 `mockups/` 或明确 **Mockups deferred**。

## Users / stakeholders

- 维护分析流与时间线的前后端工程师。
- 依赖 `POST /analyze` / `POST /analyze/resume` SSE 的产品与测试。

## Dependencies

- 权威文档：[docs/SSE_EVENT_CATALOG.md](../../SSE_EVENT_CATALOG.md)
- 类型：[src/types/analysis.ts](../../../src/types/analysis.ts)
- 现有 reducer：`timelineReducer`、`timelineDisplay`、`reactLinearTimeline` 等保持为 L3。

## Success metrics

- Slice A 合并后：**Vitest / 现有相关用例全绿**；有 LLM key 时 **E2E SSE 流程**（如 `test_e2e_full_stream`）行为与重构前一致。
- 新 L1/L2 有 **单元测试**（多 chunk、半行 JSON、与现 hook 对齐）。
- `applyStreamingSwitch` 与 `multiAnalyzeStreamEvents` **不再重复**维护同一套 todo 解析逻辑。
- **后端：** `app/sse/framing.py` + `app/sse/envelope.py`（或等价路径）落地；`main.py` 与 stream adapter **无散落的重复成帧/信封逻辑**；相关 **pytest 全绿**。
- **注册表：** 每个已登记的系统工具在 `tool_call` SSE 上带有与注册表一致的 `toolPresentation`（及在适用时的 `parameterControl`）；**未知工具**触发可观测日志（及可选 dev 告警）。

## Open questions

- **后端 4 与 5 是否同一 PR？** 可 **拆分 PR**（先 `app/sse` 再注册表，或相反），但两者均属 **本交付范围**，不得标记为「以后再说」而无限期跳过；顺序见 `design.md` **Implementation order**。
- **未知 `toolName` 的 DEFAULT：** 当前产品倾向 **默认 `action`**（避免悄悄吞掉重要步骤）；若改为默认 `state`，须在 `design.md` ADR 写明风险与回滚。
- **Mockups？** 本交付以无视觉改版为主；见 `acceptance-ui.md` 与 `design.md` Mockups 节。
