# 任务执行流程分析

## 概述

本文档详细分析从任务规划完成后到任务执行的完整流程，特别是如何将一级任务路由到对应的专用智能体执行。

---

## 完整执行流程

```
任务规划完成（TaskPlan）
    ↓
TaskExecutor.execute_plan_stream()
    ├─ 按依赖关系找到就绪任务
    ├─ 根据任务类型路由
    │   ├─ TaskType.SECURITY → _execute_security_task()
    │   │   └─ SubAgentMiddleware.run_skill_stream()
    │   │       ├─ 加载 Skill（从 SkillRegistry）
    │   │       ├─ 检查是否有 workflow_steps
    │   │       ├─ 有 workflow → _run_workflow_mode()
    │   │       └─ 无 workflow → _run_free_mode()
    │   └─ TaskType.RESEARCH → _execute_research_task()
    │       └─ DeepResearchAgent.research_stream()
    └─ 流式返回执行事件
```

---

## 详细流程分析

### Phase 1: 任务执行入口（TaskExecutor.execute_plan_stream）

**位置**：`python-agent-service/app/middleware/task_planner.py:498-567`

**主要逻辑**：

1. **初始化执行状态**
   ```python
   plan.status = TaskStatus.RUNNING
   executed_tasks = set()  # 已执行的任务 ID
   remaining_tasks = list(plan.tasks)  # 待执行的任务列表
   ```

2. **依赖关系管理循环**
   ```python
   while remaining_tasks:
       # 找到可以执行的任务（依赖已完成）
       ready_tasks = []
       for task in remaining_tasks:
           if all(dep in executed_tasks for dep in task.depends_on):
               ready_tasks.append(task)
       
       # 执行第一个就绪的任务
       task = ready_tasks[0]
       # ...
   ```

3. **任务类型路由**
   ```python
   if task.task_type == TaskType.SECURITY:
       # 安全任务 → 调用安全子智能体
       async for event in self._execute_security_task(task, user_input):
           yield event
   else:
       # 研究任务 → 调用 Deep Researcher
       async for event in self._execute_research_task(task, user_input):
           yield event
   ```

---

### Phase 2: 安全任务执行（_execute_security_task）

**位置**：`python-agent-service/app/middleware/task_planner.py:568-728`

**执行流程**：

#### 2.1 获取技能名称
```python
skill_name = task.skill_name or "general-security"
```

**技能来源**：
- 优先使用 `task.skill_name`（来自意图理解的 `skill_hint`）
- 如果没有，使用 `general-security` 作为默认值

#### 2.2 调用 SubAgentMiddleware
```python
async for event in self.security_agent.run_skill_stream(
    skill_name=skill_name,
    task_description=f"{task.description}\n\nUser input:\n{user_input}",
):
    # 转换 SkillEvent 为前端事件格式
    yield event
```

**关键点**：
- `self.security_agent` 是 `SubAgentMiddleware` 实例
- 传入 `skill_name`（如 "email-security", "binary-analysis"）
- 传入任务描述（包含任务描述和用户原始输入）

#### 2.3 事件转换
将 `SkillEvent` 转换为前端期望的事件格式：
- `skill_start` → `step` 事件
- `tool_call` → `tool_call` 事件
- `tool_result` → `tool_result` 和 `task_step` 事件
- `skill_complete` → `step` 事件（完成）
- `skill_error` → `error` 事件

---

### Phase 3: 安全子智能体执行（SubAgentMiddleware.run_skill_stream）

**位置**：`python-agent-service/app/middleware/subagents.py:265-329`

**执行流程**：

#### 3.1 加载 Skill
```python
skill = self._registry.get(skill_name)
if not skill:
    yield SkillEvent("skill_error", ...)
    return
```

**Skill 来源**：
- 从 `SkillRegistry` 中获取
- Skill 定义在 `python-agent-service/app/prompts/skills/` 目录下的 `SKILL.md` 文件

#### 3.2 准备执行环境
```python
model = skill.model or self.default_model  # 使用技能指定的模型或默认模型
all_tools = self.default_tools + list(skill.tools)  # 合并默认工具和技能工具
```

#### 3.3 选择执行模式

**模式 1：Workflow Mode（结构化流程）**
```python
if skill.workflow_steps:
    # 按 workflow_steps 顺序执行
    async for event in self._run_workflow_mode(...):
        yield event
```

**模式 2：Free Mode（自由模式）**
```python
else:
    # LLM 自由决定调用哪些工具
    async for event in self._run_free_mode(...):
        yield event
```

---

### Phase 4: Workflow Mode 执行（_run_workflow_mode）

**位置**：`python-agent-service/app/middleware/subagents.py:331-409`

**执行流程**：

1. **构建消息**
   ```python
   messages = [
       SystemMessage(content=skill.system_prompt),  # Skill 的系统提示词
       HumanMessage(content=task_description),  # 任务描述
   ]
   ```

2. **按步骤执行**
   ```python
   for step_idx, step in enumerate(skill.workflow_steps):
       # 执行每个 workflow step
       # 1. 发送 step 开始事件
       # 2. 调用 LLM（带工具）
       # 3. 执行工具调用
       # 4. 收集结果
       # 5. 发送 step 完成事件
   ```

3. **工具调用**
   - LLM 决定调用哪些工具
   - 执行工具调用
   - 收集工具结果
   - 继续下一步

---

### Phase 5: Free Mode 执行（_run_free_mode）

**位置**：`python-agent-service/app/middleware/subagents.py:411-500`

**执行流程**：

1. **构建 Agent**
   ```python
   agent = create_structured_agent(
       model=model,
       tools=all_tools,
       system_prompt=skill.system_prompt,
   )
   ```

2. **流式执行**
   ```python
   async for event in agent.astream(...):
       # 监听工具调用事件
       # 转换并发送 SkillEvent
   ```

---

### Phase 6: 研究任务执行（_execute_research_task）

**位置**：`python-agent-service/app/middleware/task_planner.py:729-803`

**执行流程**：

```python
async for event in self.research_agent.research_stream(
    query=f"{task.description}\n\n{user_input}",
    language=self.language,
):
    # 转换研究事件为前端格式
    yield event
```

**关键点**：
- `self.research_agent` 是 `DeepResearchAgent` 实例
- 使用 `research_stream` 进行流式研究
- 传入查询（任务描述 + 用户输入）

---

### Phase 7: DeepResearchAgent 执行（research_stream）

**位置**：`python-agent-service/app/agents/research_agent.py:250-398`

**执行流程**：

1. **构建研究 Agent**
   ```python
   agent = create_structured_agent(
       model=self.model,
       tools=self.tools,  # 研究工具（web_search, scrape_url 等）
       system_prompt=RESEARCH_SYSTEM_PROMPT,
   )
   ```

2. **流式执行**
   ```python
   async for event in agent.astream(...):
       # 监听工具调用（web_search, scrape_url 等）
       # 发送研究事件
   ```

---

## 关键组件说明

### 1. TaskExecutor

**职责**：
- 管理任务执行流程
- 处理依赖关系
- 路由任务到对应的智能体
- 转换事件格式

**关键方法**：
- `execute_plan_stream()` - 主执行流程
- `_execute_security_task()` - 安全任务执行
- `_execute_research_task()` - 研究任务执行

---

### 2. SubAgentMiddleware

**职责**：
- 管理技能（Skill）注册表
- 执行技能流式任务
- 支持 Workflow Mode 和 Free Mode

**关键方法**：
- `run_skill_stream()` - 执行技能流式任务
- `_run_workflow_mode()` - 结构化流程执行
- `_run_free_mode()` - 自由模式执行

**技能加载**：
- 从 `SkillRegistry` 获取技能定义
- 技能定义在 `app/prompts/skills/*/SKILL.md` 文件中

---

### 3. DeepResearchAgent

**职责**：
- 执行深度研究任务
- 使用研究工具（web_search, scrape_url 等）
- 生成研究报告

**关键方法**：
- `research_stream()` - 流式研究执行

---

## 任务路由逻辑

### 路由决策

**决策点**：`TaskExecutor.execute_plan_stream()` 中的任务类型判断

```python
if task.task_type == TaskType.SECURITY:
    # 路由到安全子智能体
    async for event in self._execute_security_task(task, user_input):
        yield event
else:
    # 路由到研究智能体
    async for event in self._execute_research_task(task, user_input):
        yield event
```

### 任务类型来源

**来源**：`TaskPlanner._create_plan_from_intent_tasks()`

```python
if task_desc.expertise_needed == "research":
    task_type = TaskType.RESEARCH
else:
    task_type = TaskType.SECURITY
```

**关键字段**：
- `expertise_needed` - 来自意图理解的 `TaskDescription`
- `skill_name` - 来自意图理解的 `skill_hint`

---

## 技能匹配逻辑

### 安全任务的技能选择

**优先级**：
1. **意图理解的 `skill_hint`**（最高优先级）
   - 来自 `TaskDescription.skill_hint`
   - 例如："email-security", "binary-analysis"

2. **security_subtype 映射**（后备）
   - 如果 `skill_hint` 为空，使用 `SECURITY_SKILL_MAPPING`
   - 映射表：
     ```python
     SECURITY_SKILL_MAPPING = {
         "email_analysis": "email-security",
         "malware_analysis": "binary-analysis",
         "web_attack": "web-security",
         "soc_alert": "soc-alert",
         "vuln_scan": "vuln-scan",
         "ioc_lookup": "general-security",
         "generic_security": "general-security",
     }
     ```

3. **默认技能**（最后后备）
   - 如果以上都没有，使用 `"general-security"`

---

## 执行模式

### 安全任务执行模式

#### Workflow Mode（结构化流程）

**触发条件**：Skill 定义了 `workflow_steps`

**执行方式**：
- 按 `workflow_steps` 顺序执行
- 每个 step 有明确的工具调用要求
- LLM 在 step 范围内决定具体工具调用

**示例**：
```yaml
workflow_steps:
  - id: "extract_headers"
    label: "Extract Email Headers"
    tools: ["read_file", "parse_email"]
  - id: "analyze_sender"
    label: "Analyze Sender"
    tools: ["ioc_lookup"]
```

#### Free Mode（自由模式）

**触发条件**：Skill 没有定义 `workflow_steps`

**执行方式**：
- LLM 自由决定调用哪些工具
- 使用 Skill 的系统提示词指导行为
- 可以使用所有可用工具

---

### 研究任务执行模式

**执行方式**：
- 使用 `DeepResearchAgent.research_stream()`
- 流式执行研究流程
- 使用研究工具（web_search, scrape_url 等）
- 生成研究报告

---

## 事件流转换

### SkillEvent → 前端事件

**转换位置**：`TaskExecutor._execute_security_task()`

**转换映射**：

| SkillEvent Type | 前端事件类型 | 说明 |
|----------------|------------|------|
| `skill_start` | `step` | 技能启动 |
| `tool_call` | `tool_call` | 工具调用开始 |
| `tool_result` | `tool_result` + `task_step` | 工具调用完成 |
| `skill_complete` | `step` | 技能完成 |
| `skill_error` | `error` | 技能错误 |

---

## 依赖关系处理

### 依赖关系执行顺序

**逻辑**：
```python
while remaining_tasks:
    # 找到所有依赖已完成的任务
    ready_tasks = [
        task for task in remaining_tasks
        if all(dep in executed_tasks for dep in task.depends_on)
    ]
    
    # 执行第一个就绪的任务
    task = ready_tasks[0]
    # ...
    
    # 标记为已执行
    executed_tasks.add(task.id)
```

**关键点**：
- 依赖关系来自 `task.depends_on`（任务 ID 列表）
- 只有所有依赖任务完成后，才能执行当前任务
- 支持并行执行（如果有多个独立任务）

---

## 错误处理

### 任务执行错误

**处理位置**：`TaskExecutor.execute_plan_stream()`

**错误处理**：
```python
try:
    if task.task_type == TaskType.SECURITY:
        async for event in self._execute_security_task(task, user_input):
            yield event
except Exception as e:
    task.status = TaskStatus.ERROR
    task.error = str(e)
    yield {
        "type": "task_error",
        "id": task.id,
        "error": str(e),
    }
```

### 技能执行错误

**处理位置**：`SubAgentMiddleware.run_skill_stream()`

**错误处理**：
- 技能不存在 → 返回 `skill_error` 事件
- 工具调用失败 → 记录错误，继续执行
- 超时 → 返回超时错误

---

## 总结

### 任务执行流程

1. **任务规划完成** → `TaskPlan` 对象
2. **TaskExecutor 初始化** → 传入 `security_agent` 和 `research_agent`
3. **按依赖关系执行** → 找到就绪任务
4. **任务类型路由** → SECURITY 或 RESEARCH
5. **调用对应智能体** → `SubAgentMiddleware` 或 `DeepResearchAgent`
6. **流式返回事件** → 转换为前端格式

### 关键路由点

1. **任务类型判断**：`task.task_type == TaskType.SECURITY`
2. **技能选择**：`task.skill_name`（来自意图理解的 `skill_hint`）
3. **智能体调用**：`SubAgentMiddleware.run_skill_stream(skill_name, ...)`

### 执行模式

- **安全任务**：Workflow Mode（结构化）或 Free Mode（自由）
- **研究任务**：流式研究模式

### 事件流

- 所有执行都是流式的（`AsyncGenerator`）
- 事件实时转换和发送
- 支持前端实时显示进度
