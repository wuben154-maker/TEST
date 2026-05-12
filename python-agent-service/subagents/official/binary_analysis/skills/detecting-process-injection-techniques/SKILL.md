---
name: detecting-process-injection-techniques
description: |
  It guides FR-17 behavior-chain analysis when static evidence suggests process
  injection: VirtualAllocEx, WriteProcessMemory, CreateRemoteThread,
  NtCreateThreadEx, QueueUserAPC, SetThreadContext, NtMapViewOfSection,
  OpenProcess, or related API clusters in `imports` / `disassembly`, plus
  aligned cues in `strings_iocs`. Activates when
  `two-phase-behavior-chain-reconstruction` delegates the `process_injection`
  row or when analysts map 进程注入, DLL injection, APC injection, remote thread
  code injection, process hollowing, or reflective loading from
  sandbox-visible facts. It does not add host memory forensics, live Sysmon
  ingestion, or tools outside the project sandbox and evidence writers.
  Triggers: process_injection, T1055, process injection, behavior chain, FR-17.
  中文触发词：进程注入、远线程、APC 注入、行为链、DLL 注入。
domain: cybersecurity
subdomain: malware-analysis
tags:
- malware
- process-injection
- detection
- t1055
- fr-17
- behavior-chain
- defense-evasion
version: 1.0.0
author: mahipal
license: Apache-2.0
compatibility: binary_analysis FR-17 · MITRE T1055 · Proto-02/Proto-03
allowed-tools: file_read evidence_chain
d3fend_techniques:
- Executable Denylisting
- Execution Isolation
- File Metadata Consistency Validation
- Content Format Conversion
- File Content Analysis
nist_csf:
- DE.AE-02
- RS.AN-03
- ID.RA-01
- DE.CM-01
---

# Detecting Process Injection Techniques

## Upstream, downstream, orchestrator

- **Triggered by** `two-phase-behavior-chain-reconstruction` (Gap-04) at the
  specialist gate `process_injection` (see that skill’s gate table). This is
  not a first-hop skill; **Stage FR-17** is reached under
  `binary-analysis-e2e-orchestrator` only after prior FRs have materialised
  `file_meta` and structure/string/decompiler facts. After **`behavior_chain`**
  inferences (or explicit `analysis_coverage`), hand off to **FR-09 → FR-08 →
  FR-13 → FR-14 → FR-15**; do not spawn a second binary orchestrator.
- **Must read first** `binary-analysis-evidence-chain-protocol` (Proto-02) and
  `binary-analysis-sanitize-untrusted-strings` (Proto-03) before any chain write.
- **Hollowing split** When CreateProcess (suspended), NtUnmapViewOfSection, or
  GetThreadContext / SetThreadContext dominate, also read
  `detecting-process-hollowing-technique` and keep **one** primary narrative
  to avoid duplicate `behavior_chain` nodes.
- **Document path (E2E-02)** If the session is document-first,
  `document-analysis-e2e-orchestrator` owns `doc_analysis_partial` and
  document buckets; load this skill only to supplement **child binary** FR-17
  when the wrapper invokes it.

## When to Use

- FR-04 / FR-06 / FR-07 facts show **two or more** injection primitives (for
  example `VirtualAllocEx` + `WriteProcessMemory` + `CreateRemoteThread`, or
  `QueueUserAPC`, `SetThreadContext`, `NtMapViewOfSection`) in the same
  reachable cluster, or FR-07 `function_tag` already marks **process
  manipulation**.
- `two-phase-behavior-chain-reconstruction` matched the **`process_injection`**
  gate and loaded this skill to turn imports / decompilation into
  **`behavior_chain`** inferences with citations.
- You must relate MITRE **T1055** sub-techniques to **observed** facts while
  staying inside NFR-05 budget.

**Do not use** as a substitute for FR-04 import extraction, FR-06 string
harvesting, or FR-07 decompilation. Do not use for **pure** legitimate DLL
loading with no cross-process primitives. Do not claim **memory-dump**,
**malfind**, or **Sysmon** artefacts unless they already exist as sanitised,
bounded facts from allowed tooling (never raw host log bytes or hexdumps in
prompts).

## Routing (upstream / downstream)

| Direction | Owner |
|-----------|--------|
| **Invoked by** | `two-phase-behavior-chain-reconstruction` (Gap-04) **`process_injection`** row; context is **Stage FR-17** under `binary-analysis-e2e-orchestrator`. |
| **Must read first** | `binary-analysis-evidence-chain-protocol` (Proto-02) and `binary-analysis-sanitize-untrusted-strings` (Proto-03) before any chain write. |
| **Consumes** | Existing **`imports`**, **`strings_iocs`**, **`disassembly`** facts (`decompiled_function`, `function_tag`, `callgraph_edge` when present). |
| **Hands off to** | Gap-04 / orchestrator after **`behavior_chain`** inferences (or explicit `analysis_coverage`); then **FR-09 → FR-08 → FR-13 → FR-14 → FR-15**. |
| **Return to orchestrator** | After injection-oriented nodes are written or a downgrade is recorded; do not fork a second binary orchestrator. |
| **Downgrade** | If FR-07 skipped decompilation, `callgraph_edge` is missing, or only a single primitive appears globally, record **`analysis_coverage`** on `behavior_chain` per E2E-01 instead of inventing remote-thread narratives. Prefer already-sanitised FR-06 / FR-07 facts over new dumps. |
| **Hollowing split** | When **CreateProcess (suspended)**, **NtUnmapViewOfSection**, **GetThreadContext** / **SetThreadContext** dominate the evidence, also read `detecting-process-hollowing-technique` and keep **one** primary narrative to avoid duplicate `behavior_chain` nodes. |
| **Document path** | If the active session is **E2E-02** document-first, `document-analysis-e2e-orchestrator` owns document buckets and sets `doc_analysis_partial=true` when E2E-02 budget/recursion downgrades the parent; this skill only supplements **child binary** FR-17 when a child sample is in scope and injection-related facts exist. |

## Runtime Contract

This skill is a **specialist interpretation layer for process-injection
attribution** inside `binary_analysis`. It does not introduce new agent tools.

1. **Tool surface** — Follow this run’s `audit-runs/<run_id>/contracts.md`
   boundary: `file_identify`, `evidence_chain`, `scoring`, `decision_gate`,
   `report_gen`, `bash`, `python_exec`, `file_read`, `sandbox_session`, and
   `document_extract` only on the document orchestrator path. Do **not** name
   `pe_dump`, `network_capture`, `shell_exec`, `task`, or other non-runtime tools.
2. **Sandbox and zero raw bytes** — Samples live under `/workspace/<analysis_id>/`
   via `sandbox_session`. Do **not** `open()` the specimen on the analyst host or
   paste hexdumps, PE blobs, or full event XML into the LLM. Any optional analyst
   command examples belong **only** inside sandbox `bash` / `python_exec` with
   **bounded** stdout, and **never** as mandatory agent steps in this skill.
3. **Evidence writes** — Use `evidence_chain.append_indicator` with
   `bucket=behavior_chain` (Proto-02) for this skill’s inferences. The bucket is
   the append target, not a field on the Indicator.
4. **Facts vs inferences** — API names, import tables, and decompiler lines
   observed by tools are **`kind: fact`** in their home buckets (`imports`,
   `strings_iocs`, `disassembly`). Injection **technique labels**, victim /
   actor process hypotheses, and MITRE mappings are **`kind: inference`** in
   **`behavior_chain`** with non-empty `evidence_refs` to those fact ids.
   Use `source_fr: "FR-17"` for FR-17 outputs. **`severity`** is **INFO** /
   **WARNING** / **CRITICAL** only; **`confidence`** is **HIGH** / **MEDIUM** /
   **LOW** when `kind` is `inference`.
5. **Untrusted snippets** — When quoting sample-derived text in prompts, wrap with
   `{open_tag}` / `{close_tag}` per `agent.md` and sanitise per Proto-03 before
   persistence.
6. **Budget** — Respect `{max_rounds}`, `{token_budget}`, and `{threshold_pct}`
   from `agent.md`: prefer short `file_read` windows on skill references and
   already-materialised facts before expanding prose.

## Workflow

### Step 1 — Classify injection pattern from static facts

From **sanitised** `imports`, `strings_iocs`, and `disassembly`, map signals to
injection families (pattern anchors in `references/api-reference.md`):

- **Classic remote thread / DLL injection** — OpenProcess + VirtualAllocEx +
  WriteProcessMemory + CreateRemoteThread (or NtCreateThreadEx).
- **APC injection** — QueueUserAPC / NtQueueApcThread with writable remote
  allocation in the same module story.
- **Thread context / hijack** — SuspendThread + GetThreadContext + SetThreadContext
  paired with remote writes.
- **Section / mapping** — NtMapViewOfSection or MapViewOfFile with RWX or
  suspicious sharing flags in decompiler text.
- **Reflective or manual map** — LoadLibrary absent while memory-write + execution
  primitives cluster (inference only when `evidence_refs` cover the cluster).

### Step 2 — Tie signals to FR-07 structure

Link high-signal APIs to **`function_tag`** / **`decompiled_function`** facts via
`callgraph_edge` when available. If edges are missing, cite **import / string
fact ids** only; do not infer cross-process edges from prose alone.

### Step 3 — Write `behavior_chain` inferences

`two-phase-behavior-chain-reconstruction` may emit **`function_behavior_node`**
/ **`function_behavior_edge`** for the module graph. This skill adds
injection-specific labeling using **`process_injection_node`** or
**`module_chain_summary`** with `data.capability="process_manipulation"` when
facts support the narrative (all remain `kind: inference` with
`source_fr: "FR-17"`). Example shape (illustrative ids):

```json
{
  "source_fr": "FR-17",
  "indicator_type": "process_injection_node",
  "kind": "inference",
  "severity": "WARNING",
  "confidence": "HIGH",
  "evidence_refs": ["01JABCDEFACTIMPORT01", "01JABCDEFUNTAGFUNC01"],
  "data": {
    "capability": "process_manipulation",
    "technique_family": "classic_remote_thread_injection",
    "summary": "WriteProcessMemory plus CreateRemoteThread cluster in main module",
    "rationale": "Cited import and function_tag facts show the full triad in one cluster."
  }
}
```

Persist with `evidence_chain.append_indicator(bucket="behavior_chain", ...)`;
do not add a `bucket` key to the JSON payload.

If the injection hypothesis cannot be tied to any fact id, **do not** write a
positive inference; optionally add `analysis_coverage` with **SKIPPED** or
**DEGRADED** reason on bucket `behavior_chain`.

## Validation Criteria

- Every **`behavior_chain`** inference lists at least one **fact** id in
  `evidence_refs`.
- No non-contract tools are prescribed as agent calls.
- Sample-derived text in model context is tag-wrapped / sanitised per Proto-03.
- Downgrades use `analysis_coverage` instead of speculative chains when FR-07
  inputs are incomplete.

## References

- `references/api-reference.md` — API sequences and external-telemetry context
- `binary-analysis-evidence-chain-protocol` — Proto-02
- `binary-analysis-sanitize-untrusted-strings` — Proto-03
- `two-phase-behavior-chain-reconstruction` — FR-17 gap routing
- `binary-analysis-e2e-orchestrator/references/fr08-signal-matrix.md` — pre-read cue for hollowing hand-off
- `detecting-process-hollowing-technique` — hollowing-specific split
- `binary-analysis-e2e-orchestrator` — stage map and FR-17 entry
