## Why

当前实现将 **每个官方 Skill 目录映射为一个 SubAgent 类型**（`official_subagents.build_subagent_specs` 遍历 `discover_skill_metadata`），子 Agent 与 Skill **一一绑定**；主 Agent 通过 `task(subagent_type=…)` 只能看到 **固定枚举**，路由依赖提示词与手写分支而非 **与注册表同源的可扩展目录**。这限制新增能力与运维成本。本变更将 **大方案拆解后的 Phase 1**：先只改造 **官方 Skill 来源**、**子 Agent 专属 Skill 集合**、**子 Agent 类型动态扩展**、**主 Agent 委派目录动态生成**；租户级 Skill 与市场冲突策略保留扩展通道，不在本阶段实现。

## What Changes

- **Skill 来源（Phase 1）**：仅使用 **平台官方** Skill 包（现有 `skills/` 或等价路径）；引入 **稳定的 SkillSource / 合并接口**，后续可接入租户源而不改编排内核。
- **子 Agent 与 Skill 解耦**：SubAgent **不再**隐含「一个 skill 名 = 一种 subagent」；每种 SubAgent **声明其专属 Skill 子集**（可多 Skill + 可选共享 Skill），由配置或 manifest 驱动。
- **子 Agent 包目录（Phase 1 官方）**：每个启用的子 Agent 对应 **独立文件目录**（统一约定：提示词文件 + `skills/` 子目录等）；**Phase 1 仅加载官方提供的包**（如 `subagents/official/<id>/`）；**未来**通过同一套目录约定与注册表中的 `source`（或路径前缀）支持 **用户/租户自定义** 子 Agent，本阶段仅预留字段或文档，不实现用户包发现。
- **发现与加载**：主 Agent 仅通过 **`subagents.registry.yaml`** 得知 **哪些子 Agent 启用**、**bundle 根路径**、**工具 profile** 等；运行时 **进入对应目录** 读取 `AGENT.md`（或等价文件名）与 `skills/` 下 Skill 包，再创建/编译该 SubAgent 规格（与全局 `skills/` 仓库可并存，由 registry 声明合并顺序）。
- **子 Agent 可扩展**：启用列表与 bundle 路径由 **注册表** 驱动；新增官方子 Agent **主要**为新增目录 + 注册表一项 + `TOOL_PROFILES`，无需在编排入口硬编码类型名。
- **主 Agent 动态委派**：注入 `task` 工具的 **可用 agent 类型说明 / schema** 与注册表 **同源**，随注册表变化自动更新；**不**依赖写死的「几条路由规则」枚举业务类型。
- **主 Agent 装配逻辑**：主 Agent 的 **技能索引与子 Agent 类型集合** 由 **`skill.config.yaml`（各包）+ `subagents.registry.yaml`（全局）** 在运行时（或按设计文档中的刷新策略）解析后 **动态生成**；**SKILL.md 正文** 仍采用 **渐进披露**（仅元数据/路径进默认上下文，全文按需 `read_file` 或等价加载）。
- **配置文件**：约定 **Skill 包级** `skill.config.yaml`、**全局** `subagents.registry.yaml`（启用项 + 指向各 **子 Agent bundle 目录**），以及 **每子 Agent 包内** `AGENT.md` + `skills/` 布局；细节见 `design.md` **D8 / D10**；刷新语义见 **D9**。
- **SubAgent `id` 兼容**：Phase 1 **强制** 与历史由 `discover_skill_metadata().name`（技能目录名）派生的 `task(subagent_type)` **字符串一致**，避免前端、日志与既有会话语义断裂；**新增** 类型仍使用同一命名约定（kebab-case）。
- **非本阶段**：租户上传/市场安装、RLS、`capability_id` 冲突消解、统一 SSE 信封全量改造（参见既有变更 `agent-skill-tenancy-capability-model`，作为后续阶段）。
- **BREAKING**（缩小）：在遵守 `id` 兼容策略的前提下，**不应**随意重命名既有 SubAgent `id`；若未来必须改名，需单独迁移说明与别名期。

## Capabilities

### New Capabilities

- `skill-sources-official`: Phase 1 仅官方 Skill；Skill 列表合并逻辑；预留 `SkillSource` 扩展点供未来租户源接入。
- `subagent-catalog-delegation`: SubAgent 定义（工具 profile、专属 skills 列表、描述/路由提示）；动态注册表；主 Agent `task` 目录同源生成。

### Modified Capabilities

- （无）`openspec/specs/` 下尚无已归档基线；与 `agent-skill-tenancy-capability-model` 为互补关系而非修改其 delta。

## Impact

- **后端**：`python-agent-service/app/agents/official_subagents.py`、`app/prompts/skills/discovery.py`、`app/tools/enhanced_tools.py`、`_vendor/deepagents` 中与 `task` 描述生成相关的补丁或扩展点。
- **新目录**：`python-agent-service/config/subagents.registry.yaml`、`python-agent-service/subagents/official/<id>/`（`AGENT.md` + `skills/`）；可选与现有 `skills/` 并存（`extra_skill_package_ids` 迁移桥）。
- **提示词**：`MASTER_AGENT.md` 中与「固定子类型」相关的表述改为「以系统注入的目录为准」。
- **前端**：若展示依赖特定 subagent 名称列表，需改为消费服务端元数据或保持名称兼容。
- **文档**：实现完成后更新 `project_context.md` 中 Agent/SubAgent/Skill 关系说明。
