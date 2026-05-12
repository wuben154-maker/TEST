# Delivery pipeline — Appendix

Reference material for **SKILL.md v4.0**. The agent reads sections on demand (e.g. `→ see SKILL_APPENDIX.md §C`); not required for every session.

---

## §A — Cursor Plan mode limitations

### Official Cursor plan file vs `docs/Process/`

| Location | Who writes | What it is |
|----------|------------|------------|
| `%USERPROFILE%\.cursor\plans\*.plan.md` | Cursor Plan mode (built-in) | Plan UI artifact: YAML `todos`, overview. **Not** under `docs/Process/`. |
| `docs/Process/<slug>/proposal.md`, `design.md`, … | Agent + Write tool (or user manually) | delivery-pipeline Phase 2 on-disk source of truth. |

Cursor persists the Plan conversation into `~/.cursor/plans/` (or `<repo>/.cursor/plans/` with "Save to workspace"). It does **not** expand that into `proposal.md` / `design.md` — that step is this workflow's job.

The repo **cannot** force "Plan mode = write files to disk." That is a Cursor product decision.

### Practical equivalents (planning + files before Agent build)

1. **`/process-plan-docs`** from Agent — same planning depth as Plan mode but files land under `docs/Process/`. No `src/` edits.
2. **Save official plan** to workspace → `<repo>/.cursor/plans/`. Still not `docs/Process/` until you copy or run option 1.
3. **After Plan only** — Agent: "Materialize `~/.cursor/plans/<file>.plan.md` into `docs/Process/<slug>/` with Write."

---

## §B — Why Phase 2 files did not appear

Using `delivery-pipeline` (or any Skill) **does not run a script** — it adds instructions for the model. Files appear only when the model calls **Write**.

**Common causes:**

1. **Cursor Plan mode** — The UI often only updates the Plan panel / `.plan.md` bubble. Filesystem Write may be unavailable.
2. **Ask / read-only chat** — No Write tool → no files.
3. **Model summarized in chat** — Even in Agent mode, without explicit "persist with tools" instruction, the model may only reply with markdown.

**Recovery (pick one):**

1. Run **`/process-plan-docs`** from Agent with `<slug>`.
2. Direct instruction: "Create `docs/Process/<slug>/proposal.md` and `design.md` using Write; follow delivery-pipeline Phase 2."
3. Copy content from Plan panel into files manually.

### If Cursor Plan UI only updates the plan bubble

Treat as expected (see above). Recovery: run `/process-plan-docs` or doc-only Agent chat.

---

## §C — design.md Path A: plan traceability styles

When a Cursor `*.plan.md` exists, `design.md` references it via one of two styles.

### Style 1 — `## Source plan (traceability)` (default)

1. After `## Metadata`, add `## Source plan (traceability)`.
2. Include: **path** to plan file; **1–3 sentences** of plan intent; explicit line: "`design.md` is the implementation source of truth."
3. **Merge** every substantive requirement from the plan into the body sections **once** (scope, architecture, contracts, touch list). Do **not** paste the full plan then duplicate sections as "expansion."
4. Then `## Todo list` and all required sections — single instance of each heading.

### Style 2 — `## Cursor plan (archived)` (verbatim; user/audit request only)

1. After `## Metadata`, add `## Cursor plan (archived)`.
2. Paste the **complete** plan markdown body (below YAML frontmatter). Optionally `### Plan YAML frontmatter` in a fenced `yaml` block.
3. Then `## Todo list` and expansion. **Dedupe**: if this creates duplicate headings vs the plan, fold into one section each.

If multiple plan files exist, use the one the user declares canonical (or latest by date).

### Path B — No plan file

Author `design.md` greenfield to the same depth standard. No `## Source plan (traceability)` or archive section (unless citing an informal doc).

---

## §D — Why GFM task lists instead of YAML todos

Cursor's Plan files use YAML `todos:` because the Plan UI parses that format. Repo `design.md` is read primarily as **Markdown**; YAML-only todos in frontmatter render as raw text in most previews.

Therefore `design.md` uses `## Todo list` with `- [ ]` / `- [x]` (GFM task lists) — visible in any editor/preview. Optional `design.md` frontmatter: `name`, `overview`, `isProject` only. Do **not** add `todos:` to `design.md` frontmatter.

---

## §E — Phase 7 gate decision tree

```
Is outcome DONE or DONE_WITH_CONCERNS?
├─ No → manual path (§7.3)
└─ Yes
   ├─ Did all Phase 5 test commands exit 0?
   │  ├─ No → manual path
   │  └─ Yes
   │     ├─ Does acceptance-ui.md exist?
   │     │  ├─ No (backend-only) → /qa = N/A, /design-review = N/A → check secrets gate
   │     │  └─ Yes
   │     │     ├─ Were Playwright MCP browser_* tools invocable?
   │     │     │  ├─ No → manual path (MCP unavailable)
   │     │     │  └─ Yes
   │     │     │     ├─ /qa ran and passed? No → manual path
   │     │     │     └─ Yes
   │     │     │        ├─ target.local.yaml exists?
   │     │     │        │  ├─ No → manual path
   │     │     │        │  └─ Yes → /design-review ran and passed (or explicit waiver)?
   │     │     │        │     ├─ No → manual path
   │     │     │        │     └─ Yes → check secrets gate
   │     │     │        └─ (fallthrough)
   │     └─ Sign-off rows have evidence?
   │        ├─ No → manual path
   │        └─ Yes → check secrets gate
   └─ Secrets gate: any .env / *.pem / chrome-debug-profile staged?
      ├─ Yes → manual path (unstage first)
      └─ No → ✅ AUTO-COMMIT + TAG
```

---

## §F — Relation to OpenSpec

OpenSpec CLI is **not** part of this pipeline. Repository folders under `openspec/changes/` may coexist for history; this workflow does not require them for new work.

---

## §G — Acceptance artifacts lifecycle

### Acceptance criteria — user-owned in Plan

- **Source of truth:** The user supplies acceptance standards in Plan, via conversation (agent asks, user answers) and/or by editing `acceptance.md` / `acceptance-ui.md` directly in the IDE.
- **Agent role:** Structure and transcribe what the user said (ids, tables, links to `design.md`). Do not invent major criteria the user never agreed to.
- If the user writes acceptance files alone, only check format against `ACCEPTANCE_SPEC.md` / `ACCEPTANCE_UI_SPEC.md` and suggest fixes.

### Mockups — user-provided files only

- Never generate mockup images (no AI image tools, no placeholder PNGs).
- The user copies screenshots/wireframes into `docs/Process/<slug>/mockups/`.
- Agent ensures `mockups/` dir exists; checks for `*.png|jpg|jpeg|webp|pdf`. If none:
  1. Ask **once**: explain path; offer A) user adds files now (pause) B) skip mockups (record `## Mockups deferred` with user confirmation).
  2. Do not re-ask in a loop. Respect skip.
- If mockups skipped, Phase 6 `/design-review` relies on `acceptance-ui.md` + live URL only.

### Artifact timing

| Artifact | Phase |
|----------|-------|
| `proposal.md`, `design.md` | Phase 2 — agent writes; user edits. |
| `acceptance.md` / `acceptance-ui.md` | Phase 2 — content from user; agent structures. |
| `mockups/*` | Phase 2 — user copies files; agent verifies or documents skip. |
| Sign-off tables | Phase 6 — after verification. |

---

## §H — SecManus auth bootstrap details

For local E2E/QA with logged-in UI, run `npm run auth:bootstrap` from repo root:

1. Requires Python API running (e.g. `uvicorn` on port 8000).
2. Credentials in repo root `.env` / `.env.local`: `E2E_EMAIL`, `E2E_PASSWORD` (aliases: `LOCAL_AUTH_EMAIL` / `LOCAL_AUTH_PASSWORD`).
3. Optional: `E2E_API_BASE` (default `http://127.0.0.1:8000`), `LOCAL_AUTH_FRONTEND_URL` (default `http://127.0.0.1:8080`).
4. Stdout = URL with `#__secmanus_bootstrap=...`. In Playwright MCP, `browser_navigate` to that URL **once** — seeds `localStorage`, reloads.
5. DEV only (`import.meta.env.DEV`); production builds ignore the hash.

Full docs: `docs/Process/LOCAL_AUTOMATION_AUTH.md`.
