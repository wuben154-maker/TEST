# Proposal — SOC Alert Hypothesis-Driven Triage (OSCAR, Phase 1)

## Metadata

- **Slug:** `soc-alert-oscar-phase1`
- **Related:** [design.md](./design.md), [acceptance.md](./acceptance.md)

## Problem

The current `soc-alert` subagent is template-oriented (parse → IOCs → static severity). Real SOC triage needs **hypothesis testing**, **evidence-linked verdicts**, and **platform-aware normalization**. Financial-industry practice (e.g. Qingteng / Dropzone-style patterns) shows that **alert-only** reasoning yields poor accuracy unless paired with **context** and **upstream noise control**.

## Goals

1. **Methodology:** Adopt **hypothesis-driven investigation** framed as **OSCAR** (Obtain → Strategize → Collect → Analyze → Report) inside the existing **standard** `soc-alert` subagent (registry + `AGENT.md` + bundle `SKILL.md` + scripts).
2. **L1 — Normalize, classify, hypothesize, decide:** Unified **`NormalizedAlert`** and **platform adapters** for **CrowdStrike Falcon**, **Splunk** (notable / alert-shaped JSON), and **Microsoft Sentinel**, with **extensibility** for future platforms.
3. **L0 — Source filtering:** Lightweight **preset rules** + optional **aggregation** before LLM-heavy triage (inspired by multi-stage denoising in industry write-ups).
4. **Context Memory (Phase 1):** Persist and apply **organization / asset / baseline** facts so triage is **context-aware**; when evidence is insufficient, **lower confidence** and list **required follow-ups**.
5. **Platform intelligence:** **Auto-detect** alert source platform when possible; on high confidence, **prompt** the user to connect the relevant API (future enrichment); on low confidence, **disambiguate** via user choice, then run a **connector onboarding** path (documented steps + optional stub hooks — see design for Phase 1 vs later).
6. **Input (Phase 1):** Primary path is **user-pasted JSON** (and file paths under `/uploads/` as today).

## Non-goals (Phase 1)

- Production-grade, credential-stored **live SIEM queries** for all three vendors (full OAuth/API implementation may be **stubbed or deferred** behind clear acceptance slices).
- New **compiled** LangGraph subagent (remain **standard** `soc-alert` unless explicitly changed later).
- Dedicated **settings UI** for Context Memory (use **chat**, **`request_user_input`**, and/or **`session_parameters`** as per design).

## Users

- SOC analysts using SecManus chat to triage pasted alerts.
- SecManus maintainers extending platform adapters.

## Dependencies

- Existing Deep Agent stack: `task(soc-alert)`, `create_common_tools()`, SkillsMiddleware, bundle `subagents/official/soc-alert/`.
- Optional: `session_parameters` (Supabase) for durable Context Memory — subject to design choice.

## Success metrics

- All **acceptance** criteria **A-*** pass with evidence (pytest / manual protocol).
- Pasted representative samples per platform normalize to **`NormalizedAlert`** with stable fields.
- Reports show **competing hypotheses**, **evidence per hypothesis**, and **verdict with confidence**; insufficient context yields **explicit uncertainty**.

## Open questions (resolved for Phase 1 planning)

| Topic | Resolution |
|-------|------------|
| Subagent style | **Standard** `soc-alert` + SKILL/scripts (not compiled graph). |
| Nested `task()` | **Out of scope**; main agent delegates `soc-alert` only. |
| Context Memory UI | **No new screens** in Phase 1; conversational + storage as in design. |
| API auto-integration | Phase 1 delivers **detection + onboarding playbook + hooks**; full auto-query per vendor may be **incremental**. |
