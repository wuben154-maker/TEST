## Context

Deep research runs as a compiled LangGraph subgraph (`open_deep_research_compiled.py`). Each `stream_mode="updates"` chunk is converted by `_extract_stream_events` into canonical SSE-shaped dicts and queued into the main agent stream. The UI today renders these as **plain text** lines (e.g., linear timeline). Problems are content-level: system prompts leak into `step.detail`, duplicate human briefs, merged thinking+text in `reasoning`, raw block-shaped tool outputs, and ambiguous ordering of “draft-like” supervisor prose vs final `conclusion`.

## Goals / Non-Goals

**Goals:**

- Reduce redundant and internal-only text in the **user-visible** deep-research SSE sequence while keeping **canonical event types** (`step`, `reasoning`, `tool_call`, `tool_result`, `conclusion`, `error`, `done` as applicable).
- Apply **plain-text** conventions only (prefixes, section headers in string content, clearer `step.label` copy)—no dependency on collapsible UI, tabs, or new interaction patterns.
- Keep **one** authoritative final answer path: `conclusion` remains the terminal user-facing report body; intermediate long text is labeled in plain language so the linear read order is understandable.

**Non-Goals:**

- New frontend components, folding panels, or timeline layout changes.
- Changing LangGraph topology or research quality (prompts in `prompts.py`) except where needed to support safer redaction (not expected).
- Unifying non–deep-research subagents beyond shared helpers if reuse is trivial.

## Decisions

1. **Built-in system prompts**  
   **Decision:** Do not emit `step` events whose payload is `SystemMessage` content for deep-research stream extraction (compiled path).  
   **Rationale:** Matches `SSE_EVENT_CATALOG` intent (internal instructions are not user timeline material).  
   **Alternative considered:** Emit as `debug` with `internal: true`—rejected for MVP to avoid doubling traffic; can add later for operator mode.

2. **Duplicate brief (`write_research_brief` vs `research_supervisor` human)**  
   **Decision:** Track last normalized “research brief” body; if a subsequent `HumanMessage` in another node’s update matches, skip emitting the second `step` (`… input`).  
   **Rationale:** Same semantic content currently appears twice because `write_research_brief` seeds `supervisor_messages`.  
   **Normalization:** trim whitespace; optional collapse of repeated newlines for comparison.

3. **Reasoning vs thinking (`think_tool` and AIMessage)**  
   **Decision:** When extracting text from AIMessage for `reasoning` events, emit **at most two** plain-text segments in order: optional block prefixed `[Thinking]` (or localized equivalent via existing label helper if available) for chain-of-thought content, then `[Answer]` or unlabeled second paragraph for visible text—or split into **two** `reasoning` events in fixed order (thinking first, then visible) to keep lines short.  
   **Rationale:** Preserves plain-text linear view while making role obvious without UI chrome.  
   **Alternative:** Single event with `---` separator—acceptable if documented; prefer explicit prefixes for grepability.

4. **`ConductResearch` `tool_result`**  
   **Decision:** Parse list/dict content blocks; strip or summarize `type: thinking` into a short line or omit from `toolOutput` if empty after summary; put factual findings into `toolOutput` as plain text with bounded length (reuse existing preview limits where present).  
   **Rationale:** Never show `str(list)` / repr artifacts.

5. **Supervisor long output vs `final_report_generation` vs `conclusion`**  
   **Decision:** Prefix or `step.label` disambiguation in plain text: e.g., `step` with `label` “Research findings (draft)” before large non-final AIMessage bodies; `final_report_generation` node `step` labeled “Final report generation”; `conclusion` unchanged as sole final deliverable text.  
   **Rationale:** User reads top-to-bottom without new UI.

6. **Per-node bare `step` (`label` = raw node name)**  
   **Decision:** Map graph node ids to **short product labels** in plain text (clarify → brief → research → final) for the initial `step` per update, or drop redundant node-only `step` if a richer event follows in the same tick—pick one consistent rule to avoid double headers.  
   **Rationale:** Raw `research_supervisor` is engineer-facing.

## Risks / Trade-offs

- **Risk:** Aggressive dedup hides legitimately changed brief—**Mitigation:** compare normalized full string equality only; optionally allow re-emit if length delta &gt; threshold (future).
- **Risk:** Removing system `step` reduces debuggability—**Mitigation:** optional debug flag later; run logs already written on disk.
- **Risk:** Two `reasoning` lines per message increases line count—**Mitigation:** still clearer than one blob; cap thinking preview length.

## Migration Plan

- Ship backend-only behavior change; frontends consuming plain text see improved strings without feature flags if acceptable.
- Document new conventions in `SSE_EVENT_CATALOG.md`; add/adjust tests in `python-agent-service/tests/` for event sequences (golden or substring assertions).

## Open Questions

- Exact localized prefixes (`[Thinking]` / `[Answer]`) vs using `get_stream_adapter_label` keys—align with existing i18n in stream adapter.
- Whether to suppress **all** per-tick `step` for deep research and rely on `tool_*` + `reasoning` only (may be follow-up if still too busy).
