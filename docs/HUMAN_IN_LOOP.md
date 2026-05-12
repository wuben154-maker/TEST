# Human-in-the-loop（人机协同）说明

本文说明本仓库中 **两类** LangGraph 中断：由策略触发的 **工具审批**（`interrupt_on`），以及由 Agent **显式调用工具** 触发的 **自定义用户输入**（`request_user_input`）。二者都通过 `interrupt` 暂停图执行，经 `POST /analyze/resume` 恢复。

---

## 1. 总览


| 维度         | 类型 A：工具审批（策略 HITL）                                                                  | 类型 B：自定义用户输入（`request_user_input`）                                                                     |
| ---------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| **机制**     | LangChain `HumanInTheLoopMiddleware` + `create_deep_agent(..., interrupt_on={...})` | 工具 `request_user_input` 内部调用 `interrupt(payload)`                                                      |
| **典型用途**   | 危险或敏感工具执行前必须人工批准/拒绝/改参                                                              | 缺参澄清、多选一、短表单、自由文本补充                                                                                    |
| **SSE 标识** | `interruptKind: langchain_hitl_v1`                                                  | `interruptKind: user_input_v1`                                                                         |
| **主要事件类型** | `decision_request`（含 `hitlRequest`）                                                 | `choice` → `decision_request`；`form`/`text` → `parameter_request`                                      |
| **配置入口**   | 环境变量 `AGENT_HITL_INTERRUPT_TOOLS`；registry 子 Agent 可选 `interrupt_on`                | `AGENT_HITL_ENABLED=true` 时子 Agent 常见工具集包含该工具；主 Agent 需 `AGENT_HITL_MAIN_REQUEST_USER_INPUT_TOOL=true`；`request_user_input` 的启停与 LLM `description` 可由 `config/tool_presentation.yaml` 覆盖 |
| **模型侧建议**  | 不要伪造审批结果；等待客户端恢复                                                                    | 不要用本工具代替「工具调用审批」；审批走类型 A                                                                               |


实现参考：`python-agent-service/app/parsers/hitl_interrupt_sse.py`、`app/tools/hitl_tools.py`、`app/config/settings.py`。

---

## 2. 启用前提（两类共用）

1. `**AGENT_HITL_ENABLED=true`**（`python-agent-service/.env`）
  - 关闭时：不注入 `interrupt_on`、不提供 `/analyze/resume`、子 Agent 侧也不挂 HITL 相关工具链（与当前实现一致）。
2. `**AGENT_MODE=deepagent**`
  - Simple 模式无完整 LangGraph 编排，不适用本文中断语义。
3. **可恢复的会话状态（checkpointer）**
  - `session_id` / `thread_id` 与前端项目会话一致，否则无法在同一轮对话上 `resume`。
4. **改配置后重启 Agent 服务**
  - 避免进程内缓存的旧图仍不带 HITL。
5. **阻塞新分析（可选，默认开启）**
  - `AGENT_HITL_BLOCK_ANALYZE_WHEN_PENDING=true` 时，存在未处理 interrupt 再发普通 `/analyze` 会收到错误类事件（如 `hitl-pending`）；应先 `/analyze/resume`。

更细的 **resume JSON、`done.awaitingHuman`、错误码** 见：[Process/history/HITL_RESUME.md](./Process/history/HITL_RESUME.md)。

---

## 3. 类型 A：工具审批（`interrupt_on` / `langchain_hitl_v1`）

### 3.1 是什么

在 **模型已发起某工具调用、尚未真正执行** 时，中间件将执行流打断，把「待审工具调用」以结构化载荷交给前端；人工决策后，通过 `resume` 把 `**decisions`**（批准 / 编辑参数 / 拒绝等）交回 LangGraph，图再继续。

### 3.2 如何配置

- **主 Agent + 默认通用子 Agent**  
  - 设置 `**AGENT_HITL_INTERRUPT_TOOLS`** 为 **逗号分隔的真实工具名**（必须与图中注册的工具名完全一致）。  
  - 示例：`AGENT_HITL_INTERRUPT_TOOLS=web_search,read_file`（按你实际暴露给模型的工具名填写）。
- **Registry 子 Agent（标准 runtime）**  
  - 在 `config/subagents.registry.yaml` 对应条目中配置 `**interrupt_on`**（工具名 → 布尔）。  
  - **Compiled 子图**（如部分 deep-research 编译路径）在 Phase 1 可能 **忽略** registry 的 `interrupt_on`，需单独改造 builder 才能生效。

### 3.3 前端/SSE 上长什么样

- 事件：`decision_request`（或与其它 HITL 事件组合出现）。  
- 字段要点：  
  - `interruptKind: langchain_hitl_v1`  
  - `interruptId`：对应 LangGraph `Interrupt.id`，多中断时需按文档映射到 `resume`。  
  - `hitlRequest`：`HumanInTheLoopMiddleware` 侧 `HITLRequest` 的 JSON 安全副本（含 `action_requests` / `review_configs` 等）。  
  - `decision`：适配器生成的 UI 友好结构（选项、问题文案等）。

流结束前通常还有 `**step`（如 `hitl-waiting`）** 与 `**done.awaitingHuman: true`**。

### 3.4 恢复（resume）时要注意什么

- `POST /analyze/resume` 的 body 中 `**resume**` 需符合 LangGraph `Command(resume=...)` 与 LangChain HITL 约定，常见为带 `**decisions**` 的字典（如 `approve` / `edit` / `reject`）。  
- 具体形状以当前 LangGraph 版本与 `hitlRequest` 为准；示例与多 interrupt 映射见 [HITL_RESUME.md](./Process/history/HITL_RESUME.md)。

---

## 4. 类型 B：自定义用户输入（`request_user_input` / `user_input_v1`）

### 4.1 是什么

模型 **主动调用** 工具 `request_user_input`，传入问题与交互形态；运行时 `interrupt` 挂起，**恢复时传入的值** 作为工具返回值进入后续推理（例如 `{"ok": true, "response": ...}` 中的 `response`）。

### 4.2 三种子形态（`kind`）


| `kind`       | 含义          | 映射到的 SSE（便于复用现有 UI）                                           |
| ------------ | ----------- | ------------------------------------------------------------- |
| `**choice`** | 用户从若干选项中选一个 | `decision_request`，`userInputKind: choice`                    |
| `**form**`   | 多字段表单       | `parameter_request`，`userInputKind: form`                     |
| `**text**`   | 单行/短文本回复    | `parameter_request`，`userInputKind: text`（适配器会生成默认字段 `reply`） |


事件上均带 `**interruptKind: user_input_v1**`、`interruptId`、`requestId`（可与工具入参 `request_id` 对齐）。

### 4.3 如何启用工具

- **子 Agent**：在 `AGENT_HITL_ENABLED=true` 时，常见工具链会包含 `request_user_input`（与 `create_common_tools` / 配置一致，以当前代码为准）。  
- **主 Agent**：需 `**AGENT_HITL_MAIN_REQUEST_USER_INPUT_TOOL=true`** 才会注册该工具。

### 4.4 恢复（resume）时要注意什么

- 与类型 A 相同走 `**POST /analyze/resume**`，`resume` 内容为 LangGraph 期望的 **对该 interrupt 的应答**（常为标量、字符串或结构化对象，取决于 `interrupt` 契约）。  
- 多 pending interrupt 时，按 LangGraph 文档使用 **interrupt id → 值** 的映射形式。  
- 实现上工具返回结构见 `app/tools/hitl_tools.py` 中 `_request_user_input_impl`。

---

## 5. 类型 A 与类型 B 如何选择（给产品与提示词）

- **要拦的是「某一个工具调用能不能执行」**（安全/合规）→ 用 **类型 A**（`interrupt_on` / 环境变量或 registry），不要用 `request_user_input` 冒充审批流。  
- **要收集的是「业务参数、澄清、选项」** → 用 **类型 B**（`request_user_input`），在 prompt 中写清何时调用、字段含义。  
- 系统提示中的简要约定见：`python-agent-service/app/prompts/MASTER_AGENT.md` 与各子 Agent `AGENT.md` 中的 *Human-in-the-loop* 小节。

### 5.1 澄清引导架构（Clarification Gate）

为让主 Agent 和子 Agent **灵活判断何时需要人工输入**（而非在每轮对话固定强制检查），系统采用了三层 prompt-driven 设计：

| 层 | 组件 | 说明 |
|----|------|------|
| **共享指南** | `app/prompts/clarify_gate.md` | 定义四维度歧义分析、`kind` 选择决策树、提问规范、反模式清单。当 `AGENT_HITL_MAIN_REQUEST_USER_INPUT_TOOL=true` 时由 `load_prompt("clarify_gate")` 加载并追加到主 Agent system prompt。 |
| **主 Agent Step 0.5** | `MASTER_AGENT.md` → *Step 0.5: Clarification Gate* | Scope Gate 通过后、Route 之前的快速评估点。引用共享指南并补充主 Agent 特有场景（模糊目标、分析类型歧义、缺少凭证等）。 |
| **子 Agent 域级覆盖** | 各 `subagents/official/<id>/AGENT.md` → *Clarification scenarios* | 领域特定触发场景表（scenario → `kind` 映射）+ 本域反模式。 |

**与 Deep Research `clarify_with_user` 的关系**：Deep Research 保留其 **编程式、必检** 的专用节点（structured output + programmatic `interrupt()`）。上述指南适用于 **所有其他** Agent，采用 **tool-call-driven** 方式——当模型判断需要澄清时调用 `request_user_input`，不需要额外的图节点。

**`FieldSpec` 类型化表单字段**：`kind=form` 的 `fields` 参数已从 `list[dict]` 升级为 `list[FieldSpec]`（Pydantic model），每个字段含 `name`、`label`、`param_type`（text/password/url/number/email）、`required`、`placeholder`。序列化时自动转为 camelCase（`paramType`）以匹配下游 SSE pipeline。

**model_validator 交叉校验**：`RequestUserInputArgs` 增加了 `@model_validator` 确保 `kind=choice` 时 `options` 非空、`kind=form` 时 `fields` 非空，在 LLM tool-call 参数阶段即可捕获结构错误。

---

## 6. Deep-Research 子图中断传播

### 6.1 问题背景

Deep-research 子图 (`open_deep_research_original`) 通过 `clarify_with_user` 节点调用 `interrupt()` 请求用户澄清。该子图被封装在 `RunnableLambda` 中作为 `CompiledSubAgent` 运行在主图的 `task()` 工具内。由于 `RunnableLambda` 不是一个 LangGraph 子图（无独立 checkpointer），子图内部的 `interrupt()` 不会自动传播到主图。

### 6.2 解决方案（compiled adapter 层面传播）

`open_deep_research_compiled.py` 中的 `_run_open_deep_research_subagent()` 在 `astream` 循环中显式检测 `__interrupt__` 事件：

1. **检测**：当 `event_type == "updates"` 且 `event_data` 包含 `__interrupt__` 键时，提取 `Interrupt` 对象。
2. **传播**：调用 `langgraph_interrupt(intr.value)` 将中断信号传播到主图。主图暂停，前端收到 `parameter_request` / `decision_request` SSE 事件。
3. **恢复**：用户通过 `POST /analyze/resume` 提交回复后，主图恢复，`langgraph_interrupt()` 返回用户回复内容。
4. **重跑**：用户回复作为 `HumanMessage` 追加到输入消息列表，deep-research 子图从头重新运行。`clarify_with_user` 节点看到已有用户回复后，跳过追问并直接进入研究阶段。
5. **安全上限**：最多重跑 3 次（`_HITL_MAX_CLARIFY_RERUNS`），防止无限循环。

### 6.3 独立适配器（original adapter）

`open_deep_research_original_adapter.py` 中的 `stream_open_deep_research_original()` 是独立的 SSE 生成器（不经过主图），检测到 `__interrupt__` 后提取 `prompt` 字段作为 `clarification_question`，yield `research_clarification_required` 事件后终止流。

### 6.4 关键代码

| 文件 | 改动 |
|------|------|
| `app/agents/research/open_deep_research_compiled.py` | `_run_open_deep_research_subagent()` — for 循环 + `__interrupt__` 检测 + `langgraph_interrupt()` 传播 + 消息注入重跑 |
| `app/agents/research/open_deep_research_original_adapter.py` | `stream_open_deep_research_original()` — `__interrupt__` 检测 + break |
| `tests/test_research_interrupt_propagation.py` | 4 个测试覆盖检测 + 重跑 + 正常路径 |

---

## 7. 其它：`raw_interrupt_v1`

若 `interrupt` 的 value **既不是** HITL 标准 `HITLRequest` 形字典，**也不是** `user_input_v1` 载荷，适配器会退化为 `**parameter_request`**，`interruptKind: raw_interrupt_v1`，`detail` 中为 JSON 摘要。客户端仍可 `resume` 传回复，但需自行约定含义与校验。

---

## 8. 相关文档与代码


| 资源                      | 路径                                                                                                    |
| ----------------------- | ----------------------------------------------------------------------------------------------------- |
| Resume 契约与 env 表        | [docs/Process/history/HITL_RESUME.md](./Process/history/HITL_RESUME.md)                               |
| SSE 事件与 HITL 字段         | [docs/SSE_EVENT_CATALOG.md](./SSE_EVENT_CATALOG.md)                                                   |
| Interrupt → SSE         | `python-agent-service/app/parsers/hitl_interrupt_sse.py`                                              |
| `request_user_input`    | `python-agent-service/app/tools/hitl_tools.py`；启用/描述覆盖见 `config/tool_presentation.yaml`              |
| 通用工具装配                 | `python-agent-service/app/tools/enhanced_tools.py`（`create_common_tools`）                            |
| 主图 `interrupt_on` 与环境变量 | `python-agent-service/app/config/settings.py`、`app/agents/deep_agent.py`                              |
| 前端状态与恢复调用               | `src/hooks/useStreamingAnalysis.ts`、`useStreamingAnalysisMulti.ts`（`hitlAwaiting`、`submitHitlResume`） |


---

## 9. 修订记录

- **v3**：新增 §5.1 澄清引导架构——`CLARIFY_GATE_GUIDE` 共享指南、`MASTER_AGENT.md` Step 0.5、四个子 Agent 域级覆盖；`FieldSpec` 类型化表单字段；`RequestUserInputArgs` model_validator 交叉校验。
- **v2**：新增 §6 Deep-Research 子图中断传播（compiled adapter 检测 `__interrupt__` → `langgraph_interrupt()` 传播 → 用户回复重跑子图；original adapter 检测后 yield SSE + break）。
- **v1**：与当前仓库 HITL 实现及 `langgraph` 1.0.8 语义对齐；若升级 LangGraph / LangChain，请以官方 `Command(resume=...)` 与 HITL 中间件文档为准并回查 `hitl_interrupt_sse.py`。

