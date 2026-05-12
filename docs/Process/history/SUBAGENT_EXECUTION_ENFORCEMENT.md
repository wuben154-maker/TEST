# SubAgent 强制执行设计文档

> **背景**：本文档分析当前主智能体（`DeepAgentWithIntent`）将安全/研究任务委派给 Sub-Agent 的机制，
> 梳理其中存在的"软性约束"风险，并提出四个由轻到重的加固方案，供后续优化参考。

---

## 一、现状与问题

### 1.1 执行路径回顾

`analyze_stream()` 中，SECURITY/RESEARCH 类型的任务执行流程如下：

```
TaskPlanner.plan_tasks()
    → build_task_instruction()
        → HumanMessage(content=task_instruction)
            → adapt_astream_to_sse(self.agent, initial_state, ...)
                → 主 Agent LLM 推理
                    → 调用 task(subagent_type=..., description=...) 工具
                        → SubAgentMiddleware → Sub-Agent runnable.invoke()
```

关键节点在 `deep_agent.py` 第 657–702 行：

```python
task_instruction = build_task_instruction(
    user_input=text,
    intent_result=intent_result,
    task_plan=exec_plan,
    context_results=context_results_str,
    language=effective_input_language,
)
initial_state = {
    "messages": [HumanMessage(content=task_instruction)],
    ...
}
async for event in adapt_astream_to_sse(self.agent, initial_state, config, ...):
    yield event
```

`task_instruction` 的内容格式（来自 `task_instruction_builder.py`）：

```
[Intent Summary]
task_category: security
Analysis goals: detect phishing, extract IOCs

[Planned Tasks - Execute in order]
1. subagent_type=email-security, description="{taskObjective: ..., files: [...]}"

[User Input]
请分析这封邮件...

[Instruction]
Call the task tool for each planned task above, in order.
Use the exact subagent_type and description. Do not skip tasks or add preamble.
After all tasks complete, provide a concise summary.
```

### 1.2 核心问题

**当前系统对"必须走 Sub-Agent"的保证完全依赖 Prompt，没有任何代码层面的硬性阻止。**

主 Agent 同时持有：
- `task()` 工具（委派给 Sub-Agent）
- `common_tools`（`extract_iocs`、`decode_base64`、`lookup_threat_intel`、`web_search`、`read_file` 等通用工具）

在 LLM 推理的自由度下，主 Agent 理论上可以忽略 `[Instruction]` 段的要求，直接使用 `common_tools` 自己执行分析，而不调用 `task()`。

---

## 二、现有约束机制

### 2.1 三重 Prompt 软性约束

| 层级 | 位置 | 内容 |
|------|------|------|
| 系统提示（静态） | `MASTER_AGENT.md` `<task-execution-mode>` | "Call the task tool for each planned task in the order listed" |
| 运行时注入（动态） | `SubAgentMiddleware.wrap_model_call()` | 每次 LLM 调用前追加 `TASK_SYSTEM_PROMPT` |
| 用户消息（请求级） | `build_task_instruction()` 生成的 `HumanMessage` | 在消息正文中直接写明 `subagent_type` 和 `[Instruction]` |

**三重约束叠加**对主流高智能模型（Claude Sonnet/Opus、GPT-4o）效果良好，但属于软性约束，不能排除 LLM 自主"优化"执行路径的可能。

### 2.2 工具集隔离（唯一的隐性硬性约束）

主 Agent 和 Sub-Agent 的工具集是分开注册的：

```
主 Agent 工具：
  extract_iocs, decode_base64, lookup_threat_intel
  web_search, scrape_url
  read_file, write_file, grep
  task()  ← 唯一的 Sub-Agent 调用入口

Sub-Agent (email-security) 专属工具：
  email_header_parser, spf_dkim_dmarc_check
  attachment_analyzer, phishing_detector, ...

Sub-Agent (binary-analysis) 专属工具：
  pe_analyzer, sandbox_detonate, yara_scan, ...
```

**结论**：即使主 Agent 绕过 `task()` 自己执行，也只能使用通用工具，无法调用专用安全分析工具。深度分析能力（邮件头解析、PE 文件分析、沙箱等）**物理上只存在于 Sub-Agent**，这是当前系统唯一的事实强制。

---

## 三、加固方案

### 方案一：Prompt 加固

**改动位置**：`python-agent-service/app/prompts/MASTER_AGENT.md`

在 `<task-execution-mode>` 段追加更强的约束语言：

```markdown
<task-execution-mode>
## Task Execution Mode

When the user message contains a **[Planned Tasks - Execute in order]** section:

1. **Call the task tool** for each planned task in the order listed
2. **Use the exact subagent_type and description** from the plan
3. **Do not skip tasks** - execute every task in the list
4. **Do not add preamble** - start calling the task tool immediately
5. **After all tasks complete**, provide a brief summary

**CRITICAL CONSTRAINT**:
- You MUST NOT analyze security/research content directly using your own tools.
- Your ONLY allowed action for tasks in the [Planned Tasks] section is calling `task()`.
- Bypassing `task()` and performing direct analysis is a protocol violation.
- If a subagent_type is not available, report the error; do not substitute with direct analysis.
</task-execution-mode>
```

**优点**：改动极小，零代码改动，立即生效。  
**缺点**：仍是软性约束，低智能模型或异常输入下可能失效。  
**适用场景**：快速加固，作为其他方案的补充。

---

### 方案二：主 Agent 工具清单收窄（推荐）

**改动位置**：`python-agent-service/app/agents/deep_agent.py` → `_build_official_agent()`

**核心思路**：主 Agent 只保留"编排工具"，移除所有安全分析工具。安全分析工具只注册给 Sub-Agent。

```python
# deep_agent.py - _build_official_agent()
def _build_official_agent(self):
    from app._vendor.deepagents import create_deep_agent

    # 仅保留编排类工具（文件管理、任务追踪），移除安全分析工具
    orchestration_tools = create_orchestration_tools()  # 只含 read/write/grep/todos

    # 安全分析工具仅在 Sub-Agent 层注册（create_security_subagents 内部管理）
    subagents = create_security_subagents(model=self.model)

    return create_deep_agent(
        model=self.model,
        tools=orchestration_tools,   # ← 主 Agent 不持有安全分析工具
        subagents=subagents,
        ...
    )
```

**工具分层示意**：

```
主 Agent（编排层）
├── read_file / write_file / grep      ← 文件 I/O
├── write_todos / read_todos           ← 任务追踪
├── web_search / scrape_url            ← 基础信息获取（可选移除）
└── task(subagent_type, description)   ← 唯一的 Sub-Agent 调用入口

Sub-Agent（执行层）
├── email-security:   email_header_parser, spf_dkim_check, phishing_detector, ...
├── binary-analysis:  pe_analyzer, sandbox_detonate, yara_scan, ...
├── web-security:     http_log_analyzer, xss_detector, sqli_scanner, ...
├── soc-alert:        siem_query, alert_correlator, ...
├── vuln-scan:        cve_lookup, cvss_scorer, ...
├── general-security: extract_iocs, decode_base64, lookup_threat_intel, ...
└── deep-research:    research_tools (tavily_search, arxiv, ...)
```

**优点**：物理隔离，主 Agent 即使"想自己干"也没有能力；架构更清晰，职责分离更明确。  
**缺点**：需要将 `common_tools` 拆分为"编排工具"和"执行工具"两组，改动量中等。  
**适用场景**：推荐作为长期架构标准。

---

### 方案三：可观测性守卫（SSE 验证层）

**改动位置**：`python-agent-service/app/parsers/deepagents_stream_adapter.py`

**核心思路**：在 SSE 事件流中追踪是否有 `task()` 工具调用，若 SECURITY/RESEARCH 任务执行完却没有触发任何 Sub-Agent，则发出警告事件。

```python
# deepagents_stream_adapter.py
async def adapt_astream_to_sse(agent, initial_state, config, language="en"):
    task_tool_called = False
    task_category = initial_state.get("task_category", "")

    async for event in agent.astream(initial_state, config, stream_mode="updates"):
        # 检测 task() 工具调用
        for node_name, node_output in event.items():
            messages = node_output.get("messages", [])
            for msg in messages:
                if hasattr(msg, "tool_calls"):
                    for tc in msg.tool_calls:
                        if tc.get("name") == "task":
                            task_tool_called = True
        yield _convert_to_sse(event)

    # 执行后校验
    if task_category in ("security", "research") and not task_tool_called:
        yield {
            "type": "warning",
            "id": "subagent-bypass-detected",
            "internal": True,
            "message": (
                f"[Guard] task_category={task_category} but no task() tool call detected. "
                "Main Agent may have executed directly without Sub-Agent delegation."
            ),
        }
```

**优点**：零侵入性，不改变执行逻辑；提供可观测性，便于监控和告警；可扩展为自动重试。  
**缺点**：不阻止执行，只能事后检测；需要解析 LangGraph stream 事件结构。  
**适用场景**：作为生产环境监控层，与其他方案配合使用。

---

### 方案四：Python 层强制路由（最强）

**改动位置**：`python-agent-service/app/agents/deep_agent.py` → `analyze_stream()`

**核心思路**：完全跳过主 Agent 的 LLM 推理，在 Python 代码层直接按任务计划调用对应 Sub-Agent 的 runnable，主 Agent 仅负责汇总结果。

```python
# analyze_stream() 中替换第 657-702 行逻辑

async def _execute_plan_with_forced_subagents(
    self,
    exec_tasks: list[PlannedTask],
    context_results_str: str | None,
    text: str,
    intent_result: IntentResult,
    ui_language: str,
) -> AsyncGenerator[dict, None]:
    """
    强制路由：每个任务直接调用对应 Sub-Agent runnable，
    不经过主 Agent LLM 推理，100% 保证走 Sub-Agent。
    """
    task_results = []

    for task in exec_tasks:
        subagent_name = _get_subagent_type(task)

        # 直接获取 sub-agent runnable（从 SubAgentMiddleware 注册表中取）
        subagent_runnable = self._get_subagent_runnable(subagent_name)
        if subagent_runnable is None:
            yield {
                "type": "step",
                "id": f"task-{task.id}-error",
                "label": f"Sub-Agent {subagent_name} not found",
                "status": "error",
            }
            continue

        yield {"type": "task_start", "id": task.id, "task": task.to_dict()}

        # 构造 Sub-Agent 输入 state
        payload = json.dumps(task.context, ensure_ascii=False)
        subagent_state = {
            "messages": [HumanMessage(content=payload)],
            "files": task.context.get("files", {}),
        }

        # 直接调用 Sub-Agent
        result = await subagent_runnable.ainvoke(subagent_state)
        final_msg = result["messages"][-1].content if result.get("messages") else ""

        task_results.append({"task": task, "result": final_msg})
        yield {"type": "reasoning", "content": final_msg, "taskId": task.id}
        yield {"type": "task_complete", "id": task.id}

    # 用主 Agent LLM 汇总所有结果（主 Agent 只做 synthesis，不做分析）
    summary = await self._synthesize_results(task_results, intent_result, ui_language)
    yield {"type": "conclusion", "id": "conclusion", "content": summary}


async def _synthesize_results(
    self,
    task_results: list[dict],
    intent_result: IntentResult,
    language: str,
) -> str:
    """用主 Agent LLM 将各 Sub-Agent 结果汇总为最终报告。"""
    synthesis_prompt = _build_synthesis_prompt(task_results, intent_result, language)
    response = await self.model.ainvoke([HumanMessage(content=synthesis_prompt)])
    return response.content
```

**优点**：100% 保证每个任务走 Sub-Agent；执行路径完全可预测；便于单元测试。  
**缺点**：
- 失去主 Agent 的"自适应编排"能力（如动态决定是否合并任务、跳过已完成步骤）
- 需要暴露 Sub-Agent runnable 的访问接口（当前 `SubAgentMiddleware` 不对外提供）
- 无法利用 LangGraph 的状态持久化和多轮对话能力

**适用场景**：对执行路径确定性有极高要求的场景（如合规审计、自动化测试流水线）。

---

## 四、方案对比矩阵

| 方案 | 强制程度 | 改动量 | 风险 | 是否影响主 Agent 自适应能力 | 推荐优先级 |
|------|----------|--------|------|---------------------------|-----------|
| 方案一：Prompt 加固 | 软性（LLM依赖） | 极小（仅改 .md） | 低 | 否 | 立即可做，作为基础保障 |
| **方案二：工具清单收窄** | **半强制（物理隔离）** | **中（拆分 tools）** | **低** | **否** | **推荐，长期架构标准** |
| 方案三：可观测性守卫 | 检测（事后） | 小（改 adapter） | 低 | 否 | 推荐，与方案二配套使用 |
| 方案四：Python 强制路由 | 100% 强制 | 大（重构执行层） | 中 | 是（失去自适应） | 仅特殊场景使用 |

---

## 五、推荐实施路径

### Phase 1（立即）：Prompt 加固
- 修改 `MASTER_AGENT.md`，在 `<task-execution-mode>` 中增加 `CRITICAL CONSTRAINT` 段
- 成本：10 分钟，零风险

### Phase 2（短期）：工具清单收窄
- 将 `create_common_tools()` 拆分为：
  - `create_orchestration_tools()` — 主 Agent 专用（文件 I/O、任务追踪）
  - `create_security_tools()` — Sub-Agent 专用（安全分析）
- 修改 `_build_official_agent()` 中的 `tools=orchestration_tools`
- 修改 `create_security_subagents()` 中每个 Sub-Agent 使用 `create_security_tools()`
- 预计工作量：1–2 天

### Phase 3（中期）：可观测性守卫
- 在 `deepagents_stream_adapter.py` 中追加 Sub-Agent 调用检测逻辑
- 将 `subagent-bypass-detected` 事件接入监控/告警系统
- 预计工作量：半天

### Phase 4（按需）：Python 强制路由
- 仅在合规审计或自动化测试场景下启用
- 可作为 `analyze_stream()` 的可选执行模式（通过 `force_subagent=True` 参数控制）

---

## 六、相关文件索引

| 文件 | 关键内容 |
|------|---------|
| `python-agent-service/app/agents/deep_agent.py` | `analyze_stream()` 第 587–702 行：任务执行主逻辑 |
| `python-agent-service/app/middleware/task_instruction_builder.py` | `build_task_instruction()`：构造发给主 Agent 的 HumanMessage |
| `python-agent-service/app/prompts/MASTER_AGENT.md` | `<task-execution-mode>` 第 117–128 行：Prompt 约束 |
| `python-agent-service/app/_vendor/deepagents/middleware/subagents.py` | `task()` 工具定义、`SubAgentMiddleware`、`TASK_SYSTEM_PROMPT` |
| `python-agent-service/app/agents/official_subagents.py` | `create_security_subagents()`：Sub-Agent 注册 |
| `python-agent-service/app/tools/enhanced_tools.py` | `create_common_tools()`：当前工具清单（方案二改动点） |
| `python-agent-service/app/parsers/deepagents_stream_adapter.py` | `adapt_astream_to_sse()`：方案三改动点 |
