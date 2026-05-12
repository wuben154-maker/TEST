# Proposal — workspace-sandbox-unification

## Metadata

- **Slug:** `workspace-sandbox-unification`
- **Owner:** chenf
- **Updated:** 2026-04-20
- **Tier:** Standard

## Problem

The Python Agent Service currently exposes three overlapping weaknesses in how file-system access is scoped and how paths surface to the UI:

1. **Isolation is partial.** Only the `/uploads/` route is wrapped by `ScopedUploadFilesystemBackend` (via a `ContextVar` set at the entry of each `analyze`/`resume` request). Other routes in the `CompositeBackend` — `/memories/`, `/parameters/`, `/skills/`, the default `StateBackend`, and large-tool-result eviction directories — do not enforce per-user or per-project isolation. `StoreBackend` currently uses fixed namespaces (`"memories"`, `"parameters"`) with no owner component, so two users sharing the same process can in principle read each other's persisted memory.
2. **Internal paths leak to the UI.** Tool results from `ls` / `glob` / `read_file` / `grep` and any LLM reasoning that embeds file paths are streamed verbatim through the SSE adapter. The UI ends up showing raw strings such as `/uploads/u_ab12cd34/foo.txt`, `/skills/web-security/SKILL.md`, or Windows absolute paths — exposing hashed identifiers, the internal route taxonomy, and platform details that should never be end-user-visible.
3. **Agents can freely enumerate the virtual file system.** `FilesystemMiddleware` always mounts the full seven-tool set (`ls`, `read_file`, `write_file`, `edit_file`, `glob`, `grep`, `execute`) for both the main agent and every subagent. `ls("/")` on a `CompositeBackend` enumerates every mounted prefix, letting the LLM discover the existence of `/memories/`, `/skills-*/`, `/parameters/`, etc. `glob("**/*")` has similar reach. There is no switch to constrain enumeration to the current user's workspace.

## Goals

- **G1 — Unified virtual root.** The main agent and all subagents see a single logical entry point `/workspace/` for all user-writable data (uploads, analysis artifacts, reports destined for the user).
- **G2 — Hard owner isolation across persistence layers.** User → Project → Session resolve deterministically to an `owner_segment`; every backend that persists data across turns (`/workspace/`, `/memories/`, `/parameters/`) is scoped by that segment.
- **G3 — Enumeration scope.** `ls` and `glob` are constrained at the facade layer so that:
  - `ls("/")` returns the contents of the caller's `/workspace/`, not the `CompositeBackend` route list.
  - `glob` / `ls` on any path outside `/workspace/…` returns an explicit error to the LLM.
  - `read_file` remains globally callable (so skills can still be progressively loaded).
- **G4 — Zero path leakage to the UI.** No SSE event, reasoning text, tool input/output, or block payload rendered in the UI contains a raw internal path. All user-facing path-like strings are rewritten to the `Workspace/…` label (or a labeled `System Skill: …` / `Memory: …` equivalent for non-workspace routes).
- **G5 — Skills keep working untouched.** The subagent skill loading pipeline (prompt injection + explicit `read_file('/skills[-*]/…/SKILL.md')`) continues to function without modification, because skill discovery does not rely on `ls`/`glob`.

## Non-goals

- **No public API contract changes.** `/analyze` request/response schema stays the same.
- **No database migration.** `session_parameters` and related tables are untouched in this delivery.
- **No historical data migration.** Existing on-disk `u_*` / `s_*` trees are not reformatted; the old `/uploads/` virtual prefix is not kept as an alias.
- **No frontend component rewrites.** The UI only benefits from cleaner text content; no new components or visual layouts are introduced.
- **No change to `execute`-tool sandboxing.** E2B sandbox policy and shell command surface are out of scope.
- **No change to the Anthropic-style skills discovery protocol.** SKILL.md frontmatter + SkillsMiddleware injection remains authoritative.

## Users / stakeholders

| Role | Interaction |
|------|-------------|
| End user (logged-in) | Sees only `Workspace/…` labels; can switch between projects with strict data isolation |
| End user (anonymous) | Single per-session workspace; cannot cross-contaminate other anonymous users |
| Main Agent LLM | Sees `/workspace/` as its single writable root; `ls`/`glob` limited; `read_file` unrestricted |
| Subagent LLM | Same as main agent plus read access to its own `/skills-<subagent_id>/` bundle |
| Operations | Disk layout remains `<upload_dir>/u_<hash>/[p_<hash>|default]/…` for audit traceability |

## Scope

### In scope

- New `WorkspaceFacadeBackend` (decorator around `ScopedUploadFilesystemBackend`) performing two-way path rewriting between LLM-visible `/workspace/` and the internal owner-scoped tree.
- Extension of `owner_segment()` to accept `project_id` and emit a two-level path (`u_<uid>/p_<pid>` or `u_<uid>/default`).
- Namespace repair for `/memories/` and `/parameters/` `StoreBackend` so each uses an owner-qualified namespace.
- Vendored `FilesystemMiddleware` SECMANUS PATCH exposing `ls_allowed_prefixes` / `glob_allowed_prefixes` constructor arguments and root-redirect behaviour.
- Path scrubber applied in `parsers/deepagents_stream_adapter.py` across all text-bearing SSE event fields.
- Prompt updates (`prompts/MASTER_AGENT.md` + 5 × `subagents/official/*/AGENT.md`) to teach the agents about `/workspace/` and the enumeration constraint.
- Unit / integration tests for: facade path rewriting, owner_segment with project, scrub rewriter, middleware prefix enforcement, scoped ls/glob behaviour.
- One Playwright E2E verifying no raw path strings appear in the user-visible analysis stream.

### Out of scope

- Upgrading `InMemoryStore` to a persistent store (Supabase / PostgreSQL). Already tracked separately.
- Cross-project "shared" workspace routes (e.g. `/shared/`).
- HITL resume flow path-scrub is covered, but new HITL UX is not in scope.
- Historical compatibility shim at `/uploads/`.

## Dependencies

- Existing `app/backends/upload_scope.py` `ContextVar` mechanism (reused, renamed).
- `app/services/upload_path_auth.py` `owner_segment()` (extended).
- `app/agents/deep_agent.py` already wires per-request owner scope (only needs `project_id` plumbing).
- Vendored `app/_vendor/deepagents/middleware/filesystem.py` v0.5.2 — SECMANUS PATCH blocks already in use; one additional patch block required.
- `SubAgent` registry and `SkillsMiddleware` — read only, no changes.

## Success metrics

| Metric | Target |
|--------|--------|
| Raw internal path occurrences in UI event stream (Playwright regex assertion) | 0 across full smoke flow |
| `ls("/")` result contains `/memories/` or `/skills/` from the LLM's perspective | Never |
| Cross-project contamination via `/workspace/` | Impossible — verified by multi-owner pytest |
| `/memories/` / `/parameters/` namespace includes owner segment | 100% of writes |
| Skill load latency regression | 0% (no change to skill discovery path) |
| Existing `pytest` suite pass rate | 100% (no regression) |

## Risks

| Risk | Mitigation |
|------|-----------|
| Subagent `AGENT.md` text out of sync with backend route (`/uploads/` still mentioned) | Grep-and-replace covered in touch list; unit test asserts no occurrence of `/uploads/` in shipped prompt files |
| Scrub regex over-matches and corrupts legitimate user content | Scrub applied only to path-shaped tokens starting with `/` + known prefixes; plus unit fixtures covering false-positive cases |
| `ls_allowed_prefixes` patch conflicts with future deepagents upstream | Patch guarded by `# --- SECMANUS PATCH: workspace-ls-scope (start/end) ---` markers consistent with existing conventions |
| Tests pass locally but path leakage still occurs through a new event type added later | Scrub pipeline is keyed on event categories, not a field allowlist; adding a new event type requires opt-in |
