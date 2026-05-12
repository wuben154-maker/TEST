# Proposal — `observability-logging-standards`

## Metadata

- **Slug:** `observability-logging-standards`
- **Author:** Agent
- **Created:** 2026-04-16
- **Status:** draft

## Problem

The current codebase lacks the observability infrastructure required for an AI Agent to automatically analyze production logs and diagnose/fix bugs. Key gaps:

1. **No request-level correlation** — `ContextVar` holds `user_id`/`project_id`/`request_id` but structlog is not configured with `merge_contextvars`, so these fields are absent from most log lines. An AI Agent cannot trace a single request end-to-end.
2. **No HTTP access logging** — No middleware records `method`, `path`, `status_code`, `latency_ms`. Error rate trends and slow endpoints are invisible.
3. **Silent exceptions** — `deep_agent.py` has 10+ bare `except Exception: pass` blocks that swallow errors without any log. These are debugging black holes.
4. **Inconsistent event naming** — Mix of English sentences (`"Received analysis request"`) and snake_case keys (`billing_gate_load_failed`). AI Agents need stable, enumerable event names for pattern matching.
5. **open_deep_research has no structlog** — Uses raw `logging.getLogger(__name__)` with only one `logger.warning` call. No structured fields, no request correlation.
6. **No logging standards in AGENT.md** — No project-wide convention for log levels, event naming, or required fields.
7. **Vendor log format mismatch** — `_vendor/deepagents` uses stdlib `logging` with plain text, mixing with the app's JSON output.

## Goals

1. Enable request-level log correlation across the entire analysis pipeline (including deep-research subgraph).
2. Establish and enforce a project-wide logging standard (event naming, required fields, level usage).
3. Add HTTP access logging middleware with structured fields.
4. Eliminate all silent `except: pass` in our own code (not vendor).
5. Optimize `open_deep_research_original` module with proper structlog, request correlation, and remove unnecessary file-based logs.
6. Unify vendor log output format via `ProcessorFormatter`.
7. Document all conventions in `AGENT.md` so future developers and AI Agents share the same contract.

## Non-goals

- Frontend error reporting (Sentry integration) — separate delivery.
- External log sinks (ELK/Loki/CloudWatch) — deployment-specific, deferred.
- Performance metrics / Web Vitals — separate delivery.
- Modifying `_vendor/deepagents` source code — vendor code, only configure formatters externally.

## Users

- **AI Agent (primary)**: Automated log analysis, root-cause diagnosis, and bug-fix proposal.
- **Developers**: Local debugging and production troubleshooting.
- **Ops / SRE**: Production monitoring and alerting.

## Scope

- Backend only (`python-agent-service/`).
- Touches: `app/main.py`, `app/agents/deep_agent.py`, `app/agents/research/open_deep_research_original/`, `app/agents/research/open_deep_research_original_adapter.py`, `AGENT.md`.
- New file: `app/middleware/request_logging.py` (HTTP access log middleware).

## Dependencies

- `structlog` (already installed, ≥ 24.4.0).
- No new external dependencies.

## Success metrics

| Metric | Target |
|--------|--------|
| Every log line from `app/` contains `request_id` when in analyze scope | 100% |
| All `except: pass` in non-vendor code replaced with at least `logger.debug` | 0 silent catches |
| `open_deep_research` uses structlog with request correlation | Yes |
| HTTP access log middleware emits structured JSON per request | Yes |
| `AGENT.md` has logging standards section | Yes |
| All event names in touched files follow snake_case convention | Yes |
