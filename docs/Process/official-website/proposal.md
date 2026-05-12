# Proposal — Official marketing home (`official-website`)

## Metadata

- **Slug:** `official-website`
- **Date:** 2026-05-06
- **Related:** [`design.md`](./design.md), [`acceptance.md`](./acceptance.md), [`acceptance-ui.md`](./acceptance-ui.md)

## Problem

The SPA currently lands logged-in users on the full workspace (`Index` at `/`). There is no public marketing entry that matches the approved static reference. Login and logout destinations are not aligned with a dedicated public home.

## Goals

1. Rebuild the **public marketing homepage** in the React/Vite app, using the visual and information structure of the user-provided static reference HTML (same sections: header/nav, hero with chat composer affordance, features grid, workflow narrative, footer).
2. **Internationalize marketing copy** using the existing app-wide i18n (`LanguageProvider`, locales `en` / `zh` / `ja` / `ko`): same meanings as English, **`t.marketing`** namespace; no separate product-scope change beyond translation and wiring keys.
3. Make **`/`** the **default application entry** (public): first paint is the marketing page, not the workspace shell.
4. All primary **login / sign-in** entry points on that page **`Link` to `/auth`** (existing `Auth` screen).
5. On **logout**, navigate to **`/`** (marketing home), replacing the previous `navigate("/auth")`.

## Non-goals

- Implement separate `pricing.html` / `terms.html` / `privacy.html` / `signup.html` serverside or full legal pages unless content is supplied (stub / placeholder / single combined policy page can be deferred; see design).
- Wire hero composer to authenticated streaming (beyond “continue to `/auth`”); post-login continues to **`/start`** as today unless product asks otherwise.
- Duplicate Google Fonts offline bundling unless required by policy (reference uses DM Sans CDN).

## Users

- Anonymous visitors discovering the product.
- Returning users signing in via obvious CTAs.

## Dependencies

- `react-router-dom` route table in `src/App.tsx`.
- `AuthProvider` / `signOut` in `src/contexts/AuthContext.tsx`.
- `AppWorkspaceShell` auth gate (logged-out users already redirect to `/auth` from workspace routes).

## Success metrics (qualitative)

- Visual parity **good enough for ship** versus reference (within component/Tailwind tokens; no verbatim 2000-line inline CSS paste).
- Visiting `/` never mounts `AppWorkspaceShell` without navigation to a protected route.

## Reference asset (informal)

- User path: `C:/Users/chenf/Downloads/5-6官网/5-6官网/index.backup.5.Stop Manual Work. Start Security Agent.2.html` (not in repo). **Mockups:** deferred; see `acceptance-ui.md`.
