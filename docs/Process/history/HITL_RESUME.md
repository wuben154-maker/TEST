# Human-in-the-loop: resume contract

This document matches `langgraph` **1.0.8** behavior in this repo.

## Versions

- **langgraph**: 1.0.8 (`Command`, `interrupt`, `StateSnapshot.interrupts`)
- **Interrupt stream key**: `__interrupt__` on `updates` chunks (see `app/parsers/hitl_interrupt_sse.py`)

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/analyze` | Normal turn; blocked while `StateSnapshot.interrupts` is non-empty (when `AGENT_HITL_ENABLED` and blocking flag on). |
| `POST` | `/analyze/resume` | Resume after interrupt; requires `AGENT_HITL_ENABLED=true`. |

## Resume body (`POST /analyze/resume`)

JSON (`AnalyzeResumeRequest`):

- `session_id` (string, required): same as `thread_id` used for `/analyze`.
- `resume` (any): forwarded to `Command(resume=resume)`.
  - **HumanInTheLoopMiddleware** (tool review): pass a dict with `decisions` (list of `approve` / `edit` / `reject` decisions). For a single pending review, the stream adapter surfaces `hitlRequest`; match LangChain examples (often `{"decisions": [{"type": "approve"}]}`).
  - **Single `interrupt("question")` style**: pass a scalar or string; LangGraph resumes the next interrupt with that value.
  - **Multiple interrupts by id**: use the mapping form described in LangGraph `Command` doc (`resume` as map of interrupt id → value).
- `request_id`, `project_id`, `ui_language`, `model_id`: optional; same semantics as `/analyze`.

## SSE when paused

When the graph hits an interrupt, the adapter emits:

1. One or more `decision_request` and/or `parameter_request` events with `interruptKind` (`langchain_hitl_v1` or `user_input_v1`).
2. `step` with `id: hitl-waiting`, `status: waiting`.
3. `done` with `awaitingHuman: true` and `hitl: { interruptIds: [...] }`.

The client must call `/analyze/resume` before sending another normal `/analyze` message (if blocking is enabled).

## Environment flags (python-agent-service)

| Variable | Default | Meaning |
|----------|---------|---------|
| `AGENT_HITL_ENABLED` | `false` | Master switch for HITL + resume route. |
| `AGENT_HITL_INTERRUPT_TOOLS` | empty | Comma-separated tool names → `interrupt_on` for main + general-purpose subagent (`True` each). |
| `AGENT_HITL_MAIN_REQUEST_USER_INPUT_TOOL` | `false` | Also register `request_user_input` on the **main** agent (subagents get it when HITL is enabled via common tools). |
| `AGENT_HITL_BLOCK_ANALYZE_WHEN_PENDING` | `true` | Reject new `/analyze` while interrupts are pending. |

## Error cases (SSE / UX)

- `hitl-pending`: new `/analyze` while interrupts exist.
- `hitl-nothing-pending`: `/analyze/resume` when `aget_state().interrupts` is empty.

## Further reading

- `docs/Process/SSE_EVENT_CATALOG.md` — HITL-related event types.
- `openspec/changes/human-in-the-loop-agents/` — proposal and tasks.
