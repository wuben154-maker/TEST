# Process documentation layout

Per-delivery work is stored under **`docs/Process/<requirement-slug>/`** (kebab-case slug, similar to OpenSpec change names).

| File | Purpose |
|------|---------|
| `proposal.md` | Requirements, scope, non-goals, stakeholders, success signals. |
| `design.md` | Detailed design: diagrams, flows, pseudocode, **files/paths to change**, risks. |
| `acceptance.md` | **Backend / API / non-UI** acceptance (see `_templates/ACCEPTANCE_SPEC.md`). |
| `acceptance-ui.md` | **Frontend / UI** acceptance checklist (see `_templates/ACCEPTANCE_UI_SPEC.md`). |
| `mockups/` | **UI reference screenshots** (png/jpg/webp/pdf) for this requirement. |
| `tasks.md` | Optional implementation checklist (if the team uses it). |

Shared templates live in **`docs/Process/_templates/`**.

**`/design-review`:** template **`target.example.yaml`** → local **`target.local.yaml`** (gitignored, **test-only, not published**). **Secrets** in root **`.env`**, not duplicated in YAML — see **`.cursor/design-review-handoff/README.md`**. **Mockup images** under **`docs/Process/<slug>/mockups/`**.
