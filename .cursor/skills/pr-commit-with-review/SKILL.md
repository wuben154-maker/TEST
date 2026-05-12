---
name: pr-commit-with-review
description: |
  Cursor **`review`** gate → **commit on local `<head>`** → **`git push` to `origin/<head>`** → **`gh pr create --base <pr-base>`** (English PR body). Push-only if user says so.
  Does **not** invoke `~/.claude/skills/review` (`/review`).
  Use for "pr-commit-with-review", "commit after review", PR to **<pr-base>**.
---

# PR commit (review gate)

**End state (default):** after review → **commit on the current local branch** → **push to `origin` with the same branch name** → **open (or update) a PR targeting `<pr-base>`**.

Before creating **PR-bound commits**, complete one **code review** round using the **Cursor Command `review`** rules below. **Do not** run the external **`/review`** skill (`~/.claude/skills/review`) or its checklist—this workflow is **Cursor-review-only** until you change this file.

This skill covers **commit / push / open PR** only—not full release automation (version bump, CHANGELOG, heavy `/ship` steps). For that, use **`/ship`** or your team's ship flow.

**Language policy:** This skill is written in English. **PR title, PR body, and `body.md` MUST be English only** (no Chinese or mixed-language strings in those artifacts). Commit messages stay English. If the user supplies context in another language, translate into English for the PR.

---

## Project configuration

**Single source of truth:** `.cursor/project-config.md` — edit `PR_BASE` there; do **not** add a local copy here.

The agent reads `PR_BASE` from `.cursor/project-config.md § Git Workflow` at Step 0 and uses it everywhere `<pr-base>` appears.

**Runtime override:** If the user invokes the skill with an explicit base branch (e.g. "pr to main", "base branch is release/v2"), that value **overrides `PR_BASE` for this run only** — no file is modified.

---

## Golden rules

| Rule | Detail |
|------|--------|
| **Review before commit** | Do not `git commit` until Cursor-style review is done and every **Critical** item is resolved or explicitly **Accepted risk** by the user. |
| **No secrets / junk** | Never stage `.env`, `*.pem`, keys, `**/.vscode/chrome-debug-profile/**`, etc. Align with **delivery-pipeline GR-SECRETS** and **`AGENT.md`**. |
| **Explicit staging** | Use `git add <path>…`; avoid blind `git add -A`. Always `git diff --cached` before commit. |
| **No surprise force-push** | Do not `git push --force` unless the user **explicitly** asks. |
| **Review vs. edits** | Follow **Cursor Command `review`**: findings first, by severity; **do not change code** unless the user **explicitly** asks you to apply fixes. |
| **English PR** | **PR title and body: English only.** |
| **Review diff ref** | Prefer **`origin/<head>`**. If it does not exist yet, fall back to **`origin/<pr-base>`**. |
| **PR merge base** | **Always `<pr-base>`** for **`gh pr create --base`** (this repo's integration branch). Push targets **`origin/<head>`** only—never push "into" `<pr-base>` via this skill except by **merging the PR** on the forge. |

---

## Step 0 — Preflight

1. `git branch --show-current` → record as **`<head>`** (must not be empty; detached HEAD → stop and ask).
2. **`git fetch origin --quiet`** when network is available.
3. Resolve **`<pr-base>`**:
   - If the user supplied an explicit base branch in this invocation → use that value.
   - Else → read **`PR_BASE`** from **`.cursor/project-config.md § Git Workflow`**.
   - After fetch, if **`origin/<pr-base>`** does not resolve → **STOP** and tell the user to fix remote/fetch or update `PR_BASE` (PR cannot target a missing branch).
4. Resolve **`<review-ref>`** for Step 1:
   - If `git rev-parse --verify "origin/<head>" >/dev/null 2>&1` → **`<review-ref> = origin/<head>`**;
   - Else (first push of this branch) → **`<review-ref> = origin/<pr-base>`**.
5. Print **`<head>`**, **`<pr-base>`** (and its source: file config or runtime override), and **`<review-ref>`** in the session log.
6. If **`<head>`** equals **`<pr-base>`** (or another known shared integration branch) and the work is not an intentional direct commit there, warn the user: feature work should use a **feature branch**; **stop** unless the user confirms.
7. `git status`; `git diff` / `git diff --cached` — confirm there is work to commit or staged changes (or a clean tree after e.g. delivery-pipeline Phase 7 before push-only steps).

---

## Step 1 — Review gate (blocking)

**Do not run a new `git commit` until this step completes.**

### Cursor Command `review` (authoritative)

Perform the review pass **exactly** in this spirit (project Cursor Command **`review`**):

> Review the relevant code with a code review mindset. **Prioritize bugs, behavioral regressions, security issues, and missing tests.** **Findings must be the primary focus, ordered by severity.** **Do not make code changes unless the user explicitly asks for them.**

**Inputs:**

- **Primary diff for review:** **`git diff <review-ref>`** — local tree vs **`origin/<head>`** when it exists, else vs **`origin/<pr-base>`** (same delta basis as a new branch off integration).
- Optionally add one line: **`git diff --stat origin/<pr-base>...HEAD`** (what the PR will contain vs `<pr-base>`; informational).
- Read enough surrounding context to judge regressions and security (open changed files when diff hunks are unclear).

**Output:**

- A **severity-ordered** findings list (e.g. Critical / High / Medium / Low). Each item: **what**, **where** (file:line or region), **why it matters**, **suggested fix** (optional, still no edits unless asked).
- Stay concise; no narrative filler.

### Gate policy

- Map the top findings to **Critical / High** vs **Medium / Low** consistently. **Block** Step 2 if **Critical** issues remain **unresolved** and the user has not explicitly **Accepted risk** (short English rationale you can paste into the PR template).
- **High**: strongly recommend fix or documented acceptance before commit; if the user insists, note it in the review summary and in **Pre-merge review** on the PR body.
- **Medium / Low**: may proceed to commit if the user accepts; **list** them in the agent output and in **Residual risk / follow-ups** on the PR body when applicable.

### Gate exit

Give a short **Review summary**:

- `Critical: N` (must be 0 or **Accepted risk** with rationale)
- `High / Medium / Low: …` (counts or one line each)
- One line: **clear to commit?** yes/no + reason

---

## Step 2 — Stage and self-check

1. `git add` only paths **clearly in scope** for this PR.
2. `git diff --cached` — confirm no secrets or accidental large/binary junk.
3. If the index is **empty**, stop and explain.

---

## Step 3 — Commit

1. **Messages:** Conventional Commits in English: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`.
2. **Single theme:** One PR should express **one clear intent**; if the diff is broad, split commits (bisect-friendly) or split branches/PRs (confirm with the user).
3. Run:

```bash
git commit -m "feat(scope): short imperative summary"
```

4. For **multiple commits**: repeat `git add` + `git commit` per logical chunk.

---

## Step 4 — Push

```bash
git push -u origin "$(git branch --show-current)"
```

If push fails: `git fetch`, then **rebase or merge `<pr-base>` (or `origin/<pr-base>`)** per team practice—**no** unrequested force-push.

---

## Required PR body template (English only)

When opening a PR, **`gh pr create --body`** MUST be filled from this template—**no one-liner stubs**. The agent fills it from the diff, review outcome, and `docs/Process/<slug>/` if present. For missing items use **`N/A`** plus one short English sentence.

**PR title (align with Summary):** `feat|fix|refactor|docs|test|chore(scope): short English summary`

**PR body — all headings and bullet text in English:**

```markdown
## Summary
- **What:** One or two sentences on the user- or system-visible change.
- **Why:** Motivation, context, or link to issue / requirement.

## Scope
- **In scope:** What this PR includes (modules / behavior).
- **Out of scope:** What is intentionally excluded (avoid reviewer false negatives).

## Implementation notes (optional)
- Key design trade-offs, contract changes, config keys, migration notes; or `N/A`.

## Pre-merge review
- **Review date:** YYYY-MM-DD (UTC if relevant)
- **Gate result:** Critical open issues: 0 (or: **Accepted risk** — list items and rationale)
- **Residual risk / follow-ups:** Non-critical findings deferred to later PRs; or `None`

## How to review
- **Start here:** `path/one`, `path/two` (3–5 paths max)
- **Risk areas:** Auth, concurrency, LLM trust boundaries, migrations, etc.; or `None`

## Test plan
- [ ] Unit / integration: (command or scope)
- [ ] Manual / E2E: (steps or `N/A`)
- [ ] Regression: (critical paths touched by this change)

## Docs & design
- **DESIGN.md / design standards:** Updated? (UI changes usually **yes**); cite sync or waiver in English.
- **Process docs:** `docs/Process/...` updated; or `N/A`.
```

**Optional:** If `.github/pull_request_template.md` exists, **merge** these sections into it without duplicating headings.

**Hard rule:** Do not paste Chinese (or bilingual) content into the PR title or body. Translate user-provided Chinese intent into clear English for the template.

---

## PR destination (remote + branches, not a repo subpath)

A **pull request is not stored under a project directory**. `gh pr create` opens a PR on the **git forge** for **`origin`** (e.g. GitHub). Targets are:

| Part | Meaning |
|------|---------|
| **Base (`<pr-base>`)** | Value from **Project configuration** (`PR_BASE`) or runtime override — passed as `gh pr create --base <pr-base>`. |
| **Head** | **`origin/<head>`** after **Step 4** (same name as your local branch on `origin`). |
| **Review compare** | **`<review-ref>`**: **`origin/<head>`** if present, else **`origin/<pr-base>`**. |

So there is **no filesystem folder path** for "where the PR lives"; only **remote**, **`<pr-base>`**, and **`<head>`**.

---

## Step 5 — Open PR

**Default:** after **Step 4** succeeds, open a PR **into `<pr-base>`** when `gh` is available. **Skip** this step only if the user explicitly asked **push-only** (no PR).

1. If **`gh pr view`** succeeds for the current branch: the PR already exists → refresh description if needed: `gh pr edit <number> --body-file /path/to/body.md` (do **not** change base unless the user asks).
2. Else **create**:
   - Fill **§ Required PR body template** (English only) to a **temp file** (e.g. `%TEMP%\pr-body-<head>.md` on Windows, or `mktemp` on Unix); do **not** stage it.
   - Run:

```bash
gh pr create --base <pr-base> --title "<type>(<scope>): <summary>" --body-file /path/to/body.md
```

   - **Base must be `<pr-base>`** (resolved in Step 0) for new PRs in this workflow.

---

## Split vs. `/ship`

| Need | This skill | `/ship` |
|------|------------|---------|
| Review gate before commit | Yes | Yes (heavier pre-landing bundle) |
| Commit + push + lean PR (English body) | Yes | May be too heavy |
| VERSION / CHANGELOG / document-release / metrics | No | Yes |

---

## Integration: `delivery-pipeline` Phase 8

When this skill runs **after** **delivery-pipeline** **Phase 7** (local `delivery(<slug>)` commit + tag already exists):

1. Run **Step 1 (review)** on **`git diff <review-ref>`** (typically **`origin/<head>`**; else **`origin/<pr-base>`**).
2. **Skip Step 3 (commit)** if the working tree is clean; Phase 7 already recorded the checkpoint.
3. If post-review fixes are needed → commit them, then **push** (Step 4); **Step 5** opens or updates PR **into `<pr-base>`** unless user said push-only.

If your repo's `delivery-pipeline` **SKILL.md** does not list **Phase 8** yet, treat this section as the publish appendix anyway.

---

## Completion

End with **one sentence**: whether review cleared the gate, commit SHA (if any), pushed or not, PR URL (if any).
