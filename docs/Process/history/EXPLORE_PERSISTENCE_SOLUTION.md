# Explore 过程保存到历史记录的解决方案

## 现状

- **流式分析时**：`StreamEventRenderer` 展示 reasoning + explore 列表（web_search、read_file 等工具调用）
- **分析完成后**：`resetForProject` 清空状态，界面切换到对话历史
- **历史记录**：只保存 reasoning、taskPlan、taskSummary 等，**不保存 streamEvents**，因此 explore 列表在历史中不可见

## 方案概览

将 `streamEvents` 存入 `thinking_steps.__extended`，与 taskPlan、understanding、taskSummary 一致，无需改 DB schema。

---

## 一、后端修改

### 1.1 `message_persistence.py`：从 events 提取 stream_events

在 `_build_state_from_events` 中收集 tool_call、tool_result、task_start、task_complete，并转为前端 `StreamEvent` 格式：

```python
# 在 _build_state_from_events 中新增
EXPLORE_TOOLS = frozenset({"web_search", "scrape_url", "read_file", "grep", "glob", "ls"})

def _extract_stream_events(events: list[dict]) -> list[dict]:
    """Build stream_events list from raw events (matches frontend StreamEvent format)."""
    stream_events: list[dict] = []
    for i, ev in enumerate(events):
        t = ev.get("type")
        if t == "tool_call":
            if ev.get("toolName") == "write_todos":
                continue  # Skip write_todos like frontend
            stream_events.append({
                "type": "tool_call",
                "id": ev.get("id") or f"tc-{ev.get('timestamp', 0)}",
                "timestamp": ev.get("timestamp"),
                "toolName": ev.get("toolName"),
                "toolInput": ev.get("toolInput"),
            })
        elif t == "tool_result":
            stream_events.append({
                "type": "tool_result",
                "id": ev.get("id") or f"tr-{ev.get('timestamp', 0)}",
                "timestamp": ev.get("timestamp"),
                "toolName": ev.get("toolName"),
                "toolOutput": ev.get("toolOutput"),
            })
        elif t == "task_start":
            stream_events.append({
                "type": "task_start",
                "id": ev.get("id"),
                "taskId": ev.get("id"),
                "timestamp": ev.get("timestamp"),
            })
        elif t == "task_complete":
            stream_events.append({
                "type": "task_complete",
                "id": ev.get("id"),
                "taskId": ev.get("id"),
                "taskStatus": "success",
                "timestamp": ev.get("timestamp"),
            })
    return stream_events
```

在 `_build_state_from_events` 的 for 循环后添加：

```python
stream_events = _extract_stream_events(events)
```

在 `return` 的 state 中增加 `"stream_events": stream_events`。

### 1.2 `message_persistence.py`：写入 `__extended`

在 `_extended_thinking_steps` 中增加 `streamEvents`：

```python
def _extended_thinking_steps(state: dict) -> dict:
    return {
        "steps": state["thinking_steps"],
        "__extended": {
            "taskPlan": state.get("task_plan"),
            "understanding": state.get("understanding"),
            "taskSummary": state.get("task_summary"),
            "workspaceTitle": state.get("workspace_title") or None,
            "streamEvents": state.get("stream_events") or [],  # 新增
        },
    }
```

---

## 二、前端修改

### 2.1 `types/project.ts`：ConversationMessage 增加 streamEvents

```typescript
export interface ConversationMessage {
  // ... 现有字段
  streamEvents?: StreamEvent[];  // 新增
}
```

### 2.2 `buildConversationMessages.ts`：写入 streamEvents

在 `assistantMsg` 中增加：

```typescript
const assistantMsg: ConversationMessage = {
  // ... 现有字段
  streamEvents: cloneSnapshot(state.streamEvents ?? []),
};
```

在 `snapshot` 中增加 `streamEvents: cloneSnapshot(state.streamEvents ?? [])`。

在 `if (!hasReasoning && !hasBlocks && ...)` 中增加 `hasStreamEvents` 判断（可选，用于提前返回）。

### 2.3 `useConversationPersistence.ts`：PersistenceState 与 assistantMsg

- 在 `PersistenceState` 中增加 `streamEvents?: StreamEvent[]`
- 在 `snapshot` 中增加 `streamEvents: cloneSnapshot(state.streamEvents ?? [])`
- 在 `assistantMsg` 中增加 `streamEvents: snapshot.streamEvents ?? []`

注意：`useConversationPersistence` 的 `state` 来自 `onProjectAnalysisComplete` 等，需确保传入的 state 包含 `streamEvents`。当前 `persistProjectAnalysis` 由 `useStreamingAnalysisMulti` 的 `onProjectAnalysisComplete` 触发，而实际持久化由后端完成，前端 `useConversationPersistence` 可能只做 append。需要确认调用链是否传入 `streamEvents`。

### 2.4 `useProjects.ts`：reloadProjectMessages 解析 streamEvents

在 `reloadProjectMessages` 的 `loaded` 映射中，从 `__extended` 读取 `streamEvents`：

```typescript
const extendedData = thinkingSteps?.__extended || {};
return {
  // ... 现有字段
  streamEvents: extendedData.streamEvents ?? [],
};
```

### 2.5 `CommandCenter.tsx`：历史 turn 渲染 StreamEventRenderer

在对话历史的 turn 渲染中，当 `turn.assistant.streamEvents?.length > 0` 或 `turn.assistant.reasoning` 时，增加 `StreamEventRenderer`：

```tsx
{/* 历史 turn 中的 reasoning + explore */}
{(turn.assistant.reasoning || (turn.assistant.streamEvents?.length ?? 0) > 0) && (
  <section className="animate-fade-in mt-2">
    <StreamEventRenderer
      reasoningContent={turn.assistant.reasoning || ''}
      events={turn.assistant.streamEvents ?? []}
      taskPlan={turn.assistant.taskPlan}
      isStreaming={false}
    />
  </section>
)}
```

插入位置：在 `ReasoningPanel` 之后、`taskPlan` 的 `TaskExecutionPanel` 之前。

---

## 三、数据流说明

1. **流式分析**：`useStreamingAnalysisMulti` 收集 tool_call、tool_result 等 → `streamEvents`
2. **分析完成**：`buildConversationMessages(state)` 生成含 `streamEvents` 的 assistantMsg → `appendToConversation`
3. **后端持久化**：`persist_analysis_result` 从 `collected_events` 提取 `stream_events` → 写入 `thinking_steps.__extended.streamEvents`
4. **刷新/重载**：`reloadProjectMessages` 从 API 的 `thinking_steps.__extended` 解析 `streamEvents`
5. **历史展示**：`CommandCenter` 对含 `streamEvents` 的 turn 渲染 `StreamEventRenderer`

---

## 四、注意事项

1. **DB 兼容**：`thinking_steps` 为 JSONB，`__extended` 可自由扩展，无需迁移
2. **旧数据**：历史消息无 `streamEvents` 时，`extendedData.streamEvents` 为 `undefined`，使用 `?? []` 即可
3. **体积**：`toolOutput` 可能较大，可按需截断（如 `maxResultPreview`）或只存 explore 相关事件

---

## 五、实施顺序建议

1. 后端：`_extract_stream_events` + `_build_state_from_events` + `_extended_thinking_steps`
2. 前端：`ConversationMessage.streamEvents` + `buildConversationMessages` + `reloadProjectMessages`
3. 前端：`CommandCenter` 历史 turn 中渲染 `StreamEventRenderer`
