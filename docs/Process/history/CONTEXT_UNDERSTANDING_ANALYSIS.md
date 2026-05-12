# 上下文理解能力分析

## 用户需求场景

1. **查询历史结果**："前面几次需求执行的结果是什么？"
2. **合并结果**："把这些结果合并成一个文档"
3. **引用历史**："基于上次的分析结果，继续深入"

## 当前系统能力分析

### ✅ 已具备的能力

#### 1. 短期记忆（Short-term Memory）
- **位置**：`ContextRetriever._session_history`
- **容量**：最近 20 条交互记录（可配置）
- **内容**：意图理解结果、用户输入摘要
- **获取方式**：`get_short_term_context(session_id)`

#### 2. 长期记忆（Long-term Memory）
- **位置**：`StoreBackend` (namespace: `memories/{session_id}`)
- **存储**：持久化存储，支持跨会话
- **搜索**：
  - 精确关键词匹配
  - 模糊匹配（Jaccard 相似度）
  - 最近 N 条记录
- **获取方式**：`get_long_term_context(session_id, key, query, limit)`

#### 3. 上下文摘要（Context Summary）
- **功能**：`get_context_summary(session_id, language)`
- **提取内容**：
  - 关键实体（IOCs, IPs, domains, hashes, filenames）
  - 分析过的文件列表（最多 5 个）
  - 用户偏好（语言、任务类型）
  - 最近交互摘要（最多 5 条，每条最多 80 字符）

### ❌ 当前不足

#### 1. 历史结果查询能力不足
- **问题**：`get_context_summary()` 只显示最近 5 条摘要，且只显示前 80 个字符
- **影响**：无法完整展示历史任务执行结果
- **示例**：
  ```python
  # 当前实现
  summaries.append(f"  - [{category}] {summary[:80]}")  # 只显示 80 字符
  ```

#### 2. 任务结果保存机制缺失
- **问题**：只保存意图理解结果，不保存任务执行结果
- **当前保存**：
  ```python
  # 只保存意图理解结果
  self.context_retriever.add_to_short_term(session_id, {
      "type": "intent_result",
      "category": result.task_category.value,
      "summary": result.summary,  # 只有摘要
      ...
  })
  ```
- **缺失**：任务执行结果、分析报告、生成的文件等

#### 3. 意图识别能力不足
- **问题**：无法识别"查询历史结果"、"合并结果"这类意图
- **当前分类**：只有 `SECURITY`, `RESEARCH`, `UNKNOWN`, `PARAMETER_NEEDED`
- **缺失**：`HISTORY_QUERY`, `RESULT_MERGE` 等任务类型

#### 4. 结果合并功能缺失
- **问题**：没有合并多个任务结果的功能
- **缺失**：
  - 识别需要合并的历史结果
  - 提取多个结果的内容
  - 合并成文档的逻辑

## 改进方案

### 方案 1：增强上下文摘要（短期方案）

**目标**：在现有框架内增强历史结果展示能力

**改进点**：
1. 增加历史摘要长度限制（从 80 字符增加到 500 字符）
2. 增加历史记录数量（从 5 条增加到 10-20 条）
3. 添加任务结果标识（区分意图理解结果和任务执行结果）

**实现**：
```python
def _extract_recent_summaries(self, history: list[dict], language: str = "en", limit: int = 10) -> list[str]:
    """Extract recent interaction summaries with full content."""
    summaries = []
    
    for entry in history[-limit:]:
        entry_type = entry.get("type", "unknown")
        summary = entry.get("summary", "")
        category = entry.get("category", "")
        
        # 增加长度限制，支持完整结果展示
        if entry_type == "task_result":
            # 任务执行结果：显示完整内容（最多 500 字符）
            summaries.append(f"  - [Task Result: {category}] {summary[:500]}")
        elif entry_type == "intent_result":
            # 意图理解结果：显示摘要（最多 200 字符）
            summaries.append(f"  - [Intent: {category}] {summary[:200]}")
        else:
            summaries.append(f"  - [{entry_type}] {summary[:200]}")
    
    return summaries
```

### 方案 2：添加任务结果保存机制（中期方案）

**目标**：在任务执行完成后，保存完整结果到长期记忆

**实现**：
```python
async def save_task_result(
    self,
    session_id: str,
    task_id: str,
    task_category: str,
    result_content: str,
    metadata: dict | None = None
):
    """Save task execution result to long-term memory.
    
    Args:
        session_id: Session ID
        task_id: Unique task identifier
        task_category: Task category (security/research/etc.)
        result_content: Full task result content
        metadata: Additional metadata (timestamp, files, etc.)
    """
    key = f"task_result_{task_id}"
    value = {
        "task_id": task_id,
        "category": task_category,
        "content": result_content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **metadata or {}
    }
    
    await self.context_retriever.save_to_long_term(
        session_id,
        key,
        value,
        encrypted=False,
        metadata={
            "type": "task_result",
            "category": task_category,
            "access_count": 0,
        }
    )
```

### 方案 3：增强意图识别（中期方案）

**目标**：识别"查询历史"、"合并结果"等新意图类型

**实现**：
```python
class TaskCategory(str, Enum):
    """Task category enumeration."""
    SECURITY = "security"
    RESEARCH = "research"
    UNKNOWN = "unknown"
    PARAMETER_NEEDED = "parameter_needed"
    # 新增
    HISTORY_QUERY = "history_query"      # 查询历史结果
    RESULT_MERGE = "result_merge"        # 合并结果
    RESULT_EXPORT = "result_export"      # 导出结果
```

**Phase 1 提示词增强**：
- 添加历史查询意图识别
- 添加结果合并意图识别
- 识别用户提到的"前面几次"、"合并"、"文档"等关键词

### 方案 4：实现结果查询和合并功能（长期方案）

**目标**：完整支持历史结果查询和合并

**功能模块**：

#### 4.1 历史结果查询工具
```python
async def query_task_results(
    self,
    session_id: str,
    query: str = "",
    category: str = "",
    limit: int = 10
) -> list[dict]:
    """Query historical task results.
    
    Args:
        session_id: Session ID
        query: Search query (fuzzy matching)
        category: Filter by task category
        limit: Maximum number of results
    
    Returns:
        List of task results matching the query
    """
    # 1. 从长期记忆查询
    results = await self.context_retriever.get_long_term_context(
        session_id,
        key=f"task_result_{category}" if category else "",
        query=query,
        limit=limit
    )
    
    # 2. 过滤任务结果
    task_results = [
        r for r in results 
        if r.get("metadata", {}).get("type") == "task_result"
    ]
    
    return task_results
```

#### 4.2 结果合并工具
```python
async def merge_task_results(
    self,
    session_id: str,
    task_ids: list[str] | None = None,
    query: str = "",
    output_format: str = "markdown"
) -> str:
    """Merge multiple task results into a single document.
    
    Args:
        session_id: Session ID
        task_ids: Specific task IDs to merge (if None, use query)
        query: Query to find tasks to merge
        output_format: Output format (markdown/pdf/docx)
    
    Returns:
        Merged document content
    """
    # 1. 获取要合并的结果
    if task_ids:
        results = []
        for task_id in task_ids:
            result = await self.context_retriever.get_long_term_context(
                session_id,
                key=f"task_result_{task_id}",
                limit=1
            )
            if result:
                results.extend(result)
    else:
        results = await self.query_task_results(session_id, query=query)
    
    # 2. 合并内容
    merged_parts = []
    for i, result in enumerate(results, 1):
        content = result.get("value", {}).get("content", "")
        category = result.get("value", {}).get("category", "")
        timestamp = result.get("value", {}).get("timestamp", "")
        
        merged_parts.append(f"## Task {i}: {category}")
        merged_parts.append(f"**Time**: {timestamp}")
        merged_parts.append(f"\n{content}\n")
        merged_parts.append("---\n")
    
    merged_content = "\n".join(merged_parts)
    
    # 3. 根据格式生成文档
    if output_format == "markdown":
        return merged_content
    elif output_format == "pdf":
        # 使用报告生成工具转换为 PDF
        return await self._convert_to_pdf(merged_content)
    # ... 其他格式
    
    return merged_content
```

#### 4.3 意图理解增强
在 Phase 1 提示词中添加：
```
## Intent Recognition

The user may ask to:
- Query previous task results: "前面几次需求执行的结果", "show me previous analysis"
- Merge results: "把这些结果合并成一个文档", "combine all results into one document"
- Export results: "导出所有结果", "export to PDF"

If the user mentions:
- "前面几次" / "previous" / "history" → task_category: "history_query"
- "合并" / "merge" / "combine" → task_category: "result_merge"
- "导出" / "export" / "文档" / "document" → task_category: "result_export"
```

## 实施优先级

### 阶段 1：快速改进（1-2 天）
1. ✅ 增加历史摘要长度（80 → 500 字符）
2. ✅ 增加历史记录数量（5 → 10-20 条）
3. ✅ 添加任务结果类型标识

### 阶段 2：核心功能（3-5 天）
1. ✅ 实现任务结果保存机制
2. ✅ 添加历史结果查询工具
3. ✅ 增强意图识别（添加 HISTORY_QUERY, RESULT_MERGE）

### 阶段 3：完整功能（1-2 周）
1. ✅ 实现结果合并功能
2. ✅ 支持多种输出格式（Markdown/PDF/DOCX）
3. ✅ 添加结果导出功能

## 当前状态总结

| 功能 | 当前能力 | 改进后能力 |
|------|---------|-----------|
| 查询历史结果 | ⚠️ 部分支持（只显示最近 5 条，80 字符） | ✅ 完整支持（10-20 条，500 字符） |
| 保存任务结果 | ❌ 不支持 | ✅ 支持完整结果保存 |
| 识别查询意图 | ❌ 不支持 | ✅ 支持 HISTORY_QUERY |
| 识别合并意图 | ❌ 不支持 | ✅ 支持 RESULT_MERGE |
| 合并结果 | ❌ 不支持 | ✅ 支持多格式合并 |
| 导出文档 | ❌ 不支持 | ✅ 支持 Markdown/PDF/DOCX |

## 结论

**当前系统部分支持上下文理解，但不足以满足用户需求。**

**主要问题**：
1. 历史结果展示不完整（只显示摘要，不显示完整内容）
2. 没有专门的任务结果保存机制
3. 无法识别"查询历史"、"合并结果"这类意图
4. 没有结果合并功能

**建议**：按照上述三个阶段逐步实施改进，优先完成阶段 1 的快速改进，然后逐步实现核心功能和完整功能。
