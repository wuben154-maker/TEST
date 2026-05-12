---
name: update-deepagents-vendor
description: Sync the vendored DeepAgents code under python-agent-service/app/_vendor/deepagents/ with the latest upstream langchain-ai/deepagents repository, automatically re-applying all SECMANUS PATCH blocks and running syntax + pytest verification. Use when the user says "更新 deepagents", "升级 vendor", "sync upstream deepagents", "deepagents 有新版本", or "vendor 同步".
---

# Update DeepAgents Vendor

Upstream source: **https://github.com/langchain-ai/deepagents** (main branch)  
Vendor path: **`python-agent-service/app/_vendor/deepagents/`**  
Patch registry: **`python-agent-service/app/_vendor/deepagents/middleware/SECMANUS_VENDOR_PATCHES.md`**

---

## Phase 0 — Pre-flight check

1. Read **`SECMANUS_VENDOR_PATCHES.md`** — understand every current patch (file, block boundaries, purpose).
2. Run `git status python-agent-service/app/_vendor/deepagents/` — confirm no uncommitted edits. If dirty, **STOP** and ask user to commit or stash first.
3. Record the current git short SHA as the rollback anchor:
   ```
   git rev-parse --short HEAD
   ```

---

## Phase 1 — Extract all current SECMANUS patches

For each file listed in **`SECMANUS_VENDOR_PATCHES.md`** (and any file containing `# --- SECMANUS PATCH`):

1. **Read the full file** and extract every block delimited by:
   ```
   # --- SECMANUS PATCH: <name> (start) ---
   ...code...
   # --- end SECMANUS PATCH (<name>); upstream was: ... ---
   ```
2. Also capture:
   - The **import additions** marked with `SECMANUS PATCH` inline comments.
   - The top-of-file **SECMANUS VENDOR FORK NOTICE** banner.
3. Store extracted patch text in memory (or a temp file under `/tmp/secmanus_patches/`) keyed by `<filename>/<name>`.

**Current known patches (as of last audit):**

| File | Patch name | Purpose |
|------|-----------|---------|
| `middleware/subagents.py` | VENDOR FORK NOTICE banner | Merge reminder header |
| `middleware/subagents.py` | imports | `asyncio`, `AIMessage`, `RunnableLambda`, `SystemMessage`, SecManus app imports |
| `middleware/subagents.py` | subagent -> main SSE bridge | `_tool_output_text_for_sse` + `_ainvoke_subagent_with_sse_queue` functions |
| `middleware/subagents.py` | task() invoke_cfg | Propagate LangGraph config (sync path) |
| `middleware/subagents.py` | atask() SSE queue | Async path SSE delegation |
| `middleware/subagents.py` | build_subagent_task_messages | `SystemMessage` with `subagent_response_language` |

> **After running a real sync, update this table** with any new patches added.

---

## Phase 2 — Download upstream files

Use the GitHub raw content URL pattern:

```
https://raw.githubusercontent.com/langchain-ai/deepagents/main/<path>
```

Files to download (mirror the current vendor tree):

```
deepagents/__init__.py
deepagents/graph.py
deepagents/base_prompt.md
deepagents/backends/__init__.py
deepagents/backends/protocol.py
deepagents/backends/state.py
deepagents/backends/filesystem.py
deepagents/backends/composite.py
deepagents/backends/store.py
deepagents/backends/local_shell.py
deepagents/backends/sandbox.py
deepagents/backends/utils.py
deepagents/middleware/__init__.py
deepagents/middleware/_utils.py
deepagents/middleware/filesystem.py
deepagents/middleware/memory.py
deepagents/middleware/patch_tool_calls.py
deepagents/middleware/skills.py
deepagents/middleware/subagents.py
deepagents/middleware/summarization.py
```

Shell command (PowerShell, repo root):

```powershell
$base = "https://raw.githubusercontent.com/langchain-ai/deepagents/main"
$vendor = "python-agent-service/app/_vendor"
$files = @(
  "deepagents/__init__.py",
  "deepagents/graph.py",
  "deepagents/base_prompt.md",
  "deepagents/backends/__init__.py",
  "deepagents/backends/protocol.py",
  "deepagents/backends/state.py",
  "deepagents/backends/filesystem.py",
  "deepagents/backends/composite.py",
  "deepagents/backends/store.py",
  "deepagents/backends/local_shell.py",
  "deepagents/backends/sandbox.py",
  "deepagents/backends/utils.py",
  "deepagents/middleware/__init__.py",
  "deepagents/middleware/_utils.py",
  "deepagents/middleware/filesystem.py",
  "deepagents/middleware/memory.py",
  "deepagents/middleware/patch_tool_calls.py",
  "deepagents/middleware/skills.py",
  "deepagents/middleware/subagents.py",
  "deepagents/middleware/summarization.py"
)
foreach ($f in $files) {
  $url = "$base/$f"
  $dest = "$vendor/$f"
  Invoke-WebRequest -Uri $url -OutFile $dest -ErrorAction Stop
  Write-Host "Downloaded: $f"
}
```

> If GitHub raw access is unavailable (network / rate limit):
> Alternative: `git clone --depth 1 https://github.com/langchain-ai/deepagents.git /tmp/deepagents-upstream`
> then copy files manually.

**Do not overwrite these SecManus-only files** (not from upstream):
- `middleware/SECMANUS_VENDOR_PATCHES.md`
- `middleware/patch_tool_calls.py` (check if upstream has it; if yes, diff carefully)
- `backends/filesystem.py` — has SecManus-specific imports (`app.datetime_support`); **always diff before overwrite**

---

## Phase 3 — Diff analysis (before re-patching)

For each patched file, run a diff between upstream (just downloaded) and the saved patch extraction:

```powershell
# Example for subagents.py
git diff HEAD -- python-agent-service/app/_vendor/deepagents/middleware/subagents.py
```

**Classify each change:**

| Category | Action |
|----------|--------|
| New upstream function/class | Note in diff summary; no patch conflict |
| Upstream changed a function that a SECMANUS PATCH modifies | **CONFLICT** → manual resolution required |
| Upstream added imports | Merge with SECMANUS import additions |
| Pure upstream additions (no overlap) | Safe to accept |

If **any CONFLICT** is found: **STOP**, show the conflicting sections, and ask user how to resolve before continuing.

---

## Phase 4 — Re-apply SECMANUS patches

For each patched file (starting with `middleware/subagents.py`):

### 4.1 Fork notice banner

Prepend to the top of the file (after any module docstring):

```python
# =============================================================================
# SECMANUS VENDOR FORK NOTICE (DeepAgents upstream: langchain-ai/deepagents)
# =============================================================================
# This file is vendored from the official DeepAgents package. Local edits are
# wrapped in "SECMANUS PATCH" blocks below.
#
# When upgrading / merging upstream DeepAgents:
#   1. Diff this file against the new upstream `middleware/subagents.py`.
#   2. Re-apply every block marked `# --- SECMANUS PATCH: ... ---`.
#   3. See `SECMANUS_VENDOR_PATCHES.md` in this directory for a patch checklist.
# Related (non-upstream) code: `app/parsers/deepagents_stream_adapter.py` sets
#   `configurable["subagent_sse_event_queue"]` consumed here via `invoke_cfg`.
# =============================================================================
```

### 4.2 Import additions

Immediately after upstream import block, insert the SECMANUS import block (saved in Phase 1). Wrap with markers:

```python
# --- SECMANUS PATCH: imports (extend messages/runnables for SSE bridge; asyncio above) ---
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import Runnable, RunnableLambda
# --- end SECMANUS PATCH (imports); upstream was: HumanMessage, ToolMessage, Runnable only ---
```

Plus all `from app.*` imports extracted from Phase 1.

### 4.3 Function / block patches

Insert each saved SECMANUS block at the same logical location (before/after the same upstream function as before). Use the extracted context lines (2–3 lines before/after) to locate the insertion point.

### 4.4 `backends/filesystem.py` — `fmt_timestamp` DI parameter

Upstream has **no** `app.*` imports. Our patch adds a dependency-injection slot so the project layer controls timestamp formatting without polluting vendor code.

After overwriting with upstream content, re-apply **three** blocks (see `SECMANUS_VENDOR_PATCHES.md`):

1. **`from collections.abc import Callable`** — add to stdlib imports; remove any `from app.datetime_support import ...` that may have crept in.
2. **`_default_fmt_mtime` module-level function** — pure stdlib fallback formatter (UTC, `"%Y-%m-%d %H:%M:%S"`).
3. **`fmt_timestamp` parameter in `__init__`** — `Callable[[float], str] | None = None`; store as `self._fmt_mtime = fmt_timestamp if fmt_timestamp is not None else _default_fmt_mtime`.
4. **6× call-site replacements** — any inline datetime format or `_fmt_utc_mtime(st.st_mtime)` → `self._fmt_mtime(st.st_mtime)` in `list_directory` and `glob_info`.

**No `from app.*` import should remain in `filesystem.py` after re-apply.**

### 4.5 `backends/local_shell.py` — pass-through

Add `from collections.abc import Callable` and `fmt_timestamp: Callable[[float], str] | None = None` to `__init__`; pass `fmt_timestamp=fmt_timestamp` to `super().__init__(...)`.

### 4.6 `app/backends/composite.py` — injection point (non-vendor, no re-apply needed)

This file is **not** replaced from upstream. It already defines `_fmt_ts` and passes it to every `FilesystemBackend(...)` call. Verify after sync that all new `FilesystemBackend(...)` instantiations in this file also receive `fmt_timestamp=_fmt_ts`.

---

## Phase 5 — Verification

### 5.1 Syntax check (all patched files)

```powershell
cd python-agent-service
python -m py_compile app/_vendor/deepagents/middleware/subagents.py
python -m py_compile app/_vendor/deepagents/backends/filesystem.py
python -m py_compile app/_vendor/deepagents/middleware/summarization.py
```

All must exit 0. Fix any `SyntaxError` before proceeding.

### 5.2 Import check

```powershell
python -c "from app._vendor.deepagents.middleware.subagents import SubAgentMiddleware; print('OK')"
python -c "from app._vendor.deepagents.graph import create_deep_agent; print('OK')"
```

### 5.3 Automated tests

```powershell
cd python-agent-service
python -m pytest tests/ -k "deepagent or subagent or vendor" -x -q 2>&1 | Select-String -NotMatch "^$"
```

If no vendor-specific test tag exists, run the full test suite (or the streaming tests):

```powershell
python -m pytest tests/ -x -q
```

All tests must pass before committing.

---

## Phase 6 — Update patch registry

Open **`middleware/SECMANUS_VENDOR_PATCHES.md`** and:

1. Add a row to the changelog table:

   | Date | Upstream commit / tag | Files updated | Conflicts | Notes |
   |------|-----------------------|---------------|-----------|-------|
   | YYYY-MM-DD | `<upstream-sha>` | `subagents.py`, ... | None / list | ... |

2. Update any patch descriptions that changed during this sync.

---

## Phase 7 — Commit

Stage only vendor files:

```powershell
git add python-agent-service/app/_vendor/deepagents/
git commit -m "chore(vendor): sync deepagents upstream <upstream-sha> + re-apply SECMANUS patches"
```

Tag format: `vendor/deepagents-<YYYYMMDD>-<short-sha>`

---

## Phase 8 — Upstream changes summary

**Goal:** Produce a developer-readable summary of what actually changed in upstream DeepAgents since the last sync. Save it to disk so the team can decide if any consumer code needs updates.

### 8.1 Get the raw diff

```powershell
# Compare vendor tree against pre-sync commit (recorded in Phase 0)
git diff <pre-sync-sha> HEAD -- python-agent-service/app/_vendor/deepagents/ > /tmp/deepagents-upstream-diff.txt
```

### 8.2 Analyze and categorize

Read the diff and classify every change under the following headings. Ignore whitespace-only and comment-only diffs. Ignore lines that are purely SECMANUS PATCH additions (those are our own changes, not upstream).

**Categories to report:**

| Category | What to look for |
|----------|-----------------|
| **New public API** | New `class`, `def` at module/class top level that didn't exist before |
| **Removed / renamed API** | Lines removed from public interface (`class`, `def`, exported names in `__all__`) |
| **Signature changes** | Parameter added/removed/renamed in existing functions |
| **Behavior changes** | Logic changes in function bodies (new branches, changed defaults, error handling) |
| **New dependencies** | New `import` statements in upstream (not our SECMANUS additions) |
| **Config / schema changes** | New keys in TypedDicts, new protocol methods, new fields |
| **base_prompt.md changes** | Any changes to the default agent system prompt |

### 8.3 Output format

Write the summary to:

```
docs/Process/history/deepagents-upstream-changelog-<YYYYMMDD>.md
```

Use this template:

```markdown
# DeepAgents Upstream Changelog — <YYYYMMDD>

**Sync date:** <YYYY-MM-DD>  
**Pre-sync SHA:** `<pre-sync-sha>`  
**Post-sync SHA:** `<post-sync-sha>`  
**Upstream branch:** main  

## Summary

<1-3 sentence high-level description of this upstream release>

## New public API

- `<file>`: `<ClassName / function_name>` — <what it does>

## Removed / renamed API

- `<file>`: `<name>` removed / renamed to `<new_name>`

## Signature changes

- `<file>` → `<function_name>(<old_sig>)` → `(<new_sig>)` — <impact>

## Behavior changes

- `<file>` → `<function_name>`: <description of logic change>

## New upstream dependencies

- `<file>`: `import <module>` added

## Config / schema changes

- `<file>`: `<TypedDict / field>` — <change>

## base_prompt.md changes

<diff summary or "No changes">

## Impact on SecManus

<For each item above, note whether it: (A) requires changes to SECMANUS PATCH blocks, (B) requires changes to consumer code in app/, or (C) is safe to ignore>

## SECMANUS PATCH compatibility

| Patch | Status after this sync |
|-------|----------------------|
| `subagents.py` — SSE bridge | ✅ No conflict / ⚠️ Needs review / ❌ Conflict — see Phase 4 notes |
| `filesystem.py` — fmt_timestamp DI | ✅ / ⚠️ / ❌ |
| `local_shell.py` — fmt_timestamp pass-through | ✅ / ⚠️ / ❌ |
```

### 8.4 Highlight actionable items

After writing the file, **print to chat** a condensed version:

- List any **removed APIs** that SecManus currently imports (grep `app/` for the symbol).
- List any **signature changes** to functions called from `app/agents/deep_agent.py` or `app/backends/`.
- Flag any change to `base_prompt.md` that might conflict with `app/prompts/MASTER_AGENT.md`.
- State clearly: **"No consumer code changes required"** or **"⚠️ Review needed in: <files>"**.

---

## Rollback

If anything breaks after commit:

```powershell
git revert HEAD   # or
git reset --hard <pre-sync-sha>
```

The pre-sync SHA was recorded in Phase 0.

---

## Checklist

```
- [ ] Phase 0: working tree clean; rollback SHA recorded
- [ ] Phase 1: all SECMANUS patches extracted and saved
- [ ] Phase 2: all upstream files downloaded; protected files NOT overwritten blindly
- [ ] Phase 3: diff analysis complete; no unresolved conflicts
- [ ] Phase 4: all patches re-applied with correct markers
- [ ] Phase 5: py_compile + import check + pytest all green
- [ ] Phase 6: SECMANUS_VENDOR_PATCHES.md updated with sync record
- [ ] Phase 7: committed with correct message and tag
- [ ] Phase 8: upstream changelog written to docs/Process/history/; actionable items reported to user
```
