## Why

Uploading multiple files today keeps full contents in the browser and sends them inline in `POST /analyze`, which inflates memory, request bodies, and LangGraph `state["files"]` for legacy mode. The main agent also receives large truncated previews (e.g. 6k char budget) while tools such as `ls` can expose a filesystem view that is wider than the user’s upload area. We need a **scoped upload + sandboxed filesystem** model and a **thin first turn for the main agent** so routing delegates to the right subagent without loading full file bodies into state or the initial LLM context.

## What Changes

- **Upload-first flow**: Client uploads files via a dedicated API (multipart or chunked), receives **virtual paths** only; `POST /analyze` carries **metadata + paths**, not full file bodies. **BREAKING** for clients that relied solely on inline `attachments[].content` (legacy may remain behind a feature flag or deprecation window).
- **Configurable limits**: Max files per batch (default **10**), max size per file (default **100MB**), enforced on **upload**; clear user-visible errors when exceeded. Limits configurable via environment / app config.
- **Per-owner storage layout**: On disk under `upload_dir`, each **authenticated user** gets an isolated subtree (`user_id`-scoped); **anonymous** users use a **high-entropy `session_id`** subtree. All server-side path resolution validates that requested virtual paths belong to the **current identity** (prefix + optional upload registry) to prevent cross-user access and path enumeration abuse.
- **Unified sandbox for main + subagents**: `read_file`, `ls`, `grep`, and related tools resolve to the **same CompositeBackend view** for the request; default exploration is constrained to the caller’s upload prefix (not repository root or server-wide directories).
- **Main agent first-turn content**: Human message contains a **structured file manifest** (display name, virtual path, `content_type`, `size_bytes`, optional `sha256`) plus user text and system time; **no large inline file bodies** by default. Optional **tiny** per-file sniff (e.g. first N bytes of text or magic summary) is configurable and budget-capped separately from legacy 6k “preview” behavior.
- **State storage**: Pre-uploaded files **do not** populate `state["files"]` with full `FileData` content (aligned with existing tests); inline legacy path remains supported only for small payloads if retained.
- **UI**: After upload, the chat input / outgoing request summary **lists attached file names** (and optionally paths or sizes) so users see what will be analyzed.

## Capabilities

### New Capabilities

- `scoped-file-uploads`: Authenticated and anonymous upload APIs, disk layout, quotas (count + size), ownership checks, anti-enumeration rules, and responses exposing only allowed virtual paths.
- `agent-filesystem-sandbox`: Tool-visible filesystem: CompositeBackend routing, per-request sandbox root, identical backend for main agent and all subagents, rejection of paths outside the allowed prefix.
- `analyze-attachment-protocol`: Shape of `POST /analyze` attachments when using pre-uploaded files; main-agent first message manifest; deprecation policy for inline `content`; interaction with persistence and SSE.

### Modified Capabilities

- *(none — no `openspec/specs/` baseline exists in-repo yet)*

## Impact

- **Frontend**: `CommandCenter` / file pickers, streaming hook payload, env-driven limits; remove long-lived in-memory full file content for large uploads.
- **Backend**: New or extended upload route(s), auth binding (`user_id` / `session_id`), path validation middleware or helpers, `composite.py` / backend factory wiring for scoped roots, `deep_agent.py` manifest builder and budget logic, settings in `app/config`, nginx/reverse-proxy body size docs.
- **Tests**: Extend or add tests for upload ownership, `analyze` with `file_path` only, sandbox `ls` scope, regression for `state["files"]` without disk files.
- **Docs**: `project_context.md`, `docs/ARCHITECTURE.md` or env docs for limits and upload flow.
