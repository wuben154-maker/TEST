---
name: analyzing-ransomware-encryption-mechanisms
description: |
  This skill maps FR-08 / FR-13 ransomware-encryption interpretation from static E2E-01 evidence
  (hybrid ciphers, key wrapping, IV handling, weak-implementation heuristics) into
  `llm_inferences` and family-oriented scoring, without running host-side production
  decryptors. Activates when `binary-analysis-e2e-orchestrator/references/fr08-signal-matrix.md`
  matches the ransomware row, when `binary-analysis-family-triage-workflow` fires the
  FR-13 `ransomware` gate, or when `two-phase-behavior-chain-reconstruction` delegates
  `ransomware_behavior`. Use when analysts need 勒索软件 / 加密机制 / 密钥封装 reasoning,
  AES–RSA hybrids, ChaCha20 or Salsa stories, ransomware family triage,
  decryptor-feasibility hypotheses, or offline NoMoreRansom-style pointers (never as live
  tool calls here). Keywords: ransomware family, encryption analysis, key recovery.
domain: cybersecurity
subdomain: malware-analysis
tags:
- malware
- ransomware
- encryption
- cryptanalysis
- reverse-engineering
version: 1.0.0
author: mahipal
license: Apache-2.0
nist_csf:
- DE.AE-02
- RS.AN-03
- ID.RA-01
- DE.CM-01
---

# Analyzing Ransomware Encryption Mechanisms

## Role (single ownership)

- **Class:** FR-08 / FR-13 **workflow specialist** (family- and scheme-oriented interpretation on top of evidence already collected by the pipeline). This file does not replace `binary-analysis-e2e-orchestrator` stage scheduling, `ghidra-priority-queue-workflow` invocation shapes, or the rule engine behind `scoring` (ADR-04).
- **Not in scope here:** end-user data recovery, paying ransoms, or executing untrusted decryptor binaries outside the analysis sandbox.

## Upstream, downstream, and return

| Direction | Party | Contract |
|----------|--------|----------|
| **Who triggers this skill** | `binary-analysis-e2e-orchestrator` (Stage **FR-08** after the evidence snapshot) when `binary-analysis-e2e-orchestrator/references/fr08-signal-matrix.md` (ransomware row) matches; `binary-analysis-family-triage-workflow` when the **`ransomware`** gate fires at **FR-13** (see that workflow’s specialist table); and/or `two-phase-behavior-chain-reconstruction` when the **ransomware_behavior** row delegates here. | Load this `SKILL.md` only if the combined facts justify it; do not preload when only generic crypto imports exist. |
| **This skill defers to** | `ghidra-priority-queue-workflow`, `binary-analysis-sanitize-untrusted-strings`, `binary-analysis-evidence-chain-protocol` (Proto-02) | Method shapes, sanitize before any LLM-facing text, and Indicator schema. Append indicators with `source_fr` per the `Indicator` model (not the rubric alias `source_skill`). |
| **When to add** `reverse-engineering-ransomware-encryption-routine` | After **FR-07** exports enough decompiled or managed material to name functions on the file-encrypt path | Use that skill for per-routine disassembly of key flow; this skill stays at scheme / evidence-mapping level. |
| **When to return to the orchestrator** | After emitting the required `llm_inferences` Indicators (or a `gap_note` / `analysis_coverage` fact when facts are missing) | FR-13 `scoring` and FR-15 `report_gen` need traceable, cited inferences. |
| **Document / parent path** | If `doc_analysis_partial` or nested-binary coverage blocks encryption facts | Follow `document-analysis-e2e-orchestrator` and do not force a ransomware family on the parent. |

**Downgrade (orchestrator-aligned):** If **FR-07** is skipped (`decompiler_unavailable`, `fr02_ac8_strategic_skip`, or related `analysis_coverage` reasons in `disassembly`), reason about what is still provable from `imports`, `strings_iocs`, and partial `behavior_chain` only, append a coverage-style fact or `gap_note`, and avoid inventing per-function crypto flows.

## When to Use

- Crypto-related imports or decompiled call sites exist together with file-targeting, ransom-note filename patterns, or behavior edges suggesting bulk file encryption.
- The session question asks for encryption **scheme**, KDF, key-wrapping model, or feasibility at the level of **indicators and hypotheses** for the evidence chain.
- A **family** or pattern-class label is needed in `llm_inferences` with citation back to `imports` / `strings_iocs` / `disassembly` / `behavior_chain` fact ids.

**Do not use** as the only source for **IOC extraction** (use `binary-analysis-ioc-extraction-workflow` / FR-06) or for **YARA** authoring (dedicated YARA skills). Do not claim decryptability without a cited weak-implementation or public-decryptor fact.

## Runtime contract (tools, sandbox, and bytes)

- **Allowed tools** per the repo **`contracts.md`** tool boundary (5+3+1 plus `document_extract` on the document tier only): `file_identify`, `evidence_chain`, `scoring`, `decision_gate`, `report_gen`, `bash`, `python_exec`, `file_read`, `sandbox_session` (`SandboxSessionTool`). `document_extract` is callable **only** after `document-analysis-e2e-orchestrator` is loaded and only for document-tier samples (E2E-02). Use primitives **after** `sandbox_session` establishes `/workspace/<analysis_id>/` per the parent orchestrator. **Do not** name forbidden or non-runtime tools (`pe_dump`, `network_capture`, `shell_exec`, `task`, or other unwired names).
- **Zero raw host sample bytes in LLM context:** never paste unbounded hexdumps. Any quoted sample-derived string must go through the Proto-03 path described in `binary-analysis-sanitize-untrusted-strings`. Use `{open_tag}` / `{close_tag}` in prompts only as injected by the runtime control plane (`build-contracts` scope A).
- **Facts vs inference (ADR-03, IR-01):** only tool outputs and normalized evidence records are `kind="fact"`. Ransomware **scheme conclusions** and family-like labels for this layer belong in **`llm_inferences`** with `kind="inference"` and non-empty `evidence_refs` pointing at the supporting fact rows.

## NFR-05 and prompt control

Token rounds and ceilings are bounded by the parent `agent.md` and orchestrator (`{max_rounds}`, `{token_budget}`, `{threshold_pct}`). Read this skill **once** when a gate or matrix row fires; move long pattern tables to `references/api-reference.md` and open that reference only when a subsection is needed.

## Workflow

### 1) Read existing facts (no new file_identify)

Consume `file_meta`, `imports` / `sections` / `headers` (as present), `strings_iocs`, `packer`, `triage`, `disassembly`, and `behavior_chain` from the evidence snapshot. Do not assert PE/ELF import tables from memory—cite fact ids.

### 2) Reconstruct a scheme narrative

- Map observed APIs (CryptoAPI, CNG, OpenSSL, libsodium, custom constants) to an expected **hybrid** story: per-file or per-blob symmetric key, mode (CBC/CTR/GCM/ECB), IV/nonce source, and asymmetric wrapping (RSA, ECDH) if imports or decompilation support it.
- Check `strings_iocs` and `behavior_chain` for extension lists, note filenames, and shadow-volume deletion only as **defanged** or summarized facts already stored.

### 3) Weakest-link heuristics (inference, not new facts)

- Flag predictable seeds, key reuse, ECB, missing IV randomness, or hard-coded keys only when a **cited** fact or decompiler excerpt supports the claim. Otherwise use a **`gap_note`** with `missing_evidence` instead of a strong conclusion.

### 4) Write Indicators to `llm_inferences`

Follow `binary-analysis-e2e-orchestrator/references/fr08-signal-matrix.md` minimal shapes. Prefer:

- `indicator_type: threat_class` with `data.classes` including `Ransomware` and `data.hypotheses: ["ransomware_encryption"]` when the three signal groups in that matrix are satisfied.
- `indicator_type: family_candidate` with `data.specialist_skill: "analyzing-ransomware-encryption-mechanisms"` when a class-like watermark or unique scheme points to a named family, still with `evidence_refs`.
- `indicator_type: gap_note` when the gate fired weakly (e.g. only generic crypto) or when FR-17 coverage is too thin to tie crypto to victim-file operations.

`source_fr` should be `FR-08` when the hand-off is from the signal matrix, or `FR-13` when the family-triage gate emitted the load request—match the active stage in the parent orchestrator’s schedule. When calling `evidence_chain.append_indicator`, set `bucket="llm_inferences"` for these rows.

#### Example inference shape (Proto-02)

Template only—replace placeholder ids; validate against Proto-02 before append:

```json
{
  "source_fr": "FR-08",
  "bucket": "llm_inferences",
  "indicator_type": "threat_class",
  "severity": "WARNING",
  "confidence": "HIGH",
  "kind": "inference",
  "evidence_refs": ["<fact-import-1>", "<fact-string-2>", "<fact-behavior-3>"],
  "data": {
    "classes": ["Ransomware"],
    "hypotheses": ["ransomware_encryption"],
    "rationale": "Sanitized: crypto API triad, document-extension bulk ops, and ransom-note filename in strings_iocs (see fact ids)."
  }
}
```

### 5) Optional: deeper routine analysis

If `decompiled_function` / `function_tag` data ties named routines to the encrypt path, load **`reverse-engineering-ransomware-encryption-routine`** and merge conclusions without duplicating that skill’s disassembly checklists here.

## Degradation

| Condition | Action |
|-----------|--------|
| FR-07 skipped (`decompiler_unavailable`, `fr02_ac8_strategic_skip`, or thin `disassembly` / `analysis_coverage` reasons) | Stay with static facts only; add `gap_note` or `analysis_coverage`; do not invent per-function crypto flows. |
| FR-17 skipped | State the behavior-chain gap per orchestrator; lower confidence when linking crypto APIs to victim-file operations. |
| `doc_analysis_partial` or nested-binary coverage blocks encryption facts | Follow `document-analysis-e2e-orchestrator`; do not force a ransomware family label on the parent context. |
| Gate fired on generic crypto only (weak matrix match) | Prefer `gap_note` with `missing_evidence` over a high-confidence `threat_class`. |

## Output expectations for the analyst

- A concise **Encryption scheme** paragraph: algorithm family, key lifecycle, and what is still unknown.
- A **feasibility** line framed as *hypothesis* with confidence and `evidence_refs`, not a guarantee.
- A pointer to public decryptor research (`references/api-reference.md` external links) only as **recommendation to verify offline**, not as tool invocation in this example.

## References (progressive disclosure)

- `references/api-reference.md` — algorithm cheat sheets, import name tables, and known-family pattern notes. Read only when a subsection is required to stay within `{token_budget}`.
