# DeepAgents Upstream Changelog — 20260414

**Sync date:** 2026-04-14  
**Pre-sync SHA:** `b6a082f`  
**Post-sync SHA:** `bbf553c`  
**Upstream version:** v0.5.2 (released 2026-04-10)  
**Upstream branch:** main  

## Summary

DeepAgents v0.5.2 introduces a **Permissions system** for filesystem access control, splits subagent code into sync (`subagents.py`) and async-remote (`async_subagents.py`) modules, renames several backend protocol methods to cleaner names (keeping deprecated shims until v0.7), and adds model profiles infrastructure (`profiles/`). The `base_prompt.md` file has been removed from the library. All internal package imports were changed to absolute `deepagents.*` paths (which we replace with `app._vendor.deepagents.*` during vendoring).

## New public API

- `middleware/permissions.py`: `FilesystemPermission` TypedDict + `PermissionsMiddleware` class — route-scoped filesystem access control
- `middleware/async_subagents.py`: `AsyncSubAgent`, `AsyncSubAgentMiddleware` — connect to remote LangGraph Platform servers as async subagents
- `middleware/_tool_exclusion.py`: `ToolExclusionMiddleware` — exclude specific tools from agent
- `backends/langsmith.py`: `LangsmithBackend` — LangSmith artifact storage backend
- `_models.py`: `resolve_model()` helper — normalize model string to `BaseChatModel`
- `_version.py`: `__version__` constant — v0.5.2
- `profiles/`: `_HarnessProfile`, `_openai.py`, `_openrouter.py` — model-specific harness configurations
- `graph.py`: New `permissions: list[FilesystemPermission] | None` parameter in `create_deep_agent()`
- `graph.py`: New `cache: BaseCache | None` parameter in `create_deep_agent()` — LLM response caching
- `backends/state.py`: `upload_files()` method added to `StateBackend`

## Removed / renamed API

- `base_prompt.md` — **removed** from upstream entirely (was `deepagents/base_prompt.md`); not referenced in SecManus
- `backends/protocol.py`: `ls_info()` → renamed to `ls()` (returns `LsResult`); old name kept as deprecated shim until v0.7
- `backends/protocol.py`: `glob_info()` → renamed to `glob()` (returns `GlobResult`); deprecated shim kept
- `backends/protocol.py`: `grep_raw()` → renamed to `grep()` (returns `GrepResult`); deprecated shim kept
- `backends/protocol.py`: `als_info()` → `als()`, `aglob_info()` → `aglob()`, `agrep_raw()` → `agrep()` — async variants renamed similarly

## Signature changes

- `graph.py` → `create_deep_agent(...)` — added `permissions`, `cache`, `AsyncSubAgent` to `subagents` union; all new params are optional with `None` defaults — **backward compatible**
- `backends/filesystem.py` → `FilesystemBackend.__init__()` — upstream still has only 3 params (`root_dir`, `virtual_mode`, `max_file_size_mb`); our SECMANUS PATCH adds 4th `fmt_timestamp`
- `backends/filesystem.py` → `modified_at` formatting changed from `_fmt_utc_mtime()` → `datetime.fromtimestamp(st.st_mtime).isoformat()` inline; our SECMANUS PATCH replaces with `self._fmt_mtime()`

## Behavior changes

- `backends/filesystem.py` → `FilesystemBackend`: Added `PermissionError` catch in ripgrep path (bug fix from v0.5.2)
- `middleware/subagents.py` → `_build_task_tool()`: `StructuredTool.from_function()` now passes `infer_schema=False, args_schema=TaskToolSchema` — more explicit schema control (our vendor now includes this)
- `middleware/subagents.py` → `task()`/`atask()`: `tool_call_id` null check now happens **before** `subagent.invoke()` (upstream fix for cleaner error handling); our SECMANUS PATCH preserves this ordering
- `middleware/summarization.py`: Significant updates (60 KB → larger); context window and chunking logic improved

## New upstream dependencies

- `middleware/async_subagents.py`: `from langgraph_sdk import get_client, get_sync_client` — LangGraph SDK for remote subagents
- `graph.py`: `from deepagents._models import resolve_model` — model normalization
- `middleware/permissions.py`: new module, no new external deps

## Config / schema changes

- `graph.py` → `create_deep_agent()`: New `permissions` key in graph configurable — accepts `list[FilesystemPermission]` to scope filesystem access by route
- `backends/composite.py`: Significant expansion; permissions routing now integrated into composite backend

## base_prompt.md changes

File has been **removed** from upstream. The `deepagents/base_prompt.md` no longer exists in `langchain-ai/deepagents`. SecManus uses `app/prompts/MASTER_AGENT.md` as the system prompt — no overlap.

## Impact on SecManus

| Item | Impact | Action |
|------|--------|--------|
| `create_deep_agent()` new params (`permissions`, `cache`) | **(C) Safe to ignore** — optional params with `None` default; existing call in `app/agents/deep_agent.py` unchanged |
| `AsyncSubAgent` in subagents union | **(C) Safe to ignore** — additive type; SecManus uses `SubAgent` only |
| `ls_info()`, `glob_info()`, `grep_raw()` deprecated | **(B) ⚠️ Review recommended** — `app/backends/upload_scope.py` (3 calls) and `app/backends/filtered_skills_root.py` (2 calls) use deprecated names; shims work until v0.7 but generate `DeprecationWarning`. Migrate to `ls()`, `glob()`, `grep()` before v0.7 upgrade. |
| `base_prompt.md` removed | **(C) Safe to ignore** — SecManus never imported this file |
| `backends/state.py` `upload_files()` added | **(C) Safe to ignore** — new feature, not called by SecManus yet |
| `middleware/permissions.py` | **(C) Safe to ignore for now** — new optional feature; SecManus can adopt later for workspace isolation |
| `fmt_timestamp` DI in `filesystem.py` | **(A) SECMANUS PATCH re-applied** — upstream `isoformat()` → `self._fmt_mtime()` patch re-applied successfully |
| `_return_command_with_state_update` simplified | **(A) SECMANUS PATCH kept** — our richer `aimessage_to_handoff_plain_text` logic preserved over upstream's simple `.text.rstrip()` |

## SECMANUS PATCH compatibility

| Patch | Status after this sync |
|-------|----------------------|
| `subagents.py` — VENDOR FORK NOTICE banner | ✅ Re-applied |
| `subagents.py` — SSE bridge (`_ainvoke_subagent_with_sse_queue`) | ✅ Re-applied; insertion point unchanged |
| `subagents.py` — `task()` invoke_cfg | ✅ Re-applied; `tool_call_id` check now correctly before invoke |
| `subagents.py` — `atask()` SSE queue | ✅ Re-applied |
| `subagents.py` — `build_subagent_task_messages` / language injection | ✅ Re-applied; `_validate_and_prepare_state` still accepts `runtime` param |
| `filesystem.py` — fmt_timestamp DI | ✅ Re-applied; upstream changed from `_fmt_utc_mtime()` to inline `isoformat()` — all 6 call sites replaced with `self._fmt_mtime()` |
| `local_shell.py` — fmt_timestamp pass-through | ✅ Re-applied |
| All vendor files — absolute import rewrite | ✅ Bulk-replaced `from deepagents.` → `from app._vendor.deepagents.` (23 files) |
