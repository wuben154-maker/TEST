# Proposal: Web Threat E2B Dynamic Escalation (L4)

## Problem

The current `detect_web_attack` pipeline has three static layers:

- **L1** — YARA rules + entropy scan
- **L2** — AST sink analysis (PHP / JSP / Python / ASPX)
- **L3** — Local interpreter syntax check (`php -l` / `py_compile`) — **only PHP and Python**

Two structural gaps exist:

1. **Language blind spots**: JSP and ASPX have static sink scanners but no L3 equivalent because the host has no Java/ASP.NET runtime. Results are inconclusive for these file types.
2. **Gray-zone findings**: For PHP/Python, L1–L3 may produce medium-severity findings with sub-80% confidence — suspicious but not definitive. Static analysis alone cannot determine whether the code actually executes dangerous behavior.

## Goals

- Add **L4 dynamic analysis** using E2B cloud sandbox, triggered **only** when L1–L3 produce inconclusive results.
- Support **all web file types**: php, python, jsp, aspx, javascript, and unknown.
- Keep L4 **opt-in** via env flag (`WEB_THREAT_E2B_ESCALATION_ENABLED`), default off.
- Preserve the existing pipeline contract — `detect_web_attack` output shape is backward-compatible.

## Non-goals

- Replacing L1–L3 (they remain mandatory and run first).
- Running E2B for clean files or definitively-identified threats.
- Real-time interactive detonation (no UI, no streaming for this delivery).

## Users

Web-security subagent analysts who need deeper evidence when static layers return gray-zone findings.

## Scope

Backend only — `subagents/official/web_security/tools/` and `config/sandbox.yaml`.

## Dependencies

- `E2B_API_KEY` must be set.
- `WEB_THREAT_E2B_ESCALATION_ENABLED=true` must be set.
- E2B base template must include Python 3, bash, `strings`, and optionally `node` / `php`.

## Success metrics

- Escalation fires for JSP/ASPX/unknown files with any findings.
- Escalation fires for PHP/Python gray-zone cases (severity < high OR confidence < 0.80).
- Escalation is skipped when findings are already critical/high with ≥ 0.80 confidence.
- All existing tests continue to pass (no regression on L1–L3).
- New unit tests cover trigger logic and output parsing.
