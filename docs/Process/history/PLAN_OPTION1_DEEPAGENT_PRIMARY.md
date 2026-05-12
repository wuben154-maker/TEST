# 方案1：以 DeepAgent 为主执行路径的改造方案

> 对应 FLOW_ANALYSIS_CRITIQUE 中「双路径并存」问题的解决方案：将主 Agent 图作为唯一执行入口，**完整保留现有意图理解效果**。

**核心变更**：专业任务（SECURITY/RESEARCH）不再经 `TaskExecutor → AgentTaskAdapter → streamable_subagents`，改为由主 Agent 通过 `task(subagent_type, description)` 工具驱动其内置的 SubAgentMiddleware 执行。

---

## 一、改造目标

| 目标 | 说明 |
|------|------|
| **消除双路径** | 主 Agent 图成为专业任务（SECURITY/RESEARCH）的唯一执行入口 |
| **保留意图理解** | 意图理解的所有能力、分支、效果 100% 保留 |
| **统一 SubAgent 构建** | 移除 streamable_subagents，仅保留 create_deep_agent 内建的 SubAgentMiddleware |
| **简化维护** | 只需理解「意图理解 + 主 Agent 图」一套体系 |

---

## 二、必须保留的意图理解能力清单

以下能力在改造中**不得丢失**，需在方案中逐一落实：

| 能力 | 触发条件 | 当前处理方式 | 保留方式 |
|------|----------|--------------|----------|
| 参数请求 | `intent_result.parameter_requests` 非空 | 返回 `parameter_request` 事件，等待用户提交 | **不变**，仍在 `analyze_stream` 前段处理 |
| 简单问题直接回答 | `is_simple_question` 且 `direct_response` | 直接 LLM 响应，跳过任务规划 | **不变**，仍是单独分支 |
| 超出边界 + 引导 | `TaskCategory.UNKNOWN` 且 `suggested_alternatives` | 显示替代方案，结束 | **不变** |
| UNKNOWN 能力提示 | `TaskCategory.UNKNOWN` 无 alternatives | 显示能力范围提示，结束 | **不变** |
| 两阶段意图理解 | Phase1 + Phase2（若启用） | 文件解析、上下文加载、LLM 分类 | **不变**，`IntentUnderstandingMiddleware` 不动 |
| 澄清重提交 | 正则检测 "Continue analyzing" 等 | 解析原始输入 + 参数，重新理解 | **不变** |
| 语言检测 | 根据用户输入字符 | 覆盖 `language` 参数 | **不变** |
| 短时/长时记忆 | ContextRetriever | 用于意图分类、后续分析 | **不变** |
| CONTEXT 任务 | `task_type == "context"` | ContextRetriever 查询/合并 | **保留**，见 4.3 节 |

---

## 三、目标架构

### 3.1 改造前 vs 改造后

```
【改造前】
用户输入
  → 意图理解 (保留)
  → 分支: 参数/简单问题/超出范围/UNKNOWN → 直接返回
  → TaskPlanner (保留，转 TaskPlan)
  → TaskExecutor → AgentTaskAdapter → streamable_subagents  ← 主路径，绕过主 Agent
  → (失败时) main Agent (adapt_astream_to_sse)              ← 兜底

【改造后】
用户输入
  → 意图理解 (保留，逻辑不变)
  → 分支: 参数/简单问题/超出范围/UNKNOWN → 直接返回
  → TaskPlanner (保留，转 TaskPlan)
  → CONTEXT 任务? → 执行 ContextRetriever，结果注入上下文
  → 构建「任务指令消息」
  → main Agent.astream(任务指令)  ← 唯一执行入口
       → 主 Agent 调用 task(subagent_type, description) 驱动 SubAgent
       → adapt_astream_to_sse 映射为 SSE 事件
  → 生成 conclusion 报告
```

### 3.2 数据流

1. **IntentResult** → 不变，继续支撑所有分支判断  
2. **TaskPlan** → 继续由 TaskPlanner 产出，但用途改为「构造主 Agent 输入」  
3. **任务指令消息** → 新结构：将 TaskPlan 转为供主 Agent 执行的明确指令（见 4.2）

---

## 四、详细改造步骤

### 4.1 意图理解层：零改动

- `IntentUnderstandingMiddleware`、`IntentClassifier`、`ContextRetriever`、`FileParser`、`IntentResult` 等**保持现状**
- 所有分支判断（parameter_request、simple_question、out-of-scope、unknown）**保持现状**
- Phase2 若后续启用，仅在此层扩展，不改本方案

### 4.2 新增：任务指令构造器（TaskPlan → 主 Agent 输入）

**目的**：将 `TaskPlan` 转为主 Agent 可执行的、明确的任务指令。

**新增模块**：`app/middleware/task_instruction_builder.py`

```python
def build_task_instruction(
    user_input: str,
    intent_result: IntentResult,
    task_plan: TaskPlan,
    language: str = "en",
) -> str:
    """Build the enriched prompt for main Agent to execute tasks.
    
    Returns a string that will be the first HumanMessage content.
    """
    # 结构示例:
    # [Intent Summary]
    # Task category: security. Analysis goals: ...
    #
    # [Planned Tasks - Execute in order]
    # 1. subagent_type=email-security, description="..."
    # 2. subagent_type=deep-research, description="..."
    #
    # [User Input]
    # {user_input}
    #
    # [Instruction]
    # Call the task tool for each planned task above, in order. Use the exact
    # subagent_type and description. Do not skip tasks. After all tasks complete,
    # provide a concise summary for the user.
```

**要点**：
- 每个 `PlannedTask` 显式写出 `subagent_type`（即 skill_name，如 `email-security`、`deep-research`）
- `subagent_type` 必须与 `create_deep_agent(subagents=create_security_subagents(...))` 中 SubAgent 的 `name` 一致，二者均来自 `get_skill_registry()`，天然对齐
- 依赖关系通过顺序表达：有 `depends_on` 的任务排在依赖任务之后
- 指令必须足够明确，减少主 Agent 自由发挥，保证按计划调用 `task`

### 4.3 CONTEXT 任务处理策略

CONTEXT 任务（历史查询、结果合并等）不通过子智能体，而是 `ContextRetriever`。

**策略**：在调用主 Agent 前，先执行所有 CONTEXT 任务，将结果注入任务指令。

1. 从 `TaskPlan` 中筛出 `task_type == CONTEXT` 的任务
2. 调用现有 `TaskExecutor._execute_context_task`（或抽出为 `ContextTaskRunner`）执行
3. 将结果拼接到任务指令的 `[Context from previous queries]` 段落
4. 剩余 SECURITY/RESEARCH 任务通过主 Agent 的 `task` 工具执行

若 `TaskPlan` 中仅有 CONTEXT 任务，则只执行 ContextRetriever 逻辑，不调用主 Agent。

### 4.4 主 Agent 调用流程

**修改**：`DeepAgentWithIntent.analyze_stream` 中「专业任务」分支

```python
# 伪代码
if task_plan:
    # 1. 若有 CONTEXT 任务，先执行并收集结果
    context_results = await _run_context_tasks_if_any(task_plan)
    
    # 2. 过滤出 SECURITY/RESEARCH 任务
    exec_tasks = [t for t in task_plan.tasks if t.task_type in (SECURITY, RESEARCH)]
    
    if not exec_tasks:
        # 仅 CONTEXT 任务，直接返回 context_results 的结论
        yield from _format_context_only_response(context_results)
        yield {"type": "done", "id": "done"}
        return
    
    # 3. 构建任务指令（含 context_results）
    task_instruction = build_task_instruction(
        user_input=text,
        intent_result=intent_result,
        task_plan=TaskPlan(tasks=exec_tasks, ...),
        context_results=context_results,
        language=language,
    )
    
    # 4. 调用主 Agent（唯一执行入口）
    initial_state = {
        "messages": [HumanMessage(content=task_instruction)],
        # ... 其他 state 字段
    }
    
    async for event in adapt_astream_to_sse(
        self.agent,  # create_deep_agent 产出的主 Agent
        initial_state,
        config={"configurable": {"thread_id": self.session_id}},
        language=language,
    ):
        yield event
```

### 4.5 移除或废弃的组件

| 组件 | 处理方式 |
|------|----------|
| `streamable_subagents` | **移除**，不再构建独立子智能体图 |
| `AgentTaskAdapter` | **移除**，主 Agent 通过 `task` 工具直接调用 SubAgentMiddleware |
| `TaskExecutor._execute_security_task` | **移除** |
| `TaskExecutor._execute_research_task` | **移除**（已与 security 合并） |
| `TaskExecutor._execute_context_task` | **保留并复用**，用于 CONTEXT 任务预处理 |
| `adapt_subagent_astream_to_skill_events` | **移除**（或保留用于未来扩展） |
| `create_streamable_subagents` | **移除** |

### 4.6 TaskExecutor 职责收窄

- **保留**：`execute_plan_stream` 中仅负责 CONTEXT 任务执行的逻辑  
- **重命名/拆分**：可拆为 `ContextTaskRunner`，专门处理 CONTEXT 任务  
- **移除**：SECURITY/RESEARCH 的执行逻辑  

或更简单：保留 `TaskExecutor`，但 `execute_plan_stream` 仅对 CONTEXT 任务 yield 事件；SECURITY/RESEARCH 不再经此路径。

### 4.7 主 Agent System Prompt 增强

在 `MASTER_SYSTEM_PROMPT` 或传入 `create_deep_agent` 的 `system_prompt` 中，增加对「按任务指令调用 task」的明确说明：

```markdown
## Task Execution Mode

When the user message contains a [Planned Tasks] section with explicit subagent_type and description:

1. Call the task tool for each task in order
2. Use the exact subagent_type and description from the plan
3. Do not add commentary between task calls
4. When all tasks complete, provide a brief summary for the user
```

避免主 Agent 自行拆任务或改变顺序。

### 4.8 SSE 事件与前端兼容

- 继续使用 `adapt_astream_to_sse`，将主 Agent 的 `agent`/`tools` 节点输出映射为 `tool_call`、`tool_result`、`reasoning`、`conclusion`、`done`
- `task` 工具的一次调用对应：
  - 一个 `tool_call`（task 开始）
  - 一个 `tool_result`（子智能体完成后的 ToolMessage）
- 子智能体内部的 `tool_call`/`tool_result` 在方案1中**不再**逐条上报，仅为一次 task 的聚合结果

若前端强依赖「子智能体内的细粒度步骤」，需单独评估扩展方案（见 六、后续扩展）。

### 4.9 结论报告生成

- 主 Agent 的最后一轮文本可作为 conclusion
- 若需与现有「按任务分组」的报告格式一致，可在 `adapt_astream_to_sse` 后增加一步：根据 `tool_call`/`tool_result` 序列还原任务结构，再调用 `_format_conclusion_report`

### 4.10 错误与 Fallback

- 主 Agent 调用失败时，保持当前策略：记录错误，yield `step`（status=warning），可选 fallback 到简化分析
- 不再存在「streamable 路径 vs 主 Agent 路径」的选择，只有主 Agent 一条路径

### 4.11 初始化顺序修复（顺带）

- 修正 `DeepAgentWithIntent` 中 checkpointer 注入顺序：先 `_create_checkpointer()`，再对 `intent_middleware.context_retriever` 注入 `_checkpointer`

---

## 五、改造任务清单（按阶段）

### 阶段 1：基础改造（约 1 周）

| 序号 | 任务 | 说明 |
|------|------|------|
| 1 | 新增 `task_instruction_builder.py` | 实现 `build_task_instruction` |
| 2 | 修改 `analyze_stream` 专业任务分支 | 用任务指令 + 主 Agent 替代 TaskExecutor（SECURITY/RESEARCH） |
| 3 | 实现 CONTEXT 任务预处理 | 先执行 CONTEXT，结果注入任务指令 |
| 4 | 主 Agent system prompt 增加任务执行说明 | 明确按计划调用 task |

### 阶段 2：清理与验证（约 3–5 天）

| 序号 | 任务 | 说明 |
|------|------|------|
| 5 | 移除 `streamable_subagents` | 删除 `create_streamable_subagents` 及其调用 |
| 6 | 移除 `AgentTaskAdapter` | 删除类及所有引用 |
| 7 | 精简 `TaskExecutor` | 仅保留 CONTEXT 相关逻辑，或拆为 `ContextTaskRunner` |
| 8 | 修复 checkpointer 注入顺序 | 见 4.11 |
| 9 | 端到端回归测试 | 覆盖参数请求、简单问题、超出范围、UNKNOWN、单任务、多任务、CONTEXT 任务 |

### 阶段 3：文档与收尾（约 1–2 天）

| 序号 | 任务 | 说明 |
|------|------|------|
| 10 | 更新 `project_context.md` | 描述新的单一执行路径 |
| 11 | 更新 `ARCHITECTURE.md` / `FLOW_ANALYSIS_CRITIQUE.md` | 标注方案1已落地 |
| 12 | 更新 `DEEPAGENTS_MIGRATION_ASSESSMENT.md` | 说明任务规划与主 Agent 的集成方式 |

---

## 六、后续扩展（可选）

| 扩展 | 说明 |
|------|------|
| **子智能体内部流式** | 若需恢复 subagent 内 tool_call/tool_result 的实时流式，需扩展官方 `SubAgentMiddleware` 或在其外层包装，在 `atask` 中改为 `subagent.astream()` 并转发事件；工作量大，可单独立项 |
| **并行 task 调用** | 主 Agent 已支持在一次回合中发出多个 tool_call，可依赖 prompt 引导其对无依赖任务并行调用 `task` |
| **Phase2 意图理解** | 若启用 Phase2，仅在 `IntentUnderstandingMiddleware` 中扩展，本方案无需调整 |

---

## 七、风险与缓解

| 风险 | 缓解 |
|------|------|
| 主 Agent 未严格按计划调用 task | 加强 system prompt 与任务指令的约束，必要时在指令中采用更结构化的格式（如 JSON） |
| 子智能体内部步骤不再流式 | 在文档中明确这是方案1的取舍，若业务强制要求再推进「子智能体内部流式」扩展 |
| CONTEXT + SECURITY 混合任务的顺序 | 通过 `TaskPlan` 的 `depends_on` 保证 CONTEXT 先执行，其输出写入任务指令 |

---

## 八、验收标准

1. 所有意图理解分支行为与改造前一致（参数请求、简单问题、超出范围、UNKNOWN）  
2. 专业任务（SECURITY/RESEARCH）仅通过主 Agent 的 `task` 工具执行  
3. `streamable_subagents`、`AgentTaskAdapter` 已移除  
4. CONTEXT 任务继续通过 ContextRetriever 正确执行  
5. 前端 SSE 事件协议保持兼容，`adapt_astream_to_sse` 输出格式不变  
6. 端到端测试通过，包括多任务、依赖关系、多语言  

---

> 文档生成日期：2026-02  
> 关联：`FLOW_ANALYSIS_CRITIQUE.md`、`DEEPAGENTS_MIGRATION_ASSESSMENT.md`
