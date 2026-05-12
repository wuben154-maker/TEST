# 移除 LLM 任务规划总结

## 变更概述

根据需求，移除了 `task_planner.py` 中的 LLM 任务规划功能，任务规划现在完全由意图理解完成。

---

## 已完成的变更

### 1. 移除 PLANNING_PROMPT 类属性

**位置**：`python-agent-service/app/middleware/task_planner.py`

**变更**：
- 删除了 `PLANNING_PROMPT` 类属性（约 100 行）
- 添加了注释说明：任务规划现在完全由意图理解完成

---

### 2. 移除 `_llm_plan` 方法

**位置**：`python-agent-service/app/middleware/task_planner.py`

**变更**：
- 删除了 `_llm_plan` 方法（约 40 行）
- 该方法用于调用 LLM 进行任务规划

---

### 3. 移除 `_parse_plan_result` 方法

**位置**：`python-agent-service/app/middleware/task_planner.py`

**变更**：
- 删除了 `_parse_plan_result` 方法（约 30 行）
- 该方法用于解析 LLM 返回的任务规划结果

---

### 4. 简化 `plan_tasks` 方法

**位置**：`python-agent-service/app/middleware/task_planner.py`

**变更前**：
```python
async def plan_tasks(self, user_input: str, intent_result: Any, language: str) -> TaskPlan:
    # Priority 1: Use tasks from intent understanding
    if intent_tasks:
        return self._create_plan_from_intent_tasks(intent_result, language)
    
    # Priority 2: Assess complexity and plan accordingly
    complexity = self._assess_complexity(user_input, intent_result)
    
    # Simple request: Create single task plan
    if complexity <= self.complexity_threshold:
        return self._create_simple_plan(intent_result, language)
    
    # Complex request: Use LLM for intelligent task decomposition
    plan_result = await self._llm_plan(user_input, intent_result, language, complexity)
    plan = self._parse_plan_result(plan_result, intent_result, language)
    return plan
```

**变更后**：
```python
async def plan_tasks(self, user_input: str, intent_result: Any, language: str) -> TaskPlan:
    # Priority 1: Use tasks already identified by intent understanding
    intent_tasks = getattr(intent_result, 'tasks', []) or []
    
    if intent_tasks:
        return self._create_plan_from_intent_tasks(intent_result, language)
    
    # Priority 2: If no tasks from intent understanding, create simple plan
    # All task planning is now done by intent understanding, not by task planner
    return self._create_simple_plan(intent_result, language)
```

**关键变化**：
- 移除了复杂度评估逻辑
- 移除了 LLM 规划调用
- 简化了流程：有任务就用，没有就创建简单计划

---

### 5. 简化 `__init__` 方法

**位置**：`python-agent-service/app/middleware/task_planner.py`

**变更前**：
```python
def __init__(
    self,
    llm: BaseChatModel,
    enable_auto_planning: bool = True,
    complexity_threshold: int = 3,
):
    self.llm = llm
    self.enable_auto_planning = enable_auto_planning
    self.complexity_threshold = complexity_threshold
```

**变更后**：
```python
def __init__(self):
    """初始化任务规划器。
    
    NOTE: 任务规划现在完全由意图理解完成，不再需要 LLM 或复杂度评估。
    """
```

**关键变化**：
- 移除了 `llm` 参数（不再需要）
- 移除了 `enable_auto_planning` 参数（不再需要）
- 移除了 `complexity_threshold` 参数（不再需要）

---

### 6. 更新 `deep_agent.py` 中的初始化

**位置**：`python-agent-service/app/agents/deep_agent.py`

**变更**：
```python
# 变更前
self.task_planner = TaskPlanner(llm=self.model)

# 变更后
self.task_planner = TaskPlanner()
```

---

### 7. 将 PLANNING_PROMPT 关键内容合并到系统提示词

**位置**：`python-agent-service/app/prompts/MASTER_AGENT.md`

**新增内容**：
- **Task Types and Skill Mapping** 部分
  - 任务类型说明（security/research/general）
  - 可用安全技能列表（email-security, binary-analysis, web-security, soc-alert, vuln-scan, general-security）
  - 技能选择指南

**目的**：
- 确保意图理解阶段就能正确选择任务类型和技能
- 统一任务规划规则到意图理解提示词中

---

## 保留的方法

### 1. `_create_plan_from_intent_tasks`
- **用途**：将意图理解的任务列表转换为 `PlannedTask` 对象
- **保留原因**：这是任务规划的核心功能，仍然需要

### 2. `_create_simple_plan`
- **用途**：当意图理解未生成任务时，创建简单的单一任务计划
- **保留原因**：作为后备机制，确保系统在边界情况下仍能工作

### 3. `_assess_complexity`
- **状态**：仍然存在，但不再被调用
- **建议**：可以后续移除（如果确认不再需要）

---

## 影响分析

### 正面影响

1. **简化架构**：
   - 移除了任务规划层的 LLM 调用
   - 减少了代码复杂度
   - 降低了系统延迟（少一次 LLM 调用）

2. **统一规划**：
   - 所有任务规划都在意图理解阶段完成
   - 避免了二次规划可能带来的不一致

3. **降低成本**：
   - 减少了 LLM API 调用次数
   - 降低了系统运行成本

### 潜在影响

1. **边界情况处理**：
   - 如果意图理解未生成任务，现在只能创建简单计划
   - 可能需要确保意图理解总是能生成任务

2. **依赖关系**：
   - 依赖关系现在完全由意图理解阶段设置
   - 需要确保意图理解能正确识别任务依赖

---

## 验证检查点

- [x] `PLANNING_PROMPT` 已移除
- [x] `_llm_plan` 方法已移除
- [x] `_parse_plan_result` 方法已移除
- [x] `plan_tasks` 方法已简化
- [x] `__init__` 方法已简化
- [x] `deep_agent.py` 中的初始化已更新
- [x] 系统提示词已更新（添加任务类型和技能映射）
- [x] 代码编译通过

---

## 总结

成功移除了 `task_planner.py` 中的 LLM 任务规划功能，任务规划现在完全由意图理解完成。系统架构更加简洁，减少了 LLM 调用次数，降低了成本和延迟。
