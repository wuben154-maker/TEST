# Acceptance — soc-alert-oscar-phase1

## Metadata

- **Slug:** `soc-alert-oscar-phase1`
- **Owner:** SecManus Team (TBD)
- **Updated:** 2026-04-07
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope

This acceptance covers:

- `soc-alert` subagent behavior (prompts + SKILL + bundle scripts)
- L0 / L1 pipeline and **CrowdStrike / Splunk / Sentinel** normalization
- Platform auto-detection and **connector onboarding** prompts (Phase 1 depth per criteria)
- **Context Memory** persistence and use in triage
- Automated tests listed below

## Environment

- **Runtime:** Local `python-agent-service` with `pytest`
- **Base URL:** N/A for core criteria (no new HTTP endpoints required for pass)
- **Feature flags:** None required

## Functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| A-01 | **OSCAR + hypothesis:** `SKILL.md` documents Obtain → Strategize → Collect → Analyze → Report and requires **at least two competing hypotheses** before Collect. | Manual doc review + grep |
| A-02 | **Verdict quality:** `AGENT.md` requires every verdict to cite **evidence**; if context insufficient, **lower confidence** and list **gaps / required follow-ups**. | File review |
| A-03 | **L0 present:** Preset noise rules exist (config or code) and **at least one** aggregation or duplicate-window behavior is implemented **or** explicitly documented as no-op with rationale in `design.md`. | Code review + unit test `A-03` |
| A-04 | **CrowdStrike:** Sample Falcon-style JSON fixture normalizes to `NormalizedAlert` with `source_platform=crowdstrike` and populated `entities` or `vendor_blob` suitable for process-oriented hypotheses. | `pytest` |
| A-05 | **Splunk:** Sample Splunk alert / notable-style JSON normalizes with `source_platform=splunk`. | `pytest` |
| A-06 | **Sentinel:** Sample Sentinel alert JSON normalizes with `source_platform=sentinel` and preserves MITRE fields when present. | `pytest` |
| A-07 | **Extensibility:** A **registry** (dict or entry-point pattern) allows adding a fourth adapter without modifying the three core adapter modules’ internals beyond registration. | Code review + minimal test registering a fake adapter |
| A-08 | **Unknown platform:** Unrecognized JSON yields `source_platform=unknown` without crash; detector reports confidence. | `pytest` |
| A-09 | **Context Memory:** Org context can be **read and merged** into triage (helper + SKILL instructions); persistence uses **`session_parameters`** or documented equivalent. | `pytest` or integration script + doc |
| A-10 | **Platform intelligence:** `AGENT.md` or `SKILL.md` instructs: if detector **high confidence** → ask user whether to **connect vendor API**; if **low** → **user selects platform** then follow **onboarding playbook** (checklist exists in repo). | File review + playbook file exists |
| A-11 | **Onboarding playbook:** For each of CrowdStrike / Splunk / Sentinel, a markdown or doc in bundle lists **non-secret** setup steps (env var **names** only, links to vendor docs). | File exists review |
| A-12 | **Input path:** SKILL states primary input is **pasted JSON** and/or **`read_file`** on `/uploads/...`. | File review |
| A-13 | **Regression:** Existing pytest suite for agent/subagent/skills passes (no new failures). | `pytest` (project-defined scope in Phase 6) |

## Non-functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| N-01 | No secrets (API keys, tokens) committed in playbook or fixtures | `git grep` / review |
| N-02 | New Python code comments and docstrings in **English** per `AGENT.md` | Spot review |

## Evidence notes

- A-04–A-06: Golden JSON fixtures under `python-agent-service/tests/fixtures/soc_alert/` (or adjacent) — **synthetic/sanitized** only.
- A-09: If Supabase unavailable locally, allow **in-memory fallback** only if explicitly documented in `design.md` **and** acceptance sign-off notes the waiver.

## Sign-off

| ID | Result | Verifier | Date | Notes |
|----|--------|----------|------|-------|
| A-01 | | | | |
| A-02 | | | | |
| A-03 | | | | |
| A-04 | | | | |
| A-05 | | | | |
| A-06 | | | | |
| A-07 | | | | |
| A-08 | | | | |
| A-09 | | | | |
| A-10 | | | | |
| A-11 | | | | |
| A-12 | | | | |
| A-13 | | | | |
| N-01 | | | | |
| N-02 | | | | |
