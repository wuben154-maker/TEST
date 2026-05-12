---
name: binary-analysis-evidence-chain-protocol
description: |
  Protocol every binary_analysis skill MUST follow when appending findings to
  the shared evidence chain. Defines the Indicator schema (`source_fr`,
  `indicator_type`, `kind`, `severity`, `confidence`, `evidence_refs`,
  `derived_from`, `data`), the bucket routing table for binary v1.0 and
  document v1.1 buckets, protected document-bucket ownership, and the strict
  boundary between fact and inference. Activates on any request involving
  evidence chain writes, Indicator authoring, bucket routing, document bucket
  writes, or fact-vs-inference tagging.
license: Apache-2.0
compatibility: binary_analysis Indicator schema v1.0.0 · evidence chain v1.1.0
allowed-tools: evidence_chain
metadata:
  id: Proto-02
  batch: C8
  adr: ADR-02, ADR-03
  fr: FR-09, FR-08
  ir: IR-01, IR-12
  stability: stable
---

# Evidence Chain Writing Protocol (Proto-02)

> The evidence chain is the **single source of truth** for every downstream
> consumer — FR-08 (LLM), FR-13 (`scoring` tool), FR-14
> (`decision_gate` tool), FR-15 (`report_gen` tool). If a finding is
> not in the chain, it does not exist.
> If it is in the chain, it must be attributable.

## When to Use

- Before writing ANY indicator from any skill workflow.
- When deciding which bucket a new finding belongs in.
- When labelling `kind: fact` vs `kind: inference`.
- When constructing `evidence_refs` / `derived_from` for a derived indicator.

**Do not** write to the chain by hand-crafting JSON on disk. The only
supported writer is `evidence_chain.append_indicator` — the store rejects
`update` / `delete` calls by design (FR-09 AC-8 / ADR-02).

## Indicator Schema (summary)

Full pydantic definition lives in `binary_analysis.schema.indicator.Indicator`
(C2, frozen at Indicator `schema_version = "1.0.0"`). E2E-02 extends the
evidence-chain snapshot to v1.1.0 by adding document buckets only; it does not
add Indicator fields. The fields this protocol governs (field names MUST match
the pydantic model exactly — the store rejects extra fields):

| Field | Required | Notes |
|-------|----------|-------|
| `id` | auto | ULID assigned by `EvidenceChainStore` when omitted; globally unique (IR-12). Do not set by hand. |
| `source_fr` | ✅ | The FR that produced this indicator, e.g. `"FR-04"`, `"FR-08"`. |
| `indicator_type` | ✅ | Short snake_case label, e.g. `suspicious_import`, `c2_url`, `high_entropy_section`, `analysis_coverage`. |
| `severity` | ✅ | `"INFO" \| "WARNING" \| "CRITICAL"` — **three levels only** (see `schema.indicator.Severity`). Do NOT emit `LOW` / `MEDIUM` / `HIGH` for severity; those values belong to `confidence`. |
| `confidence` | ✅ for `inference` / optional for `fact` | `"HIGH" \| "MEDIUM" \| "LOW"` (see `schema.indicator.Confidence`). Facts may omit this field. |
| `kind` | ✅ | Literal `"fact"` or `"inference"` (ADR-03). No other values. |
| `evidence_refs` | ✅ for `inference` | Non-empty list of `Indicator.id` values this inference rests on. Facts default to an empty list. |
| `derived_from` | optional | List of tool-invocation / audit log refs. Use when the Indicator has no upstream chain-internal refs (atomic fact). |
| `created_at` | auto | UTC datetime; auto-populated when omitted. |
| `data` | ✅ | Structured JSON payload. Content schema is bucket-specific. Sample-derived strings inside `data` MUST be sanitised (see Proto-03) before the Indicator is read back into an LLM context. |

The producing tool name (`"file_identify"`, `"pefile"`, `"ghidra"`,
`"yara"`, …) is NOT a schema field — it is recorded separately in
`<analysis_id>.audit.jsonl` via `log_indicator_write` / `log_tool_call`.
If you need the provenance inside the Indicator itself, put it under
`data.producer` or `data.tool`.

The bucket is NOT a field on the Indicator either — it is the first
argument to `EvidenceChainStore.append(bucket, indicator)` /
`evidence_chain.append_indicator(bucket=..., ...)`. One Indicator
lives in exactly one bucket.

## Buckets and Routing

The `Bucket` StrEnum in `schema.evidence_chain` has 21 members in v1.1.0:
the original 17 binary buckets plus 4 document buckets added additively for
E2E-02. The **stage → bucket** map below routes each finding to its primary
bucket. If a finding belongs in two buckets, write it to the primary bucket
and cross-reference via `evidence_refs` from a second Indicator — do not
duplicate payload.

| Bucket | Who writes | Typical `indicator_type` examples |
|--------|------------|-----------------------------------|
| `file_meta` | `file_identify` tool | `pe_detected`, `elf_detected`, `macho_detected`, `sha256`, `ssdeep`, `size_bytes` |
| `triage` | FR-02 heuristic routing | `triage_risk_level`, `recommended_strategy`, `packing_severity_hint`, `triage_signal_summary` |
| `headers` | FR-04 structural parsers | `pe_rich_header`, `elf_dynamic_entry`, `macho_load_cmd`, `malformed_structure` |
| `imports` | FR-04 | `suspicious_import`, `imphash`, `import_count` |
| `exports` | FR-04 | `export_symbol`, `export_count` |
| `sections` | FR-04 / FR-05 | `writable_executable_section`, `section_name_anomaly` |
| `resources` | FR-04 | `high_entropy_resource`, `executable_resource` |
| `debug_info` | FR-04 | `pdb_path`, `debug_guid` |
| `entropy` | FR-05 | `overall_entropy`, `entropy_histogram`, `entropy_anomaly` |
| `packer` | FR-05 | `high_entropy_section`, `upx_signature`, `commercial_packer_match`, `unpack_result`, `tool_missing` |
| `strings_iocs` | FR-06 (after Proto-03 sanitisation) | `c2_url`, `ipv4`, `domain`, `registry_path`, `mutex`, `anti_debug_string` |
| `disassembly` | FR-07 | `function_tag`, `crypto_constant`, `anti_debug_pattern` |
| `behavior_chain` | FR-17 | `process_injection_node`, `persistence_node`, `c2_exfil_node`, `module_chain_summary`, `targeted_attack_indicator` |
| `llm_inferences` | FR-08 / FR-13 workflows | `gap_note`, `family_candidate`, `family_config`, `family_divergence`, `family_absent`, `threat_class`, `verdict`, `self_consistency_downgrade` |
| `scoring` | FR-13 `scoring` tool | `rule_match`, `risk_score`, `verdict`, `verdict_divergence` |
| `decision_gate` | FR-14 `decision_gate` tool | `recommended_escalation`, `escalation_reason` |
| `dynamic_behavior` | *(reserved — v1.5)* | empty placeholder in v1; do NOT write here |
| `document_analysis` | `document_extract` / deterministic document rules | protected v1.1 bucket; `indicator_type` must come from `indicator_types_v1_1.DOC_ANALYSIS_TYPES` |
| `macro_analysis` | `document_extract` / sandbox VBA or XL4 workers | protected v1.1 bucket; `indicator_type` must come from `indicator_types_v1_1.MACRO_ANALYSIS_TYPES` |
| `embedded_payloads` | `document_extract` / recursion controller | protected v1.1 bucket; `indicator_type` must come from `indicator_types_v1_1.EMBEDDED_PAYLOADS_TYPES` |
| `delivery_chain_doc` | recursion controller / deterministic document rules | protected v1.1 bucket; `indicator_type` must come from `indicator_types_v1_1.DELIVERY_CHAIN_DOC_TYPES` |

**`analysis_coverage` is a cross-bucket *convention*, not a bucket.**
When a stage downgrades (tool missing, strategic skip, token-budget
truncation), append an Indicator with `indicator_type="analysis_coverage"`
and `data={"dimension": <str>, "status": "COMPLETED"|"DEGRADED"|"SKIPPED",
"reason": <str>}` into the most-relevant domain bucket (e.g.
`strings_iocs` for FLOSS timeouts, `disassembly` for decompiler downgrades,
`behavior_chain` for FR-17 skips, or `llm_inferences` when the downgrade
is LLM-driven). `report_gen` scans all buckets for these markers and
surfaces them in the `analysis_coverage` report section (FR-15 AC-6).

**`audit_gaps` is a cross-bucket *convention*, not a bucket.** When the
LLM notes a missing check that contradicts a fact, emit an `inference`
into `llm_inferences` with `indicator_type="audit_gap"` and non-empty
`evidence_refs` back to the contradicting `fact`.

## Fact vs Inference Decision Rule

Use this single decision tree before every `append_indicator`:

```text
Is the claim fully derivable from a deterministic tool's output
without any LLM reasoning step?
├── Yes  → kind: "fact"
│         severity: from tool or the bucket-specific rule
│         (INFO / WARNING / CRITICAL — 3 levels only)
│         confidence: optional; omit for deterministic facts
│         evidence_refs: optional (empty list is fine for atomic facts)
│         data.producer: optional string naming the producing tool
└── No   → kind: "inference"
          confidence: HIGH | MEDIUM | LOW   (required; see calibration below)
          evidence_refs: non-empty list of fact IDs the inference rests on
          (if truly foundational, use derived_from to cite an audit-log
           tool-invocation ID — but empty evidence_refs + empty
           derived_from is rejected by the inference validator)
```

### Confidence calibration (inferences only)

- `HIGH` — The inference would hold for any analyst given the same facts.
  Typical trigger: a strong multi-signal convergence (YARA match + matching
  imphash + matching Rich Header).
- `MEDIUM` — The inference is the best explanation but alternatives exist.
  Typical trigger: a single strong signal (one family-specific string) or
  multiple weak signals that only together point at the same conclusion.
- `LOW` — Speculative or based on incomplete coverage (e.g. decompilation
  unavailable). Downstream consumers may demote or ignore these.

## Required Fields per Bucket

| Bucket | `kind` constraints | Extra bucket-specific rules |
|--------|--------------------|-----------------------------|
| `file_meta` | fact only | populate `data.producer = "file_identify"` for traceability |
| `triage`, `headers`, `imports`, `exports`, `sections`, `resources`, `debug_info`, `entropy`, `packer`, `disassembly`, `behavior_chain` | facts AND inferences | inferences require non-empty `evidence_refs` |
| `strings_iocs` | facts AND inferences | sample-derived strings inside `data.*` MUST be sanitised (Proto-03) when the Indicator may be read back into an LLM context |
| `llm_inferences` | inference only (plus `fact` Indicators with `indicator_type="analysis_coverage"` recording LLM-stage downgrades) | inferences require non-empty `evidence_refs`; cross-bucket `audit_gap` / `analysis_coverage` markers may also live here |
| `scoring` | fact only (rule-engine output) | LLM-side divergence is recorded as `data.verdict_divergence` on the rule-engine Indicator; it is NOT a separate `inference` Indicator |
| `decision_gate` | fact only | produced by `decision_gate` as a pure function over `scoring` plus cross-bucket `analysis_coverage` markers |
| `dynamic_behavior` | ∅ | reserved for v1.5 external sandbox integration; MUST remain empty in v1 |
| `document_analysis`, `macro_analysis`, `embedded_payloads`, `delivery_chain_doc` | deterministic facts only | protected document buckets; LLM conclusions MUST go to `llm_inferences`, and `indicator_type` values are validated by `indicator_types_v1_1` |

`analysis_coverage` (cross-bucket convention): `kind="fact"`,
`indicator_type="analysis_coverage"`, `data.dimension` ∈
{`structure`, `entropy`, `strings`, `decompilation`, `behavior_chain`,
`llm_inferences`}, `data.status` ∈ {`COMPLETED`, `DEGRADED`, `SKIPPED`},
optional `data.reason`.  One Indicator per (stage, downgrade) pair.

## `suspicious_import` payload convention (FR-04 → FR-07)

The `imports` bucket carries one `suspicious_import` `fact` per high-risk
imported symbol that FR-07's priority queue may want to seed
decompilation from. The schema is **format-neutral** (PE / ELF / Mach-O
all use the same `indicator_type`); format-specific aggregate facts
(`elf_capability`, `macho_capability`, …) live alongside it but are not
the FR-07 priority feed.

| `data.*` field | Required | Notes |
|----------------|----------|-------|
| `producer` | ✅ | `"pefile"` / `"lief"` / `"otool"`, etc. |
| `module` | ✅ | Library / DLL name — format-neutral (`kernel32.dll`, `libc.so.6`, `/usr/lib/libcurl.dylib`). PE skill MAY also emit a legacy `dll` alias for backward compatibility; new consumers SHOULD prefer `module`. |
| `symbol` | ✅ | The imported function / dynamic symbol name. |
| `capability` | optional | One of `process_manipulation` / `dynamic_loading` / `network` / `crypto` / `persistence` / `anti_debug` when the writer wants to pre-classify; otherwise omit. |
| `thunk_addr` | optional | Hex string (e.g. `"0x402008"`). PE IAT entry / ELF PLT entry / Mach-O `__la_symbol_ptr` slot. **Resolves to the import stub, not the user function** — provided for completeness; FR-07 SHOULD prefer `data.callers` (below) when present. |
| `callers` | optional | List of `{"addr": "0x...", "name": "<func or null>"}` — the user functions that reference the import. The producer computes this best-effort by scanning `.text` (PE) / executable segments (ELF / Mach-O) for instructions referencing `thunk_addr`, then walking back to the containing function. Empty / omitted means the producer either could not perform the xref scan or the symbol is unreferenced. FR-07 Step 0 emits one priority-queue token per caller — `<caller_name>@<caller_addr>`, falling back to `FUN_<addr>@<addr>` when `name` is null — so the priority list resolves to user functions instead of import stubs. |

## Minimal Examples

Fact from FR-04 (suspicious import) written into the `imports` bucket.
The minimum required shape (legacy PE compatibility) is the first
example; the second example shows the full schema including the
optional caller xref FR-07 prefers.

```json
{
  "source_fr": "FR-04",
  "indicator_type": "suspicious_import",
  "severity": "WARNING",
  "kind": "fact",
  "evidence_refs": [],
  "data": {
    "producer": "pefile",
    "module": "kernel32.dll",
    "dll": "kernel32.dll",
    "symbol": "VirtualAllocEx",
    "capability": "process_manipulation"
  }
}
```

```json
{
  "source_fr": "FR-04",
  "indicator_type": "suspicious_import",
  "severity": "WARNING",
  "kind": "fact",
  "evidence_refs": [],
  "data": {
    "producer": "pefile",
    "module": "kernel32.dll",
    "dll": "kernel32.dll",
    "symbol": "CreateRemoteThread",
    "capability": "process_manipulation",
    "thunk_addr": "0x402008",
    "callers": [
      {"addr": "0x401a40", "name": "main"},
      {"addr": "0x401d80", "name": null}
    ]
  }
}
```

Inference from FR-08 citing the fact above, appended into the
`behavior_chain` bucket:

```json
{
  "source_fr": "FR-08",
  "indicator_type": "process_injection_candidate",
  "severity": "CRITICAL",
  "confidence": "MEDIUM",
  "kind": "inference",
  "evidence_refs": [
    "<id-of-VirtualAllocEx-fact>",
    "<id-of-WriteProcessMemory-fact>",
    "<id-of-CreateRemoteThread-fact>"
  ],
  "data": {
    "technique": "T1055.002",
    "rationale": "classic VirtualAllocEx + WriteProcessMemory + CreateRemoteThread triad"
  }
}
```

Analysis-coverage marker recording a strategic FR-07 skip, appended
into the `disassembly` bucket:

```json
{
  "source_fr": "FR-07",
  "indicator_type": "analysis_coverage",
  "severity": "INFO",
  "kind": "fact",
  "evidence_refs": [],
  "data": {
    "dimension": "decompilation",
    "status": "SKIPPED",
    "reason": "fr02_ac8_strategic_skip"
  }
}
```

## Anti-Patterns

- ❌ Writing an `inference` with an empty `evidence_refs` and no
  `derived_from`. If the claim has no upstream, it is speculation —
  either downgrade to `confidence: "LOW"` with a `derived_from`
  pointing at the raw tool-log audit ID, or drop it. The inference
  validator in `schema.indicator` rejects the empty case at
  construction time.
- ❌ Using `kind: "fact"` for an LLM-written Indicator. If the model
  produced it, it is an `inference`, period.
- ❌ Mutating an existing Indicator (e.g. "upgrade severity later").
  The store rejects `update` / `delete` by design (FR-09 AC-8). Append
  a new Indicator with `evidence_refs` pointing at the prior one and
  `indicator_type="severity_revision"`.
- ❌ Writing unsanitised sample-derived strings into `strings_iocs`
  payloads. Proto-03 must be applied first.
- ❌ Using `severity: "HIGH"` / `"MEDIUM"` / `"LOW"`. Those values
  belong to `confidence`. `severity` is strictly
  `INFO` / `WARNING` / `CRITICAL`.
- ❌ Using field names `tag` / `value` / `tool` on the Indicator
  itself. They do not exist in the pydantic model — the store rejects
  them as extra fields. Use `indicator_type` / `data` / (record the
  producer under `data.producer` or via the audit log).
- ❌ Writing to non-existent buckets (`packing`, `analysis_coverage`,
  `audit_gaps`). `packing` is spelled `packer` in the Bucket enum;
  the other two are cross-bucket conventions, not buckets.
- ❌ Writing LLM conclusions directly into `document_analysis`,
  `macro_analysis`, `embedded_payloads`, or `delivery_chain_doc`. Those
  protected v1.1 buckets are owned by `document_extract`, deterministic
  rules, and recursion bookkeeping; LLM document conclusions belong in
  `llm_inferences`.

## Output Format

This skill is a contract, not a workflow. Successful application is visible in
the shape of the evidence chain:

- Every `inference` carries a non-empty `evidence_refs` (or an explicit
  `derived_from`) plus a `confidence`.
- Every `fact` has a `source_fr` and, where useful, a `data.producer`.
- Every stage downgrade is mirrored by an `analysis_coverage` Indicator
  appended into the most-relevant domain bucket.
- Every bucket name comes from the 21-member `Bucket` enum (no
  `packing` / `analysis_coverage` / `audit_gaps` buckets).
- Protected document buckets use `indicator_types_v1_1` values only; LLM
  document reasoning is stored as `llm_inferences`.
