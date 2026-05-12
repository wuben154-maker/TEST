# Acceptance UI — history-sidebar-persistent

## Metadata

- **Slug:** `history-sidebar-persistent`
- **Links:** [proposal](./proposal.md), [design](./design.md)
- **Updated:** 2026-04-20

## Scope

- `ProjectSidebar` presentation and layout integration on `Index`, `WorkspaceLayout`, `PostLoginWorkspaceStart`.
- Top navigation / compact header menu behavior vs breakpoint.

## Reference assets

## Mockups deferred

Reference layout: user-provided `main-workspace(2).html` (local); no image mockups in repo.

## Visual criteria

| ID | Criterion |
|----|-----------|
| U-01 | On viewports `>= 768px`, a project sidebar column is visible as part of the main flex row (not only a drawer). |
| U-02 | Expanded width is 240px (`w-60`); collapsed width is 48px (`w-12`) with expand + create icons only. |
| U-03 | Project rows are single-line title with leading dot; active row uses stronger surface/border treatment consistent with reference tokens. |
| U-04 | Sidebar uses warm dark background (`#201e1b`) and border `#2e2c28` (not the prior cool gray-purple strip). |

## Interaction criteria

| ID | Criterion |
|----|-----------|
| I-01 | Top bar shield/menu: on `md+` toggles collapsed state; below `md` toggles mobile drawer open/closed. |
| I-02 | Selecting a project closes the mobile drawer; desktop collapse state is unchanged. |
| I-03 | Desktop collapsed preference survives reload (localStorage). |
| I-04 | Delete project remains available via row overflow menu (not inline trash on every row). |

## Responsive

- **375px:** drawer + scrim; no persistent column consuming layout width.
- **1024px+:** docked column; collapse control visible.

## Accessibility

- Sidebar `aside` has an accessible name; project rows are keyboard-activatable; focus ring visible; delete is reachable from menu.

## Sign-off

| ID | Pass | Verifier | Date | Notes |
|----|------|----------|------|-------|
| U-01 | Y | Agent | 2026-04-20 | E2E-01 complementary aside; layout code review |
| U-02 | Y | Agent | 2026-04-20 | `md:w-60` / `md:w-12` in `ProjectSidebar` |
| U-03 | Y | Agent | 2026-04-20 | Dot + single-line row; overflow menu for delete |
| U-04 | Y | Agent | 2026-04-20 | Warm tokens `#201e1b` / `#2e2c28` |
| I-01 | Y | Agent | 2026-04-20 | `useProjectSidebarChrome` + `TopNavbar` / `CompactWorkspaceHeader` |
| I-02 | Y | Agent | 2026-04-20 | `closeMobileSidebar` / `onMobileOpenChange(false)` on select |
| I-03 | Y | Agent | 2026-04-20 | Vitest `useWorkspaceSidebarCollapsed` persistence |
| I-04 | Y | Agent | 2026-04-20 | `DropdownMenu` + `MoreVertical` per row |

**Exploratory MCP:** `browser_navigate` hit `/auth` (unauthenticated session); logged-in UI covered by **E2E-01** and Vitest.
