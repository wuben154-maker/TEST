# 上下文任务执行分析

## 问题描述

用户提出了一个关键问题：**上下文相关的任务（如查询历史结果、合并结果）应该如何执行？**

### 示例场景

1. **历史查询**："上一次邮件里面的IOC是什么？"
2. **结果合并**："帮我合并某两次任务执行结果的内容"

### 当前问题

**当前系统只支持两种任务类型**：
- `TaskType.SECURITY` → 调用安全子智能体（skill 流程）
- `TaskType.RESEARCH` → 调用研究智能体

**上下文任务的问题**：
- 意图理解会生成 `expertise_needed == "general"` 的任务
- 当前代码会将 `expertise_needed == "general"` 的任务归类为 `TaskType.SECURITY`
- 但上下文任务不应该走 skill 流程，应该直接调用 `ContextRetriever` 的方法

---

## 当前实现分析

### 1. 任务类型定义

**位置**：`task_planner.py:32-35`

```python
class TaskType(str, Enum):
    """任务类型。"""
    SECURITY = "security"  # 安全专有任务 - 走 skill 流程
    RESEARCH = "research"  # 通用任务 - 走 Deep Researcher
```

**问题**：缺少 `CONTEXT` 或 `GENERAL` 类型

### 2. 任务规划逻辑

**位置**：`task_planner.py:274-291`

```python
for i, task_desc in enumerate(intent_result.tasks):
    # Determine task type
    task_type = TaskType.SECURITY
    skill_name = task_desc.skill_hint
    
    if task_desc.expertise_needed == "research":
        task_type = TaskType.RESEARCH
        skill_name = None
    elif task_type == TaskType.SECURITY:
        # Use skill_hint if available
        if not skill_name:
            # Fallback to security_subtype mapping
            # ...
```

**问题**：
- 如果 `expertise_needed == "general"`，会被归类为 `TaskType.SECURITY`
- 没有识别上下文任务的逻辑

### 3. 任务执行逻辑

**位置**：`task_planner.py:528-535`

```python
if task.task_type == TaskType.SECURITY:
    # 安全任务 - 使用 skill 流程
    async for event in self._execute_security_task(task, user_input):
        yield event
else:
    # 研究任务 - 使用 Deep Researcher
    async for event in self._execute_research_task(task, user_input):
        yield event
```

**问题**：
- 没有处理上下文任务的执行逻辑
- 上下文任务会被错误地路由到安全任务或研究任务

### 4. ContextRetriever 已有方法

**位置**：`context_retriever.py`

已有方法：
- `get_conversation_history()` - 获取对话历史
- `search_conversations()` - 搜索对话
- `get_analysis_results()` - 获取分析结果
- `merge_analysis_results()` - 合并分析结果

**问题**：这些方法没有被任务执行器调用

---

## 解决方案

### 方案 1：添加 CONTEXT 任务类型（推荐）

#### 1.1 扩展 TaskType 枚举

```python
class TaskType(str, Enum):
    """任务类型。"""
    SECURITY = "security"  # 安全专有任务 - 走 skill 流程
    RESEARCH = "research"  # 通用任务 - 走 Deep Researcher
    CONTEXT = "context"    # 上下文任务 - 直接调用 ContextRetriever
```

#### 1.2 在任务规划阶段识别上下文任务

**位置**：`TaskPlanner._create_plan_from_intent_tasks()`

```python
for i, task_desc in enumerate(intent_result.tasks):
    # Determine task type
    task_type = TaskType.SECURITY
    skill_name = task_desc.skill_hint
    
    # Check if this is a context-related task
    if task_desc.expertise_needed == "general":
        # Check context_needed to determine if it's a context task
        context_needed = task_desc.context_needed or []
        if any(keyword in ["session_history", "previous_results", "conversation_history"] 
               for keyword in context_needed):
            task_type = TaskType.CONTEXT
            skill_name = None
        elif task_desc.description.lower().startswith(("query", "get", "retrieve", "find")):
            # History query patterns
            if any(keyword in task_desc.description.lower() 
                   for keyword in ["previous", "last", "history", "earlier"]):
                task_type = TaskType.CONTEXT
                skill_name = None
        elif "merge" in task_desc.description.lower() or "combine" in task_desc.description.lower():
            # Result merging patterns
            task_type = TaskType.CONTEXT
            skill_name = None
    elif task_desc.expertise_needed == "research":
        task_type = TaskType.RESEARCH
        skill_name = None
    elif task_type == TaskType.SECURITY:
        # ... existing security task logic ...
```

#### 1.3 添加上下文任务执行方法

**位置**：`TaskExecutor` 类

```python
async def _execute_context_task(
    self,
    task: PlannedTask,
    user_input: str,
    session_id: str,
) -> AsyncGenerator[dict, None]:
    """执行上下文任务 - 查询历史或合并结果。
    
    支持的任务类型：
    1. 历史查询：查询之前的分析结果
    2. 结果合并：合并多个分析结果
    3. 上下文检索：检索相关上下文信息
    """
    import time
    
    logger.info(
        "Executing context task",
        task_id=task.id,
        description=task.description,
    )
    
    task_start = time.time()
    
    try:
        # Parse task description to determine action
        desc_lower = task.description.lower()
        
        # 1. History Query
        if any(keyword in desc_lower for keyword in ["query", "get", "retrieve", "find", "what", "show"]):
            # Extract query parameters from description
            # Example: "What were the IOCs in the previous email analysis?"
            # Example: "Get the results from the last task"
            
            # Get conversation history
            from app.middleware.context_retriever import ContextRetriever
            # Note: ContextRetriever should be passed to TaskExecutor
            context_retriever = self.context_retriever
            
            yield {
                "type": "step",
                "id": f"context-{task.id}-query",
                "label": "Querying History",
                "status": "running",
                "detail": "Retrieving relevant analysis results...",
            }
            
            # Search conversations
            history = await context_retriever.search_conversations(
                session_id=session_id,
                query=task.description,
                limit=10,
            )
            
            if history:
                # Format results
                result_content = self._format_history_results(history, task.description)
                task.result = result_content
                
                yield {
                    "type": "step",
                    "id": f"context-{task.id}-complete",
                    "label": "Query Complete",
                    "status": "success",
                    "detail": f"Found {len(history)} relevant result(s)",
                }
            else:
                task.result = "No relevant results found in history."
                yield {
                    "type": "step",
                    "id": f"context-{task.id}-not-found",
                    "label": "No Results",
                    "status": "warning",
                    "detail": "No matching results found in conversation history",
                }
        
        # 2. Result Merging
        elif "merge" in desc_lower or "combine" in desc_lower:
            # Extract result IDs from description or context_needed
            # Example: "Merge the results from task 1 and task 2"
            
            yield {
                "type": "step",
                "id": f"context-{task.id}-merge",
                "label": "Merging Results",
                "status": "running",
                "detail": "Combining analysis results...",
            }
            
            # Extract result IDs from task description or use context_needed
            result_ids = self._extract_result_ids(task.description, task.context_needed)
            
            if result_ids:
                merged_result = await context_retriever.merge_analysis_results(
                    session_id=session_id,
                    result_ids=result_ids,
                    language=self.language,
                )
                task.result = merged_result
                
                yield {
                    "type": "step",
                    "id": f"context-{task.id}-merge-complete",
                    "label": "Merge Complete",
                    "status": "success",
                    "detail": f"Merged {len(result_ids)} result(s)",
                }
            else:
                task.result = "Could not identify which results to merge. Please specify result IDs."
                yield {
                    "type": "step",
                    "id": f"context-{task.id}-merge-error",
                    "label": "Merge Error",
                    "status": "error",
                    "detail": "Could not identify result IDs to merge",
                }
        
        # 3. Default: General context retrieval
        else:
            # General context query
            yield {
                "type": "step",
                "id": f"context-{task.id}-retrieve",
                "label": "Retrieving Context",
                "status": "running",
                "detail": "Fetching relevant context...",
            }
            
            # Get context summary
            context_summary = await context_retriever.get_context_summary(
                session_id=session_id,
                language=self.language,
                query=task.description,
            )
            
            task.result = context_summary
            
            yield {
                "type": "step",
                "id": f"context-{task.id}-complete",
                "label": "Context Retrieved",
                "status": "success",
                "detail": "Context information retrieved",
            }
        
    except Exception as e:
        logger.error("Context task execution failed", task_id=task.id, error=str(e))
        task.result = f"Context task encountered an error: {str(e)}"
        yield {
            "type": "error",
            "id": f"context-{task.id}-error",
            "label": "Error",
            "status": "error",
            "detail": task.result,
        }
    
    task.duration_ms = int((time.time() - task_start) * 1000)
    
    # Send reasoning content
    if task.result:
        yield {
            "type": "reasoning",
            "taskId": task.id,
            "content": task.result,
        }
    
    def _format_history_results(self, history: list[dict], query: str) -> str:
        """Format history results for display."""
        parts = [f"## Query Results\n\nQuery: {query}\n\n"]
        
        for idx, entry in enumerate(history, 1):
            parts.append(f"### Result {idx}\n")
            parts.append(f"**Type**: {entry.get('type', 'N/A')}\n")
            parts.append(f"**Timestamp**: {entry.get('timestamp', 'N/A')}\n")
            
            if entry.get('summary'):
                parts.append(f"**Summary**: {entry['summary']}\n")
            
            if entry.get('content'):
                # Truncate long content
                content = entry['content']
                if len(content) > 500:
                    content = content[:500] + "..."
                parts.append(f"**Content**: {content}\n")
            
            parts.append("\n---\n")
        
        return "\n".join(parts)
    
    def _extract_result_ids(self, description: str, context_needed: list[str]) -> list[str]:
        """Extract result IDs from task description or context_needed."""
        # Try to extract from description (e.g., "task 1", "result 2")
        import re
        
        # Pattern: "task 1", "result 2", "analysis 3"
        patterns = [
            r'task\s+(\d+)',
            r'result\s+(\d+)',
            r'analysis\s+(\d+)',
        ]
        
        result_ids = []
        for pattern in patterns:
            matches = re.findall(pattern, description.lower())
            result_ids.extend(matches)
        
        # If no IDs found, try to use context_needed
        if not result_ids and context_needed:
            # Assume context_needed contains result references
            # This is a simplified implementation
            pass
        
        return result_ids
```

#### 1.4 更新任务执行路由

**位置**：`TaskExecutor.execute_plan_stream()`

```python
try:
    if task.task_type == TaskType.SECURITY:
        # 安全任务 - 使用 skill 流程
        async for event in self._execute_security_task(task, user_input):
            yield event
    elif task.task_type == TaskType.RESEARCH:
        # 研究任务 - 使用 Deep Researcher
        async for event in self._execute_research_task(task, user_input):
            yield event
    elif task.task_type == TaskType.CONTEXT:
        # 上下文任务 - 直接调用 ContextRetriever
        async for event in self._execute_context_task(task, user_input, session_id):
            yield event
    else:
        # Unknown task type - fallback to security
        logger.warning("Unknown task type, falling back to security", task_type=task.task_type)
        async for event in self._execute_security_task(task, user_input):
            yield event
```

#### 1.5 更新 TaskExecutor 初始化

**位置**：`TaskExecutor.__init__()`

```python
def __init__(
    self,
    security_agent: Any,  # SubAgentMiddleware
    research_agent: Any,  # DeepResearchAgent
    context_retriever: Any = None,  # ContextRetriever
    session_id: str = "default",  # Session ID for context tasks
    language: str = "en",
):
    """初始化任务执行器。
    
    Args:
        security_agent: 安全子智能体中间件
        research_agent: 深度研究智能体
        context_retriever: 上下文检索器（用于上下文任务）
        session_id: 会话 ID（用于上下文任务）
        language: 语言
    """
    self.security_agent = security_agent
    self.research_agent = research_agent
    self.context_retriever = context_retriever
    self.session_id = session_id
    self.language = language
```

#### 1.6 更新 DeepAgentWithIntent

**位置**：`deep_agent.py`

```python
task_executor = TaskExecutor(
    security_agent=self.subagent_middleware,
    research_agent=self.research_agent,
    context_retriever=self.intent_middleware.context_retriever,  # Add this
    session_id=self.session_id,  # Add this
    language=language,
)
```

---

## 实施步骤

### Phase 1: 扩展任务类型

1. ✅ 添加 `TaskType.CONTEXT` 枚举值
2. ✅ 更新任务规划逻辑，识别上下文任务
3. ✅ 更新任务执行路由，支持上下文任务

### Phase 2: 实现上下文任务执行

1. ✅ 添加 `_execute_context_task()` 方法
2. ✅ 实现历史查询逻辑
3. ✅ 实现结果合并逻辑
4. ✅ 实现通用上下文检索逻辑

### Phase 3: 集成和测试

1. ✅ 更新 `TaskExecutor` 初始化，添加 `context_retriever` 和 `session_id`
2. ✅ 更新 `DeepAgentWithIntent`，传递 `context_retriever`
3. ✅ 测试上下文任务执行

---

## 总结

### 问题

当前系统缺少对上下文相关任务的支持，导致：
- 历史查询任务被错误地路由到安全任务
- 结果合并任务无法执行
- 上下文检索功能未被利用

### 解决方案

**添加 `TaskType.CONTEXT` 任务类型**，并实现 `_execute_context_task()` 方法：
- 识别上下文任务（通过 `expertise_needed == "general"` 和 `context_needed` 字段）
- 执行历史查询、结果合并、上下文检索
- 直接调用 `ContextRetriever` 的相应方法

### 优势

- ✅ 清晰的职责分离（上下文任务 vs 安全任务 vs 研究任务）
- ✅ 复用已有的 `ContextRetriever` 方法
- ✅ 保持现有架构的一致性
- ✅ 易于扩展（可以添加更多上下文任务类型）
