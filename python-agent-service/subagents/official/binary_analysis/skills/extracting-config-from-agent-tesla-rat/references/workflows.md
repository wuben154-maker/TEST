# Analysis Workflows — `extracting-config-from-agent-tesla-rat`

## Placement in the binary path

`binary-analysis-e2e-orchestrator` runs FR stages through at least FR-08. At
**FR-13**, `binary-analysis-family-triage-workflow` scans the evidence chain
and may load this specialist when the **`agent_tesla` gate** matches (see
that workflow’s delegation table). This skill is **not** a parallel
orchestrator; it only shapes **`llm_inferences`** for Agent Tesla–like config
**after** the gate and **after** Proto-02/Proto-03 preconditions.

## Primary flow (logical)

```text
[FR-01..FR-12 facts in chain]
        |
        v
[Binary-analysis-family-triage-workflow @ FR-13]
        |
   agent_tesla gate true?
   /        \
  no        yes
  |          v
  |    [file_read this SKILL.md + family specialist pass]
  |          |
  |          v
  |    [evidence_chain append: family_candidate / family_config]
  |          |
  +----> [FR-09 .. FR-15 as orchestrated]
```

## Document path (E2E-02)

If analysis is **document-first** and an embedded child PE is still partial,
follow `document-analysis-e2e-orchestrator` ( **`doc_analysis_partial`**
semantics, recursion and budget from E2E-02). Do not assert full
`family_config` on the parent from incomplete child decompilation.

## Related

See `SKILL.md` for routing, downgrades, and NFR-05 reference discipline.
