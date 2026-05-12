---
name: reverse-engineering-ransomware-encryption-routine
description: |
  Third-person secondary FR-07 specialist: links Ghidra or managed decompiler
  output to a concrete per-function ransomware encryption path (API surfaces,
  key/IV materialisation, and hybrid wrapping) only after
  `analyzing-ransomware-encryption-mechanisms` and FR-04/06 evidence justify it.
  Does not start decompilation or family verdicts. Triggers on ransomware
  routine reverse engineering, 勒索软件 加密例程, hybrid AES/RSA, ChaCha20,
  CryptoAPI, BCrypt, key-flow tracing, decompiled crypto path, or when
  `binary-analysis-family-triage-workflow` / the FR-08 signal matrix defers
  here for deeper function-level detail.
domain: cybersecurity
subdomain: malware-analysis
tags:
- ransomware
- encryption
- reverse-engineering
- cryptanalysis
- aes
- rsa
- decryption
- malware-analysis
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
- DE.AE-02
- RS.AN-03
- ID.RA-01
- DE.CM-01
---

# Reverse Engineering Ransomware Encryption Routine

## Role (single ownership)

- **Class:** **FR-07a / FR-07b interpretation workflow** (native or managed) that turns decompiler `file_read` pages into a **per-routine** story: which functions acquire keys, which encrypt buffers, and how material is wrapped for storage. This file is **not** the FR-08/FR-13 scheme mapper (`analyzing-ransomware-encryption-mechanisms`), not the generic Ghidra contract (`ghidra-priority-queue-workflow` / `reverse-engineering-malware-with-ghidra`), and not an IOC or YARA author.

- **Not in scope:** host-side `open()` on the sample, production decryptor execution, paying ransoms, or tools outside the binary_analysis contract surface (`binary-analysis-prompt-optimizer/references/build-contracts.md`, parent orchestrator).

## Upstream, downstream, and return

| Direction | Party | Contract |
|-----------|--------|----------|
| **Who triggers this skill** | `binary-analysis-e2e-orchestrator` **FR-07** path after `decompile_input` and priority-queue steps exist; `binary-analysis-family-triage-workflow` **only when** the specialist table routes past primary `analyzing-ransomware-encryption-mechanisms`; `two-phase-behavior-chain-reconstruction` when the matrix row says to read this skill **second**; `binary-analysis-e2e-orchestrator/references/fr08-signal-matrix.md` ransomware row (secondary, after function-level crypto evidence is plausible). | Load this `SKILL.md` **only if** the evidence snapshot already ties crypto to file operations; skip when only generic imports exist. |
| **Load before this file** | `ghidra-priority-queue-workflow` (FR-07a) or the FR-07b managed path in the orchestrator; `binary-analysis-evidence-chain-protocol` (Proto-02); `analyzing-ransomware-encryption-mechanisms` for scheme context; `binary-analysis-sanitize-untrusted-strings` (Proto-03) before any LLM-facing excerpt. | Facts are appended with `evidence_chain.append_indicator(bucket="disassembly", ...)`; the Indicator field is `source_fr` (Proto-02 — bucket is the append argument, not a JSON key). |
| **Peers** | `reverse-engineering-malware-with-ghidra`, `reverse-engineering-rust-malware`, `analyzing-golang-malware-with-ghidra`, `reverse-engineering-dotnet-malware-with-dnspy` — format-specific reading aids. | |
| **Downstream** | FR-17 `two-phase-behavior-chain-reconstruction` may consume new `function_tag` / `callgraph_edge` facts; FR-08 / FR-13 / FR-15 interpret higher-level impact — not owned here. | |
| **Return to orchestrator** | When decompilation coverage is documented with Proto-02 facts or an `analysis_coverage` downgrade, per `ghidra-priority-queue-workflow` / managed FR-07b tables. | Do not jump to FR-08 from this file alone. |
| **Document / parent path** | If the session is **document-tier** or `doc_analysis_partial` blocks binary crypto facts | Use `document-analysis-e2e-orchestrator` only; this skill is **binary** FR-07. |

## When to use

- Paged decompiler or managed export is **available or expected** under `/workspace/<analysis_id>/` per the active FR-07 workflow, and the question needs **function names**, call order, and **key/IV** handling detail beyond the scheme summary.
- The user or matrix asks to **trace** `CryptEncrypt` / `BCryptEncrypt` / OpenSSL / libsodium / managed crypto surfaces from body code to file writes.
- A **downgrade** path is required when the export is missing or only partial: still stay inside Proto-02 with `analysis_coverage` / `function_tag` discipline.

**Do not use** as the first ransomware skill in a session (start with `analyzing-ransomware-encryption-mechanisms` and orchestrator stage order). **Do not use** to request new `file_identify` calls or to paste raw hexdumps.

## Runtime contract (tools, sandbox, and bytes)

- **Allowed surface** matches the Tool Boundary in the parent audit `contracts.md`: project tools `file_identify` (consume the first-hop `file_meta`; do not re-call unnecessarily), `evidence_chain`, `scoring`, `decision_gate`, `report_gen`; sandbox primitives `bash`, `python_exec`, `file_read`, and `sandbox_session` only after a session exists. External analyzers (Ghidra, dnSpy, FR-04/06/07 recipes) run **only** as commands or scripts inside that sandbox via those primitives — not as additional agent tool names. **`document_extract`** is allowed **only** after `document-analysis-e2e-orchestrator` is loaded and **only** for document formats — never for PE/ELF/Mach-O. **Do not** name `pe_dump`, `network_capture`, `shell_exec`, or `task`.
- **Zero raw sample bytes in LLM context:** decompilation text arrives via paginated `file_read` of exports under the workspace. Any quoted sample-derived string follows Proto-03 and `{open_tag}` / `{close_tag}` from the runtime control plane.
- **Facts vs inference (ADR-03):** decompiler-anchored labels (`decompiled_function`, `function_tag`, `crypto_constant` in **`disassembly`**) are `kind: fact` when traceable to export text or structured tool output. Hypotheses about recoverability, intent, or family belong in **`llm_inferences`** with `kind: inference` and **non-empty** `evidence_refs` to fact ids.

## NFR-05 and prompt control

`{token_budget}`, `{threshold_pct}`, and `{max_rounds}` are defined only in `agent.md` and orchestrator control surfaces. Read `references/api-reference.md` only when a named constant or table row is needed; read `references/workflows.md` for ASCII phase diagrams.

## Workflow

### 1) Gate on upstream facts

- Confirm `decompile_input` and `packer` / `unpack_result` per the orchestrator **input selection** rule before treating exports as authoritative.
- Read existing **`imports`**, **`strings_iocs`**, and **`disassembly`** rows from the evidence snapshot. Prefer citing fact ids over re-deriving PE import tables from memory.

### 2) Map crypto API surfaces to functions

- From paged C/C#/IL text, name the functions that: acquire context, generate or import keys, set IVs/nonces, encrypt buffers, and wrap symmetric material with asymmetric primitives.
- Cross-check against FR-04 `suspicious_import` / triage facts when symbols are thunks; record **`function_tag`** and **`decompiled_function`** per Proto-02 (`source_fr: "FR-07"`), not free-form chat claims.

### 3) Reconstruct a key-flow narrative (bounded)

- State hybrid patterns only when the export or a stored **`crypto_constant`** / string fact supports them (CBC/CTR/GCM, RSA/OAEP vs PKCS#1 v1.5, ChaCha20 IETF). Mark uncertainty with **`analysis_coverage`** instead of fabricating call chains.

### 4) Optional inference for recoverability (strict)

- Weak PRNG, IV reuse, or ECB are **inference** only with explicit `evidence_refs` to the supporting facts. Otherwise emit **`gap_note`** / **`audit_gaps` convention** in `llm_inferences` per Proto-02.

**Example (fact template — replace ids; validate per `Indicator.model_validate` before append):**

```json
{
  "source_fr": "FR-07",
  "indicator_type": "function_tag",
  "severity": "INFO",
  "kind": "fact",
  "evidence_refs": [],
  "data": {
    "address": "0x140001234",
    "name": "FUN_encrypt_file",
    "priority_rank": 2,
    "capability_tags": ["crypto"],
    "source": "ghidra"
  }
}
```

Use the same `data.*` shape as `ghidra-priority-queue-workflow` (address, name, `priority_rank`, `capability_tags`, `source`). For FR-07b managed exports, set `"source"` to the producer the orchestrator documents (for example `dnspy`). Prefer non-empty `evidence_refs` to the active `decompile_priority` / `decompiled_function` row when one exists.

## Degrade and tool-missing

| Situation | Action |
|-----------|--------|
| Ghidra / managed static export missing, timeout, or `fr02_ac8_strategic_skip` | Follow the orchestrator FR-07 table; append `analysis_coverage` in **`disassembly`** with sanctioned `data.reason` values — do not invent per-function flow. |
| Only imports/strings exist, no decompile | Stay at `analyzing-ransomware-encryption-mechanisms` or FR-06 heuristics; do not feign decompiler detail. |
| User asks for IR report, verdict, or YARA | Defer to FR-15 / dedicated skills after facts exist. |

## References (project)

- `references/api-reference.md` — constant and pattern hints (read on demand).
- `references/workflows.md` — high-level phase diagrams (not executable steps).

## External background (non-authoritative)

- [Morphisec - Ransomware encryption overview](https://www.morphisec.com/blog/breaking-down-ransomware-encryption-key-strategies-algorithms-and-implementation-trends/)
- [Emsisoft - Ransomware encryption methods](https://www.emsisoft.com/en/blog/27649/ransomware-encryption-methods/)
- [No More Ransom](https://www.nomoreransom.org/)
- [MITRE ATT&CK T1486](https://attack.mitre.org/techniques/T1486/)
