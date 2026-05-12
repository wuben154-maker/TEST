---
name: detecting-dll-sideloading-attacks
description: |
  It describes static recognition of DLL side-loading (MITRE T1574.002) from PE
  import and delay-load facts, runtime `LoadLibrary` / `LdrLoadDll` xrefs in
  FR-07 output, same-directory and writable-path DLL strings, and optional
  manifest or search-order hints, then encodes `behavior_chain` inferences with
  Proto-02 `evidence_refs` back to FR-04 and FR-07 facts. The runtime loads
  this specialist when the FR-17 gate `dll_sideloading` fires in
  `two-phase-behavior-chain-reconstruction` (dynamic-loading or
  process-manipulation modules plus suspicious DLL path or loader xref
  evidence). Triggers: DLL side-loading, side-load, DLL search order hijack,
  T1574.002, dynamic loading, behavior chain, FR-17. 中文触发词：DLL 侧载、DLL
  劫持、搜索顺序劫持、动态加载、行为链。
domain: cybersecurity
subdomain: threat-hunting
tags:
- threat-hunting
- mitre-attack
- dll-sideloading
- defense-evasion
- t1574
- edr
- proactive-detection
version: '1.0'
author: mahipal
license: Apache-2.0
d3fend_techniques:
- File Metadata Consistency Validation
- Content Format Conversion
- File Content Analysis
- Platform Hardening
- File Format Verification
nist_csf:
- DE.CM-01
- DE.AE-02
- DE.AE-07
- ID.RA-05
compatibility: binary_analysis FR-17 · ADR-13 · T1574.002
allowed-tools: file_read evidence_chain
---

# Detecting DLL Sideloading Attacks

## When to Use

- After FR-04 and FR-06 have populated imports and strings, and FR-07 has
  decompilation plus a call graph, when
  `two-phase-behavior-chain-reconstruction` matched the **`dll_sideloading`**
  gate: dynamic-loading or process-manipulation module labeling plus a
  suspicious DLL path or basename, side-by-side manifest signal, custom search
  path, or `LoadLibrary` / `LdrLoadDll` xref to a sample-derived DLL string.
- When attributing a module’s `dynamic_loading` or `process_manipulation`
  behavior to a **search-order** or **side-by-side** DLL resolution pattern
  rather than only static import table resolution.

**Do not use** as a substitute for the Gap-04 methodology, import parsing, or
`binary-analysis-evidence-chain-protocol`. **Do not use** when only common
system DLL names appear with no path anomaly and no callgraph path to a
loader, matching the two-phase “Do not read when” row.

## Routing (upstream / downstream)

| Direction | Owner |
|-----------|--------|
| **Invoked by** | `two-phase-behavior-chain-reconstruction` (Gap-04) **`dll_sideloading`** row; context is **Stage FR-17** under `binary-analysis-e2e-orchestrator`. The agent loads this file with `file_read` on `examples/binary_analysis/skills/detecting-dll-sideloading-attacks/SKILL.md` only when that gate is satisfied. |
| **Must read first** | `binary-analysis-evidence-chain-protocol` (Proto-02) and `binary-analysis-sanitize-untrusted-strings` (Proto-03) before any chain write. |
| **Consumes** | Existing **`imports`**, **`sections`**, **`strings_iocs`**, and FR-07 **`disassembly`** facts (`decompiled_function`, `function_tag`, `callgraph_edge` when present). It does not synthesize call edges or import facts. |
| **Hands off to** | Gap-04 / orchestrator after **`behavior_chain`** inferences; then **FR-09 → FR-08 → FR-13 → FR-14 → FR-15** as in `binary-analysis-e2e-orchestrator`, unless FR-17 is skipped. When FR-17 is skipped, the orchestrator still runs **FR-08** on remaining structured evidence (E2E-01); the report must state the **behavior_chain** gap. |
| **Return to orchestrator** | After sideloading-oriented nodes are written or a downgrade is recorded; do not fork a second binary orchestrator. |
| **Degrade** | If the gate’s **“Do not read when”** row is true, **do not** `file_read` this skill’s `SKILL.md` for that module. If `callgraph_edge` is missing, decompilation is skipped, or `analysis_coverage` on `disassembly` applies, do not add sideloading inferences; rely on `analysis_coverage` and orchestrator behavior-chain semantics instead. |
| **Document path** | If the session is E2E-02 document-first, `document-analysis-e2e-orchestrator` owns document buckets; set `doc_analysis_partial=true` when E2E-02 budget or recursion downgrades the parent. This skill applies only to **in-scope child binary** FR-17 work when a child sample is present. |

Telemetry-only procedures (Sysmon, MDE, EDR hunt playbooks) are **out of scope** for on-host tool execution. `references/standards.md` lists background MITRE and search-order context for human mapping, not for agent tool calls.

## Prerequisites

- `binary-analysis-evidence-chain-protocol` (Proto-02): append to **Bucket** `behavior_chain` only; `kind: inference` requires non-empty `evidence_refs` to fact indicator IDs; use `source_fr: "FR-17"`. (Rubric text may say `source_skill`; the implemented `Indicator` model uses `source_fr`.)
- `binary-analysis-sanitize-untrusted-strings` (Proto-03): any sample-derived string in `data` or rationale passes through `sanitize` before LLM or report use; align with `binary_analysis.prompts` `{open_tag}` / `{close_tag}` when templating.
- FR-04 structural and FR-07 decompiler inputs must exist for the full specialist workflow.

## Runtime contract

This skill is a **specialist interpretation layer for DLL side-loading
attribution** inside `binary_analysis`. It does not introduce new agent tools.

1. **Tool surface** — Follow this run’s `audit-runs/<run_id>/contracts.md`
   boundary: `file_identify`, `evidence_chain`, `scoring`, `decision_gate`,
   `report_gen`, `bash`, `python_exec`, `file_read`, `sandbox_session`, and
   `document_extract` only on the document orchestrator path. Structured PE
   import, string, and decompiler products reach this skill as **evidence-chain
   facts** from FR-04 / FR-06 / FR-07; they are not separate tool names. Do
   **not** name `pe_dump`, `network_capture`, `shell_exec`, `task`, or other
   non-runtime tools.
2. **Sandbox and zero raw bytes** — Samples live under `/workspace/<analysis_id>/`
   via `sandbox_session`. Do **not** `open()` the specimen on the analyst host or
   paste hexdumps or full PE blobs into the LLM. Optional analyst digressions
   belong only inside sandbox `bash` / `python_exec` with **bounded** stdout.
3. **Evidence writes** — Use `evidence_chain.append_indicator` with
   `bucket=behavior_chain` (Proto-02). The bucket is the append target, not a
   field on the Indicator. Persist with
   `evidence_chain.append_indicator(bucket="behavior_chain", ...)`; do not add a
   `bucket` key to the JSON payload.
4. **Facts vs inferences** — Import rows, delay-load metadata, and string hits
   already stored by upstream stages are **`kind: fact`** in their home buckets
   (`imports`, `strings_iocs`, `disassembly`). “This binary side-loads a
   malicious DLL in this order” is **`kind: inference`** in **`behavior_chain`**
   with `evidence_refs` to those fact ids. Use `source_fr: "FR-17"`.
   **`severity`** is **INFO** / **WARNING** / **CRITICAL** only; **`confidence`**
   is **HIGH** / **MEDIUM** / **LOW** when `kind` is `inference`.
5. **Untrusted snippets** — When quoting sample-derived text in prompts, wrap with
   `{open_tag}` / `{close_tag}` per `agent.md` and sanitise per Proto-03 before
   persistence.
6. **Budget** — Respect `{max_rounds}`, `{token_budget}`, and `{threshold_pct}`
   from `agent.md` when the parent injects them: prefer already-materialised facts
   before expanding extra DLL candidates.

## Workflow (static / sandbox contract)

1. **Align imports and delay-loads** with the **`imports`** bucket: note DLLs that are commonly resolved from the application directory and therefore sideloading-prone.
2. **Correlate strings** in `strings_iocs`: same-folder paths, user-writable directories, `%TEMP%` / `AppData`, or explicit `.\` relative loads that are **not** explained by the static import table alone.
3. **Walk the call graph** (`callgraph_edge` only; never infer from pseudo-C order): from functions tagged for dynamic loading, find reachability to `LoadLibrary*`, `LoadLibraryEx*`, or `LdrLoadDll` and tie string facts with `evidence_refs`.
4. **Optional manifest or PE resource** facts (from `headers` / FR-04): if `dependentAssembly` or `.local` / redirection appears, link it in `evidence_refs` to explain order-of-resolution changes.
5. **Emit inferences** into **Bucket** `behavior_chain` with `indicator_type` `function_behavior_node` and/or `module_chain_summary` and `data.capability` of `dynamic_loading` or `dll_sideloading`; set `mitre_attack` to `["T1574.002"]` when the inference is justified. Keep every inference tied to at least one `imports`, `strings_iocs`, or `disassembly` fact ID.

**Fact vs inference:** Delay-load and import list entries are **facts** from tools. The statement “this process intends to side-load a malicious DLL in this search order” is an **inference** and belongs in `behavior_chain` with cited facts.

## Indicator shape (illustrative)

The store receives `append_indicator(bucket, indicator)`; `bucket` is `behavior_chain`. A valid inference (field names match `Indicator` / Proto-02; omit `id` for auto-ULID; rubric “`source_skill`” maps to **`source_fr`** in code):

```json
{
  "source_fr": "FR-17",
  "kind": "inference",
  "indicator_type": "module_chain_summary",
  "severity": "WARNING",
  "confidence": "MEDIUM",
  "evidence_refs": [
    "01HZEXAMPLEEXAMPLEIMPHASHFACT01",
    "01HZEXAMPLEEXAMPLELDRSTRFACT02"
  ],
  "data": {
    "capability": "dll_sideloading",
    "rationale": "One-line summary; any embedded path uses sanitize() before append.",
    "mitre_attack": [
      "T1574.002"
    ]
  }
}
```

## Degrade paths

| Situation | Action |
|----------|--------|
| No `callgraph_edge` or FR-17 skipped (decompiler down) | Do not add sideloading inferences; rely on orchestrator `analysis_coverage` for `behavior_chain`. FR-08 still runs on other facts; document the **behavior_chain** gap in FR-15. |
| `strings_iocs` degraded (FLOSS timeout) | Lower `confidence`; cite string coverage fact if an `analysis_coverage` marker exists |
| Packed and FR-07 strategically skipped | No static loader proof; do not mark HIGH confidence on sideloading |
| Gate “Do not read when” in two-phase is true | Do not `file_read` this `SKILL.md` for that module |

For **document** parent workflows, `doc_analysis_partial` and document orchestrator rules apply per E2E-02; this file is a **binary** specialist only.

## Budget and reference discipline (NFR-05)

- Read this `SKILL.md` only when the `dll_sideloading` gate fires (touched in Phase 2). Do not preload every reference. Longer MITRE and Windows search-order material lives under `references/standards.md`.
- If the system prompt or parent stage injects `{token_budget}` / `{threshold_pct}` / `{max_rounds}`, stop expanding DLL candidates before those limits instead of best-effort enumerating every string hit.

## Related skills

- `two-phase-behavior-chain-reconstruction` (gate and Phase 1/2)
- `binary-analysis-e2e-orchestrator` (FR-17 and stage order)
- `binary-analysis-evidence-chain-protocol` (Proto-02)
- `binary-analysis-sanitize-untrusted-strings` (Proto-03)
- `references/standards.md` — T1574.x mapping and search order (read on demand)

## Key concepts (short)

| Label | Role |
|-------|------|
| T1574.002 | DLL side-loading (ATT&CK) |
| Search order | Application directory, System32, CWD, PATH (static reasoning uses import + string + graph) |
| Proxy DLL | Exports forward to a legitimate DLL; combine with decompiler evidence before labeling |

## ASCII — resolution sketch

```text
[exe directory]
    malicious.dll   <- searched before system tree if name matches delay-load or LoadLibraryW arg
[system32]
    legitimate.dll
```

## References (on demand)

- `references/standards.md` — MITRE rows and Windows DLL search order reference
- `references/api-reference.md` — human telemetry / EVTX / SOC patterns (read on demand; not agent tools)
- `references/workflows.md` — human Splunk/MDE playbooks (read on demand; not agent steps)
