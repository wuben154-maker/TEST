---
name: performing-yara-rule-development-for-detection
description: |
  Provides optional FR-15 methodology for drafting YARA or YARA-X rules from
  sandbox-derived strings, imports, and byte patterns, with false-positive
  discipline and performance-aware conditions. It is loaded only when the
  call site requests a YARA report appendix, not for default chain-only runs.
  Triggers: YARA rule, YARA-X, signature development, malware detection,
  pattern matching, family rule, threat hunting, retrohunt, PE strings.
  中文: YARA 规则、检测签名、误报控制、FR-15 附录、恶意软件检测。
domain: cybersecurity
subdomain: malware-analysis
tags:
- yara
- malware-detection
- signature-development
- threat-hunting
- pattern-matching
- yara-x
- indicator-development
version: '1.0'
author: mahipal
license: Apache-2.0
nist_csf:
- DE.AE-02
- RS.AN-03
- ID.RA-01
- DE.CM-01
compatibility: binary_analysis FR-15 optional appendix (YARA) · not a Proto-02 owner
allowed-tools: sandbox_session bash python_exec file_read evidence_chain
---

# Performing YARA Rule Development for Detection

> **Scope:** Methodology and pattern reference for optional **YARA / YARA-X**
> detection rules. Runtime reporting stays on `report_gen` outputs: draft rule
> text is for the human-facing appendix, not a substitute for `evidence_chain`
> facts unless the product workflow explicitly says otherwise. Read
> `binary-analysis-evidence-chain-protocol` (Proto-02) and
> `binary-analysis-sanitize-untrusted-strings` (Proto-03) before pasting any
> sample-derived text into LLM messages.

## Upstream / downstream

| Direction | Skill or stage |
|-----------|----------------|
| **Who loads this** | `binary-analysis-e2e-orchestrator` / `document-analysis-e2e-orchestrator` at **FR-15** only when the **call site requests a YARA appendix**. |
| **Who is upstream** | Same orchestrators after `file_identify` and prior stages have produced facts; use existing `strings_iocs`, structure, and behavior context—do not re-identify the sample on the host. |
| **Dependencies (read first)** | `binary-analysis-evidence-chain-protocol` (Proto-02), `binary-analysis-sanitize-untrusted-strings` (Proto-03). |
| **Complements** | `extracting-iocs-from-malware-samples` / `binary-analysis-ioc-extraction-workflow` (FR-06) for string taxonomy; `binary-analysis-family-triage-workflow` when family labels matter. |
| **After this skill** | Return control to the active orchestrator. Emit YARA as **report appendix** text. **Do not** use `file_read` on `report_gen` host `md_path` (orchestrator guard). |

**Document path:** If `doc_analysis_partial=true` or coverage is thin, state limitations in the appendix prose; do not claim full-file YARA coverage.

## When to Use

- The user or integration explicitly asked for a **YARA (or YARA-X) appendix** in the final report.
- You are at **FR-15** and need durable string / hex / import anchors that survive recompilation, distinct from one-off `strings_iocs` rows.
- You need **rule structure**, condition ordering, and **F/P tradeoffs** for a hand-off to engineers or a hunt platform.

**Do not use** to justify reading sample bytes on the analyst host, importing ad hoc tools, or streaming raw hexdumps into the model without Proto-03 wrapping.

## Operating constraints (hard)

- **Sandbox only:** String extraction, `pefile`, YARA compile/match, and benchmarks run under `sandbox_session` on paths under `/workspace/<analysis_id>/`. Never `open()` the user’s local sample path from host Python or shell.
- **No raw bytes in LLM context:** Use summarized indicators and sanitized snippets only; long literals belong in the appendix block, not in chat, unless wrapped per Proto-03.
- **Tool surface:** Use only the contract set (e.g. `sandbox_session`, `bash`, `python_exec`, `file_read`, `evidence_chain`, and `document_extract` on document routes when the document orchestrator is active). Do not assert `pe_dump`, `network_capture`, `shell_exec`, or `task`.
- **Budget:** Respect `{token_budget}`, `{threshold_pct}`, and `{max_rounds}` from the runtime prompt. Load `references/api-reference.md` on demand; do not preload every table when the budget is tight.
- **Fact vs inference:** YARA *draft* text is analyst deliverable. Campaign attribution, VT verdict, or “this sample is X family” without evidence refs belongs in `llm_inferences`, not in fact buckets.

## Overview

YARA and YARA-X match textual and binary patterns to classify and hunt malware.
Good rules bind unique stack strings, C2 URL shapes, mutex names, crypto
constants, and import/API combinations while avoiding packer noise and
compiler boilerplate. Prefer unpacked or primary payloads when
`unpack_result.status="success"`; otherwise mark coverage gaps explicitly.

## Key concepts (summary)

- **Sections:** `meta` (context), `strings` (text / hex / regex), `condition` (boolean logic with `filesize`, `uint16`, and short-circuit-friendly order).
- **Anchors:** Family-unique strings; avoid generic `msvcrt` / `kernel32` noise unless combined with rarer neighbors.
- **Performance:** Cheapest, most selective checks first; limit `filesize`; prefer hex over heavy regex; use `private` subrules when composing.

## Workflow

1. **Ground in existing facts** — Reuse FR-04 / FR-06 / FR-17 outputs from the chain; add sandbox-only `string_extract` / `python_exec` work only for gaps, inside `/workspace/<analysis_id>/`.
2. **Draft the rule** — Name, `meta` (author, `description`, TLP, reference hash), `strings`, and `condition` with F/P checks described in `references/standards.md`.
3. **Validate in sandbox** — `yara.compile` and match against a **sandbox-local** corpora path; never point scans at the analyst’s home directory.

**Long examples, yara-python tables, and illustrative scripts** live in
`references/api-reference.md` (read progressively).

## Degrade / partial paths

- **Insufficient unique strings:** Emit a *partial* rule with `gap_note`-style
  prose in the appendix; recommend FR-05 unpack or FR-07 follow-up; do not fake matches.
- **YARA compile error:** Return syntax error line; strip to a minimal `meta`+`strings` shell if needed.
- **Sandbox tool missing:** Record `tool_missing` in narrative; do not claim validated coverage.

## Validation criteria (targets)

- Rule source compiles (`yara` or `yara-x` in sandbox).
- Intended positives covered on the **sandbox** test set; clean-corpus F/P
  rate meets team policy (e.g. well below 0.1% for broad rules).
- Scan throughput sufficient for the deployment context (e.g. large corpus jobs).
- `meta` includes description, author, date, and TLP where policy requires.

## External references (language & ecosystem)

- [YARA documentation](https://virustotal.github.io/yara/)
- [YARA-X (Rust implementation)](https://github.com/VirusTotal/yara-x)
- [Yara-Rules community](https://github.com/Yara-Rules/rules)
- [ReversingLabs — YARA for malware detection](https://www.reversinglabs.com/blog/writing-detailed-yara-rules-for-malware-detection)
- [YARA rule crafting (threat hunting)](https://cyberthreatintelligencenetwork.com/index.php/2024/09/11/yara-rule-crafting-a-deep-dive-into-signature-based-threat-hunting-strategies/)
