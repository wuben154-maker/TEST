# 意图理解功能核对报告

## 核对目标

检查增强意图理解是否达到以下要求：
1. ✅ 支持专项任务理解（security tasks）
2. ✅ 支持 Deep Research 任务理解
3. ✅ 支持复合任务理解（多个任务）
4. ✅ 支持上下文关联任务理解（历史查询、结果合并等）
5. ✅ 支持不确定问题的通过自动推理方式给出用户需求选项澄清能力

---

## 1. 专项任务理解（Security Tasks）

### ✅ 数据结构支持
- **TaskDescription.expertise_needed**: 支持 `"security"` 值
- **TaskDescription.skill_hint**: 可以指定具体的 skill（如 `"email-security"`, `"binary-analysis"`）
- **IntentResult.security_subtype**: 支持安全子类型（email_analysis, malware_analysis 等）

### ✅ 提示词支持
- `MASTER_AGENT.md` 中明确说明支持安全任务
- 提示词中包含安全任务的示例和说明

### ⚠️ 潜在问题
- **LLM 可能不总是生成多个任务**：即使提示词说 "can be 1 or more"，LLM 可能倾向于只返回单个任务
- **skill_hint 可能为空**：LLM 可能不总是提供 skill_hint

### 📋 建议改进
1. 在提示词中更明确地说明：对于安全任务，**必须**提供 `skill_hint`
2. 添加示例，展示如何为不同类型的安全任务指定 skill

---

## 2. Deep Research 任务理解

### ✅ 数据结构支持
- **TaskDescription.expertise_needed**: 支持 `"research"` 值
- **IntentResult.research_topic**: 支持研究主题

### ✅ 提示词支持
- `MASTER_AGENT.md` 中明确说明支持研究任务
- 提示词中包含研究任务的示例

### ⚠️ 潜在问题
- **研究任务可能被误分类为 security**：如果用户输入包含安全相关关键词，LLM 可能误判

### 📋 建议改进
1. 在提示词中更明确地区分 research 和 security：
   - Research: 信息收集、技术研究、文档分析
   - Security: 威胁分析、恶意代码检测、安全事件响应

---

## 3. 复合任务理解（多个任务）

### ✅ 数据结构支持
- **IntentResult.tasks**: `list[TaskDescription]` 可以包含多个任务
- **TaskDescription**: 每个任务独立描述，支持不同的 `expertise_needed`

### ✅ 提示词支持
- 提示词中明确说明："tasks: Break down into actionable task descriptions **(can be 1 or more)**"
- 提示词中说明："Support any type of request, handle **complex multi-step tasks**"

### ⚠️ 潜在问题
- **LLM 可能不总是拆分任务**：即使输入明显包含多个任务，LLM 可能只返回单个任务
- **任务依赖关系未明确**：当前 `TaskDescription` 没有 `depends_on` 字段

### 📋 建议改进
1. **增强提示词**：添加明确的复合任务示例
   ```json
   {
     "intent_description": "用户想要分析文件并研究相关漏洞",
     "tasks": [
       {
         "description": "分析文件 sample.exe 的安全威胁",
         "expertise_needed": "security",
         "skill_hint": "binary-analysis"
       },
       {
         "description": "研究从文件分析中提取的漏洞信息",
         "expertise_needed": "research"
       }
     ]
   }
   ```

2. **添加任务依赖字段**（可选）：
   ```python
   @dataclass
   class TaskDescription:
       # ... existing fields ...
       depends_on: list[str] = field(default_factory=list)  # Task IDs this task depends on
   ```

---

## 4. 上下文关联任务理解

### ✅ 上下文检索支持
- **ContextRetriever**: 可以检索短期和长期记忆
- **get_short_term_context()**: 获取当前会话的历史
- **get_long_term_context()**: 支持关键词和模糊匹配

### ✅ 提示词支持
- 提示词中说明："Consider context from previous conversations"
- 上下文会被传递给 LLM

### ❌ **缺失功能**
1. **历史查询任务理解不足**：
   - 提示词中没有明确说明如何处理"前面几次分析的结果是什么？"这类查询
   - 没有专门的 `intent_type` 或 `expertise_needed` 值来标识历史查询任务

2. **结果合并任务理解不足**：
   - 提示词中没有明确说明如何处理"把这些结果合并成一个文档"这类请求
   - 没有专门的字段来标识需要合并的历史结果

### 📋 建议改进

#### 改进 1：增强提示词，明确支持上下文关联任务

在 `MASTER_AGENT.md` 的 `<intent-understanding>` section 中添加：

```markdown
### Context-Related Tasks

The system can understand and handle context-related requests:

1. **History Queries**:
   - "前面几次分析的结果是什么？"
   - "What were the results of previous analyses?"
   - Intent type: `history_query`
   - Expertise needed: `general`
   - Tasks: [{"description": "查询会话中的历史分析结果", "expertise_needed": "general"}]

2. **Result Merging**:
   - "把这些结果合并成一个文档"
   - "Merge the previous analysis results into a single report"
   - Intent type: `result_merge`
   - Expertise needed: `general`
   - Tasks: [{"description": "合并历史分析结果", "expertise_needed": "general", "context_needed": ["previous_results"]}]

3. **Context-Dependent Analysis**:
   - "基于前面的分析，进一步调查..."
   - "Based on previous findings, investigate..."
   - Intent type: `context_dependent`
   - Tasks should include `context_needed` field with references to previous results
```

#### 改进 2：增强 TaskDescription，支持上下文引用

```python
@dataclass
class TaskDescription:
    # ... existing fields ...
    context_needed: list[str] = field(default_factory=list)  # ✅ 已存在
    # 建议：明确说明 context_needed 可以包含：
    # - "previous_results": 需要前面的分析结果
    # - "session_history": 需要会话历史
    # - 具体的文件名或任务ID
```

#### 改进 3：在 ContextRetriever 中添加历史查询辅助方法

```python
class ContextRetriever:
    # ... existing methods ...
    
    async def get_recent_analysis_results(
        self, 
        session_id: str, 
        limit: int = 5
    ) -> list[dict]:
        """Get recent analysis results for history queries."""
        # 实现逻辑：从历史记录中提取分析结果
        pass
    
    async def get_analysis_results_for_merge(
        self,
        session_id: str,
        query: str = ""
    ) -> list[dict]:
        """Get analysis results that match merge query."""
        # 实现逻辑：根据查询匹配需要合并的结果
        pass
```

---

## 5. 不确定问题的自动推理澄清

### ✅ 实现支持
- **`_generate_clarification_questions_with_llm()`**: 使用 LLM 推理生成澄清问题
- **置信度分级**: MEDIUM (0.4-0.7) 和 LOW (< 0.4) 会触发澄清
- **提示词**: `MASTER_AGENT.md` 中有 `clarification-reasoning` section

### ✅ 提示词支持
- `clarification-reasoning` section 提供了详细的指导
- 区分了 Medium 和 Low 置信度的不同处理方式

### ⚠️ 潜在问题
1. **澄清问题可能不够具体**：LLM 可能生成过于通用的问题
2. **澄清问题可能不包含选项**：当前实现只生成问题，不生成选项

### 📋 建议改进

#### 改进 1：增强澄清问题生成，支持选项

修改 `_generate_clarification_questions_with_llm()` 方法，要求 LLM 生成带选项的问题：

```python
prompt = f"""{clarification_prompt_template}

## Current Understanding Context
...

## Your Task

Based on the above context, generate clarification questions with **options** when applicable.

### Format for Questions with Options:
```
To better understand your request, could you clarify:

1. [Question]
   Options:
   - Option A: [description]
   - Option B: [description]
   - Option C: [description]

2. [Question]
   Options:
   - Option A: [description]
   - Option B: [description]
```

### Format for Open Questions:
```
To better understand your request, could you clarify:

1. [Open-ended question]
2. [Another open-ended question]
```

Generate questions in {language}. Focus on actual gaps in understanding.
"""
```

#### 改进 2：增强 ParameterRequest，支持选项

```python
@dataclass
class ParameterRequest:
    # ... existing fields ...
    options: list[dict] = field(default_factory=list)  # [{"value": "A", "label": "Option A"}]
    allow_custom: bool = True  # Whether to allow custom input beyond options
```

---

## 总结

### ✅ 已满足的要求

1. **专项任务理解**：✅ 数据结构支持，提示词支持
2. **Deep Research 任务理解**：✅ 数据结构支持，提示词支持
3. **复合任务理解**：✅ 数据结构支持，提示词支持（但可能需要增强示例）
4. **自动推理澄清**：✅ 实现完整，提示词支持

### ⚠️ 部分满足的要求

1. **复合任务理解**：
   - ⚠️ LLM 可能不总是拆分任务
   - ⚠️ 缺少任务依赖关系字段

2. **上下文关联任务理解**：
   - ⚠️ 上下文检索功能存在
   - ❌ **提示词中缺少明确的历史查询和结果合并场景说明**
   - ❌ **缺少专门的历史查询和结果合并任务类型**

### 📋 优先级改进建议

#### P0（必须改进）
1. **增强提示词，明确支持上下文关联任务**
   - 添加历史查询场景说明
   - 添加结果合并场景说明
   - 添加示例

#### P1（重要改进）
2. **增强复合任务理解的提示词**
   - 添加更多复合任务示例
   - 明确说明何时应该拆分任务

3. **增强澄清问题生成**
   - 支持生成带选项的问题
   - 增强 ParameterRequest 支持选项

#### P2（可选改进）
4. **添加任务依赖关系字段**
5. **增强 ContextRetriever，添加历史查询辅助方法**

---

## 下一步行动

1. **立即改进**：增强 `MASTER_AGENT.md` 的 `<intent-understanding>` section，添加上下文关联任务说明
2. **测试验证**：创建测试用例，验证：
   - 复合任务是否能正确拆分
   - 历史查询是否能正确识别
   - 结果合并是否能正确理解
   - 澄清问题是否足够具体
