# 意图理解到任务规划流程总结

## 当前流程概览

```
用户输入（文本 + 文件）
    ↓
意图理解（IntentUnderstandingMiddleware.understand）
    ├─ 文件解析和去重（基于 hash_sha256）
    ├─ 上下文加载（短时记忆 + 长时记忆）
    ├─ LLM 意图分类（IntentClassifier.classify）
    │   └─ 生成 tasks 列表（TaskDescription 对象）
    └─ 返回 IntentResult（包含 tasks）
    ↓
任务规划（TaskPlanner.plan_tasks）
    ├─ 有 tasks？
    │   ├─ 是 → _create_plan_from_intent_tasks
    │   │   ├─ 转换 TaskDescription → PlannedTask
    │   │   ├─ 处理依赖关系（基于 context_needed）
    │   │   └─ 返回 TaskPlan
    │   └─ 否 → _create_simple_plan
    │       └─ 创建单一任务计划（后备机制）
    ↓
任务执行（TaskExecutor.execute_plan_stream）
    └─ 按依赖关系执行任务
```

---

## 详细流程分析

### Phase 1: 意图理解（IntentUnderstandingMiddleware）

#### 1.1 文件处理
- **文件解析**：解析各种文件类型（email, log, binary, etc.）
- **文件去重**：基于 `hash_sha256` 检测并移除重复文件
- **文件信息提取**：提取文件名、类型、内容等

#### 1.2 上下文加载
- **短时记忆**：当前会话的上下文
- **长时记忆**：历史会话的相关信息
- **上下文摘要**：生成上下文摘要供 LLM 使用

#### 1.3 意图分类（IntentClassifier.classify）
- **LLM 调用**：使用 `MASTER_AGENT.md` 提示词
- **任务生成**：生成 `TaskDescription` 对象列表
  - `description`: 任务描述
  - `expertise_needed`: security/research/general
  - `skill_hint`: 建议的技能名称
  - `key_entities`: 关键实体（文件、IP、域名等）
  - `context_needed`: 需要的上下文（任务依赖）

#### 1.4 返回结果
- **IntentResult**：包含 `tasks` 列表和其他元数据

---

### Phase 2: 任务规划（TaskPlanner）

#### 2.1 主流程（plan_tasks）

**决策逻辑**：
```python
if intent_result.tasks:
    # 有任务 → 使用意图理解的任务
    return _create_plan_from_intent_tasks(intent_result, language)
else:
    # 无任务 → 创建简单计划（后备）
    return _create_simple_plan(intent_result, language)
```

#### 2.2 任务转换（_create_plan_from_intent_tasks）

**转换逻辑**：
1. **遍历意图理解的任务列表**
2. **确定任务类型**：
   - `expertise_needed == "research"` → `TaskType.RESEARCH`
   - 否则 → `TaskType.SECURITY`
3. **确定技能名称**：
   - 优先使用 `skill_hint`
   - 否则根据 `security_subtype` 映射
   - 最后使用 `general-security`
4. **创建 PlannedTask 对象**
5. **处理依赖关系**：
   - 检测合并任务（包含 "merge"/"合并"）
   - 合并任务依赖所有前面的任务
   - 其他任务根据 `context_needed` 和 `key_entities` 匹配依赖

#### 2.3 简单计划（_create_simple_plan）

**后备机制**：
- 当意图理解未生成任务时使用
- 根据 `task_category` 创建单一任务
- 使用 `security_subtype` 映射技能

---

## 当前实现的问题和改进建议

### 🔴 P0 问题（严重）

#### 1. **依赖关系解析不够准确**

**问题**：
- 当前依赖关系解析基于简单的字符串匹配（`context_needed` 和 `key_entities`）
- 可能无法准确识别任务依赖关系
- 合并任务的检测基于关键词（"merge"/"合并"），不够可靠

**改进建议**：
```python
# 改进方案 1：在意图理解阶段明确指定依赖关系
# 在 TaskDescription 中添加 depends_on_task_ids 字段
@dataclass
class TaskDescription:
    # ... 现有字段 ...
    depends_on_task_ids: list[int] = field(default_factory=list)  # 依赖的任务索引

# 改进方案 2：使用更智能的依赖匹配
# 基于任务描述和 key_entities 的语义匹配，而不是简单的字符串匹配
```

#### 2. **简单计划可能不够准确**

**问题**：
- 当意图理解未生成任务时，`_create_simple_plan` 只能创建单一任务
- 如果用户输入了多个文件，应该创建多个任务，但简单计划只创建一个

**改进建议**：
```python
def _create_simple_plan(self, intent_result: Any, language: str) -> TaskPlan:
    # 检查是否有多个文件
    file_count = getattr(intent_result, 'file_count', 0) or 0
    if file_count > 1:
        # 为每个文件创建任务
        tasks = []
        for i in range(file_count):
            task = PlannedTask(...)
            tasks.append(task)
        return TaskPlan(tasks=tasks, is_single_task=False)
    # ... 现有逻辑
```

---

### 🟡 P1 问题（重要）

#### 3. **未使用的复杂度评估方法**

**问题**：
- `_assess_complexity` 方法仍然存在，但不再被调用
- 代码冗余，可能造成混淆

**改进建议**：
- 移除 `_assess_complexity` 方法
- 移除 `COMPLEXITY_INDICATORS` 常量

#### 4. **任务优先级设置不够智能**

**问题**：
- 当前优先级设置：`priority = len(depends_on) + 1`
- 所有独立任务都是 `priority = 1`
- 没有考虑任务的重要性或紧急程度

**改进建议**：
```python
# 在意图理解阶段，LLM 可以评估任务优先级
# 在 TaskDescription 中添加 priority 字段
@dataclass
class TaskDescription:
    # ... 现有字段 ...
    priority: int = 1  # 1 = 最高优先级
```

#### 5. **技能映射可能不完整**

**问题**：
- `SECURITY_SKILL_MAPPING` 是硬编码的映射表
- 如果意图理解返回的 `skill_hint` 不在映射表中，会使用 `general-security`
- 可能无法充分利用所有可用技能

**改进建议**：
- 从技能注册表动态获取可用技能列表
- 验证 `skill_hint` 是否在可用技能列表中
- 如果不在，使用最接近的技能或提示意图理解改进

---

### 🟢 P2 问题（优化）

#### 6. **缺少任务验证**

**问题**：
- 没有验证任务的有效性（如技能是否存在、任务描述是否完整）
- 可能导致执行时出错

**改进建议**：
```python
def _validate_task(self, planned_task: PlannedTask) -> bool:
    """验证任务的有效性"""
    if planned_task.task_type == TaskType.SECURITY:
        if not planned_task.skill_name:
            logger.warning("Security task missing skill_name")
            return False
        # 验证技能是否存在
        # ...
    return True
```

#### 7. **缺少任务去重**

**问题**：
- 如果意图理解生成了重复的任务（相同描述），不会去重
- 可能导致重复执行

**改进建议**：
```python
def _deduplicate_tasks(self, tasks: list[PlannedTask]) -> list[PlannedTask]:
    """去重任务列表"""
    seen = set()
    unique_tasks = []
    for task in tasks:
        task_key = (task.description, task.skill_name, tuple(task.key_entities))
        if task_key not in seen:
            seen.add(task_key)
            unique_tasks.append(task)
    return unique_tasks
```

#### 8. **缺少任务合并优化**

**问题**：
- 如果多个任务可以合并执行（如相同技能、相同文件类型），没有优化
- 可能影响执行效率

**改进建议**：
- 检测可以合并的任务（相同技能、相似描述）
- 提供任务合并选项（可选功能）

---

## 改进优先级建议

### 立即实施（P0）
1. ✅ **改进依赖关系解析**：在意图理解阶段明确指定依赖关系
2. ✅ **改进简单计划**：支持多文件场景

### 近期实施（P1）
3. ✅ **清理未使用代码**：移除 `_assess_complexity` 方法
4. ✅ **改进优先级设置**：在意图理解阶段评估优先级
5. ✅ **改进技能映射**：动态验证和映射技能

### 长期优化（P2）
6. ✅ **任务验证**：添加任务有效性验证
7. ✅ **任务去重**：检测并移除重复任务
8. ✅ **任务合并优化**：优化任务执行顺序

---

## 架构优化建议

### 1. **统一任务描述格式**

**建议**：在意图理解阶段就生成完整的任务信息，包括：
- 任务类型（security/research）
- 技能名称（skill_name）
- 优先级（priority）
- 依赖关系（depends_on_task_ids）

这样任务规划阶段只需要转换格式，不需要再做决策。

### 2. **任务规划器简化**

**建议**：任务规划器可以进一步简化：
- 移除 `_create_simple_plan`（确保意图理解总是生成任务）
- 只保留 `_create_plan_from_intent_tasks`（格式转换）
- 将依赖关系处理移到意图理解阶段

### 3. **错误处理增强**

**建议**：添加更完善的错误处理：
- 意图理解失败时的降级策略
- 任务规划失败时的恢复机制
- 任务执行失败时的重试逻辑

---

## 总结

### 当前架构优势
- ✅ 清晰的职责分离（意图理解 vs 任务规划）
- ✅ 文件去重机制
- ✅ 依赖关系支持
- ✅ 后备机制（简单计划）

### 需要改进的地方
- ⚠️ 依赖关系解析不够准确
- ⚠️ 简单计划不支持多文件
- ⚠️ 未使用的代码需要清理
- ⚠️ 任务验证和去重缺失

### 建议的改进方向
1. **增强意图理解**：让意图理解生成更完整的任务信息
2. **简化任务规划**：任务规划只负责格式转换
3. **增强验证**：添加任务验证和去重机制
4. **优化执行**：改进任务优先级和依赖关系处理
