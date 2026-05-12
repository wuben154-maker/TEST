# 意图理解 → 主 Agent → 专业 Agent 流程与 Skill 规范分析

> 基于对 `deep_agent.py`、`task_instruction_builder.py`、`official_subagents.py`、DeepAgents 官方实现及 Anthropic Agent Skills 文档的阅读，对当前流程合理性、与官方 DeepAgents 的契合度以及 Skill 规范符合性进行分析。

---

## 一、当前流程概览

```
用户输入 (text + files)
    ↓
[1] IntentUnderstandingMiddleware.understand()  → IntentResult
    ↓
[2] 意图分支 (intent_handlers 责任链)
    - parameter_request → 返回 parameter_request 事件，结束
    - simple_question → 直接 LLM 响应，结束
    - unknown / out_of_scope → 引导或提示，结束
    - 专业任务 → 继续
    ↓
[3] TaskPlanner.plan_tasks()  → TaskPlan (SECURITY/RESEARCH/CONTEXT)
    ↓
[4] CONTEXT 任务预处理 (run_context_tasks_stream / collect_context_results)
    ↓
[5] build_task_instruction()  → 任务指令（含 subagent_type、description）
    ↓
[6] 主 Agent (create_deep_agent) astream()
    - 输入: HumanMessage(build_task_instruction(...))
    - 主 Agent 通过 task(subagent_type, description) 调用 SubAgentMiddleware
    ↓
[7] SubAgentMiddleware 的 task 工具
    - 选择 subagent_type (email-security, web-security, deep-research, ...)
    - 创建 HumanMessage(description)
    - 调用对应 SubAgent 的 runnable.invoke()
    ↓
[8] SubAgent 执行 (带 SkillsMiddleware, skills=["/skills/email-security/"])
    - SkillsMiddleware 从 backend (/skills/) 加载 SKILL.md 元数据
    - 执行分析 / 研究任务
    - 返回 ToolMessage 给主 Agent
    ↓
[9] adapt_astream_to_sse  → SSE 事件流
```

---

## 二、与 DeepAgents 官方设计的契合度

### 2.1 官方 DeepAgents 的设计要点

从 `app/_vendor/deepagents/` 可见：

1. **create_deep_agent** 内置中间件栈：
   - TodoListMiddleware
   - MemoryMiddleware（可选）
   - SkillsMiddleware（可选，需传入 `skills` 参数）
   - FilesystemMiddleware
   - SubAgentMiddleware
   - SummarizationMiddleware
   - PatchToolCallsMiddleware

2. **SubAgent 调用方式**：
   - 主 Agent 通过 `task` 工具调用
   - 工具签名为 `task(description, subagent_type, runtime)`
   - SubAgent 由 SubAgentMiddleware 提供，每个 SubAgent 可配置 `skills`、`tools`、`middleware`

3. **官方假设**：
   - 主 Agent 接收用户输入，自行决定是否调用 `task`
   - 主 Agent 根据任务复杂度、独立性选择 subagent_type
   - 主 Agent 可并发调用多个 task（并行子任务）

### 2.2 当前实现与官方的差异

| 维度 | 官方设计 | 当前实现 | 评估 |
|------|----------|----------|------|
| **主 Agent 输入** | 用户原始输入 | 预构建的 `build_task_instruction()` 指令，显式列出「按顺序调用 task(subagent_type, description)」 | ⚠️ 偏离：主 Agent 不再做「是否调用 task」「选哪个 subagent」的决策 |
| **任务规划** | 主 Agent 自行规划 | 意图理解 + TaskPlanner 预先规划，主 Agent 仅执行 | ✅ 合理：在安全分析场景下，意图理解可减少主 Agent 的规划负担、提升路由准确率 |
| **主 Agent 的 Skills** | 可选 `skills` 参数 | **未传入** `skills`，主 Agent 无 SkillsMiddleware | ⚠️ 主 Agent 不加载任何 Skill 元数据，符合当前「只做路由/调度」的定位 |
| **SubAgent 的 Skills** | 每个 SubAgent 可配置 `skills` | 每个 SubAgent 有 `skills=[f"/skills/{skill.name}/"]` | ✅ 符合官方 SubAgent 规范 |
| **Backend 与 Skills 来源** | StateBackend 需 invoke(files=...)，FilesystemBackend 从磁盘加载 | 使用 CompositeBackend，`/skills/` 路由到 FilesystemBackend(SKILLS_DIR) | ✅ 符合官方 SkillsMiddleware 的 backend 协议 |
| **task 工具调用** | 主 Agent 自由选择 subagent_type 和 description | 指令中显式给出 subagent_type 和 description，主 Agent 照做 | ⚠️ 主 Agent 更像是「执行器」而非「规划者」 |

### 2.3 设计取舍的合理性

**当前架构本质上是「预规划 + 主 Agent 执行」**：

- **优点**：
  - 意图理解可在 Phase 1 做分流（简单问题、参数请求、超出范围等），减少主 Agent 调用
  - 任务规划在 LLM 意图分类阶段完成，便于与 skill 映射（SECURITY_SKILL_MAPPING）绑定
  - 主 Agent 输入明确，有利于稳定、可预测的执行路径
  - 适合安全分析这种「高确定性路由」场景

- **缺点 / 风险**：
  - 主 Agent 的「自主规划」能力被削弱，更像是「脚本执行器」
  - 若任务规划出错（如选错 skill），主 Agent 难以自主纠错
  - 与官方「主 Agent 自由选择 task」的示例用法不完全一致，但属于合理的业务定制

**结论**：在安全分析场景下，预规划 + 主 Agent 执行的模式是**合理且可接受的**，但需要清楚这是对官方「主 Agent 主导规划」模式的扩展，而非 1:1 复刻。建议在 `docs/ARCHITECTURE.md` 中显式说明这一设计取舍。

---

## 三、Skill 使用与 Anthropic 规范符合性

### 3.1 Anthropic Agent Skills 规范要点

根据 [Anthropic Agent Skills 文档](https://docs.anthropic.com/en/docs/agents-and-tools/agent-skills/overview)：

1. **SKILL.md 结构**：
   - 必须有 YAML frontmatter（`---` 包裹）
   - 必需字段：`name`、`description`
   - `name`：1–64 字符，小写字母、数字、连字符，不能以连字符开头/结尾，不能包含 `--`
   - `description`：1–1024 字符，说明 Skill 做什么及何时使用
   - 主体为 Markdown 指令（工作流、最佳实践、示例）

2. **Progressive Disclosure（渐进披露）**：
   - Level 1：元数据（name、description）——启动时加载，轻量
   - Level 2：SKILL.md 主体——Skill 被触发时加载
   - Level 3：资源文件（脚本、参考文档）——按需加载

3. **文件系统模型**：
   - Skill 以目录形式存在，包含 SKILL.md 及可选脚本
   - Claude 通过 bash/read_file 读取 SKILL.md 等

### 3.2 DeepAgents 官方的 SkillsMiddleware 实现

`app/_vendor/deepagents/middleware/skills.py`：

- 遵循 [agentskills.io](https://agentskills.io/specification) 规范
- `SkillMetadata`：`name`、`description`、`path`、`license`、`compatibility`、`allowed_tools`
- 从 backend 的 `ls_info`、`download_files` 加载 SKILL.md
- 校验 `name` 与目录名一致、`description` 长度等

### 3.3 当前 Skill 结构（以 email-security 为例）

```yaml
---
name: email-security
display_name: Email Security Analyst
description: Analyze email headers, detect phishing indicators, ...
version: 1.0.0
author: security-team
triggers: [...]
tags: [...]
workflow_steps: [...]
---
```

### 3.4 规范符合性分析

| 规范项 | Anthropic / agentskills.io | 当前实现 | 符合性 |
|--------|----------------------------|----------|--------|
| **name** | 1–64 字符，小写字母数字连字符 | `email-security` ✅ | ✅ |
| **description** | 1–1024 字符，非空 | 有且 < 1024 | ✅ |
| **name 与目录名一致** | 必须 | `email-security` 目录 ↔ name | ✅ |
| **YAML frontmatter** | 必须 | 有 `---` 包裹 | ✅ |
| **SKILL.md 主体** | Markdown 指令 | 有 Capabilities、Workflow、Output Format 等 | ✅ |
| **display_name, version, triggers, workflow_steps** | 非规范字段 | 项目扩展字段 | ⚠️ 扩展字段，DeepAgents SkillsMiddleware 会忽略，仅项目内部使用 |
| **allowed-tools** | 规范可选字段 | 当前未用 | ⚠️ 可考虑补充以约束工具范围 |

**结论**：当前 Skill 的 `name`、`description`、frontmatter、目录结构均符合 Anthropic / agentskills.io 规范。`display_name`、`triggers`、`workflow_steps` 等为项目自定义扩展，由 `app/prompts/skills/loader.py` 使用，不影响 DeepAgents SkillsMiddleware 的加载逻辑（SkillsMiddleware 只解析 `name`、`description`、`path`、`license`、`compatibility`、`allowed_tools`）。

### 3.5 双轨 Skill 加载

当前存在两套 Skill 加载机制：

1. **DeepAgents SkillsMiddleware**（官方）：
   - 从 backend `/skills/{skill_name}/` 加载
   - 解析 YAML frontmatter → SkillMetadata
   - 注入系统提示中的技能列表（元数据 + 路径）
   - SubAgent 通过 `skills=[f"/skills/{skill.name}/"]` 使用

2. **app/prompts/skills/loader.py**（自研）：
   - 从 `SKILLS_DIR` 加载
   - 解析为 `SkillSpec`（含 `workflow_steps`、`triggers` 等扩展字段）
   - 用于 `create_security_subagents` 构建 SubAgent 的 `name`、`description`、`system_prompt`

两套机制都读取同一个 `skills/*/SKILL.md` 文件，但解析逻辑不同：官方 SkillsMiddleware 只关心规范字段；自研 loader 解析扩展字段。**建议**：在 `SkillSpec` 与 `SkillMetadata` 之间建立明确映射，避免两套解析结果不一致（例如 description 被截断或格式不同）。

---

## 四、总结与建议

### 4.1 流程合理性

| 环节 | 评估 | 说明 |
|------|------|------|
| 意图理解 → 任务规划 | ✅ 合理 | 符合「预规划 + 确定性路由」的业务需求 |
| 主 Agent 仅执行指令 | ⚠️ 合理但偏离官方 | 主 Agent 不做自主规划，属于业务定制 |
| CONTEXT 预处理 | ✅ 合理 | 先收集上下文再注入任务指令，减少主 Agent 负担 |
| SubAgent 通过 task 工具调用 | ✅ 符合官方 | 使用 SubAgentMiddleware 的 task 工具 |
| Skills 加载路径 | ✅ 符合官方 | Backend `/skills/` → FilesystemBackend，SubAgent 配置 skills |

### 4.2 与 DeepAgents 官方的契合度

- **架构层面**：使用官方 `create_deep_agent`、SubAgentMiddleware、SkillsMiddleware、Backend 协议，整体架构一致。
- **执行模式**：采用「预规划 + 主 Agent 执行」而非「主 Agent 自由规划」，是合理的场景化扩展，但需在文档中明确说明。

### 4.3 Skill 规范符合性

- **Anthropic / agentskills.io**：`name`、`description`、frontmatter、目录结构符合规范。
- **扩展字段**：`display_name`、`triggers`、`workflow_steps` 等为项目扩展，不影响规范兼容性；建议在 SKILL.md 中补充 `allowed-tools`（如需要）以更好约束工具使用。

### 4.4 优先级建议

1. **文档化**：在 `ARCHITECTURE.md` 中明确写出「预规划 + 主 Agent 执行」的设计取舍，以及与官方「主 Agent 自主规划」的差异。
2. **Skill 一致性**：统一 `SkillSpec`（loader）与 `SkillMetadata`（SkillsMiddleware）的解析约定，避免 description 等字段不一致。
3. **可选**：为主 Agent 增加 `skills` 参数（如 `/skills/` 根目录），让主 Agent 也能看到技能元数据，便于在 fallback 或简单任务中自主选择；当前无此需求可暂不实施。
4. **可选**：在 SKILL.md frontmatter 中增加 `allowed-tools`，与 Anthropic 规范对齐，便于后续与更多工具集成。

---

## 五、官方模式改造（已完成）

已完成按 DeepAgents 官方模式的 Skill 加载改造：

1. **新增 `app/prompts/skills/discovery.py`**：仅解析 frontmatter 的 `name`、`description`，不做 full SKILL.md 解析。
2. **重构 `create_security_subagents`**：使用 `discover_skill_metadata()` 获取技能列表，SubAgent 采用通用 `SUBAGENT_BASE_PROMPT`，不再预加载 SKILL.md 正文。
3. **SkillsMiddleware 负责完整加载**：SubAgent 运行时，SkillsMiddleware 从 backend `/skills/{name}/` 加载元数据并注入系统提示，LLM 按需通过 `read_file` 读取 SKILL.md。
4. **UnifiedSkillRegistry 薄适配层**：基于 discovery 提供 `get()`、`list_skills()`，供 task_planner、main.py、security_subagents 等兼容使用。
5. **loader.py 保留**：用于测试及需要完整 SkillSpec（含 triggers、workflow_steps）的 legacy 场景；主流程已不再依赖。

---

> 本分析基于 2025-02 的代码与文档状态，若后续有重构，建议同步更新 `project_context.md` 与 `ARCHITECTURE.md`。
