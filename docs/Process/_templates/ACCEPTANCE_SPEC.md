# Acceptance document specification

This document defines how to write **`acceptance.md`** alongside **`proposal.md`** and **`design.md`** under `docs/Process/<requirement-slug>/`.

## Purpose

`acceptance.md` is the **single source of truth** for **non-UI** verification: APIs, jobs, data contracts, performance budgets, security checks, and observability. It complements automated tests and is used after implementation for a **manual or scripted sign-off**.

**Lifecycle:** Criterion **content** is **user-provided** in **Plan** (conversation and/or direct file edits); the agent may **structure** into tables. Complete **Sign-off** only **after** build and verification (**`delivery-pipeline`** Phase 6).

## Required sections

1. **Metadata** — Slug (must match folder name), owner, last updated date, related `proposal.md` / `design.md` links.
2. **Scope reference** — Bullet list pointing to which parts of `design.md` this acceptance covers.
3. **Environment** — Where verification runs (local compose, staging URL, feature flags).
4. **Functional criteria** — Numbered, **testable** statements (Given / When / Then or checklist). Each item MUST be objectively verifiable (command, HTTP response, DB state, log line).
5. **Non-functional criteria** — Latency, error rate, payload limits, idempotency, authn/z as applicable.
6. **Evidence** — For each criterion id (e.g. `A-01`), specify what constitutes pass: command, expected output shape, or screenshot of logs (no secrets).
7. **Sign-off** — Table: criterion id | pass/fail | verifier | date | notes.

## Rules

- **No vague wording** — Replace “should be fast” with “p95 under 200ms under load X”.
- **Stable ids** — Use stable prefixes (`A-01`, `N-01`) so regressions can reference them in PRs.
- **Traceability** — Each criterion should map to a sentence or section in `design.md` or `proposal.md`.
- **Secrets** — Never store credentials in `acceptance.md`; reference env vars or secret stores.

## When `acceptance.md` is mandatory

For deliveries that **do not** go through `/design-review`, **`acceptance.md` is required** before Agent-mode implementation begins, and must be **re-verified** after `/qa` (or equivalent) completes.

For **user-visible UI** work, use **`acceptance-ui.md`** per **`ACCEPTANCE_UI_SPEC.md`**; **`mockups/`** is user-provided or explicitly skipped. Keep **`acceptance.md`** for API/data contracts the UI depends on (optional but recommended when backends change).
