---
name: analyzing-command-and-control-communication
description: >-
  It guides FR-17 behavior-chain analysis for generic malware command-and-control
  (C2): beaconing, HTTP(S) / DNS / custom transports, URI and header patterns,
  TLS fingerprint hints, and infrastructure clustering grounded in static
  evidence. Activates when `two-phase-behavior-chain-reconstruction` delegates
  the `network_c2` or `generic_c2_behavior` row, when
  `binary-analysis-family-triage-workflow` routes `generic_c2`, or when analysts
  ask for C2 / beacon / 命令与控制 /
  通信协议 reasoning inside the binary runtime. It does not add PCAP agents,
  host-side sample reads, or tools outside the project sandbox and
  `evidence_chain` writers.
domain: cybersecurity
subdomain: malware-analysis
tags:
- malware
- C2
- command-and-control
- beacon
- protocol-analysis
version: 1.0.0
author: mahipal
license: Apache-2.0
nist_csf:
- DE.AE-02
- RS.AN-03
- ID.RA-01
- DE.CM-01
---

# Analyzing Command-and-Control Communication

## When to Use

- FR-06 / FR-07 facts already surface **URLs, domains, IPs, User-Agent strings,
  hard-coded paths**, or **network API clusters** (`InternetOpen`, `HttpSendRequest`,
  `WinHttpSendRequest`, `connect`, `send`, `recv`, CFNetwork, POSIX sockets)
  that imply outbound C2.
- `two-phase-behavior-chain-reconstruction` matched the **`network_c2`** /
  **`generic_c2_behavior`** gate and loaded this skill to turn those facts into
  **`behavior_chain`** inferences with citations.
- `binary-analysis-family-triage-workflow` needs **generic C2** interpretation
  (not yet replaced by a HIGH-confidence family workflow such as Cobalt Strike or
  Agent Tesla).
- You must explain **beacon timing, channel choice, encoding, or failover
  hypotheses** while staying inside NFR-05 budget.

**Do not use** as a substitute for FR-06 string extraction, FR-07 decompilation,
or the orchestrator’s **document** path. Do not claim live PCAP, full TLS
session, or passive-DNS artefacts unless they appear as **sanitised, bounded**
facts from allowed tooling (never raw capture bytes or host log dumps in
prompts). For **DNS tunneling, ICMP encapsulation, or steganographic HTTP**
emphasis, prefer **`analyzing-network-covert-channels-in-malware`** per
`binary-analysis-e2e-orchestrator` FR-08 signal matrix.

## Routing (upstream / downstream)

| Direction | Owner |
|-----------|--------|
| **Invoked by** | `two-phase-behavior-chain-reconstruction` (**`network_c2`** / related rows); `binary-analysis-family-triage-workflow` (**`generic_c2`**); FR-08 signal matrix rows that name this skill. Context is **Stage FR-17** under `binary-analysis-e2e-orchestrator`. |
| **Must read first** | `binary-analysis-evidence-chain-protocol` (Proto-02) and `binary-analysis-sanitize-untrusted-strings` (Proto-03) before any chain write. |
| **Consumes** | **`strings_iocs`**, **`imports`**, **`disassembly`** facts (`decompiled_function`, `function_tag`, `callgraph_edge` when present); optional **`behavior_chain`** nodes from earlier modules. |
| **Hands off to** | Gap-04 / orchestrator after **`behavior_chain`** inferences (or explicit `analysis_coverage`); then **FR-09 → FR-08 → FR-13 → FR-14 → FR-15**. |
| **Return to orchestrator** | After C2-oriented nodes are written or a downgrade is recorded; do not fork a second binary orchestrator. |
| **Downgrade** | If FR-07 skipped decompilation, TLS metadata is missing, or only noisy CDN hosts remain after denoise, record **`analysis_coverage`** on `behavior_chain` (e.g. `behavior_chain_unavailable`, `c2_hypothesis_low_signal`) instead of inventing packet-level detail. Prefer already-sanitised FR-06 strings over new dumps. When family-specific C2 fingerprints dominate, defer to **`analyzing-cobalt-strike-beacon-configuration`**, **`analyzing-cobaltstrike-malleable-c2-profiles`**, or **`extracting-config-from-agent-tesla-rat`** per FR-13 gates. |
| **Covert-channel emphasis** | If indicators match DNS/ICMP/custom binary tunnel patterns, read **`analyzing-network-covert-channels-in-malware`** for technique-specific checklist; still keep chain writes consistent with Proto-02. |
| **Document path** | If the active session is **E2E-02** document-first, `document-analysis-e2e-orchestrator` owns document buckets. Set or respect **`doc_analysis_partial=true`** per E2E-02 when recursive budget is exhausted, parent coverage is downgraded, or tool-owned document facts are incomplete; this skill only supplements **child binary** FR-17 reasoning when invoked, does not own that flag, and must not clear it or rewrite document-bucket facts. |

## Runtime Contract

This skill is a **specialist interpretation layer for generic C2 behavior**
inside `binary_analysis`. It does not introduce new agent tools.

1. **Tool surface** — Use only the `audit-runs/<run_id>/contracts.md` 5+3+1
   surface: `file_identify`, `evidence_chain`, `scoring`, `decision_gate`,
   `report_gen`, `bash`, `python_exec`, `file_read`, `sandbox_session`, and
   `document_extract` only after `document-analysis-e2e-orchestrator` for
   document formats. Do **not** name `pe_dump`, `network_capture`, `shell_exec`,
   `task`, or other non-contract tools. Do **not** treat passive-DNS portals,
   PCAP agents, or host packet GUI apps as first-class agent capabilities.
2. **Sandbox and zero raw bytes** — Samples and any optional PCAP live under
   `/workspace/<analysis_id>/` via `sandbox_session`. Do **not** `open()` the
   specimen on the analyst host or paste hexdumps / full HTTP bodies into the
   LLM. Summaries must stay truncated and sanitised per Proto-03. Optional
   analyst command examples belong **only** inside sandbox `bash` / `python_exec`
   with **bounded** stdout (see `references/api-reference.md`), never as mandatory
   agent steps.
3. **Facts vs inferences** — URLs, domains, IPs, mutexes, import names, and
   literals observed by tools stay **`kind: fact`** in their home buckets
   (typically `strings_iocs` / `imports` / `disassembly`). **Beacon models,
   protocol labels, framework guesses, MITRE mappings, and infrastructure
   narratives** are **`kind: inference`** in the **`behavior_chain`** bucket
   (append only via the **`evidence_chain`** tool) with non-empty `evidence_refs`
   to those fact ids. Use **`source_fr`** (the implemented Indicator field;
   rubric text may say `source_skill` but the schema is `source_fr`) of
   **`"FR-17"`** for FR-17 outputs. Severity uses **INFO / WARNING / CRITICAL**
   only; confidence uses **HIGH / MEDIUM / LOW** when `kind` is `inference`.
   Prefer `indicator_type` values that already exist in the project vocabulary
   (for example `c2_exfil_node`, `module_chain_summary`,
   `targeted_attack_indicator`, `analysis_coverage`) rather than inventing new
   types.
4. **Untrusted snippets** — When quoting sample-derived text in prompts, wrap
   with `{open_tag}` / `{close_tag}` per `agent.md` and sanitise per Proto-03
   before persistence.
5. **Budget** — Respect `{max_rounds}`, `{token_budget}`, and `{threshold_pct}`
   from `agent.md`: prefer short `file_read` windows on skill references and
   already-materialised facts before expanding prose.

## Workflow

### Step 1 — Anchor on static facts

From **sanitised** FR-06 / FR-07 facts, list candidate **endpoints** (scheme,
host, port hints), **periodicity cues** (sleep/jitter strings, timer APIs), and
**encoding hints** (Base64, XOR constants, custom magic). Map each cluster to
**function_tag** / **decompiled_function** facts via `callgraph_edge` when
available; otherwise cite string / import ids only.

### Step 2 — Classify the channel (inference)

Hypothesise transport (**HTTP(S)**, **DNS**, **raw TCP/UDP**, **named pipe / SMB**,
**cloud API**) with explicit uncertainty. If the static picture is ambiguous,
emit **MEDIUM** or **LOW** confidence and list alternative channels in
`data.notes` rather than asserting packet-level truth.

### Step 3 — Separate generic vs family-specific

If strings/config patterns match a **known framework** handled by dedicated
skills, **cite those skills in prose** and avoid duplicating their extraction
recipes; keep this skill’s chain entries focused on **gaps** or **cross-cutting
links** (for example how unpacking exposes network initialisation).

### Step 4 — Write `behavior_chain` inferences

For each C2 hypothesis, append indicators with:

- `kind: inference`, required `confidence`, non-empty `evidence_refs`.
- `data.capability` or module metadata consistent with `network_c2` usage in
  `two-phase-behavior-chain-reconstruction`.
- Optional `data.protocol_hint`, `data.transport`, `data.ioc_summary` (all
  sanitised) aligned with FR-08 threat-class conventions.

If work stops early, add `indicator_type: analysis_coverage` in the appropriate
bucket per Proto-02.

### Step 5 — Detection-oriented summary (non-authoritative)

Suricata/YARA-style examples belong in **reports or analyst notes**, not as
executable agent steps. When suggesting signatures, tie every literal back to a
**fact id** so scoring can trace provenance.

## Key Concepts

| Term | Definition |
|------|------------|
| **Beaconing** | Periodic check-in from implant to C2; static artefacts often include sleep/jitter configuration strings or timer loops. |
| **Jitter** | Randomised delay around a base interval to evade simple timing detection. |
| **Malleable profile** | Operator-controlled shaping of HTTP(S) C2 (handled in depth by the Cobalt Strike profile skill). |
| **Failover channel** | Alternate host, port, or protocol declared in strings or reachable only after primary failure. |

Deeper packet-tool syntax and optional sandbox command snippets live in
`references/api-reference.md`.

## Output Shape (for reports / FR-08 handoff)

Keep prose aligned with evidence chain facts:

- **Endpoints** — defanged summaries only; cite fact ids.
- **Hypothesised framework** — label as inference with confidence.
- **Gaps** — missing TLS metadata, unresolved CDN noise, or absent decompilation;
  mirror with `analysis_coverage` rows.

Do not fabricate JA3 hashes, certificate fields, or registration dates without a
corresponding fact or explicit downgrade.
