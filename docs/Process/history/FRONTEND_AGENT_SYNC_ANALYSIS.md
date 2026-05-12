# 前端对话框与 Agent 工作流程同步分析

> **2026-03 更新（unify-agent-sse-timeline）**：后端 SSE 事件带 `schemaVersion` / `seq` / `scope`；前端 `useStreamingAnalysisMulti` 将非 `internal` 事件追加到 `PerProjectStreamingState.timeline`，并在落库时写入 `messages.timeline`（需执行迁移 `20260324120000_messages_timeline.sql`）。统一时间线 UI（仅按 `timeline` 渲染、Thinking 与 Reasoning 解耦等）仍在演进，见 `openspec/changes/unify-agent-sse-timeline/`。

## 目标流程对照

| 目标步骤 | 描述 | 实现状态 | 说明 |
|---------|------|----------|------|
| 1 | 提交请求，对话框显示请求内容 | ✅ 已达成 | `userInput` + `inputTimestamp`，`ChatMessage type="user"` |
| 2 | Thinking 动画（主 Agent 开始工作） | ✅ 已达成 | `isThinkingPhase = isAnalyzing && !taskPlan`，`ChatMessage isThinking={true}` |
| 3 | 展示 Thinking 过程内容（主 Agent 开始 LLM） | ✅ 已达成 | `reasoning` 事件 → `currentReasoning`，Reasoning Process 可折叠展示 |
| 4 | 展示 Thinking 结果（直接回复则流程结束） | ✅ 已达成 | `conclusion` 事件 → `replyContent`（无 taskPlan 时） |
| 5 | 如果是任务，展示任务列表 | ✅ 已达成 | `write_todos` → `task_plan` → `taskPlan`，`TaskExecutionPanel` |
| 6 | 任务列表执行并更新状态 | ⚠️ 部分达成 | `task_start`/`task_complete` 有，子 Agent 内部步骤无 |
| 7 | 任务结束：对话展示摘要，右侧展示详细结果 | ⚠️ 部分达成 | 摘要有，右侧 blocks 依赖 conclusion 格式 |

---

## 详细分析

### 1. 提交请求，对话框显示请求内容 ✅

- **前端**：`analyzeInput` 时设置 `userInput`、`inputTimestamp`
- **展示**：`ReasoningPanel` 中 `ChatMessage type="user"` 展示用户输入
- **结论**：实现正确

### 2. Thinking 动画 ✅

- **前端**：`isThinkingPhase = isAnalyzing && !taskPlan`，在 `taskPlan` 出现前显示 Thinking 动画
- **展示**：`ChatMessage isThinking={true}` 显示动画
- **结论**：与「主 Agent 开始工作」阶段对应

### 3. 展示 Thinking 过程内容 ✅

- **后端**：`adapt_astream_to_sse` 从 AIMessage 提取 thinking/text，发出 `reasoning` 事件
- **前端**：`reasoning` → `currentReasoning`，`ReasoningPanel` 中「Reasoning Process」可折叠展示
- **结论**：主 Agent LLM 思考过程可正确展示

### 4. 展示 Thinking 结果（直接回复） ✅

- **后端**：主 Agent 纯文本回复时发出 `conclusion`
- **前端**：`replyContent={!taskPlan ? conclusion : undefined}`，无任务时在对话区展示结论
- **结论**：直接回复流程正确

### 5. 展示任务列表 ✅

- **后端**：主 Agent 调用 `write_todos` 时，`adapt_astream_to_sse` 发出 `task_plan`
- **前端**：`handleTaskPlan` 更新 `taskPlan`，`TaskExecutionPanel` 展示任务列表
- **结论**：任务列表展示正确

### 6. 任务执行与状态更新 ⚠️

**已实现：**

- `task_start`：当前任务标为 running
- `task_complete`：任务标为 success
- `step`：子 Agent 调用时发出 `task-running-{id}` 等步骤

**缺失：**

- 子 Agent 内部 `skill_start`、`skill_complete`、`workflow_step` 等事件未流式传到前端
- 当前 `adapt_astream_to_sse` 只处理主 Agent 的 `astream`，子 Agent 通过 `task()` 调用时，其内部执行过程不经过该适配器
- `adapt_subagent_astream_to_skill_events` 存在但未接入主流程
- 因此：任务级状态有，子 Agent 内部步骤级进度无

### 7. 任务结束：摘要 + 右侧详细结果 ⚠️

**对话区摘要：**

- 后端：`task_summary`（主 Agent 终局 `SM_TASK_DIGEST` 或启发式摘要，与 `conclusion` 同轮）
- 前端：`ReasoningPanel` 中「Execution summary」展示 `taskSummary`
- 结论：摘要展示正确

**右侧工作区详细结果：**

- 后端：`conclusion` 内容为 `final_response`（主 Agent 最后 AIMessage 文本或 task_outputs 拼接）
- 前端：`processConclusion` 根据内容生成 blocks：
  - JSON：生成 summary、log、decoder、intel 等结构化 blocks
  - Markdown/纯文本：生成 `type: 'analysis'` 的单一 block
- 问题：
  1. 主 Agent 的 conclusion 多为自然语言，通常不是 JSON，右侧多为单一 analysis block
  2. 子 Agent 的详细结构化结果（如 IOC、解码等）未单独作为 blocks 传回，而是被主 Agent 整合进文本
  3. 若主 Agent 未按约定输出 JSON，右侧无法得到细粒度 blocks

**Todo 清空：**

- 后端：每次新请求前 `aupdate_state(config, {"todos": []})` 清空 todos
- 前端：新分析开始时 `reset` 清空 `taskPlan`，无单独的「todo 已清空」展示
- 结论：逻辑正确，但无显式「清空」提示

---

## 架构层面的差异

### 当前 DeepAgent 流程（无独立意图理解）

```
用户输入 → 主 Agent astream（意图理解 + 规划 + 执行一体化）
         → adapt_astream_to_sse
         → step, reasoning, task_plan, task_start, task_complete, conclusion, done
```

- 无单独的 `understanding` 事件：意图理解在主 Agent 首轮 LLM 内完成，未单独暴露
- 前端有 `handleUnderstanding`，但当前后端不会发出 `understanding`

### 旧流程（IntentUnderstandingMiddleware）

- 有独立意图理解阶段，可发出 `understanding`、`parameter_request` 等
- 当前主流程已不再使用该路径

---

## 改进建议

### 高优先级

1. **子 Agent 步骤可见性**  
   - 在 SubAgentMiddleware 调用子 Agent 时，接入 `adapt_subagent_astream_to_skill_events`  
   - 将 `skill_start`、`skill_complete`、`workflow_step` 等事件并入主 SSE 流  
   - 前端已有 `handleWorkflowStep`，只需后端补齐事件

2. **右侧工作区 blocks 来源**  
   - 方案 A：要求子 Agent 返回结构化 JSON，由主 Agent 或中间件汇总后通过 `blocks` 事件下发  
   - 方案 B：在 `conclusion` 之外增加 `blocks` 事件，专门承载工作区 blocks  
   - 方案 C：在 MASTER_AGENT 中明确要求主 Agent 在任务型回复时输出约定 JSON 结构

### 中优先级

3. **Understanding 展示（可选）**  
   - 若需展示「意图理解」阶段，可在主 Agent 首轮 LLM 返回后解析并发出 `understanding` 事件  
   - 或在主 Agent prompt 中要求输出结构化 understanding，再在适配器中转换为事件

4. **任务结束时的 Todo 清空提示**  
   - 在流结束时发出 `plan_complete` 或 `todos_cleared`  
   - 前端可据此显示「任务已全部完成」等提示

### 低优先级

5. **Markdown 结论的 blocks 增强**  
   - 对非 JSON 的 markdown 结论做简单解析（标题、列表等），生成更细粒度的 blocks

---

## 总结

| 目标 | 状态 | 备注 |
|------|------|------|
| 1. 请求展示 | ✅ | 正常 |
| 2. Thinking 动画 | ✅ | 正常 |
| 3. Thinking 过程内容 | ✅ | 正常 |
| 4. 直接回复结论 | ✅ | 正常 |
| 5. 任务列表 | ✅ | 正常 |
| 6. 任务执行与状态 | ⚠️ | 任务级有，子 Agent 步骤级无 |
| 7. 摘要 + 右侧详细结果 | ⚠️ | 摘要有，右侧依赖 conclusion 格式，子 Agent 详细结果未单独传递 |

整体上，对话区与主 Agent 流程的同步已基本到位，主要差距在：  
1）子 Agent 内部步骤的实时展示；  
2）右侧工作区 blocks 的结构化与细粒度来源。
