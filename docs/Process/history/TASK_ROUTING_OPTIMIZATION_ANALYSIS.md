# 任务路由优化分析

## 当前流程分析

### 现有流程

```
意图理解
  ↓ 生成 TaskDescription (skill_hint, expertise_needed)
任务规划
  ↓ 转换为 PlannedTask (task_type, skill_name)
任务执行
  ↓ 根据 task_type 路由
    ├─ SECURITY → _execute_security_task()
    │   └─ SubAgentMiddleware.run_skill_stream(skill_name)
    └─ RESEARCH → _execute_research_task()
        └─ DeepResearchAgent.research_stream()
```

### 当前路由逻辑

**位置**：`TaskExecutor.execute_plan_stream()` (line 528-535)

```python
if task.task_type == TaskType.SECURITY:
    async for event in self._execute_security_task(task, user_input):
        yield event
else:
    async for event in self._execute_research_task(task, user_input):
        yield event
```

**技能选择**：`_execute_security_task()` (line 580)

```python
skill_name = task.skill_name or "general-security"
```

**技能来源**：
1. `task.skill_name`（来自意图理解的 `skill_hint`）
2. 默认值 `"general-security"`

---

## 当前问题分析

### ✅ 已解决的问题

1. **任务类型路由**：通过 `task_type` 明确区分 SECURITY 和 RESEARCH
2. **技能提示**：意图理解可以生成 `skill_hint`
3. **后备机制**：如果 `skill_hint` 为空，有后备逻辑（security_subtype 映射）

### ⚠️ 潜在问题

#### 1. 技能不存在时的处理

**当前行为**：
- `SubAgentMiddleware.run_skill_stream()` 如果 skill 不存在，返回 `skill_error` 事件
- 任务执行会继续，但返回错误

**代码位置**：`subagents.py:289-298`

```python
skill = self._registry.get(skill_name)
if not skill:
    available = ", ".join(self.list_skills())
    yield SkillEvent(
        "skill_error",
        label=f"Unknown skill: {skill_name}",
        status="error",
        detail=f"Available skills: {available}",
    )
    return
```

**问题**：
- 如果意图理解给出了错误的 `skill_hint`，系统直接失败
- 没有尝试动态匹配或回退到合适的技能

#### 2. 技能匹配不够智能

**当前逻辑**：
- 优先使用 `skill_hint`（来自意图理解）
- 如果为空，使用 `security_subtype` 映射
- 如果都没有，使用 `"general-security"`

**代码位置**：`task_planner.py:274-291`

```python
skill_name = task_desc.skill_hint

if not skill_name:
    # Fallback to security_subtype mapping
    security_subtype = getattr(intent_result, 'security_subtype', None)
    if security_subtype:
        skill_name = self.SECURITY_SKILL_MAPPING.get(subtype_value, "general-security")
    else:
        skill_name = "general-security"
```

**问题**：
- 如果 `skill_hint` 存在但无效（skill 不存在），没有动态匹配机制
- 没有基于任务描述和 `key_entities` 的智能匹配

#### 3. 缺少技能验证

**当前行为**：
- 任务规划阶段不验证 skill 是否存在
- 只有在执行阶段才发现 skill 不存在

**问题**：
- 如果 skill 不存在，任务已经进入执行阶段，浪费了资源
- 应该在任务规划阶段就验证 skill 的有效性

---

## 是否需要 SmartRouter？

### SmartRouter 的原始设计目标

根据 `UNDERSTANDING_ORIENTED_WITH_SUBAGENTS.md`，SmartRouter 的设计目标是：

1. **智能技能匹配**：根据意图描述匹配 skill
2. **动态路由**：基于任务描述和关键实体匹配
3. **回退机制**：如果匹配失败，回退到合适的技能

### 当前流程 vs SmartRouter

| 功能 | 当前流程 | SmartRouter |
|------|---------|-------------|
| 任务类型路由 | ✅ 通过 `task_type` | ✅ 通过 `execution_type` |
| 技能选择 | ⚠️ 依赖意图理解的 `skill_hint` | ✅ 智能匹配（skill_hint + 动态匹配） |
| 技能验证 | ❌ 执行阶段才发现 | ✅ 规划阶段验证 |
| 回退机制 | ⚠️ 简单回退到 `general-security` | ✅ 智能回退（基于任务描述） |
| 动态匹配 | ❌ 无 | ✅ 基于任务描述、key_entities、标签 |

---

## 优化建议

### 方案 1：轻量级优化（推荐）

**不引入 SmartRouter，但增强现有流程**

#### 1.1 在任务规划阶段验证技能

**位置**：`TaskPlanner._create_plan_from_intent_tasks()`

```python
def _create_plan_from_intent_tasks(self, intent_result, language):
    # ... 现有逻辑 ...
    
    # 验证 skill 是否存在
    if task_type == TaskType.SECURITY:
        if skill_name and not self._validate_skill(skill_name):
            # Skill 不存在，尝试动态匹配
            skill_name = self._match_skill_by_task(task_desc)
    
    # ... 创建 PlannedTask ...
```

#### 1.2 添加技能匹配方法

**位置**：`TaskPlanner` 类

```python
def _validate_skill(self, skill_name: str) -> bool:
    """验证 skill 是否存在"""
    # 需要访问 SkillRegistry
    # 可以通过依赖注入或全局获取
    from app.prompts.skills import get_skill_registry
    registry = get_skill_registry()
    return registry.get(skill_name) is not None

def _match_skill_by_task(self, task_desc: TaskDescription) -> str:
    """基于任务描述动态匹配 skill"""
    from app.prompts.skills import get_skill_registry
    registry = get_skill_registry()
    
    # 1. 基于 key_entities 匹配
    for entity in task_desc.key_entities:
        if entity.endswith((".eml", ".msg")):
            if registry.get("email-security"):
                return "email-security"
        elif entity.endswith((".exe", ".dll", ".bin")):
            if registry.get("binary-analysis"):
                return "binary-analysis"
        elif entity.endswith(".pcap"):
            if registry.get("network-analysis"):
                return "network-analysis"
    
    # 2. 基于任务描述关键词匹配
    desc_lower = task_desc.description.lower()
    if "email" in desc_lower:
        if registry.get("email-security"):
            return "email-security"
    elif "malware" in desc_lower or "binary" in desc_lower:
        if registry.get("binary-analysis"):
            return "binary-analysis"
    elif "web" in desc_lower or "xss" in desc_lower:
        if registry.get("web-security"):
            return "web-security"
    
    # 3. 默认回退
    return "general-security"
```

#### 1.3 在执行阶段添加回退

**位置**：`TaskExecutor._execute_security_task()`

```python
async def _execute_security_task(self, task, user_input):
    skill_name = task.skill_name or "general-security"
    
    # 验证 skill 是否存在
    if not self._validate_skill(skill_name):
        logger.warning(
            "Skill not found, attempting fallback",
            skill_name=skill_name,
            task_id=task.id,
        )
        # 尝试动态匹配
        skill_name = self._match_skill_by_description(task.description)
        if not skill_name:
            skill_name = "general-security"
    
    # ... 执行逻辑 ...
```

**优点**：
- ✅ 改动小，不引入新组件
- ✅ 保持现有架构
- ✅ 解决技能不存在的问题

**缺点**：
- ⚠️ 技能匹配逻辑分散在多个地方
- ⚠️ 没有统一的技能匹配策略

---

### 方案 2：引入轻量级 Router（可选）

**引入一个简单的 Router 类，但不完全实现 SmartRouter**

#### 2.1 创建 TaskRouter

**位置**：`python-agent-service/app/middleware/task_router.py`

```python
class TaskRouter:
    """轻量级任务路由：验证和匹配技能"""
    
    def __init__(self, skill_registry):
        self.registry = skill_registry
    
    def validate_and_match_skill(
        self,
        skill_hint: str | None,
        task_description: str,
        key_entities: list[str],
    ) -> str:
        """验证技能，如果不存在则动态匹配"""
        
        # 1. 如果 skill_hint 存在且有效，直接使用
        if skill_hint and self.registry.get(skill_hint):
            return skill_hint
        
        # 2. 动态匹配
        matched = self._match_skill(task_description, key_entities)
        if matched:
            return matched
        
        # 3. 默认回退
        return "general-security"
    
    def _match_skill(
        self,
        task_description: str,
        key_entities: list[str],
    ) -> str | None:
        """基于任务描述和关键实体匹配技能"""
        # ... 匹配逻辑 ...
```

#### 2.2 在任务规划阶段使用

**位置**：`TaskPlanner._create_plan_from_intent_tasks()`

```python
def _create_plan_from_intent_tasks(self, intent_result, language):
    from app.middleware.task_router import TaskRouter
    from app.prompts.skills import get_skill_registry
    
    router = TaskRouter(get_skill_registry())
    
    for task_desc in intent_result.tasks:
        if task_desc.expertise_needed == "security":
            skill_name = router.validate_and_match_skill(
                skill_hint=task_desc.skill_hint,
                task_description=task_desc.description,
                key_entities=task_desc.key_entities,
            )
        # ... 创建 PlannedTask ...
```

**优点**：
- ✅ 统一的技能匹配逻辑
- ✅ 职责清晰（Router 负责匹配）
- ✅ 易于测试和维护

**缺点**：
- ⚠️ 引入新组件，增加复杂度
- ⚠️ 需要修改任务规划逻辑

---

### 方案 3：完整 SmartRouter（不推荐）

**完全实现 SmartRouter，包括 ExecutionEngine**

**不推荐的原因**：
- ❌ 当前流程已经足够简单和清晰
- ❌ 引入 SmartRouter 会增加不必要的抽象层
- ❌ 意图理解已经生成了 `skill_hint`，不需要额外的路由层
- ❌ 执行逻辑已经通过 `TaskExecutor` 很好地组织

---

## 推荐方案

### 推荐：方案 1（轻量级优化）

**理由**：
1. **最小改动**：只需要在现有代码中添加技能验证和匹配逻辑
2. **保持架构**：不引入新组件，保持现有流程清晰
3. **解决问题**：解决技能不存在和匹配不够智能的问题
4. **易于实现**：改动小，风险低

### 实施步骤

1. **在 `TaskPlanner` 中添加技能验证和匹配方法**
   - `_validate_skill()`：验证技能是否存在
   - `_match_skill_by_task()`：基于任务描述动态匹配

2. **在 `_create_plan_from_intent_tasks()` 中调用验证**
   - 如果 `skill_hint` 存在但无效，尝试动态匹配
   - 如果匹配失败，回退到 `general-security`

3. **在 `TaskExecutor._execute_security_task()` 中添加回退**
   - 如果技能不存在，尝试动态匹配
   - 记录警告日志

---

## 总结

### 是否需要 SmartRouter？

**答案：不需要完整的 SmartRouter，但需要轻量级优化**

**原因**：
1. ✅ 当前流程已经足够清晰（意图理解 → 任务规划 → 任务执行）
2. ✅ 任务类型路由已经通过 `task_type` 很好地实现
3. ⚠️ 但技能验证和匹配需要增强

### 优化重点

1. **技能验证**：在任务规划阶段验证技能是否存在
2. **动态匹配**：如果技能不存在，基于任务描述和 `key_entities` 动态匹配
3. **回退机制**：如果匹配失败，回退到 `general-security`

### 实施优先级

- **P0（立即）**：技能验证（防止执行阶段才发现技能不存在）
- **P1（近期）**：动态匹配（提高技能匹配准确度）
- **P2（可选）**：统一 Router 类（如果匹配逻辑变得复杂）
