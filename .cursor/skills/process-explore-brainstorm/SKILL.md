---
name: process-explore-brainstorm
description: >
  Structured brainstorming during requirements exploration (Cursor Ask mode). Use when the user
  wants ideation, alternatives, risks, or "think wider" before locking scope — alone or alongside
  delivery-pipeline Phase 1.
license: MIT
compatibility: Best used in Cursor Ask mode; read-only on the codebase unless user asks to inspect.
metadata:
  author: secmanus-workspace
  version: "1.0"
---

# Explore-phase brainstorming companion

**Do not write production code** in this skill unless the user explicitly asks for examples. Prefer questions, options, and structured notes they can paste into `docs/Process/<slug>/proposal.md` later.

## When to apply

User signals: 头脑风暴、多方案、有没有更好的、风险、边界、竞品式对比、要不要做、MVP 范围等。

## Method (pick 2–4 per session)

1. **Problem reframing** — Restate goal as user outcome + constraint + success metric (one paragraph each).
2. **Option tree** — At least 3 approaches: trade-offs (cost, time, risk, maintainability).
3. **Pre-mortem** — "It failed in production because…" (list 5 causes, then mitigations).
4. **HMW** — "How might we…" questions for the top 2 gaps.
5. **Non-goals** — Explicitly list what this delivery will **not** do (prevents scope creep).
6. **Dependency map** — Who/what must exist first (teams, data, flags, migrations).

## Output shape

End with a short **Exploration summary** block the user can copy:

```markdown
## Exploration summary (brainstorm)
- Problem (user-outcome framing):
- Options considered:
- Recommended direction (with caveat):
- Non-goals:
- Open questions for Plan mode:
```

## Handoff

Remind the user: after exploration is **human-approved**, switch to **Plan mode** and create `docs/Process/<kebab-slug>/proposal.md` + `design.md` per **`delivery-pipeline`** skill.
