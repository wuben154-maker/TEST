# UI Acceptance — `react-timeline-v0-parity`

## Metadata

- **Slug:** `react-timeline-v0-parity`
- **Updated:** 2026-03-30（Task List 分桶 + 正式回答协议）
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope

- **Screens / routes:** 主分析对话区（`Index` / `CommandCenter` 挂载的推理与消息列表面板）。
- **Components:** 新建 `ReActTimelineView`（或等价）为对话区**唯一**挂载的时间线 UI；旧 `TimelineUnifiedBody` / `ThinkingChain` 等**文件可保留**，但**不得**在同一挂载树中与新版并存；**不包含**物理删除旧文件（由你后续单独要求）。

## Reference assets (`mockups/`)

## Mockups deferred

- **User confirmation:** 用户选择以 **在线参考** [CodeGen 演示](https://v0-webui-ten.vercel.app/) 与本地示例源码目录 `b_lx7WQRylOUg-1774749340024/components/ai-chat-panel.tsx` 为对照，**暂不**向 `mockups/` 提交截图。
- **Phase 6:** `/design-review` 以 `**acceptance-ui.md` 下列标准 + 在线/本地对照** 为主；若后续补充 `mockups/*.png`，在 Reference assets 表中登记路径。


| File (repo-relative) | Description   |
| -------------------- | ------------- |
| —                    | （无）— deferred |


## Visual criteria


| ID   | Criterion                                                                                                   | How to verify                           |
| ---- | ----------------------------------------------------------------------------------------------------------- | --------------------------------------- |
| U-01 | Thinking 与 Reasoning **合并为单一「Thinking」区块**；结构对齐参考：Brain 行 + 可选折叠                                            | 对照 `ai-chat-panel.tsx` 中 Thinking 分支    |
| U-02 | **有推理正文**时折叠可用；**无推理正文**时折叠无效（无展开区或控件不可用）                                                                   | 用仅有 tool、无 reasoning 的 fixture 流验证      |
| U-03 | Thinking 阶段结束后显示 **Thought / 思考了 N 秒**（与现文案 i18n 一致即可）                                                      | 流结束或段结束时可见时长                            |
| U-04 | Thinking 块**下方**展示 **模型正式回答**；内容来自 SSE **`type: answer`**（与终局 **`conclusion`** 区分），**不**与折叠内 `reasoning` 混同 | 联调带 `answer`；无 `answer` 时回答区可为空                    |
| U-05 | **Task List** 样式对齐示例：父行标题 + 左边线子列表 + 完成勾                                                                    | 与参考截图/在线页对比                             |
| U-06 | **同一列表**内，相同**任务 id** 的行随 `write_todos` **更新状态**而非重复堆积                                                      | 勾选/状态变更流                                |
| U-11 | **子代理（或新 `listBucketKey`）** 出现 **另一段** Task List，与主列表**同时**存在于时间线、顺序按 `seq`                                 | 委派 + 子代理 write_todos                    |
| U-07 | **Tool Execution** 对齐示例：父行 + 子行；**不**展示工具返回正文                                                               | 无大段 result 文本；仅有工具名 + 解析出的 path/url     |
| U-08 | 工具展示路径/URL **来自 `toolInput` JSON 解析**，非硬编码单一路径                                                              | spot-check 多种工具 input 键名                |
| U-09 | **时间线顺序**与 SSE `seq` 一致；可出现：Thinking→Tool→Thinking→Task→Tool→摘要                                             | 对照 `design.md` 交错用例 + fixture 测试        |
| U-10 | `**step` 事件**渲染为与 Thinking、Task List **同级**的时间线一项；**无**前端写死「委派子智能体」为唯一来源                                    | 后端仅发 step 时仍显示正确文案（来自 `label`/`detail`） |


## Interaction criteria


| ID   | Criterion                                                                                                              | How to verify    |
| ---- | ---------------------------------------------------------------------------------------------------------------------- | ---------------- |
| I-01 | Thinking 折叠：点击/hover 行为与参考一致（Brain ↔ Chevron）                                                                          | 手动               |
| I-02 | Task / Tool 父行可折叠子列表（若参考实现支持）                                                                                          | 手动               |
| I-03 | 主对话时间线区域 **仅** 渲染新版；**无**旧版 `TimelineUnifiedBody` 链路与新版同时出现在 DOM（可用 React DevTools / 源码搜索 `TimelineUnifiedBody` 挂载点确认） | Code review + 手动 |


## Responsive

- **375 / 768 / 1024：** 时间线不横向溢出；长 URL/path 断行或省略与现有 `ChatMessage` 一致即可（本交付不强制新断行算法）。

## Accessibility

- 折叠控件为 **button** 或带 `aria-expanded`；图标装饰 `aria-hidden` 适当使用。
- 对比度不低于现有主题 tokens。

## Sign-off


| ID        | Result | Verifier | Date | Notes |
| --------- | ------ | -------- | ---- | ----- |
| U-01–U-11 |        |          |      |       |
| I-01–I-03 |        |          |      |       |


