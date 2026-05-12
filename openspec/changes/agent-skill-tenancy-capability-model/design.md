## Context

- **当前状态**：`official_subagents.py` 按文件系统发现的 Skill 元数据 **一对一** 生成 SubAgent 规格；`get_tools_for_agent(agent_name)` 用分支为各子类型装配工具；主 Agent 持有通用 + 研究工具。Skill 通过 `SkillsMiddleware` 与共享 `skills` 源挂载，与「租户」「冲突」「动态注册表」尚无产品级模型。
- **动机**：对齐 OpenClaw 类产品的 **技能可发现、可治理、可扩展** 思路，同时保留 SecManus **安全分析场景下的工具隔离与委派** 需求。
- **约束**：实现将分阶段；本设计区分 **规范层**（必须先一致）与 **实现顺序**（见 `tasks.md`）。

## Goals / Non-Goals

**Goals:**

- 定义 **官方 Skill**（全租户可见）与 **租户 Skill**（仅本租户可见，含上传与市场安装）的归属与可见性规则。
- 定义 **冲突键**（`capability_id`）及 **默认冲突策略**：同键多包时 **后加入者失效**；并定义与 **官方 vs 租户** 同键时的 **可配置优先级**。
- 定义 **Capability Registry** 聚合视图：Skill 元数据、（可选）Subagent 运行形态、工具配置引用、路由提示 **同源** 生成主 Agent 可见列表与 `task` 工具描述素材。
- 定义 **主 Agent 循环** 与 **护栏**（终止判定、步数/预算、可选 HITL）。
- 定义 **流式事件信封**（父子关联、统一阶段类型），使子 Agent 内过程可与主线程 **同构展示**。

**Non-Goals:**

- 本变更文档 **不** 规定具体数据库表结构、API 路径或 LangGraph 节点名（留待实现任务）。
- **不** 要求一次性移除现有「每 Skill 一 SubAgent」实现；迁移可为渐进式。
- **不** 规定技能市场商业模式与计费（仅「安装到租户」行为边界）。

## Decisions

### D1. 冲突键：`capability_id`（声明式）

- **内容**：每个 Skill 包在 manifest（如 SKILL.md frontmatter 或 sidecar `skill.yaml`）中 **必须/应当** 声明 `capability_id`（稳定字符串，如 `secmanus.ioc_extract`）。
- **理由**：纯语义或向量判断 **不可审计**；声明式键与运营、测试、UI 解释一致。
- **备选**：仅用 skill `name` 作为键 —— 被拒：名称可读性与稳定性不如 capability 命名空间。

### D2. 默认冲突策略：同租户有效集合内「后加入失效」

- **内容**：对同一 `capability_id`，在同一租户的 **候选安装列表**（官方全局包 + 租户私有包，经可见性过滤后）中，按 **确定性排序键**（见 D3）排序后 **仅保留第一个**；其余标记为 `conflict_suppressed`，**不进入有效 Registry**，并对管理员 **可查询原因**。
- **用户原话「后加入失效」** 落实为：在 **同级优先级** 下，**时间更晚** 的记录失效；若引入 **优先级层级**（D4），则 **先按层级，再按时间**。
- **备选**：自动合并或让用户每次对话选择 —— 延后到 Phase 2，避免首版 UI 过重。

### D3. 排序键（确定性）

- **建议**：`(precedence_tier, install_seq, package_id)` 其中 `install_seq` 为单调递增安装序号或 `installed_at` 时间戳（租户内）；`package_id` 为 tie-break。
- **理由**：保证多端、重放、缓存一致。

### D4. 官方 vs 租户同 `capability_id` 的优先级（可配置）

- **内容**：产品级配置 `skill_conflict.precedence`：
  - `official_wins`：官方包始终优先于租户同键包（租户后装 **不覆盖** 官方；租户包标记冲突失效）。
  - `tenant_overrides_official`：租户包在 **同 tier 内** 按时间覆盖可见的官方包（适用于强定制部署）。
  - 默认推荐 **`official_wins`**，与「平台统一安全分析口径」一致；需在部署文档中写明。
- **理由**：「仅后加入失效」在跨来源时不足以回答「谁赢」。

### D5. Skill 作用域：独立于「主 / 子 Agent」

- **内容**：Skill 条目带 `scope`：`global_index`（主与子均可见索引）、`main_only`、`subagent_only`、或绑定 `runtime_profile_id`。**加载**仍遵循 **渐进式**：索引轻量注入，全文 SKILL.md **按需读取**（可观测为一步）。
- **理由**：解耦「文档/workflow」与「执行隔离单元」。

### D6. Subagent：少枚举「业务域」，多枚举「运行形态」

- **内容**：长期目标为少量稳定类型，如 `general-purpose`（上下文隔离）、`compiled-graph-*`（如 deep-research）。领域差异主要靠 **Skill + 工具策略**，而非 N 个 `task` 类型名。
- **理由**：降低扩展成本；与 DeepAgents 默认模式一致。
- **迁移**：现有 per-skill SubAgent 可逐步收束到 `general-purpose` + 指令中指定 SKILL 路径。

### D7. 主循环与终止

- **内容**：规范层定义 **Observe–Act** 循环；终止须至少满足其一：**显式完成工具/状态**、**待办清空**、**用户确认（若策略要求）**、或 **达到步数/费用上限**（硬护栏）。
- **理由**：避免仅依赖模型主观「我觉得完了」。

### D8. 流式事件信封（概念）

- **字段（规范层）**：`run_id`、`parent_run_id`、`depth`、`phase`（枚举：`reasoning` | `tool_call` | `subagent_start` | `subagent_event` | `skill_load` | `done` | `error` 等）、`payload`（工具名摘要、子类型 id、文本增量等）、`tenant_id` / `session_id`（实现时填入）。
- **理由**：前端单轴嵌套渲染；编译子图可通过 **适配层** 映射到相同 `phase`。

## Risks / Trade-offs

- **[Risk] `capability_id` 声明缺失或随意** → **Mitigation**：发现阶段打 warning；可选拒绝注册；文档模板与 linter。
- **[Risk] 租户期望「覆盖官方」但与默认 `official_wins` 不符** → **Mitigation**：控制台明示策略；部署默认写清。
- **[Risk] 动态 Subagent 列表与模型幻觉** → **Mitigation**：`task` schema 与系统提示 **同源生成**；路由 hints + triggers；可选轻量候选缩小。
- **[Risk] 编译子图与 `task()` 事件形状不一致** → **Mitigation**：适配器统一为信封（已在 vendor 补丁方向有先例）。
- **[Trade-off] 少 SubAgent 类型** 可能略增主 Agent 提示长度（须在委派指令中写清 SKILL）→ 用 **紧凑索引 + 按需读文件** 抵消。

## Migration Plan

1. **Phase 0**：规范与事件信封对齐（无行为变更或仅日志）。
2. **Phase 1**：Registry 纯本地合并（官方目录 + 可选本地 override 文件）实现冲突与排序 **逻辑验证**。
3. **Phase 2**：持久化租户 Skill + RLS + API；前端管理冲突与禁用原因。
4. **Phase 3**：收束 SubAgent 类型与工具策略层。
5. **Rollback**：关闭租户源与冲突解析标志，回退至当前文件系统发现（实现任务中定义 feature flag）。

## Open Questions

- 技能市场 **签名与供应链**（哈希、发布者验证）是否纳入首版？
- `capability_id` **命名空间** 是否由平台注册表分配，还是允许租户私有前缀？
- 冲突失效的 Skill 是否仍允许 **显式 @ 引用**（调试用途）？
