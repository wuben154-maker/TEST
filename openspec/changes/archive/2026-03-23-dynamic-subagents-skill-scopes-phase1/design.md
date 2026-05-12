## Context

- **现状**：`build_subagent_specs()` 对每个 `discover_skill_metadata` 条目生成一个 SubAgent，`name`/`description` 来自 Skill；工具来自 `get_tools_for_agent(meta.name)` 的分支。主 Agent 侧 `create_deep_agent(..., subagents=...)` 一次性固定列表；`SubAgentMiddleware` 内 `TASK_TOOL_DESCRIPTION` 拼接 `available_agents`。
- **目标（Phase 1）**：官方 Skill 仍为 **权威内容来源**，但 **编排层** 改为：**SubAgent 定义** 与 **Skill 目录发现** 分离又可组合；**委派元数据** 单一来源生成。

## Goals / Non-Goals

**Goals:**

- 提供 `SkillSource`（或等价协议）接口：`list_official_packages()` Phase 1 实现；`list_tenant_packages(tenant_id)` **返回空或 NotImplemented 占位**，类型与调用点固定，便于 Phase 2 填实现。
- 引入 **SubAgentSpec** 概念：`id`, `enabled`, **`bundle_path`（子 Agent 包根目录）**, `description`, `routing_hints`, `tool_profile_ref`, **`skill_roots`**（默认含 `bundle/skills/` + 可选附加全局包 id）、`include_shared_skills`, `runtime_kind`（`standard` | `compiled_subgraph` 等）、`source`（`official` | 预留 `user`）。
- **RegistryBuilder**：读取 **`subagents.registry.yaml`** → 过滤 **`enabled: true`** → 解析每条目的 **`bundle_path`** → 自包内加载 **`AGENT.md`** 与 **`skills/`** → 合并 `SkillSource` / 共享桶 → 输出 `SubAgentSpec[]` 供 `create_deep_agent` 使用。
- **同源委派文案**：从 Registry 生成 `available_agents` 段落或结构化列表，注入 `task` 工具描述（与 vendor 补丁点对齐），避免手写路由表。
- **主 Agent 侧装配**：主 Agent 的 **可见技能包索引** 由 **全局 `skills/` 与各包 `skill.config.yaml`** 决定；**子 Agent 清单、`task()` 文案与每子 Agent 的 system prompt / skills 根** 由 **`subagents.registry.yaml`（启用项 + `bundle_path`）+ 各 bundle 目录（D10）** 决定，不在代码里写死枚举。
- **渐进披露（不变）**：默认上下文中只注入 **紧凑技能元数据**（名称、简述、路径/定位符）；完整 **SKILL.md** 仅在模型执行 **read_skill / read_file**（或等价）时加载，避免 Token 膨胀。
- 保留 **deep-research** 等编译子图作为 Registry 中 `runtime_kind=compiled` 的一条目，而非与「一个 skill 目录」强行 1:1。

**Non-Goals:**

- 不实现租户存储、市场、冲突解析、多租户 RLS。
- **不实现** 用户/租户 **自定义子 Agent 包** 的注册、上传与扫描（仅 **官方** `source: official`）；与 D10 预留字段不矛盾。
- 不强制统一全量 SSE 事件模型（可与后续变更衔接）。
- 不要求一次删掉所有 `get_tools_for_agent` 分支；允许 Phase 1 将分支 **收敛为** `TOOL_PROFILES[profile_id]` 映射，由 SubAgentSpec 引用 `profile_id`。

## Decisions

### D1. Skill 与 SubAgent 配置分离

- **决策**：全局 **Skill 仓库**（如 `skills/`）仍由 `SkillSource` / `skill.config.yaml` 描述；**每个子 Agent 包** 自带 **`skills/` 子目录** 存放 **仅该子 Agent 使用** 的包（或与全局包并存）。Registry 通过 **`bundle_path` + 可选 `extra_skill_package_ids`** 拼出本子 Agent 的 SkillsMiddleware `sources`。
- **备选**：仅扁平 `skills/`、无 per-agent 目录 —— 被拒（与「独立目录统一设计」不一致）。

### D2. 共享 Skill 桶

- **决策**：可选 `shared_skills` 源（如 `/skills/_shared/` 或 frontmatter `scope: global`）同时挂到主 Agent 与选定 SubAgent；**主 Agent 默认 Skill 列表** 与 **各 SubAgent 的 skill_paths** 在设计上区分。
- **理由**：满足「子 Agent 有自己专属 skill」同时保留通用安全基线。

### D3. 动态扩展的边界

- **决策**：Phase 1「动态」= **由配置文件驱动注册表内容**，而非在业务代码里硬编码类型列表；**不要求**多进程间零停机热插拔。
- **与 D9 配合**：配置变更何时生效（重启 / 新会话 / 显式 reload）由 **D9** 明确；本条强调「扩展方式」而非「刷新频率」。

### D4. 路由「非写死」的含义

- **决策**：**不**在 Python 中维护 `if intent == x: use email-security`；主 Agent **仅**依赖模型 + **系统注入的** SubAgent 目录（description 中含 **when to use** 由注册表字段 `routing_hints` 填充）。可选：后续再加轻量分类器，**不在本 Phase 强制**。
- **理由**：用户要求的「动态可扩展」首先落在 **目录与 schema 同源**，而非新意图引擎。

### D5. 与大包变更的关系

- **决策**：`agent-skill-tenancy-capability-model` 中的租户、冲突、SSE 统一信封 **延后**；本 Phase 的 `SkillSource` 接口 **预留** `tenant_id` 参数（可为 Optional）以便无缝衔接。

### D6. SubAgent 类型 `id` 与历史 `meta.name` 字符串兼容

- **决策（Phase 1 规范）**：凡由旧逻辑「**一个技能目录 → 一个 SubAgent**」已存在的类型，注册表中的 **`id` 必须与该技能包的 `meta.name`（即目录名 / discovery 输出的 name）完全一致**。这样 `task(subagent_type=…)`、前端展示键、历史日志与评测脚本保持不变。
- **新增 SubAgent**：`id` **必须**为稳定 kebab-case；若该类型主要服务某技能包，**推荐** `id` 仍与该包 `package_id` 一致，除非刻意提供「多 Skill 合一」的合成类型（此时 `id` 为新的合成名，且须在 `routing_hints` 中写清适用场景）。
- **备选**：自由重命名 + 别名映射表 —— 延后；Phase 1 不引入别名复杂度。

### D7. Skill 编排配置文件（包内，可选）

- **文件位置**：每个官方技能包目录根下可选 **`skill.config.yaml`**（UTF-8）。若缺省，编排层仅从 **SKILL.md YAML frontmatter** + **目录名** 推断（与现网兼容）。
- **职责划分**：
  - **SKILL.md frontmatter**：面向 LLM 与文档（`name`, `description`, `version` 等），继续由 SkillsMiddleware / 人类阅读使用。
  - **skill.config.yaml**：面向 **运行时编排**（索引范围、标签、预留字段），避免把实现细节堆进 frontmatter。
- **建议字段**（Phase 1 实现子集，其余预留）：

```yaml
# skill.config.yaml — example schema (versioned)
schema_version: 1
package_id: email-security          # optional; default = parent directory name
visibility:
  index_on_main: true               # whether main agent skill index lists this package
  subagent_only: false              # if true, exclude from main index unless shared bucket forces
tags: [email, phishing]             # optional, for future filtering / tenancy
# reserved for Phase 2+: capability_id, requires.bins, etc.
```

- **合并规则**：`package_id` 缺省 → 目录名；`visibility` 缺省 → 与当前「全局 skills 源」行为等价（主/子均可通过路径读，索引策略由 Registry 再裁剪）。

### D8. SubAgent 注册表配置文件（全局 — 启用与发现入口）

- **文件位置**：建议 `python-agent-service/config/subagents.registry.yaml`（路径可 settings 覆盖）。
- **职责**：声明 **哪些子 Agent 启用**、**官方/用户来源（Phase 1 仅 official）**、**bundle 根路径**、`task()` 用 **description / routing_hints**、**tool_profile**、**运行时种类**、可选 **附加全局 skill 包 id**（迁移期兼容）。
- **主 Agent 发现流程**：读 registry → **`enabled: true` 且 `source: official`**（Phase 1 忽略或拒绝 `user`）→ 解析 `bundle_path` → 进入目录加载 **D10** → 生成 `SubAgentSpec` → `create_deep_agent` + `TASK_TOOL_DESCRIPTION` **同源**。
- **建议顶层结构**（与 D10 配套）：

```yaml
# subagents.registry.yaml — example schema
schema_version: 2
defaults:
  bundles_root: subagents/official    # optional; bundle_path can be relative to this
shared_skills:
  package_ids: []
subagents:
  - id: email-security
    enabled: true
    source: official                  # Phase 1 only official; user reserved for future
    bundle_path: email-security       # => subagents/official/email-security/ when relative
    description: "Short line for task() catalog"
    routing_hints: "Use when ..."
    tool_profile: email-security
    extra_skill_package_ids: []       # optional: pull-in legacy global skills/ packages by id
    include_shared_skills: true
    runtime: standard
  - id: deep-research
    enabled: true
    source: official
    bundle_path: deep-research
    description: "..."
    routing_hints: "..."
    tool_profile: deep-research
    extra_skill_package_ids: []
    include_shared_skills: false
    runtime: compiled
```

- **加载顺序**：校验 `id` 唯一、`bundle_path` 存在且含 **D10 必需文件**（`AGENT.md` 或编译型例外）→ 合并 `bundle/skills/**` 与 `extra_skill_package_ids` 解析路径 → 构建子 Agent 列表。
- **与 D7 关系**：全局 `skills/` 内包的 `skill.config.yaml` 仍管 **主索引**；**bundle/skills/** 下包可沿用同一套 **每包 SKILL.md + 可选 skill.config.yaml** 约定。

### D10. 子 Agent 包目录（统一布局；Phase 1 官方）

- **根路径**：默认 **`python-agent-service/subagents/official/<id>/`**（与 registry `bundle_path` 对应）；部署可通过 `bundles_root` 改写。
- **必选 / 推荐文件**：
  - **`AGENT.md`**：子 Agent **system prompt 正文**（Markdown）；可含可选 YAML frontmatter（仅文档/本地元数据），**委派用 `description` / `routing_hints` 以 registry 为准**，避免与 `task()` 文案双源漂移。
  - **`skills/`**：目录；**每个直接子目录** 为一个 Skill 包（内含 **`SKILL.md`**，可选 **`skill.config.yaml`**），约定与全局仓库 **相同**，便于工具链复用。
- **编译型子 Agent**（`runtime: compiled`）：允许 **`AGENT.md` 省略或极短**（若运行时完全由编译子图驱动）；**`skills/`** 仍可用于渐进披露与文档一致；具体以实现校验规则为准。
- **Phase 1**：仅加载 **`source: official`** 且存在于发行目录下的 bundle；**`source: user`** 可出现在 schema 中但必须 **默认禁用或解析器拒绝**，待未来「用户自定义子 Agent」变更启用。
- **未来用户自定义**：同一布局，根路径例如 **`subagents/user/<id>/`** 或租户配置目录；registry 增加 `source: user` + 鉴权/扫描根列表；**本 Phase 不实现**扫描与用户上传，仅在 design 与 schema 预留。

### D11. 特化子 Agent（如 open_deep_research）如何与统一模型对齐

**要统一的不是「内部实现」，而是「产品边界与编排接口」。** `open_deep_research` 这类 **预编译子图（CompiledSubAgent）** 与 **标准 DeepAgent 子规格（SubAgent dict）** 在 DeepAgents 里 **本就对应两种构造路径**；统一设计做在 **registry → 适配器 → 最终条目** 这一层。

```
subagents.registry.yaml  (同一 schema：id / enabled / bundle / description / runtime …)
            │
            ▼
    RegistryBuilder.dispatch
            │
     ┌──────┴──────┐
     ▼             ▼
runtime:      runtime:
standard      compiled  ──► 注册表中的工厂函数（代码内）
     │             │        例如 build_open_deep_research_compiled_subagent(...)
     ▼             │        内部仍是 LangGraph compile、专用节点，不强行改成 AGENT+skills 图
  读 AGENT.md    ◄─┘
  + bundle/skills/
  + TOOL_PROFILES
     │
     ▼
  二者都产出 SubAgentMiddleware 可接受的
  「SubAgent | CompiledSubAgent」列表项
```

- **统一的部分**  
  - **启用与发现**：与其它子 Agent 一样，由 registry **`enabled` + `bundle_path` + `source`** 控制是否出现在主 Agent 视野里。  
  - **`task(subagent_type)` 目录**：`description` / `routing_hints` **只来自 registry**，与标准子 Agent 同源生成，主模型不靠硬编码分支选类型。  
  - **Bundle 目录（D10）**：编译型仍可有 **`subagents/official/deep-research/`**，用于 **`skills/`**（渐进披露文档）、可选短 **`AGENT.md`**、运维说明；**不要求**用同一套「纯 prompt 驱动」替代内部图。  
  - **工具 profile**：registry 的 `tool_profile` 可对编译型 **不适用或部分适用**（由工厂内部决定）；字段可留空或仅作元数据，但 **schema 不换表**。

- **不统一的部分（刻意保留）**  
  - **子图拓扑、节点、状态类型**：仍在 **专用 Python 模块**（如 `build_open_deep_research_compiled_subagent`）中维护。  
  - **流式事件形状**：继续由 **现有 adapter** 归一到 SSE；不要求与标准子 Agent 字节级相同。

- **实现要点**：维护 **`COMPILED_SUBAGENT_BUILDERS: dict[str, Callable[..., CompiledSubAgent]]`**（或等价），key 为 registry **`id`**（如 `deep-research`）。`RegistryBuilder` 见 `runtime: compiled` 则 **调用对应工厂**，入参包含 **resolved bundle 路径、registry 行、Skill 根列表**（便于给子图挂 SkillsMiddleware 或读 SKILL.md）。**新增编译型类型 = 新工厂 + registry 一行 + bundle 目录**，不在 `official_subagents.py` 里再写散落 `if meta.name == "deep-research"`。

- **与 Claude Code 类比**：内置 **Plan / Explore** 与自定义 `.md` 子 Agent **对外都是「可被委派的 agent type」**；内部有的走轻量模板、有的走硬编码管线。SecManus 的 **registry + `runtime` + 工厂** 起的就是这层「外观统一、实现可特化」的作用。

### D9. 配置文件变更是否必须重启后台？

**结论：不必然，但取决于你把「注册表快照」绑在生命周期的哪一层。** 分三层说明：

| 变更对象 | 典型生效方式 | 是否必须重启 |
|----------|----------------|--------------|
| **`SKILL.md` 正文**（渐进披露） | 模型下次 **read_file** 读到的是磁盘当前内容 | **否**（除非实现层对文件内容做了长期内存缓存且未失效） |
| **`skill.config.yaml`**（索引/可见性） | 若每次 **构建会话 Agent** 或每次 **合并 SkillSource** 时重新读盘，则 **新会话** 即可生效 | **否**（对已创建的长生命周期 graph 可能仍用旧索引，直到重建） |
| **`subagents.registry.yaml`**（启用项、bundle 路径、子 Agent 列表、`task` 描述） | 若 `create_deep_agent` 仅在 **进程启动** 调用一次，则 registry 变更 **必须重启**（或 **显式 reload** 重新编译图） | **是**，除非实现「每会话 / 定时 / 管理接口 reload」 |
| **某 bundle 内 `AGENT.md` / `skills/`** | 与 **SKILL.md** 类似：重建图或新会话后可见索引/提示词变化；**渐进披露** 的正文仍按需读文件 | 依 **D9** 与是否缓存文件内容而定 |

**推荐 Phase 1 默认（实现简单、行为可预期）**：

1. **进程启动时** 读取 `subagents.registry.yaml` 与扫描 `skill.config.yaml`，构建 **Registry 快照** 并 **`create_deep_agent` 一次** → 配置文件变更 **需要重启** 才能影响主图与子 Agent 枚举。
2. **可选增强（后续或同一 Phase 若工作量允许）**：在 **每次新分析会话**（或每个 WebSocket 连接）创建 **新的** graph 实例时重新读 registry → **改 YAML 后新开会话即生效**，无需重启进程（仍在进行中的旧会话保持旧快照）。
3. **运维向**：提供 **POST /internal/reload-agent-registry**（鉴权保护）触发重新加载与 `create_deep_agent`，作为重启的替代。

**答用户问**：若按「最简单」的启动时单次编译实现，**是，改 skill / subagent 配置文件一般要重启**（或做 reload）。若实现会话级重建 graph，则 **registry 类变更可做到仅重启会话即生效**；**SKILL.md 内容** 在渐进披露模型下通常 **本就不需要重启** 即可在下次读取时看到新正文。

## Risks / Trade-offs

- **[Risk] Registry 与 filesystem 不同步** → **Mitigation**：启动时校验 skill 路径存在性；日志 warning。
- **[Risk] `task` 描述过长** → **Mitigation**：紧凑一行摘要 + `routing_hints` 长度限制；保持 general-purpose 说明。
- **[Trade-off] 纯模型路由可能不稳** → 后续可加 triggers；本 Phase 文档标注局限。
- **[Risk] 用户误以为改配置立即全局生效** → **Mitigation**：在运维文档与 API 文档中写明 **快照边界**（进程级 vs 会话级）；若仅启动时加载，明确「需重启或 reload」。
- **[Risk] `AGENT.md` 与 registry `description` 语义不一致** → **Mitigation**：约定 **`task()` 展示与路由说明以 registry 为准**；`AGENT.md` 专注行为指令（与 D10 一致）。
- **[Risk] 编译型工厂与 registry `id` 不同步** → **Mitigation**：启动时校验 **`runtime: compiled` 的 id 必须在 `COMPILED_SUBAGENT_BUILDERS` 有入口**；缺则 fail fast 或 log error 并跳过该项。

## Migration Plan

1. 新增 Registry 模块与配置，与旧逻辑 **双写对比测试**（同请求下 subagent 列表差异）。
2. 切换 `build_subagent_specs` 调用 Registry 输出。
3. 废弃「每 skill 自动一条 SubAgent」的隐式规则；为每个官方子 Agent 建立 **D10 bundle**（可从现 `skills/<id>` 迁移或 `extra_skill_package_ids` 桥接）；`discover_skill_metadata` 作为全局 SkillSource 数据源之一。
4. 文档与 `project_context.md` 更新。

## Open Questions

- 专属 Skill 是否允许 **仅索引不复制**（同一路径多 SubAgent 引用）— 默认 **允许**，靠提示词约束读取范围（与 D7/D8 一致：`skill_package_ids` 可重复引用同一 `package_id`）。
