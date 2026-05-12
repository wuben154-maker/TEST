---
name: extracting-config-from-agent-tesla-rat
description: |
  It describes how to turn FR-04 / FR-06 / FR-07b facts into FR-13
  `llm_inferences` for Agent Tesla–like .NET RATs: exfil method (SMTP, FTP,
  Telegram, Discord), credential-theft and keylogger settings, and C2 or webhook
  endpoints, using only chain facts and sandbox-scoped work—no host-side sample
  I/O. The runtime loads this file after `binary-analysis-family-triage-workflow`
  fires the `agent_tesla` gate (YARA or family hint, .NET or stealer namespace
  evidence, SMTP/FTP/Telegram strings, credential-store paths, or matching
  behavior nodes). Triggers: Agent Tesla, agent tesla, AgentTesla, .NET RAT,
  SMTP exfil, Telegram bot token, keylogger, FR-13, family config, stealer
  config, strings_iocs, disassembly. 中文: Agent Tesla、特斯拉木马、.NET
  窃密、SMTP/电报外泄、家族配置、FR-13 家族门控。It does not replace
  `reverse-engineering-dotnet-malware-with-dnspy` (FR-07b facts) or
  `binary-analysis-family-triage-workflow` (gate and orchestration).
domain: cybersecurity
subdomain: malware-analysis
tags:
- agent-tesla
- rat
- config-extraction
- dotnet
- malware-analysis
- keylogger
- credential-theft
version: '1.0'
author: mahipal
license: Apache-2.0
atlas_techniques:
- AML.T0024
- AML.T0056
- AML.T0086
nist_ai_rmf:
- GOVERN-1.1
- MEASURE-2.7
- MANAGE-3.1
nist_csf:
- DE.AE-02
- RS.AN-03
- ID.RA-01
- DE.CM-01
compatibility: binary_analysis FR-13 · ADR-13 · FR-07b
allowed-tools: file_read evidence_chain
---

# Extracting Config from Agent Tesla RAT

## When to Use

- After `binary-analysis-family-triage-workflow` Step 1 marks the
  **`agent_tesla` gate** as satisfied and selects this specialist (see that
  workflow’s gate table: `.NET` / stealer / SMTP–FTP–Telegram evidence, not a
  lone generic mail host).
- When structured **family config** (exfil channel, partial endpoints,
  high-level settings) should be added to the evidence chain for FR-13
  `scoring`, backed by **existing** `strings_iocs`, `imports`, `disassembly`,
  and optional `behavior_chain` facts.
- When FR-07b (`reverse-engineering-dotnet-malware-with-dnspy`) or FR-06
  surfaces `managed_config_candidate`, decrypted string facts, or cleartext
  IOC rows that plausibly map to Agent Tesla–style exfil (SMTP client APIs,
  `Telegram.Bot`–like imports, FTP upload helpers, Discord webhook URLs).

**Do not use** when the gate’s **“Do not load when”** row is true (only a
generic SMTP string, no .NET or stealer context, or packed sample with
unusable strings). **Do not use** to replace the family triage gate,
Cobalt Strike specialists, or the document orchestrator. **Do not use** to
paste raw sample bytes, full PE content, or un-sanitised creds into prompts.

## Routing (upstream / downstream)

| Direction | Contract |
|-----------|----------|
| **Invoked by** | `binary-analysis-family-triage-workflow` (Workflow-02) when the **`agent_tesla`** row passes; always under `binary-analysis-e2e-orchestrator` **Stage FR-13** after FR-08 triage and prior facts exist. |
| **Must read first** | `binary-analysis-evidence-chain-protocol` (Proto-02) and `binary-analysis-sanitize-untrusted-strings` (Proto-03) before any `llm_inferences` append. |
| **Consumes** | `triage`, `imports`, `strings_iocs`, `disassembly` (FR-07b), optional `behavior_chain` **facts**; it does not create new `strings_iocs` rows without tool backing. |
| **Hands off to** | FR-09 consolidation, FR-08 narrative as scheduled, then FR-13 `scoring` and FR-15 `report_gen` via the parent orchestrator. |
| **Return to orchestrator** | After emitting `family_candidate` and/or `family_config` inferences (or a documented downgrade), do not start a second binary orchestration pass. |
| **Degrade** | See table below. For **document-embedded** binaries, if the child analysis did not complete, follow `document-analysis-e2e-orchestrator` and set **`doc_analysis_partial=true`** per E2E-02; do not assert family config on the parent from partial child text alone. |

## Prerequisites

- Proto-02: `evidence_chain.append_indicator(bucket="llm_inferences", …)`;
  **`kind: inference`** requires **`evidence_refs`** to fact indicator ids;
  `source_fr: "FR-13"`.
- Proto-03: any sample-originated literal in `data` or report text must pass
  `sanitize` and, when embedded in system-controlled templates, use
  `{open_tag}` / `{close_tag}`.
- Upstream **FR-07b** or FR-06 must have produced analyzable .NET or string
  surface; if the sample is only a non-.NET dropper, this specialist cannot
  invent Agent Tesla config.

## Runtime contract

1. **Tool surface (ADR-13 / contracts.md)** — Use only the project runtime
   surface: `file_identify`, `evidence_chain`, `scoring`, `decision_gate`,
   `report_gen`, `bash`, `python_exec`, `file_read`, `sandbox_session`, and
   `document_extract` on the **document** path only. FR-04 / FR-06 / FR-07
   outputs reach this skill as **evidence facts**, not as separate invented
   tool names. Do **not** name `pe_dump`, `network_capture`, `shell_exec`,
   `task`, or host `open()` on the specimen.
2. **Sandbox and zero raw bytes** — Sample bytes live under
   `/workspace/<analysis_id>/` via **`SandboxSessionTool`**. Do not hexdump
   into the LLM. Optional `bash` / `python_exec` digressions (regex, helper
   scripts) run **in the sandbox** with bounded stdout, same as
   `reverse-engineering-dotnet-malware-with-dnspy`.
3. **Facts vs inferences** — SMTP hosts, import rows, and decompiler string
   facts are **`kind: fact`** in their home buckets. “This sample’s exfil
   profile matches Agent Tesla v3-style SMTP+Telegram” is **`kind: inference`**
   in **`llm_inferences`** with **non-empty `evidence_refs`**.
4. **Indicator field names** — Follow Proto-02 / `Indicator`: use
   **`source_fr`** (rubric’s “`source_skill`” maps to this field in code).

## Workflow (evidence alignment)

1. **Confirm gate honesty** — Re-read the family triage `agent_tesla` row;
   if the “Do not load when” conditions now apply, **stop** and let the
   workflow emit `family_absent` or another branch instead of forcing this
   file.
2. **Map exfil and settings to facts** — Correlate SMTP/FTP/Telegram/Discord
   patterns described in `references/api-reference.md` to actual
   `strings_iocs` or `disassembly` indicator ids. Prefer `managed_config_candidate`
   or decompiler-backed rows over uncited prose.
3. **Build `family_config` (when fields are defensible)** — Follow the JSON
   shape in `binary-analysis-family-triage-workflow` Step 3 (`indicator_type:
   "family_config"`, `data.family` / `data.fields` with sanitised or tagged
   literals per Proto-03). Use severity/confidence per that workflow (strong
   multi-field agreement → higher confidence; single weak string → lower).
4. **Optional `family_candidate`** — If the triage step did not already emit a
   candidate, you may add `family_candidate` with
   `data.specialist_skill: "extracting-config-from-agent-tesla-rat"` only when
   evidence supports it.
5. **Never** copy full credentials into `data` — use hash, length, defanged
   fragments, or `<untrusted_sample_content>…` wrappers as required by
   `binary-analysis-sanitize-untrusted-strings`.

## Degrade paths

| Situation | Action |
|-----------|--------|
| FR-07b missing or `analysis_coverage` on `decompilation` (no useful IL/C#) | Do not fabricate `family_config`; cite coverage facts; downgraded narrative only. |
| Strings truncated / FLOSS timeout (`analysis_coverage` on `strings_iocs`) | Lower `confidence`; reference the coverage fact id. |
| Packed, unpack failed or not whitelisted (FR-05) | No high-confidence exfil field extraction; state gap in `rationale` with refs to `packer` / `headers` facts. |
| Document child incomplete (`doc_analysis_partial`) | Defer or mark partial per document orchestrator; do not backfill from parent doc text alone. |
| Only secondary blog-style context, no id-matched facts | Do not `file_read` deeper references until at least one fact id exists to cite. |

## Indicator shape (illustrative)

`bucket` is the `append_indicator` argument, not a field on the JSON body:

```json
{
  "source_fr": "FR-13",
  "kind": "inference",
  "indicator_type": "family_config",
  "severity": "WARNING",
  "confidence": "MEDIUM",
  "evidence_refs": [
    "01STRINGIOCSMTPHOSTFACTEXAMPLE00",
    "01DISASMANAGEDCONFIGCANDIDATE01"
  ],
  "data": {
    "family": "AgentTesla",
    "config_schema": "inferred_smtp_telegram",
    "fields": {
      "exfil_method": "smtp",
      "smtp_port": 587,
      "notes": "Placeholders; real host strings must be sanitised in production append."
    }
  }
}
```

## Budget and reference discipline (NFR-05)

- Load this `SKILL.md` only when the `agent_tesla` gate fires; do not read
  every reference up front.
- When `agent.md` or the parent stage injects `{max_rounds}`,
  `{token_budget}`, or `{threshold_pct}`, stop after one specialist pass
  instead of re-reading the entire decompiler output.
- Deeper pattern tables: `references/api-reference.md` (on demand). Broader
  incident-response context: `references/standards.md`. Human SOAR-style
  flows: `references/workflows.md` — **not** agent tool steps.

## Related skills

- `binary-analysis-family-triage-workflow` (gate and `llm_inferences` shapes)
- `binary-analysis-e2e-orchestrator` (FR-13 stage order)
- `reverse-engineering-dotnet-malware-with-dnspy` (FR-07b facts)
- `binary-analysis-evidence-chain-protocol` (Proto-02)
- `binary-analysis-sanitize-untrusted-strings` (Proto-03)
- `analyzing-command-and-control-communication` (generic C2 when exfil is not
  Agent Tesla–specific)

## Key concepts (short)

| Term | Role |
|------|------|
| Agent Tesla | .NET RAT / stealer; common exfil: SMTP, FTP, Telegram, Discord |
| `agent_tesla` gate | family triage row requiring multi-signal support before this skill loads |
| `family_config` | FR-13 inference summarising extracted fields, always with `evidence_refs` |

## References (on demand)

- `references/api-reference.md` — string/regex and channel patterns (read when mapping facts)
- `references/standards.md` — standards and technique mapping
- `references/workflows.md` — high-level triage order (not a second orchestrator)

External URLs below are **background reading** for analysts; the agent does
not call them as tools.

- [Splunk - Agent Tesla Detection and Analysis](https://www.splunk.com/en_us/blog/security/inside-the-mind-of-a-rat-agent-tesla-detection-and-analysis.html)
- [Qualys - Catching the RAT Agent Tesla](https://blog.qualys.com/vulnerabilities-threat-research/2022/02/02/catching-the-rat-called-agent-tesla)
- [ANY.RUN Agent Tesla Analysis](https://any.run/malware-trends/agenttesla/)
- [Trustwave - Agent Tesla Novel Loader](https://www.trustwave.com/en-us/resources/blogs/spiderlabs-blog/agent-teslas-new-ride-the-rise-of-a-novel-loader/)
- [Malpedia - Agent Tesla](https://malpedia.caad.fkie.fraunhofer.de/details/win.agent_tesla)
