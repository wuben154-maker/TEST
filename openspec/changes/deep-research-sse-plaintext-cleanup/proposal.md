## Why

Open deep research (compiled subgraph) mirrors LangGraph updates into the main SSE stream as canonical events (`step`, `reasoning`, `tool_call`, `tool_result`, `conclusion`). Today that mapping is faithful but noisy: built-in system prompts and repeated research-brief text appear as user-visible `step` details, tool outputs sometimes surface raw block structures, and intermediate supervisor prose sits alongside final-report generation without clear textual distinction. Users see a cluttered linear timeline even when the UI remains plain text. This change tightens **what** we emit and **how** we normalize payloads so the same plain-text timeline reads as a single coherent narrative.

## What Changes

- Stop emitting user-visible SSE events whose primary payload is **built-in system prompt** text for `write_research_brief` / `research_supervisor` (or emit only on non-user channels per catalog; default: omit from user timeline).
- **Deduplicate** `write_research_brief input` vs `research_supervisor input` when normalized content is identical—emit one representative event.
- **Normalize `reasoning` text** for deep research: separate or order thinking vs user-visible model text in plain text (e.g., prefixed sections or distinct events) so `think_tool` + AIMessage content do not read as one undifferentiated blob where avoidable.
- **Normalize `tool_result` for `ConductResearch`** (and similar): never expose Python/list repr; produce stable plain-text summaries from structured blocks (thinking vs findings).
- **Clarify narrative roles in plain text** for long supervisor outputs vs `final_report_generation` vs final `conclusion` (labels or short prefixes in `step`/`reasoning` content)—no new interactive UI; still linear plain text.
- Update `docs/Process/SSE_EVENT_CATALOG.md` (and types if needed) to document deep-research-specific rules.

## Capabilities

### New Capabilities

- `deep-research-sse-events`: Requirements for SSE event selection, deduplication, and plain-text normalization when `scope` is subagent deep-research (compiled open_deep_research path).

### Modified Capabilities

- (none — no existing `openspec/specs/` entries)

## Impact

- **Backend**: `python-agent-service/app/agents/research/open_deep_research_compiled.py` (`_extract_stream_events` and related), possibly `open_deep_research_original_adapter.py` if parity needed; helpers may align with `app/_vendor/deepagents/middleware/subagents.py` thinking/text split patterns.
- **Frontend**: Prefer **none** for this change (plain text only); if `ThinkingEventType` or envelope fields gain optional keys, minimal typing updates in `src/types/analysis.ts` only if required.
- **Docs**: `docs/Process/SSE_EVENT_CATALOG.md`, optionally `project_context.md` after implementation.
