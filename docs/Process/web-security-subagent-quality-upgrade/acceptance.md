# Acceptance — web-security-subagent-quality-upgrade

## Metadata

- **Slug:** `web-security-subagent-quality-upgrade`
- **Owner:** (assign)
- **Updated:** 2026-04-25
- **Related:** [proposal.md](./proposal.md), [design.md](./design.md)

## Scope

This acceptance covers:

- `detect_web_attack` input contract for raw content and `/workspace/...` file paths.
- Owner-scoped backend file reading through DeepAgents runtime backend.
- Web artifact normalization and traffic/code branch detection.
- Structured evidence, risk score, and security stats derivation.
- `web-security` subagent SOP and flow tests.

## Environment

- **Runtime:** Local Python Agent Service test environment.
- **Entrypoints:** `detect_web_attack` tool, `analyze_web_threat` pipeline, and `stream_analyze_request` / `/analyze` flow tests.
- **Feature flags:** Existing `WEB_THREAT_*` flags remain respected. E2B remains optional and skipped unless configured.
- **External services:** No live external target scanning required.

## Functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| A-01 | `detect_web_attack` accepts exactly one input source: `request_data` or `file_path`. Passing both returns a structured `ambiguous_input` error; passing neither returns `missing_input`. | Unit test in web-security tool tests |
| A-02 | `detect_web_attack(file_path="/workspace/shell.php", hint="code")` reads content through the runtime backend and detects the same PHP sink findings as direct raw-content mode. | Unit test with fake backend/runtime |
| A-03 | File-path mode never uses local filesystem path conversion or exposes physical owner-scoped paths in returned output. | Unit test + output assertion |
| A-04 | Backend read failure for `file_path` returns a structured `file_read_failed` result and does not instruct or attempt `ls`/`glob` fallback; UTF-8 decode failures fall back to raw byte download and safe decoding. | Unit test |
| A-05 | URL-only encoded XSS input is classified/analyzed and produces a finding with a query-parameter evidence location. | Unit test |
| A-06 | Access-log or WAF-log input containing encoded XSS/SQLi is normalized and produces field-level evidence rather than clean `unknown`. | Unit test |
| A-07 | JSON request body payloads are expanded into structured locations such as `body.json:<path>` and scanned for SQLi/XSS. | Unit test |
| A-08 | Header and cookie payloads are scanned and attributed to `header:<name>` or `cookie:<name>` evidence locations. | Unit test |
| A-09 | Hosted-code analysis includes first-pass JS/HTML/TS surface coverage for DOM XSS or execution sinks without regressing PHP/JSP/Python/ASPX scanners. | Unit tests with fixtures |
| A-10 | `findings[]` include severity, confidence, evidence location, signals, and risk score where applicable; webshell outputs can include `decoded_artifacts[]`, `capabilities[]`, `iocs[]`, `mitre_attack[]`, and `recommended_actions[]` across PHP/Python/JSP/ASPX/JS/HTML where supported; legacy top-level fields remain present. | Schema/output unit test |
| A-11 | Security stats derivation can produce severity, risk score, threat classes, validation dimensions, and actionable counts from web-security tool output or subagent stats JSON. | `stats_meta` unit test |
| A-12 | Uploaded or workspace `.php` Web files route to `web-security` and the subagent calls `detect_web_attack(file_path=...)`. | Flow/E2E test |
| A-13 | `web-security` final report cites structured evidence locations for high/critical findings and preserves detailed tool-derived findings. | Flow/E2E assertion or golden output check |
| A-14 | Existing `detect_web_attack(request_data=...)` callers and renderer tests remain compatible. | Existing regression tests |

## Non-functional criteria

| ID | Criterion | Verification |
|----|-----------|--------------|
| N-01 | Input processing remains bounded by existing `MAX_INPUT_BYTES`; truncated inputs mark truncation in source/parse metadata. | Unit test |
| N-02 | File-path reads preserve tenant isolation by using backend routing for `/workspace/` paths. | Unit test/fake backend assertion and code review |
| N-03 | No secrets or full cookies/tokens are logged; snippets are truncated in findings/renderers. | Test or code review |
| N-04 | E2B dynamic analysis behavior remains gated by existing `WEB_THREAT_E2B_*` flags and absent API key does not fail baseline analysis. | Existing + focused pytest |
| N-05 | Added normalization/scanning does not introduce heavy new runtime dependencies unless explicitly approved. | Dependency review |

## Evidence notes

- A-01 to A-04: expected to map to `websec-tool-runtime-file-input`.
- A-05 to A-08: expected to map to `websec-normalized-artifacts` and `websec-traffic-detectors`.
- A-09: expected to map to `websec-code-branch-js-html`.
- A-10 to A-11: expected to map to `websec-risk-scoring` and deterministic webshell analysis.
- A-12 to A-13: expected to map to `websec-e2e-tighten`.
- A-14: focused regression command should include existing web-security pipeline/renderer tests.

## Sign-off

Outcome: **BLOCKED** for automatic completion because `tests/test_e2e_web_file_flow.py`
requires live LLM calls and both E2E scenarios failed before assertions with
Gemini `RESOURCE_EXHAUSTED` / monthly spending cap 429. Backend/unit verification
passed.

| ID | Result | Evidence | Verifier | Date | Notes |
|----|--------|----------|----------|------|-------|
| A-01 | PASS | `python -m pytest tests/test_web_security_quality_upgrade.py -q` | Agent | 2026-04-25 | Ambiguous/missing input covered. |
| A-02 | PASS | `tests/test_web_security_quality_upgrade.py::test_detect_web_attack_reads_workspace_file_via_runtime_backend`; `test_detect_web_attack_normalizes_workspace_path_variants`; `test_detect_web_attack_tool_runtime_is_injected_argument` | Agent | 2026-04-25 | Fake runtime backend proves backend read path; tool runtime is injected; common `Workspace/...` path variants are normalized. |
| A-03 | PASS | `test_detect_web_attack_reads_workspace_file_via_runtime_backend` + code review | Agent | 2026-04-25 | Returned source path is virtual `/workspace/...`. |
| A-04 | PASS | `test_detect_web_attack_file_read_failure_is_structured`; `test_detect_web_attack_falls_back_to_bytes_for_non_utf8_file` | Agent | 2026-04-25 | No fallback path discovery; non-UTF-8 PHP text falls back to scoped raw-byte download and remains analyzable. |
| A-05 | PASS | `test_url_only_encoded_xss_is_detected_with_query_location` | Agent | 2026-04-25 | Evidence location `query:q`. |
| A-06 | PASS | `test_access_log_encoded_xss_is_detected_with_log_location` | Agent | 2026-04-25 | Evidence location `log.request_uri:q`. |
| A-07 | PASS | `test_json_body_sqli_is_detected_with_json_location` | Agent | 2026-04-25 | Evidence location `body.json:password`. |
| A-08 | PASS | `test_header_and_cookie_payloads_are_scanned` | Agent | 2026-04-25 | Header and cookie locations covered. |
| A-09 | PASS | `test_js_html_dom_xss_sink_is_detected`; `tests/test_web_security_pipeline.py` | Agent | 2026-04-25 | JS/HTML added; PHP/JSP/Python/ASPX regression passed. |
| A-10 | PASS | `test_findings_include_risk_score_for_actionable_items`; `test_detect_web_attack_decodes_php_payload_and_extracts_behavior`; `test_detect_web_attack_extracts_python_webshell_intel`; `test_detect_web_attack_extracts_jsp_webshell_intel`; `test_detect_web_attack_extracts_aspx_webshell_intel`; renderer tests | Agent | 2026-04-27 | Legacy top-level fields remain; PHP decoded payloads and Python/JSP/ASPX webshell code produce structured capabilities, IOCs, and MITRE mappings. |
| A-11 | PASS | `python -m pytest tests/test_stats_meta.py -q` | Agent | 2026-04-25 | `risk_score`/threat classes/actionable derive from findings. |
| A-12 | BLOCKED | `python -m pytest tests/test_e2e_upload_to_llm_first_message.py::test_upload_five_files_then_first_llm_input_snapshot -q` passed for pre-LLM manifest path contract; `python -m pytest tests/test_e2e_web_file_flow.py -q` remains blocked | Agent | 2026-04-25 | Manifest now exposes `/workspace/<stored_filename>` and explicitly instructs `detect_web_attack(file_path=...)`; live LLM route assertion remains blocked by Gemini 429 spending cap. |
| A-13 | BLOCKED | `python -m pytest tests/test_e2e_web_file_flow.py -q` | Agent | 2026-04-25 | External Gemini 429 before final report assertions. |
| A-14 | PASS | `tests/test_web_security_pipeline.py`; `tests/test_detect_web_attack_renderer.py` | Agent | 2026-04-25 | Raw `request_data` compatibility preserved. |
| N-01 | PASS | `tests/test_web_security_pipeline.py::test_n01_truncation_flag` | Agent | 2026-04-25 | Truncation flag covered. |
| N-02 | PASS | `test_detect_web_attack_reads_workspace_file_via_runtime_backend`; `test_detect_web_attack_normalizes_workspace_path_variants` + code review | Agent | 2026-04-25 | Backend routing used for canonicalized file mode. |
| N-03 | PASS | Code review + snippet truncation assertions in scanner tests | Agent | 2026-04-25 | Findings snippets bounded; no full cookie logging added. |
| N-04 | PASS | `python -m pytest tests/test_web_threat_e2b_escalation.py -q` | Agent | 2026-04-25 | E2B remains flag-gated and optional. |
| N-05 | PASS | Dependency review | Agent | 2026-04-25 | No new runtime dependencies added. |
