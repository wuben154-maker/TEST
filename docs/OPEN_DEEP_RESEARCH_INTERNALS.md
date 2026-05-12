# Open Deep Research — Runtime Internals

This document explains the runtime architecture of the **Open Deep Research** subsystem,
including the three-layer LangGraph structure, the supervisor ↔ supervisor\_tools ReAct
loop, SSE signal flow, and how the compiled adapter bridges LangGraph events to the
SecManus frontend.

Source files (all under `python-agent-service/app/agents/research/`):

| File | Role |
|------|------|
| `open_deep_research_original/deep_researcher.py` | Graph definition: nodes, edges, subgraphs |
| `open_deep_research_original/configuration.py` | Runtime parameters (iterations, concurrency, models) |
| `open_deep_research_compiled.py` | Compiled adapter: `astream` → SSE event extraction |
| `open_deep_research_original_adapter.py` | Legacy adapter (`updates`-only, no phase milestones) |

---

## 1. Three-Layer Graph Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Main Graph  (deep_researcher)                                  │
│                                                                 │
│  START ──► clarify_with_user ──► write_research_brief           │
│                                        │                        │
│                                        ▼                        │
│               ┌────────────────────────────────────────┐        │
│               │  research_supervisor (supervisor_subgraph)│      │
│               │                                          │      │
│               │  START ──► supervisor ◄──┐               │      │
│               │               │         │               │      │
│               │               ▼         │               │      │
│               │       supervisor_tools ─┘               │      │
│               │               │                         │      │
│               │          (on exit)                       │      │
│               │               ▼                         │      │
│               │              END                        │      │
│               └────────────────────────────────────────┘        │
│                                        │                        │
│                                        ▼                        │
│                         final_report_generation ──► END         │
└─────────────────────────────────────────────────────────────────┘

           supervisor_tools 内部调用 researcher_subgraph (ainvoke):
           ┌────────────────────────────────────────────┐
           │  Researcher Subgraph                       │
           │                                            │
           │  START ──► researcher ◄──┐                 │
           │               │         │                  │
           │               ▼         │                  │
           │       researcher_tools ─┘                  │
           │               │                            │
           │          (on exit)                          │
           │               ▼                            │
           │       compress_research ──► END            │
           └────────────────────────────────────────────┘
```

### 1.1 Main Graph Nodes

| Node | Input | Output | Description |
|------|-------|--------|-------------|
| `clarify_with_user` | User messages | `goto write_research_brief` or `END` (with interrupt for clarification) | Decides if clarification is needed; if `allow_clarification=False`, skips directly |
| `write_research_brief` | User messages | `goto research_supervisor` with `research_brief` + `supervisor_messages` | Uses structured output (`ResearchQuestion`) to generate a focused research brief |
| `research_supervisor` | Mounted as `supervisor_subgraph` | `notes`, `research_brief` | The entire supervisor ↔ supervisor\_tools loop runs as a compiled subgraph |
| `final_report_generation` | Accumulated `notes` | `final_report` | Synthesizes all collected research into a comprehensive report |

### 1.2 Graph Construction

```python
# deep_researcher.py L802-820
deep_researcher_builder = StateGraph(AgentState, input=AgentInputState, config_schema=Configuration)

deep_researcher_builder.add_node("clarify_with_user", clarify_with_user)
deep_researcher_builder.add_node("write_research_brief", write_research_brief)
deep_researcher_builder.add_node("research_supervisor", supervisor_subgraph)  # mounted subgraph
deep_researcher_builder.add_node("final_report_generation", final_report_generation)

deep_researcher_builder.add_edge(START, "clarify_with_user")
deep_researcher_builder.add_edge("research_supervisor", "final_report_generation")
deep_researcher_builder.add_edge("final_report_generation", END)

deep_researcher = deep_researcher_builder.compile()
```

---

## 2. Supervisor ↔ Supervisor\_Tools ReAct Loop

This is the **core research execution mechanism**. It implements a classic **ReAct
(Reasoning + Acting)** pattern within LangGraph.

### 2.1 Design Principle

The loop separates **decision-making** (supervisor) from **action execution**
(supervisor\_tools), creating a clean feedback cycle:

```
supervisor (Think / Decide)
    │
    │  AIMessage with tool_calls
    ▼
supervisor_tools (Act / Observe)
    │
    │  ToolMessage results
    ▼
supervisor (Reflect / Next Decision)
    │
    ...loop continues...
    │
    ▼
   END (when research is complete)
```

**Why two nodes instead of one?**

1. **Separation of concerns** — The LLM reasoning step (`supervisor`) only produces
   decisions (tool calls); tool execution (`supervisor_tools`) handles I/O, concurrency,
   and error recovery. This prevents LLM calls from being blocked by slow tool execution.

2. **LangGraph streaming granularity** — Each node completion emits an `updates` chunk.
   By splitting into two nodes, the stream produces fine-grained progress signals:
   one when the LLM finishes deciding, another when tools finish executing. A single
   combined node would only emit once at the end, hiding intermediate progress.

3. **Flexible routing** — `supervisor_tools` can conditionally route to `END` (on
   `ResearchComplete` or iteration cap) or back to `supervisor` (for another round).
   This pattern is idiomatic in LangGraph and avoids complex conditional edges.

4. **Parallel tool execution** — `supervisor_tools` can run multiple `ConductResearch`
   calls concurrently via `asyncio.gather`, while `supervisor` focuses purely on
   strategic planning.

### 2.2 Supervisor Node (`supervisor`)

```python
# deep_researcher.py L240-289
async def supervisor(state: SupervisorState, config: RunnableConfig)
    -> Command[Literal["supervisor_tools"]]:
```

**Available tools bound to the LLM:**

| Tool | Purpose |
|------|---------|
| `ConductResearch` | Delegate a specific research topic to a researcher subgraph |
| `ResearchComplete` | Signal that enough research has been collected |
| `think_tool` | Internal strategic reflection (not executed externally) |

**Behavior:**
- Reads `supervisor_messages` (conversation history including previous tool results)
- Invokes the LLM with tool bindings
- **Always** routes to `supervisor_tools` (unconditional `goto`)
- Increments `research_iterations` counter

### 2.3 Supervisor\_Tools Node (`supervisor_tools`)

```python
# deep_researcher.py L291-427
async def supervisor_tools(state: SupervisorState, config: RunnableConfig)
    -> Command[Literal["supervisor", "__end__"]]:
```

**Exit conditions (checked first, any one triggers `goto=END`):**

| Condition | Config parameter | Default |
|-----------|-----------------|---------|
| `research_iterations > max_researcher_iterations` | `max_researcher_iterations` | 6 |
| No tool calls in latest AIMessage | — | — |
| `ResearchComplete` tool was called | — | — |

**Tool execution (when loop continues):**

1. **`think_tool`** calls → record reflection as `ToolMessage`; loop continues
2. **`ConductResearch`** calls → each spawns a researcher subgraph via `ainvoke`:
   - Up to `max_concurrent_research_units` (default 5) run in parallel via `asyncio.gather`
   - Overflow calls receive an error message
   - Results come back as `compressed_research` strings in `ToolMessage`
3. All `ToolMessage` results are appended to `supervisor_messages`
4. Routes back to `supervisor` for the next reasoning step

### 2.4 Loop Lifecycle Example

```
Iteration 1:
  supervisor  → LLM decides: ConductResearch("AI safety trends"),
                              ConductResearch("AI regulation overview")
  supervisor_tools → runs 2 researcher subgraphs in parallel
                   → returns compressed results as ToolMessages
                   → goto supervisor

Iteration 2:
  supervisor  → LLM reflects on results, decides: ConductResearch("Case studies")
  supervisor_tools → runs 1 researcher subgraph
                   → goto supervisor

Iteration 3:
  supervisor  → LLM decides: ResearchComplete (enough data collected)
  supervisor_tools → detects ResearchComplete → goto END
                   → passes accumulated `notes` to main graph
```

### 2.5 Configuration Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_researcher_iterations` | 6 | Maximum supervisor ↔ supervisor\_tools rounds |
| `max_concurrent_research_units` | 5 | Max parallel `ConductResearch` per round |
| `max_react_tool_calls` | 10 | Max tool calls per researcher subgraph |
| `research_model` | Gateway default | LLM for supervisor and researcher |
| `compression_model` | Gateway default | LLM for `compress_research` |

---

## 3. Researcher Subgraph

Each `ConductResearch` tool call spawns an independent researcher subgraph.

### 3.1 Nodes

| Node | Role |
|------|------|
| `researcher` | LLM with search tools + `think_tool`; generates tool calls |
| `researcher_tools` | Executes search tools; routes to `researcher` or `compress_research` |
| `compress_research` | Synthesizes all findings into a concise summary |

### 3.2 Execution Mode

```python
# open_deep_research_compiled.py L497-529
async def stream_researcher_subgraph_with_sse(researcher_graph, initial_state, config, ...):
    result = await researcher_graph.ainvoke(dict(initial_state), config=config)
```

The researcher subgraph runs via **`ainvoke` only** (not `astream`). This was a
deliberate design decision — an earlier implementation used `astream` and pushed
intermediate events to `subagent_sse_event_queue`, but this produced excessive SSE
noise for the frontend. The current approach returns only the final `compressed_research`
string to the supervisor.

### 3.3 Exit Conditions

The `researcher_tools` node exits the loop when:
- No tool calls in the latest AIMessage
- `tool_call_iterations >= max_react_tool_calls` (default 10)
- `ResearchComplete` tool was called (not typically used at researcher level)

All paths lead to `compress_research` → `END`.

---

## 4. SSE Signal Flow

The compiled adapter (`open_deep_research_compiled.py`) bridges LangGraph streaming
events to SecManus SSE events for the frontend.

### 4.1 Stream Configuration

```python
# open_deep_research_compiled.py L618-626
async for raw_event in original_research_graph.astream(
    {"messages": [HumanMessage(content=query)]},
    config=config,
    stream_mode=["messages", "updates"],
    subgraphs=True,
):
```

Two stream modes run simultaneously:
- **`messages`** — Token-level LLM output chunks (real-time streaming)
- **`updates`** — Node completion state updates (structural events)

`subgraphs=True` ensures nested supervisor/researcher node events are visible.

### 4.2 Four-Phase UI Timeline

The main graph maps to four UI progress phases:

| Phase ID | Label Key | Triggered by node completion |
|----------|-----------|------------------------------|
| `deep_research_clarify` | `research_sse_phase_clarify` | `clarify_with_user` |
| `deep_research_plan` | `research_sse_phase_brief` | `write_research_brief` |
| `deep_research_collect` | `research_sse_phase_collect` | `research_supervisor` |
| `deep_research_report` | `research_sse_phase_final` | `final_report_generation` |

Phase transitions use **leading edges**: when a node completes, the current phase is
marked `success` and the next phase is marked `running`.

```python
# open_deep_research_compiled.py L60-64
_MAIN_GRAPH_PHASE_EDGES = {
    "clarify_with_user":        ("deep_research_clarify", "deep_research_plan"),
    "write_research_brief":     ("deep_research_plan",    "deep_research_collect"),
    "research_supervisor":      ("deep_research_collect",  "deep_research_report"),
    "final_report_generation":  ("deep_research_report",   None),
}
```

**Key rule:** Only **main-graph top-level** node keys trigger phase transitions. Nested
nodes like `supervisor`, `supervisor_tools`, `researcher`, `compress_research` do **not**
advance the four-slot UI timeline — they all map to the `deep_research_collect` phase
label for display purposes only.

### 4.3 SSE Events by Node

#### `research_supervisor` (main graph level)

| Event | When | Payload |
|-------|------|---------|
| `step` (phase milestone) | Node completes | `phaseId: "deep_research_collect"` → `success`; `phaseId: "deep_research_report"` → `running` |
| `step` (debug) | Node completes | `id: "debug-node-research_supervisor"`, `visibility: "debug"` |

This node fires **once** when the entire supervisor subgraph finishes — not on each
internal loop iteration.

#### `supervisor` / `supervisor_tools` (inside supervisor subgraph) — **SILENT**

All five nodes (`supervisor`, `supervisor_tools`, `researcher`, `researcher_tools`,
`compress_research`) are in `_SUPERVISOR_SILENT_NODES`. During the research collection
phase, **all** LLM token deltas, thinking, debug steps, and non-ConductResearch
tool\_calls / tool\_results are **suppressed** from SSE. Only ConductResearch-related
events pass:

| Event | Source node | Trigger | Payload |
|-------|-------------|---------|---------|
| `tool_call` | `supervisor` | AIMessage with `ConductResearch` tool\_call | `toolName: "ConductResearch"`, `status: "running"` |
| `tool_result` | `supervisor_tools` | ToolMessage named `ConductResearch` | `toolName: "ConductResearch"`, `status: "success"` |

The UI receives `tool_call` (status `running`) when the supervisor dispatches a
research task, and `tool_result` (status `success`) when that task completes —
enabling the work list to update from "running" to "done".

**Why researcher nodes are also silent:** Although `stream_researcher_subgraph_with_sse`
runs the researcher via `ainvoke()` (not `astream`), the parent graph's
`astream(subgraphs=True)` penetrates through `ainvoke()` and exposes internal events
from `researcher`, `researcher_tools`, and `compress_research` — including `web_search`
tool calls and LLM token deltas. Adding these nodes to the silent set suppresses all
that noise.

**Callback isolation:** The parent adapter's `LlmInvokeLifecycleCallbackHandler` is
stripped from the config before passing to the research graph's `astream()`. This
prevents orphan `llm_invoke_start/end` events from researcher `ainvoke` internal LLM
calls that would otherwise create empty thinking blocks in the frontend.

#### `researcher` / `researcher_tools` / `compress_research`

**Current behavior: No real-time SSE.** Since the researcher subgraph runs via
`ainvoke`, no intermediate events reach the parent stream. The ConductResearch
`tool_result` on `supervisor_tools` is the completion signal for each research task
(see silent-node table above).

### 4.4 Event Extraction Pipeline

```
LangGraph astream(stream_mode=["messages","updates"], subgraphs=True)
    │
    ├── "messages" events ──► FILTER: only AIMessage/AIMessageChunk pass
    │                      │  (SystemMessage, HumanMessage, ToolMessage discarded —
    │                      │   they leak through subgraphs=True state mutations)
    │                      ├── Silent-node check (_SUPERVISOR_SILENT_NODES)
    │                      ├── LlmInvokeEmitter (token-level delta)
    │                      └── Early tool_call push (before updates)
    │
    └── "updates" events  ──► research_llm_emit.close() (end current LLM invoke)
                           ──► _extract_stream_events():
                                ├── _research_phase_transition_events()  → phase milestones
                                ├── debug step per node
                                ├── SystemMessage → discarded
                                ├── HumanMessage → debug-input (with dedup)
                                ├── AIMessage → llm_invoke_triplet (skip if streamed)
                                │            → tool_call (dedup with messages stream)
                                └── ToolMessage → tool_result
```

### 4.5 SSE Event Shape Reference

| `type` | Key fields | Description |
|--------|-----------|-------------|
| `step` (milestone) | `phaseId`, `phaseIndex`, `status` (`running`/`success`/`skipped`), `subagentName: "deep-research"`, `researchSubgraph: true` | UI progress bar |
| `step` (debug) | `id: "debug-node-*"`, `visibility: "debug"`, `internal: true`, `node`, `label` | Internal node tracking |
| `step` (human input) | `id: "debug-input-*"`, `detail`, `source` (message key) | HumanMessage received |
| `llm_invoke_start` | `invokeId` | LLM call begins |
| `llm_delta` | `invokeId`, `channel` (`reasoning`\|`text`), `content` | Streaming token |
| `llm_invoke_end` | `invokeId` | LLM call ends |
| `tool_call` | `id`, `toolName`, `toolInput`, `node`, `status: "running"` | Tool invocation started |
| `tool_result` | `id`, `toolName`, `toolOutput`, `node`, `status: "success"` | Tool result returned |
| `error` | `id`, `status`, `detail` | Subagent exception |

### 4.6 Text Prefix Labels

Visible LLM output is prefixed based on the current node:

| Node set | Prefix label key | Typical display |
|----------|-----------------|-----------------|
| `supervisor`, `supervisor_tools`, `researcher`, `researcher_tools`, `compress_research`, `research_supervisor` | `research_sse_prefix_draft_findings` | "Draft findings" |
| `final_report_generation` | `research_sse_prefix_final_prep` | "Final preparation" |
| Other nodes | `research_sse_prefix_answer` | "Answer" |

Thinking content uses `research_sse_prefix_thinking`.

### 4.7 Deduplication Mechanisms

1. **Tool call dedup** — `emitted_tool_call_sse_ids` (set) prevents the same tool call
   from being emitted twice (once from `messages` stream, once from `updates` stream).

2. **Research brief dedup** — When `research_supervisor` or `supervisor` receives a
   `HumanMessage` whose normalized content matches the brief generated by
   `write_research_brief`, the `debug-input` event is suppressed.

3. **Phase milestone dedup** — `research_phase_markers_done` (set) ensures each phase
   transition (`running`/`success`) fires at most once.

---

## 5. Adapter Integration

### 5.1 Compiled Adapter (primary path)

`open_deep_research_compiled.py` → `_run_open_deep_research_subagent()`:
- Uses `astream(stream_mode=["messages","updates"], subgraphs=True)`
- Pushes events to `subagent_sse_event_queue` or `subagent_stream_writer`
- Events are picked up by `deepagents_stream_adapter.py` →
  `_merge_astream_and_lifecycle` → `tag_merged_subagent_sse` (adds
  `subagentStream: true`, `researchSubgraph: true`)

### 5.2 Legacy Adapter

`open_deep_research_original_adapter.py`:
- Uses `stream_mode="updates"` only (no token streaming)
- Produces `tool_call`, `tool_result`, `reasoning` (as `llm_invoke_triplet`)
- No `phaseId` milestones
- `research_supervisor` key used only to detect `reached_research_execution`

---

## 6. Layered Query Input (Main Agent → Research Graph)

When the main agent delegates to `task(deep-research)`, it uses a structured
format in the task `description` to separate the user's original question from
its own preliminary web\_search findings:

```
ORIGINAL_QUERY: <user's verbatim question>
---CONTEXT---
<main agent's explore findings — preliminary, may be inaccurate>
```

### 6.1 Why Separation Matters

The main agent's explore step (Path B `web_search`) can introduce inaccuracies:
fabricated CVE numbers, wrong attributions, speculative claims. Without separation,
`clarify_with_user` sees a richly detailed message and skips clarification — even
when the user's actual question was vague.

### 6.2 Parsing (`open_deep_research_compiled.py`)

`parse_layered_task_description(raw_query)` splits on `---CONTEXT---`:

| Input format | `original_query` | `explore_context` |
|---|---|---|
| `ORIGINAL_QUERY: Q\n---CONTEXT---\nC` | `Q` | `C` |
| `ORIGINAL_QUERY: Q` (no separator) | `Q` | `""` |
| Plain text (backward compatible) | full text | `""` |

`_build_layered_research_messages()` then constructs the initial message list:

```python
# Layered format:
[
    HumanMessage(content="user's original question"),
    SystemMessage(content="[Preliminary context from routing agent — may contain inaccuracies...]\n<explore findings>"),
]

# Plain format (backward compatible):
[HumanMessage(content="full query")]
```

### 6.3 Effect on `clarify_with_user`

The prompt (`clarify_with_user_instructions.md`) instructs the LLM to:
- Focus on the **Human message** (user's original question) for clarity judgment
- Treat the System message as unverified hints, not confirmed facts
- Ask for clarification if the original question is vague — even if context is detailed

### 6.4 MASTER\_AGENT.md Contract

The main agent is instructed (under Delegation Practices → `deep-research description
format`) to always use the layered format. `ORIGINAL_QUERY:` must be the user's
verbatim text, never rephrased or enriched.

---

## 7. Sequence Diagram — Full Research Run

```
User           Main Graph                Supervisor Subgraph           Researcher Subgraph
 │                │                              │                            │
 │  query ──────► │                              │                            │
 │                │  clarify_with_user            │                            │
 │                │  ──► SSE: clarify=running     │                            │
 │                │  ──► SSE: clarify=success     │                            │
 │                │       plan=running            │                            │
 │                │                               │                            │
 │                │  write_research_brief          │                            │
 │                │  ──► SSE: plan=success         │                            │
 │                │       collect=running          │                            │
 │                │                               │                            │
 │                │  ═══► research_supervisor ═══► │                            │
 │                │                               │  supervisor (LLM)          │
 │                │                  llm_delta ◄── │  ──► tool_call(Conduct×2)  │
 │                │                               │                            │
 │                │                               │  supervisor_tools          │
 │                │                               │  ──► ainvoke ────────────► │ researcher
 │                │                               │                            │ ──► search
 │                │                               │                            │ ──► compress
 │                │                               │  ◄── compressed_research ─ │
 │                │               tool_result ◄── │                            │
 │                │                               │                            │
 │                │                               │  supervisor (reflect)      │
 │                │                  llm_delta ◄── │  ──► ResearchComplete      │
 │                │                               │                            │
 │                │                               │  supervisor_tools          │
 │                │                               │  ──► goto END              │
 │                │                               │                            │
 │                │  ◄═══ research_supervisor ═══  │                            │
 │                │  ──► SSE: collect=success      │                            │
 │                │       report=running           │                            │
 │                │                               │                            │
 │                │  final_report_generation       │                            │
 │                │  ──► SSE: report=success       │                            │
 │                │  ──► SSE: WRAPUP text          │                            │
 │  ◄──── report  │                               │                            │
```
