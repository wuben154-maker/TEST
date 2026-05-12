# Acceptance: Web Threat E2B Dynamic Escalation (L4)

## Scope

Backend only. No UI criteria.

## Acceptance Criteria

| ID | Criterion | Verifiable by |
|----|-----------|--------------|
| AC-01 | When `WEB_THREAT_E2B_ESCALATION_ENABLED=false` (default), `layers.e2b == "disabled"` for all inputs | Unit test: env unset |
| AC-02 | JSP file with any L1–L2 finding → `should_escalate` returns `True`, reason starts with `l3_blind:jsp` | Unit test: mock findings + lang=jsp |
| AC-03 | ASPX file with any finding → `should_escalate` returns `True`, reason starts with `l3_blind:aspx` | Unit test: mock findings + lang=aspx |
| AC-04 | PHP file, severity=critical, confidence=0.90 → `should_escalate` returns `False` (definitive, skip) | Unit test: high-conf findings |
| AC-05 | PHP file, severity=medium, confidence=0.55 → `should_escalate` returns `True` (gray zone) | Unit test: gray-zone findings |
| AC-06 | No findings from L1–L3 → `should_escalate` returns `False` regardless of language | Unit test: empty findings list |
| AC-07 | E2B sandbox stdout containing `uid=0` → Finding with `id="e2b-rce-confirmed"`, severity=critical, layer=L4 | Unit test: mock output |
| AC-08 | E2B sandbox stdout containing `Runtime.exec` (JSP strings) → Finding with severity=high, layer=L4 | Unit test: mock output |
| AC-09 | E2B execution error (exception) → `layers.e2b == "error"`, no crash | Unit test: mock exception |
| AC-10 | `LayerId` now accepts `"L4"` without Pydantic validation error | Unit test: Finding(layer="L4") |
| AC-11 | All existing `test_web_threat_*.py` tests pass (no L1–L3 regression) | `pytest tests/test_web_threat*.py` |
| AC-12 | `detect_web_attack()` output still includes legacy top-level fields (`attacks_detected`, `severity`) | Existing tests cover this |

## Sign-off

| ID | Status | Evidence | Notes |
|----|--------|---------|-------|
| AC-01 | PASS | `test_should_escalate_disabled_by_default` | |
| AC-02 | PASS | `test_should_escalate_jsp_any_finding` | |
| AC-03 | PASS | `test_should_escalate_aspx_any_finding` | |
| AC-04 | PASS | `test_should_not_escalate_definitive_php` | |
| AC-05 | PASS | `test_should_escalate_gray_zone_php` | |
| AC-06 | PASS | `test_should_not_escalate_no_findings` | |
| AC-07 | PASS | `test_analyse_output_rce_uid` | |
| AC-08 | PASS | `test_analyse_output_java_exec_string` | |
| AC-09 | PASS | `test_run_e2b_dynamic_handles_exception` | |
| AC-10 | PASS | `test_layer_id_l4_accepted` + `test_analysis_layers_status_e2b_fields` | |
| AC-11 | PASS | `pytest test_web_threat_yara_sandbox.py test_web_security_pipeline.py` → 15 passed | |
| AC-12 | PASS | Existing `test_detect_web_attack_legacy_top_level` green | |
