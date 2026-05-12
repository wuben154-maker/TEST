# 上下文摘要增强方案

## 当前问题分析

### 现有实现限制

当前 `ContextRetriever.get_context_summary()` 方法存在以下限制：

1. **提取数量限制过严**:
   - 实体：最多10个 (`entities[:10]`)
   - 文件：最多5个 (`files[:5]`)
   - 最近摘要：最多5条 (`limit=5`)
   - 摘要长度：每条最多80-100字符

2. **只使用短期记忆**:
   - 仅从 `get_short_term_context()` 获取数据
   - 未充分利用长期记忆中的相关信息
   - 未考虑历史对话的完整上下文

3. **摘要方式简单**:
   - 使用简单的截断（`[:100]`）
   - 未使用LLM生成智能摘要
   - 未考虑信息重要性排序

4. **缺乏相关性过滤**:
   - 未根据当前查询过滤相关历史
   - 未考虑时间衰减（越近越重要）
   - 未考虑访问频率（常用信息更重要）

## 改进方案

### P0: 基础增强（立即实施）

#### 1. 增加提取数量限制

```python
# 当前
entities[:10]  # 改为 20
files[:5]      # 改为 10
limit=5        # 改为 10
[:100]         # 改为 200
```

**影响**: 最小改动，立即提升摘要信息量

#### 2. 集成长期记忆

```python
async def get_context_summary(
    self, 
    session_id: str, 
    language: str = "en",
    query: str = "",  # 新增：当前查询，用于相关性过滤
    include_long_term: bool = True  # 新增：是否包含长期记忆
) -> str:
    # 1. 获取短期记忆（现有逻辑）
    short_term = self.get_short_term_context(session_id)
    
    # 2. 获取长期记忆（新增）
    long_term = []
    if include_long_term and self.store:
        long_term = await self.get_long_term_context(
            session_id=session_id,
            query=query,  # 使用查询进行相关性过滤
            limit=10
        )
    
    # 3. 合并和去重
    combined_history = self._merge_and_deduplicate(short_term, long_term)
    
    # 4. 生成摘要（使用合并后的历史）
    ...
```

**影响**: 显著提升上下文覆盖范围，利用历史对话

#### 3. 智能摘要生成

```python
async def _generate_llm_summary(
    self,
    history: list[dict],
    language: str = "en",
    max_length: int = 500
) -> str:
    """Use LLM to generate intelligent summary."""
    if not self._llm:
        return self._extractive_summary(history)  # Fallback
    
    # Format history for LLM
    formatted = self._format_history_for_llm(history)
    
    prompt = f"""Summarize the following conversation history, focusing on:
- Key decisions and outcomes
- Important entities (IOCs, files, etc.)
- User preferences
- Ongoing tasks or analysis

History:
{formatted}

Generate a concise summary (max {max_length} characters):"""
    
    response = await self._llm.ainvoke([HumanMessage(content=prompt)])
    return response.content
```

**影响**: 生成更智能、更相关的摘要

### P1: 高级增强（中期实施）

#### 4. 相关性排序和过滤

```python
def _rank_by_relevance(
    self,
    history: list[dict],
    query: str = "",
    time_decay: bool = True
) -> list[dict]:
    """Rank history entries by relevance to current query."""
    scored = []
    
    for entry in history:
        score = 0.0
        
        # 1. Time decay (more recent = higher score)
        if time_decay:
            timestamp = entry.get("timestamp")
            if timestamp:
                age_hours = (datetime.now() - parse_timestamp(timestamp)).total_seconds() / 3600
                time_score = 1.0 / (1.0 + age_hours / 24)  # Decay over 24 hours
                score += time_score * 0.3
        
        # 2. Query relevance (if query provided)
        if query:
            text = f"{entry.get('summary', '')} {entry.get('text', '')}"
            similarity = self._calculate_similarity(query.lower(), text.lower())
            score += similarity * 0.5
        
        # 3. Access frequency (from metadata)
        access_count = entry.get("metadata", {}).get("access_count", 0)
        score += min(access_count / 10.0, 1.0) * 0.2
        
        scored.append((score, entry))
    
    # Sort by score descending
    scored.sort(key=lambda x: x[0], reverse=True)
    return [entry for _, entry in scored]
```

**影响**: 优先显示最相关的历史信息

#### 5. 分层摘要结构

```python
def get_context_summary(
    self,
    session_id: str,
    language: str = "en",
    query: str = "",
    detail_level: str = "standard"  # "minimal", "standard", "detailed"
) -> str:
    """Generate context summary with configurable detail level."""
    
    # Detail level configurations
    configs = {
        "minimal": {
            "max_entities": 5,
            "max_files": 3,
            "max_summaries": 3,
            "summary_length": 50
        },
        "standard": {
            "max_entities": 15,
            "max_files": 8,
            "max_summaries": 8,
            "summary_length": 150
        },
        "detailed": {
            "max_entities": 30,
            "max_files": 15,
            "max_summaries": 15,
            "summary_length": 300
        }
    }
    
    config = configs.get(detail_level, configs["standard"])
    # ... use config for extraction
```

**影响**: 根据需求灵活调整摘要详细程度

#### 6. 关键信息提取增强

```python
def _extract_key_insights(self, history: list[dict]) -> dict:
    """Extract key insights from history."""
    insights = {
        "ongoing_tasks": [],
        "completed_tasks": [],
        "key_findings": [],
        "user_questions": [],
        "system_decisions": []
    }
    
    for entry in history:
        entry_type = entry.get("type", "")
        category = entry.get("category", "")
        
        if entry_type == "intent_result":
            if category == "security":
                insights["ongoing_tasks"].append({
                    "type": "security_analysis",
                    "summary": entry.get("summary", "")
                })
        
        # Extract findings from analysis results
        if "finding" in entry.get("summary", "").lower():
            insights["key_findings"].append(entry.get("summary", ""))
    
    return insights
```

**影响**: 提取结构化洞察，而非简单文本

### P2: 集成增强（长期优化）

#### 7. 与 SummarizationMiddleware 集成

```python
async def get_context_summary(
    self,
    session_id: str,
    language: str = "en",
    query: str = "",
    summarization_middleware: SummarizationMiddleware = None
) -> str:
    """Generate context summary with optional LLM summarization."""
    
    # Get raw history
    history = self.get_short_term_context(session_id)
    
    # If summarization middleware available, use it for intelligent compression
    if summarization_middleware:
        # Convert history to messages
        messages = self._history_to_messages(history)
        
        # Use summarization middleware to compress
        compressed_messages = await summarization_middleware.process_messages(
            messages,
            session_id=session_id
        )
        
        # Extract summary from compressed messages
        summary = self._extract_summary_from_messages(compressed_messages)
        return summary
    
    # Fallback to extractive summary
    return self._extractive_summary(history)
```

**影响**: 复用现有的 SummarizationMiddleware 能力

#### 8. 动态摘要长度调整

```python
def _calculate_optimal_summary_length(
    self,
    available_tokens: int,
    base_tokens: int = 500  # Base tokens for other context
) -> int:
    """Calculate optimal summary length based on available tokens."""
    remaining_tokens = available_tokens - base_tokens
    
    # Reserve 20% for safety
    safe_tokens = int(remaining_tokens * 0.8)
    
    # Convert to characters (roughly 4 chars per token)
    max_chars = safe_tokens * 4
    
    return max_chars
```

**影响**: 根据可用token动态调整摘要长度

## 实施优先级

### 阶段1: 快速改进（1-2天）
1. ✅ 增加提取数量限制（P0-1）
2. ✅ 集成长期记忆（P0-2）
3. ✅ 增加摘要长度限制（P0-1）

### 阶段2: 智能增强（3-5天）
4. ✅ 智能摘要生成（P0-3）
5. ✅ 相关性排序（P1-4）
6. ✅ 分层摘要结构（P1-5）

### 阶段3: 深度优化（1-2周）
7. ✅ 关键信息提取增强（P1-6）
8. ✅ 与 SummarizationMiddleware 集成（P2-7）
9. ✅ 动态摘要长度调整（P2-8）

## 配置选项

建议在 `intent_config.py` 中添加配置：

```python
@dataclass
class ContextSummaryConfig:
    """Configuration for context summary generation."""
    
    # Extraction limits
    max_entities: int = 20
    max_files: int = 10
    max_summaries: int = 10
    summary_length: int = 200
    
    # Long-term memory
    include_long_term: bool = True
    long_term_limit: int = 10
    
    # LLM summarization
    use_llm_summary: bool = True
    llm_summary_max_length: int = 500
    
    # Relevance ranking
    enable_relevance_ranking: bool = True
    time_decay_enabled: bool = True
    
    # Detail level
    default_detail_level: str = "standard"  # minimal, standard, detailed
```

## 预期效果

### 改进前
- 摘要长度：~200-300字符
- 信息覆盖：仅短期记忆，5-10条记录
- 摘要质量：简单截断，信息丢失

### 改进后
- 摘要长度：~500-1000字符（可配置）
- 信息覆盖：短期+长期记忆，10-30条记录
- 摘要质量：LLM智能摘要，保留关键信息
- 相关性：优先显示最相关的历史信息

## 注意事项

1. **性能考虑**: LLM摘要会增加延迟，建议异步处理
2. **Token限制**: 需要平衡摘要长度和可用token
3. **缓存策略**: 可以缓存摘要结果，避免重复计算
4. **降级策略**: LLM不可用时，使用提取式摘要作为fallback
