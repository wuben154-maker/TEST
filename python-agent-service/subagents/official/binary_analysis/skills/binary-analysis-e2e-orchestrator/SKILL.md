---
name: binary-analysis-e2e-orchestrator
description: |
  Top-level orchestrator for the binary_analysis example (E2E-01 static malware triage).
  Read this skill at the start of every analysis session. Maps the twelve E2E-01 phases
  (FR-01, FR-02, FR-04–FR-09, FR-13–FR-15, FR-17) to recommended sub-skills, the evidence-chain
  bucket each phase must write, and downgrade paths when tools are unavailable. Applies to any
  binary analysis request: PE / ELF / Mach-O triage, malware family attribution, verdict /
  risk scoring, IOC extraction, behavior-chain reconstruction, or report generation.
license: Apache-2.0
compatibility: deepagents>=0.4.3 · binary_analysis E2E-01 v1
allowed-tools: sandbox_session bash python_exec file_read evidence_chain scoring decision_gate report_gen file_identify
metadata:
  id: Proto-01
  role: orchestrator
  version: 1.0.0
  batch: C8
  adr: ADR-11, ADR-14, ADR-15
  fr: FR-01, FR-02, FR-04, FR-05, FR-06, FR-07, FR-08, FR-09, FR-13, FR-14, FR-15, FR-17
  stability: stable
---

# Binary analysis E2E-01 orchestrator

This skill owns only the binary path’s Stage Map, phase scheduling, recommended skills, and downgrade paths. Concrete methodology belongs to referenced workflow skills; global first-hop routing, safety red lines, and verdict authority belong in `prompts/agent.md`.

## When to Use

- Use this skill after `file_identify` classifies the sample as PE / ELF / Mach-O.
- If `file_identify.document_tier` is non-empty (`P0` / `P1` / `P2`), stop the binary path and read `document-analysis-e2e-orchestrator/SKILL.md` instead.
- **DO NOT** call `document_extract` on this path; that tool belongs only to the document orchestrator and must not be used for PE / ELF / Mach-O.

## Stage map

Each phase describes only the scheduling surface: primary tool, recommended skills, target bucket, completion signal, and downgrade path. Before executing in-phase methodology, read the corresponding recommended workflow skill.

### Scheduling rules

- Strict order: FR-01 → FR-02; FR-07 → FR-17; FR-09 → FR-08 → FR-13 → FR-14 → FR-15.
- After FR-02, as soon as input is ready, FR-04 / FR-05 / FR-06 may be planned in the same LLM turn.
- FR-07 is gated by FR-04 structural facts and FR-05 `packer` / `unpack_result` conclusions.
- Before calling `bash` / `python_exec` / `file_read`, if no sandbox session exists yet, call only `sandbox_session(action="create")` to create one; do not use it to bypass the `file_identify` first hop or to read raw sample bytes.
- When a phase cannot complete, append `analysis_coverage` or a phase-specific gap indicator; do not fabricate evidence.

### Stage FR-01 · Confirm file identification result

- Tool: none. The `file_identify` first hop is already done per `agent.md`; this phase only consumes `file_meta`, without calling again.
- Recommended skills: none
- Bucket: `file_meta`
- Completion signal: first-hop result is written to `file_meta`, including format, size, and fingerprint facts; or a `format_unsupported` fact exists.
- Downgrade: stop the binary pipeline on unsupported / empty / oversize input with `Verdict=UNKNOWN` and `escalation=MANUAL_REVERSE`.

### Stage FR-02 · Quick triage

- Tool: `python_exec` for parser heuristics, entropy, and import sparsity checks.
- Recommended skills:
  - PE → `pe-structural-anomaly-checklist`, only for timestamp, section name, and section-count heuristics.
  - ELF → `analyzing-elf-structure`, only for ELF triage heuristics.
  - Mach-O → `analyzing-macho-structure`, only for Mach-O triage heuristics.
- Bucket: `triage`
- Completion signal: `risk_level`, `recommended_strategy`, `packing_severity_hint`, and the FR-02 signal set are present.
- Downgrade: on parser failure, record high-risk malformed triage facts; when heuristics are missing, record coverage downgrade and hand off to FR-04/05/06 classification.

### Stage FR-04 · Structural parsing

- Tool: `python_exec` with `pefile` / `lief`; use `bash` for `readelf` / `otool` when needed.
- Recommended skills:
  - PE → `performing-static-malware-analysis-with-pe-studio` + `pe-structural-anomaly-checklist`
  - ELF → `analyzing-elf-structure`
  - Mach-O → `analyzing-macho-structure`
- Buckets: `headers`, `imports`, `sections`
- Completion signal: at least one `fact` per structural bucket, or a `malformed_structure` fact explaining incomplete parsing.
- Downgrade: append `severity=CRITICAL` facts for malformed structure and continue later phases.

### Stage FR-05 · Entropy, packer detection, and unpacking

- Tool: `python_exec` for entropy and hashes; `bash` for DIE and allowlisted `upx -t` / `upx -d`.
- Recommended skills:
  - `analyzing-packed-malware-with-upx-unpacker`
  - `detecting-commercial-packers-with-die`
- Bucket: `packer`
- Completion signal: entropy facts, packer match / none / missing-tool fact, and exactly one `unpack_result` fact written.
- Downgrade: when DIE is missing, fall back to entropy and section heuristics; when unpacking is unavailable or not allowlisted, set `unpack_result.status` to `not_attempted` or `skipped_not_whitelisted`.

### Stage FR-06 · Strings and IOC extraction

- Tool: `bash` for `strings` / FLOSS; `python_exec` for classification.
- Execution rules: do not use `grep`, `cat`, `head`, `tail`, `xxd`, `hexdump`, or `od` to read or filter `sample.bin` directly. For IOC keywords such as `powershell`, use `strings -a -n 6` / FLOSS to produce bounded string surfaces, or scan bytes with `python_exec` and return only structured, length-limited, sanitized offset / count / printable snippets; do not return raw binary context.
- Recommended skills:
  - `binary-analysis-ioc-extraction-workflow`
  - `binary-analysis-sanitize-untrusted-strings`
- Bucket: `strings_iocs`
- Completion signal: classified IOC facts written or explicit `no_ioc_found` fact; defanged / sanitized before entering the LLM.
- Downgrade: on FLOSS timeout, fall back to `strings -a -n 6` and record string coverage downgrade.

### Stage FR-07 · Decompilation and semantic export

FR-07 splits by sample type into two parallel sub-paths: **FR-07a · Native decompilation** (PE / ELF / Mach-O / Go / Rust via Ghidra `analyzeHeadless` + `DecompileByList.py`) and **FR-07b · Managed decompilation** (.NET via dnSpy / ILSpy static export, **without** calling Ghidra). Both share the same `disassembly` bucket, the same FR-17 handoff interface, and the same strategic-skip logic, but differ in tools and completion signals.

#### Shared prerequisite (both sub-paths)

1. **Write `decompile_input` fact**: use `evidence_chain.query` to read `packer.unpack_result`, derive `input_path` / `input_sha256` per the “input selection” rules below, then use `evidence_chain.append` to write a **single** `decompile_input` fact to `disassembly`. This fact is a hard prerequisite for FR-07 sub-path work; do not proceed without it.
2. **Input selection**: if the `packer` bucket has `unpack_result.status="success"`, switch decompilation input to `data.unpacked_path` and cancel FR-02 AC-8 proactive skip; otherwise use the FR-01 original sample path. For `unpack_result.status` in `failed` / `not_attempted` / `skipped_not_whitelisted` / `skipped_commercial_protector` / `tool_missing` (SPEC FR-05 AC-9 v0.3.1+ six-value enum), **any non-`success` status must not be treated as successful unpack**.

#### FR-07a · Native decompilation (PE / ELF / Mach-O / Go / Rust)

- Tools:
  - Step 0: `python_exec` reads `decompile_input` + `imports` + `strings_iocs`, writes a **single** `decompile_priority` fact.
  - Step 1: `bash` invokes `analyzeHeadless` + `-postScript DecompileByList.py` only in the sanctioned command shape from `ghidra-priority-queue-workflow`.
  - Step 2: `file_read` paginates `manifest.json` and each function’s `<addr>.c`.
- Recommended skills:
  - `ghidra-priority-queue-workflow` (authoritative invocation contract for FR-07a; read first)
  - `binary-analysis-evidence-chain-protocol` (verify schema before writing facts)
  - PE / default → `performing-static-malware-analysis-with-pe-studio` + `reverse-engineering-malware-with-ghidra`
  - ELF → `analyzing-linux-elf-malware-with-ghidra`
  - Mach-O → `reverse-engineering-malware-with-ghidra` (default) + priority table from the end of FR-04 `analyzing-macho-structure` section “Mach-O Hand-off to FR-07” (dyld stubs / Obj-C / Swift deep dives not yet a standalone skill; track P1-10)
  - Go → `analyzing-golang-malware-with-ghidra`
  - Rust → `reverse-engineering-rust-malware`
  - Note: priority queue is now scheduled from FR-01 `file_meta.data.format` (PE → `HIGH_RISK_APIS_WIN32`, ELF → POSIX, Mach-O → Mach; FR-07b handles .NET / CIL / ManagedPE); FR-04 producers feed Step 0 via format-neutral `suspicious_import` schema (`data.callers` / `data.thunk_addr` / `data.module`) so Step 0 emits `<caller_name>@<caller_addr>` tokens instead of import symbol names, avoiding Ghidra resolving tokens to thunk stubs. Go / Rust statically linked paths currently inherit the host format provider; pclntab / crate metadata signals still pending FR-04 producer (track P1-10). See `ghidra-priority-queue-workflow` Step 0 SIGNAL_PROVIDERS table and `binary-analysis-evidence-chain-protocol` `suspicious_import` payload contract.
- Bucket: `disassembly`
- Completion signal (explicit OR):
  - (`decompile_priority` × 1) with `data.budget` recording `bash_timeout_s` / `per_fn_timeout_s` / `top_n`
  - **AND** (`decompiled_function` ≥ 1)
  - **AND** (`function_tag` ≥ 1)
  - **AND** ((`callgraph_edge` ≥ 1) **OR** (`analysis_coverage` with `data.reason ∈ {callgraph_unavailable, decompile_all_failed, manifest_missing, decompiler_unavailable, fr02_ac8_strategic_skip}`))

#### FR-07b · Managed decompilation (.NET)

- Tools:
  - Step 0: `python_exec` reads `decompile_input`, confirms .NET (`pefile.DIRECTORY_ENTRY_COM_DESCRIPTOR` or `mscoree.dll` import).
  - Step 1: `bash` runs allowlisted static export tools in the sandbox (`de4dot` / `ilspycmd` / `monodis` / `dnSpy.Console`) to export assemblies to IL / C# under `/workspace/<aid>/dotnet/`. **Do not** invoke the dnSpy debugger or run the .NET sample.
  - Step 2: `file_read` paginates exported `.cs` / `.il` / `manifest` files.
- Recommended skills:
  - `reverse-engineering-dotnet-malware-with-dnspy` (methodology authority for FR-07b)
  - `binary-analysis-evidence-chain-protocol` (managed-code `indicator_type` reference)
  - `binary-analysis-sanitize-untrusted-strings` (required before any .NET decompiler output enters the LLM)
- Bucket: `disassembly`
- Completion signal (differs from FR-07a; managed path does not write `decompile_priority`; callgraph not exportable by default):
  - (`managed_metadata` × 1) (runtime version, assembly name, obfuscator, module count)
  - **AND** ((`decompiled_function` ≥ 1) **OR** (`managed_config_candidate` ≥ 1) **OR** (`managed_resource` ≥ 1))
  - **AND** (`function_tag` ≥ 1)
  - **AND** ((`callgraph_edge` ≥ 1) **OR** (`analysis_coverage` with `data.reason ∈ {managed_callgraph_unavailable, decompiler_unavailable, deobfuscator_unavailable, manifest_missing}`))
  - Note: .NET defaults to `managed_callgraph_unavailable`—dnSpy / ILSpy static export does not emit a call graph; `callgraph_edge` only when the sandbox has a callgraph-capable .NET decompiler.

#### Downgrade paths (shared by both sub-paths, distinguished by reason)

| Trigger | Sub-path | Action | `analysis_coverage.data.reason` |
|---|---|---|---|
| Ghidra `analyzeHeadless` unavailable or timeout | FR-07a | Append `status="SKIPPED"` / `dimension="decompilation"` to `disassembly`, skip FR-17 | `decompiler_unavailable` |
| `analyzeHeadless` exits but `manifest.json` missing | FR-07a | Append `status="DEGRADED"` / `dimension="decompilation"` to `disassembly`, skip FR-17 | `manifest_missing` |
| Manifest exists but all functions `timeout` / `not_found` / `error` | FR-07a | Append `status="DEGRADED"` / `dimension="decompilation"` to `disassembly`, skip FR-17 | `decompile_all_failed` |
| Static .NET decompilers (dnSpy.Console / ILSpy / monodis) all unavailable in sandbox | FR-07b | Append `status="SKIPPED"` / `dimension="decompilation"` to `disassembly`, skip FR-17 | `decompiler_unavailable` |
| .NET decompiler available but de4dot etc. missing and sample protected by ConfuserEx / custom obfuscator | FR-07b | Append `status="DEGRADED"` / `dimension="decompilation"` to `disassembly`, partial `managed_metadata` then skip `decompiled_function` writes | `deobfuscator_unavailable` |
| Call graph cannot be exported (FR-07a Ghidra callgraph failure / FR-07b managed default) | FR-07a + FR-07b | Append `analysis_coverage` to `disassembly`, skip FR-17 | `callgraph_unavailable` (FR-07a) / `managed_callgraph_unavailable` (FR-07b) |
| FR-02 yields `risk_level="CRITICAL"` and `packing_severity_hint="SEVERE"` (aggregate formula SPEC FR-02 AC-9: `global_entropy ≥ 7.2 AND (section_name_hits non-empty OR import_sparsity ≥ 0.8)`), and FR-05 has not yet proven unpacked or successful unpack | FR-07a + FR-07b | Proactively skip FR-07 / FR-17; re-evaluate when FR-05 results are available | `fr02_ac8_strategic_skip` |
| FR-05 later writes unpacked fact, or `unpack_result.status="success"` with `data.unpacked_path` available | FR-07a + FR-07b | Cancel proactive skip; run FR-07 per input selection; new `decompile_priority` (FR-07a) or `managed_metadata` (FR-07b) fact **must** set `data.cancels_strategic_skip=true` and list original skip indicator id in `evidence_refs` so FR-13 / FR-15 can observe “skip canceled” | none; do not append a new skip marker |

### Stage FR-17 · Behavior chain reconstruction

- Tool: `python_exec` post-processing of decompilation exports.
- Recommended skills:
  - `two-phase-behavior-chain-reconstruction`
- Bucket: `behavior_chain`
- Completion signal: module-level and function-level behavior nodes present; if callgraph / decompilation unavailable, at least write a static-evidence downgrade graph or skip coverage indicator.
- Downgrade:
  - If FR-07 has `callgraph_edge`, must use `two-phase-behavior-chain-reconstruction`; do not replace the formal two-phase graph with a static fallback.
  - If no decompilation input or callgraph missing, but `imports` / `strings_iocs` / `packer` / `embedded_payloads` contain citeable facts, use `evidence_chain.append` for `kind="inference"`, `source_fr="FR-17"`, `indicator_type="static_behavior_node"` downgrade nodes; nodes express only provable capabilities (e.g. `network_c2_candidate`, `anti_analysis`, `embedded_payload_staging`), `confidence` at most `MEDIUM`, `data.degraded=true`, `evidence_refs` must point to upstream facts.
  - When static evidence is also insufficient, append `analysis_coverage` with `dimension="behavior_chain"`, then continue FR-09 / FR-08.

### Stage FR-09 · Evidence chain snapshot

- Tool: `evidence_chain`
- Recommended skills:
  - `binary-analysis-evidence-chain-protocol`
- Buckets: read all buckets; this phase does not write.
- Completion signal: snapshot obtained for FR-08 and rule tools.
- Downgrade: none.

### Stage FR-08 · LLM semantic analysis

- Tool: none; this phase is the LLM reasoning loop over the evidence snapshot.
- Recommended skills:
  - `binary-analysis-evidence-chain-protocol`
  - `binary-analysis-sanitize-untrusted-strings`
  - `references/fr08-signal-matrix.md` (hypothesis triggers from facts, specialized skills, and `llm_inferences` writes)
- Bucket: `llm_inferences`; if reasoning is tightly bound to existing facts, may also write `strings_iocs` or `behavior_chain`.
- Completion signal:
  - **Quick scan**: initial inferences from triage and structural facts.
  - **Deep dive**: evidence-backed inferences from strings, packer, decompilation, and `behavior_chain`.
  - **Synthesis**: integrate `behavior_chain`, self-consistency on `evidence_refs`; on conflict with facts or old conclusions, append confidence downgrade inferences.
- Downgrade: if the LLM provider is unreachable or schema errors repeat, return a fact-level report with `Verdict=UNKNOWN` and `escalation=MANUAL_REVERSE`.

### Stage FR-13 · Scoring and classification

- Tool: `scoring`
- Recommended skills:
  - `binary-analysis-family-triage-workflow`
  - `analyzing-malware-family-relationships-with-malpedia`
  - Load family-specific skills only when explicitly requested by a workflow.
- Bucket: `scoring`
- Completion signal: verdict, risk score, and family candidates (if applicable) written as rules-engine facts.
- Downgrade: missing rules is a code defect; fail fast.

### Stage FR-14 · Decision gate

- Tool: `decision_gate`
- Recommended skills:
  - `analyzing-malware-sandbox-evasion-techniques`
  - `conducting-malware-incident-response`
  - `building-automated-malware-submission-pipeline`
- Bucket: `decision_gate`
- Completion signal: escalation recommendations and rationale cite scoring and coverage facts.
- Downgrade: none; this phase is a pure function over existing evidence.

### Stage FR-15 · Report generation

- Tool: `report_gen`
- Recommended skills:
  - Read `performing-yara-rule-development-for-detection` only when the caller requests a YARA appendix.
- Buckets: read all buckets; reports go to disk, not into the evidence chain.
- Completion signal: JSON and Markdown reports generated with `schema_version="1.0.0"`.
- User-visible output: do not only say “detailed report written to: …”. The final explicit response must keep a brief conclusion and append `## Appendix: Detailed report`, pasting the full `markdown_content` returned by `report_gen` into the appendix; if response budget is tight, show segments and state clearly that the remainder is still at `md_path`.
- Downgrade: fail fast on schema mismatch. `report_gen.output_dir` is a host path, not `/workspace/<analysis_id>/...`; do not call `file_read` on generated host reports.

## Downgrade paths

- `format_unsupported`: stop pipeline, minimal unknown verdict and manual reverse escalation.
- `malformed_structure`: record critical structural facts and continue with available evidence.
- `tool_missing`: record deterministic tool coverage gaps in affected buckets.
- `floss_timeout`: fall back to basic strings extraction.
- `decompiler_unavailable` / `fr02_ac8_strategic_skip`: skip FR-07 and FR-17; FR-08 reasons over remaining facts.
- `llm_degraded`: stop generating inferences; return a fact-level report.
