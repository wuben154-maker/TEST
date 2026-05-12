# 上下文任务执行实现总结

## 实现概述

已成功实现上下文任务执行功能，支持历史查询、结果合并和上下文检索。

---

## 实现内容

### 1. 扩展任务类型枚举

**文件**：`python-agent-service/app/middleware/task_planner.py`

**变更**：
```python
class TaskType(str, Enum):
    SECURITY = "security"  # 安全专有任务 - 走 skill 流程
    RESEARCH = "research"  # 通用任务 - 走 Deep Researcher
    CONTEXT = "context"    # 上下文任务 - 直接调用 ContextRetriever (新增)
```

---

### 2. 任务规划阶段识别上下文任务

**位置**：`TaskPlanner._create_plan_from_intent_tasks()`

**识别逻辑**：
1. **检查 `expertise_needed == "general"`**
2. **检查 `context_needed` 字段**：包含 `["session_history", "previous_results", "conversation_history"]`
3. **检查任务描述关键词**：
   - 查询关键词：`["query", "get", "retrieve", "find", "what", "show", "previous", "last", "history", "earlier"]`
   - 合并关键词：`["merge", "combine", "consolidate"]`

**代码逻辑**：
```python
if task_desc.expertise_needed == "general":
    context_needed = task_desc.context_needed or []
    context_keywords = ["session_history", "previous_results", "conversation_history", "history", "results"]
    
    if any(keyword in str(context_needed).lower() for keyword in context_keywords):
        task_type = TaskType.CONTEXT
    elif any(pattern in desc_lower for pattern in query_patterns):
        task_type = TaskType.CONTEXT
    elif any(pattern in desc_lower for pattern in merge_patterns):
        task_type = TaskType.CONTEXT
```

---

### 3. 实现上下文任务执行方法

**位置**：`TaskExecutor._execute_context_task()`

**支持的任务类型**：

#### 3.1 历史查询
- **触发条件**：任务描述包含 `["query", "get", "retrieve", "find", "what", "show", "list"]`
- **执行逻辑**：
  ```python
  history = await self.context_retriever.search_conversations(
      session_id=self.session_id,
      query=task.description,
      limit=10,
  )
  ```
- **输出**：格式化的历史结果

#### 3.2 结果合并
- **触发条件**：任务描述包含 `["merge", "combine", "consolidate"]`
- **执行逻辑**：
  1. 从任务描述中提取结果 ID（支持多种模式）
  2. 如果未指定 ID，使用最近的 2 个结果
  3. 调用 `merge_analysis_results()` 合并结果
- **输出**：合并后的文档

#### 3.3 通用上下文检索
- **触发条件**：不匹配上述两种模式
- **执行逻辑**：
  ```python
  context_summary = await self.context_retriever.get_context_summary(
      session_id=self.session_id,
      language=self.language,
      query=task.description[:100],
  )
  ```
- **输出**：上下文摘要

---

### 4. 辅助方法

#### 4.1 `_format_history_results()`
**功能**：格式化历史查询结果
- 生成 Markdown 格式的报告
- 包含类型、时间戳、摘要、内容
- 自动截断长内容（>500 字符）

#### 4.2 `_extract_result_ids()`
**功能**：从任务描述中提取结果 ID
**支持的模式**：
- `"task 1"`, `"result 2"`, `"analysis 3"`
- `"task id: abc123"`, `"id: abc123"`
- UUID 格式：`"12345678-1234-1234-1234-123456789abc"`

---

### 5. 更新任务执行路由

**位置**：`TaskExecutor.execute_plan_stream()`

**变更**：
```python
if task.task_type == TaskType.SECURITY:
    async for event in self._execute_security_task(task, user_input):
        yield event
elif task.task_type == TaskType.RESEARCH:
    async for event in self._execute_research_task(task, user_input):
        yield event
elif task.task_type == TaskType.CONTEXT:
    async for event in self._execute_context_task(task, user_input):
        yield event  # 新增
else:
    # Fallback to security
    async for event in self._execute_security_task(task, user_input):
        yield event
```

---

### 6. 更新 TaskExecutor 初始化

**位置**：`TaskExecutor.__init__()`

**新增参数**：
```python
def __init__(
    self,
    security_agent: Any,
    research_agent: Any,
    context_retriever: Any = None,  # 新增
    session_id: str = "default",    # 新增
    language: str = "en",
):
    self.context_retriever = context_retriever
    self.session_id = session_id
```

---

### 7. 更新 DeepAgentWithIntent

**位置**：`deep_agent.py`

**变更**：
```python
task_executor = TaskExecutor(
    security_agent=self.subagent_middleware,
    research_agent=self.research_agent,
    context_retriever=self.intent_middleware.context_retriever,  # 新增
    session_id=self.session_id,  # 新增
    language=language,
)
```

---

## 使用示例

### 示例 1：历史查询

**用户输入**："上一次邮件里面的IOC是什么？"

**意图理解结果**：
```json
{
  "intent_description": "User wants to query IOCs from previous email analysis",
  "tasks": [{
    "description": "Query IOCs from previous email analysis",
    "expertise_needed": "general",
    "context_needed": ["session_history", "previous_results"]
  }]
}
```

**执行流程**：
1. 任务规划识别为 `TaskType.CONTEXT`
2. 执行 `_execute_context_task()`
3. 调用 `search_conversations()` 搜索历史
4. 格式化并返回结果

---

### 示例 2：结果合并

**用户输入**："帮我合并某两次任务执行结果的内容"

**意图理解结果**：
```json
{
  "intent_description": "User wants to merge results from two previous tasks",
  "tasks": [{
    "description": "Merge results from task 1 and task 2",
    "expertise_needed": "general",
    "context_needed": ["previous_results"]
  }]
}
```

**执行流程**：
1. 任务规划识别为 `TaskType.CONTEXT`
2. 执行 `_execute_context_task()`
3. 从描述中提取结果 ID（"task 1", "task 2"）
4. 调用 `merge_analysis_results()` 合并结果
5. 返回合并后的文档

---

## 错误处理

### 1. ContextRetriever 不可用
- 返回错误事件
- 记录警告日志

### 2. 历史查询无结果
- 返回警告事件
- 提示用户未找到相关结果

### 3. 结果合并失败
- 尝试使用最近的 2 个结果
- 如果仍然失败，返回错误事件

---

## 测试建议

### 测试用例 1：历史查询
- **输入**："What were the IOCs in the previous email analysis?"
- **预期**：返回历史邮件分析结果中的 IOC

### 测试用例 2：结果合并
- **输入**："Merge the results from the last two tasks"
- **预期**：合并最近两个任务的结果

### 测试用例 3：上下文检索
- **输入**："Show me the context from previous conversations"
- **预期**：返回上下文摘要

### 测试用例 4：错误处理
- **输入**：上下文任务但 `context_retriever` 为 `None`
- **预期**：返回错误事件

---

## 总结

### 实现的功能
- ✅ 扩展任务类型，支持 `CONTEXT` 类型
- ✅ 任务规划阶段识别上下文任务
- ✅ 实现上下文任务执行方法
- ✅ 支持历史查询、结果合并、上下文检索
- ✅ 更新任务执行路由
- ✅ 集成到 `DeepAgentWithIntent`

### 优势
- ✅ 清晰的职责分离（上下文任务 vs 安全任务 vs 研究任务）
- ✅ 复用已有的 `ContextRetriever` 方法
- ✅ 保持现有架构的一致性
- ✅ 易于扩展（可以添加更多上下文任务类型）

### 后续优化建议
- **P1**：增强结果 ID 提取逻辑（支持更多模式）
- **P2**：添加上下文任务的缓存机制
- **P3**：支持上下文任务的并行执行
