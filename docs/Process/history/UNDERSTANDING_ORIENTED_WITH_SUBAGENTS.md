# 理解导向 + 专业子智能体架构设计

## 核心问题

**如何做到既能用理解导向，又能把安全的专业任务交给专业的子智能体执行？**

## 设计目标

1. ✅ **理解导向**：不强制分类，灵活理解用户意图
2. ✅ **专业执行**：安全任务由专业子智能体执行
3. ✅ **智能路由**：根据理解结果智能匹配到合适的 skill
4. ✅ **动态适应**：支持复杂、混合、边界情况

## 架构设计

### 整体流程

```
用户输入
  ↓
[理解导向的意图理解]
  → 理解意图（不强制分类）
  → 生成任务描述
  → 提取关键信息
  ↓
[智能路由层]
  → 根据意图描述匹配 skill
  → 确定执行方式（skill / research / direct）
  ↓
[专业执行层]
  → 安全任务 → 专业子智能体（skill）
  → 研究任务 → Deep Research Agent
  → 其他任务 → 直接执行
```

### 关键设计点

#### 1. 意图理解阶段：理解导向

**不再强制分类，而是理解意图并生成任务描述**

```python
class IntentResult:
    """理解导向的意图理解结果"""
    # 移除强制分类
    # task_category: TaskCategory  # ❌ 移除
    
    # 改为意图描述
    intent_description: str  # ✅ 自然语言描述意图
    intent_type: str  # ✅ 意图类型（但不强制枚举）
    
    # 任务信息
    tasks: list[TaskDescription]  # ✅ 直接生成任务描述
    key_entities: list[str]
    analysis_goals: list[str]
    
    # 上下文需求
    needs_more_context: bool
    context_queries: list[dict]
```

**提示词改进**：

```python
"""
You are an intelligent assistant. Understand what the user wants to accomplish.

## Your Goal
1. Understand the user's intent (don't force it into categories)
2. Identify what they want to achieve
3. Break down into actionable task descriptions
4. Consider context from previous conversations

## Task Description Format
For each task, provide:
- What needs to be done (natural language)
- What type of expertise is needed (security/research/general)
- Key information needed (entities, files, context)

## Flexibility
- Support any type of request
- Handle complex, multi-step tasks
- No need to fit into predefined categories
- If it's a security task, describe what security analysis is needed
- If it's research, describe what research topic
- If it's something else, describe it naturally

## Return Format
{
  "intent_description": "用户想要...",
  "intent_type": "security_analysis|research|history_query|result_merge|...",
  "tasks": [
    {
      "description": "分析邮件的安全威胁",
      "expertise_needed": "security",
      "skill_hint": "email-security",  // 可选：建议的 skill
      "key_entities": ["email.eml"],
      "context_needed": []
    }
  ],
  "key_entities": [...],
  "analysis_goals": [...]
}
"""
```

#### 2. 智能路由层：Skill 匹配

**根据意图描述，智能匹配到合适的 skill**

```python
class SmartRouter:
    """智能路由：根据意图描述匹配 skill"""
    
    def __init__(self, skill_registry: SkillRegistry):
        self.registry = skill_registry
    
    async def route_intent(
        self, 
        intent_result: IntentResult
    ) -> ExecutionPlan:
        """根据意图理解结果，生成执行计划"""
        
        execution_plan = ExecutionPlan()
        
        for task_desc in intent_result.tasks:
            # 1. 确定执行方式
            execution_type = self._determine_execution_type(task_desc)
            
            if execution_type == "skill":
                # 2. 匹配 skill
                skill = self._match_skill(task_desc)
                
                if skill:
                    execution_plan.add_task(
                        type="skill",
                        skill_name=skill.name,
                        task_description=task_desc.description,
                        context=task_desc.context_needed
                    )
                else:
                    # 没有匹配的 skill，使用通用安全 skill
                    execution_plan.add_task(
                        type="skill",
                        skill_name="general-security",
                        task_description=task_desc.description
                    )
            
            elif execution_type == "research":
                execution_plan.add_task(
                    type="research",
                    topic=task_desc.description,
                    context=task_desc.context_needed
                )
            
            else:
                # 直接执行（通用任务）
                execution_plan.add_task(
                    type="direct",
                    description=task_desc.description
                )
        
        return execution_plan
    
    def _determine_execution_type(self, task_desc: TaskDescription) -> str:
        """确定执行方式"""
        expertise = task_desc.expertise_needed.lower()
        
        if expertise == "security":
            return "skill"
        elif expertise == "research":
            return "research"
        else:
            return "direct"
    
    def _match_skill(
        self, 
        task_desc: TaskDescription
    ) -> SkillSpec | None:
        """智能匹配 skill"""
        
        # 1. 如果任务描述中有 skill_hint，优先使用
        if task_desc.skill_hint:
            skill = self.registry.get(task_desc.skill_hint)
            if skill:
                return skill
        
        # 2. 基于任务描述查询匹配的 skill
        matches = self.registry.find_by_query(task_desc.description)
        if matches:
            # 返回优先级最高的匹配
            return matches[0][1]
        
        # 3. 基于关键实体匹配
        for entity in task_desc.key_entities:
            # 根据文件类型匹配
            if entity.endswith((".eml", ".msg")):
                return self.registry.get("email-security")
            elif entity.endswith((".exe", ".dll", ".bin")):
                return self.registry.get("binary-analysis")
            elif entity.endswith((".pcap")):
                return self.registry.get("network-analysis")
        
        # 4. 基于标签匹配
        if "email" in task_desc.description.lower():
            return self.registry.get("email-security")
        elif "malware" in task_desc.description.lower() or "binary" in task_desc.description.lower():
            return self.registry.get("binary-analysis")
        elif "web" in task_desc.description.lower() or "xss" in task_desc.description.lower():
            return self.registry.get("web-security")
        
        # 5. 默认返回通用安全 skill
        return self.registry.get("general-security")
```

#### 3. 执行层：专业子智能体

**根据执行计划，调用相应的执行器**

```python
class ExecutionEngine:
    """执行引擎：根据执行计划调用相应的执行器"""
    
    def __init__(
        self,
        subagent_middleware: SubAgentMiddleware,
        research_agent: DeepResearchAgent,
        direct_executor: Any
    ):
        self.subagent = subagent_middleware
        self.research = research_agent
        self.direct = direct_executor
    
    async def execute_plan(
        self,
        plan: ExecutionPlan
    ) -> ExecutionResult:
        """执行计划"""
        
        results = []
        
        for task in plan.tasks:
            if task.type == "skill":
                # 调用专业子智能体
                result = await self.subagent.run_skill(
                    skill_name=task.skill_name,
                    task_description=task.task_description,
                    context=task.context
                )
                results.append({
                    "type": "skill",
                    "skill": task.skill_name,
                    "result": result
                })
            
            elif task.type == "research":
                # 调用研究智能体
                result = await self.research.research(
                    topic=task.topic,
                    context=task.context
                )
                results.append({
                    "type": "research",
                    "result": result
                })
            
            else:
                # 直接执行
                result = await self.direct.execute(
                    description=task.description
                )
                results.append({
                    "type": "direct",
                    "result": result
                })
        
        return ExecutionResult(results)
```

## 完整流程示例

### 示例 1：简单安全任务

```
用户输入："分析这个邮件"

[意图理解]
  → intent_description: "用户想要分析邮件的安全威胁"
  → intent_type: "security_analysis"
  → tasks: [
      {
        description: "分析邮件 email.eml 的安全威胁，检测钓鱼、恶意附件、可疑链接",
        expertise_needed: "security",
        skill_hint: "email-security",
        key_entities: ["email.eml"]
      }
    ]

[智能路由]
  → 匹配到 skill: "email-security"
  → 执行方式: skill

[专业执行]
  → 调用 SubAgentMiddleware.run_skill("email-security", ...)
  → 专业子智能体执行邮件安全分析
```

### 示例 2：复杂混合任务

```
用户输入："分析这个文件，然后研究相关漏洞"

[意图理解]
  → intent_description: "用户想要分析文件并研究相关漏洞"
  → intent_type: "compound_task"
  → tasks: [
      {
        description: "分析文件 sample.exe 的安全威胁",
        expertise_needed: "security",
        skill_hint: "binary-analysis",
        key_entities: ["sample.exe"]
      },
      {
        description: "研究从文件分析中提取的漏洞信息",
        expertise_needed: "research",
        key_entities: []
      }
    ]

[智能路由]
  → Task 1: 匹配到 skill "binary-analysis"
  → Task 2: 路由到 research agent

[专业执行]
  → Task 1: 调用 binary-analysis skill
  → Task 2: 调用 Deep Research Agent
  → 合并结果
```

### 示例 3：边界情况

```
用户输入："前面几次分析的结果是什么？"

[意图理解]
  → intent_description: "用户想要查询历史分析结果"
  → intent_type: "history_query"
  → tasks: [
      {
        description: "查询会话中的历史分析结果",
        expertise_needed: "general",
        key_entities: []
      }
    ]

[智能路由]
  → 执行方式: direct（不需要专业 skill）

[执行]
  → 直接查询历史记录
  → 返回结果
```

## 实现方案

### 阶段 1：增强意图理解（理解导向）

**修改 `IntentResult` 和提示词**：

```python
@dataclass
class IntentResult:
    """理解导向的意图理解结果"""
    # 意图描述（自然语言）
    intent_description: str
    intent_type: str  # 不强制枚举
    
    # 任务列表
    tasks: list[TaskDescription] = field(default_factory=list)
    
    # 关键信息
    key_entities: list[str] = field(default_factory=list)
    analysis_goals: list[str] = field(default_factory=list)
    suggested_approach: str = ""
    
    # 上下文需求
    needs_more_context: bool = False
    context_queries: list[dict] = field(default_factory=list)
    
    # 元数据
    confidence: float = 0.8
    reasoning: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass
class TaskDescription:
    """任务描述"""
    description: str  # 任务描述（自然语言）
    expertise_needed: str  # security/research/general
    skill_hint: str = ""  # 建议的 skill 名称（可选）
    key_entities: list[str] = field(default_factory=list)
    context_needed: list[str] = field(default_factory=list)
```

### 阶段 2：实现智能路由层

**创建 `SmartRouter` 类**：

```python
class SmartRouter:
    """智能路由：根据意图描述匹配 skill"""
    
    def __init__(self, skill_registry: SkillRegistry):
        self.registry = skill_registry
    
    async def route_intent(
        self,
        intent_result: IntentResult
    ) -> ExecutionPlan:
        """路由意图到执行计划"""
        # 实现见上方
        ...
```

### 阶段 3：集成到主流程

**修改 `DeepAgentWithIntent`**：

```python
class DeepAgentWithIntent:
    def __init__(self, session_id: str = "default"):
        # ... 现有初始化 ...
        
        # 添加智能路由
        self.smart_router = SmartRouter(
            skill_registry=get_skill_registry()
        )
        
        # 添加执行引擎
        self.execution_engine = ExecutionEngine(
            subagent_middleware=self.subagent_middleware,
            research_agent=self.research_agent,
            direct_executor=self._create_direct_executor()
        )
    
    async def analyze_stream(
        self,
        text: str,
        files: list[dict] | None = None,
        skip_intent: bool = False,
        language: str = "en",
    ) -> AsyncGenerator[dict, None]:
        """分析流程（增强版）"""
        
        # 1. 意图理解（理解导向）
        intent_result = await self.intent_middleware.understand(
            text=text,
            files=files,
            session_id=self.session_id,
            language=language,
        )
        
        # 2. 智能路由
        execution_plan = await self.smart_router.route_intent(intent_result)
        
        # 3. 执行计划
        execution_result = await self.execution_engine.execute_plan(execution_plan)
        
        # 4. 返回结果
        yield from self._format_results(execution_result)
```

## 优势对比

### 当前系统（分类导向）

```
用户输入 → 强制分类 → 静态路由 → 执行
  ↓
问题：
- 只有 4 种分类，限制灵活性
- 边界情况归类为 unknown
- 无法处理复杂混合任务
```

### 新系统（理解导向 + 智能路由）

```
用户输入 → 理解意图 → 智能路由 → 专业执行
  ↓
优势：
- 不限制意图类型，灵活理解
- 智能匹配 skill，专业执行
- 支持复杂、混合、边界情况
- 保持专业性的同时提高灵活性
```

## 实施步骤

### 步骤 1：修改意图理解（1-2 天）
1. ✅ 修改 `IntentResult`，移除强制分类
2. ✅ 添加 `TaskDescription` 数据类
3. ✅ 修改提示词，改为理解导向

### 步骤 2：实现智能路由（2-3 天）
1. ✅ 创建 `SmartRouter` 类
2. ✅ 实现 skill 匹配逻辑
3. ✅ 实现执行计划生成

### 步骤 3：集成执行引擎（2-3 天）
1. ✅ 创建 `ExecutionEngine` 类
2. ✅ 集成到主流程
3. ✅ 测试各种场景

### 步骤 4：优化和测试（1 周）
1. ✅ 优化 skill 匹配算法
2. ✅ 处理边界情况
3. ✅ 性能优化

## 关键设计原则

### 1. 理解优先，路由其次
- **意图理解阶段**：专注于理解用户意图，不强制分类
- **路由阶段**：根据理解结果，智能匹配到合适的执行器

### 2. 专业能力保留
- **安全任务**：仍然由专业子智能体（skill）执行
- **研究任务**：由 Deep Research Agent 执行
- **其他任务**：直接执行或通用处理

### 3. 灵活性与专业性平衡
- **灵活性**：理解阶段不限制意图类型
- **专业性**：执行阶段使用专业能力
- **智能路由**：连接理解和执行

## 总结

**核心思路**：
1. **理解阶段**：理解导向，不强制分类
2. **路由阶段**：智能匹配，找到合适的执行器
3. **执行阶段**：专业执行，利用子智能体的专业能力

**关键创新**：
- 将"分类"改为"理解 + 路由"
- 保持灵活性的同时保留专业性
- 智能匹配 skill，而不是静态路由

这样既能达到 Manus 级别的灵活性，又能保持专业子智能体的专业性。
