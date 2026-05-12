# 任务规划器 P0/P1 优化实现总结

## 优化概述

根据全面流程分析，完成了以下 P0（严重）和 P1（重要）优化：

### P0 优化（严重）

1. **简化任务类型推断逻辑**
   - 位置：`task_planner.py:279-301`
   - 问题：多层 if-else，后备逻辑可能不一致
   - 优化：优先使用 `task_type`，简化后备推断

2. **移除依赖关系后备逻辑**
   - 位置：`task_planner.py:347-375`
   - 问题：仍保留 `context_needed` 字符串匹配
   - 优化：完全依赖 `depends_on_task_ids`，移除后备逻辑

### P1 优化（重要）

3. **添加技能验证**
   - 位置：`task_planner.py:264-298`（新增方法）
   - 问题：规划阶段不验证技能是否存在
   - 优化：添加技能验证，无效时使用默认技能

---

## 详细实现

### 1. 简化任务类型推断逻辑

#### 优化前

```python
# 多层 if-else 判断，逻辑复杂
task_type_str = getattr(task_desc, 'task_type', '') or ...
if task_type_str:
    if task_type_str == "security":
        task_type = TaskType.SECURITY
    elif task_type_str == "research":
        task_type = TaskType.RESEARCH
    elif task_type_str == "context":
        task_type = TaskType.CONTEXT
    else:
        task_type = TaskType.SECURITY
else:
    if task_desc.expertise_needed == "research":
        task_type = TaskType.RESEARCH
    elif task_desc.expertise_needed == "security":
        task_type = TaskType.SECURITY
    else:
        task_type = TaskType.SECURITY

# 还有额外的 context 任务检测逻辑...
if not task_type_str and task_desc.expertise_needed == "general":
    # 复杂的 context 任务检测...
```

#### 优化后

```python
# 简化逻辑：优先使用 task_type，简单后备
task_type_str = getattr(task_desc, 'task_type', '') or (task_desc.task_type if hasattr(task_desc, 'task_type') else '')

# Determine task type: prioritize explicit task_type, simple fallback
if task_type_str in ["security", "research", "context"]:
    task_type = TaskType(task_type_str)
else:
    # Simple fallback: only use expertise_needed if task_type not set
    if task_desc.expertise_needed == "research":
        task_type = TaskType.RESEARCH
    elif task_desc.expertise_needed == "security":
        task_type = TaskType.SECURITY
    else:
        # Default to security for general tasks
        task_type = TaskType.SECURITY
        logger.warning(
            "Task type not explicitly set, defaulting to security",
            task_index=i,
            expertise_needed=task_desc.expertise_needed,
            task_type_str=task_type_str,
        )
```

**改进点**：
- ✅ 移除了复杂的 context 任务检测逻辑（应该在意图理解阶段完成）
- ✅ 使用 `TaskType(task_type_str)` 直接构造，更简洁
- ✅ 添加警告日志，便于调试
- ✅ 逻辑更清晰，易于维护

---

### 2. 移除依赖关系后备逻辑

#### 优化前

```python
if task_desc.depends_on_task_ids:
    # 使用 depends_on_task_ids
    ...
elif task_desc.context_needed:
    # 后备逻辑：使用 context_needed 字符串匹配
    logger.info("Using legacy context_needed matching...")
    
    # 检测合并任务
    is_merge_task = ("merge" in ... or "合并" in ...)
    if is_merge_task:
        # 依赖所有前面的任务
        ...
    else:
        # 字符串匹配 context_needed 和 key_entities
        ...
```

#### 优化后

```python
# P0 Optimization: Resolve dependencies - fully rely on depends_on_task_ids
# Removed legacy context_needed string matching for consistency
for i, (task_desc, planned_task) in enumerate(zip(intent_result.tasks, planned_tasks)):
    if task_desc.depends_on_task_ids:
        # Use explicit task indices from intent understanding
        depends_on_ids = []
        for dep_index in task_desc.depends_on_task_ids:
            # Validate index is within bounds
            if 0 <= dep_index < len(task_id_map) and dep_index in task_id_map:
                depends_on_ids.append(task_id_map[dep_index])
            else:
                logger.warning(
                    "Invalid task dependency index",
                    task_index=i,
                    depends_on_index=dep_index,
                    total_tasks=len(task_id_map),
                )
        
        if depends_on_ids:
            planned_task.depends_on = depends_on_ids
            planned_task.priority = len(depends_on_ids) + 1
    else:
        # No explicit dependencies - task is independent
        # Log if context_needed suggests there might be dependencies
        if task_desc.context_needed:
            logger.info(
                "Task has context_needed but no depends_on_task_ids - treating as independent",
                task_index=i,
                context_needed=task_desc.context_needed,
                description=task_desc.description[:100],
            )
```

**改进点**：
- ✅ 完全移除了 `context_needed` 字符串匹配逻辑
- ✅ 完全依赖 `depends_on_task_ids`（由意图理解提供）
- ✅ 如果 `context_needed` 存在但没有 `depends_on_task_ids`，记录信息日志但不设置依赖
- ✅ 逻辑更一致，减少歧义

---

### 3. 添加技能验证

#### 新增方法

```python
def _validate_and_fix_skill(self, skill_name: str) -> str:
    """P1 Optimization: Validate skill exists, return valid skill name.
    
    Args:
        skill_name: Skill name to validate
        
    Returns:
        Valid skill name (original if valid, default if invalid)
    """
    if not skill_name:
        return "general-security"
    
    try:
        from app.prompts.skills import get_skill_registry
        registry = get_skill_registry()
        
        # Check if skill exists in registry
        skill = registry.get(skill_name)
        if skill:
            return skill_name
        
        # Skill not found, use default
        logger.warning(
            "Skill not found in registry, using default",
            skill_name=skill_name,
            available_skills=[s.name for s in registry.list_skills()[:10]],  # Log first 10
        )
        return "general-security"
    except Exception as e:
        # If registry access fails, log and use default
        logger.warning(
            "Failed to validate skill (registry access error), using default",
            skill_name=skill_name,
            error=str(e),
        )
        return "general-security"
```

#### 使用位置

```python
# Determine skill name (only for security tasks)
skill_name = None
if task_type == TaskType.SECURITY:
    # Priority 1: Use skill_hint from intent understanding
    skill_name = task_desc.skill_hint
    
    # Priority 2: Validate skill exists, if not use fallback
    if skill_name:
        skill_name = self._validate_and_fix_skill(skill_name)
    
    # Priority 3: Fallback to security_subtype mapping
    if not skill_name:
        security_subtype = getattr(intent_result, 'security_subtype', None)
        if security_subtype:
            subtype_value = security_subtype.value if hasattr(security_subtype, 'value') else str(security_subtype)
            skill_name = self.SECURITY_SKILL_MAPPING.get(subtype_value, "general-security")
        else:
            skill_name = "general-security"
    
    # Final validation
    skill_name = self._validate_and_fix_skill(skill_name)
```

**改进点**：
- ✅ 在任务规划阶段验证技能是否存在
- ✅ 如果技能不存在，使用默认技能 `general-security`
- ✅ 记录警告日志，包含可用技能列表（前10个）
- ✅ 处理技能注册表访问失败的情况
- ✅ 在多个位置进行验证（skill_hint 和最终确定时）

---

## 优化效果

### 代码质量改进

1. **可维护性提升**
   - 任务类型推断逻辑从 ~70 行减少到 ~25 行
   - 依赖关系处理逻辑从 ~60 行减少到 ~30 行
   - 代码更清晰，易于理解

2. **一致性提升**
   - 完全依赖意图理解提供的 `task_type` 和 `depends_on_task_ids`
   - 移除了可能产生不一致结果的后备逻辑
   - 技能验证确保所有技能都是有效的

3. **错误处理改进**
   - 添加了警告日志，便于调试
   - 技能验证失败时有明确的降级策略
   - 依赖索引验证更严格

### 功能改进

1. **任务类型确定更准确**
   - 优先使用意图理解提供的 `task_type`
   - 减少了推断错误的可能性

2. **依赖关系更可靠**
   - 完全依赖明确的 `depends_on_task_ids`
   - 避免了字符串匹配可能产生的错误依赖

3. **技能使用更安全**
   - 在规划阶段就验证技能是否存在
   - 避免了执行阶段才发现技能不存在的问题

---

## 测试建议

### 1. 任务类型推断测试

- ✅ 测试 `task_type` 明确设置的情况
- ✅ 测试 `task_type` 未设置但 `expertise_needed` 设置的情况
- ✅ 测试 `task_type` 和 `expertise_needed` 都不设置的情况（应该使用默认值并记录警告）

### 2. 依赖关系测试

- ✅ 测试 `depends_on_task_ids` 明确设置的情况
- ✅ 测试 `depends_on_task_ids` 未设置的情况（应该作为独立任务）
- ✅ 测试 `depends_on_task_ids` 包含无效索引的情况（应该记录警告并忽略）

### 3. 技能验证测试

- ✅ 测试有效技能名称（应该通过验证）
- ✅ 测试无效技能名称（应该使用默认技能并记录警告）
- ✅ 测试技能注册表访问失败的情况（应该使用默认技能并记录警告）
- ✅ 测试 `skill_hint` 为空的情况（应该使用后备逻辑）

---

## 总结

### 已完成的优化

1. ✅ **简化任务类型推断逻辑**：从多层 if-else 简化为优先使用 `task_type`，简单后备
2. ✅ **移除依赖关系后备逻辑**：完全依赖 `depends_on_task_ids`，移除 `context_needed` 字符串匹配
3. ✅ **添加技能验证**：在任务规划阶段验证技能是否存在，无效时使用默认技能

### 关键改进

- **代码简化**：减少了约 100 行复杂逻辑
- **逻辑一致性**：完全依赖意图理解提供的信息
- **错误预防**：在规划阶段就发现和修复问题
- **可维护性**：代码更清晰，易于理解和修改

### 后续建议

- 确保意图理解总是提供 `task_type` 和 `depends_on_task_ids`
- 监控警告日志，识别需要改进的地方
- 考虑添加单元测试覆盖这些优化
