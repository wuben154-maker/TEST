# Acceptance — `log-persistence-configurable`

## Metadata

- **Slug:** `log-persistence-configurable`
- **Owner:** chenf
- **Updated:** 2026-04-16
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope

- Backend log sink configuration (stdout / file / both)
- Backend `/api/client-errors` endpoint
- Frontend remote error sink

## Environment

- **Runtime:** local dev (python + vite)
- **Base URL:** `http://localhost:8000`
- **Feature flags:** `LOG_SINK` env var

## Functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| A-01 | `LOG_SINK=stdout` (default): no file handler created, logs only go to stdout | Unit test |
| A-02 | `LOG_SINK=file`: RotatingFileHandler created, writes JSON lines to configured path | Unit test |
| A-03 | `LOG_SINK=both`: both StreamHandler and RotatingFileHandler active | Unit test |
| A-04 | Log file auto-rotates when exceeding `LOG_FILE_MAX_BYTES` | Unit test / config inspection |
| A-05 | `POST /api/client-errors` with valid payload returns 204 | pytest integration |
| A-06 | `POST /api/client-errors` with invalid payload returns 422 | pytest integration |
| A-07 | `POST /api/client-errors` rate limit (>10 req/min per IP) returns 429 | pytest integration |
| A-08 | Frontend remoteSink batches entries and POSTs when buffer reaches batchSize | Vitest |
| A-09 | Frontend remoteSink flushes on timer (5s interval) | Vitest |
| A-10 | Frontend remoteSink handles network failure gracefully (no crash) | Vitest |
| A-11 | remoteSink only registered in production mode (not dev) | Code review |

## Non-functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| N-01 | Zero new third-party dependencies (both backend and frontend) | package.json / requirements.txt diff |
| N-02 | Default behavior (LOG_SINK=stdout) unchanged — existing deployments unaffected | Unit test |
| N-03 | All existing tests pass (no regression) | `npm run test` + `pytest` |

## Sign-off

| ID | Result | Evidence | Verifier | Date | Notes |
|----|--------|----------|----------|------|-------|
| A-01 | PASS | `test_default_is_stdout` + `test_stdout_handler_conditional` passed | Agent | 2026-04-16 | |
| A-02 | PASS | `test_log_sink_file_accepted` + `test_file_handler_conditional` + `test_rotating_file_handler_used` passed | Agent | 2026-04-16 | |
| A-03 | PASS | `test_log_sink_both_accepted` + source confirms both handlers | Agent | 2026-04-16 | |
| A-04 | PASS | `test_log_file_defaults` = 10MiB max + 5 backups; `RotatingFileHandler` handles rotation | Agent | 2026-04-16 | |
| A-05 | PASS | `test_valid_payload_returns_204` + `test_empty_errors_returns_204` passed | Agent | 2026-04-16 | |
| A-06 | PASS | `test_invalid_payload_returns_422` + `test_too_many_entries_returns_422` passed | Agent | 2026-04-16 | |
| A-07 | PASS | `test_rate_limit_returns_429` — 11th request within 60s returns 429 | Agent | 2026-04-16 | |
| A-08 | PASS | `batches entries up to batchSize then flushes` — Vitest passed | Agent | 2026-04-16 | |
| A-09 | PASS | `flushes on timer interval` — Vitest passed (5s fake timer) | Agent | 2026-04-16 | |
| A-10 | PASS | `handles network failure without crashing` — Vitest passed | Agent | 2026-04-16 | |
| A-11 | PASS | `src/main.tsx`: `if (!import.meta.env.DEV) { logger.addSink(...) }` — code review | Agent | 2026-04-16 | |
| N-01 | PASS | No new deps in `package.json` or `requirements.txt` — stdlib `RotatingFileHandler` + native `fetch` | Agent | 2026-04-16 | |
| N-02 | PASS | `test_default_is_stdout` — default LOG_SINK=stdout, no file handler added | Agent | 2026-04-16 | |
| N-03 | PASS | pytest 15/15, Vitest 255/255 — zero regression | Agent | 2026-04-16 | |
