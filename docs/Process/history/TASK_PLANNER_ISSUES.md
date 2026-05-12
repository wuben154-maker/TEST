# 任务规划代码逻辑问题分析

## 问题概述

任务规划器（TaskPlanner）在接收意图理解结果后，存在以下主要问题：

---

## 🔴 P0 问题（严重）

### 1. **未利用意图理解已生成的任务列表**

**问题描述**：
- 意图理解已经生成了 `intent_result.tasks`（`TaskDescription` 列表）
- 任务规划器完全忽略了这些已分解的任务，重新进行任务规划
- 导致重复工作和可能的不一致

**代码位置**：
- `task_planner.py:375-427` - `plan_tasks` 方法
- `task_planner.py:429-471` - `_create_simple_plan` 方法

**当前逻辑**：
```python
async def plan_tasks(self, user_input: str, intent_result: Any, language: str) -> TaskPlan:
    complexity = self._assess_complexity(user_input, intent_result)
    
    # 简单请求：直接创建单任务计划
    if not self.enable_auto_planning or complexity <= self.complexity_threshold:
        return self._create_simple_plan(intent_result, language)  # ❌ 只创建单一任务
    
    # 复杂请求：使用 LLM 进行智能任务拆分
    plan_result = await self._llm_plan(user_input, intent_result, language, complexity)
    # ❌ 完全忽略了 intent_result.tasks
```

**问题影响**：
- 意图理解已经分解的任务被丢弃
- LLM 可能生成与意图理解不一致的任务
- 浪费计算资源（重复规划）

**修复建议**：
```python
async def plan_tasks(self, user_input: str, intent_result: Any, language: str) -> TaskPlan:
    # ✅ 优先使用意图理解已生成的任务
    if hasattr(intent_result, 'tasks') and intent_result.tasks:
        return self._create_plan_from_intent_tasks(intent_result, language)
    
    # 如果没有任务列表，再使用复杂度评估
    complexity = self._assess_complexity(user_input, intent_result)
    # ...
```

---

### 2. **简单计划未利用意图理解的任务信息**

**问题描述**：
- `_create_simple_plan` 方法只创建一个任务
- 即使意图理解已经生成了多个任务（`intent_result.tasks`），也被忽略
- 只使用了 `task_category` 和 `security_subtype`，忽略了 `tasks` 列表

**代码位置**：
- `task_planner.py:429-471` - `_create_simple_plan` 方法

**当前逻辑**：
```python
def _create_simple_plan(self, intent_result: Any, language: str) -> TaskPlan:
    # ❌ 只创建一个任务，忽略 intent_result.tasks
    task = PlannedTask(
        title=title,
        description=getattr(intent_result, 'summary', '') or '',
        task_type=task_type,
        skill_name=skill_name,
    )
    return TaskPlan(tasks=[task], is_single_task=True)
```

**修复建议**：
```python
def _create_simple_plan(self, intent_result: Any, language: str) -> TaskPlan:
    # ✅ 检查是否有已生成的任务列表
    intent_tasks = getattr(intent_result, 'tasks', []) or []
    
    if intent_tasks:
        # 使用意图理解的任务列表
        planned_tasks = []
        for task_desc in intent_tasks:
            planned_task = self._convert_task_description_to_planned_task(
                task_desc, intent_result, language
            )
            planned_tasks.append(planned_task)
        
        return TaskPlan(
            tasks=planned_tasks,
            is_single_task=len(planned_tasks) == 1,
        )
    
    # 如果没有任务列表，创建默认单一任务
    # ...
```

---

## 🟡 P1 问题（重要）

### 3. **复杂度评估过于简单，未利用意图理解结果**

**问题描述**：
- `_assess_complexity` 使用硬编码关键词匹配
- 没有利用意图理解已经分析的信息（如 `tasks` 数量、`analysis_goals` 等）
- 评估结果可能不准确

**代码位置**：
- `task_planner.py:335-373` - `_assess_complexity` 方法

**当前逻辑**：
```python
def _assess_complexity(self, user_input: str, intent_result: Any) -> int:
    score = 1
    input_lower = user_input.lower()
    
    # ❌ 只检查关键词，没有利用意图理解结果
    for indicator in COMPLEXITY_INDICATORS["multiple_targets"]:
        if indicator in input_lower:
            score += 2
            break
    # ...
```

**修复建议**：
```python
def _assess_complexity(self, user_input: str, intent_result: Any) -> int:
    score = 1
    
    # ✅ 优先使用意图理解的任务数量
    intent_tasks = getattr(intent_result, 'tasks', []) or []
    if len(intent_tasks) > 1:
        return min(len(intent_tasks) * 2, 10)  # 多个任务 = 高复杂度
    
    # ✅ 使用意图理解的置信度
    confidence = getattr(intent_result, 'confidence', 0.8)
    if confidence < 0.5:
        score += 2  # 低置信度 = 更复杂
    
    # ✅ 使用分析目标数量
    goals = getattr(intent_result, 'analysis_goals', []) or []
    if len(goals) > 2:
        score += len(goals) - 2
    
    # 关键词匹配作为补充
    # ...
```

---

### 4. **LLM 规划提示词未包含意图理解的任务信息**

**问题描述**：
- `_llm_plan` 方法的提示词没有包含 `intent_result.tasks`
- LLM 可能生成与意图理解不一致的任务

**代码位置**：
- `task_planner.py:473-521` - `_llm_plan` 方法
- `task_planner.py:245-316` - `PLANNING_PROMPT` 模板

**当前逻辑**：
```python
PLANNING_PROMPT = """...
## Intent Understanding Results
- Category: {category}
- Confidence: {confidence}
- Summary: {summary}
# ❌ 缺少 tasks 列表
...
"""
```

**修复建议**：
```python
PLANNING_PROMPT = """...
## Intent Understanding Results
- Category: {category}
- Confidence: {confidence}
- Summary: {summary}
- Tasks Already Identified: {tasks_list}  # ✅ 添加任务列表
- Task Descriptions: {task_descriptions}  # ✅ 添加任务描述
...
"""
```

---

### 5. **硬编码的多语言消息**

**问题描述**：
- `PLANNER_MESSAGES` 字典硬编码在代码中
- 应该从 `LABELS.md` 加载

**代码位置**：
- `task_planner.py:158-208` - `PLANNER_MESSAGES` 字典

**修复建议**：
```python
# ✅ 从 LABELS.md 加载
from app.parsers.labels import get_intent_label

def get_planner_message(key: str, language: str) -> str:
    return get_intent_label(f"planner_{key}", language)
```

---

## 🟢 P2 问题（改进）

### 6. **任务类型映射可能不准确**

**问题描述**：
- `SECURITY_SKILL_MAPPING` 是硬编码的映射
- 意图理解可能已经提供了 `skill_hint`，但没有被使用

**代码位置**：
- `task_planner.py:229-238` - `SECURITY_SKILL_MAPPING`
- `task_planner.py:450-455` - skill 选择逻辑

**修复建议**：
```python
# ✅ 优先使用意图理解的 skill_hint
skill_name = None
if hasattr(intent_result, 'tasks') and intent_result.tasks:
    # 使用第一个任务的 skill_hint
    skill_name = intent_result.tasks[0].skill_hint

if not skill_name:
    # Fallback 到 security_subtype 映射
    security_subtype = getattr(intent_result, 'security_subtype', None)
    if security_subtype:
        skill_name = self.SECURITY_SKILL_MAPPING.get(subtype_value, "general-security")
```

---

### 7. **任务依赖关系未从意图理解传递**

**问题描述**：
- 意图理解可能已经识别了任务间的依赖关系
- 但任务规划器没有利用这些信息

**修复建议**：
- 在 `TaskDescription` 中添加 `depends_on` 字段
- 任务规划器从意图理解结果中提取依赖关系

---

## 📋 修复优先级

### 立即修复（P0）
1. ✅ **利用意图理解已生成的任务列表** - 避免重复规划
2. ✅ **简单计划使用意图理解的任务** - 保持一致性

### 近期修复（P1）
3. ✅ **改进复杂度评估** - 利用意图理解结果
4. ✅ **更新 LLM 规划提示词** - 包含任务信息
5. ✅ **移除硬编码消息** - 使用 LABELS.md

### 可选改进（P2）
6. ✅ **使用意图理解的 skill_hint**
7. ✅ **传递任务依赖关系**

---

## 🔧 修复方案

### 方案 1：优先使用意图理解的任务（推荐）

```python
async def plan_tasks(
    self,
    user_input: str,
    intent_result: Any,
    language: str = "en",
) -> TaskPlan:
    """根据意图理解结果规划任务。"""
    
    # ✅ 优先使用意图理解已生成的任务
    intent_tasks = getattr(intent_result, 'tasks', []) or []
    
    if intent_tasks:
        logger.info(
            "Using tasks from intent understanding",
            task_count=len(intent_tasks),
        )
        return self._create_plan_from_intent_tasks(intent_result, language)
    
    # 如果没有任务列表，使用复杂度评估
    complexity = self._assess_complexity(user_input, intent_result)
    
    if not self.enable_auto_planning or complexity <= self.complexity_threshold:
        return self._create_simple_plan(intent_result, language)
    
    # 复杂请求：使用 LLM 规划
    try:
        plan_result = await self._llm_plan(user_input, intent_result, language, complexity)
        plan = self._parse_plan_result(plan_result, intent_result, language)
        return plan
    except Exception as e:
        logger.warning("LLM planning failed, using simple plan", error=str(e))
        return self._create_simple_plan(intent_result, language)

def _create_plan_from_intent_tasks(
    self,
    intent_result: Any,
    language: str,
) -> TaskPlan:
    """从意图理解的任务列表创建任务计划。"""
    planned_tasks = []
    
    for task_desc in intent_result.tasks:
        # 确定任务类型
        task_type = TaskType.SECURITY
        skill_name = task_desc.skill_hint
        
        if task_desc.expertise_needed == "research":
            task_type = TaskType.RESEARCH
            skill_name = None
        elif task_type == TaskType.SECURITY and not skill_name:
            # Fallback 到 security_subtype 映射
            security_subtype = getattr(intent_result, 'security_subtype', None)
            if security_subtype:
                subtype_value = security_subtype.value if hasattr(security_subtype, 'value') else str(security_subtype)
                skill_name = self.SECURITY_SKILL_MAPPING.get(subtype_value, "general-security")
            else:
                skill_name = "general-security"
        
        # 创建 PlannedTask
        planned_task = PlannedTask(
            title=task_desc.description[:50],  # 截断为标题
            description=task_desc.description,
            task_type=task_type,
            skill_name=skill_name,
            priority=1,  # 可以根据 key_entities 等调整
        )
        
        planned_tasks.append(planned_task)
    
    return TaskPlan(
        tasks=planned_tasks,
        is_single_task=len(planned_tasks) == 1,
    )
```

---

## 📊 影响分析

### 修复后的优势
1. ✅ **避免重复工作** - 直接使用意图理解的任务
2. ✅ **保持一致性** - 任务规划与意图理解一致
3. ✅ **提高效率** - 减少 LLM 调用
4. ✅ **更好的准确性** - 利用意图理解的深度分析

### 潜在风险
1. ⚠️ **如果意图理解任务不完整** - 可能需要 LLM 补充
2. ⚠️ **任务依赖关系** - 需要从意图理解传递

---

## 🎯 总结

**核心问题**：任务规划器没有充分利用意图理解已经生成的任务列表，导致重复工作和可能的不一致。

**解决方案**：优先使用 `intent_result.tasks`，只有在没有任务列表时才进行复杂度评估和 LLM 规划。

**预期效果**：
- 减少 LLM 调用（提高效率）
- 保持任务规划与意图理解的一致性
- 提高整体系统的准确性
