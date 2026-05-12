---
name: document-analysis-e2e-orchestrator
description: |
  Top-level orchestrator for E2E-02 document-centric malware analysis.
  When file_identify returns document_tier ∈ {P0,P1,P2} or
  document_format ∈ {ooxml_*, ole2_*, pdf, rtf, hta, onenote, encrypted_office},
  **read this skill first**. Maps the nine E2E-02 phases (FR-01, FR-03, FR-06, FR-08, FR-09,
  FR-13, FR-14, FR-15, FR-30) to recommended sub-skills, the evidence-chain buckets each phase
  must write, and downgrade paths when tools are unavailable. Applies to any document-centric
  malware analysis request: Office macro carriers, PDF trigger analysis, RTF/HTA script
  embedding, OneNote / encrypted Office partial analysis, polyglot document+PE routing.
license: Apache-2.0
compatibility: deepagents>=0.4.3 · binary_analysis E2E-02 v1
allowed-tools: sandbox_session bash python_exec file_read file_identify document_extract evidence_chain scoring decision_gate report_gen
metadata:
  id: Proto-02
  role: orchestrator
  version: 1.0.0
  batch: P1
  adr: ADR-11, ADR-14, ADR-15, ADR-DOC-10
  fr: FR-01, FR-03, FR-06, FR-08, FR-09, FR-13, FR-14, FR-15, FR-30
  stability: stable
---

# Document analysis E2E-02 orchestrator

This skill owns only the document path’s Stage Map, phase scheduling, required skill reads, and downgrade paths. The binary path is owned by `binary-analysis-e2e-orchestrator`; concrete parsing, IOCs, macro simulation, and reporting methodology belong to referenced tools or workflow skills.

## When to Use

- Use this skill when `file_identify.document_tier ∈ {P0, P1, P2}`, or `document_format` is `ooxml_*`, `ole2_*`, `pdf`, `rtf`, `hta`, `onenote`, or `encrypted_office`.
- Read this skill before any document workflow skill or before calling `document_extract`.
- If `document_tier` is empty and the format is PE / ELF / Mach-O, stop the document path and read `binary-analysis-e2e-orchestrator` instead.

## Operating Principles

- **Sandbox-only VBA.** VBA / vmonkey simulation runs only in sandbox-routed subprocesses; the host must not directly import or execute Office, Adobe Reader, vmonkey, or parser packages.
- **Mode exclusivity (mutually exclusive).** The parent document session uses only this document Stage Map. Embedded PE / ELF / Mach-O are analyzed via FR-30 recursive child sessions; do not inline the binary Stage Map into the parent document path.
- **Protected document buckets.** `document_analysis`, `macro_analysis`, `embedded_payloads`, and `delivery_chain_doc` are owned by `document_extract`, deterministic rules, and schema allowlists. LLM conclusions go in `llm_inferences`; `analysis_coverage` goes in inherited buckets such as `strings_iocs` and `llm_inferences`, not into the four protected document buckets.
- **Password and sample hygiene.** Password attempts and raw sample bytes must not enter LLM context, tool parameters, or audit logs in cleartext.
- **Sandbox session boundary.** Before calling `document_extract`, `bash`, `python_exec`, or `file_read`, if no session exists yet, call only `sandbox_session(action="create")` to create one; do not use it to bypass the `file_identify` first hop or to read raw document samples directly.
- **No shell filtering of raw samples.** Even when `bash` is available, do not use `grep`, `cat`, `head`, `tail`, `xxd`, `hexdump`, or `od` to read or filter the raw document sample. Document string surfaces come from `document_extract` facts; on parser failure, use only bounded ASCII / UTF-16 extraction via `python_exec`, returning structured, length-limited, sanitized snippets or counts.

## Stage map

Each phase describes only the scheduling surface: primary tool, required skill reads, target bucket, completion signal, and downgrade path.

### Scheduling rules

- Strict order: FR-01 → FR-03; FR-03 → FR-06 → FR-30; FR-09 → FR-08 → FR-13 → FR-14 → FR-15.
- After `document_extract` returns, FR-06 IOC classification and FR-30 embedded-payload routing may be planned in the same LLM turn.
- FR-09 may run after the last write needed for current reasoning; it does not require a dedicated turn.
- When parsers or recursion branches are incomplete, append named downgrade / coverage indicators and continue only along the documented paths below.

### Stage FR-01 · Confirm file identification result

- Tool: none. The `file_identify` first hop is already done per `agent.md`; this phase only consumes `file_meta`, without calling again.
- Recommended skills: none
- Bucket: `file_meta`
- Completion signal: first-hop result is written to `file_meta`, including `document_format`, `document_tier`, and sha256 facts; or a `format_unsupported` fact explaining why the document pipeline cannot start.
- Downgrade: stop on unsupported / empty / oversize input with `Verdict=UNKNOWN` and `escalation=MANUAL_REVERSE`. Binary formats reroute to the binary orchestrator.

### Stage FR-03 · Document extraction and script simulation

- Tool: `document_extract`
- Recommended skills: none; parser orchestration is owned by the tool.
- Buckets: `document_analysis`, `macro_analysis`, `embedded_payloads`
- Completion signal: `document_extract.status ∈ {ok, degraded}`; document facts exist; macro facts or `no_macro_found` exist; embedded payloads recorded if present.
- Downgrade:
  - `document_parser_failed`: fall back to string-level extraction and append `analysis_coverage` to `strings_iocs`.
  - `vba_simulation_timeout`: keep static olevba facts and append `vba_simulation_gap`; runtime string reconstruction unavailable.
  - `encrypted_office_no_password`: after password exhaustion, consume any protected OLE fallback facts from `document_extract`; continue to FR-06 / FR-08 when macro, trigger, or IOC facts exist, otherwise stop after outer metadata with unknown verdict and manual reverse escalation.
  - `onenote_parser_unavailable`: fall back to byte-level ASCII / UTF-16 extraction and OneNote object signature scanning.

### Stage FR-06 · Strings and IOC extraction

- Tool: `python_exec` to classify IOCs from document-derived strings and macro / script facts.
- Execution rules: classify only strings derived from `document_extract`, or controlled string surfaces from `python_exec` on the parser downgrade path; do not scan the raw sample with shell filters.
- Required skill reads before FR-06:
  - Read `/subagent-skills/binary-analysis/binary-analysis-ioc-extraction-workflow/SKILL.md`.
  - Read `/subagent-skills/binary-analysis/binary-analysis-sanitize-untrusted-strings/SKILL.md`.
- Bucket: `strings_iocs`
- Completion signal: classified IOC facts written or `no_ioc_found`; document-derived strings defanged / sanitized before entering the LLM.
- Downgrade: no IOCs is not failure; record `no_ioc_found` and continue to FR-30.

### Stage FR-30 · Embedded payload routing and recursive analysis

- Tool: `document_extract` results plus host recursive child-session protocol (`build_binary_analyst_agent`), not `task`.
- Recommended skills: none; recursion protocol is owned by the host.
- Buckets: `delivery_chain_doc`, `embedded_payloads`
- Completion signal: each embedded payload is linked to child analysis, archived as non-recursive payload, or marked depth-limited.
- Downgrade:
  - `recursion_budget_exceeded`: preserve child-sample completeness, set `doc_analysis_partial=true` on the parent document, and continue with trimmed parent-level reasoning.
  - `recursion_depth_exceeded`: record deepest unanalyzed payload; do not recurse further.

### Stage FR-09 · Evidence chain snapshot

- Tool: `evidence_chain`
- Required skill reads before FR-09:
  - Read `/subagent-skills/binary-analysis/binary-analysis-evidence-chain-protocol/SKILL.md`.
- Buckets: read all buckets; this phase does not write.
- Completion signal: snapshot includes document and inherited buckets needed for FR-08 and rule tools.
- Downgrade: none.

### Stage FR-08 · LLM semantic analysis

- Tool: none; this phase is the LLM reasoning loop over the document evidence snapshot.
- Required skill reads before FR-08:
  - Read `/subagent-skills/binary-analysis/binary-analysis-evidence-chain-protocol/SKILL.md`.
  - Read `/subagent-skills/binary-analysis/binary-analysis-sanitize-untrusted-strings/SKILL.md`.
- Conditional skill reads:
  - Office active content → read `/subagent-skills/binary-analysis/analyzing-macro-malware-in-office-documents/SKILL.md`.
  - PDF triggers / objects → read `/subagent-skills/binary-analysis/analyzing-pdf-malware-with-pdfid/SKILL.md`.
- Bucket: `llm_inferences`; if reasoning is tightly bound to existing IOC facts, may also write `strings_iocs`.
- Completion signal:
  - **Quick scan**: write initial document threat hypotheses from FR-03 facts.
  - **Deep dive**: write evidence-backed reasoning from macro events, PDF / RTF / HTA triggers, IOC clustering, and embedded-payload links.
  - **Synthesis**: run self-consistency checks on parent document facts vs child-sample facts; on conflict or incomplete evidence, append confidence downgrade inferences.
- Document-specific inference rules:
  - `doc_analysis_partial=true`, `vba_simulation_gap`, parser fallback, and child-analysis gaps must all factor into confidence downgrade.
  - Parent vs child evidence views stay separated; parent reasoning cites parent facts; child-sample verdicts remain child-level facts for document rules to consume.
- Downgrade: if the LLM provider is unreachable or schema errors repeat, return a fact-level report with `Verdict=UNKNOWN` and `escalation=MANUAL_REVERSE`.

### Stage FR-13 · Scoring, classification, and document_role

- Tool: `scoring`
- Recommended skills:
  - Read `binary-analysis-family-triage-workflow` only when a completed child binary analysis supplies family evidence.
- Bucket: `scoring`
- Completion signal: verdict, risk score, and deterministic `document_role` written.
- Downgrade: unknown downgrade reasons must use the finite enum, including `document_parser_failed`, `encrypted_office_no_password`, `onenote_parser_unavailable`, `recursion_budget_exceeded`; fail fast when rules are missing.

### Stage FR-14 · Decision gate

- Tool: `decision_gate`
- Recommended skills:
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
- Completion signal: JSON and Markdown reports generated with `schema_version="1.1.0"`; when applicable include document buckets, `document_role`, `doc_analysis_partial`, and `unknown_downgrade_reason`.
- User-visible output: do not only say “detailed report written to: …”. The final explicit response must keep a brief conclusion and append `## Appendix: Detailed report`, pasting the full `markdown_content` returned by `report_gen` into the appendix; if response budget is tight, show segments and state clearly that the remainder is still at `md_path`.
- Downgrade: fail fast on schema mismatch. `report_gen.output_dir` is a host path, not `/workspace/<analysis_id>/...`; do not call `file_read` on generated host reports.

## Downgrade paths

- `document_parser_failed`: fatal parser error; fall back to string extraction and write downgrade coverage outside protected document buckets.
- `vba_simulation_timeout`: sandbox VBA simulation timed out; keep static extraction and mark incomplete simulation coverage.
- `encrypted_office_no_password`: password dictionary exhausted; if protected OLE fallback facts exist, continue with `doc_analysis_partial=true` semantics and lower confidence, otherwise stop after outer metadata, unknown verdict and manual reverse escalation.
- `onenote_parser_unavailable`: OneNote parser missing; use byte-level strings and GUID scanning.
- `recursion_budget_exceeded`: recursion budget exhausted; set `doc_analysis_partial=true`, preserve child analysis results, and lower parent document inference confidence.
