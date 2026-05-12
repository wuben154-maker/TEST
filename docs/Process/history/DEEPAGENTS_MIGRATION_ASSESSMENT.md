# 迁移至官方 Deep Agents 源码改造评估

> 评估将当前自实现的多智能体架构替换为官方 [langchain-ai/deepagents](https://github.com/langchain-ai/deepagents) 源码所需的改造工作。

---

## 迁移完成状态 (2026-02)

| 组件 | 状态 | 说明 |
|------|------|------|
| **官方代码** | ✅ 100% 下载 | `app/_vendor/deepagents/` 完整 vendored：backends, middleware, graph |
| **Backends** | ✅ 完成 | protocol, utils, state, filesystem, composite, store, local_shell, sandbox |
| **Middleware** | ✅ 完成 | filesystem, memory, subagents, summarization, skills, patch_tool_calls |
| **扩展层** | ✅ 保留 | IntentUnderstandingMiddleware、TaskPlanner、TaskExecutor 作为 agent 之上的业务逻辑 |

---

## 一、当前实现 vs 官方实现 对比概览

| 维度 | 当前实现 (SecManus) | 官方 Deep Agents |
|------|---------------------|------------------|
| **Agent 构建** | LangGraph `StateGraph` 手写图 | `create_agent()` + `create_deep_agent()` |
| **中间件体系** | 自研 `*Middleware` 类 | `langchain.agents.middleware` (`AgentMiddleware`) |
| **子 Agent** | Skill 注册表 + `task`/`parallel_tasks` 工具 | `SubAgentMiddleware` + `task(subagent_type, description)` |
| **意图理解** | 两阶段 `IntentUnderstandingMiddleware` | ❌ 无 |
| **任务规划** | `TaskPlanner` + `TaskExecutor` | ❌ 无（主 Agent 自行决策） |
| **Backend** | 自研 `StateBackend`/`StoreBackend`/`CompositeBackend` | `deepagents.backends` 协议 |
| **依赖版本** | `langchain>=0.3.0`, `langgraph>=0.2.0` | `langchain>=1.2.10`, `langchain-core>=1.2.10` |
| **流式事件** | 自定义 SSE 事件协议 | LangGraph 原生流式 |

---

## 二、核心架构差异

### 2.1 Agent 创建方式

**当前：**
```python
# deep_agent.py - 手写 LangGraph 图
graph = StateGraph(DeepAgentState)
graph.add_node("agent", agent_node)
graph.add_node("tools", tool_node)
graph.add_edge(START, "agent")
graph.add_conditional_edges("agent", should_continue, {"tools": "tools", END: END})
graph.add_edge("tools", "agent")
return graph.compile(checkpointer=self.checkpointer)
```

**官方：**
```python
# deepagents/graph.py - 基于 create_agent
return create_agent(
    model,
    system_prompt=final_system_prompt,
    tools=tools,
    middleware=deepagent_middleware,  # TodoList, Filesystem, SubAgent, Summarization...
    checkpointer=checkpointer,
    store=store,
).with_config({"recursion_limit": 1000})
```

**改造要点：** 需要从「手写 StateGraph」迁移到「`create_agent` + middleware 栈」。官方使用 `langchain.agents.create_agent`，与当前 LangGraph 直接构图方式不同。

---

### 2.2 子 Agent / Skill 模型

**当前：**
- `SkillSpec` + `SkillRegistry`：按 skill 名称（如 `email-security`）注册
- 工具：`task(skill_name, task_description)`、`parallel_tasks(tasks=[...])`
- 主 Agent 通过工具调用子 Agent，子 Agent 由 `SubAgentMiddleware.run_skill_stream` 执行

**官方：**
- `SubAgent` TypedDict：`name`, `description`, `system_prompt`, `tools`, `model`, `middleware`
- 工具：`task(description, subagent_type, runtime)`，通过 `subagent_type` 选择子 Agent
- 子 Agent 由 `create_agent` 编译为 `Runnable`，通过 `SubAgentMiddleware` 注入

**改造要点：**
1. 将 `SkillSpec` 映射为 `SubAgent` 结构
2. 将 `task(skill_name, task_description)` 改为 `task(description, subagent_type)`（官方无 `parallel_tasks`，需在主 Agent 中并行多次 `task` 调用）
3. 官方子 Agent 是完整 Agent 图，每个都有 TodoList/Filesystem/Summarization 等中间件；当前 skill 是轻量级「技能 + 工具」组合

---

### 2.3 意图理解与任务规划（官方无对应能力）

**当前独有：**
- `IntentUnderstandingMiddleware`：两阶段意图理解（Phase1 分类 + Phase2 上下文增强）
- `TaskPlanner`：根据意图生成 `TaskPlan`，拆分为 `PlannedTask`
- `TaskExecutor`：按计划调用 `SubAgentMiddleware.run_skill_stream` 或 `DeepResearchAgent`
- 支持：简单问题直接回答、超出范围建议、参数收集、任务分类路由

**官方：**
- 无意图理解层
- 无显式任务规划器
- 主 Agent 直接根据用户输入决定是否调用 `task` 工具

**改造要点：**
1. **保留意图理解**：作为「前置中间件」或「预处理步骤」，在调用官方 `create_deep_agent` 之前执行
2. **任务规划**：两种策略
   - **策略 A**：保留 `TaskPlanner` + `TaskExecutor`，但 `TaskExecutor` 改为调用官方编译后的 Agent 的 `task` 工具（需通过某种方式注入或模拟）
   - **策略 B**：放弃显式任务规划，依赖主 Agent 自行拆解任务；需在 system prompt 中强化「安全分析任务拆分」指引

---

### 2.4 Backend 协议

**当前：**
- `app/backends/`：`StateBackend`, `StoreBackend`, `CompositeBackend`, `create_layered_backend`
- 与 Supabase / PostgreSQL 集成，支持 `session_parameters` 等加密存储

**官方：**
- `deepagents.backends`：`StateBackend`, `StoreBackend`, `CompositeBackend`
- 协议：`BackendProtocol`, `SandboxBackendProtocol`（支持 `execute`）
- 使用 `BackendFactory` 或实例传入

**改造要点：**
1. 对比 `BackendProtocol` 接口，适配当前实现的 `read`/`write`/`edit`/`ls`/`grep` 等
2. 若官方 backend 与 Supabase 不直接兼容，需实现 `StoreBackend` 的 Supabase 适配器
3. 官方 `FilesystemMiddleware` 依赖 `ToolRuntime` 获取 backend，当前 `FilesystemMiddleware` 直接持有 backend 实例，需统一

---

### 2.5 中间件栈

**当前：**
```
IntentUnderstandingMiddleware (前置，非图内)
TodoListMiddleware
FilesystemMiddleware(backend=composite_backend)
SubAgentMiddleware(registry=skill_registry, default_tools=...)
SummarizationMiddleware
```

**官方：**
```
TodoListMiddleware
[MemoryMiddleware] (若 memory 路径存在)
[SkillsMiddleware] (若 skills 路径存在)
FilesystemMiddleware(backend=backend)
SubAgentMiddleware(backend=backend, subagents=[...])
SummarizationMiddleware
AnthropicPromptCachingMiddleware
PatchToolCallsMiddleware
[HumanInTheLoopMiddleware] (若 interrupt_on 存在)
```

**改造要点：**
1. 用官方 `FilesystemMiddleware`、`SubAgentMiddleware`、`SummarizationMiddleware` 替换自研版本
2. `IntentUnderstandingMiddleware` 需作为「图外预处理」保留
3. 官方使用 `SkillsMiddleware` 从 backend 路径加载 skill 文件；当前 skill 在代码中定义，需决定：迁移到文件系统，或扩展 `SkillsMiddleware` 支持内存 skill

---

### 2.6 流式事件与前端协议

**当前：**
- 自定义 SSE 事件：`step`, `understanding`, `parameter_request`, `tool_call`, `tool_result`, `reasoning`, `conclusion`, `done`
- 与 `useStreamingAnalysis`、`ReasoningPanel`、`TaskExecutionPanel` 等前端组件强耦合

**官方：**
- LangGraph 原生 `astream`：按节点输出 `{node_name: node_output}` 的流
- 无预定义「step/understanding/conclusion」等业务事件

**改造要点：**
1. 在 `analyze_stream` 中，对官方 Agent 的 `astream` 输出做**适配层**：将 `agent`/`tools` 节点输出映射为当前 `step`/`tool_call`/`tool_result`/`reasoning` 等事件
2. `understanding`、`parameter_request` 等来自意图理解层的事件，需在调用 Agent 前/后单独 yield
3. 保持 `parsers/events.py` 与前端协议不变，避免大规模前端改动

---

## 三、依赖升级

| 包 | 当前 | 官方 deepagents 要求 |
|----|------|----------------------|
| langchain | >=0.3.0 | >=1.2.10 |
| langchain-core | (间接) | >=1.2.10 |
| langgraph | >=0.2.0 | (间接，依赖 langchain) |
| langchain-anthropic | >=0.2.0 | >=1.3.3 |
| langchain-google-genai | >=2.0.0 | >=4.2.0 |
| Python | 3.11+ | 3.11+ |

**改造要点：**
1. 升级 `requirements.txt` 至官方兼容版本
2. 注意 `langchain.agents` 模块：`create_agent`、`AgentMiddleware` 等可能在 0.3 vs 1.2 间有 API 变更
3. 需全面回归测试，尤其是工具、中间件、checkpointer 相关逻辑

---

## 四、改造任务清单（按优先级）

### P0 - 必须完成

| 序号 | 任务 | 工作量 | 说明 |
|------|------|--------|------|
| 1 | 依赖升级 | 中 | 升级 langchain/langchain-core 至 1.2+，解决兼容性问题 |
| 2 | 引入 deepagents 包 | 小 | `pip install deepagents` 或作为 git submodule 引入 |
| 3 | Backend 适配 | 中 | 实现 `BackendProtocol` 接口，或包装当前 backend 以兼容 |
| 4 | 子 Agent 迁移 | 高 | 将 `SkillSpec` 转为 `SubAgent`，用 `SubAgentMiddleware` 替换 `SubAgentMiddleware` |
| 5 | 流式事件适配层 | 高 | 将官方 Agent 流式输出映射为现有 SSE 事件协议 |
| 6 | 意图理解保留 | 中 | 在调用 Agent 前执行 `understand_intent`，将结果注入 system prompt 或首条消息 |

### P1 - 重要

| 序号 | 任务 | 工作量 | 说明 |
|------|------|--------|------|
| 7 | 任务规划策略选择 | 中 | 选 A（保留 TaskExecutor 调用官方 task）或 B（放弃，强化 prompt） |
| 8 | Checkpointer 集成 | 中 | 官方支持 `checkpointer` 参数，保持与 PostgreSQL 的兼容 |
| 9 | 安全工具与 Skill 集成 | 中 | 将 `create_common_tools`、security tools 作为 subagent 的 tools 传入 |

### P2 - 可选

| 序号 | 任务 | 工作量 | 说明 |
|------|------|--------|------|
| 10 | 并行任务 | 中 | 官方无 `parallel_tasks`，需在主 Agent prompt 中引导「并行调用多个 task」 |
| 11 | SkillsMiddleware 与 skill 文件 | 低 | 若采用文件系统 skill，需将 `app/prompts/skills/` 转为目录结构 |
| 12 | 简单问题直接回答 | 低 | 当前在意图理解后直接返回，可保留为图外分支 |

---

## 五、推荐迁移路径

### 阶段 1：最小可行迁移（2–3 周）

1. 升级依赖，引入 `deepagents`
2. 用 `create_deep_agent` 创建「无意图理解」的 Agent，仅做基础分析
3. 实现流式事件适配层，使 `analyze_stream` 输出与现有前端协议一致
4. 验证：基础对话、工具调用、子 Agent 调用可正常流式返回

### 阶段 2：业务能力对齐（2–3 周）

1. 将 `SkillSpec` 映射为 `SubAgent`，接入 `SubAgentMiddleware`
2. 保留意图理解作为预处理，将 `IntentResult` 注入首条消息或 system prompt
3. 实现 Backend 与 Supabase 的兼容（若官方无现成实现）
4. 决策：保留或简化 TaskPlanner/TaskExecutor

### 阶段 3：优化与收敛（1–2 周）

1. 优化 prompt，使主 Agent 能更好拆解安全分析任务
2. 评估 `parallel_tasks` 的替代方案（主 Agent 并行调用 task）
3. 完善测试、文档与 `project_context.md` 更新

---

## 六、风险与权衡

| 风险 | 缓解措施 |
|------|----------|
| 依赖升级导致 breaking changes | 分阶段升级，优先在独立分支验证 |
| 官方 API 与当前业务差异大 | 保留适配层，避免前端和业务逻辑大改 |
| 意图理解/任务规划需保留 | 作为图外预处理 + prompt 增强，不依赖官方实现 |
| 官方更新节奏快 | 锁定版本，定期评估升级 |

---

## 七、结论

**是否值得迁移？**

- **优势**：使用官方维护的 Agent 框架，减少自研维护成本；与 LangChain 生态更一致；可享受官方后续能力（如 MCP、新中间件等）
- **成本**：依赖升级、Backend 适配、子 Agent 模型迁移、流式事件适配、意图理解/任务规划的保留与集成，整体工作量约 **4–8 周**（视团队熟悉度而定）

**建议**：若项目对「与官方 Deep Agents 对齐」有明确需求，可按上述三阶段迁移；若当前实现已稳定且无强烈升级动机，可暂缓迁移，仅将官方实现作为参考，逐步吸收其设计思路（如 middleware 结构、SubAgent 规范等）。

---

> 文档生成日期：2026-02-24  
> 参考：https://github.com/langchain-ai/deepagents
