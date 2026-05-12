---
name: analyzing-cobaltstrike-malleable-c2-profiles
description: >-
  It interprets Cobalt Strike Malleable C2 profile DSL (HTTP/DNS request blocks,
  transforms, sleep/jitter) and static profile-shaped cues in the evidence
  chain to support network and signature-oriented indicators for
  `binary-analysis-family-triage-workflow` when the `cobalt_strike` gate
  is active, when URI/User-Agent/headers in `strings_iocs` match a known
  profile class, or when analysts ask for Malleable C2 / malleable profile /
  C2 伪装 / URI 指纹 reasoning after base beacon facts. It defers full beacon
  TLV extraction to `analyzing-cobalt-strike-beacon-configuration`. It uses
  only the project sandbox, `python_exec` / `bash` under
  `sandbox_session`, and `evidence_chain` writers; no host-side sample reads
  or non-contract tools.
domain: cybersecurity
subdomain: malware-analysis
tags:
- cobalt-strike
- malleable-c2
- c2-detection
- beacon-analysis
- network-signatures
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
---

# Analyzing Cobalt Strike Malleable C2 Profiles

## When to Use

- **`binary-analysis-family-triage-workflow`** raised **`cobalt_strike`**
  and you need **profile-level** interpretation (GET/POST blocks, URI
  templates, header/metadata transforms) **after** or **alongside** primary
  **`analyzing-cobalt-strike-beacon-configuration`** work.
- **`strings_iocs`** (or `disassembly` commentary) already contains **profile
  fragments** (for example `http-get`, `http-post`, `set uri`, or
  recognisable malleable section labels) and you must map them to
  **defensive signatures** and structured indicators without fabricating
  packet captures.
- Analysts request **Malleable C2**, **Cobalt Strike profile**, **HTTP
  staging / metadata transforms**, or **可塑性 C2 / 配置文件** analysis in
  the `binary_analysis` runtime.

**Do not use** to replace `analyzing-cobalt-strike-beacon-configuration`
when the task is **beacon configuration extraction from a PE or dump**. Do
not treat **Suricata / Snort deployment** or **PCAP live capture** as
first-class **agent** capabilities; optional offline commands belong only
in **bounded** `bash` / `python_exec` inside `sandbox_session` (see
`references/api-reference.md`).

## Routing (upstream / downstream)

| Direction | Owner |
| --- | --- |
| **Invoked by** | `binary-analysis-family-triage-workflow` ( **`cobalt_strike`**, *secondary* for **profile shaping** per Workflow-02); optional context from `analyzing-command-and-control-communication` when C2 string signals overlap. Stage is **FR-13** family reasoning under `binary-analysis-e2e-orchestrator`. |
| **Must read first** | `binary-analysis-evidence-chain-protocol` (Proto-02) and `binary-analysis-sanitize-untrusted-strings` (Proto-03) before any new chain write. |
| **Consumes** | `strings_iocs`, `disassembly` / decompile facts, `file_meta` path hints, and any existing **`analyzing-cobalt-strike-beacon-configuration`** family facts. |
| **Peers / defer** | **`analyzing-cobalt-strike-beacon-configuration`** (beacon config authority); `extracting-config-from-agent-tesla-rat` when the gate is not Cobalt Strike. |
| **Hands off to** | FR-13 scoring path via orchestrator: **FR-09** evidence polish then **FR-08**; no duplicate orchestrator. |
| **Return to orchestrator** | After `family_config` or `analysis_coverage` is recorded, or a downgrade path is explicit. |
| **Downgrade** | Profile parser unavailable in sandbox, incomplete profile text only, or libraries missing in the worker image: emit `analysis_coverage` in **`llm_inferences`** and cite sanitised `strings_iocs` facts only. Do not invent full profile AST without tool-backed fragments. If **E2E-02** document path is active, respect `document-analysis-e2e-orchestrator` and **`doc_analysis_partial=true`** when document recursion or budget limits leave profile text partial; this skill only assists **child binary** or **text artefact** interpretation when loaded, and does not rewrite document-bucket **tool-owned** facts. |

## Runtime contract

1. **Tool surface** — Use only the project **5+3+1** set: `file_identify`,
   `evidence_chain`, `scoring`, `decision_gate`, `report_gen`, `bash`,
   `python_exec`, `file_read`, `sandbox_session`, and `document_extract`
   **only** after `document-analysis-e2e-orchestrator` and **only** for
   document-class inputs. Do **not** name `pe_dump`, `network_capture`,
   `shell_exec`, or `task`.
2. **Sandbox and zero raw bytes** — Sample bytes and any optional derived
   files stay under `/workspace/<analysis_id>/` via `sandbox_session`. Do
   not `open()` specimens on the analyst host. Do not paste hexdumps, full
   profile bodies, or long HTTP transaction dumps into the LLM: wrap
   short excerpts with `{open_tag}` / `{close_tag}` and run **Proto-03**
   sanitisation before persistence.
3. **Facts vs inferences** — Tool-extracted URLs, hostnames, literals, and
   import or string table entries stay **`kind: fact`** in their home
   buckets. **Profile class labels, transform chains, and signature
   hypotheses** are **`kind: inference`** in **`llm_inferences`**
   (typically as **`family_config`** or structured narrative under FR-13
   routing) with non-empty `evidence_refs` to the underlying fact
   indicator ids. Use **`source_fr: "FR-13"`** for these outputs. Prefer
   existing `indicator_type` / vocabulary entries (for example
   `family_config`, `analysis_coverage`, `c2_exfil_node`) per Proto-02
   rather than ad-hoc type names. Reference **`Bucket` enum** names in text
   (for example `llm_inferences`, `strings_iocs`); do not invent
   paraphrased Chinese bucket names in JSON payloads.
4. **Budget** — Respect `{max_rounds}`, `{token_budget}`, and
   `{threshold_pct}` from `agent.md`. Read `references/api-reference.md` on
   demand (progressive disclosure); do not pre-load the whole reference
   every round.

## Workflow

1. **Anchor on facts** — List sanitised **URI**, **User-Agent**, **Host**,
   **spawnto**-like, and **sleep/jitter** strings already in `strings_iocs` /
   related facts. Confirm whether `analyzing-cobalt-strike-beacon-configuration`
   already produced overlapping indicators to avoid duplicate **fact**
   records.
2. **Resolve profile text** — If a `*.profile` (or similar) was uploaded to
   the workspace, use `file_read` / `python_exec` **inside**
   `sandbox_session` to parse (optional third-party modules such as
   `dissect.cobaltstrike` / `pyMalleableC2` are invoked only in that
   context; see `references/api-reference.md`). If only substrings exist,
   stay at fragment-level reasoning and mark coverage limitations.
3. **Map to detections** — For each high-value channel (for example
   `http-get` / `http-post` blocks, DNS beacons, pipenames), list **defensive
   observables** (content matches, header predicates) as **human-oriented
   signature hints**; do not claim live IDS deployment.
4. **Write chain** — Append **`family_config`**-style inferences to
   **`llm_inferences`** with `evidence_refs` and calibrated **confidence**;
   if parsing failed, add **`analysis_coverage`** (`kind: fact` per Proto-02
   patterns used elsewhere) with the reason and retain partial facts only.

## Output expectations

- Structured narrative plus optional JSON-style summary in report output
  (FR-15) listing **C2 channel shape** (schemes, paths, user agents,
  sleep/jitter) and **signature-oriented** hints, all without embedding
  unsanitised long secrets.
- For detailed API names, key tables, and **Suricata-style** rule sketches,
  see `references/api-reference.md`.
