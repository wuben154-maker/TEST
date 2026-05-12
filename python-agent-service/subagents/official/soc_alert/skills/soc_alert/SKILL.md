---
name: soc-alert
display_name: SOC Alert Analyst
description: Standard SOC alert triage workflow for SIEM and EDR investigations.
version: 2.0.0
author: security-team
triggers:
  - alert
  - siem
  - soc
  - incident
  - event
  - splunk
  - elastic
  - sentinel
  - qradar
  - crowdstrike
  - edr
  - detection
  - triage
  - mitre
  - att&ck
  - kill chain
  - ioc
  - correlation
  - investigation
  - playbook
tags:
  - soc
  - incident-response
  - triage
  - siem
priority: 10
max_iterations: 12
timeout_seconds: 120
---

# SOC Alert Standard Skill

This skill defines the standard `soc-alert` subagent triage process. Use it when the task is alert triage, SIEM correlation, or incident prioritization.

This is a standard skill-driven flow. Do not assume a compiled subagent runtime.

## Skill activation checklist

- The task contains one or more alerts, detections, or SOC investigation questions.
- You need to classify severity/priority or determine true/false positive likelihood.
- You need IOC enrichment, telemetry correlation, or MITRE ATT&CK mapping.

## Required execution contract

Execute the following stages in order. Read each stage file before running the stage logic.

1. `stages/node1_analysis.md`
2. `stages/node2_planning.md`
3. `stages/node3_solve.md`
4. **Tool `execute_soc_solve_plan`** — pass the node3 JSON as `solve_plan` (plus `raw_alert_context` / scope fields when available). This runs the fixed executor (auth + vendor APIs). No LLM node4.
5. `stages/node5_judge.md`

Hard sequencing rules (must follow):

- Complete LLM stages strictly in order: node1 -> node2 -> node3.
- Immediately after valid node3 JSON, **call** `execute_soc_solve_plan` once with that object. Do not simulate execution in prose and do not call per-item generic action tools for rows already in the solve plan unless the executor fails and the skill explicitly directs a fallback.
- Use the **tool return value** (soc_execution_v1) verbatim as `execution_result` when applying node5. Do not output the final triage conclusion before node5 is completed.
- Do not skip node1, node2, or node3. Do not skip the automated execution step (the executor may record per-item failures; that still counts as execution completed for node5).
- If an LLM stage is blocked (for example, missing data), output a structured blocked result for that stage, then continue with explicit uncertainty; for node3, still emit valid script-parseable JSON where possible (use `generic_action: null` for non-automatable items).

For each stage:

- Follow the instructions from the stage file.
- Keep outputs structured and reusable by the next stage.
- Preserve uncertainty; do not fabricate telemetry.

## Tool usage policy

Use the SOC API tools only when they materially reduce uncertainty.

- **`execute_soc_solve_plan` is mandatory** once node3 JSON is ready; it replaces ad-hoc node4 LLM work and drives auth + API execution for all planned sub-questions.
- Prefer targeted, hypothesis-driven tool calls over broad collection.
- Capture why each tool was called and how it affected confidence.
- If a tool fails, continue with available evidence and record the gap.
- Do not call tools that are irrelevant to the alert scope.

## Evidence and confidence rules

- Every major conclusion must reference concrete evidence.
- Distinguish observed facts from analytic inference.
- Confidence must degrade when data is missing, stale, or conflicting.
- If MITRE mapping is weak, state "insufficient evidence" explicitly.

## Output schema (required)

Produce a final JSON-like structured report with these sections:

- `Alert Classification`
- `Severity`
- `Priority`
- `True Positive Assessment`:
  - `Confidence`
  - `Reasoning`
- `MITRE ATT&CK Mapping`:
  - `Tactic`
  - `Technique`
  - `Sub-technique` (optional)
- `Alert Context`:
  - `Source`
  - `Affected Assets`
  - `Timeline`
- `Related Indicators`
- `Kill Chain Stage`
- `Investigation Steps`
- `Recommended Actions`:
  - `Immediate`
  - `Short-term`
  - `Long-term`
- `Tuning Recommendations` (optional)

## Priority guidance

Use this matrix unless tenant-specific policy says otherwise:

- `P1 (Critical)`: active exploitation, ransomware behavior, confirmed data exfiltration.
- `P2 (High)`: likely malicious execution, credential abuse, lateral movement signs.
- `P3 (Medium)`: suspicious reconnaissance, repeated policy violations, partial indicators.
- `P4 (Low)`: blocked attempts, benign anomalies, informational events.

## False-positive checks

- Approved administrative activity or maintenance windows.
- Known scanner or validation traffic.
- Expected baseline behavior for host/user/application.
- Previously validated benign indicators.

## Escalation triggers

- Multiple high-severity detections with shared entities.
- Clear lateral movement progression.
- Critical asset or privileged identity involvement.
- Signs of persistence plus command-and-control behavior.

## Notes

- Keep all analyst-facing instructions and reasoning in English.
- If required context is missing, request clarification with specific fields needed.