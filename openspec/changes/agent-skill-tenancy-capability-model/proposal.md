## Why

SecManus 当前将 **Skill 与子 Agent 类型强绑定**（每个技能目录对应一个 `task(subagent_type=…)`），主 Agent 的工具面与循环形态也相对固定，扩展新能力需要改多处代码且难以表达 **多租户下的技能来源与互斥**。需要一份统一的需求与设计方案：**技能分层可见（官方 / 租户私有）**、**声明式冲突消解**、**能力与运行形态解耦**（Skill / 工具 / 子 Agent / UI 事件），以便后续实现可分阶段落地。

## What Changes

- 引入 **技能归属与可见性模型**：平台官方 Skill 对所有租户可见；租户上传或从技能市场安装到租户的 Skill **仅该租户可见**。
- 引入 **冲突策略**：多个 Skill 若声明为同一业务能力（见设计中的 `capability_id`），则互斥；**默认规则为后加入者对该冲突组失效（不进入有效注册表）**，并与「官方 vs 租户」优先级一并可配置（见设计）。
- 引入 **统一 Capability / Skill / Subagent 注册视图**（概念层）：Skill 索引与加载受 **租户有效集合 + 开关** 约束；子 Agent 类型可动态扩展，但 **主 Agent 所见的类型列表与路由说明** 与注册表 **同源生成**，避免漂移。
- 明确 **主 Agent 执行语义**：推理 → 工具调用或委派子 Agent → 观测结果 → 终止判定循环，并配套 **护栏**（步数/预算、显式完成信号等）。
- 明确 **流式 UI 事件模型**：主从运行共享 **阶段类型**（如推理、工具、子运行、技能加载、完成、错误）与 **父子关联字段**，子 Agent 内过程可对齐展示。
- **BREAKING**（潜在）：若未来实现租户级 Skill 存储与解析，现有「仅本地 `skills/` 目录」的加载路径需演进为「合并官方 + 租户源」；具体破坏面在实现阶段在 `tasks.md` 中逐项列出。

## Capabilities

### New Capabilities

- `skill-tenancy`: 官方与租户级 Skill 的归属、可见性、安装来源（上传 / 市场），以及注入 Agent 上下文前的 **有效技能集合** 计算输入。
- `skill-conflict-resolution`: `capability_id`（或等价键）定义、冲突检测、默认「后加入失效」规则、与官方/租户优先级及运营可观测性（禁用原因）。
- `agent-orchestration`: 主 Agent 循环语义、Capability Registry 与子 Agent 动态注册及路由信号、工具策略分层（概念）、统一流式事件信封供前端嵌套展示。

### Modified Capabilities

- （无）当前 `openspec/specs/` 下尚无既有能力规范。

## Impact

- **后端**：`python-agent-service` 的 Skill 发现/加载、（未来）租户存储与 API、`create_deep_agent` / SubAgent 规格构建、工具装配与流式适配。
- **前端**：`src/hooks` 与 `reasoning/*` 对 SSE/事件类型的解析与展示，若引入嵌套时间轴需协议对齐。
- **数据与平台**：Supabase（或等价）中租户、技能包、安装记录、冲突状态等表与 RLS（实现阶段细化）。
- **文档**：`project_context.md` 需在实现落地后更新架构描述。
