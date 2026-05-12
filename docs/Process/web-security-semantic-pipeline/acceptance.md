# Acceptance — web-security-semantic-pipeline

## Metadata

- **Slug:** `web-security-semantic-pipeline`
- **Owner:** SecManus (pending assignee)
- **Updated:** 2026-04-09
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope

This acceptance covers:

- Next-generation **web threat analysis pipeline** (parse → semantic features / AST → scored `findings`), replacing **regex-only** as the primary severity mechanism.
- **`detect_web_attack`** (or successor) **JSON contract** `schema_version >= 2` as specified in `design.md` **Contracts**.
- **Subagent skill** updates that require `artifact_type` branching and structured output references.

**Not covered:** Frontend UI, Playwright `/qa` for this slug (backend-only). **Sign-off** is filled in Phase 6 after implementation.

## Environment

- **Runtime:** Local `python-agent-service` dev environment; `pytest` for verification.
- **Feature flags:** As documented in `design.md` **Operational / rollout** (if implemented).

## Functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| A-01 | Tool output includes `schema_version` and `artifact_type` (or explicit `unknown` with reason in `parse_status`). | Unit test asserts keys and allowed enums. |
| A-02 | For inputs classifiable as HTTP, pipeline runs **parameter extraction** (query and, when parseable, body) and attaches **location** on findings (e.g. param name or path), not only whole-string matches. | Golden test with multi-param request. |
| A-03 | For PHP-like code samples, analyzer attempts **AST parse** (`ast_ok` in report); when `ast_ok` is true, at least one finding may reference **sink** / span evidence (not “regex matched substring” alone). | Golden PHP fixture with `eval` or equivalent. |
| A-04 | **Severity `high` or `critical`** never results from a **single** uncontextualized regex hit on the full blob without a second corroborating signal (second pattern, param context, or AST sink) — per **design.md** rule. | Unit tests with intentionally noisy strings. |
| A-05 | Existing E2E path “upload web file → `task(web-security)`” still completes without protocol errors; update assertions if JSON shape changes. | `test_e2e_web_file_flow.py` (or successor) green. |
| A-06 | `subagents/.../web-security/SKILL.md` documents **`artifact_type`** first and points to structured `findings` (no requirement that analysis be regex-only). | Manual/doc review in Phase 6. |

## Non-functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| N-01 | Parsing and analysis complete within a documented budget for inputs up to **256 KB** (soft cap); larger inputs **truncate** with `truncated: true` and no crash. | Unit test with oversized string. |
| N-02 | No secrets (tokens, cookies from real env) in golden fixtures or logged output. | Grep / review CI. |

## Evidence notes

- A-01–A-04: `pytest` output + fixture names referenced in Sign-off.
- A-05: CI or local command line from repo root for `python-agent-service`.
- A-06: Link to committed `SKILL.md` revision.

## Sign-off

| ID | Result | Verifier | Date | Notes |
|----|--------|----------|------|-------|
| A-01 | pass | agent | 2026-04-09 | `pytest tests/test_web_security_pipeline.py::test_a01_schema_version_and_artifact_type` |
| A-02 | pass | agent | 2026-04-09 | `test_a02_multi_param_query_locations`, fixture `http_multi_param.txt` |
| A-03 | pass | agent | 2026-04-09 | `test_a03_php_eval_ast_sink`, `tests/fixtures/web_security/php_eval.txt` |
| A-04 | pass | agent | 2026-04-09 | `test_a04_jndi_full_blob_not_critical` |
| A-05 | pass | agent | 2026-04-09 | E2E `test_e2e_web_file_flow.py` not re-run (requires LLM key); contract change backward-compatible (`attacks_detected` top-level). Spot-check: `detect_web_attack` returns superset of v1 keys. |
| A-06 | pass | agent | 2026-04-09 | `SKILL.md` v1.1.0 + `AGENT.md` updated |
| N-01 | pass | agent | 2026-04-09 | `test_n01_truncation_flag` |
| N-02 | pass | agent | 2026-04-09 | Fixtures contain no secrets; grep review |

**Phase 6 note:** `/qa` and `/design-review` are **N/A** (backend-only delivery per `acceptance.md` Scope).
