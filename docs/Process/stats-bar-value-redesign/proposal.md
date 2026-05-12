# Proposal — Stats Bar Value Redesign

## Problem

The current `TaskStatsBar` (`src/components/workspace/TaskStatsBar.tsx`) shows **11 metrics** across a primary row + a technical row, but roughly half of them are **process-counters** (`toolCallCount`, `blockCount`, `thinkingDurationMs`, `sandboxRunCount`, `subagentCount`, `durationMs`) that describe *how the LLM ran* rather than *what the user should do*.

Concretely:

- `toolCallCount` / `blockCount` / `thinkingDurationMs` carry no decision value — a security analyst does not care that the agent called 17 tools or thought for 4.2s.
- `sandboxRunCount`·`subagentCount` is surfaced as an abstract "evidence depth" chip that users cannot map to an action.
- `riskScore` is extracted from markdown via regex (`reportProcessMeta.extractRiskScoreFromBlocks`), so it is fragile across languages and output templates.
- Both **deep-research** reports (evidence + citations + knowledge gaps) and **security** reports (severity + IOCs + validation depth) share the same generic field set. Neither domain gets what it needs.

Result: users look at the bar, cannot quickly answer "how bad is it / what do I do next / can I trust this", and the technical row is cognitive noise.

## Goals

1. **Decision-first, 5 chips max, single row.** Only surface fields that either (a) trigger an immediate user action or (b) justify confidence in the conclusion.
2. **Task-domain profiles.** Render different fields for `research` vs `security` tasks; hide the entire bar for anything else.
3. **Meta-first data path.** Backend attaches a structured `meta` payload on the final `agent_response` SSE event. Frontend renders straight from `meta`; no markdown regex fallback in scope.
4. **Delete** all process-counters and audit fields from the stats bar surface.

## Non-goals

- Not changing subagent `SKILL.md` output-format sections or the report body renderers (`SummaryBlock` / `AnalysisBlock` / `IntelCard` / `TextBlock`).
- Not introducing a `generic` profile or a "simplified" fallback bar.
- Not moving audit fields (`completedAt`, `durationMs`, `sessionId`, `requestId`) to any other surface (tooltip, popover, shared-report page) — they are removed from the stats bar entirely.
- Not building a P2 popover or hover panel on the stats bar.
- Not changing billing/observability collection — process counters keep flowing in SSE; we just stop rendering them.

## Users & scenarios

| Persona | Task kind | "I open the report and I want to know…" |
|---------|-----------|-----|
| SOC / IR analyst | `security` (web / email / binary / soc) | How severe? Numeric risk? How many findings I must handle and of what grade? What attack class? How was this verified? |
| Threat researcher / product manager | `research` (deep-research) | How many key findings and recommendations? How broad are the sources? How fresh is the evidence? What gaps remain? |

## Scope

| Layer | Change |
|-------|--------|
| Frontend types | `AnalysisResultStats` narrowed: drop `toolCallCount`, `sandboxRunCount`, `blockCount`, `thinkingDurationMs`, `subagentCount`. Add `taskKind`, `security?`, `research?` sub-objects. |
| Frontend hook | `useStreamingAnalysisMulti` stops accumulating deleted counters; consumes `meta` from the final `agent_response` event to populate the new sub-objects. |
| Frontend components | `TaskStatsBar` rewritten to render one of two profiles based on `taskKind`; removes primary/tech split, severity pill, depth chip. Updates in `LiveWorkspace.tsx` / `PostLoginWorkspaceStart.tsx` props contract where needed. |
| Frontend i18n | `t.workspace.taskPanel` keys: add new field labels, mark deleted keys as removed across `en/zh/ja/ko`. |
| Backend SSE | `adapt_astream_to_sse` (`python-agent-service/app/parsers/deepagents_stream_adapter.py`) attaches a `meta` object to the final `agent_response` event when the task type is recognised. |
| Backend subagents | deep_research and 4 security subagents produce meta fields (risk score / threat class / validation level / key findings / sources / freshness / gaps) as structured output, parsed into the `meta` payload. |
| Persistence | `meta` is persisted with the assistant message `stats` field (existing `stats?: AnalysisResultStats` on `ConversationMessage`), so bar survives reload. |

## Dependencies

- Existing SSE event adapter (`app/parsers/deepagents_stream_adapter.py`).
- Existing `WorkspaceBlock` types (consumed when backend cannot emit meta — but in scope we only lean on structured subagent output, not on blocks regex).
- i18n files `src/i18n/locales/{en,zh,ja,ko}.ts`.
- No new environment variables; no new dependencies.

## Success metrics

1. **Bar contains zero process-counter fields** (verified by component test + e2e snapshot).
2. **≥90% of finished security/research runs** produce an `agent_response` event with a populated `meta.security` or `meta.research` object (verified by an integration test that drives each subagent end-to-end).
3. **User-visible "decision" can be read from the bar in ≤3 seconds** — smoke-tested in `/design-review`:
   - security: severity + risk score + actionable + threat class visible without scroll;
   - research: key findings + recommendations + sources + freshness visible without scroll.
4. **No regression on persistence** — after reload, the bar re-hydrates from persisted `message.stats` with identical chips.

## Risks

| Risk | Mitigation |
|------|------------|
| Subagent output not structured enough to populate meta reliably | Deep-research already has a known output format; security subagents lean on `detect_web_attack` schema-v2 `findings[]` + `signals`. Where meta is missing, frontend hides the chip (not the whole bar). |
| i18n drift (4 languages × ~8 keys) | Add a Vitest snapshot ensuring all 4 locales share the same key set. |
| Severity pill / depth chip removal is visually jarring to existing users | Scoped to this delivery; release note in CHANGELOG. |

## Out-of-scope follow-ups (not in this delivery)

- Populating the **P2** fields (affected assets, IOC count, cross-source verification, evidence time span) into the **report body** via subagent SKILL.md tweaks. Noted here so the knowledge is not lost; scheduled separately.
- `generic` task-kind profile.
- Shared-report page (`pages/SharedReport.tsx`) alignment. It may still render the old stats format; a follow-up delivery will reconcile.
