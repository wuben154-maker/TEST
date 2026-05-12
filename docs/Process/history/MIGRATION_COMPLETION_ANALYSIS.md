# 官方 DeepAgent 迁移改造完成度分析

> 基于迁移方案 [官方_deepagent_迁移方案_87bb3bbf.plan.md] 对当前代码进行对照分析。  
> 分析日期：2025-02-25

---

## 一、总体结论

| 维度 | 状态 | 说明 |
|------|------|------|
| **Phase 1** 依赖与基础层 | ✅ 基本满足 | 依赖升级、DatabaseBackend、create_layered_backend 已完成 |
| **Phase 2** Agent 核心替换 | ✅ 满足 | create_deep_agent、7 个 SubAgent（含 deep-research）、AgentTaskAdapter 已实现 |
| **Phase 3** 意图理解与任务规划 | ✅ 满足（按暂不改造方案） | 图外预处理、TaskExecutor 直接驱动，符合 Phase 3 暂缓决策 |
| **Phase 4** 流式事件适配层 | ✅ 完成 | deepagents_stream_adapter 已实现；子 Agent 工具调用实时流已实现 |
| **Phase 5** Checkpointer、Store、配置 | ✅ 完成 | Checkpointer 已集成；灰度回退不需要，已取消 |

**核心功能**：端到端分析流程可跑通（意图理解 → 任务规划 → TaskExecutor → AgentTaskAdapter → create_deep_agent SubAgent）。

---

## 二、逐项对照

### 2.1 Phase 1：依赖与基础层

| 需求 | 实现状态 | 说明 |
|------|----------|------|
| 依赖升级 langchain 1.2+、deepagents 0.4+ | ✅ | requirements.txt 已升级 |
| DatabaseBackend（Supabase/PostgreSQL） | ✅ | database_backend.py 已实现，支持 DATABASE_MODE 切换 |
| create_layered_backend 使用 DatabaseBackend | ✅ | composite.py 中 /memories/、/parameters/ 路由到 DatabaseBackend |
| /skills/ 路由暴露 skills 目录 | ✅ | create_layered_backend 添加 /skills/ → FilesystemBackend(SKILLS_DIR) |
| BackendProtocol 协议 | ✅ 官方协议 | Strategy B：使用 app._vendor.deepagents.backends.protocol，DatabaseBackend 等返回官方类型（FileInfo、GrepMatch、WriteResult 等） |

### 2.2 Phase 2：Agent 核心替换

| 需求 | 实现状态 | 说明 |
|------|----------|------|
| 用 create_deep_agent 替换手写 StateGraph | ✅ | deep_agent.py 已删除手写图，使用 _build_official_agent() 调用 create_deep_agent |
| 7 个 SubAgent（含 deep-research） | ✅ | official_subagents.py 的 create_security_subagents 返回 7 个，含 deep-research |
| deep-research 使用 research_tools | ✅ | deep-research 单独使用 create_research_tools()，其余用 create_common_tools() |
| skills=["/skills/{name}/"] 注入 | ✅ | 每个 SubAgent 配置 skills 路径 |
| AgentTaskAdapter 提供 run_skill_stream | ✅ | Phase 4：优先使用 streamable_subagents.astream() 产出 tool_call/tool_result 实时流；无子图时回退 ainvoke |
| 移除 DeepResearchAgent 独立图 | ✅ | deep_agent.py 已移除 research_agent，TaskExecutor 无 research_agent 参数 |
| RESEARCH 任务路由到 deep-research | ✅ | TaskExecutor 对 TaskType.RESEARCH 调用 _execute_security_task(skill_name_override="deep-research") |

### 2.3 Phase 3：意图理解与任务规划（暂不改造）

| 需求（按暂缓方案） | 实现状态 | 说明 |
|--------------------|----------|------|
| 意图理解为图外预处理 | ✅ | analyze_stream 先调用 understand_intent()，再 TaskPlanner |
| TaskPlanner 保留 | ✅ | 根据 IntentResult 生成 TaskPlan |
| TaskExecutor 直接驱动 AgentTaskAdapter | ✅ | 根据 TaskPlan 调用 run_skill_stream(skill_name, task_description) |
| 无 research_agent 参数 | ✅ | TaskExecutor 仅接收 security_agent |
| 参数请求、简单问题、超出范围 | ✅ | analyze_stream 中 yield parameter_request、reasoning、done 等 |

### 2.4 Phase 4：流式事件适配层

| 需求 | 实现状态 | 说明 |
|------|----------|------|
| 新建 deepagents_stream_adapter.py | ✅ 已实现 | adapt_astream_to_sse、adapt_subagent_astream_to_skill_events |
| 事件映射到前端协议 | ✅ 已实现 | 适配层 + 子 Agent 工具调用实时流 |
| 意图相关事件由 analyze_stream yield | ✅ | step、understanding、parameter_request 等由 analyze_stream 直接产生 |
| 任务执行事件（task_plan、task_step 等） | ✅ | TaskExecutor._execute_security_task 产生 step、tool_call、tool_result、task_step 等 |

**已解决**：Phase 4 已实现 streamable_subagents + adapt_subagent_astream_to_skill_events，AgentTaskAdapter 使用 astream 产出 tool_call、tool_result 的实时流。

### 2.5 Phase 5：Checkpointer、Store、配置

| 需求 | 实现状态 | 说明 |
|------|----------|------|
| Checkpointer 传入 create_deep_agent | ✅ | _build_official_agent 传入 checkpointer |

| 需求 | 实现状态 | 说明 |
|------|----------|------|
| 灰度回退 USE_OFFICIAL_DEEPAGENT | 已取消 | 不需要灰度回退，无需实现 |

---

## 三、文件变更清单对照

| 计划操作 | 实际状态 |
|----------|----------|
| 新增 database_backend.py | ✅ 已实现 |
| 新增 deepagents_stream_adapter.py | ✅ 已实现 |
| 重构 deep_agent.py | ✅ 已接入 create_deep_agent |
| 改造 task_planner.py | ✅ TaskExecutor 已改造 |
| 删除/废弃 subagents.py | ✅ 已删除 | SkillEvent 已迁至 skill_events.py，SubAgentSpec 已迁至 security_subagents.py |
| 改造 research_agent.py | ✅ 已完成 | DeepResearchAgent 独立图已移除，保留说明文档 |
| 保留 intent_understanding.py | ✅ 保持图外预处理 |

---

## 四、主要差距与建议

### 4.1 高优先级

1. ~~**工具调用实时流缺失**~~ → **已实现**：Phase 4 streamable_subagents + adapt_subagent_astream_to_skill_events。

2. ~~**deepagents_stream_adapter 未实现**~~ → **已实现**：adapt_astream_to_sse、adapt_subagent_astream_to_skill_events。

### 4.2 中优先级

3. ~~**灰度回退未实现**~~ → **已取消**：不需要灰度回退方案。

4. ~~**subagents.py 与 research_agent.py 清理**~~ → **已完成**：SkillEvent 迁至 skill_events.py，subagents.py 已删除；DeepResearchAgent 已移除，research_agent.py 保留说明。

### 4.3 低优先级

5. ~~**BackendProtocol 与官方协议**~~ → **已解决**：Strategy B 全面使用 app._vendor.deepagents.backends 官方协议，DatabaseBackend 等已适配。

---

## 五、满足改造需求的核心判断

| 判断项 | 结论 |
|--------|------|
| 是否使用官方 create_deep_agent 作为 Agent 引擎 | ✅ 是 |
| 是否保留意图理解、任务规划业务逻辑 | ✅ 是（图外预处理 + 直接驱动） |
| 安全技能是否通过官方 SubAgent + skills 机制 | ✅ 是 |
| deep-research 是否与安全技能统一为 SubAgent | ✅ 是 |
| 端到端分析流程是否可跑通 | ✅ 是 |
| 前端 SSE 事件协议是否保持兼容 | ✅ 是（含子 Agent 工具调用实时流） |
| 是否具备灰度回退能力 | 不需要 | 已取消灰度回退方案 |

**总结**：当前实现**已满足**改造需求，核心架构已迁移完成。已实现：  
- 子 Agent 工具调用的实时流式事件（Phase 4）  
- 独立流式适配层（deepagents_stream_adapter.py）  
- 灰度回退：不需要，已取消。
