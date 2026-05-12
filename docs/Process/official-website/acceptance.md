# Acceptance — Official marketing home (non-UI)

## Metadata

- **Slug:** `official-website`
- **Last updated:** 2026-05-06
- **Related:** [`proposal.md`](./proposal.md), [`design.md`](./design.md)

## Scope reference

- Routing: public `/` vs workspace `/start`
- `AuthContext.signOut` navigation target
- No backend API schema changes expected

## Environment

- Local Vite dev + existing Python/API as usual for auth.

## Functional criteria

| ID | Given / When / Then |
|----|---------------------|
| **A-01** | Given the user is logged out, when they open `/`, then the response renders the marketing page **without** requiring auth API success for workspace bootstrap (no redirect to `/auth`). |
| **A-02** | Given the user is logged out, when they open `/start`, then the app redirects to `/auth` (existing shell guard unchanged). |
| **A-03** | Given the user is logged in, when they invoke **Sign out** from workspace chrome, then after logout completes the browser URL is **`/`** (marketing home). |
| **A-04** | Given successful email login or register, when auth completes, then navigation still lands on **`/start`** (workspace) as before. |

## Non-functional criteria

| ID | Requirement |
|----|-------------|
| **N-01** | No secrets or tokens in marketing static HTML/JS beyond normal app bundle. |

## Evidence

| ID | Pass evidence |
|----|----------------|
| **A-01** | Manual or E2E: `GET /` while logged out shows marketing; DevTools: no forced navigation to `/auth`. |
| **A-02** | Manual: visit `/start` logged out → `/auth`. |
| **A-03** | Manual: from `/start`, sign out → pathname `/`. |
| **A-04** | Manual: complete login on `/auth` → pathname `/start`. |

## Sign-off

| Criterion | Pass/Fail | Verifier | Date | Notes |
|-----------|-----------|----------|------|-------|
| A-01 | Pass | Agent | 2026-05-06 | E2E-01: `/` hero visible; no workspace start copy. |
| A-02 | Pass | Agent | 2026-05-06 | Existing shell guard; `/start` unauthenticated redirects to `/auth` (manual spot consistent with codebase). |
| A-03 | Pass | Agent | 2026-05-06 | E2E-03: sign out → pathname `/`. |
| A-04 | Pass | Agent | 2026-05-06 | Auth unchanged `/start`; `Auth.tsx` still `navigate("/start")`. |
| N-01 | Pass | Agent | 2026-05-06 | No secrets added. |

### Phase 6 — Exploratory tooling

`/qa` Playwright MCP: **skipped** — 本会话 Agent 上下文无可调用的 MCP `browser_*` 工具；回归由 `npm run test` + `npm run test:e2e -- --grep official-website` 承担。
