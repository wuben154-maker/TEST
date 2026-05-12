# 工具与注册表说明（Python Agent Service）

本文描述后端 `**python-agent-service**` 中：工具在 **YAML** 中的声明方式、**SSE/UI** 元数据、以及 **LangChain `StructuredTool`** 如何被装配到主 Agent 与子 Agent。实现以仓库当前代码为准。

---

## 1. 配置文件位置


| 资源                 | 路径                                                     |
| ------------------ | ------------------------------------------------------ |
| 工具展示与通用装配声明        | `python-agent-service/config/tool_presentation.yaml`   |
| 环境变量说明（含配置引用）      | `python-agent-service/config/env.md`                   |
| 运行时加载与热重载          | `python-agent-service/app/sse/tool_presentation.py`    |
| 通用工具工厂             | `python-agent-service/app/tools/enhanced_tools.py`     |
| 研究类工具实现            | `python-agent-service/app/tools/research_tools.py`     |
| HITL 工具            | `python-agent-service/app/tools/hitl_tools.py`         |
| 子 Agent 工具 profile | `python-agent-service/app/agents/subagent_registry.py` |
| 主图装配入口             | `python-agent-service/app/agents/deep_agent.py`        |


---

## 2. `tool_presentation.yaml` 的两种形态

### 2.1 推荐：分层（Tiered）

顶层包含以下任一键时，视为 **分层模式**（此时若仍存在旧的顶层 `tools:`，**不会**再作为装配来源）：

- `**system_tools`**：DeepAgents / 运行时内置工具名，用于 **SSE**（`presentation`、`emit_output` 等）。**不由** `create_common_tools()` 挂载。
- `**common_tools`**：**主 Agent 与默认 profile 子 Agent** 的 **StructuredTool 装配清单**（见下文第 3 节）。
- `**subagent_tools`**：主要用于 **SSE / 产品 UI** 上对「技能向」工具名的说明；**默认注册表子 Agent 不会**通过 `create_common_tools()` 自动挂载这些 Python 工具（能力由 bundle `skills` 与提示词承担）。

### 2.2 兼容：扁平 `tools:`

仅存在 `**tools:`** 映射、且 **没有**上述分层键时，为 **Legacy** 模式：装配逻辑仍按代码中固定顺序（安全工具 → 研究三件套 → 可选 HITL），主要用于测试与旧环境。

---

## 3. 每个工具条目字段（各节通用）


| 字段                 | 含义                                                                                                |
| ------------------ | ------------------------------------------------------------------------------------------------- |
| `**presentation`** | `task` | `action` | `state` | `parameter`（必填）。用于 SSE 事件上的 `toolPresentation` 等。                   |
| `**emit_output**`  | 默认 `true`。为 `false` 时通常不在 SSE 中下发该工具的输出正文（如 `read_file`）。                                         |
| `**enabled**`      | 默认 `true`。在 **分层模式下**，`common_tools` 里 `**enabled: true`** 且实现存在时，才会被 `create_common_tools()` 挂载。 |
| `**description**`  | 可选。若对应工厂从注册表读取，会覆盖传给模型的 **StructuredTool.description**（热重载后随 YAML 更新）。                            |


---

## 4. `create_common_tools()`：谁会被挂到主/子 Agent？

**入口**：`app/tools/enhanced_tools.py` → `create_common_tools(include_hitl=..., only_names=...)`

### 4.1 分层 YAML

按 `**common_tools` 在文件中的声明顺序** 遍历；对每个名字：

1. 若传入 `**only_names`**，且当前名不在集合内 → 跳过（用于 `deep-research` 等 profile，仅保留研究子集）。
2. 若注册表无规则或 `**enabled` 不为 true** → 跳过。
3. 若名为 `**request_user_input`**：仅当运行时 `**include_hitl` 为 true** 时，通过 `hitl_tools.create_hitl_tools()` 挂载（YAML 仍控制是否出现在清单与描述文案）。
4. 否则调用 `**app.tools.common_tool_registry.try_mount_common_tool()`**：安全四件套与 `search_history` 由 `**COMMON_TOOL_MOUNTERS**` 挂载；研究三件套委托 `research_tools.try_append_research_tool(..., assume_yaml_enabled=True)`。元数据见 `**ToolSpec`**（`app/tools/tool_spec.py`）。
5. 若 `try_mount_common_tool` 返回 false：打日志 `**common_tools_no_impl`**，不挂载。

**扩展清单时：** 在 `app/sse/tool_presentation.py` 中更新 `COMMON_SECURITY_TOOL_ORDER` 或 `RESEARCH_TOOL_ORDER`，在 `app/tools/common_tool_registry.py` 中为安全类/`search_history` 增加对应 mounter（研究类仅更新 `RESEARCH_TOOL_ORDER`），并补充/更新测试。

**主 Agent**（`deep_agent.py`）当前调用：

`create_common_tools(include_hitl=<按设置与主 Agent HITL 开关>)`

不再单独拼接 `create_research_tools()`；研究三件套只要在 `common_tools` 里启用，即由上述逻辑统一挂载。

### 4.2 Legacy `tools:`

- 固定顺序挂载 **安全四件套**（仍尊重各工具在 YAML 中的 `enabled` / `description`）。
- 再按 `**RESEARCH_TOOL_ORDER`** 尝试挂载研究三件套（尊重 YAML `enabled`）。
- 最后在 `**only_names is None**` 且 `**include_hitl**` 与 YAML 允许时，在列表末尾追加 HITL。

### 4.3 `create_research_tools()`

`app/tools/research_tools.py` 中的 `**create_research_tools()**` 现为薄封装：

等同于 `**create_common_tools(only_names=frozenset(RESEARCH_TOOL_ORDER))**`，供测试或显式「只要研究工具」的场景使用。

**常量**：`RESEARCH_TOOL_ORDER` 定义在 `app/sse/tool_presentation.py`。

---

## 5. 子 Agent 工具 Profile（注册表）

`app/agents/subagent_registry.py` 中 `**build_tool_profiles()`** 当前约定：


| Profile                                        | 工具列表                                                                                                  |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `default`、`email-security`、`web-security` 等标准项 | `create_common_tools()` 全量（与主 Agent 同一套 `common_tools` 声明）                                            |
| `deep-research`（标准 agent 模式）                   | `create_common_tools(only_names=RESEARCH_TOOL_ORDER)`，仅研究三件套，且顺序与 YAML 中 `common_tools` 里出现的顺序一致（过滤后） |


专用子 Agent 行为仍以 `**config/subagents.registry.yaml**` 与 bundle 内 `**skills` / 提示词** 为主；注册表不额外挂载邮件/Web 专用 Python 工具行（与历史设计一致）。

---

## 6. 系统内置工具（`system_tools`）

下列名称在 YAML 的 `**system_tools`** 中主要用于 **前端/SSE 展示分类**，由 DeepAgents 图在运行时提供，**不**经过 `create_common_tools()`：

例如：`write_todos`、`task`、`read_file`、`grep`、`glob`、`ls`、`analyze_file_structure`、`edit_file`、`write_file`、`execute`，以及研究流程相关状态类展示名（如 `think_tool`、`ConductResearch`、`ResearchComplete`）等——**以当前 `tool_presentation.yaml` 为准**。

---

## 7. HITL：`request_user_input`

- **实现**：`app/tools/hitl_tools.py`（`interrupt` 挂起，恢复后把用户输入交回模型）。
- **描述**：可被 `tool_presentation.yaml` 中 `request_user_input` 的 `**description`** 覆盖。
- **是否出现在工具列表**：除 YAML `enabled` 外，还受 `**include_hitl`**（主/子 Agent 构建处传入）与全局 HITL 相关设置约束；详见 `docs/HUMAN_IN_LOOP.md`（若存在）。

---

## 8. 可选工厂：`create_email_tools` / `create_web_tools`

位于 `**enhanced_tools.py**`，按 `EMAIL_SECURITY_TOOL_ORDER` / `WEB_SECURITY_TOOL_ORDER` 与 YAML 中的 `enabled` / `description` 装配。**默认注册表子 Agent 不调用**；可用于测试或按需组合。

---

## 9. 运行时注册表与热重载

- `**app/sse/tool_presentation.py`** 按 `**tool_presentation.yaml` 文件 mtime** 缓存 `**ToolRegistrySnapshot`**（规则表 + `**common_tools` 键顺序**）。
- `**get_tool_rule(name)`**、`**resolve_tool_presentation**`、`**should_emit_tool_output**`、`**is_tiered_tool_registry()**`、`**common_tools_key_order()**` 均基于该快照。
- YAML 缺失或解析失败时，使用代码内 **默认规则表**（非分层、无 `common_tools` 顺序），装配走 **Legacy** 分支。

---

## 10. 与其它文档的关系

- **SSE 事件与工具展示字段**：`docs/SSE_EVENT_CATALOG.md`
- **子 Agent 与技能架构**：`docs/SUBAGENT_AND_SKILL_ARCHITECTURE.md`
- **人在回路（HITL）**：`docs/HUMAN_IN_LOOP.md`
- **整体架构**：`docs/ARCHITECTURE.md`

---

## 11. 修改清单后的自检建议

1. 修改 `**common_tools`** 顺序或 `enabled` 后，确认主 Agent 与子 Agent（默认 profile）工具列表是否符合预期。
2. `**deep-research**` profile 仅保留研究名：确认三件套在 YAML 中仍为 `**enabled: true**`（若全关则该 profile 可能无工具）。
3. 若新增 `common_tools` 名称，必须在 `**enhanced_tools` / `research_tools` / `hitl_tools**` 之一实现挂载逻辑，否则会触发 `**common_tools_no_impl**` 警告且无 StructuredTool。

