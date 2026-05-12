## Context

- **Current**: Frontend reads files into memory and sends `attachments[].content` in JSON to `POST /analyze`. `deep_agent.analyze_stream` supports **Mode A** (`file_path` → disk via `CompositeBackend` `/uploads/`) and **Mode B** (inline → `state["files"]` via `create_file_data`). Main-agent user text includes a budgeted preview (e.g. 6k chars). Tools can list or read paths routed by CompositeBackend; without a tight default root, exploration may surface more of the virtual tree than intended.
- **Constraints**: DeepAgents **StateBackend** stores file bodies in `state["files"]` as `FileData` with line `content`; **FilesystemBackend** serves `/uploads/` from `upload_dir`. Pre-uploaded files should stay on disk and **not** duplicate full content into state (existing tests: `test_analyze_stream_file_path_not_in_state`).
- **Stakeholders**: Product (UX, limits), backend (security, storage), frontend (memory, progress), security (isolation, enumeration).

## Goals / Non-Goals

**Goals:**

- Upload-first: browser does **not** retain full file bodies for large attachments; server persists under an **owner-scoped** directory and returns **virtual paths** only.
- **Authorization**: Any operation that resolves a path (upload write, analyze attachment reference, tool read) **MUST** verify the path belongs to the current `user_id` (JWT) or anonymous `session_id` (high-entropy, bound to the same request context the client uses for analyze).
- **Single sandbox view**: Main agent and **all** subagents use the **same** backend factory / composite routes for the thread so `ls`/`read_file` cannot widen scope in subgraphs.
- **Main-agent first turn**: Short, structured **manifest** for routing; heavy analysis remains in subagents via `read_file` on virtual paths.
- **Configurable limits**: Max files per request (default 10), max bytes per file (default 100MB), enforced at **upload**; user-visible errors.

**Non-Goals:**

- **Agent-layer** rejection of 100MB files (already enforced at upload); tool **response** truncation for LLM context may remain separate (existing `TOOL_RESULT_TOKEN_LIMIT` style limits).
- Replacing Supabase RLS or full product IAM; this change focuses on **upload disk** and **agent tool** surfaces.
- Multipart resumable upload standard (e.g. tus) unless explicitly added later; initial design can use single-shot multipart POST per file or small batch.

## Decisions

### D1 — Identity key for disk layout

- **Decision**: **Authenticated**: namespace by `user_id` (stable UUID from auth). **Anonymous**: namespace by **cryptographic random** `session_id` (already used for analyze); client sends the same `session_id` / header for upload and analyze.
- **Rationale**: Aligns with existing `session_id` / `project_id` usage; logged-in users get durable ownership tied to JWT `sub`.
- **Alternatives**: Only `session_id` for everyone (logged-in users harder to correlate across devices); only `user_id` (breaks anonymous uploads unless synthetic server-issued session).

### D2 — Virtual path shape

- **Decision**: Expose stable virtual paths to the LLM, e.g. `/uploads/{ownerSegment}/{uploadBatchOrSession}/{sanitizedFilename}` where `ownerSegment` is `u-{user_id}` or `s-{session_id}` (exact encoding TBD in implementation; must be injective and validated).
- **Rationale**: Matches existing `CompositeBackend` `/uploads/` routing; easy to validate prefix against caller.
- **Alternatives**: Opaque `upload_id` only in API, server maps to path internally (stronger anti-guess; can be **phase 2** table-backed registry).

### D3 — Anti-enumeration and authorization

- **Decision**: **Mandatory** server-side check: resolved realpath under `upload_dir / ownerRoot` **and** virtual path prefix matches authenticated owner. Reject with **403** (not 404 distinction optional for info leakage trade-off). Rate-limit repeated failures.
- **Rationale**: Security does not rely on obscurity of UUIDs alone.
- **Alternatives**: Public opaque tokens only (adds DB table and lifecycle).

### D4 — Main-agent manifest vs legacy preview budget

- **Decision**: Replace large inline previews for pre-uploaded files with a **manifest** (paths, names, types, sizes, optional sha256). Optional **L1 sniff**: first **≤4KB** text or binary magic label, with a **separate** small cap (e.g. **8–16KB total** across files), configurable via settings. Deprecate or reduce the old **6000-char parsed preview** for `file_path` mode.
- **Rationale**: Routing needs filenames/extensions and paths; subagents read full content from disk.
- **Alternatives**: Keep 6k for compatibility (noisy); zero sniff (more `read_file` rounds).

### D5 — Subagent backend parity

- **Decision**: Ensure `create_deep_agent` / `task()` subagents receive the **same** `backend` factory instance or equivalent configuration so Composite routes and **effective cwd / ls root** cannot expand.
- **Rationale**: User requirement: subagents inherit the same sandbox.
- **Alternatives**: Per-subagent narrower sandbox (stricter but more work; can be future hardening).

### D6 — Frontend configuration

- **Decision**: Expose `VITE_MAX_UPLOAD_FILES` and `VITE_MAX_UPLOAD_BYTES_PER_FILE` (or single JSON config endpoint) with defaults 10 and 100MB; **mirror** limits server-side.
- **Rationale**: UX pre-check + server is source of truth.

### D7 — Inline legacy `attachments[].content`

- **Decision**: **Phase 1**: Keep for backward compatibility behind explicit flag or size threshold (e.g. only if total payload &lt; N KB). **Phase 2**: remove or admin-only.
- **Rationale**: Smooth migration for any external API consumers.

## Risks / Trade-offs

| Risk | Mitigation |
|------|------------|
| Reverse proxy body limit &lt; 100MB | Document `client_max_body_size` / platform limits; return clear error. |
| Disk fill / abuse | Per-user quotas (future), TTL cleanup job for anonymous uploads, max files. |
| Path traversal or symlink escape | Normalize paths, `realpath` under owner root, reject symlinks leaving root if policy requires. |
| Subagent middleware reinstantiates backend | Integration test: `ls` from subagent same as main under scoped root. |
| Breaking API for inline-only clients | Deprecation window + changelog; feature flag. |

## Migration Plan

1. Ship upload API + server validation; frontend switches to upload-then-analyze with paths.
2. Keep inline path for small payloads or flag-gated period.
3. Update docs and default proxy limits.
4. Monitor 413/403 rates; tune rate limits.

**Rollback**: Feature flag to revert frontend to inline; old clients continue until removed.

## Open Questions

- Whether to add **DB-backed `upload_id`** registry in v1 or v2 (improves revoke/TTL and audit).
- Exact **TTL** for anonymous files on disk.
- Whether **images** should use a separate multimodal message path (out of scope unless specified).
