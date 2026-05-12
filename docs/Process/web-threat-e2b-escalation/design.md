# Design: Web Threat E2B Dynamic Escalation (L4)

## Metadata

- **slug**: web-threat-e2b-escalation
- **overview**: Add L4 E2B dynamic sandbox, triggered only when L1–L3 static analysis is inconclusive.

## Todo list

- [x] **docs** — proposal.md + design.md + acceptance.md
- [ ] **layer-env** — add `e2b_escalation_enabled()` + `e2b_escalation_confidence_threshold()` to `layer_env.py`
- [ ] **models** — extend `LayerId` to include `"L4"`; add `e2b`, `e2b_detail`, `e2b_trigger_reason` to `AnalysisLayersStatus`
- [ ] **e2b-layer** — create `e2b_dynamic_layer.py` with `should_escalate()` + `run_e2b_dynamic()`
- [ ] **pipeline** — wire L4 call after L3 in `pipeline.py`
- [ ] **config** — add `web-dynamic` template to `sandbox.yaml`; add `WEB_THREAT_E2B_ESCALATION_ENABLED` to `.env.example`
- [ ] **tests** — `test_web_threat_e2b_escalation.py` covering trigger logic + output parsing
- [ ] **skill** — update `SKILL.md` to document `parse_status.layers.e2b` field

## Architecture

```
analyze_web_threat(request_data, hint)
  │
  ├─ classify_artifact()         → artifact_type
  │
  ├─ [http branch] analyze_traffic_params()
  │
  └─ [code branch]
       ├─ L1: yara_layer + entropy_findings       → findings[], layers.yara/entropy
       ├─ L2: scan_hosted_code()                  → findings[], lang
       ├─ L3: run_syntax_sandbox() [php/python]   → findings[], layers.sandbox
       └─ L4: run_e2b_dynamic()   [conditional]   → findings[], layers.e2b
                │
                └─ Trigger: should_escalate(findings, lang, l3_status, artifact_type)
```

## Trigger Logic

```python
def should_escalate(findings, lang, artifact_type) -> (bool, str):

    # 1. No E2B key or feature disabled → always skip
    if not e2b_api_key or not e2b_escalation_enabled():
        return False, "disabled"

    # 2. HTTP traffic artifacts → never escalate (no code to run)
    if artifact_type == "http_traffic":
        return False, "http_traffic"

    # 3. No findings from L1–L3 → clean, skip
    if not findings:
        return False, "no_findings"

    # 4. Language L3 cannot handle → escalate on any finding
    if lang in ("jsp", "aspx", "unknown", ""):
        return True, f"l3_blind:{lang or 'unknown'}"

    # 5. PHP/Python: definitive result → skip (save cost)
    max_conf = max(f.confidence for f in findings)
    max_sev_rank = _severity_rank(findings)   # critical=4, high=3, medium=2 …
    threshold = e2b_escalation_confidence_threshold()  # default 0.80

    if max_sev_rank >= RANK_HIGH and max_conf >= threshold:
        return False, "definitive_result"

    # 6. Gray zone: suspicious but inconclusive
    if max_sev_rank >= RANK_MEDIUM:
        return True, f"gray_zone:sev_rank={max_sev_rank},conf={max_conf:.2f}"

    return False, "low_severity"
```

## Per-language Analysis Strategy in E2B

| Language | Method | Command |
|----------|--------|---------|
| `php` | Execute + capture | `timeout 8 php {path} 2>&1 \| head -200` |
| `python` | Execute + capture | `timeout 8 python3 {path} 2>&1 \| head -200` |
| `javascript` | Execute + capture | `timeout 8 node {path} 2>&1 \| head -200` (fallback: strings) |
| `jsp` | Strings extraction | `strings {path} \| grep -Ei 'runtime.exec\|ProcessBuilder\|/bin/sh\|exec[(]' \| head -50` |
| `aspx` | Strings extraction | `strings {path} \| grep -Ei 'Process.Start\|Invoke\|cmd.exe\|powershell\|eval' \| head -50` |
| `unknown` | File + strings | `file {path}; strings {path} \| head -100` |

## Suspicious Output Patterns → Finding Severity

| Pattern | Severity | Confidence | Signal name |
|---------|---------|-----------|-------------|
| `uid=\d+` / `root:x:0` (RCE confirmed) | critical | 0.92 | `rce_confirmed_dynamic` |
| `/etc/passwd`, `/etc/shadow` read | critical | 0.90 | `sensitive_file_read` |
| `Runtime.exec` / `ProcessBuilder` in strings | high | 0.78 | `java_exec_string` |
| `Process.Start` / `powershell` in strings | high | 0.78 | `dotnet_exec_string` |
| `exec(` / `system(` / `eval(` in dynamic output | high | 0.75 | `dyn_exec_observed` |
| `base64_decode` / `gzinflate` in strings | medium | 0.60 | `obfuscation_string` |
| Non-zero exit code + unexpected output | medium | 0.55 | `unexpected_output` |

## Contracts

### New env vars

| Var | Default | Effect |
|-----|---------|--------|
| `WEB_THREAT_E2B_ESCALATION_ENABLED` | `false` | Enable L4 |
| `WEB_THREAT_E2B_CONFIDENCE_THRESHOLD` | `0.80` | Confidence above which L4 is skipped (definitive) |

### Output shape additions (backward compatible)

```python
# parse_status.layers (AnalysisLayersStatus)
{
  "yara": "ok",
  "entropy": "ok",
  "sandbox": "clean",           # L3 (unchanged)
  "sandbox_detail": "...",
  "e2b": "suspicious",          # L4: skipped | disabled | clean | suspicious | error | skipped:<reason>
  "e2b_detail": "uid=0(root)",  # truncated E2B stdout/stderr
  "e2b_trigger_reason": "l3_blind:jsp"  # why L4 was triggered
}
```

`LayerId` extended to `Literal["L1", "L2", "L3", "L4"]` — existing `L3` findings unaffected.

### Finding shape (L4 findings)

```python
Finding(
    id="e2b-rce-confirmed",      # stable id
    category="rce",              # or "webshell"
    severity="critical",
    confidence=0.92,
    layer="L4",                  # new value
    evidence=Evidence(
        snippet="uid=0(root)",
        location="L4:e2b:dynamic:php",
    ),
    signals=[Signal(type="sandbox_trace", name="rce_confirmed_dynamic", weight=1.0)],
)
```

## Edge Cases & Errors

| Scenario | Behaviour |
|----------|-----------|
| E2B API key missing | `layers.e2b = "skipped:no_api_key"`, no findings |
| E2B sandbox creation fails | `layers.e2b = "error"`, detail = exc message |
| Command timeout (> 8s) | `layers.e2b = "error"`, detail = "timeout" |
| Output is empty | `layers.e2b = "clean"`, no additional findings |
| L4 disabled by env | `layers.e2b = "disabled"` |

## Code Touch List

| Path | Change |
|------|--------|
| `subagents/official/web_security/tools/layer_env.py` | Add `e2b_escalation_enabled()`, `e2b_escalation_confidence_threshold()` |
| `subagents/official/web_security/tools/models.py` | `LayerId` += `"L4"`; `AnalysisLayersStatus` += e2b fields |
| `subagents/official/web_security/tools/e2b_dynamic_layer.py` | **NEW** — trigger + execution + output analysis |
| `subagents/official/web_security/tools/pipeline.py` | Import + call L4 after L3 block |
| `config/sandbox.yaml` | Add `web-dynamic` template |
| `python-agent-service/.env.example` | Document `WEB_THREAT_E2B_ESCALATION_ENABLED` |
| `subagents/official/web_security/skills/web_security/SKILL.md` | Document `layers.e2b` |
| `tests/test_web_threat_e2b_escalation.py` | **NEW** — unit tests |

## Implementation Order

1. `models.py` (contracts) → 2. `layer_env.py` (toggles) → 3. `e2b_dynamic_layer.py` (core) → 4. `pipeline.py` (wire) → 5. `sandbox.yaml` + `.env.example` → 6. tests → 7. SKILL.md

## Testing Strategy

- **Unit tests** (no E2B network): mock `AsyncSandbox.create`, patch `E2B_API_KEY`, assert trigger conditions and finding generation.
- **Trigger-only tests**: verify `should_escalate()` returns correct `(bool, reason)` for all combinations of lang × severity × confidence.
- **Output analysis tests**: feed synthetic stdout strings, assert correct Finding severity/confidence.
- **Regression**: existing `test_web_threat_*.py` must remain green — no L1–L3 behavior changes.

## Mockups deferred

Backend-only delivery. No UI changes. Mockups skipped by design.
