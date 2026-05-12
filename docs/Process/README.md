# Process documentation layout

Per-delivery work is stored under **`docs/Process/<requirement-slug>/`** (kebab-case slug, similar to OpenSpec change names).

| File | Purpose |
|------|---------|
| `proposal.md` | Requirements, scope, non-goals, stakeholders, success signals. |
| `design.md` | **Implementation-grade** design: must be **more detailed than Cursor Plan’s default plan text** — diagrams, flows, pseudocode, **files/paths**, contracts, edge cases, rollout/order, rationale, UI breakdown. **Phase 4 todos** live in an early **`## Todo list`** section as **`- [ ]` / `- [x]`** (GFM task list) for readable preview; optional YAML frontmatter may include **`name`** / **`overview`** only — see **`delivery-pipeline`** skill. |
| `acceptance.md` | **Backend / API / non-UI** acceptance — **criteria from the user** in Plan (dialogue + edits); see `_templates/ACCEPTANCE_SPEC.md`. |
| `acceptance-ui.md` | **Frontend / UI** acceptance — **criteria from the user** in Plan; see `_templates/ACCEPTANCE_UI_SPEC.md`. |
| `mockups/` | **User-copied** reference screenshots (png/jpg/webp/pdf). Agents **do not** generate these; they only check presence or record an explicit **skip**. |
| `tasks.md` | Optional implementation checklist (if the team uses it). |

Shared templates live in **`docs/Process/_templates/`**.

**`/design-review` test target:** copy **`.cursor/design-review-handoff/target.example.yaml`** → **`target.local.yaml`** (gitignored — **not committed, not shipped**). Put **`base_url`** / paths there only; **account secrets** go in **repo root `.env`** (`E2E_*` for **`npm run auth:bootstrap`**). See **`.cursor/design-review-handoff/README.md`**. **Mockup images** live under **`docs/Process/<slug>/mockups/`**.

### Plan phase: files must land before build

`proposal.md`, `design.md`, and **`acceptance.md` / `acceptance-ui.md`** (content **provided by the user** in Plan, agent may structure) must be settled **during Plan**. **Mockups:** user **copies files** into **`mockups/`**; if none, user may **skip once** after a single prompt (document deferral). **Sign-off** rows are filled **after** implementation.

See **`.cursor/skills/delivery-pipeline/SKILL.md`** (section **“Plan vs Agent — where files must appear”**).
