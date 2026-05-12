# 意图理解优化实现总结

## 优化概述

根据用户需求，完成了以下优化：

1. **意图理解提示词优化**：添加"我是谁"、工作范围和边界说明，超出边界时给出3-4个引导式解决方案
2. **语言检测优化**：根据用户输入语言返回，而不是界面设定语言
3. **普通问题判断**：普通问题直接返回大模型推理结果，无需任务规划
4. **任务类型映射优化**：在意图理解阶段就明确任务类型（security/research/context），确保都能对应

---

## 实现内容

### 1. MASTER_AGENT.md 优化

#### 1.1 添加"我是谁"和工作范围说明

**位置**：`<role>` 部分

**新增内容**：
- **Who I Am**：明确身份（专业网络安全AI智能体）
- **My Core Identity**：核心身份、领域专长、次要能力、运行模式
- **My Work Scope and Boundaries**：详细的能力范围和边界说明

#### 1.2 超出边界时的引导式解决方案

**位置**：`<role>` 部分和 `Out of Scope Detection Rules`

**新增内容**：
- 当请求超出能力范围时，提供3-4个引导式替代方案
- 每个方案包含：option编号、title、description
- 示例格式：
  ```json
  {
    "suggested_alternatives": [
      {
        "option": 1,
        "title": "Security-related research",
        "description": "I can research security implications..."
      },
      ...
    ]
  }
  ```

#### 1.3 语言检测说明

**位置**：`Response Summary Guidelines`

**更新内容**：
- 强调：**Always respond in the same language as the user's input**
- 明确：**Detect the language automatically from the user's input text, NOT from any interface setting**

#### 1.4 任务类型分类和路由说明

**位置**：新增 `Task Type Classification and Routing` 部分

**新增内容**：
- **Simple Questions (Direct Response)**：定义、示例、特征、响应格式
- **Professional Tasks (Require Task Planning)**：三种类型（security/research/context）
- **Task Type Mapping Rules**：明确的映射规则
- **CRITICAL**：每个任务必须明确设置 `task_type`，不能有歧义

---

### 2. 语言检测实现

#### 2.1 添加语言检测方法

**位置**：`IntentUnderstandingMiddleware._detect_language()`

**实现逻辑**：
```python
def _detect_language(self, text: str) -> str:
    """Detect language from user input text."""
    # 检测中文字符
    if any('\u4e00' <= char <= '\u9fff' for char in text):
        return "zh"
    
    # 检测日文字符（平假名、片假名、汉字）
    if any('\u3040' <= char <= '\u309f' or '\u30a0' <= char <= '\u30ff' for char in text):
        return "ja"
    
    # 检测韩文字符
    if any('\uac00' <= char <= '\ud7a3' for char in text):
        return "ko"
    
    # 默认英语
    return "en"
```

#### 2.2 在意图理解中使用检测到的语言

**位置**：`IntentUnderstandingMiddleware.understand()`

**变更**：
```python
# Step 0: Detect language from user input (not interface setting)
detected_language = self._detect_language(text)
# Use detected language instead of interface setting
language = detected_language
```

---

### 3. 普通问题判断实现

#### 3.1 扩展 IntentResult 模型

**位置**：`intent_models.py`

**新增字段**：
```python
is_simple_question: bool = False  # True if this is a simple question
direct_response: bool = False  # True if direct LLM response should be returned
```

#### 3.2 更新 PHASE1_TOOL Schema

**位置**：`intent_classifier.py`

**新增字段**：
```python
"is_simple_question": {
    "type": "boolean",
    "description": "True if this is a simple question that can be answered directly"
},
"direct_response": {
    "type": "boolean",
    "description": "True if direct LLM response should be returned (no task planning needed)"
}
```

#### 3.3 在 DeepAgentWithIntent 中处理普通问题

**位置**：`deep_agent.py`

**新增逻辑**：
```python
# Check if this is a simple question (direct response, no task planning)
if intent_result.is_simple_question and intent_result.direct_response:
    # Direct LLM response for simple questions
    response = await self.model.ainvoke([
        SystemMessage(content=MASTER_SYSTEM_PROMPT),
        HumanMessage(content=response_prompt)
    ])
    yield {
        "type": "reasoning",
        "content": response.content,
    }
    return  # Skip task planning
```

---

### 4. 任务类型映射优化

#### 4.1 扩展 TaskDescription 模型

**位置**：`intent_models.py`

**新增字段**：
```python
task_type: str = ""  # Explicit task type: "security" | "research" | "context" (MUST be set)
```

#### 4.2 更新 PHASE1_TOOL Schema

**位置**：`intent_classifier.py`

**新增字段**：
```python
"task_type": {
    "type": "string",
    "enum": ["security", "research", "context"],
    "description": "Explicit task type. MUST be set",
    "required": true
}
```

#### 4.3 在 _parse_result 中解析 task_type

**位置**：`intent_classifier.py`

**实现逻辑**：
```python
# Determine task_type: use explicit task_type if provided, otherwise infer from expertise_needed
task_type = task_data.get("task_type", "")
expertise_needed = task_data.get("expertise_needed", "general")

# If task_type not explicitly set, infer from expertise_needed
if not task_type:
    if expertise_needed == "research":
        task_type = "research"
    elif expertise_needed == "security":
        task_type = "security"
    else:
        # For "general", check context_needed to determine if it's context task
        if context_keywords in context_needed:
            task_type = "context"
        else:
            task_type = "security"  # Default
```

#### 4.4 在任务规划中使用 task_type

**位置**：`task_planner.py`

**更新逻辑**：
```python
# Use explicit task_type from intent understanding (if provided)
task_type_str = getattr(task_desc, 'task_type', '') or (task_desc.task_type if hasattr(task_desc, 'task_type') else '')

# Determine task type: prioritize explicit task_type from intent understanding
if task_type_str:
    if task_type_str == "security":
        task_type = TaskType.SECURITY
    elif task_type_str == "research":
        task_type = TaskType.RESEARCH
    elif task_type_str == "context":
        task_type = TaskType.CONTEXT
```

---

### 5. 超出边界请求处理

#### 5.1 扩展 IntentResult 模型

**位置**：`intent_models.py`

**新增字段**：
```python
suggested_alternatives: list[dict] = field(default_factory=list)  # 3-4 guided alternative solutions
```

#### 5.2 在 DeepAgentWithIntent 中处理超出边界请求

**位置**：`deep_agent.py`

**新增逻辑**：
```python
# Check for out-of-scope requests with suggested alternatives
if intent_result.task_category == TaskCategory.UNKNOWN and intent_result.suggested_alternatives:
    # Show out-of-scope message with alternatives
    yield {
        "type": "step",
        "label": "Capability Notice",
        "status": "warning",
        "detail": intent_result.summary,
    }
    
    # Show suggested alternatives
    for alt in intent_result.suggested_alternatives:
        yield {
            "type": "step",
            "label": f"Option {alt.get('option', 0)}: {alt.get('title', '')}",
            "status": "info",
            "detail": alt.get("description", ""),
        }
```

---

## 关键变更总结

### 数据模型变更

1. **TaskDescription**：
   - 新增 `task_type` 字段（必需）

2. **IntentResult**：
   - 新增 `is_simple_question` 字段
   - 新增 `direct_response` 字段
   - 新增 `suggested_alternatives` 字段

### 提示词变更

1. **MASTER_AGENT.md**：
   - 扩展 `<role>` 部分，添加详细的"我是谁"和工作范围说明
   - 添加超出边界时的引导式解决方案格式
   - 强调语言检测规则（根据用户输入，不是界面设置）
   - 添加任务类型分类和路由说明

### 代码逻辑变更

1. **IntentUnderstandingMiddleware**：
   - 添加 `_detect_language()` 方法
   - 在 `understand()` 中使用检测到的语言

2. **IntentClassifier**：
   - 更新 `PHASE1_TOOL` schema，添加新字段
   - 更新 `_parse_result()`，解析新字段和 `task_type`

3. **TaskPlanner**：
   - 更新 `_create_plan_from_intent_tasks()`，优先使用 `task_type` 字段

4. **DeepAgentWithIntent**：
   - 添加普通问题的直接响应逻辑
   - 添加超出边界请求的处理逻辑

---

## 使用示例

### 示例 1：普通问题（直接响应）

**用户输入**："What is a zero-day vulnerability?"

**意图理解结果**：
```json
{
  "is_simple_question": true,
  "direct_response": true,
  "tasks": []
}
```

**执行流程**：
1. 检测为普通问题
2. 直接调用 LLM 生成回答
3. 返回推理内容
4. 跳过任务规划

---

### 示例 2：专业任务（任务规划）

**用户输入**："Analyze this email file"

**意图理解结果**：
```json
{
  "is_simple_question": false,
  "direct_response": false,
  "tasks": [{
    "description": "Analyze email file email.eml",
    "expertise_needed": "security",
    "task_type": "security",  // 明确设置
    "skill_hint": "email-security"
  }]
}
```

**执行流程**：
1. 检测为专业任务
2. 进入任务规划
3. 使用 `task_type: "security"` 路由到安全任务执行

---

### 示例 3：超出边界请求

**用户输入**："What's the weather today?"

**意图理解结果**：
```json
{
  "task_category": "unknown",
  "confidence": 0.1,
  "suggested_alternatives": [
    {
      "option": 1,
      "title": "Security-related research",
      "description": "I can research security implications..."
    },
    {
      "option": 2,
      "title": "Threat intelligence",
      "description": "I can help analyze security threats..."
    },
    {
      "option": 3,
      "title": "General research",
      "description": "I can conduct deep research..."
    },
    {
      "option": 4,
      "title": "Security analysis",
      "description": "I can analyze security-related files..."
    }
  ]
}
```

**执行流程**：
1. 检测为超出边界请求
2. 显示能力范围提示
3. 显示4个引导式替代方案
4. 结束流程

---

## 总结

### 已完成的优化

1. ✅ **意图理解提示词优化**：添加"我是谁"、工作范围和边界说明，超出边界时给出3-4个引导式解决方案
2. ✅ **语言检测优化**：根据用户输入语言返回，而不是界面设定语言
3. ✅ **普通问题判断**：普通问题直接返回大模型推理结果，无需任务规划
4. ✅ **任务类型映射优化**：在意图理解阶段就明确任务类型（security/research/context），确保都能对应

### 关键改进

- **明确的身份定位**：聚焦网络安全领域的专业智能体，也能做deep research
- **智能边界处理**：超出边界时提供引导式解决方案，而不是简单拒绝
- **语言自适应**：完全根据用户输入语言返回，提升用户体验
- **任务类型明确化**：在意图理解阶段就确定任务类型，避免执行阶段的歧义
