# Proposal — history-sidebar-persistent

## Problem

The history projects UI used a full-height slide-over drawer with a different visual language than the reference workspace HTML (warm dark tokens, 240px persistent rail, dot + single-line project rows, collapsible narrow strip on desktop).

## Goals

- Dock the project sidebar as a **persistent** column on `md+` (240px expanded, 48px collapsed).
- Align list rows with the reference: **status dot + project title** (ellipsis), hover/active surfaces matching the mock.
- Keep **mobile** as an overlay drawer with scrim.
- Persist desktop collapsed preference in `localStorage`.
- Top bar menu: **toggle collapse** on desktop, **toggle drawer** on mobile.

## Non-goals

- Moving the top header inside the main column only (HTML mock layout); navbar remains full-width above the content row.
- Backend/API changes.

## Success

Users see a stable left rail for projects on desktop; shield/menu behavior matches breakpoint expectations; automated tests pass.
