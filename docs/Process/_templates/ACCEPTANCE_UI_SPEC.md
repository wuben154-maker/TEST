# UI acceptance document specification

This document defines how to write **`acceptance-ui.md`** alongside **`proposal.md`** and **`design.md`** under `docs/Process/<requirement-slug>/`. It mirrors the structure spirit of **`ACCEPTANCE_SPEC.md`** (backend) but targets **visual, interaction, and responsive** verification.

## Purpose

`acceptance-ui.md` is the **checklist source** for human or agent sign-off **before** considering UI work done, together with **`/design-review`** and reference images under **`mockups/`**.

**Lifecycle:** **`acceptance-ui.md`** content is **user-provided** in **Plan** (dialogue and/or edits); agent structures text. **`mockups/`** files are **copied in by the user** — agents do not generate images; if the user skips mockups, document deferral once. **Sign-off** only **after** verification (**`delivery-pipeline`** Phase 6).

## Reference screenshots

- Store files under **`docs/Process/<requirement-slug>/mockups/`** (committed to the repo unless the team decides otherwise).
- Supported: `.png`, `.jpg`, `.jpeg`, `.webp`, `.pdf`.
- Name files clearly (e.g. `01-home-desktop.png`, `02-home-mobile.png`).

## Required sections

1. **Metadata** — Slug (must match folder name), links to `proposal.md` / `design.md`, last updated.
2. **Scope** — Which screens, routes, or components this acceptance covers (map to `design.md` headings).
3. **Reference assets** — Table listing each mockup file (path relative to repo root) and what it represents.
4. **Visual criteria** — Numbered items (prefix **`U-01`**, **`U-02`**, …): layout, hierarchy, spacing, typography, states tied to **observable** checks (e.g. “primary CTA visible above fold at 1440px”).
5. **Interaction criteria** — Prefix **`I-01`**, …: hover/focus, keyboard, errors, loading, empty states.
6. **Responsive** — Breakpoints to verify (e.g. 375 / 768 / 1024) and what must hold at each.
7. **Accessibility** — Contrast, focus order, touch targets (reference WCAG level the team targets).
8. **Sign-off** — Table: id | pass/fail | verifier | date | notes.

## Rules

- **Stable ids** — Use `U-` / `I-` prefixes so PRs and `/design-review` findings can reference them.
- **No secrets** — Never put credentials in `acceptance-ui.md`.
- **Traceability** — Each criterion should map to text in `design.md` or `proposal.md`.
- **Live URL** — Copy **`target.example.yaml`** → **`target.local.yaml`** (gitignored; **local test only**, not shipped). **`base_url`** / paths only; **login secrets** in repo **`.env`** + **`npm run auth:bootstrap`** — see **`.cursor/design-review-handoff/README.md`**. Do not put credentials in `acceptance-ui.md`.

## When mandatory

For any delivery with **user-visible UI changes**, **`acceptance-ui.md`** is **required** before Agent-mode implementation. **`mockups/`** is **recommended**; if the user **opts out** after one prompt, record **`## Mockups deferred`** and proceed without reference images.
