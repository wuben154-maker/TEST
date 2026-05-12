# Stats payload sentinel — design.md (Patch tier)

## Metadata
- slug: `stats-payload-sentinel`
- date: 2026-04-25
- tier: Patch (≤ 3 source files + 2 prompt files + tests; no schema/API change)
- related-bug: "对话窗口里 subagent summary 末尾出现 `\`\`\`json {...}\`\`\`` 这一段（research_stats / findings 的结构化 stats payload）"

## Problem

`stats-bar-value-redesign` and the follow-up "model-generated findings" delivery
instruct subagents (deep-research final-report; web/email/binary/SOC) to append
**one fenced JSON block** after `## SM_SUBAGENT_WRAPUP` so the backend can
derive the stats bar (`research_stats` / `findings`) from a structured payload.

Backend `stats_meta` parsers correctly read the payload from the **raw**
`task_outputs`. But `subagent_sse_visible_text(...)` (in
`app/parsers/final_message_split.py`) returns *the same wrapup body*, JSON
included, to the chat UI as the streamed "summary preview". The fenced JSON
block leaks into the user-facing chat bubble.

## Fix — sentinel heading

Introduce a stable sentinel heading **`### SM_STATS_PAYLOAD`** (H3, distinct
from the H2 `## SM_SUBAGENT_WRAPUP`). Subagents emit the JSON only after this
sentinel; the backend strips the sentinel and everything after it before
returning the wrapup to the chat UI.

```
## SM_SUBAGENT_WRAPUP

[2-6 sentence preview — visible in chat]

### SM_STATS_PAYLOAD

```json
{ ... }
```
```

Why a sentinel rather than "find the first ```json block in wrapup":
- Robust against future use of fenced JSON in the prose itself.
- Localizable: prompt change is one heading line; backend change is one
  string-find.
- `stats_meta._extract_..._from_text` reads `task_outputs` (full raw output)
  and is unaffected — it scans for `\`\`\`json` regardless of preceding heading.

## Code touch list

| File | Change |
|---|---|
| `python-agent-service/app/parsers/final_message_split.py` | Add `SUBAGENT_STATS_PAYLOAD_HEADING = "### SM_STATS_PAYLOAD"`; helper `_strip_stats_payload_tail(text)` truncates from that heading line onward; call from `subagent_sse_visible_text` after `split_subagent_wrapup_and_full` returns wrapup, **and** from the wrapup-only fallback branch. |
| `python-agent-service/app/prompts/subagent_output_appendix.py` | Insert `### SM_STATS_PAYLOAD` line above the fenced ```\`\`\`json``` block; update prose to call out the sentinel as required when emitting the block. |
| `python-agent-service/app/agents/research/open_deep_research_original/prompt_md/final_report_generation_prompt.md` | Same insertion before the `research_stats` fenced block. (Braces remain `{{ }}` because this file goes through `str.format`.) |
| `python-agent-service/tests/test_final_message_split.py` | New tests: (a) `subagent_sse_visible_text` strips sentinel + JSON tail; (b) when sentinel absent, behaviour unchanged; (c) sentinel inside the *full body* (above WRAPUP) is **not** affected. |
| `python-agent-service/tests/test_research_output_language.py` | Existing format-smoke test must remain green (sentinel does not introduce new placeholders). |
| `python-agent-service/tests/test_stats_meta.py` | Existing fenced-json extraction tests must remain green (sentinel is a comment from the parser's perspective). |

No DB / API / UI component changes.

## Testing strategy

### Unit (pytest)

| ID | Scenario | Assertion |
|---|---|---|
| S-01 | Wrapup contains `### SM_STATS_PAYLOAD` followed by ```json``` block | `subagent_sse_visible_text` returns wrapup prose **without** sentinel and JSON |
| S-02 | Wrapup contains no sentinel | `subagent_sse_visible_text` returns the wrapup as-is (regression guard) |
| S-03 | Sentinel appears inside the full-body prefix (above WRAPUP) | not stripped; full body preserved (because `split_subagent_wrapup_and_full` already separates the prefix from wrapup) |
| S-04 | Body-first layout, wrapup wholly absent → heuristic fallback | sentinel-stripped if it accidentally landed in heuristic excerpt (defensive) |
| S-05 | `_extract_findings_from_task_output` / `_extract_research_stats_from_text` still find the fenced JSON when the sentinel is in front of it | stats_meta unaffected |
| S-06 | `final_report_generation_prompt.format(...)` smoke test (existing) | still green — sentinel adds no `{` placeholder |

E2E: not needed for Patch tier.

## Edge cases

- **LLM omits the sentinel** (violates prompt): prose remains, but the fenced
  JSON also remains in the chat bubble — same as today. Acceptable; the
  prompt is explicit and a defensive "trim trailing fenced ```json``` from
  wrapup" can be added later if real outputs show non-compliance.
- **Sentinel appears in main body** (model accident): only the wrapup is
  trimmed; the main body delivered to the parent agent / conclusion pipeline
  is untouched.
- **Multiple sentinels**: trim from the **first** occurrence onward.

## Implementation order

1. Write red tests S-01 .. S-04.
2. Implement `_strip_stats_payload_tail` + call sites.
3. Update both prompt files with the sentinel line.
4. Run targeted backend tests → green.
5. Run full backend + frontend suite for regression.

## Round 2 (2026-04-25) — `conclusion.content` also leaked the sentinel

After S-01..S-05 shipped, the user reported the sentinel + fenced JSON still
appearing in the chat for a deep-research turn. Repro analysis traced the
escape path to a **second** out-point that the round-1 fix did not cover:

When a subagent emits its body **without** the canonical
`## SM_SUBAGENT_WRAPUP` heading (deep-research's free-form layout often does
this — the model writes prose, then directly the `### SM_STATS_PAYLOAD`
sentinel + fenced JSON), `split_subagent_wrapup_and_full` returns
`(None, None)`. The adapter's finalize then falls back to
`heuristic_digest_and_report(raw_final)`, which keeps the sentinel and JSON
inside `conclusion_body`. That body is forwarded into the SSE
`conclusion.content` after only `strip_digest_tail(...)` — which knows
nothing about `### SM_STATS_PAYLOAD`. The chat UI therefore renders the JSON
when `streamingConclusionForChat` lands in the legacy fallback path
(`taskKind` not yet set, or `blocks` not yet emitted).

### Fix
- New public helper **`strip_conclusion_machine_tails(text)`** in
  `final_message_split.py` removes the *first-occurring* of either
  `### SM_STATS_PAYLOAD` or `## SM_TASK_DIGEST`, dropping that line and
  everything after.
- All three `conclusion.content` out-points in `deepagents_stream_adapter.py`
  (post-tasks finalize, conclusion-without-tasks, reasoning fallback) replace
  `strip_digest_tail(...)` with `strip_conclusion_machine_tails(...)`.
- Existing `subagent_sse_visible_text` strip path is untouched — round-1
  still handles the tool-output preview channel.

### Tests added (`test_final_message_split.py`)
- C-01: stats payload tail stripped from prose.
- C-02: digest tail stripped (regression guard for the original behaviour).
- C-03: both tails in either order — earliest tail wins, the rest disappears
  with the dropped suffix.
- C-04: body without machine tails — no-op, content preserved.
- C-05: defensive — empty / `None` input returns input unchanged.

### Why this is safe for stats derivation
`derive_research_meta` / `derive_security_meta` parse `research_stats` /
`findings` from the **raw** subagent task outputs (`task_outputs`), not from
the cleaned `conclusion.content`. Stripping the tail from `conclusion.content`
therefore does not affect the stats bar — confirmed by the green
`test_stats_meta.py` and `test_message_persistence_stats.py` suites
(157 passing).
