---
name: analyzing-cobalt-strike-beacon-configuration
description: >-
  It guides FR-13 Cobalt Strike beacon configuration reasoning: XOR-wrapped TLV
  blobs, C2 host lists, sleep/jitter, watermark, spawnto, and pipe settings,
  grounded in FR-04/FR-06/FR-07 facts and bounded sandbox parsing only. It
  activates when `binary-analysis-family-triage-workflow` satisfies the
  `cobalt_strike` gate, when analysts ask for beacon config / BeaconType /
  Cobalt Strike watermark / CS beacon / 信标配置 / C2 解析 after triage, or when
  `analyzing-cobaltstrike-malleable-c2-profiles` needs authoritative TLV-level
  facts. It defers Malleable C2 DSL interpretation to
  `analyzing-cobaltstrike-malleable-c2-profiles`. Runtime uses only ADR-13
  tools plus `sandbox_session`; no host-side sample I/O.
domain: cybersecurity
subdomain: malware-analysis
tags:
- cobalt-strike
- beacon
- c2
- malware-analysis
- config-extraction
- threat-hunting
- red-team-tools
version: '1.0'
author: mahipal
license: Apache-2.0
nist_csf:
- DE.AE-02
- RS.AN-03
- ID.RA-01
- DE.CM-01
compatibility: binary_analysis FR-13 · schema_version 1.0.0
allowed-tools: evidence_chain file_read python_exec bash sandbox_session
metadata:
  id: Skill-FR13-CobaltBeacon
  batch: C8
  adr: ADR-03, ADR-05, ADR-13
  fr: FR-13
  stability: stable
---

# Analyzing Cobalt Strike Beacon Configuration

## When to Use

- **`binary-analysis-family-triage-workflow`** selects the **`cobalt_strike`**
  gate and needs **primary** beacon **TLV / XOR config** extraction reasoning
  (not only HTTP profile shaping).
- **`analyzing-cobaltstrike-malleable-c2-profiles`** already ran or is queued
  and you must **anchor** profile hypotheses to **decoded beacon fields**
  (domains, ports, User-Agent, watermark) without duplicating that skill’s DSL
  work.
- Analysts request **beacon configuration**, **Cobalt Strike watermark**,
  **BeaconType**, **sleep/jitter from config**, **named pipe beacon**, or
  **信标 / CS 配置** analysis inside the `binary_analysis` runtime.

**Do not use** as a substitute for **`analyzing-cobaltstrike-malleable-c2-profiles`**
when the task is **pure malleable profile** interpretation with no TLV blob.
**Do not** claim **live PCAP capture**, **host Volatility**, or **Wireshark**
as agent tools; optional bounded commands run only inside **`sandbox_session`**.

## Routing (upstream / downstream)

| Direction | Owner |
| --- | --- |
| **Invoked by** | `binary-analysis-family-triage-workflow` (**`cobalt_strike`**, **primary** beacon specialist per Workflow-02); stage **FR-13** under `binary-analysis-e2e-orchestrator`. |
| **Must read first** | `binary-analysis-evidence-chain-protocol` (Proto-02) and `binary-analysis-sanitize-untrusted-strings` (Proto-03) before new chain writes. |
| **Consumes** | `triage`, `headers`, `sections`, `imports`, `strings_iocs`, `disassembly`, optional `packer` / `entropy` facts; optional **`unpack_with_upx`** outcome when packing obscures config. |
| **Peers / defer** | **`analyzing-cobaltstrike-malleable-c2-profiles`** (malleable DSL and signature shaping); `extracting-config-from-agent-tesla-rat` when the gate is not Cobalt Strike; generic C2 hygiene stays in `analyzing-command-and-control-communication`. |
| **Hands off to** | FR-09 evidence consolidation, FR-08 narrative, then FR-13 `scoring` / FR-15 `report_gen` via the orchestrator—no second orchestrator instance. |
| **Return to orchestrator** | After `family_config` / `family_candidate` inferences (or explicit downgrade) are recorded in `llm_inferences`. |
| **Downgrade** | Packed sample with no unpack path, truncated strings, or sandbox parser failure: append **`analysis_coverage`** with `status: "DEGRADED"` / `"SKIPPED"` in the most relevant bucket (`packer`, `strings_iocs`, or `llm_inferences`) and cite only existing facts—no fabricated TLV rows. If **E2E-02** is active and document recursion or budget forces partial coverage, set **`doc_analysis_partial=true`** per `document-analysis-e2e-orchestrator`; do not assert full beacon config from parent text alone. |

## Runtime contract

1. **Tool surface (ADR-13)** — Use only the project **5+3+1** tool family:
   `file_identify`, `evidence_chain`, `scoring`, `decision_gate`, `report_gen`,
   `bash`, `python_exec`, `file_read`, `sandbox_session`, plus analysis helpers
   **`binary_view`**, **`string_extract`**, **`import_view`**, **`entropy_view`**,
   **`disasm_decompile`**, **`decompile_function`**, **`unpack_with_upx`** as
   scheduled by the orchestrator. **`document_extract`** only on the document
   path after `document-analysis-e2e-orchestrator`. Do **not** name `pe_dump`,
   `network_capture`, `shell_exec`, or `task`.
2. **Sandbox and zero raw bytes** — Staged samples and derived artefacts stay
   under `/workspace/<analysis_id>/` via **`sandbox_session`**. Do not `open()`
   specimens on the analyst host. Do not paste full hexdumps or entire TLV
   blobs into prompts: use short excerpts wrapped with **`{open_tag}`** /
   **`{close_tag}`** and Proto-03 sanitisation before persistence or LLM replay.
3. **Facts vs inferences** — Tool-backed strings (URLs, hosts, literals from
   `string_extract` / `binary_view` / decompiler) belong in their home buckets
   as **`kind: fact`**. **Decoded field labels, watermark attribution
   hypotheses, and campaign clustering** are **`kind: inference`** in
   **`llm_inferences`** (for example `family_config`, `family_candidate`,
   `family_divergence`) with non-empty **`evidence_refs`** to fact indicator ids
   and **`source_fr: "FR-13"`**. Reference **`Bucket`** enum names in prose
   (`strings_iocs`, `llm_inferences`, …); do not invent Chinese bucket aliases
   in JSON.
4. **Budget** — Respect **`{max_rounds}`**, **`{token_budget}`**, and
   **`{threshold_pct}`** from `agent.md`. Load `references/api-reference.md`
   and `references/workflows.md` on demand (progressive disclosure), not
   every round.

## Workflow

1. **Anchor on static facts** — Confirm PE/COFF or shellcode context from
   `file_meta` / `headers` / `sections`. Review `strings_iocs` for beacon
   markers, pipe patterns, and HTTP surface already sanitised upstream.
2. **Handle packing** — If `packer` or entropy facts suggest compression, rely
   on orchestrator-scheduled **`unpack_with_upx`** or document the skip via
   **`analysis_coverage`**; do not claim a decoded config without a plausible
   unpacked view.
3. **Locate config surface** — Use **`binary_view`**, **`string_extract`**,
   and **`disasm_decompile`** / **`decompile_function`** outputs already in
   the chain; optional **`python_exec`** inside **`sandbox_session`** may run
   helpers such as `dissect.cobaltstrike` **only** in that context (see
   `references/api-reference.md`).
4. **Decode heuristically** — Apply XOR key candidates (**`0x2e`** CS 4.x,
   **`0x69`** CS 3.x) and TLV parsing rules from `references/standards.md`;
   treat uncertain parses as partial and downgrade explicitly.
5. **Write chain** — Append **`family_config`**-style inferences to
   **`llm_inferences`** with calibrated **`confidence`** and **`evidence_refs`**
   to `strings_iocs` / `disassembly` / `imports` facts. Record **`analysis_coverage`**
   when parsers fail or inputs are incomplete.

## Key concepts (summary)

- **TLV blob** — Type-Length-Value records for BeaconType, C2Server, sleep,
  jitter, User-Agent, watermark, spawnto, and pipe name fields (detail:
  `references/standards.md`).
- **XOR wrapper** — Single-byte XOR on the config blob; version-dependent keys
  above.
- **Watermark** — License-derived integer useful for clustering; attribution
  statements stay **`inference`** unless a fact row already encodes the numeric
  value from tools.

## Output expectations

- FR-15-facing narrative listing **actionable C2 endpoints**, **callback timing**,
  **spawn targets**, and **pipe names**, all traceable to fact ids—no
  unsanitised secrets inline.
- For field ID tables, optional parser commands, and defensive rule sketches,
  see `references/api-reference.md`. For end-to-end flow diagrams, see
  `references/workflows.md`.

## References

- `binary-analysis-evidence-chain-protocol/SKILL.md` (Proto-02)
- `binary-analysis-sanitize-untrusted-strings/SKILL.md` (Proto-03)
- `binary-analysis-family-triage-workflow/SKILL.md` (gate table)
- `analyzing-cobaltstrike-malleable-c2-profiles/SKILL.md` (profile peer)
- External deep links: `references/api-reference.md` (curated list)
