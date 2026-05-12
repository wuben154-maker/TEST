# Acceptance: python-agent-tool-registry-toolspec

## Metadata

| Field | Value |
|-------|-------|
| Slug | `python-agent-tool-registry-toolspec` |
| Related | [proposal.md](./proposal.md), [design.md](./design.md) |
| Last updated | 2026-04-12 |

## Scope reference

- `design.md` — Architecture, `COMMON_TOOL_MOUNTERS`, `ToolSpec`, tiered `create_common_tools()` wiring, testing strategy.

## Environment

- Local: Windows / PowerShell; Python env per `python-agent-service` (see `AGENT.md`).
- Commands run from repo root or `python-agent-service/` as noted in Evidence.

## Functional criteria

| Id | Criterion |
|----|-----------|
| A-01 | `pytest` for `python-agent-service/tests/test_common_tools_from_registry.py`, `test_conversation_history_tool.py`, and `tests/test_common_tool_registry.py` exits 0. |
| A-02 | `COMMON_TOOL_MOUNTERS` keys equal the union of `COMMON_SECURITY_TOOL_ORDER`, `{search_history}`, and `RESEARCH_TOOL_ORDER` (parity test). |
| A-03 | Tiered `create_common_tools()` still mounts security, `search_history`, and research tools via registry mounters without new `common_tools_no_impl` for known names when YAML enables them. |

## Non-functional criteria

| Id | Criterion |
|----|-----------|
| N-01 | No circular import at module load: `common_tool_registry` uses lazy imports inside mounters. |

## Evidence (Phase 6)

| Id | Pass evidence |
|----|----------------|
| A-01 | `python -m pytest tests/test_common_tool_registry.py tests/test_common_tools_from_registry.py tests/test_conversation_history_tool.py -q` → **17 passed**, exit code 0 (from `python-agent-service/`). |
| A-02 | `test_registered_names_cover_security_history_research` asserts `registered_common_tool_names()` equals `COMMON_SECURITY_TOOL_ORDER ∪ RESEARCH_TOOL_ORDER ∪ {search_history}`. |
| A-03 | Same suite exercises `create_common_tools()` / `create_research_tools()` with tiered YAML; behavior unchanged vs pre-refactor. |
| N-01 | `python -c "from app.tools.common_tool_registry import COMMON_TOOL_MOUNTERS"` from `python-agent-service/` → exit 0. |

**Note:** Full `python -m pytest` (614 tests) reported 9 failures in unrelated modules on this workstation; not used as gate for this delivery (scoped tests above are green).

## Sign-off

| Criterion id | Pass/Fail | Verifier | Date | Notes |
|--------------|-----------|----------|------|-------|
| A-01 | Pass | Agent | 2026-04-12 | See Evidence |
| A-02 | Pass | Agent | 2026-04-12 | `test_common_tool_registry.py` |
| A-03 | Pass | Agent | 2026-04-12 | Via A-01 integration tests |
| N-01 | Pass | Agent | 2026-04-12 | Import smoke |
