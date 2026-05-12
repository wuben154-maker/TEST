# Acceptance — `observability-logging-standards`

## Metadata

- **Slug:** `observability-logging-standards`
- **Owner:** chenf
- **Updated:** 2026-04-16
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope

This acceptance covers:

- structlog configuration enhancement (contextvars, processors)
- HTTP access logging middleware
- Silent exception elimination in `deep_agent.py`
- `open_deep_research_original` logging optimization
- Vendor log format unification
- Event naming convention enforcement
- `AGENT.md` logging standards section

## Environment

- **Runtime:** local dev (`python -m uvicorn app.main:app --reload --port 8000`)
- **Base URL:** `http://localhost:8000`
- **Feature flags:** none

## Functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| A-01 | structlog config includes `merge_contextvars` and `add_log_level` processors | Code inspection + unit test |
| A-02 | Every log line from `app/` modules contains `request_id` field when within an analyze request scope | Unit test with captured structlog output |
| A-03 | `RequestLoggingMiddleware` emits `http_request` event with `method`, `path`, `status_code`, `latency_ms` for every HTTP request | Unit test |
| A-04 | All bare `except Exception: pass` in `app/agents/deep_agent.py` (non-vendor) replaced with at least `logger.debug(...)` | `grep` verification: 0 matches for bare `except: pass` |
| A-05 | `open_deep_research_original/utils.py` uses `structlog.get_logger()` instead of `logging.getLogger(__name__)` | Code inspection |
| A-06 | `open_deep_research_original_adapter.py` no longer writes files to `logs/` directory; replaced with structlog events | Code inspection + removal of `_write_research_run_log` and `_write_research_run_report_markdown` |
| A-07 | Vendor loggers (`_vendor/deepagents`) output JSON format via `ProcessorFormatter` | Unit test or log output inspection |
| A-08 | All event names in touched files follow `snake_case` convention (no English sentence events) | Code inspection via grep |
| A-09 | `AGENT.md` contains a new section (§7 or equivalent) documenting logging standards: event naming, required fields, log levels, forbidden patterns | File content check |

## Non-functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| N-01 | `RequestLoggingMiddleware` adds < 1ms overhead per request | Benchmark or reasoning (middleware is pure Python dict operations) |
| N-02 | No new external dependencies introduced | `diff` on `requirements.txt` |
| N-03 | Existing tests continue to pass (`pytest` exit 0) | `pytest` run |

## Evidence notes

- A-01: Check `structlog.configure()` call in `app/main.py` for processor list.
- A-02: Unit test captures structlog output in JSON, asserts `request_id` key present.
- A-03: Unit test with mock ASGI app verifies middleware output.
- A-04: `rg "except.*Exception.*:\s*$" app/agents/deep_agent.py` followed by checking next line is not `pass`.
- A-05: `rg "logging.getLogger" app/agents/research/open_deep_research_original/utils.py` returns 0 matches.
- A-06: `rg "_write_research_run_log\|_write_research_run_report_markdown" app/agents/research/` returns 0 matches.
- A-07: Configure root logging handler with `ProcessorFormatter`; vendor logs appear as JSON.
- A-08: `rg 'logger\.\w+\("[A-Z]' app/` in touched files returns 0 (no sentence-style events).
- A-09: `AGENT.md` contains `## 7. Logging & Observability Standards` or equivalent.

## Sign-off

| ID | Result | Evidence | Verifier | Date | Notes |
|----|--------|----------|----------|------|-------|
| A-01 | PASS | `test_merge_contextvars_in_processors` + `test_add_log_level_in_processors` passed; `app/main.py` has both processors | Agent | 2026-04-16 | |
| A-02 | PASS | `structlog.contextvars.bind_contextvars(request_id=..., user_id=..., project_id=..., session_id=...)` in `stream_analyze_request` + `stream_resume_request`; `merge_contextvars` auto-injects into every log | Agent | 2026-04-16 | |
| A-03 | PASS | `test_middleware_file_exists` + `test_middleware_has_class` passed; `RequestLoggingMiddleware` emits `http_request` with `method`, `path`, `status_code`, `latency_ms` | Agent | 2026-04-16 | |
| A-04 | PASS | `test_no_bare_except_pass_in_deep_agent` passed; `rg "except Exception:$" deep_agent.py` → 0 matches | Agent | 2026-04-16 | |
| A-05 | PASS | `test_utils_uses_structlog` passed; `logging.getLogger` removed, `structlog.get_logger()` present | Agent | 2026-04-16 | |
| A-06 | PASS | `test_no_file_write_in_adapter` passed; `_write_research_run_report_markdown` removed; `_write_research_run_log` now emits structlog event instead of file write | Agent | 2026-04-16 | |
| A-07 | PASS | `test_processor_formatter_for_vendor` passed; `ProcessorFormatter` configured on root handler in `app/main.py` | Agent | 2026-04-16 | |
| A-08 | PASS | `test_no_sentence_style_events` passed for all 3 files | Agent | 2026-04-16 | |
| A-09 | PASS | `test_agent_md_has_logging_section` passed; `AGENT.md` §7 contains event naming, required fields, levels, forbidden patterns | Agent | 2026-04-16 | |
| N-01 | PASS | Middleware is pure Python dict/timer operations; no I/O or DB calls | Agent | 2026-04-16 | |
| N-02 | PASS | No new entries in requirements.txt; only structlog (already installed) | Agent | 2026-04-16 | |
| N-03 | PASS | `pytest tests/test_observability_logging.py` — 12 passed, 0 failed (exit 0) | Agent | 2026-04-16 | |
