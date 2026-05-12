## 1. Stream extraction: filter and dedupe

- [x] 1.1 Skip emitting user-visible `step` events for `SystemMessage` in `_extract_stream_events` (compiled deep-research path); verify no `<Task>` / supervisor prompt text appears in emitted `step.detail`.
- [x] 1.2 Add normalized-text tracking for research-brief `HumanMessage` `step` (`… input`): skip second emit when content equals prior brief (write_research_brief vs research_supervisor).
- [x] 1.3 Replace raw LangGraph node names in user-visible `step.label` with short plain-text phase labels per `design.md` (or drop redundant node-only `step` when same tick already carries richer events—document chosen rule in `SSE_EVENT_CATALOG.md`).

## 2. Reasoning and tool output normalization

- [x] 2.1 Split or prefix AIMessage-derived `reasoning` so thinking vs visible text is plain-text distinguishable (two events or prefixed sections); reuse or mirror `_extract_subagent_thinking_and_text` patterns where practical.
- [x] 2.2 Normalize `ConductResearch` (and related delegation) `tool_result.toolOutput`: parse block lists, never expose repr; bound length consistent with existing preview helpers.
- [x] 2.3 Add plain-text disambiguation for long pre-final supervisor AIMessage content vs `final_report_generation` (`step.label` and/or content prefix) without changing `conclusion` contract.

## 3. Tests and documentation

- [x] 3.1 Add or extend `python-agent-service/tests/` to assert event sequences or substrings for: no system prompt in user steps, deduped brief, safe `toolOutput`, marked draft vs final.
- [x] 3.2 Update `docs/Process/SSE_EVENT_CATALOG.md` section G (Open Deep Research) to match implemented behavior.
- [x] 3.3 After merge, update root `project_context.md` if event behavior is part of documented agent UX.
