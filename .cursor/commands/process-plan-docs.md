---
name: /process-plan-docs
id: process-plan-docs
category: Workflow
description: Doc-only Agent — write proposal + design under docs/Process/<slug> before implementation (write-enabled Phase 2)
---

**Goal:** Persist Phase 2 docs under **`docs/Process/<slug>/`** before Agent build. Follows **`delivery-pipeline` v4.0 — Phase 2** and its **Golden rules** (GR-ACC, GR-MOCK, GR-SIGNOFF).

**Important:** Plan mode alone often does not write files to disk. This command is meant for **Agent** (or any chat with Write tool access). See **`SKILL_APPENDIX.md §B`** if files did not appear.

**Scope (strict):**

- **ALLOWED:** Create/edit only under **`docs/Process/<slug>/`**. No application source changes.
- **FORBIDDEN:** Generating mockup images. No dependency installs, no feature implementation.

**Steps:**

1. Confirm **`<slug>`** (kebab-case).
2. Ensure **`docs/Process/<slug>/`** exists.
3. **Write `proposal.md`** and **`design.md`** per **`delivery-pipeline` v4.0 — Phase 2** (design.md sections, plan traceability Path A/B per **`SKILL_APPENDIX.md §C`**).
4. **Acceptance** — per **GR-ACC**: ask user for criteria (or read their pre-edits); structure into `acceptance.md` / `acceptance-ui.md` using `_templates/` specs. Leave Sign-off for Phase 6.
5. **Mockups** — per **GR-MOCK**: ensure `mockups/` exists; check for images; ask once if empty; skip = `## Mockups deferred`.
6. Tell user they may edit any file directly; when ready → Agent implementation.

If Plan mode cannot write files, run from normal/Agent chat.
