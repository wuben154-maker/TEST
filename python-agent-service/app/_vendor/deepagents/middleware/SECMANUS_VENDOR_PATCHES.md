# SecManus patches on vendored DeepAgents (`middleware/`)

Upstream source: **LangChain DeepAgents** (e.g. `langchain-ai/deepagents`). Files under `app/_vendor/deepagents/` are copies; some carry **SecManus-only** changes.

## `subagents.py`

Search the file for **`SECMANUS`** (or `SECMANUS PATCH`).

| Patch | Purpose |
|-------|---------|
| File header notice | Merge checklist pointer |
| Imports: stdlib `asyncio`; `AIMessage`, `RunnableLambda` | SSE bridge helpers |
| Block `_tool_output_text_for_sse` + `_ainvoke_subagent_with_sse_queue` | Push subagent progress to `configurable["subagent_sse_event_queue"]` for main SSE (full tool text; no 4k bridge cap) |
| `task()` | Same subagent runner as `atask()`: `_ainvoke_subagent_with_sse_queue` with full `invoke_cfg` + optional `runtime.stream_writer` when **no running event loop** (`asyncio.run`). If **`get_running_loop()` succeeds**, run coroutine on a **ThreadPoolExecutor** thread with **`asyncio.run`** and a **stripped copy** of `invoke_cfg` (no `subagent_sse_event_queue`, no stream_writer) to avoid unsafe cross-thread writes to main-loop `asyncio.Queue`. Avoids **`subagent.invoke`** which breaks async-only tools (binary `bash`/etc.). |
| `atask()`: `await _ainvoke_subagent_with_sse_queue(...)` | Same for async path; avoids double `ainvoke` for normal graphs via `astream(stream_mode="values")` |
| `build_subagent_task_messages` + `_validate_and_prepare_state` | Prepend `SystemMessage` with response-language rules; reads `configurable["subagent_response_language"]` or `sse_ui_language` |
| `_log_task_tool_invoke_start` + `structlog` | On every nested `task()` / `atask()` start: event `subagent_task_invoke_start` with `subagent_type`, `task_tool_call_id`, `delegation_*` (filter logs for `subagent_type=binary-analysis`) |
| `_push_lifecycle_step` in `_ainvoke_subagent_with_sse_queue` | Emits `type: "step"` SSE events (`status: "running"` / `"done"`, `phaseId` for frontend merge) bracketing every nested subagent run across all three execution paths. Uses **fan-out delivery**: pushes to BOTH `stream_writer` AND `queue` in parallel so the event survives even when `stream_writer` writes to an uncaptured LangGraph custom channel (depth-2 case: `binary-analysis` inside `email-security` whose `astream(stream_mode="values")` does not collect the custom channel). |
|| `_nested_subagent` flag + fan-out in `_push` | When `delegationDepth >= 2`, `_push` fans out to **both** `stream_writer` and `queue` for ALL events (tool_call, tool_result, llm_delta, etc.), not just lifecycle steps. Fixes the root cause where depth-2 `stream_writer` writes to an intermediate level's uncaptured "custom" channel — without this, binary-analysis tool calls and results are silently dropped and never appear in the UI timeline. |

**Consumer (not in this vendor tree):** `app/parsers/deepagents_stream_adapter.py` creates `subagent_sse_event_queue` and puts it on the main agent `config["configurable"]`. Parent run sets `subagent_response_language` in `app/agents/deep_agent.py` (`analyze_stream` / `resume_stream`).

### Merging a new upstream `subagents.py`

1. Save your current file or use `git show` to extract only `SECMANUS` blocks.
2. Replace `subagents.py` with upstream version.
3. Re-apply, in order:
   - Top-of-file **SECMANUS VENDOR FORK NOTICE** (banner).
   - Import changes (`asyncio`; extend `langchain_core.messages` / `runnables` as marked).
   - Entire block between `# --- SECMANUS PATCH: subagent -> main SSE bridge (start) ---` and `(end) ---`.
   - In `task()` and `atask()`, restore `invoke_cfg`, `_ainvoke_subagent_with_sse_queue`, and the sync `task()` thread/SSE-strip fallback as in the previous fork (do **not** restore bare `subagent.invoke` — async-only sandbox tools depend on async execution).
4. Run `python -m py_compile app/_vendor/deepagents/middleware/subagents.py` and `pytest` for streaming tests.

## `backends/filesystem.py`

Search for **`SECMANUS PATCH`** in this file.

| Patch | Purpose |
|-------|---------|
| `_default_fmt_mtime` module-level function | Pure stdlib fallback: formats `st_mtime` as `"YYYY-MM-DD HH:MM:SS"` UTC, no app dependency |
| `fmt_timestamp` parameter in `__init__` | Optional `Callable[[float], str]` injected at construction time; stored as `self._fmt_mtime` |
| 6× `self._fmt_mtime(st.st_mtime)` in `list_directory` / `glob_info` | Replaced `_fmt_utc_mtime(st.st_mtime)` calls (which no longer exist) |

**Why not in `app.datetime_support` directly:**  
The `modified_at` field is embedded in tool-call text returned to the LLM. There is no second serialization pass, so timezone conversion must happen at the vendor layer where the string is produced. Injecting a callback keeps vendor code free of project imports.

### Merging a new upstream `filesystem.py`

1. Upstream has no `fmt_timestamp` parameter — it either omits `modified_at` or uses `datetime.isoformat()`.
2. Add the `fmt_timestamp` parameter block (see markers in source) to `__init__`.
3. Replace any `_fmt_utc_mtime(...)` or inline datetime-formatting calls with `self._fmt_mtime(...)`.
4. Ensure `from collections.abc import Callable` is present in imports.
5. Run `python -m py_compile app/_vendor/deepagents/backends/filesystem.py`.

## `backends/local_shell.py`

| Patch | Purpose |
|-------|---------|
| `fmt_timestamp` parameter in `__init__` | Pass-through to `super().__init__()` (FilesystemBackend) |
| `from collections.abc import Callable` | Required for the type annotation |

### Merging a new upstream `local_shell.py`

1. Add `from collections.abc import Callable` to imports.
2. Add `fmt_timestamp: Callable[[float], str] | None = None` to `__init__`.
3. Add `fmt_timestamp=fmt_timestamp` to the `super().__init__(...)` call.

**Consumer (non-vendor):** `app/backends/composite.py` defines `_fmt_ts` (wraps `app.datetime_support.format_api_datetime`) and passes it to every `FilesystemBackend(...)` / `LocalShellBackend(...)` instantiation.

## `graph.py` (under `app/_vendor/deepagents/`)

Search the file for **`SECMANUS PATCH`**.

| Patch | Purpose |
|-------|---------|
| File header notice | Merge checklist + pointers to `context_budget` / stream adapter |
| Import `create_secmanus_summarization_middleware` | **Not** from `app.context_budget` root — that `__init__` must stay free of `summarization` to avoid circular import (`graph` → `context_budget` → … → `graph`). Use `app.context_budget.summarization`. |
| Main middleware stack: `create_secmanus_summarization_middleware(model, backend)` | Replaces upstream `create_summarization_middleware` **only** on the top-level deep agent. Adds optional compression when provider-reported prompt tokens vs context window exceed `context_compress_trigger_ratio` (`get_settings()`). Reads `RunnableConfig["configurable"]["_context_meter"]`. |

**Upstream equivalent:** a single call to `create_summarization_middleware(model, backend)` in the main `deepagent_middleware` list (same position: after `SubAgentMiddleware`, before `PatchToolCallsMiddleware`).

**Do not change:** general-purpose subagent stack (`gp_middleware`), per–inline-subagent stacks, and `CompiledSubAgent` paths — they must keep **vanilla** `create_summarization_middleware` so sub-runs do not inherit the parent `ContextMeter` and fire compression incorrectly.

### Merging a new upstream `graph.py`

1. Take upstream `graph.py`; restore single summarization import from `middleware.summarization` only.
2. Re-apply the **SECMANUS PATCH** import block (`create_secmanus_summarization_middleware` from `app.context_budget.summarization`).
3. In the main `deepagent_middleware` list, replace `create_summarization_middleware(model, backend)` in that slot with `create_secmanus_summarization_middleware(model, backend)` (see markers in source).
4. Run `python -m py_compile app/_vendor/deepagents/graph.py` and streaming / summarization tests.

## Other files

If you add more patches under `_vendor/deepagents/`, append a row here and use the same **`SECMANUS PATCH`** comment pattern in source.

---

## Sync changelog

| Date | Upstream version | Files updated | Conflicts | Notes |
|------|-----------------|---------------|-----------|-------|
| 2026-04-14 | v0.5.2 (commit ~41dc759) | `__init__.py`, `graph.py`, all backends/*, all middleware/*, new: `_models.py`, `_version.py`, `backends/langsmith.py`, `middleware/async_subagents.py`, `middleware/permissions.py`, `middleware/_tool_exclusion.py`, `profiles/*` | Soft (location drift, not logic conflict) | Major version jump from pre-0.5 to 0.5.2. `subagents.py` was already closure-based (no change to task()/atask() location). All `from deepagents.` absolute imports replaced with `from app._vendor.deepagents.`. New permissions system added. `base_prompt.md` removed upstream. |
