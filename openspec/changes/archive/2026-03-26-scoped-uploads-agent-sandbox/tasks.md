## 1. Configuration and documentation

- [x] 1.1 Add server settings: `max_upload_files_per_batch` (default 10), `max_upload_bytes_per_file` (default 104857600), optional manifest/sniff caps (`main_agent_manifest_sniff_bytes_total`, `main_agent_manifest_sniff_bytes_per_file`); document in `python-agent-service/config/env.md`
- [x] 1.2 Add frontend env vars for upload limits (defaults aligned with server); document in frontend config / README
- [x] 1.3 Document reverse-proxy max body size for 100MB uploads in `docs/ARCHITECTURE.md` or deploy notes

## 2. Upload API and storage layout

- [x] 2.1 Implement authenticated upload route(s) (e.g. `POST /uploads` or `POST /analyze/upload`) accepting multipart; bind writes to `upload_dir / u-{user_id} / ...` when JWT present
- [x] 2.2 Implement anonymous upload path using same route with required high-entropy `session_id` (header or field); bind writes to `upload_dir / s-{session_id} / ...`
- [x] 2.3 Enforce per-batch file count and per-file size on upload stream; return structured errors (413/400) with clear messages
- [x] 2.4 Sanitize filenames; prevent path traversal; optionally compute and return `sha256`
- [x] 2.5 Return response payload: `filename`, `content_type`, `size_bytes`, `virtual_path` under `/uploads/...` for each file

## 3. Authorization and anti-enumeration

- [x] 3.1 Implement `resolve_and_authorize_upload_path(virtual_path, identity)` used by upload completion, analyze attachment validation, and any download/delete helpers
- [x] 3.2 Reject with 403 when virtual path owner segment does not match current `user_id` or `session_id`; add basic rate limiting or logging hooks for repeated failures

## 4. Analyze pipeline and main-agent manifest

- [x] 4.1 Extend or confirm `AnalyzeAttachment` accepts path-only attachments; validate each path through task 3.1 before starting agent
- [x] 4.2 Replace large `file_path` preview logic in `deep_agent.analyze_stream` with structured manifest (and optional bounded sniff per design D4); remove or gate legacy 6k parsed preview for path-only mode
- [x] 4.3 Ensure `initial_state["files"]` stays empty of full `FileData` for path-only attachments (keep `test_analyze_stream_file_path_not_in_state` green; add multi-file variant)
- [x] 4.4 Wire optional legacy inline `content` behind size threshold or `settings` flag; document deprecation

## 5. Filesystem sandbox (main + subagents)

- [x] 5.1 Adjust `CompositeBackend` / backend factory so default `ls` and exploration for agent tools cannot list outside `/uploads/{ownerSegment}/` plus explicitly allowed routes (skills bundle); verify against regression tests
- [x] 5.2 Audit `create_deep_agent` / subagent specs to ensure subagents use the same `backend` factory instance or equivalent configuration as the main agent
- [x] 5.3 Add integration test: subagent `read_file` and `ls` see the same upload subtree as main agent for a given thread

## 6. Frontend

- [x] 6.1 Change `CommandCenter` (or upload hook) to stream/chunk upload to new API without holding full file array in React state after success; keep only metadata + paths for `analyzeInput`
- [x] 6.2 Enforce max files and max size in UI before/during upload with toasts matching server messages
- [x] 6.3 Ensure outgoing request to `POST /analyze` sends `attachments` with `file_path`/`virtual_path` and metadata; omit `content` for uploaded files
- [x] 6.4 Show attached file names (and optional size) in composer per spec; ensure `useStreamingAnalysisMulti` persists display metadata for history UI if needed

## 7. Cleanup, observability, and project docs

- [x] 7.1 Add TTL or cron note for anonymous upload dirs (implementation or follow-up task in backlog)
- [x] 7.2 Update `project_context.md` file-upload and analyze sections after implementation
- [x] 7.3 Run pytest for upload/analyze/sandbox tests; fix any regressions
