# Subagent 与 Skill 架构说明（DeepAgents框架下SecManus Agent和Skill设计规范）

本文档描述 **当前仓库代码** 中 Deep Agent（LangChain DeepAgents 派生实现）对 **Subagent（子 Agent）** 与 **Skill（技能包）** 的定义、配置与调用链，供后端与全栈同学对齐实现。

> **与 Cursor IDE 的区分**：仓库根目录下的 `.cursor/skills/`、Cursor 的 **Task** 工具等属于 **IDE 侧 Agent 编排**，与本文讨论的 **`python-agent-service` 运行时** 无直接代码耦合。下文若无特殊说明，**Skill / Subagent 均指 Python 服务内逻辑**。

---

## 1. 核心概念速览

| 概念 | 作用 |
|------|------|
| **主 Agent** | `create_deep_agent` 编译出的主图；负责意图理解、`write_todos`、直接工具调用、通过 `task()` 委派子 Agent、汇总报告。 |
| **Subagent** | 独立子图（或预编译 Runnable）；通过工具名 **`task`**、`subagent_type` 参数选择；拥有各自的系统提示、工具集、可选 SkillsMiddleware 源。 |
| **Skill** | 符合 Agent Skills 约定的目录：至少包含 **`SKILL.md`**（YAML frontmatter + 正文）；由 **SkillsMiddleware** 做元数据注入，Agent 通过 **`read_file`** 等后端能力按需读取全文（渐进披露）。 |
| **Backend 虚拟路径** | `CompositeBackend` 将 `/skills/`、`/skills-main/`、`/subagent-skills/<id>/` 等映射到磁盘或过滤视图；SkillsMiddleware 的 `sources` 使用这些 **POSIX 风格路径**。 |

---

## 2. Subagent：类型、定义与配置

### 2.1 类型划分

1. **Standard（标准子 Agent）**  
   - 由注册表 + bundle 目录生成 **字典形态** 的 `SubAgent` 规格，交给 `create_deep_agent`；框架会为每个子 Agent 挂载默认中间件栈，并按规格追加 **SkillsMiddleware**（若配置了 `skills` 源列表）。  
   - 实现入口：`app/agents/subagent_registry.py` → `build_subagent_specs_from_registry()`。

2. **Compiled（编译型子 Agent）**  
   - 使用 **`CompiledSubAgent`**：预构建的 `Runnable`（如独立 LangGraph），**不由** bundle 的 `AGENT.md` 驱动主逻辑。  
   - 当前仓库：**`deep-research`** 在 `runtime: compiled` 且 `RESEARCH_AGENT_MODE=compiled_subagent`（默认）时，由 `COMPILED_SUBAGENT_BUILDERS["deep-research"]` 工厂生成。  
   - 注册表中的 `interrupt_on` 等对 compiled 条目可能被忽略（见 registry 内警告日志）。

3. **General-purpose（通用子 Agent）**  
   - 由 **`create_deep_agent`** 自动追加，**不在** `subagents.registry.yaml` 中声明。  
   - `name` 为 **`general-purpose`**，描述为「复杂检索、多步任务、不确定能否快速命中时的探索型子 Agent」；工具集默认与主 Agent 传入的 `tools` 一致，并带主 Agent 同款的 Skills / HITL 配置（见 `app/_vendor/deepagents/graph.py`）。

### 2.2 代码层定义（Vendor）

`SubAgent` 为 **TypedDict**，关键字段包括（节选，完整见源码）：

- **`name`**：`task()` 的 `subagent_type` 取值。  
- **`description`**：写入 **`task` 工具说明**，供主模型路由。  
- **`system_prompt`**：子 Agent 系统提示。  
- **`tools`**：可选；缺省时在 `create_deep_agent` 处理阶段回退为主 Agent 的 `tools`。  
- **`model`**：可选；覆盖主模型。  
- **`middleware`**：在默认栈之后追加。  
- **`skills`**：SkillsMiddleware 的 **`sources`** 列表（虚拟路径字符串）。  
- **`interrupt_on`**：Human-in-the-loop 配置（需 checkpointer）。

### 2.3 配置文件：`config/subagents.registry.yaml`

- **`schema_version`**：当前为 `2`。  
- **`defaults.bundles_root`**：bundle 根目录，默认 `subagents/official`。  
- **`subagents[]`** 每条典型字段：  
  - **`id`** → 对应 `SubAgent["name"]` / `subagent_type`。  
  - **`enabled`**：为 `false` 则不出现在 `task` 目录中。  
  - **`source`**：`official` | `user`；**当前 `user` 会被跳过并打日志**（Phase 1 策略）。  
  - **`bundle_path`**：相对 `bundles_root` 的目录名。  
  - **`description` / `routing_hints`**：合并为 `task` 工具里的单行说明（`merge_task_catalog_description`），与各 bundle 内 `AGENT.md` **解耦**。  
  - **`tool_profile`**：`default` | `email-security` | `web-security` | `deep-research`，映射到 `build_tool_profiles()` 中的工具列表。  
  - **`extra_skill_package_ids`**：全局 `skills/` 下子目录名；在 **`include_shared_skills: false`** 时，通过 **`/skills-subset/<id>/`** 只暴露这些包。  
  - **`include_shared_skills`**：为 `true` 时子 Agent 的 Skills 源可包含完整 **`/skills/`**。  
  - **`runtime`**：`standard` | `compiled`。  
  - **`interrupt_on`**：可选；标准子 Agent 传入规格字典。

### 2.4 Bundle 目录约定

路径：`subagents/official/<id>/`

- **`AGENT.md`**：标准子 Agent 的系统提示正文；支持可选 YAML frontmatter（正文为 frontmatter 之后部分）。缺失时回退 `SUBAGENT_BASE_PROMPT_FALLBACK`。  
- **`skills/<包名>/SKILL.md`**：bundle 内技能包；经后端挂载到 **`/subagent-skills/<id>/`**（见下文路由）。

---

## 3. Skill：类型、定义与配置

### 3.1 形态（运行时）

- 每个技能是一个**目录**，内含 **`SKILL.md`**。  
- Frontmatter 至少用于 **`name`**、**`description`**（与 Anthropic / DeepAgents 技能规范一致）；正文为操作说明，由模型在需要时 **`read_file`** 加载。  
- SkillsMiddleware **只通过 Backend 读文件**，不直接扫本地盘（便于 StateBackend / 远程存储等后端切换）。

### 3.2 全局技能目录 `skills/`

- 物理路径解析：`app/prompts/skills/discovery.py` 中 **`get_skills_dir()`** / **`SKILLS_DIR`**（支持相对服务根、`cwd`、`SKILLS_DIR` 环境变量、常见容器路径）。  
- **主 Agent 可见性**由 **`config/main_agent_skills.yaml`** 控制：  
  - **`main_agent_skill_packages`**：列表中的**目录名**对应 `skills/<目录名>/`。  
  - 文件**不存在**或**省略该键**：视为「全部包对主 Agent 开放」（开发友好）。  
  - 文件存在且列表**为空**：主 Agent 不挂载有效全局技能源（与实现一致，见 `resolve_main_skills_route_plan`）。  
- **子 Agent**：bundle 内技能**不受**此白名单约束；是否能看到全局 `skills/` 由注册表 **`include_shared_skills`** 与 **`extra_skill_package_ids`** 决定。

### 3.3 虚拟路径与叠加顺序

**子 Agent** 的 SkillsMiddleware `sources` 由 `resolve_skills_middleware_sources()` 计算，顺序语义为（概念上）：**共享全局 → 子集 → bundle 专属**；同名 skill **后写覆盖先写**（DeepAgents 约定）。

典型虚拟前缀：

| 前缀 | 含义 |
|------|------|
| `/skills/` | 全局 `SKILLS_DIR` 下所有子包（FilesytemBackend） |
| `/skills-main/` | 全局目录的**过滤视图**，仅含白名单子目录（主 Agent 使用） |
| `/skills-subset/<subagent_id>/` | 全局目录中**仅** `extra_skill_package_ids` 允许的子目录 |
| `/subagent-skills/<subagent_id>/` | 该子 Agent bundle 下 `skills/` 目录 |

路由注册：`app/backends/composite.py` → `_attach_skill_virtual_routes()`，在 **`create_layered_backend` / `create_middleware_backend`** 时注入。

### 3.4 发现与 API 用元数据

- **`discover_official_skill_packages()`**：扫描 `SKILLS_DIR`，只解析 frontmatter，用于健康检查、`/agents`、校验等。  
- 完整 **`SKILL.md` 正文**仍由运行中的 **SkillsMiddleware** 在模型上下文中按需暴露，而非在发现阶段整文件加载。

---

## 4. 主 Agent 调用 Subagent 的流程

### 4.1 构建阶段

1. **`DeepAgentWithIntent._build_official_agent()`**（`app/agents/deep_agent.py`）调用 **`create_deep_agent(...)`**。  
2. 传入 **`subagents=build_subagent_specs()`**（来自 `official_subagents` → registry）。  
3. 传入 **`backend=self.backend_factory`**（含上传目录、技能虚拟路径等）。  
4. 传入 **`skills=self._main_skills_middleware_sources`**（来自 `resolve_main_skills_route_plan()`，可能为 `["/skills/"]` 或 `["/skills-main/"]`）。  

在 **`create_deep_agent`**（`app/_vendor/deepagents/graph.py`）内：

- 主 Agent 中间件顺序大致为：`TodoListMiddleware` →（可选）`MemoryMiddleware` →（可选）**`SkillsMiddleware`** → **`FilesystemMiddleware`** → **`SubAgentMiddleware`** → `SummarizationMiddleware` → …  
- **`SubAgentMiddleware`** 注册 **`task` / `atask`** 工具，工具描述中包含当前所有子 Agent 的 **`name` + 合并后的 description**。

### 4.2 运行阶段（一次委派）

1. 主模型发起 **tool call**：**`task`**，参数包含 **`subagent_type`**、**`description`**（任务说明，会变为子图的 `HumanMessage`）。  
2. **`_build_task_tool`**（`app/_vendor/deepagents/middleware/subagents.py`）内：  
   - 校验 `subagent_type` 是否存在于预编译的 **`subagent_graphs`**。  
   - 从父状态拷贝子状态（排除内部键），**`messages`** 设为单条 **`HumanMessage(content=description)`**。  
3. **异步路径**（流式分析）：**`atask`** 调用本仓库补丁 **`_ainvoke_subagent_with_sse_queue`**，在子 Agent **`astream`** 期间把事件写入 SSE 适配层（含 **`scope: subagent`**、`subagentName` 等），便于前端时间线合并展示。  
4. 子图结束后，将返回状态中的 **`messages`** 最后一则转为 **`ToolMessage`** 写回主线程，主 Agent 继续 ReAct 循环并汇总（行为受 **`MASTER_AGENT.md`** 约束）。

### 4.3 提示词与路由

- 主系统提示：`app/prompts/MASTER_AGENT.md`（编译进 **`MASTER_SYSTEM_PROMPT`**）。  
- 其中强调：**以运行时注入的 `task` 工具描述为准**；文中 Step 3 表格为操作指引，与工具描述冲突时 **优先工具描述**。  

### 4.4 研究子 Agent 模式开关

- 环境变量 **`RESEARCH_AGENT_MODE`**（默认 **`compiled_subagent`**）：当不为 `compiled_subagent` 时，**`deep-research`** 在 registry 中即使声明 `compiled`，也会被当作 **`standard`** 处理（使用 `AGENT.md` + `tool_profile: deep-research` 工具集）。见 `build_subagent_specs_from_registry()` 内分支。

---

## 5. 主 Agent / 子 Agent 使用 Skill 的流程

### 5.1 中间件如何「挂上」技能

- **SkillsMiddleware** 在 **每次模型请求前** 将可用技能的 **元数据列表**（名称、描述、路径提示）合并进系统消息，使模型知道有哪些 skill 以及 **在 Backend 中的路径**。  
- 模型若判断任务匹配某 skill，应 **`read_file`** 读取对应 **`.../SKILL.md`**，再按正文执行（含调用 **`execute`** 运行脚本等，若后端与策略允许）。

### 5.2 主 Agent

- **配置**：`config/main_agent_skills.yaml` + `SKILLS_DIR`。  
- **代码**：`DeepAgentWithIntent` 构造时 **`resolve_main_skills_route_plan()`** → **`create_deep_agent(..., skills=...)`**。  
- **工具**：主 Agent 在 `deep_agent.py` 中为 **`create_common_tools` + `create_research_tools`**（含 HITL 可选）；与注册表子 Agent 的 **`tool_profile`** 可不同。

### 5.3 子 Agent

- 每个标准子 Agent 在 **`build_subagent_specs_from_registry`** 中写入 **`"skills": skills_sources`**。  
- **`create_deep_agent`** 处理非 compiled 规格时，在默认中间件栈后追加 **`SkillsMiddleware(backend=backend, sources=subagent_skills)`**。  
- 子 Agent 的 **`read_file`** 与主 Agent 共用同一 **`backend_factory`** 路由，因此可访问 **`/uploads/...`**、各自挂载的技能前缀等。

---

## 6. 与前端 / SSE 的衔接（简要）

- 流式接口：`DeepAgentWithIntent.analyze_stream` → **`adapt_astream_to_sse`**；子 Agent 侧事件经 **`adapt_subagent_astream_to_skill_events`** 等合并。  
- 事件上常带 **`scope`**（`main` / `subagent`）、**`subagentName`**、**`seq`** 等，便于时间线渲染与去重。  
- 更完整的字段说明见 **`docs/SSE_EVENT_CATALOG.md`** 与 **`python-agent-service/README.md`** 中 Streaming 小节。

---

## 7. 扩展与运维要点

| 操作 | 建议 |
|------|------|
| 新增标准子 Agent | 在 `subagents.registry.yaml` 增加条目；创建 `subagents/official/<id>/AGENT.md`；按需添加 `skills/`；选择 `tool_profile`。 |
| 新增全局 Skill | 在 `skills/<包名>/SKILL.md` 添加包；若需主 Agent 可见，把 `<包名>` 加入 **`main_agent_skill_packages`**。**`security-report-mermaid`** — Markdown/Mermaid 报告体例，`references/` 与 `templates/` 来自 Apache-2.0 upstream（见包内 `LICENSE`、`NOTICE.txt`）。 |
| 仅让某子 Agent 看到部分全局包 | 设置 **`include_shared_skills: false`**，并填写 **`extra_skill_package_ids`**。 |
| 新增 compiled 子 Agent | 在 **`COMPILED_SUBAGENT_BUILDERS`** 注册工厂；registry **`runtime: compiled`**；实现需返回含 **`messages`** 的状态以便写回主图。 |
| 配置热更新 | 注册表 / `AGENT.md` / 技能修改后，若进程内缓存 Agent 实例，通常需 **新会话** 或 **重启** 才能一致生效（详见 `python-agent-service/README.md`）。 |

---

## 8. 关键源码索引

| 主题 | 路径 |
|------|------|
| 主 Agent 构建与 backend | `python-agent-service/app/agents/deep_agent.py` |
| 注册表解析与技能源计算 | `python-agent-service/app/agents/subagent_registry.py` |
| 注册表 YAML | `python-agent-service/config/subagents.registry.yaml` |
| 主 Agent 技能白名单 | `python-agent-service/config/main_agent_skills.yaml` |
| 技能发现 | `python-agent-service/app/prompts/skills/discovery.py` |
| 后端虚拟路径 | `python-agent-service/app/backends/composite.py` |
| Deep Agent 组装 | `python-agent-service/app/_vendor/deepagents/graph.py` |
| `task` 工具与子 Agent 调用 | `python-agent-service/app/_vendor/deepagents/middleware/subagents.py` |
| Skills 中间件 | `python-agent-service/app/_vendor/deepagents/middleware/skills.py` |
| SSE 适配与子流 | `python-agent-service/app/parsers/deepagents_stream_adapter.py` |
| 主 Agent 行为约定 | `python-agent-service/app/prompts/MASTER_AGENT.md` |

---

## 9. 延伸阅读

- 仓库内历史分析：`docs/Process/history/FLOW_AND_SKILL_ANALYSIS.md`  
- 服务 README（注册表与 SSE 摘要）：`python-agent-service/README.md`  

---

*文档版本：与仓库实现同步维护；若改动 registry、middleware 或 backend 路由，请同步更新本节。*
