# 诊断测试结论

基于 `tests/test_aimessage_and_events.py` 的测试结果与代码分析。

---

## 1. AIMessage 为何不包含 thinking/text？

### 测试结果

```
Model: gemini-2.5-flash
content type: <class 'str'>   # 纯字符串，非 block 列表
additional_kwargs keys: []
_extract_thinking_and_text: thinking=(empty), text='The IP address...'
[CONCLUSION] No thinking - model may not have thinking enabled (Gemini needs include_thoughts)
```

### 根因

- **模型类型**：当前默认 `google/gemini-2.5-flash`（或 gemini-3-flash-preview）
- **API 配置**：`get_model()` 中 ChatGoogleGenerativeAI 未传入 `thinking_budget` 或 `include_thoughts`
- **Anthropic 对比**：Anthropic 有 `enable_anthropic_thinking`，会传 `thinking={"type":"enabled","budget_tokens":10000}`；Gemini 无对应配置
- **结论**：Gemini 的 thinking 需显式开启，否则只返回纯文本，不返回 thought 块

### 修复方向

在 [deep_agent.py](python-agent-service/app/agents/deep_agent.py) 的 `get_model()` 中，为 Google/Gemini 增加 thinking 配置，例如：

```python
# ChatGoogleGenerativeAI 支持 thinking_budget（langchain-google PR #884）
return ChatGoogleGenerativeAI(
    model=bare_model,
    google_api_key=settings.google_api_key,
    thinking_budget=8192,  # 或 include_thoughts=True，视 SDK 版本而定
)
```

需查阅当前 `langchain-google-genai` 版本支持的参数名（`thinking_budget` / `include_thoughts`）。

---

## 2. 任务列表：write_todos 已收到，为何对话窗口不展示？

### 测试结果

```
write_todos -> task_plan 映射正常：
- task_plan events: 1
- tool_call write_todos events: 1
- task_plan.plan.tasks: 2 条（id=0,1, title, status=pending）
```

### 分析

- 后端：当 `write_todos` 在 tool_calls 中时，adapter 会发出 `task_plan` 和 `tool_call`
- 前端：仅对 `event.type === 'task_plan'` 调用 `handleTaskPlan`，**不会**从 `tool_call` 中解析 plan
- 若 `task_plan` 因某种原因未到达或格式异常，前端无法从 `tool_call` 兜底

### 修复方向

1. **前端兜底**：在 `case 'tool_call'` 中，当 `event.toolName === 'write_todos'` 且 `event.toolInput?.todos` 存在时，将 `toolInput` 转成 `plan` 格式并调用 `handleTaskPlan`，保证有 write_todos 时一定能展示任务列表
2. **后端兼容**：支持 `todos` / `tasks`、`content` / `task` 等字段，避免因格式差异导致 `raw_todos` 为空

---

## 3. 摘要内容来源与截断

### 代码逻辑（当前）

```python
# final_message_split：从主 Agent 最后 AIMessage 解析
#   ## SM_FULL_REPORT ... ## SM_TASK_DIGEST ...  (report-first; legacy digest-first also accepted)
# 失败时用 heuristic_digest_and_report（无第二次 LLM）

# task_summary：digest 段（或启发式短摘要）
yield {"type": "task_summary", "summary": summary_text}

# conclusion：SM_FULL_REPORT 段（或启发式后的正文）
yield {"type": "conclusion", "content": conclusion_body}
```

### 结论

- **task_summary** / **conclusion**：均来自**同一次**主 Agent 终局生成（锚点切分或启发式）；**无**独立 `task_multi_summary` 调用。
- **conclusion** 不再等于整段 raw `latest_ai_text`（有锚点时仅为 report 节）。

### 历史说明

早期版本曾用子 task 输出拼接或单独 LLM 生成 `task_summary`；已废弃，以 `MASTER_AGENT.md` 与 `final_message_split.py` 为准。
