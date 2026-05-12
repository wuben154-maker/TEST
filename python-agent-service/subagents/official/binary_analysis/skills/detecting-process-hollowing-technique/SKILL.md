---
name: detecting-process-hollowing-technique
description: >-
  It guides FR-17 behavior-chain analysis when static evidence supports process
  hollowing (MITRE T1055.012): suspended process creation, NtUnmapViewOfSection,
  GetThreadContext, SetThreadContext, WriteProcessMemory, ResumeThread, or
  RunPE-style API clusters in `imports`, `strings_iocs`, or `disassembly`.
  Activates when `two-phase-behavior-chain-reconstruction` routes the
  process_injection row with hollowing-specific cues, when the FR-08 signal
  matrix points here, or when `detecting-process-injection-techniques` defers
  to hollowing mapping. 用于二进制中的 进程镂空 / 空心进程 / T1055.012 行为链解读。
  It does not add EDR telemetry, host memory forensics, or non-contract tools.
domain: cybersecurity
subdomain: threat-hunting
tags:
- threat-hunting
- mitre-attack
- process-hollowing
- process-injection
- edr
- t1055
- proactive-detection
version: '1.0'
author: mahipal
license: Apache-2.0
d3fend_techniques:
- Platform Monitoring
- Process Code Segment Verification
- Segment Address Offset Randomization
- Process Analysis
- Application Hardening
nist_csf:
- DE.CM-01
- DE.AE-02
- DE.AE-07
- ID.RA-05
---

# Detecting Process Hollowing Technique

## When to Use

- FR-06 / FR-07 facts show **hollowing-relevant** API sets (for example
  `CreateProcess` with suspended creation flags, `NtUnmapViewOfSection`,
  `GetThreadContext`, `SetThreadContext`, `WriteProcessMemory`, `ResumeThread`,
  `VirtualAllocEx` in a process-targeting cluster) in **`imports`**, or matching
  strings in **`strings_iocs`**, with **`disassembly` / `function_tag`** support
  when decompilation is available.
- The **FR-08** signal matrix (`binary-analysis-e2e-orchestrator/references/fr08-signal-matrix.md`)
  or **`detecting-process-injection-techniques`** recommends this skill for
  **T1055.012**-specific interpretation after a generic injection triage.
- `two-phase-behavior-chain-reconstruction` (Gap-04) matched **process
  injection** and needs a **hollowing**-focused narrative on top of
  `process_manipulation` facts.

**Do not use** for host live-memory scans, EDR query packs, or Splunk/MDE export
ingestion as if they were agent tools. **Do not use** to replace `imports` /
`strings_iocs` extraction, PE structure authority (FR-04), or the document
orchestrator when the session is document-first for the outer container.

## Routing (upstream / downstream)

| Direction | Owner |
| --- | --- |
| **Invoked by** | `two-phase-behavior-chain-reconstruction` (Gap-04) **process_injection** path with hollowing-specific read; **Stage FR-17** under `binary-analysis-e2e-orchestrator`; optional hand-off from `detecting-process-injection-techniques`. |
| **Must read first** | `binary-analysis-evidence-chain-protocol` (Proto-02) and `binary-analysis-sanitize-untrusted-strings` (Proto-03) before writing chain indicators. |
| **Consumes** | Existing **`imports`**, **`strings_iocs`**, **`disassembly`** (`decompiled_function`, `function_tag`, `callgraph_edge` when available). |
| **Hands off to** | Orchestrator for **FR-09 to FR-15** after **`behavior_chain`** inferences (or explicit `analysis_coverage` / partial flags). |
| **Return to orchestrator** | After hollowing-oriented nodes or an explicit downgrade; do not spawn a second binary orchestrator. |
| **Downgrade** | If FR-07 is skipped, **`callgraph_edge`** is missing, or the API triad is incomplete, record **`analysis_coverage`** on the behavior path (for example `behavior_chain_unavailable`, `degraded_chain`) and cite only observed **fact** ids, no synthetic parent/child process telemetry. |
| **Document path** | If the active flow is **E2E-02** document-first, `document-analysis-e2e-orchestrator` owns **`doc_analysis_partial`** and document buckets; this skill only augments **child binary** FR-17 when invoked. |

## Runtime Contract

This skill is a **specialist interpretation layer** for **process hollowing
(T1055.012)** inside `binary_analysis`. It does not add new agent tools.

1. **Tool surface** — Follow this run’s `audit-runs/<run_id>/contracts.md`:
   `file_identify`, `evidence_chain`, `scoring`, `decision_gate`, `report_gen`,
   `bash`, `python_exec`, `file_read`, `sandbox_session` (`SandboxSessionTool`),
   and `document_extract` only after the **document** orchestrator is active on
   a document input. **Do not** name `pe_dump`, `network_capture`, `shell_exec`,
   `task`, or other non-runtime tools.
2. **Sandbox and zero raw bytes** — Samples live under `/workspace/<analysis_id>/`
   via `sandbox_session`. **Never** `open()` the sample on the analyst host, paste
   hexdumps, or stream **raw** EDR/Sysmon/XML log bodies into the LLM. Optional
   analyst-side commands in `references/` are **human** procedures only, not
   agent steps; any machine output shown to the model must be **Proto-03**
   sanitised and tag-wrapped.
3. **Facts vs inferences** — API names, section names, and import table entries
   from tools are **`kind: fact`** in their home buckets. Hollowing **technique
   labels**, MITRE links, and victim-process hypotheses are **`kind: inference`**
   in **`behavior_chain`** (or the appropriate inference bucket) with non-empty
   `evidence_refs` to those fact ids. **Do not** move LLM-styled conclusions into
   fact buckets. Use `source_fr: "FR-17"` for FR-17-originated rows. **Severity**
   uses INFO / WARNING / CRITICAL; **confidence** uses HIGH / MEDIUM / LOW for
   inference `kind`.
4. **Untrusted snippets** — Wrap sample-derived text with `{open_tag}` /
   `{close_tag}` per `agent.md` and sanitise per Proto-03 before persistence.
5. **Budget** — Respect `{max_rounds}`, `{token_budget}`, and `{threshold_pct}` from
   `agent.md`. Read `references/api-reference.md` for pattern anchors only
   (touch-what-you-need; no deep ref stacking in one turn).

## Workflow

### Step 1 — Map static facts to a hollowing sequence

From **sanitised** FR-06/FR-07 outputs, look for the classic **unmap-and-replace**
shape (order may vary; cite what exists):

- Process creation in a **suspended** or **reusable** hollowing-friendly pattern
  plus **section unmap** and **thread-context** adjust primitives.
- Co-location of **WriteProcessMemory**-style or **section mapping** calls with
  **open-process** or **suspended-create** families in the same cluster when
  `callgraph_edge` allows; otherwise keep claims minimal.

### Step 2 — Distinguish from generic injection

If evidence fits classic **remote thread / APC** but **lacks** unmap and
image-replace cues, keep primary narrative in
`detecting-process-injection-techniques` and use this skill only for **explicit
T1055.012** labelling when facts support it.

### Step 3 — Write `behavior_chain` inferences

Use `evidence_chain.append_indicator` to append to the **`behavior_chain`**
bucket only (Proto-02; one bucket per row). Emit **`function_behavior_node`**
and/or **`module_chain_summary`** indicators
with `data.capability="process_manipulation"` and a hollowing-specific summary
when the fact ids back it. Example shape (illustrative ids):

```json
{
  "source_fr": "FR-17",
  "indicator_type": "module_chain_summary",
  "kind": "inference",
  "severity": "WARNING",
  "confidence": "MEDIUM",
  "evidence_refs": ["01JABCDEFIMPORTS01", "01JABCDEFTAGFUNC01"],
  "data": {
    "capability": "process_manipulation",
    "summary": "Hollowing pattern: suspended create, unmap, write, thread-context resume (T1055.012)",
    "rationale": "Imports and tagged functions show NtUnmapViewOfSection with WriteProcessMemory and ResumeThread in the same module cluster."
  }
}
```

If the hollowing story cannot be tied to a **fact** id, **do not** assert it;
use **`analysis_coverage`** with a SKIPPED or DEGRADED reason instead.

## Validation Criteria

- Every **behavior** inference lists at least one **tool-backed fact** id in
  `evidence_refs`.
- No non-contract tool is prescribed as a mandatory agent call.
- Content derived from the sample is tag-wrapped / sanitised per Proto-03.
- Downgrades are explicit when decompilation, edges, or API clusters are
  incomplete.

## References

- `references/api-reference.md` — static API and pattern anchors; runtime scope
  note at file top
- `references/standards.md` — MITRE and related sub-technique table
- `references/workflows.md` — **human** hunting/DFIR playbooks (not agent tools)
- `binary-analysis-evidence-chain-protocol` — Proto-02
- `binary-analysis-sanitize-untrusted-strings` — Proto-03
- `two-phase-behavior-chain-reconstruction` — FR-17 gap routing
- `binary-analysis-e2e-orchestrator` — stage map and FR-08/FR-17 context
- `binary-analysis-e2e-orchestrator/references/fr08-signal-matrix.md` — FR-08
  signal matrix (T1055.012 / hollowing routing)
