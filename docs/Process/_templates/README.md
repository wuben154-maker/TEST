# Process templates

- **`design.example.md`** — Skeleton for `docs/Process/<slug>/design.md` with optional frontmatter + **`## Todo list`** (GFM **`- [ ]`** checklist).
- **`ACCEPTANCE_SPEC.md`** — Rules for writing `acceptance.md` (backend / API / non-UI).
- **`acceptance.example.md`** — Copy to `docs/Process/<slug>/acceptance.md`.
- **`ACCEPTANCE_UI_SPEC.md`** — Rules for writing `acceptance-ui.md` (frontend / UI).
- **`acceptance-ui.example.md`** — Copy to `docs/Process/<slug>/acceptance-ui.md`.

When starting a new requirement folder, copy sections from the examples as needed; do not commit secrets or production credentials into any file under `docs/Process/`.

**UI reference screenshots:** put files under **`docs/Process/<slug>/mockups/`** (see `ACCEPTANCE_UI_SPEC.md`).
