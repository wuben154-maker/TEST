---
name: /workflow-delivery-pipeline
id: workflow-delivery-pipeline
category: Workflow
description: Ask → Plan (docs/Process/<slug>) → Agent (AGENT.md) → TDD → /qa (+ acceptance-ui/mockups + /design-review, or acceptance.md)
---

Run the **`delivery-pipeline`** skill (`.cursor/skills/delivery-pipeline/SKILL.md` v4.0).

**Quick flow:** Ask → Plan (persist `proposal.md`, `design.md`, `acceptance*.md` under `docs/Process/<slug>/`) → Agent (implement + TDD) → Phase 5–6 (tests + `/qa` + `/design-review`) → Phase 7 (auto-commit if all gates pass).

**Phase 2 on disk:** Cursor Plan UI alone often does **not** write `docs/Process/`. Use **Agent** + **`/process-plan-docs`** with `<slug>` to persist files.

**Golden rules:** GR-ACC (acceptance = user-owned), GR-MOCK (no AI mockups), GR-MCP (Playwright MCP mandatory when invocable), GR-SIGNOFF (sign-off = Phase 6 only), GR-SECRETS (never stage secrets).

**Gates (Phase 3):** UI → `acceptance-ui.md` + `mockups/` (or documented skip) + `target.local.yaml`. Backend → `acceptance.md`.

**Cap:** ≤ 5 remediation rounds in Phase 6.

**Phase 7 (v4.0):** If Phase 5–6 auto-commit gates all pass → auto `git commit` + `passed/<slug>-…` tag. Otherwise → manual commit per `AGENT.md` checkpoint rules.
